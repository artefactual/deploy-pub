"""Steps for the Backlog tab of Archivematica 1.17 and 1.18: downloads, searches and deletion requests.

The tab searches the transfers sent to the backlog, and their files when asked,
in the search index, and offers each transfer for download and for a deletion
request that a Storage Service administrator decides. The steps that put a
transfer in the backlog also serve the Appraisal tab scenarios.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from lxml import etree
from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, parsers, then, when

from rt.assertions import aip as aip_checks
from rt.checklist import ChecklistItem
from rt.evidence import Evidence
from rt.pipeline.am_api import STATUS_COMPLETE, AMClient, UnitRun
from rt.pipeline.container import Container
from rt.pipeline.packages import extract_tar
from rt.pipeline.ss_api import SSClient
from rt.pipeline.web import Dashboard, StorageSite
from rt.scenario import ScenarioConfig
from rt.settings import Settings
from steps.pipeline_steps import process_transfer
from steps.storage_steps import DELETION_REASON, PACKAGE_DELETED, Restore, decide_request

BACKLOG_PAGE = "backlog/"
BACKLOG_SEARCH = "backlog/search"
# The choice that sends a transfer to the backlog instead of creating a SIP.
BACKLOG_DECISION = ("Create SIP(s)", "Send to backlog")
# The SIP UUID the unit status API reports for a transfer in the backlog.
IN_BACKLOG = "BACKLOG"
TABLE = "#backlog-entries"
# A file of SampleTransfers/Images/pictures, the sample the backlog scenarios send, and its extension
# as the index stores it: lower case, which the search needs since the field is a keyword.
SAMPLE_FILE = "MARBLES.TGA"
SAMPLE_EXTENSION = "tga"


@dataclass(frozen=True)
class SearchParameter:
    """A field of the backlog search form, with the type of query it needs and whether it is a file field."""

    label: str
    field: str
    query_type: str = "term"
    files: bool = False


FILE_NAME = SearchParameter("file name", "filename", files=True)
FILE_EXTENSION = SearchParameter("file extension", "file_extension", files=True)
ACCESSION_NUMBER = SearchParameter("accession number", "accessionid")
INGEST_DATE = SearchParameter("ingest date", "ingestdate")
TRANSFER_UUID = SearchParameter("transfer UUID", "sipuuid")


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def _wait_for_index(dashboard: Dashboard, uuid: str, timeout: float, interval: float) -> None:
    """Wait until the backlog search finds the transfer, which the index lists once its files are indexed."""
    deadline = time.monotonic() + timeout
    while True:
        payload = dashboard.session().get(
            dashboard.url(BACKLOG_SEARCH),
            params={"query": uuid, "field": TRANSFER_UUID.field, "type": "term", "sEcho": "1"},
            timeout=dashboard.timeout,
        )
        if payload.ok and payload.headers.get("Content-Type", "").startswith("application/json"):
            if any(uuid in str(row.get("uuid")) for row in payload.json().get("aaData", [])):
                return
        if time.monotonic() >= deadline:
            raise AssertionError(f"the backlog search does not list transfer {uuid} after {timeout:.0f}s")
        time.sleep(interval)


def send_to_backlog(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    dashboard: Dashboard,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    path: str,
    accession: str = "",
) -> UnitRun:
    """A standard transfer processed with the scenario configuration up to the backlog, stored and indexed.

    The state keeps the accession number and the ingest date the searches use;
    the date is the pipeline's, which runs on UTC, as of the indexing.
    """
    scenario_config.choices.append(BACKLOG_DECISION)
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
        accession=accession,
    )
    assert run.transfer is not None and run.final_status == STATUS_COMPLETE, (
        f"the transfer did not complete: {run.describe()}"
    )
    assert run.transfer.sip_uuid == IN_BACKLOG, f"the transfer was not sent to the backlog: {run.describe()}"
    package = ss.wait_for_package(
        run.transfer_uuid, timeout=settings.package_timeout, interval=settings.poll_interval
    )
    _wait_for_index(dashboard, run.transfer_uuid, settings.package_timeout, settings.poll_interval)
    state["accession"] = accession
    state["ingest_date"] = datetime.now(UTC).strftime("%Y-%m-%d")
    evidence.note(
        f"transfer {run.transfer_uuid} is in the backlog at {package.get('current_path')} and in the search index"
    )
    return run


@given(parsers.parse('a transfer of "{path}" is in the backlog'), target_fixture="run")
def transfer_in_backlog(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    dashboard: Dashboard,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    path: str,
) -> UnitRun:
    return send_to_backlog(
        am, ss, container, settings, evidence, dashboard, scenario_config, item, state, path
    )


@given(
    parsers.parse('a transfer of "{path}" with an accession number is in the backlog'), target_fixture="run"
)
def transfer_with_accession_in_backlog(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    dashboard: Dashboard,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    path: str,
) -> UnitRun:
    # Letters and digits only: the accession number is a keyword in the index, searched as typed.
    accession = f"rt{(item.id if item else 'x').replace('.', '')}acc{_run_id()}"
    return send_to_backlog(
        am,
        ss,
        container,
        settings,
        evidence,
        dashboard,
        scenario_config,
        item,
        state,
        path,
        accession=accession,
    )


# The search form ----------------------------------------------------------------------


def _rows(ui: Page) -> Locator:
    return ui.locator(f"{TABLE} tbody tr")


def search_backlog(ui: Page, parameter: SearchParameter, query: str) -> Locator:
    """Search the Backlog tab by one parameter; returns the rows of the table once it drew the answer."""
    ui.goto(f"/{BACKLOG_PAGE}")
    ui.wait_for_load_state("networkidle")
    checkbox = ui.locator("#id_show_files")
    expect(checkbox).to_be_visible()
    if checkbox.is_checked() != parameter.files:
        # The table searches again as soon as the checkbox changes.
        checkbox.set_checked(parameter.files)
        ui.wait_for_load_state("networkidle")
    form = ui.locator("#search_form")
    form.locator("input.aip-search-query-input").first.fill(query)
    form.locator("select[title='field name']").first.select_option(parameter.field)
    form.locator("select[title='query type']").first.select_option(parameter.query_type)
    with ui.expect_response(
        lambda response: f"/{BACKLOG_SEARCH}" in response.url and f"query={query}" in unquote(response.url)
    ):
        ui.locator("#search_submit").click()
    rows = _rows(ui)
    # The table draws the answer, or its "No matching records" row, a moment after it arrives.
    expect(rows.first).to_be_visible(timeout=30000)
    return rows


def _on_page(rows: Locator, text: str) -> bool:
    """Whether a row of the page drawn now, or drawn within a few seconds, has that text."""
    deadline = time.monotonic() + 5
    while True:
        if rows.filter(has_text=text).count() > 0:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


def _listed(ui: Page, rows: Locator, text: str) -> bool:
    """Whether the table lists a row with that text on its current page or a later one.

    The table pages its answer ten rows at a time, fetched from the server
    page by page, and offers no other page length.
    """
    while True:
        if _on_page(rows, text):
            return True
        next_page = ui.locator(f"{TABLE}_next")
        if next_page.count() == 0 or "disabled" in (next_page.get_attribute("class") or "").split():
            return False
        info = ui.locator(f"{TABLE}_info")
        shown = info.inner_text()
        next_page.click()
        expect(info).not_to_have_text(shown, timeout=30000)


def _column(ui: Page, row: Locator, header: str) -> str:
    """The text of the cell of a row under a column header."""
    headers = [cell.strip() for cell in ui.locator(f"{TABLE} thead th").all_inner_texts()]
    assert header in headers, f"the backlog table has no {header!r} column; its columns: {headers}"
    return row.locator("td").nth(headers.index(header)).inner_text().strip()


# Downloads ------------------------------------------------------------------------------


@when("the user downloads the transfer from the Backlog tab")
def download_from_backlog(
    ui: Page, settings: Settings, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    uuid = run.transfer_uuid
    row = search_backlog(ui, TRANSFER_UUID, uuid).filter(has_text=uuid).first
    expect(row).to_be_visible(timeout=30000)
    evidence.screenshot("the transfer in the Backlog tab")
    with ui.expect_download(timeout=settings.package_timeout * 1000) as info:
        row.locator(f"a[href='/backlog/download/{uuid}']").click()
    dest = evidence.directory / "downloads" / info.value.suggested_filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    info.value.save_as(str(dest))
    evidence.attach("backlog-download", dest)
    state["download"] = dest
    evidence.note(f"downloaded {dest.name} ({dest.stat().st_size} bytes) from the Backlog tab")


def _bag_root(extracted: Path) -> Path:
    roots = sorted(path.parent for path in extracted.rglob("bagit.txt"))
    assert roots, f"the download holds no bag (no bagit.txt under {extracted})"
    return roots[0]


@then("the package downloaded from the backlog is a valid bag")
def backlog_download_is_a_bag(evidence: Evidence, state: dict[str, Any]) -> None:
    archive: Path = state["download"]
    extracted = archive.parent / "extracted"
    extract_tar(archive, extracted)
    root = _bag_root(extracted)
    problems = aip_checks.validate_bag(root)
    assert not problems, "; ".join(problems)
    state["bag_root"] = root
    evidence.note(f"{archive.name} holds the valid bag {root.name}")


@then("it contains a transfer METS file")
def backlog_download_has_transfer_mets(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    root: Path = state["bag_root"]
    # The transfer METS sits under data/metadata, in submissionDocumentation on the releases that
    # name it METS.xml and next to it on those that name it after the transfer.
    candidates = sorted((root / "data" / "metadata").rglob("METS*.xml"))
    assert candidates, (
        f"the bag has no METS file under data/metadata; it holds {sorted(path.name for path in (root / 'data').rglob('*.xml'))}"
    )
    mets = next((path for path in candidates if run.transfer_uuid in path.name), candidates[0])
    document = etree.parse(str(mets)).getroot()
    assert etree.QName(document).localname == "mets", f"{mets.name} is not a METS document"
    evidence.attach("transfer-mets", mets)
    evidence.note(f"the bag holds the transfer METS {mets.relative_to(root)}")


# Searches ------------------------------------------------------------------------------


def search_queries(run: UnitRun, state: dict[str, Any]) -> dict[SearchParameter, str]:
    """The query of each search parameter of the checklist item for a transfer the scenario sent to the backlog."""
    return {
        FILE_NAME: SAMPLE_FILE,
        FILE_EXTENSION: SAMPLE_EXTENSION,
        ACCESSION_NUMBER: str(state["accession"]),
        INGEST_DATE: str(state["ingest_date"]),
        TRANSFER_UUID: run.transfer_uuid,
    }


@when("the user searches the backlog by each parameter on the Backlog tab")
def search_by_each_parameter(ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    """Search by the transfer UUID first, which shows the ingest date the next searches use."""
    uuid = run.transfer_uuid
    row = search_backlog(ui, TRANSFER_UUID, uuid).filter(has_text=uuid).first
    expect(row).to_be_visible(timeout=30000)
    state["ingest_date"] = _column(ui, row, "Ingest date")
    evidence.note(f"the Backlog tab lists the transfer with the ingest date {state['ingest_date']}")
    listed: dict[str, bool] = {}
    for parameter, query in search_queries(run, state).items():
        rows = search_backlog(ui, parameter, query)
        listed[parameter.label] = _listed(ui, rows, uuid)
        evidence.screenshot(f"search by {parameter.label}")
    state["listed"] = listed


@then(
    "the searches by file name, file extension, accession number, ingest date and transfer UUID list the transfer"
)
def searches_list_the_transfer(evidence: Evidence, state: dict[str, Any]) -> None:
    listed: dict[str, bool] = state["listed"]
    missing = [label for label, found in listed.items() if not found]
    assert not missing, f"searches that do not list the transfer: {', '.join(missing)}"
    evidence.note("searches that list the transfer: " + ", ".join(listed))


# Deletion requests -----------------------------------------------------------------------


@when("the user requests the deletion of the transfer from the Backlog tab")
def request_backlog_deletion(
    ui: Page, storage_site: StorageSite, evidence: Evidence, run: UnitRun, restore: Restore
) -> None:
    uuid = run.transfer_uuid
    row = search_backlog(ui, TRANSFER_UUID, uuid).filter(has_text=uuid).first
    expect(row).to_be_visible(timeout=30000)
    # The link of the deletion icon has no trailing slash; the dashboard adds it.
    row.locator(f"a[href^='/backlog/delete/{uuid}']").click()
    ui.wait_for_url(f"**/backlog/delete/{uuid}/")
    ui.fill("textarea[name='reason_for_deletion']", DELETION_REASON)
    evidence.screenshot("deletion request form")
    ui.locator("form:has(input[name='__confirm__']) input[type='submit']").click()
    ui.wait_for_url(re.compile(r"/backlog/?$"))
    messages = " | ".join(text.strip() for text in ui.locator(".alert, .messages li").all_inner_texts())
    evidence.note(f"deletion requested: {messages}")
    evidence.screenshot("deletion requested")

    def reject() -> None:
        decide_request(
            storage_site, uuid, "reject", "Regression testing: request rejected at the end of the scenario"
        )

    restore.append((f"the deletion request of transfer {uuid}", reject))


@when("the Storage Service administrator approves the deletion request")
def approve_backlog_deletion(storage_site: StorageSite, evidence: Evidence, run: UnitRun) -> None:
    uuid = run.transfer_uuid
    assert decide_request(storage_site, uuid, "approve", "Regression testing: request approved"), (
        f"the Storage Service has no pending deletion request for transfer {uuid}"
    )
    evidence.note(f"the deletion request of transfer {uuid} was approved in the Storage Service")


@then("the transfer is removed from the backlog")
def transfer_removed_from_backlog(ui: Page, ss: SSClient, evidence: Evidence, run: UnitRun) -> None:
    uuid = run.transfer_uuid
    package = ss.package(uuid)
    assert package.get("status") == PACKAGE_DELETED, (
        f"the Storage Service has the transfer as {package.get('status')}"
    )
    # The search syncs the index with the Storage Service and drops the deleted transfers.
    rows = search_backlog(ui, TRANSFER_UUID, uuid)
    evidence.screenshot("Backlog tab after the deletion")
    assert not _listed(ui, rows, uuid), f"the Backlog tab still lists transfer {uuid}"
    evidence.note(
        f"transfer {uuid} is {package.get('status')} in the Storage Service and gone from the Backlog tab"
    )
