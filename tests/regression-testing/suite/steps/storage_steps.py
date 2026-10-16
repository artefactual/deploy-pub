"""Steps for archival storage and the Storage Service.

They cover the AIP storage page of the dashboard (downloads, re-ingest and
deletion requests), the decisions a Storage Service administrator takes on
deletion requests, deleting a DIP from the packages table, and AIP storage
locations that encrypt or replicate what they store.
"""

from __future__ import annotations

import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lxml import etree
from playwright.sync_api import Download, Locator, Page, expect
from pytest_bdd import given, parsers, then, when

from rt.assertions.mets import NS, AIPMets
from rt.checklist import ChecklistItem
from rt.evidence import Evidence
from rt.pipeline.am_api import (
    JOB_AWAITING,
    JOB_COMPLETED,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_USER_INPUT,
    AMClient,
    AMError,
    UnitRun,
    UnitStatus,
)
from rt.pipeline.container import Container
from rt.pipeline.ss_api import PACKAGE_UPLOADED, SSClient
from rt.pipeline.web import Dashboard, FieldValue, StorageSite, WebError
from rt.scenario import ScenarioConfig
from rt.settings import Settings
from steps.metadata_steps import KEPT_TITLE, add_descriptive_record
from steps.pipeline_steps import (
    chain_for_job,
    follow_transfer,
    process_transfer,
    wait_for_answer,
    write_processing_config,
)

Restore = list[tuple[str, Callable[[], None]]]

ARCHIVAL_STORAGE = "archival-storage/"
DELETE_REQUESTS = "packages/package_delete_request/"
PENDING_REQUESTS = "tables-package-requests-pending-payload"
CLOSED_REQUESTS = "tables-package-requests-closed-payload"
# The decision point of the Store AIP location choice; its value is a location URI.
STORE_AIP_LOCATION_LINK = "b320ce81-9982-408a-9502-097d0daa48fa"
APPROVE_REINGEST = "Approve AIP reingest"
DELETION_REASON = "Regression testing deletion request"
PACKAGE_DELETION_REQUESTED = "DEL_REQ"
PACKAGE_DELETED = "DELETED"
SEVEN_ZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"
ENCRYPTED_LOCATION = "rt13_11 encrypted AIP storage"
REPLICATED_LOCATION = "rt13_12 replicated AIP storage"
REPLICATOR_LOCATION = "rt13_12 replicator"
# Where the locations the scenarios create keep their packages, under the "/" path of the default space.
LOCATION_ROOT = "var/archivematica/sharedDirectory/www"
# The dashboard shows the status of a package with these labels.
STATUS_LABELS = {PACKAGE_UPLOADED: "Stored", PACKAGE_DELETION_REQUESTED: "Deletion requested"}


def _aip_page(uuid: str) -> str:
    return f"/{ARCHIVAL_STORAGE}{uuid}/"


def stored_aip_uuid(run: UnitRun) -> str:
    assert run.sip_uuid and run.aip is not None, f"the run has no stored AIP: {run.describe()}"
    return run.sip_uuid


def _location_uri(location: dict[str, Any]) -> str:
    return f"/api/v2/location/{location['uuid']}/"


def _save_download(download: Download, evidence: Evidence, label: str) -> Path:
    dest = evidence.directory / "downloads" / download.suggested_filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    download.save_as(str(dest))
    evidence.attach(label, dest)
    return dest


def _alerts(page: Page) -> str:
    texts = page.locator(".alert, .messages li, [role='alert']").all_inner_texts()
    return " | ".join(text.strip() for text in texts if text.strip())


def _status_on_aip_page(ui: Page, uuid: str) -> str:
    ui.goto(_aip_page(uuid))
    row = ui.locator("tr", has=ui.locator("th", has_text=re.compile(r"^\s*Status\s*$")))
    return row.locator("td").first.inner_text().strip()


def _exists_in_pipeline(container: Container, path: str) -> bool:
    return container.exec(["test", "-e", path], check=False).returncode == 0


def _wait_for_sip(am: AMClient, uuid: str, wanted: str, timeout: float, interval: float) -> UnitStatus:
    """Poll a SIP until it reaches the wanted status; a failed SIP ends the wait."""
    deadline = time.monotonic() + timeout
    last: UnitStatus | None = None
    while time.monotonic() < deadline:
        try:
            last = am.ingest_status(uuid)
        except AMError as err:
            if err.status_code != 400:
                raise
        else:
            if last.status == wanted:
                return last
            if last.status == STATUS_FAILED:
                raise AssertionError(f"SIP {uuid} failed at {last.microservice!r}")
        time.sleep(interval)
    raise AssertionError(f"SIP {uuid} did not reach {wanted} within {timeout:.0f}s: {last}")


def _reingest_run(stored: UnitRun, uuid: str, label: str, config: str) -> UnitRun:
    """A run that follows the SIP of a re-ingested AIP; it has no transfer."""
    return UnitRun(
        transfer_uuid="",
        name=stored.name,
        transfer_type=label,
        source_path="",
        processing_config=config,
        sip=UnitStatus(
            type="SIP",
            uuid=uuid,
            name=stored.name,
            directory="",
            status=STATUS_PROCESSING,
            microservice="",
            sip_uuid=None,
            path="",
        ),
    )


