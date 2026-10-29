"""Steps for the Arrangement pane of the Appraisal tab and what an arranged SIP gives AtoM and the METS.

The pane arranges files of the backlog into directories, gives a directory a
level of description and starts a SIP from it. The SIP runs with the default
processing configuration, which the scenarios replace for their duration, and
its DIP upload hands the arrangement to AtoM as a hierarchy of descriptions.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any

from lxml import etree
from playwright.sync_api import Dialog, Locator, Page, expect
from pytest_bdd import given, parsers, then, when

from rt.assertions.mets import NS
from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_AWAITING, STATUS_FAILED, AMClient, UnitRun
from rt.pipeline.container import Container
from rt.pipeline.packages import fetch_aip
from rt.pipeline.ss_api import SSClient
from rt.pipeline.web import Dashboard
from rt.scenario import ScenarioConfig
from rt.settings import Settings
from steps.appraisal_steps import (
    SIP_FAILED,
    SIP_STARTED,
    SIP_TIMEOUT,
    TREE_NODES,
    find_sip_on_ingest_tab,
    open_pane,
)
from steps.appraisal_steps import _expand_all as expand_backlog_pane
from steps.atom_steps import ATOM_TIMEOUT, UPLOAD_DECISION, atom_rows
from steps.pipeline_steps import chain_for_job, processing_config_xml, record_units
from steps.storage_steps import Restore

ARRANGEMENT_TREE = "#arrangement-tree"
ARRANGEMENT_NODES = f"{ARRANGEMENT_TREE} li"
# The directory of the arrangement that holds the files, inside the directory the SIP is made of.
ARRANGED_DIRECTORY = "arranged"
# How many files of the backlog pane are dragged into the arrangement.
ARRANGED_FILES = 2
DEFAULT_CONFIG = "defaultProcessingMCP.xml"
# The decision every SIP made in the Appraisal tab waits at first, and the choice that lets it continue.
SIP_CREATION_DECISION = "Approve SIP Creation"
SIP_CREATION_CHOICE = "SIP Creation complete"
LEVELS_FETCH = "api/administration/dips/atom/fetch_levels/"
PATH_METADATA = "api/filesystem/metadata/"
# The label of the logical structMap the METS writer builds from the arrangement.
LOGICAL_STRUCTMAP = "Hierarchical"


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def _node(ui: Page, title: str) -> Locator:
    """The node of the arrangement tree with that title."""
    return (
        ui.locator(ARRANGEMENT_NODES)
        .filter(has=ui.locator("> div.tree-label", has_text=re.compile(rf"^\s*{re.escape(title)}(\s|$)")))
        .first
    )


def _label(node: Locator) -> Locator:
    return node.locator("> div.tree-label")


def _select(node: Locator) -> None:
    label = _label(node)
    label.click()
    expect(label).to_have_class(re.compile(r"(^|\s)tree-selected(\s|$)"))


def _expand(node: Locator) -> None:
    """Expand a directory of the arrangement tree, which fetches its children."""
    if "tree-collapsed" in (node.get_attribute("class") or "").split():
        node.locator("> i.tree-branch-head").click()
    expect(node).to_have_class(re.compile(r"(^|\s)tree-expanded(\s|$)"), timeout=30000)


def _add_directory(ui: Page, name: str, parent: Locator | None) -> Locator:
    """Create a directory with the Add directory button, inside the selected parent or at the top level."""
    if parent is not None:
        _select(parent)

    def answer(dialog: Dialog) -> None:
        dialog.accept(name)

    ui.once("dialog", answer)
    with ui.expect_response(lambda response: "create_directory_within_arrange" in response.url):
        ui.locator("#add_directory").click()
    if parent is not None:
        _expand(parent)
    node = _node(ui, name)
    expect(node).to_be_visible(timeout=30000)
    return node


# The default processing configuration ---------------------------------------------------


@given("the default processing configuration normalizes for access and stops at the Upload DIP decision")
def default_configuration_for_upload(
    am: AMClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    restore: Restore,
) -> None:
    """The scenario configuration takes the place of the default one, which an arranged SIP runs with."""
    scenario_config.choices.append(("Normalize", "Normalize for preservation and access"))
    scenario_config.removals.append(UPLOAD_DECISION)
    path = f"{settings.processing_config_dir}/{DEFAULT_CONFIG}"
    original = container.read_text(path)

    def put_back() -> None:
        container.write_text(path, original)

    restore.append(("the default processing configuration", put_back))
    content = processing_config_xml(am, scenario_config)
    container.write_text(path, content)
    evidence.write_text(f"processing-config/{DEFAULT_CONFIG}", content)
    evidence.note("the default processing configuration now normalizes for access and waits at Upload DIP")


@given("the levels of description have been fetched from AtoM")
def levels_fetched(am: AMClient, evidence: Evidence) -> None:
    levels = am.get(LEVELS_FETCH).json()
    names = [str(name) for level in levels for name in level.values()]
    assert names, "AtoM returned no levels of description"
    evidence.note(f"levels of description fetched from AtoM: {', '.join(names)}")


# Arranging --------------------------------------------------------------------------------


@when("the user arranges files of the transfer in a directory of the Arrangement pane")
def arrange_files(
    ui: Page, evidence: Evidence, scenario_config: ScenarioConfig, state: dict[str, Any]
) -> None:
    """A directory for the SIP, a directory inside it, and files of the backlog pane dragged into the latter."""
    name = f"{scenario_config.name}-{_run_id()}"
    open_pane(ui, "Arrangement")
    sip_node = _add_directory(ui, name, parent=None)
    _add_directory(ui, ARRANGED_DIRECTORY, parent=sip_node)
    evidence.screenshot("directories added to the arrangement")
    expand_backlog_pane(ui)
    files = ui.locator(f"{TREE_NODES}.tree-leaf span[tree-draggable][file-type='backlog']")
    expect(files.first).to_be_visible()
    count = min(ARRANGED_FILES, files.count())
    dragged: list[str] = []
    for index in range(count):
        # Every drop reloads the arrangement tree, which comes back collapsed.
        sip_node = _node(ui, name)
        _expand(sip_node)
        target = _node(ui, ARRANGED_DIRECTORY).locator("span[tree-droppable]").first
        expect(target).to_be_visible()
        source = files.nth(index)
        dragged.append(source.inner_text().strip())
        with ui.expect_response(lambda response: "copy_to_arrange" in response.url):
            source.drag_to(target)
        ui.wait_for_timeout(1000)
    sip_node = _node(ui, name)
    _expand(sip_node)
    directory = _node(ui, ARRANGED_DIRECTORY)
    _expand(directory)
    arranged = directory.locator("li").count()
    assert arranged == count, f"the arranged directory holds {arranged} entries after dragging {count} files"
    evidence.screenshot("files arranged")
    state["sip_name"] = name
    state["arranged_files"] = dragged
    evidence.note(f"arranged {count} files in {name}/{ARRANGED_DIRECTORY}: {', '.join(dragged)}")


@when(parsers.parse('the user applies the "{level}" level of description to the directory'))
def apply_level_of_description(
    ui: Page, am: AMClient, evidence: Evidence, state: dict[str, Any], level: str
) -> None:
    name = str(state["sip_name"])
    _expand(_node(ui, name))
    _select(_node(ui, ARRANGED_DIRECTORY))
    ui.locator("#edit_metadata_arrangement").click()
    select = ui.locator("select#lod")
    expect(select).to_be_visible(timeout=30000)
    select.select_option(label=level)
    evidence.screenshot("level of description form")
    with ui.expect_response(
        lambda response: PATH_METADATA in response.url and response.request.method == "POST"
    ):
        ui.locator("form.resource-form button.btn-success").click()
    path = f"/arrange/{name}/{ARRANGED_DIRECTORY}"
    recorded = am.get(PATH_METADATA, {"path": path}).json().get("level_of_description")
    assert recorded == level, f"the arrangement records the level {recorded!r} for {path}"
    state["level"] = level
    evidence.note(f"applied the level of description {level!r} to {name}/{ARRANGED_DIRECTORY}")


# The SIP ---------------------------------------------------------------------------------


def _approve_sip_creation(am: AMClient, dashboard: Dashboard, settings: Settings, sip_uuid: str) -> None:
    """Approve the creation of a SIP once it waits for that, which starts its processing."""
    deadline = time.monotonic() + settings.unit_timeout
    while time.monotonic() < deadline:
        job = next(
            (
                job
                for job in am.unit_jobs(sip_uuid, detailed=False)
                if job.get("name") == SIP_CREATION_DECISION and job.get("status") == JOB_AWAITING
            ),
            None,
        )
        if job is not None:
            chain = chain_for_job(job, SIP_CREATION_CHOICE)
            dashboard.post("mcp/execute/", {"uuid": str(job["uuid"]), "choice": chain}, accepted=(200,))
            return
        time.sleep(settings.poll_interval)
    raise AssertionError(
        f"SIP {sip_uuid} did not reach {SIP_CREATION_DECISION!r} within {settings.unit_timeout:.0f}s"
    )


def _wait_for_upload_decision(am: AMClient, settings: Settings, run: UnitRun) -> None:
    """Wait until the SIP waits at the Upload DIP decision; a failed SIP ends the wait."""
    sip = run.sip_uuid
    assert sip
    deadline = time.monotonic() + settings.unit_timeout
    while time.monotonic() < deadline:
        jobs = am.unit_jobs(sip, detailed=False)
        if any(job.get("name") == UPLOAD_DECISION and job.get("status") == JOB_AWAITING for job in jobs):
            return
        status = am.ingest_status(sip)
        if status.status == STATUS_FAILED:
            raise AssertionError(f"SIP {sip} failed at {status.microservice!r}")
        time.sleep(settings.poll_interval)
    raise AssertionError(
        f"SIP {sip} did not reach the Upload DIP decision within {settings.unit_timeout:.0f}s"
    )


@when("the user creates a SIP from the arrangement", target_fixture="run")
def create_sip_from_arrangement(
    ui: Page,
    am: AMClient,
    dashboard: Dashboard,
    settings: Settings,
    evidence: Evidence,
    state: dict[str, Any],
) -> UnitRun:
    name = str(state["sip_name"])
    _select(_node(ui, name))
    ui.locator("#start_sip_arrangemnt").click()
    alert = (
        ui.locator(".alert")
        .filter(has_text=re.compile(f"{re.escape(SIP_STARTED)}|{re.escape(SIP_FAILED)}"))
        .first
    )
    expect(alert).to_be_visible(timeout=SIP_TIMEOUT)
    message = alert.inner_text().strip()
    evidence.screenshot("SIP created from the arrangement")
    assert SIP_STARTED in message, f"the Arrangement pane says {message!r}"
    sip_uuid = find_sip_on_ingest_tab(ui, name)
    run = UnitRun(
        transfer_uuid="",
        name=name,
        transfer_type="SIP from the arrangement",
        source_path="",
        processing_config="default",
        sip=am.ingest_status(sip_uuid),
    )
    evidence.add_unit("sip", sip_uuid, name)
    evidence.note(f"SIP {sip_uuid} started from the arrangement {name}")
    _approve_sip_creation(am, dashboard, settings, sip_uuid)
    evidence.note(f"chose {SIP_CREATION_CHOICE!r} at {SIP_CREATION_DECISION!r} for SIP {sip_uuid}")
    _wait_for_upload_decision(am, settings, run)
    run.sip = am.ingest_status(sip_uuid)
    record_units(am, evidence, run, interval=settings.poll_interval)
    return run


# What AtoM and the METS got -------------------------------------------------------------


def _description(container: Container, settings: Settings, title: str) -> tuple[str, str, int] | None:
    """The id, level of description and digital object count of the description titled so below the target."""
    rows = atom_rows(
        container,
        settings,
        "SELECT io.id, COALESCE(t.name, ''),"
        " (SELECT COUNT(*) FROM digital_object d JOIN information_object c ON d.object_id = c.id"
        "  WHERE c.lft >= io.lft AND c.rgt <= io.rgt)"
        " FROM information_object io"
        " JOIN information_object_i18n i ON i.id = io.id AND i.culture = 'en'"
        " JOIN slug ps ON ps.slug = '" + settings.atom_target_slug + "'"
        " JOIN information_object parent ON parent.id = ps.object_id"
        " LEFT JOIN term_i18n t ON t.id = io.level_of_description_id AND t.culture = 'en'"
        " WHERE i.title = '" + title + "' AND io.lft > parent.lft AND io.rgt < parent.rgt"
        " ORDER BY io.id DESC LIMIT 1",
    )
    if not rows or len(rows[0]) < 3:
        return None
    return rows[0][0], rows[0][1], int(rows[0][2])


def _wait_for_description(
    container: Container, settings: Settings, title: str, timeout: float, interval: float
) -> tuple[str, str, int]:
    deadline = time.monotonic() + timeout
    while True:
        found = _description(container, settings, title)
        if found is not None and found[2] > 0:
            return found
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"AtoM has no description {title!r} with digital objects below {settings.atom_target_slug!r}: {found}"
            )
        time.sleep(interval)


@then("the arrangement is reflected in AtoM")
def arrangement_in_atom(
    container: Container, settings: Settings, evidence: Evidence, state: dict[str, Any]
) -> None:
    identifier, level, objects = _wait_for_description(
        container, settings, ARRANGED_DIRECTORY, ATOM_TIMEOUT, settings.poll_interval
    )
    expected = len(state["arranged_files"])
    assert objects == expected, (
        f"the description {ARRANGED_DIRECTORY!r} has {objects} digital objects, not {expected}"
    )
    evidence.note(
        f"AtoM created the description {ARRANGED_DIRECTORY!r} (id {identifier}, level {level or 'none'!r}) "
        f"with {objects} digital objects below {settings.atom_target_slug!r}"
    )


@then("the level of description is reflected in AtoM")
def level_in_atom(
    container: Container, settings: Settings, evidence: Evidence, state: dict[str, Any]
) -> None:
    identifier, level, objects = _wait_for_description(
        container, settings, ARRANGED_DIRECTORY, ATOM_TIMEOUT, settings.poll_interval
    )
    assert level == state["level"], f"the description {ARRANGED_DIRECTORY!r} has the level {level!r}"
    evidence.note(
        f"AtoM created the description {ARRANGED_DIRECTORY!r} (id {identifier}) with the level {level!r} "
        f"and {objects} digital objects"
    )


@then("a logical structMap reflecting the arrangement is in the METS")
def logical_structmap_in_mets(
    ss: SSClient, settings: Settings, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    sip = run.sip_uuid
    assert sip
    if run.aip is None:
        run.aip = fetch_aip(
            ss,
            sip,
            evidence.directory / "aip",
            size_cap=settings.aip_size_cap,
            timeout=settings.package_timeout,
            interval=settings.poll_interval,
        )
        evidence.attach("mets", run.aip.mets)
    root = etree.parse(str(run.aip.mets)).getroot()
    structmap = root.find(f".//mets:structMap[@TYPE='logical'][@LABEL='{LOGICAL_STRUCTMAP}']", NS)
    assert structmap is not None, "the METS has no logical structMap of the arrangement"
    directory = structmap.find(f".//mets:div[@LABEL='{ARRANGED_DIRECTORY}']", NS)
    assert directory is not None, f"the logical structMap has no div for {ARRANGED_DIRECTORY!r}"
    # The directory lists the derivatives normalization made next to the arranged files.
    labels = [str(div.get("LABEL")) for div in directory.findall("mets:div", NS)]
    missing = [name for name in state["arranged_files"] if name not in labels]
    assert not missing, f"the div of {ARRANGED_DIRECTORY!r} lacks {', '.join(missing)}; it holds {labels}"
    level = state.get("level")
    if level:
        assert directory.get("TYPE") == level, (
            f"the div of {ARRANGED_DIRECTORY!r} has TYPE {directory.get('TYPE')!r}"
        )
    evidence.note(
        f"the METS has the logical structMap {LOGICAL_STRUCTMAP!r} with {ARRANGED_DIRECTORY!r}"
        + (f" typed {level!r}" if level else "")
        + f" holding {', '.join(labels)}"
    )
