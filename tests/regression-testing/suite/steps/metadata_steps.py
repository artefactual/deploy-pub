"""Steps that add rights and descriptive metadata to a SIP through the dashboard forms."""

from __future__ import annotations

import re
from typing import Any

from lxml import etree
from playwright.sync_api import Page, expect
from pytest_bdd import then, when

from rt.assertions.mets import NS, AIPMets
from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_AWAITING, STATUS_COMPLETE, STATUS_USER_INPUT, AMClient, UnitRun
from rt.pipeline.ss_api import SSClient
from rt.pipeline.web import Dashboard
from rt.settings import Settings
from steps.pipeline_steps import chain_for_job, follow_transfer

REMINDER_DECISION = "Reminder: add metadata if desired"
KEPT_JURISDICTION = "US"
DELETED_NOTE = "regression testing statement to delete"
KEPT_TITLE = "Regression testing title edited"
DELETED_TITLE = "Regression testing title to delete"


def _sip_uuid(run: UnitRun) -> str:
    assert run.final_status == STATUS_USER_INPUT and run.sip_uuid, f"the SIP is not waiting: {run.describe()}"
    return run.sip_uuid


def _confirm_if_asked(ui: Page) -> None:
    """Some delete links lead to a confirmation page; its only form has a primary submit button."""
    confirm = ui.locator("input[name='__confirm__']")
    if confirm.count():
        ui.locator("form:has(input[name='__confirm__']) input[type='submit'].btn-primary").click()


# Rights ----------------------------------------------------------------------------------


def _add_rights_statement(ui: Page, sip: str, jurisdiction: str, note: str) -> None:
    ui.goto(f"/ingest/{sip}/rights/add/")
    ui.select_option("select[name='rightsbasis']", "Copyright")
    status = ui.locator("select[name$='copyrightstatus']").first
    status.select_option(index=1)
    ui.locator("input[name$='copyrightjurisdiction']").first.fill(jurisdiction)
    ui.locator("input[name$='copyrightstatusdeterminationdate']").first.fill("2026-10-16")
    ui.locator("input[name$='copyrightapplicablestartdate']").first.fill("2026-01-01")
    ui.locator("textarea[name='copyright_note']").first.fill(note)
    # Save keeps the statement form open; Next saves it and leads to the grants page.
    ui.get_by_role("button", name="Next", exact=True).click()
    ui.wait_for_url(re.compile(r"/rights/grants/\d+/$"))
    ui.locator("input[name$='-act']").first.fill("Disseminate")
    ui.locator("input[name$='-startdate']").first.fill("2026-01-01")
    restriction = ui.locator("select[name^='new_rights_restriction_']").first
    restriction.select_option(index=1)
    ui.get_by_role("button", name="Done", exact=True).click()
    ui.wait_for_url(re.compile(r"/rights/$"))


