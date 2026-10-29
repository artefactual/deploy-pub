"""Steps for the Appraisal tab of Archivematica 1.17 and 1.18: the backlog pane, tags and SIPs from tags.

The tab is an AngularJS application: its search form fills the backlog pane
with a tree of the transfers found, selecting files there feeds the Analysis
and File list panes, and the Arrangement pane creates a SIP from the files
that carry a tag.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, then, when

from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_AWAITING, STATUS_USER_INPUT, AMClient, AMError, UnitRun
from rt.pipeline.decisions import DECISIONS
from rt.pipeline.web import Dashboard
from rt.scenario import ScenarioConfig
from rt.settings import Settings
from steps.backlog_steps import TRANSFER_UUID, SearchParameter, search_queries
from steps.storage_steps import Restore

APPRAISAL_PAGE = "appraisal/"
APPRAISAL_SEARCH = "ingest/appraisal_list/"
# The Backlog pane of the tab and the tree of transfers it shows.
BACKLOG_PANE = "ui-minimize-panel.transfer-panel"
TREE = f"{BACKLOG_PANE} treecontrol"
TREE_NODES = f"{TREE} li"
# The number of files the scenarios select in the backlog pane.
SELECTED_FILES = 3
SIP_STARTED = "SIP successfully started!"
SIP_FAILED = "SIP could not be started"
# How long the dashboard may take to copy the tagged files into a SIP and start it.
SIP_TIMEOUT = 120000


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def _labels(ui: Page) -> Locator:
    return ui.locator(f"{TREE_NODES} > div.tree-label")


def _transfer_node(ui: Page, run: UnitRun) -> Locator:
    """The top-level node of the transfer in the backlog pane, titled with its directory in the backlog."""
    return ui.locator(f"{TREE} > ul > li").filter(has_text=run.transfer_uuid).first


def _counts(ui: Page) -> str:
    return ui.locator(f"{BACKLOG_PANE} .counts").first.inner_text().strip()


def search_appraisal(ui: Page, parameter: SearchParameter, query: str) -> None:
    """Search the backlog from the Appraisal tab by one parameter and wait for the backlog pane to update."""
    ui.goto(f"/{APPRAISAL_PAGE}")
    form = ui.locator("#search_form")
    expect(form.locator("input.aip-search-query-input").first).to_be_visible()
    form.locator("input.aip-search-query-input").first.fill(query)
    form.locator("select[title='field name']").first.select_option(parameter.field)
    form.locator("select[title='query type']").first.select_option(parameter.query_type)
    with ui.expect_response(
        lambda response: f"/{APPRAISAL_SEARCH}" in response.url and f"query={query}" in unquote(response.url)
    ):
        ui.locator("#search_submit").click()
    # The pane renders the tree a moment after the answer arrives.
    ui.wait_for_timeout(1000)


def _found(ui: Page, run: UnitRun) -> bool:
    deadline = time.monotonic() + 5
    while True:
        if _transfer_node(ui, run).count() > 0:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


# Searches -----------------------------------------------------------------------------


@when("the user searches the backlog by each parameter on the Appraisal tab")
def search_appraisal_by_each_parameter(
    ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    found: dict[str, bool] = {}
    queries = search_queries(run, state)
    for parameter, query in queries.items():
        search_appraisal(ui, parameter, query)
        found[parameter.label] = _found(ui, run)
        evidence.screenshot(f"Appraisal tab search by {parameter.label}")
    state["found"] = found
    state["last_search"] = list(queries)[-1].label


@then(
    "the searches by file name, file extension, accession number, ingest date and transfer UUID find the transfer"
)
def searches_find_the_transfer(evidence: Evidence, state: dict[str, Any]) -> None:
    found: dict[str, bool] = state["found"]
    missing = [label for label, hit in found.items() if not hit]
    assert not missing, f"searches that do not find the transfer: {', '.join(missing)}"
    evidence.note("searches that find the transfer: " + ", ".join(found))


@then("the search results are displayed in the backlog pane")
def results_in_backlog_pane(ui: Page, evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    """The pane shows the transfer found by the last search."""
    node = _transfer_node(ui, run)
    expect(node).to_be_visible()
    title = node.locator("> div.tree-label").first.inner_text().strip()
    evidence.note(f"the backlog pane shows {title!r} after the search by {state['last_search']}")


@given("the user has searched for the transfer on the Appraisal tab")
def searched_for_the_transfer(ui: Page, evidence: Evidence, run: UnitRun) -> None:
    search_appraisal(ui, TRANSFER_UUID, run.transfer_uuid)
    expect(_transfer_node(ui, run)).to_be_visible(timeout=30000)
    evidence.screenshot("the transfer in the backlog pane")


# Expanding, collapsing and selecting ----------------------------------------------------


def _expand_all(ui: Page) -> None:
    ui.locator(f"{BACKLOG_PANE} input[value='Expand all']").click()
    expect(ui.locator(f"{TREE_NODES}.tree-collapsed")).to_have_count(0)


@when("the user selects Expand all and then Collapse all")
def expand_and_collapse_all(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    """Record the expanded and collapsed directories after each button; a collapsed directory hides its children."""
    _expand_all(ui)
    directories = ui.locator(f"{TREE_NODES}:not(.tree-leaf)").count()
    state["expanded"] = (ui.locator(f"{TREE_NODES}.tree-expanded").count(), directories)
    evidence.screenshot("after Expand all")
    ui.locator(f"{BACKLOG_PANE} input[value='Collapse all']").click()
    expect(ui.locator(f"{TREE_NODES}.tree-expanded")).to_have_count(0)
    state["collapsed"] = (
        ui.locator(f"{TREE_NODES}.tree-expanded").count(),
        ui.locator(f"{TREE_NODES}.tree-collapsed").count(),
        ui.locator(f"{TREE_NODES}:not(.tree-leaf)").count(),
    )
    evidence.screenshot("after Collapse all")


@then("all directories expand and then collapse")
def directories_expand_and_collapse(evidence: Evidence, state: dict[str, Any]) -> None:
    expanded, directories = state["expanded"]
    expanded_after_collapse, collapsed, shown = state["collapsed"]
    assert directories > 1, f"the backlog pane shows {directories} directories, too few to tell"
    assert expanded == directories, f"after Expand all {expanded} of {directories} directories are expanded"
    assert (expanded_after_collapse, collapsed) == (0, shown), (
        f"after Collapse all {expanded_after_collapse} directories are expanded and {collapsed} of {shown} collapsed"
    )
    evidence.note(
        f"{directories} directories expanded with Expand all; Collapse all left {shown} collapsed and the rest hidden"
    )


def select_files(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    """Select the first files of the backlog pane, once every directory is expanded."""
    _expand_all(ui)
    files = ui.locator(f"{TREE_NODES}.tree-leaf > div.tree-label")
    expect(files.first).to_be_visible()
    count = min(SELECTED_FILES, files.count())
    names: list[str] = []
    for index in range(count):
        label = files.nth(index)
        label.click()
        expect(label).to_have_class(re.compile(r"(^|\s)tree-selected(\s|$)"))
        names.append(label.inner_text().strip())
    expect(ui.locator(f"{BACKLOG_PANE} .counts")).to_contain_text(f"{count} objects selected")
    state["selected_files"] = names
    evidence.note(f"selected {count} files in the backlog pane: {', '.join(names)}")
    evidence.screenshot("files selected in the backlog pane")


@given("the user has selected several files in the backlog pane")
def selected_several_files(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    select_files(ui, evidence, state)


@when("the user selects Deselect all")
def deselect_all(ui: Page) -> None:
    ui.locator(f"{BACKLOG_PANE} input[value='Deselect all']").click()


@then("the files are deselected")
def files_deselected(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    expect(_labels(ui).and_(ui.locator(".tree-selected"))).to_have_count(0)
    expect(ui.locator(f"{BACKLOG_PANE} .counts")).to_contain_text("0 objects selected")
    evidence.screenshot("after Deselect all")
    evidence.note(f"the {len(state['selected_files'])} selected files were deselected: {_counts(ui)}")


# Tags ------------------------------------------------------------------------------------


def add_tag(ui: Page, evidence: Evidence, state: dict[str, Any], tag: str) -> None:
    pane = ui.locator(BACKLOG_PANE)
    pane.locator("form input[ng-model='tag']").fill(tag)
    pane.locator("#submit-tag").click()
    tagged = ui.locator(f"{TREE} .tag").filter(has_text=tag)
    expect(tagged).to_have_count(len(state["selected_files"]), timeout=30000)
    state["tag"] = tag
    evidence.screenshot(f"tag {tag} added")
    evidence.note(f"added the tag {tag!r} to {len(state['selected_files'])} files")


def _tag_name(scenario_config: ScenarioConfig) -> str:
    return f"{scenario_config.name}-{_run_id()}"


@when("the user adds a tag to the selected files")
def user_adds_tag(
    ui: Page, evidence: Evidence, scenario_config: ScenarioConfig, state: dict[str, Any]
) -> None:
    add_tag(ui, evidence, state, _tag_name(scenario_config))


@given("the user has tagged several files in the backlog pane")
def tagged_several_files(
    ui: Page, evidence: Evidence, scenario_config: ScenarioConfig, state: dict[str, Any]
) -> None:
    select_files(ui, evidence, state)
    add_tag(ui, evidence, state, _tag_name(scenario_config))


@then("the tag is visible in the backlog pane and in the tags dropdown")
def tag_in_pane_and_dropdown(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    tag = str(state["tag"])
    tagged = ui.locator(f"{TREE} .tag").filter(has_text=tag)
    assert tagged.count() == len(state["selected_files"]), (
        f"the backlog pane shows the tag on {tagged.count()} files, not {len(state['selected_files'])}"
    )
    option = ui.locator(f"#tag-facet option[value='{tag}']")
    expect(option).to_have_count(1)
    evidence.note(
        f"the tag {tag!r} shows on {tagged.count()} files of the backlog pane and in the Tags dropdown"
    )


@then("the tag is visible in the Tags tab of the Analysis pane")
def tag_in_analysis_pane(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    tag = str(state["tag"])
    ui.locator("a[href='#/tags']").first.click()
    row = (
        ui.locator("table tr")
        .filter(has=ui.locator("td", has_text=re.compile(rf"^\s*{re.escape(tag)}\s*$")))
        .first
    )
    expect(row).to_be_visible()
    evidence.screenshot("Tags tab of the Analysis pane")
    count = row.locator("td").nth(1).inner_text().strip()
    assert count == str(len(state["selected_files"])), f"the Tags tab counts {count} files for the tag"
    evidence.note(f"the Tags tab lists {tag!r} with {count} files")


def open_pane(ui: Page, title: str) -> Locator:
    """The panel of the tab with that title, shown with its button in the minimize bar when hidden.

    A heading starts with the title of its panel; the buttons of a heading
    may name another panel, as "Finalize arrangement" of ArchivesSpace does.
    """
    heading = ui.locator(".panel-heading", has_text=re.compile(rf"^\s*{re.escape(title)}\b"))
    pane = ui.locator("ui-minimize-panel").filter(has=heading).first
    if not pane.locator(".ui-panel").first.is_visible():
        ui.locator("#minimize-bar a", has_text=re.compile(rf"^\s*{re.escape(title)}\s*$")).click()
    expect(pane.locator(".ui-panel").first).to_be_visible()
    return pane


@then("the tag is visible in the File list pane")
def tag_in_file_list_pane(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    tag = str(state["tag"])
    pane = open_pane(ui, "File list")
    expect(pane.locator("table")).to_be_visible()
    tagged = pane.locator("table tr").filter(has=ui.locator(".tag", has_text=tag))
    expect(tagged).to_have_count(len(state["selected_files"]))
    evidence.screenshot("File list pane")
    evidence.note(f"the File list pane shows the tag on {tagged.count()} files")


# SIPs from a tag --------------------------------------------------------------------------


def create_sip_from_tag(ui: Page, evidence: Evidence, state: dict[str, Any]) -> str:
    """Create a SIP from the files tagged in the backlog pane; returns the message the tab shows."""
    tag = str(state["tag"])
    open_pane(ui, "Arrangement")
    ui.locator("#tag-facet-arrangement").select_option(tag)
    # The tab asks to confirm when the arrangement already holds directories.
    ui.once("dialog", lambda dialog: dialog.accept())
    ui.locator("#arrangement-submit").click()
    alert = (
        ui.locator(".alert")
        .filter(has_text=re.compile(f"{re.escape(SIP_STARTED)}|{re.escape(SIP_FAILED)}"))
        .first
    )
    expect(alert).to_be_visible(timeout=SIP_TIMEOUT)
    message = alert.inner_text().strip()
    evidence.screenshot("SIP created from the tag")
    state["sip_message"] = message
    return message


def _reject_sip(am: AMClient, dashboard: Dashboard, sip_uuid: str, timeout: float, interval: float) -> None:
    """Reject the SIP at the decision it waits at, so it does not linger in the Ingest tab."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = am.ingest_status(sip_uuid)
        except AMError as err:
            if err.status_code != 400:
                raise
        else:
            if status.status == STATUS_USER_INPUT:
                break
        time.sleep(interval)
    else:
        raise AssertionError(f"SIP {sip_uuid} did not reach a decision within {timeout:.0f}s")
    job = next(job for job in am.unit_jobs(sip_uuid, detailed=False) if job.get("status") == JOB_AWAITING)
    choices = next(
        (entry.choices for entry in DECISIONS[str(job["name"])] if entry.link_id == job.get("link_uuid")),
        DECISIONS[str(job["name"])][0].choices,
    )
    chain = next((chain for choice, chain in choices.items() if choice.startswith("Reject")), None)
    if chain is None:
        raise AssertionError(f"the decision {job['name']!r} offers no rejection: {sorted(choices)}")
    dashboard.post("mcp/execute/", {"uuid": str(job["uuid"]), "choice": chain}, accepted=(200,))


