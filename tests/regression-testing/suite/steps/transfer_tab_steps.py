"""Steps that drive the Transfer tab: starting transfers from the browser and removing units from the grid."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from lxml import etree
from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, then, when

from rt.assertions.mets import NS
from rt.checklist import ChecklistItem
from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_AWAITING, STATUS_COMPLETE, STATUS_USER_INPUT, AMClient, UnitRun
from rt.pipeline.container import Container
from rt.pipeline.processing_config import ProcessingConfig
from rt.pipeline.ss_api import SSClient
from rt.pipeline.web import Dashboard
from rt.scenario import ScenarioConfig
from rt.settings import Settings
from steps.normalization_steps import thumbnails_for_all_objects
from steps.pipeline_steps import chain_for_job, follow_transfer, process_transfer, standard_criteria_apply

Restore = list[tuple[str, Callable[[], None]]]

STARTED_ALERT = re.compile(
    r'Transfer "(?P<name>[^"]+)" started with processing configuration "(?P<config>[^"]+)"'
)
THUMBNAIL_DECISION = "Choose thumbnail mode"


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


# Units for the grid ------------------------------------------------------------------


@given(parsers.parse('a completed transfer of "{path}" exists'))
def completed_transfer_exists(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    path: str,
) -> None:
    run = process_transfer(
        am,
        ss,
        container,
        settings,
        evidence,
        scenario_config,
        item,
        transfer_type="standard",
        path=path,
        processing_config_name="automated",
    )
    assert run.final_status == STATUS_COMPLETE, f"the transfer did not complete: {run.describe()}"
    state["completed"] = run


@given(parsers.parse('a transfer of "{path}" is waiting for a decision'))
def waiting_transfer_exists(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    dashboard: Dashboard,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    restore: Restore,
    state: dict[str, Any],
    path: str,
) -> None:
    """A transfer stopped at a decision the scenario configuration leaves to the user; answered at the end."""
    run = process_transfer(
        am, ss, container, settings, evidence, scenario_config, item, transfer_type="standard", path=path
    )
    assert run.final_status == STATUS_USER_INPUT, f"the transfer did not stop at a decision: {run.describe()}"
    state["waiting"] = run
    waiting_job = next(job for job in run.all_jobs() if job.get("status") == JOB_AWAITING)
    decision = str(waiting_job.get("name"))
    choice = chain_for_job(waiting_job)

    def answer_decision() -> None:
        dashboard.post("mcp/execute/", {"uuid": str(waiting_job["uuid"]), "choice": choice}, accepted=(200,))

    restore.append((f"the decision {decision!r} of transfer {run.transfer_uuid}", answer_decision))


# Removing units ----------------------------------------------------------------------


def _row(ui: Page, uuid: str) -> Any:
    return ui.locator(f"#sip-row-{uuid}")


@when("the user clicks Remove for the completed transfer on the Transfer tab")
def remove_completed_transfer(ui: Page, state: dict[str, Any]) -> None:
    run: UnitRun = state["completed"]
    ui.goto("/transfer/")
    row = _row(ui, run.transfer_uuid)
    expect(row).to_be_visible(timeout=60000)
    # The row actions appear on hover.
    row.hover()
    row.locator("a.btn_remove_sip").click(force=True)


@when('the user clicks "Remove all completed" on the Transfer tab')
def remove_all_completed(ui: Page, state: dict[str, Any]) -> None:
    completed: UnitRun = state["completed"]
    waiting: UnitRun = state["waiting"]
    ui.goto("/transfer/")
    expect(_row(ui, completed.transfer_uuid)).to_be_visible(timeout=60000)
    expect(_row(ui, waiting.transfer_uuid)).to_be_visible(timeout=60000)
    ui.locator("a.monitor-remove-all").click()


@then("a popup asks the user to confirm the removal")
def removal_confirmation(ui: Page, evidence: Evidence) -> None:
    dialog = ui.locator(".modal").filter(has_text="Are you sure you want to remove").first
    expect(dialog).to_be_visible()
    text = dialog.inner_text()
    assert "Are you sure you want to remove" in text, f"unexpected dialog text: {text[:200]}"
    evidence.note(
        f"confirmation: {text.strip().splitlines()[1] if len(text.strip().splitlines()) > 1 else text.strip()[:160]}"
    )
    dialog.get_by_role("button", name="Confirm").click()
    expect(dialog).to_be_hidden()


@then("the transfer no longer appears in the Transfer tab")
def transfer_removed(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    run: UnitRun = state["completed"]
    expect(_row(ui, run.transfer_uuid)).to_have_count(0)
    ui.reload()
    ui.wait_for_timeout(3000)
    expect(_row(ui, run.transfer_uuid)).to_have_count(0)
    evidence.note(f"transfer {run.transfer_uuid} is gone from the Transfer tab")


@then("the completed transfers no longer appear in the Transfer tab")
def completed_transfers_removed(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    run: UnitRun = state["completed"]
    expect(_row(ui, run.transfer_uuid)).to_have_count(0)
    ui.reload()
    ui.wait_for_timeout(3000)
    expect(_row(ui, run.transfer_uuid)).to_have_count(0)
    evidence.note(f"completed transfer {run.transfer_uuid} is gone from the Transfer tab")


@then("the transfers still in progress remain in the Transfer tab")
def waiting_transfers_remain(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    run: UnitRun = state["waiting"]
    expect(_row(ui, run.transfer_uuid)).to_be_visible(timeout=60000)
    evidence.note(f"transfer {run.transfer_uuid}, waiting for a decision, is still listed")


# Starting a transfer from the browser --------------------------------------------------


def _source_parts(ss: SSClient, settings: Settings, path: str) -> list[str]:
    """The tree nodes from the transfer source location down to a sample path."""
    locations = ss.locations(purpose="TS")
    root = settings.transfer_source_root
    for location in locations:
        location_path = str(location.get("path", "")).rstrip("/")
        if location_path and root.startswith(location_path):
            relative = root[len(location_path) :].strip("/")
            return [part for part in relative.split("/") if part] + path.strip("/").split("/")
    raise AssertionError(
        f"no transfer source location contains {root}; locations: {[loc.get('path') for loc in locations]}"
    )


def _select_tree_node(ui: Page, names: list[str]) -> None:
    """Expand the file browser down the path and leave the last node selected."""
    for index, name in enumerate(names):
        content = ui.locator(
            ".tree-node-content",
            has=ui.locator(".transfer-node-name", has_text=re.compile(rf"^{re.escape(name)}$")),
        ).first
        expect(content).to_be_visible(timeout=30000)
        content.click()
        if index < len(names) - 1:
            node = content.locator("xpath=..")
            if node.get_attribute("aria-expanded") != "true":
                content.press("ArrowRight")
            expect(node).to_have_attribute("aria-expanded", "true", timeout=30000)


def _add_directory(ui: Page, ss: SSClient, settings: Settings, path: str) -> None:
    ui.get_by_text("Browse", exact=True).click()
    expect(ui.get_by_label("Source location:")).to_be_visible()
    _select_tree_node(ui, _source_parts(ss, settings, path))
    ui.get_by_role("button", name=re.compile(r"^Add .* to transfer$")).click()


def _alert_text(ui: Page) -> str:
    alert = (
        ui.locator("[role='alert'], .alert").filter(has_text="started with processing configuration").first
    )
    expect(alert).to_be_visible(timeout=30000)
    return alert.inner_text().strip()


def _transfer_uuid_by_name(ui: Page, name: str) -> str:
    row = ui.locator(".sip-row", has_text=name).first
    expect(row).to_be_visible(timeout=60000)
    identifier = row.get_attribute("id") or ""
    return identifier.removeprefix("sip-row-")


@given(
    parsers.parse(
        'a processing configuration named "{name}" exists with the "{decision}" decision set to "{choice}"'
    )
)
def custom_configuration_exists(
    am: AMClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    restore: Restore,
    state: dict[str, Any],
    name: str,
    decision: str,
    choice: str,
) -> None:
    config = ProcessingConfig(am.processing_configuration("automated"))
    config.set(decision, choice)
    content = config.to_xml()
    path = f"{settings.processing_config_dir}/{name}ProcessingMCP.xml"
    container.write_text(path, content)
    evidence.write_text(f"processing-config/{name}ProcessingMCP.xml", content)

    def remove_configuration() -> None:
        container.exec(["rm", "-f", path])

    restore.append((f"the processing configuration {name!r}", remove_configuration))
    assert name in am.processing_configuration_names(), f"the dashboard does not list {name!r}"
    state["custom_config"] = (name, decision, choice)


@when(
    parsers.parse(
        'the user starts a transfer of "{path}" from the Transfer tab with the "{name}" processing configuration'
    )
)
def start_transfer_with_custom_configuration(
    ui: Page,
    ss: SSClient,
    settings: Settings,
    evidence: Evidence,
    state: dict[str, Any],
    path: str,
    name: str,
) -> None:
    transfer_name = f"rt-1.1-{_run_id()}"
    ui.goto("/transfer/")
    ui.fill("#transfer-name", transfer_name)
    _add_directory(ui, ss, settings, path)
    ui.get_by_role("button", name="Show processing configuration options").click()
    menu = ui.locator("ul.dropdown-menu").filter(has=ui.locator("a[role='menuitem']")).first
    expect(menu).to_be_visible()
    state["dropdown_items"] = [item.inner_text().strip() for item in menu.locator("a[role='menuitem']").all()]
    evidence.screenshot("processing configuration dropdown")
    menu.get_by_role("menuitem", name=f'Start with "{name}" configuration').click()
    state["started_alert"] = _alert_text(ui)
    state["custom_transfer_name"] = transfer_name


@then("the custom configuration appears in the dropdown next to Start transfer")
def custom_configuration_in_dropdown(evidence: Evidence, state: dict[str, Any]) -> None:
    name, _, _ = state["custom_config"]
    items: list[str] = state["dropdown_items"]
    assert any(name in item for item in items), f"dropdown items: {items}"
    evidence.note(f"dropdown options: {items}")


@then("a notification says the transfer started with the custom configuration")
def notification_names_custom_configuration(evidence: Evidence, state: dict[str, Any]) -> None:
    name, _, _ = state["custom_config"]
    alert: str = state["started_alert"]
    match = STARTED_ALERT.search(alert)
    assert match and match.group("config") == name, f"notification: {alert!r}"
    evidence.note(f"notification: {alert}")


@then("the processing follows the decisions of the custom configuration")
def processing_follows_custom_configuration(
    ui: Page, am: AMClient, ss: SSClient, settings: Settings, evidence: Evidence, state: dict[str, Any]
) -> None:
    name, _, _ = state["custom_config"]
    transfer_name: str = state["custom_transfer_name"]
    uuid = _transfer_uuid_by_name(ui, transfer_name)
    run = UnitRun(
        transfer_uuid=uuid,
        name=transfer_name,
        transfer_type="standard",
        source_path="",
        processing_config=name,
    )
    evidence.add_unit("transfer", uuid, transfer_name)
    follow_transfer(am, ss, settings, evidence, run)
    assert run.final_status == STATUS_COMPLETE, f"the transfer did not complete: {run.describe()}"
    thumbnails_for_all_objects(evidence, run)


@then(
    "the next transfer started without selecting a configuration is announced with the default configuration"
)
def next_transfer_uses_default(ui: Page, ss: SSClient, settings: Settings, evidence: Evidence) -> None:
    transfer_name = f"rt-1.1-default-{_run_id()}"
    ui.goto("/transfer/")
    ui.fill("#transfer-name", transfer_name)
    _add_directory(ui, ss, settings, "SampleTransfers/Images/pictures")
    ui.get_by_text("Start transfer", exact=True).click()
    alert = _alert_text(ui)
    match = STARTED_ALERT.search(alert)
    assert match and match.group("config") == "default", f"notification: {alert!r}"
    evidence.note(f"notification: {alert}")


# Disk image transfers ------------------------------------------------------------------

# Text fields of the disk image metadata form, and the fields that offer taxonomy terms
# in a select, where the first term offered is chosen.
DISK_IMAGE_TEXT = {
    "media_number": "1",
    "serial_number": "RT-1-5",
    "examiner": "regression testing examiner",
}
DISK_IMAGE_CHOICES = ("media_format", "imaging_software")


@when(
    parsers.parse(
        'the user starts a "Disk image" transfer of "{path}" from the Transfer tab with disk image metadata'
    )
)
def start_disk_image_transfer(
    ui: Page, ss: SSClient, settings: Settings, evidence: Evidence, state: dict[str, Any], path: str
) -> None:
    transfer_name = f"rt-1.5-{_run_id()}"
    ui.goto("/transfer/")
    ui.select_option("#transfer-type", "disk image")
    ui.fill("#transfer-name", transfer_name)
    _add_directory(ui, ss, settings, path)
    with ui.context.expect_page() as editor_info:
        ui.get_by_role("button", name=re.compile(r"^Edit component: ")).click()
    editor = editor_info.value
    editor.wait_for_load_state()
    entered: dict[str, str] = {}
    for field, value in DISK_IMAGE_TEXT.items():
        editor.fill(f"input[name='{field}']", value)
        entered[field] = value
    for field in DISK_IMAGE_CHOICES:
        select = editor.locator(f"select[name='{field}']")
        values = [
            value
            for value in select.locator("option").evaluate_all("options => options.map(o => o.value)")
            if value
        ]
        assert values, f"the {field} select offers no taxonomy term"
        select.select_option(values[0])
        entered[field] = values[0]
    state["disk_image_metadata"] = entered
    main_page = evidence.page
    evidence.page = editor
    try:
        evidence.screenshot("disk image metadata form")
    finally:
        evidence.page = main_page
    editor.locator("input[type='submit']").click()
    editor.wait_for_load_state()
    editor.close()
    ui.get_by_role("button", name="Show processing configuration options").click()
    menu = ui.locator("ul.dropdown-menu").filter(has=ui.locator("a[role='menuitem']")).first
    menu.get_by_role("menuitem", name='Start with "automated" configuration').click()
    state["started_alert"] = _alert_text(ui)
    state["disk_image_transfer_name"] = transfer_name


@then("the disk image metadata ends up in the AIP METS")
def disk_image_metadata_in_mets(
    ui: Page, am: AMClient, ss: SSClient, settings: Settings, evidence: Evidence, state: dict[str, Any]
) -> None:
    transfer_name: str = state["disk_image_transfer_name"]
    uuid = _transfer_uuid_by_name(ui, transfer_name)
    run = UnitRun(
        transfer_uuid=uuid,
        name=transfer_name,
        transfer_type="disk image",
        source_path="",
        processing_config="automated",
    )
    evidence.add_unit("transfer", uuid, transfer_name)
    state["run"] = run
    follow_transfer(am, ss, settings, evidence, run)
    assert run.final_status == STATUS_COMPLETE, f"the transfer did not complete: {run.describe()}"
    assert run.aip is not None
    root = etree.parse(str(run.aip.mets)).getroot()
    found: dict[str, str] = {}
    for wrap in root.iterfind(".//mets:sourceMD/mets:mdWrap", namespaces=NS):
        for element in wrap.iterfind("mets:xmlData/transfer_metadata/*", namespaces=NS):
            found[etree.QName(element).localname] = (element.text or "").strip()
    entered: dict[str, str] = state["disk_image_metadata"]
    missing = {field: value for field, value in entered.items() if found.get(field) != value}
    assert not missing, f"disk image metadata missing from the METS: {missing}; found {found}"
    evidence.note(f"transfer metadata in the METS: {found}")


@then("the standard AIP structure and METS structure criteria apply to the disk image AIP")
def standard_criteria_apply_to_disk_image(evidence: Evidence, state: dict[str, Any]) -> None:
    standard_criteria_apply(state["run"], evidence)