@when("the user adds, edits and deletes rights metadata for the SIP through the GUI form")
def manage_rights_metadata(ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    sip = _sip_uuid(run)
    _add_rights_statement(ui, sip, "CA", "regression testing statement kept")
    evidence.screenshot("rights statement added")
    _add_rights_statement(ui, sip, "XX", DELETED_NOTE)
    rows = ui.locator("table tbody tr")
    assert rows.count() >= 2, "the rights list does not show the two statements"
    evidence.screenshot("rights statements listed")
    # Edit the first statement: another jurisdiction.
    ui.locator("a[href$='/rights/1/'], a[href*='/rights/']").filter(has_text="Edit").first.click()
    ui.wait_for_url(re.compile(r"/rights/\d+/$"))
    ui.locator("input[name$='copyrightjurisdiction']").first.fill(KEPT_JURISDICTION)
    ui.get_by_role("button", name="Next", exact=True).click()
    ui.wait_for_url(re.compile(r"/rights/grants/\d+/$"))
    ui.get_by_role("button", name="Done", exact=True).click()
    ui.wait_for_url(re.compile(r"/rights/$"))
    evidence.screenshot("rights statement edited")
    # Delete the last statement.
    ui.get_by_role("link", name="Delete").last.click()
    _confirm_if_asked(ui)
    ui.wait_for_url(re.compile(r"/rights/$"))
    evidence.screenshot("rights statement deleted")
    state["rights_actions"] = ("added", "edited", "deleted")


@then("the user can add, edit and delete rights metadata using the GUI form")
def rights_form_works(evidence: Evidence, state: dict[str, Any]) -> None:
    assert state.get("rights_actions") == ("added", "edited", "deleted")
    evidence.note("rights statements were added, edited and deleted through the GUI form")


@then("the rights metadata is written to the METS")
def rights_in_mets(evidence: Evidence, run: UnitRun) -> None:
    assert run.aip is not None, "no AIP was fetched from the Storage Service"
    root = etree.parse(str(run.aip.mets)).getroot()
    statements = root.findall(".//mets:rightsMD//premis:rightsStatement", NS)
    jurisdictions = [
        s.findtext(".//premis:copyrightJurisdiction", default="", namespaces=NS) for s in statements
    ]
    notes = [s.findtext(".//premis:copyrightNote", default="", namespaces=NS) for s in statements]
    assert KEPT_JURISDICTION in jurisdictions, (
        f"no rights statement with jurisdiction {KEPT_JURISDICTION!r}; found {jurisdictions}"
    )
    assert DELETED_NOTE not in notes, "the deleted rights statement is in the METS"
    evidence.note(f"{len(statements)} PREMIS rights statements in the METS; jurisdictions {jurisdictions}")


# Descriptive metadata ----------------------------------------------------------------------


def add_descriptive_record(ui: Page, sip: str, title: str) -> None:
    """Add the Dublin Core record of a SIP, or fill in the one it already has."""
    ui.goto(f"/ingest/{sip}/metadata/add/")
    ui.fill("input[name='title'], textarea[name='title']", title)
    ui.fill("input[name='creator'], textarea[name='creator']", "Regression testing creator")
    # The add page shows Create for a new record and Save when the SIP already has one.
    ui.get_by_role("button", name=re.compile(r"^(Create|Save)$")).click()
    ui.wait_for_url(f"**/ingest/{sip}/metadata/")
    expect(ui.get_by_text(title)).to_be_visible()


@when("the user adds, edits and deletes descriptive metadata for the SIP through the GUI form")
def manage_descriptive_metadata(ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    """A SIP carries a single Dublin Core record: one is added and deleted, then another is added and edited."""
    sip = _sip_uuid(run)
    add_descriptive_record(ui, sip, DELETED_TITLE)
    evidence.screenshot("descriptive metadata added")
    ui.get_by_role("link", name="Delete").first.click()
    _confirm_if_asked(ui)
    ui.wait_for_url(f"**/ingest/{sip}/metadata/")
    expect(ui.get_by_text(DELETED_TITLE)).to_have_count(0)
    evidence.screenshot("descriptive metadata deleted")
    add_descriptive_record(ui, sip, "Regression testing title")
    ui.get_by_role("link", name="Edit").first.click()
    ui.wait_for_url(re.compile(r"/metadata/\d+/$"))
    ui.fill("input[name='title'], textarea[name='title']", KEPT_TITLE)
    ui.get_by_role("button", name="Save").click()
    ui.wait_for_url(f"**/ingest/{sip}/metadata/")
    expect(ui.get_by_text(KEPT_TITLE)).to_be_visible()
    evidence.screenshot("descriptive metadata edited")
    state["dc_actions"] = ("added", "deleted", "edited")


@then("the user can add, edit and delete descriptive metadata using the GUI form")
def descriptive_form_works(evidence: Evidence, state: dict[str, Any]) -> None:
    assert state.get("dc_actions") == ("added", "deleted", "edited")
    evidence.note("descriptive metadata was added, deleted, added again and edited through the GUI form")


@then("the descriptive metadata is written to the METS")
def descriptive_in_mets(evidence: Evidence, run: UnitRun) -> None:
    assert run.aip is not None, "no AIP was fetched from the Storage Service"
    mets = AIPMets(run.aip.mets)
    titles = [
        element.text or ""
        for wrap in mets.root.iterfind(".//mets:dmdSec/mets:mdWrap", namespaces=NS)
        if wrap.get("MDTYPE") == "DC"
        for element in wrap.iterfind(".//{http://purl.org/dc/elements/1.1/}title")
    ]
    assert KEPT_TITLE in titles, f"the METS has no DC title {KEPT_TITLE!r}; titles {titles}"
    assert DELETED_TITLE not in titles, "the deleted DC record is in the METS"
    evidence.note(f"DC titles in the METS: {titles}")


# Continuing the SIP -------------------------------------------------------------------------


@when("the SIP continues processing")
def sip_continues(
    am: AMClient,
    ss: SSClient,
    settings: Settings,
    dashboard: Dashboard,
    evidence: Evidence,
    run: UnitRun,
    state: dict[str, Any],
) -> None:
    """Answer the decision the SIP is waiting at and follow it to the stored AIP."""
    sip = _sip_uuid(run)
    waiting = next(job for job in run.jobs.get(sip, []) if job.get("status") == JOB_AWAITING)
    decision = str(waiting.get("name"))
    dashboard.post(
        "mcp/execute/", {"uuid": str(waiting["uuid"]), "choice": chain_for_job(waiting)}, accepted=(200,)
    )
    state.setdefault("answered", []).append(decision)
    evidence.note(f"answered {decision!r} for SIP {sip}")
    follow_transfer(am, ss, settings, evidence, run)
    assert run.final_status == STATUS_COMPLETE, f"the SIP did not complete: {run.describe()}"