def _set_aside_first_aip(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    """Keep the METS of the AIP as first stored; the re-ingested AIP takes its place in the bundle."""
    assert run.aip is not None
    before = evidence.directory / "aip-before-reingest"
    before.mkdir(parents=True, exist_ok=True)
    mets_before = before / run.aip.mets.name
    shutil.copyfile(run.aip.mets, mets_before)
    shutil.rmtree(evidence.directory / "aip", ignore_errors=True)
    state["mets_before"] = mets_before
    evidence.attach("mets-before-reingest", mets_before)


# Stored AIPs ---------------------------------------------------------------------------


@given(parsers.parse('a stored AIP of "{path}" exists'), target_fixture="run")
def stored_aip_exists(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    path: str,
) -> UnitRun:
    """An AIP stored with the automated configuration; the scenario's own configuration serves later steps."""
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
    assert run.final_status == STATUS_COMPLETE and run.aip is not None, (
        f"the transfer did not end in a stored AIP: {run.describe()}"
    )
    state["stored"] = run
    return run


@given(parsers.parse('a stored AIP of "{path}" exists with a DIP'), target_fixture="run")
def stored_aip_with_dip_exists(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    path: str,
) -> UnitRun:
    scenario_config.choices.append(("Normalize", "Normalize for preservation and access"))
    run = process_transfer(
        am, ss, container, settings, evidence, scenario_config, item, transfer_type="standard", path=path
    )
    assert run.final_status == STATUS_COMPLETE and run.aip is not None, (
        f"the transfer did not end in a stored AIP: {run.describe()}"
    )
    assert run.dip is not None, "the Storage Service has no DIP for the AIP"
    state["stored"] = run
    return run


# The AIP storage page ------------------------------------------------------------------


@when('the user clicks "Download" on the AIP storage page')
def click_download(
    ui: Page, settings: Settings, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    uuid = stored_aip_uuid(run)
    ui.goto(_aip_page(uuid))
    evidence.screenshot("AIP storage page")
    with ui.expect_download(timeout=settings.package_timeout * 1000) as info:
        ui.get_by_role("link", name="Download", exact=True).click()
    state["download"] = _save_download(info.value, evidence, "downloaded-aip")


@when(parsers.parse('the user clicks "View" next to the {name} file on the AIP storage page'))
def click_view(
    ui: Page, settings: Settings, evidence: Evidence, run: UnitRun, state: dict[str, Any], name: str
) -> None:
    uuid = stored_aip_uuid(run)
    ui.goto(_aip_page(uuid))
    row = ui.locator(
        "tr", has=ui.locator("th", has_text=re.compile(rf"^\s*{re.escape(name)} file\s*$", re.I))
    )
    link = row.get_by_role("link", name="View", exact=True)
    evidence.screenshot(f"{name} file link")
    # The link opens a new tab; without the target the file arrives as a download of this page.
    link.evaluate("link => link.removeAttribute('target')")
    with ui.expect_download(timeout=settings.package_timeout * 1000) as info:
        link.click()
    state["download"] = _save_download(info.value, evidence, f"downloaded-{name.lower()}")


@then("the AIP is downloaded")
def aip_downloaded(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    path: Path = state["download"]
    size = path.stat().st_size
    assert path.read_bytes()[:6] == SEVEN_ZIP_MAGIC, f"{path.name} is not a 7-Zip archive"
    expected = int((run.aip.package if run.aip is not None else {}).get("size") or 0)
    assert size == expected, f"downloaded {size} bytes while the Storage Service reports {expected}"
    evidence.note(f"downloaded {path.name} ({size} bytes)")


def _parsed_mets(path: Path) -> etree._Element:
    root = etree.parse(str(path)).getroot()
    assert etree.QName(root).localname == "mets", f"{path.name} is not a METS document"
    return root


@then("the METS file is downloaded")
def mets_downloaded(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    path: Path = state["download"]
    uuid = stored_aip_uuid(run)
    root = _parsed_mets(path)
    assert uuid in path.name, f"the downloaded file {path.name} is not named after the AIP"
    assert root.find(".//mets:fileSec", NS) is not None, f"{path.name} has no file section"
    evidence.note(f"downloaded {path.name} ({path.stat().st_size} bytes)")


@then("the pointer file is downloaded")
def pointer_downloaded(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    path: Path = state["download"]
    uuid = stored_aip_uuid(run)
    root = _parsed_mets(path)
    assert uuid in path.name, f"the downloaded file {path.name} is not named after the AIP"
    group = root.find(".//mets:fileGrp[@USE='Archival Information Package']", NS)
    assert group is not None, f"{path.name} has no Archival Information Package file group"
    evidence.note(f"downloaded {path.name} ({path.stat().st_size} bytes)")


# Re-ingest -----------------------------------------------------------------------------


@when(
    parsers.parse('the user starts a "{reingest}" of the AIP with the scenario\'s processing configuration'),
    target_fixture="run",
)
def start_reingest(
    ui: Page,
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    state: dict[str, Any],
    reingest: str,
) -> UnitRun:
    stored: UnitRun = state["stored"]
    uuid = stored_aip_uuid(stored)
    config = write_processing_config(am, container, settings, evidence, scenario_config)
    state["package_before"] = ss.package(uuid)
    _set_aside_first_aip(evidence, stored, state)
    ui.goto(_aip_page(uuid))
    ui.get_by_role("tab", name="Re-ingest").click()
    ui.get_by_label(reingest, exact=True).check()
    ui.select_option("select[name='reingest-processing_config']", config)
    evidence.screenshot(f"{reingest} form")
    ui.locator("button[name='submit-reingest-form']").click()
    ui.wait_for_url(re.compile(r"/archival-storage/?$"))
    evidence.note(f"{reingest} requested: {_alerts(ui)}")
    evidence.screenshot("re-ingest requested")
    run = _reingest_run(stored, uuid, f"{reingest} of AIP {uuid}", config)
    _wait_for_sip(am, uuid, STATUS_USER_INPUT, settings.unit_timeout, settings.poll_interval)
    follow_transfer(am, ss, settings, evidence, run)
    state["reingest_waiting"] = run.current_microservice
    state["reingest_config"] = config
    return run


@when("the user adds descriptive metadata to the re-ingested SIP through the GUI form")
def add_metadata_to_reingested_sip(ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    sip = run.sip_uuid
    assert sip and run.final_status == STATUS_USER_INPUT, f"the SIP is not waiting: {run.describe()}"
    add_descriptive_record(ui, sip, KEPT_TITLE)
    evidence.screenshot("descriptive metadata added to the re-ingested SIP")
    state["dc_title"] = KEPT_TITLE


@then("the AIP is sent to the Ingest tab where the re-ingest can be approved")
def reingest_awaited_approval(evidence: Evidence, state: dict[str, Any]) -> None:
    waited_at = state.get("reingest_waiting")
    assert waited_at == APPROVE_REINGEST, f"the re-ingested SIP waited at {waited_at!r}"
    evidence.note(f"the SIP waited at {APPROVE_REINGEST!r} and was approved from the Ingest tab")


@then("the microservices follow the selected processing configuration")
def reingest_follows_configuration(
    evidence: Evidence, run: UnitRun, scenario_config: ScenarioConfig, state: dict[str, Any]
) -> None:
    sip = run.sip_uuid
    assert sip
    jobs = run.jobs.get(sip, [])
    statuses = {str(job.get("name")): str(job.get("status")) for job in jobs}
    answered: list[str] = state.get("answered", [])
    problems = [
        f"the SIP did not stop at {decision!r}"
        for decision in scenario_config.removals
        if decision not in answered
    ]
    for decision, choice in scenario_config.choices:
        if statuses.get(decision) != JOB_COMPLETED:
            problems.append(f"the {decision!r} decision was not taken automatically")
        elif choice in statuses and statuses[choice] != JOB_COMPLETED:
            problems.append(f"the {choice!r} job did not complete")
    assert not problems, "; ".join(problems)
    evidence.note(
        f"the re-ingest ran with the {state['reingest_config']!r} configuration: "
        f"{len(jobs)} jobs, stopped at {answered}"
    )


@then("metadata can be added using the metadata icon in the GUI")
def reingest_metadata_in_mets(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    assert run.aip is not None, "no AIP was fetched after the re-ingest"
    title = state.get("dc_title")
    assert title, "no descriptive metadata was added"
    root = etree.parse(str(run.aip.mets)).getroot()
    titles = [
        element.text or ""
        for wrap in root.iterfind(".//mets:dmdSec/mets:mdWrap", NS)
        if wrap.get("MDTYPE") == "DC"
        for element in wrap.iterfind(".//dc:title", NS)
    ]
    assert title in titles, f"the re-ingested METS has no DC title {title!r}; titles {titles}"
    evidence.note(f"DC titles in the re-ingested METS: {titles}")


@then("the new AIP overwrites the old one in storage")
def aip_overwritten(ss: SSClient, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    uuid = stored_aip_uuid(run)
    before: dict[str, Any] = state["package_before"]
    after = ss.package(uuid)
    assert len(ss.packages(uuid=uuid)) == 1, "the Storage Service lists more than one package for the AIP"
    assert after.get("status") == PACKAGE_UPLOADED, f"the AIP is {after.get('status')} after the re-ingest"
    assert after.get("current_path") == before.get("current_path"), "the re-ingested AIP moved"
    mets_before: Path = state["mets_before"]
    assert run.aip is not None and run.aip.mets.read_bytes() != mets_before.read_bytes(), (
        "the METS did not change with the re-ingest"
    )
    evidence.note(
        f"package {uuid} at {after.get('current_path')}: {before.get('size')} bytes before, "
        f"{after.get('size')} bytes after the re-ingest"
    )


@then("the METS of the new AIP has a reingestion event")
def reingestion_event_in_mets(evidence: Evidence, run: UnitRun) -> None:
    assert run.aip is not None, "no AIP was fetched after the re-ingest"
    events = [event for event in AIPMets(run.aip.mets).all_events() if event.type == "reingestion"]
    assert events, "the METS has no reingestion event"
    evidence.note(f"{len(events)} reingestion event(s) in the METS")


@then("a DIP is created from the re-ingested AIP")
def dip_from_reingest(evidence: Evidence, run: UnitRun) -> None:
    assert run.dip is not None, "the Storage Service has no DIP for the re-ingested AIP"
    objects = [path.name for path in run.dip.objects()]
    if run.dip.root is not None:
        assert objects, "the DIP has no objects"
    evidence.note(f"DIP {run.dip.uuid} objects: {', '.join(objects) or 'not downloaded'}")


# Deletion requests ---------------------------------------------------------------------


def _pending_request(storage_site: StorageSite, uuid: str) -> dict[str, Any] | None:
    """The row of the pending deletion request of a package, as the Storage Service page embeds it."""
    try:
        payload = storage_site.script_json(DELETE_REQUESTS, PENDING_REQUESTS)
    except WebError:
        # The page embeds no table while nothing is pending.
        return None
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    for row in rows:
        if str(row.get("file", "")).startswith(uuid):
            return dict(row)
    return None


def _decide_request(storage_site: StorageSite, uuid: str, decision: str, reason: str) -> bool:
    """Approve or reject the pending deletion request of a package through its form; False when none is pending."""
    row = _pending_request(storage_site, uuid)
    if row is None:
        return False
    form = row["actions"]
    fields: dict[str, FieldValue] = {
        str(form["eventIdName"]): str(form["eventId"]),
        str(form["reasonName"]): reason,
        str(form["decisionName"]): str(form[f"{decision}Value"]),
    }
    storage_site.post(str(form["action"]), fields, accepted=(200, 301, 302))
    return True


@when("the user requests the deletion of the AIP from its storage page")
def request_deletion_in_ui(
    ui: Page,
    storage_site: StorageSite,
    evidence: Evidence,
    run: UnitRun,
    restore: Restore,
    state: dict[str, Any],
) -> None:
    uuid = stored_aip_uuid(run)
    ui.goto(_aip_page(uuid))
    ui.get_by_role("tab", name="Delete").click()
    ui.fill("input[name='delete-uuid']", uuid)
    ui.fill("textarea[name='delete-reason'], input[name='delete-reason']", DELETION_REASON)
    evidence.screenshot("deletion request form")
    ui.locator("button[name='submit-delete-form']").click()
    ui.wait_for_url(re.compile(r"/archival-storage/?$"))
    state["deletion_message"] = _alerts(ui)
    evidence.note(f"deletion requested: {state['deletion_message']}")
    evidence.screenshot("deletion requested")

    def reject() -> None:
        _decide_request(
            storage_site, uuid, "reject", "Regression testing: request rejected at the end of the scenario"
        )

    restore.append((f"the deletion request of AIP {uuid}", reject))


@then('the status of the AIP is "Deletion requested"')
def status_deletion_requested(ui: Page, ss: SSClient, evidence: Evidence, run: UnitRun) -> None:
    uuid = stored_aip_uuid(run)
    package = ss.package(uuid)
    assert package.get("status") == PACKAGE_DELETION_REQUESTED, (
        f"the Storage Service has the AIP as {package.get('status')}"
    )
    shown = _status_on_aip_page(ui, uuid)
    evidence.screenshot("AIP storage page after the request")
    assert shown == STATUS_LABELS[PACKAGE_DELETION_REQUESTED], f"the AIP page shows the status {shown!r}"
    evidence.note(f"status {shown!r} on the AIP page; {package.get('status')} in the Storage Service")


@given("the deletion of the AIP was requested from the dashboard")
def deletion_requested(
    dashboard: Dashboard,
    ss: SSClient,
    storage_site: StorageSite,
    evidence: Evidence,
    run: UnitRun,
    restore: Restore,
) -> None:
    """The AIP page's delete form, submitted as the dashboard user; rejected at the end if still pending."""
    uuid = stored_aip_uuid(run)
    dashboard.post(
        f"{ARCHIVAL_STORAGE}{uuid}/",
        {"delete-uuid": uuid, "delete-reason": DELETION_REASON, "submit-delete-form": "Delete"},
    )
    package = ss.package(uuid)
    assert package.get("status") == PACKAGE_DELETION_REQUESTED, (
        f"the AIP is {package.get('status')} after the request"
    )
    evidence.note(f"deletion of AIP {uuid} requested from the dashboard")

    def reject() -> None:
        _decide_request(
            storage_site, uuid, "reject", "Regression testing: request rejected at the end of the scenario"
        )

    restore.append((f"the deletion request of AIP {uuid}", reject))


@given("the user is logged in to the Storage Service")
def log_in_to_storage_service(ss_ui: Page, settings: Settings, evidence: Evidence) -> None:
    ss_ui.goto("/login/")
    ss_ui.fill("input[name='username']", settings.ss_user)
    ss_ui.fill("input[name='password']", settings.ss_password)
    ss_ui.locator("input[type='submit'], button[type='submit']").first.click()
    expect(ss_ui).not_to_have_url(re.compile(r"/login/"))
    evidence.screenshot("Storage Service after login", page=ss_ui)


def _pending_row(ss_ui: Page, uuid: str) -> Locator:
    ss_ui.goto(f"/{DELETE_REQUESTS}")
    table = ss_ui.locator(f"[data-table-script-id='{PENDING_REQUESTS}']")
    return table.locator("tr", has_text=uuid).first


@when(parsers.parse("the Storage Service admin {verb} the deletion request"))
def decide_deletion_request(
    ss_ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any], verb: str
) -> None:
    decisions = {"approves": "approve", "rejects": "reject"}
    decision = decisions[verb]
    uuid = stored_aip_uuid(run)
    row = _pending_row(ss_ui, uuid)
    expect(row).to_be_visible(timeout=30000)
    evidence.screenshot("pending deletion requests", page=ss_ui)
    row.locator("textarea[name='status_reason']").fill(f"Regression testing: {verb} the request")
    row.locator(f"button[name='decision'][value='{decision}']").click()
    ss_ui.wait_for_load_state()
    state["decision"] = decision
    state["decision_message"] = _alerts(ss_ui)
    evidence.note(f"the Storage Service admin {verb} the request: {state['decision_message']}")
    evidence.screenshot(f"deletion request {decision}d", page=ss_ui)


@then("the AIP is deleted")
def aip_deleted(ss: SSClient, container: Container, evidence: Evidence, run: UnitRun) -> None:
    uuid = stored_aip_uuid(run)
    package = ss.package(uuid)
    assert package.get("status") == PACKAGE_DELETED, f"the AIP is {package.get('status')}"
    path = str(package.get("current_full_path") or "")
    assert not path or not _exists_in_pipeline(container, path), f"the AIP file still exists at {path}"
    evidence.note(f"AIP {uuid} is {package.get('status')} in the Storage Service; {path} is gone")


@then("the AIP is not deleted")
def aip_kept(ss: SSClient, container: Container, evidence: Evidence, run: UnitRun) -> None:
    uuid = stored_aip_uuid(run)
    package = ss.package(uuid)
    assert package.get("status") == PACKAGE_UPLOADED, f"the AIP is {package.get('status')}"
    path = str(package.get("current_full_path") or "")
    assert _exists_in_pipeline(container, path), f"the AIP file is missing at {path}"
    evidence.note(f"AIP {uuid} is {package.get('status')} in the Storage Service and still at {path}")


def _search_archival_storage(ui: Page, uuid: str, listed: bool) -> Locator:
    """Search the Archival storage tab for an AIP until it is listed, or not, as expected.

    The search is what syncs the status of an AIP with the Storage Service, and
    the index answers the searches that follow a status change inconsistently for
    a moment, so the search is repeated a few times before giving up.
    """
    ui.goto(f"/{ARCHIVAL_STORAGE}")
    # The page runs a first search on load; it must finish before the search by UUID starts.
    ui.wait_for_load_state("networkidle")
    query = ui.locator("input.aip-search-query-input").first
    expect(query).to_be_visible()
    query.fill(uuid)
    ui.locator("select.search-field-select").first.select_option("AIPUUID")
    # Rows link to the AIP page whatever columns the table shows.
    rows = ui.locator(f"#archival-storage-entries tbody tr:has(a[href$='/archival-storage/{uuid}/'])")
    for attempt in range(6):
        if attempt:
            time.sleep(3)
        with ui.expect_response(lambda response: f"query={uuid}" in response.url):
            query.press("Enter")
        ui.wait_for_load_state("networkidle")
        if (rows.count() > 0) == listed:
            break
    return rows


@then("the AIP is no longer listed in the Archival storage tab")
def aip_not_listed(ui: Page, evidence: Evidence, run: UnitRun) -> None:
    uuid = stored_aip_uuid(run)
    rows = _search_archival_storage(ui, uuid, listed=False)
    evidence.screenshot("Archival storage search after the deletion")
    assert rows.count() == 0, f"the Archival storage tab still lists {uuid}"
    # The index drops the AIP a moment after the search results left it out.
    status = 0
    for _ in range(15):
        response = ui.goto(_aip_page(uuid))
        status = response.status if response is not None else 0
        if status == 404:
            break
        time.sleep(2)
    assert status == 404, f"the AIP page still answers {status}"
    evidence.note(f"the search lists no AIP {uuid} and its page answers 404")


@then('the status of the AIP in the Archival storage tab is back to "Stored"')
def status_back_to_stored(ui: Page, evidence: Evidence, run: UnitRun) -> None:
    uuid = stored_aip_uuid(run)
    rows = _search_archival_storage(ui, uuid, listed=True)
    evidence.screenshot("Archival storage search after the rejection")
    assert rows.count() == 1, f"the Archival storage tab lists {rows.count()} rows for {uuid}"
    shown = _status_on_aip_page(ui, uuid)
    evidence.screenshot("AIP storage page after the rejection")
    assert shown == STATUS_LABELS[PACKAGE_UPLOADED], f"the AIP page shows the status {shown!r}"
    evidence.note(f"status {shown!r} on the AIP page")


@then("the decision appears in the Closed Requests table")
def decision_in_closed_requests(ss_ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    uuid = stored_aip_uuid(run)
    labels = {"approve": "Approved", "reject": "Rejected"}
    ss_ui.goto(f"/{DELETE_REQUESTS}")
    closed = ss_ui.locator(f"[data-table-script-id='{CLOSED_REQUESTS}']")
    row = closed.locator("tr", has_text=uuid).first
    expect(row).to_be_visible(timeout=30000)
    evidence.screenshot("closed deletion requests", page=ss_ui)
    text = row.inner_text()
    assert labels[state["decision"]] in text, f"the closed request row reads {text!r}"
    evidence.note(f"closed request for {uuid}: {labels[state['decision']]}")


# DIP deletion --------------------------------------------------------------------------


@when("the user deletes the DIP from the Packages tab")
def delete_dip_in_ui(ss_ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    assert run.dip is not None, "the run has no DIP"
    dip_uuid = run.dip.uuid
    state["dip_path"] = str(run.dip.package.get("current_full_path") or "")
    ss_ui.goto("/packages/")
    search = ss_ui.locator("input.ss-table-search-input").first
    expect(search).to_be_visible()
    search.fill(dip_uuid)
    search.press("Enter")
    row = ss_ui.locator("tr", has_text=dip_uuid).first
    expect(row).to_be_visible(timeout=30000)
    evidence.screenshot("the DIP in the packages table", page=ss_ui)
    row.get_by_role("button", name="Delete").click()
    modal = ss_ui.locator(f"#confirm-delete-{dip_uuid}")
    expect(modal).to_be_visible()
    evidence.screenshot("DIP deletion confirmation", page=ss_ui)
    modal.locator("button.btn-danger[type='submit']").click()
    ss_ui.wait_for_url(re.compile(r"/packages/"))
    state["ss_message"] = _alerts(ss_ui)
    evidence.note(f"deleted DIP {dip_uuid} from the packages table: {state['ss_message']}")
    evidence.screenshot("packages table after the deletion", page=ss_ui)


@then("the DIP is deleted")
def dip_deleted(
    ss: SSClient, container: Container, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    assert run.dip is not None
    package = ss.package(run.dip.uuid)
    assert package.get("status") == PACKAGE_DELETED, f"the DIP is {package.get('status')}"
    path = str(state.get("dip_path") or "")
    assert not path or not _exists_in_pipeline(container, path), f"the DIP still exists at {path}"
    evidence.note(f"DIP {run.dip.uuid} is {package.get('status')} in the Storage Service; {path} is gone")


# Encrypted and replicated locations ----------------------------------------------------


def _location_by_description(ss: SSClient, description: str) -> dict[str, Any] | None:
    for location in ss.locations():
        if location.get("description") == description:
            return location
    return None


def _default_space(ss: SSClient) -> dict[str, Any]:
    spaces = [space for space in ss.spaces() if space.get("access_protocol") == "FS"]
    assert spaces, "the Storage Service has no local filesystem space"
    return spaces[0]


def _create_key(storage_site: StorageSite, name: str, email: str) -> str:
    """Generate a GPG key in the Storage Service; its fingerprint is in the page the form leads to."""
    response = storage_site.post(
        "administration/keys/create/", {"name_real": name, "name_email": email, "key": "Create"}
    )
    match = re.search(r"/keys/([0-9A-Fa-f]+)/detail", response.headers.get("Location", ""))
    assert match, f"the key form did not lead to a key page: {response.headers.get('Location')!r}"
    return match.group(1)


def _create_space(
    storage_site: StorageSite, protocol: str, path: str, staging_path: str, **protocol_fields: str
) -> str:
    fields: dict[str, FieldValue] = {
        "space-access_protocol": protocol,
        "space-size": "",
        "space-path": path,
        "space-staging_path": staging_path,
    }
    fields.update({f"protocol-{name}": value for name, value in protocol_fields.items()})
    response = storage_site.post("spaces/create/", fields)
    match = re.search(r"/spaces/([0-9a-f-]{36})/", response.headers.get("Location", ""))
    assert match, f"the space form did not lead to a space page: {response.headers.get('Location')!r}"
    return match.group(1)


def _create_location(
    ss: SSClient,
    storage_site: StorageSite,
    space_uuid: str,
    *,
    purpose: str,
    relative_path: str,
    description: str,
    replicators: list[str] | None = None,
) -> dict[str, Any]:
    """A location of the space for every pipeline, found back through the API by its description."""
    form = storage_site.form(f"spaces/{space_uuid}/location_create/", having="purpose")
    fields: dict[str, FieldValue] = {
        "purpose": purpose,
        "pipeline": [value for value, _ in form.options.get("pipeline", [])],
        "relative_path": relative_path,
        "description": description,
        "quota": "",
        "enabled": "on",
    }
    if replicators:
        fields["replicators"] = replicators
    storage_site.post(f"spaces/{space_uuid}/location_create/", fields)
    location = _location_by_description(ss, description)
    assert location is not None, f"the location {description!r} was not created"
    return location


def _replicator_option(storage_site: StorageSite, space_uuid: str, replicator_uuid: str) -> str:
    form = storage_site.form(f"spaces/{space_uuid}/location_create/", having="purpose")
    for value, label in form.options.get("replicators", []):
        if replicator_uuid in label:
            return value
    raise AssertionError(f"the location form does not offer the replicator {replicator_uuid}")


@given("an encrypted AIP storage location exists")
def encrypted_location_exists(
    ss: SSClient, storage_site: StorageSite, evidence: Evidence, state: dict[str, Any]
) -> None:
    """A GPG key, a GPG space on the default space's path and an AIP storage location in it; kept for later runs."""
    location = _location_by_description(ss, ENCRYPTED_LOCATION)
    if location is None:
        gpg_spaces = [space for space in ss.spaces() if space.get("access_protocol") == "GPG"]
        if gpg_spaces:
            space_uuid = str(gpg_spaces[0]["uuid"])
            evidence.note(f"reusing the GPG space {space_uuid}")
        else:
            fingerprint = _create_key(storage_site, "Regression testing 13.11", "rt13-11@example.com")
            default = _default_space(ss)
            space_uuid = _create_space(
                storage_site,
                "GPG",
                str(default.get("path") or "/"),
                str(default.get("staging_path") or "/var/archivematica/storage_service"),
                key=fingerprint,
            )
            evidence.note(f"created GPG key {fingerprint} and GPG space {space_uuid}")
        location = _create_location(
            ss,
            storage_site,
            space_uuid,
            purpose="AS",
            relative_path=f"{LOCATION_ROOT}/rt13_11-encrypted",
            description=ENCRYPTED_LOCATION,
        )
        evidence.note(f"created the encrypted location {location['uuid']}")
    else:
        evidence.note(f"reusing the encrypted location {location['uuid']}")
    state["aip_location"] = location


@given("an AIP storage location with a replicator location exists")
def replicated_location_exists(
    ss: SSClient, storage_site: StorageSite, evidence: Evidence, state: dict[str, Any]
) -> None:
    """A replicator location and an AIP storage location replicating to it, both in the default space; kept for later runs."""
    location = _location_by_description(ss, REPLICATED_LOCATION)
    replicator = _location_by_description(ss, REPLICATOR_LOCATION)
    if location is None or replicator is None:
        space_uuid = str(_default_space(ss)["uuid"])
        if replicator is None:
            replicator = _create_location(
                ss,
                storage_site,
                space_uuid,
                purpose="RP",
                relative_path=f"{LOCATION_ROOT}/rt13_12-replicas",
                description=REPLICATOR_LOCATION,
            )
        if location is None:
            option = _replicator_option(storage_site, space_uuid, str(replicator["uuid"]))
            location = _create_location(
                ss,
                storage_site,
                space_uuid,
                purpose="AS",
                relative_path=f"{LOCATION_ROOT}/rt13_12-aips",
                description=REPLICATED_LOCATION,
                replicators=[option],
            )
        evidence.note(f"created location {location['uuid']} replicating to {replicator['uuid']}")
    else:
        evidence.note(f"reusing location {location['uuid']} replicating to {replicator['uuid']}")
    state["aip_location"] = location
    state["replicator"] = replicator


@given("the scenario stores its AIP in that location")
def store_aip_in_location(scenario_config: ScenarioConfig, state: dict[str, Any]) -> None:
    scenario_config.targets[STORE_AIP_LOCATION_LINK] = _location_uri(state["aip_location"])


@then("the pointer file includes an encryption event and the public key")
def pointer_has_encryption(evidence: Evidence, run: UnitRun) -> None:
    assert run.aip is not None and run.aip.pointer is not None, "no pointer file was fetched"
    root = etree.parse(str(run.aip.pointer)).getroot()
    events = [
        event
        for event in root.iterfind(".//premis:event", NS)
        if event.findtext("premis:eventType", default="", namespaces=NS) == "encryption"
    ]
    assert events, "the pointer file has no encryption event"
    detail = events[0].findtext(".//premis:eventDetail", default="", namespaces=NS)
    key = re.search(r"key=([0-9A-Fa-f]+)", detail)
    assert key, f"the encryption event names no key: {detail!r}"
    transform = root.find(".//mets:transformFile[@TRANSFORMTYPE='decryption']", NS)
    assert transform is not None, "the pointer file has no decryption transform"
    assert transform.get("TRANSFORMKEY") == key.group(1), (
        f"the decryption transform key {transform.get('TRANSFORMKEY')!r} differs from the event's {key.group(1)!r}"
    )
    evidence.note(f"encryption event {detail!r}; decryption transform with key {key.group(1)}")


def _download_archive(ss: SSClient, evidence: Evidence, uuid: str, name: str) -> Path:
    dest = evidence.directory / "downloads" / name
    ss.download(uuid, dest)
    assert dest.read_bytes()[:6] == SEVEN_ZIP_MAGIC, f"{name} is not a 7-Zip archive"
    evidence.attach(name, dest)
    return dest


@then("the AIP can be downloaded")
def aip_can_be_downloaded(ss: SSClient, evidence: Evidence, run: UnitRun) -> None:
    uuid = stored_aip_uuid(run)
    dest = _download_archive(ss, evidence, uuid, f"{uuid}.7z")
    evidence.note(f"downloaded the AIP through the Storage Service ({dest.stat().st_size} bytes)")


@then("the AIP can be re-ingested and downloaded again")
def aip_can_be_reingested(
    am: AMClient, ss: SSClient, dashboard: Dashboard, settings: Settings, evidence: Evidence, run: UnitRun
) -> None:
    uuid = stored_aip_uuid(run)
    pipeline = str(ss.pipelines()[0]["uuid"])
    result = ss.request_reingest(uuid, pipeline, "metadata", "automated")
    evidence.note(f"metadata re-ingest requested: {result}")
    _wait_for_sip(am, uuid, STATUS_USER_INPUT, settings.unit_timeout, settings.poll_interval)
    job = next(job for job in am.unit_jobs(uuid, detailed=False) if job.get("status") == JOB_AWAITING)
    assert job.get("name") == APPROVE_REINGEST, f"the SIP waits at {job.get('name')!r}"
    dashboard.post(
        "mcp/execute/",
        {"uuid": str(job["uuid"]), "choice": chain_for_job(job, APPROVE_REINGEST)},
        accepted=(200,),
    )
    reingest = _reingest_run(run, uuid, f"metadata re-ingest of AIP {uuid}", "automated")
    wait_for_answer(am, reingest, str(job["uuid"]), interval=settings.poll_interval)
    am.wait_for_unit(reingest, timeout=settings.unit_timeout, interval=settings.poll_interval)
    assert reingest.final_status == STATUS_COMPLETE, f"the re-ingest did not complete: {reingest.describe()}"
    ss.wait_for_package(uuid, timeout=settings.package_timeout, interval=settings.poll_interval)
    dest = _download_archive(ss, evidence, uuid, f"{uuid}-after-reingest.7z")
    evidence.note(f"downloaded the re-ingested AIP through the Storage Service ({dest.stat().st_size} bytes)")


@then("the AIP is saved in the storage location")
def aip_in_location(container: Container, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    uuid = stored_aip_uuid(run)
    assert run.aip is not None
    package = run.aip.package
    location_uri = _location_uri(state["aip_location"])
    assert package.get("current_location") == location_uri, f"the AIP is in {package.get('current_location')}"
    assert package.get("status") == PACKAGE_UPLOADED, f"the AIP is {package.get('status')}"
    path = str(package.get("current_full_path") or "")
    assert _exists_in_pipeline(container, path), f"the AIP is missing at {path}"
    evidence.note(f"AIP {uuid} stored at {path}")


@then("a second copy of the AIP is saved in the replicator location")
def replica_saved(
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    run: UnitRun,
    state: dict[str, Any],
) -> None:
    uuid = stored_aip_uuid(run)
    replicator_uri = _location_uri(state["replicator"])
    deadline = time.monotonic() + settings.package_timeout
    replicas: list[str] = []
    while time.monotonic() < deadline and not replicas:
        replicas = [str(uri) for uri in ss.package(uuid).get("replicas", [])]
        if not replicas:
            time.sleep(settings.poll_interval)
    assert replicas, f"AIP {uuid} has no replica"
    replica_uuid = replicas[0].rstrip("/").rsplit("/", 1)[-1]
    replica = ss.package(replica_uuid)
    assert str(replica.get("replicated_package") or "").rstrip("/").endswith(uuid), (
        f"replica {replica_uuid} does not point back to the AIP: {replica.get('replicated_package')}"
    )
    assert replica.get("current_location") == replicator_uri, (
        f"the replica is in {replica.get('current_location')}"
    )
    assert replica.get("status") == PACKAGE_UPLOADED, f"the replica is {replica.get('status')}"
    path = str(replica.get("current_full_path") or "")
    assert _exists_in_pipeline(container, path), f"the replica is missing at {path}"
    evidence.packages.append(
        {
            "uuid": replica_uuid,
            "type": replica.get("package_type"),
            "status": replica.get("status"),
            "size": replica.get("size"),
            "current_path": replica.get("current_path"),
            "replica_of": uuid,
        }
    )
    evidence.note(f"replica {replica_uuid} stored at {path}")
