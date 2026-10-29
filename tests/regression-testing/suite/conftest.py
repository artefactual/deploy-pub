"""pytest and pytest-bdd glue: fixtures, markers, checklist coverage and evidence hooks."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page
from pytest_bdd.parser import Feature, Scenario, Step

from rt.checklist import ChecklistItem, load_checklist
from rt.evidence import FAIL, KNOWN, PASS, Evidence, slugify
from rt.known_failures import KnownFailures, load_known_failures
from rt.pipeline.am_api import AMClient
from rt.pipeline.container import Container
from rt.pipeline.fpr import FPR
from rt.pipeline.processing_config import config_name
from rt.pipeline.ss_api import SSClient
from rt.pipeline.web import Dashboard, StorageSite
from rt.scenario import ScenarioConfig
from rt.settings import Settings

pytest_plugins = [
    "steps.pipeline_steps",
    "steps.mets_steps",
    "steps.normalization_steps",
    "steps.format_steps",
    "steps.failure_steps",
    "steps.fpr_steps",
    "steps.admin_steps",
    "steps.transfer_tab_steps",
    "steps.metadata_steps",
    "steps.manual_normalization_steps",
    "steps.ui_steps",
    "steps.storage_steps",
    "steps.atom_steps",
    "steps.contentdm_steps",
    "steps.mets_validation_steps",
    "steps.backlog_steps",
    "steps.appraisal_steps",
    "steps.arrangement_steps",
]

ITEM_TAG = "item-"
SHARD_TAG = "shard-"
NEEDS_TAG = "needs-"

EVIDENCE_KEY = pytest.StashKey[Evidence]()
THEN_INDEX_KEY = pytest.StashKey[int]()
COVERAGE_KEY = pytest.StashKey[tuple[list[str], list[str]]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("regression-testing")
    group.addoption(
        "--shard", action="store", default=None, help="run only the scenarios tagged @shard-<name>"
    )
    group.addoption(
        "--strict-coverage",
        action="store_true",
        default=False,
        help="fail when a checklist item has no scenario",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "item(id): checklist item verified by the scenario")
    config.addinivalue_line("markers", "shard(name): workflow shard the scenario runs in")
    config.addinivalue_line("markers", "needs(name): companion the scenario needs (browser, atom, mail)")


def pytest_bdd_apply_tag(tag: str, function: Callable[..., Any]) -> Callable[..., Any] | None:
    marked: Callable[..., Any]
    if tag.startswith(ITEM_TAG):
        marked = pytest.mark.item(tag[len(ITEM_TAG) :])(function)
    elif tag.startswith(SHARD_TAG):
        marked = pytest.mark.shard(tag[len(SHARD_TAG) :])(function)
    elif tag.startswith(NEEDS_TAG):
        marked = pytest.mark.needs(tag[len(NEEDS_TAG) :])(function)
    else:
        return None
    return marked


def _item_id(test: pytest.Item) -> str | None:
    marker = test.get_closest_marker("item")
    return str(marker.args[0]) if marker and marker.args else None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    checklist = load_checklist()
    shard = config.getoption("--shard")
    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    covered: set[str] = set()
    for test in items:
        item_id = _item_id(test)
        if item_id is not None and item_id not in checklist:
            raise pytest.UsageError(f"{test.nodeid}: unknown checklist item {item_id!r}")
        if item_id is not None:
            covered.add(item_id)
        keep = True
        shard_marker = test.get_closest_marker("shard")
        if shard and (shard_marker is None or shard_marker.args[0] != shard):
            keep = False
        (selected if keep else deselected).append(test)
    if deselected:
        items[:] = selected
        config.hook.pytest_deselected(items=deselected)
    ordered = sorted(covered, key=lambda identifier: checklist[identifier].sort_key)
    missing = [identifier for identifier in checklist if identifier not in covered]
    config.stash[COVERAGE_KEY] = (ordered, missing)
    if config.getoption("--strict-coverage") and missing:
        raise pytest.UsageError(f"{len(missing)} checklist items have no scenario: {', '.join(missing)}")


def pytest_terminal_summary(terminalreporter: Any, config: pytest.Config) -> None:
    covered, missing = config.stash.get(COVERAGE_KEY, ([], []))
    terminalreporter.write_sep("-", "checklist coverage")
    terminalreporter.write_line(
        f"{len(covered)} of {len(covered) + len(missing)} checklist items have a scenario"
    )
    if missing:
        terminalreporter.write_line("items without a scenario: " + ", ".join(missing))


# Fixtures --------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture(scope="session")
def am(settings: Settings) -> AMClient:
    return AMClient(settings.am_url, settings.am_user, settings.am_api_key, password=settings.am_password)


@pytest.fixture(scope="session")
def known_failures() -> KnownFailures:
    return load_known_failures()


@pytest.fixture(scope="session")
def fpr(am: AMClient) -> FPR:
    return FPR(am)


@pytest.fixture(scope="session")
def dashboard(am: AMClient) -> Dashboard:
    return Dashboard(am)


@pytest.fixture
def state() -> dict[str, Any]:
    """Facts a scenario records in one step for its later steps."""
    return {}


@pytest.fixture
def restore(evidence: Evidence) -> Iterator[list[tuple[str, Callable[[], None]]]]:
    """Actions that put the global state of the pipeline back, run in reverse order at the end."""
    actions: list[tuple[str, Callable[[], None]]] = []
    yield actions
    for label, action in reversed(actions):
        try:
            action()
        except Exception as err:  # noqa: BLE001 - every restore action must get its turn
            evidence.warn(f"could not restore {label}: {err}")
        else:
            evidence.note(f"restored {label}")


@pytest.fixture(scope="session")
def ss(settings: Settings) -> SSClient:
    return SSClient(settings.ss_url, settings.ss_user, settings.ss_api_key, password=settings.ss_password)


@pytest.fixture(scope="session")
def storage_site(ss: SSClient) -> StorageSite:
    return StorageSite(ss)


@pytest.fixture(scope="session")
def container(settings: Settings) -> Container:
    return Container(settings)


@pytest.fixture(scope="session")
def checklist() -> dict[str, ChecklistItem]:
    return load_checklist()


@pytest.fixture(scope="session")
def am_version(am: AMClient) -> str:
    return am.version()


@pytest.fixture
def item(request: pytest.FixtureRequest, checklist: dict[str, ChecklistItem]) -> ChecklistItem | None:
    item_id = _item_id(request.node)
    return checklist[item_id] if item_id is not None else None


@pytest.fixture
def scenario_config(request: pytest.FixtureRequest, item: ChecklistItem | None) -> ScenarioConfig:
    name = (
        config_name(item.id) if item is not None else "rt" + slugify(request.node.name).replace("-", "")[:12]
    )
    return ScenarioConfig(name=name)


def _is_scenario(request: pytest.FixtureRequest) -> bool:
    """Whether the test is a pytest-bdd scenario, which takes the example of its outline as a fixture."""
    return "_pytest_bdd_example" in request.fixturenames


@pytest.fixture(autouse=True)
def _scenario_evidence(request: pytest.FixtureRequest) -> None:
    """Give every scenario its evidence bundle; the unit tests of the suite get none."""
    if _is_scenario(request):
        request.getfixturevalue("evidence")


@pytest.fixture
def evidence(
    request: pytest.FixtureRequest,
    settings: Settings,
    container: Container,
    item: ChecklistItem | None,
    am_version: str,
    known_failures: KnownFailures,
) -> Iterator[Evidence]:
    if item is not None and not item.applies_to(am_version):
        pytest.skip(f"item {item.id} is in the checklist of Archivematica {', '.join(item.releases)} only")
    folder = item.id if item is not None else slugify(request.node.name)
    directory = settings.evidence_dir / settings.os_label / folder
    if directory.exists():
        shutil.rmtree(directory)
    evidence = Evidence(
        directory=directory,
        os_label=settings.os_label,
        item=item,
        scenario_name=request.node.name,
        feature_file=Path(str(request.node.fspath)).name,
        known=known_failures,
    )
    evidence.versions["archivematica"] = am_version
    request.node.stash[EVIDENCE_KEY] = evidence
    request.node.stash[THEN_INDEX_KEY] = 0
    try:
        yield evidence
    finally:
        evidence.ended = evidence.ended or datetime.now(UTC)
        try:
            for warning in container.log_slice(evidence.started, evidence.ended, evidence.directory / "logs"):
                evidence.note(warning)
        except Exception as err:  # noqa: BLE001 - log collection is best effort
            evidence.note(f"log collection failed: {err}")
        if not settings.keep_extracted_aip:
            for bag in (evidence.directory / "aip").glob("*/bagit.txt"):
                shutil.rmtree(bag.parent, ignore_errors=True)
            for extracted in (evidence.directory / "dip").glob("*/"):
                shutil.rmtree(extracted, ignore_errors=True)
        evidence.write_result()


@pytest.fixture
def ui(browser: Browser, evidence: Evidence, settings: Settings) -> Iterator[Page]:
    """A page of a fresh browser context whose trace lands in the evidence bundle."""
    context = browser.new_context(viewport={"width": 1400, "height": 900}, base_url=settings.am_url)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    page = context.new_page()
    evidence.page = page
    try:
        yield page
    finally:
        trace = evidence.directory / "trace.zip"
        try:
            context.tracing.stop(path=str(trace))
            evidence.attach("trace", trace)
        finally:
            evidence.page = None
            context.close()


@pytest.fixture
def ss_ui(browser: Browser, evidence: Evidence, settings: Settings) -> Iterator[Page]:
    """A page for the Storage Service in a browser context of its own.

    The dashboard and the Storage Service usually share a host, and browsers
    ignore the port when storing cookies, so one context cannot stay logged in
    to both.
    """
    context = browser.new_context(viewport={"width": 1400, "height": 900}, base_url=settings.ss_url)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    page = context.new_page()
    try:
        yield page
    finally:
        trace = evidence.directory / "trace-storage-service.zip"
        try:
            context.tracing.stop(path=str(trace))
            evidence.attach("trace-storage-service", trace)
        finally:
            context.close()


# pytest-bdd hooks -------------------------------------------------------------


def _evidence(request: pytest.FixtureRequest) -> Evidence:
    evidence: Evidence = request.node.stash[EVIDENCE_KEY]
    return evidence


def pytest_bdd_before_scenario(request: pytest.FixtureRequest, feature: Feature, scenario: Scenario) -> None:
    evidence = _evidence(request)
    evidence.scenario_name = scenario.name
    evidence.feature_file = Path(feature.filename).name
    then_steps = [step.name for step in scenario.steps if step.type == "then"]
    evidence.set_criteria(then_steps)
    item = evidence.item
    if item is not None and len(item.criteria) != len(then_steps):
        evidence.note(
            f"the scenario has {len(then_steps)} Then steps but the checklist item has "
            f"{len(item.criteria)} criteria; the report ticks criteria by position"
        )
    request.node.stash[THEN_INDEX_KEY] = 0


def pytest_bdd_before_step(
    request: pytest.FixtureRequest,
    feature: Feature,
    scenario: Scenario,
    step: Step,
    step_func: Callable[..., Any],
) -> None:
    if step.type != "then":
        return
    index = request.node.stash[THEN_INDEX_KEY]
    _evidence(request).begin_criterion(index)
    request.node.stash[THEN_INDEX_KEY] = index + 1


def pytest_bdd_after_step(
    request: pytest.FixtureRequest,
    feature: Feature,
    scenario: Scenario,
    step: Step,
    step_func: Callable[..., Any],
    step_func_args: dict[str, Any],
) -> None:
    evidence = _evidence(request)
    if step.type == "then":
        evidence.finish_criterion(PASS)
    else:
        evidence.screenshot(f"{step.keyword} {step.name}")


def pytest_bdd_step_error(
    request: pytest.FixtureRequest,
    feature: Feature,
    scenario: Scenario,
    step: Step,
    step_func: Callable[..., Any],
    step_func_args: dict[str, Any],
    exception: BaseException,
) -> None:
    evidence = _evidence(request)
    message = f"{type(exception).__name__}: {exception}"
    if step.type == "then":
        criterion = evidence.finish_criterion(FAIL, message[:4000])
        if criterion is not None and criterion.outcome == KNOWN:
            # Replaces the step's exception: the scenario ends here as an expected failure.
            pytest.xfail(f"known failure: {criterion.message}")
    else:
        evidence.error = f"{step.keyword} {step.name}: {message[:4000]}"
        evidence.screenshot(f"error {step.name}")


def pytest_bdd_after_scenario(request: pytest.FixtureRequest, feature: Feature, scenario: Scenario) -> None:
    """Fail the test when a step recorded a failed criterion through ``evidence.fail``."""
    evidence = _evidence(request)
    if evidence.error:
        return
    failed = [criterion for criterion in evidence.criteria if criterion.outcome == FAIL]
    known = [criterion for criterion in evidence.criteria if criterion.outcome == KNOWN]
    if failed:
        pytest.fail(
            "criteria failed:\n- "
            + "\n- ".join(f"{criterion.text}: {criterion.message}" for criterion in failed + known),
            pytrace=False,
        )
    if known:
        pytest.xfail("known failures:\n- " + "\n- ".join(f"{c.text}: {c.message}" for c in known))