def find_sip_on_ingest_tab(ui: Page, name: str) -> str:
    """The UUID of the SIP named like that on the Ingest tab.

    The directory cell of a row ends with the "UUID" abbreviation that shows
    the identifier of the SIP on hover.
    """
    ui.goto("/ingest/")
    directory = ui.locator(
        ".sip-detail-directory", has_text=re.compile(rf"^\s*{re.escape(name)}\s*(UUID\s*)?$")
    )
    row = ui.locator(".sip-row").filter(has=directory).first
    expect(row).to_be_visible(timeout=120000)
    return (row.get_attribute("id") or "").removeprefix("sip-row-")


def _sip_cleanup(
    am: AMClient, dashboard: Dashboard, settings: Settings, restore: Restore, sip_uuid: str
) -> None:
    def reject() -> None:
        _reject_sip(am, dashboard, sip_uuid, settings.unit_timeout, settings.poll_interval)

    restore.append((f"the SIP {sip_uuid} created from the tag, rejected", reject))


@then("a SIP can be created from the tag in the Arrangement pane")
def sip_created_from_tag(
    ui: Page,
    am: AMClient,
    dashboard: Dashboard,
    settings: Settings,
    evidence: Evidence,
    restore: Restore,
    state: dict[str, Any],
) -> None:
    message = create_sip_from_tag(ui, evidence, state)
    assert SIP_STARTED in message, f"the Arrangement pane says {message!r}"
    sip_uuid = find_sip_on_ingest_tab(ui, str(state["tag"]))
    _sip_cleanup(am, dashboard, settings, restore, sip_uuid)
    evidence.note(f"the Arrangement pane started SIP {sip_uuid} from the tag {state['tag']!r}: {message}")


@when("the user creates a SIP from the tag in the Arrangement pane")
def user_creates_sip_from_tag(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    create_sip_from_tag(ui, evidence, state)


@then("the SIP is started")
def sip_started(evidence: Evidence, state: dict[str, Any]) -> None:
    message = str(state["sip_message"])
    assert SIP_STARTED in message, f"the Arrangement pane says {message!r}"
    evidence.note(f"the Arrangement pane says {message!r}")


@then("the SIP appears on the Ingest tab")
def sip_on_ingest_tab(
    ui: Page,
    am: AMClient,
    dashboard: Dashboard,
    settings: Settings,
    evidence: Evidence,
    restore: Restore,
    state: dict[str, Any],
) -> None:
    sip_uuid = find_sip_on_ingest_tab(ui, str(state["tag"]))
    _sip_cleanup(am, dashboard, settings, restore, sip_uuid)
    status = am.ingest_status(sip_uuid)
    evidence.screenshot("the SIP on the Ingest tab")
    evidence.add_unit("sip", sip_uuid, status.name, status.status, status.microservice)
    evidence.note(
        f"SIP {sip_uuid} ({status.name!r}) is on the Ingest tab, {status.status} at {status.microservice!r}"
    )
