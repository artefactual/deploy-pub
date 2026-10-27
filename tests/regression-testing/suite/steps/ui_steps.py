"""Steps that drive the dashboard through a browser."""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, then, when

from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_AWAITING, STATUS_USER_INPUT, AMClient, UnitRun
from rt.pipeline.dashboard_ui import DashboardUI
from rt.pipeline.ss_api import SSClient
from rt.settings import Settings
from steps.pipeline_steps import follow_transfer, wait_for_answer


@given("the user is logged in to the dashboard")
@when("the user logs in to the dashboard")
def log_in(ui: Page, settings: Settings) -> None:
    ui.goto("/")
    ui.get_by_label("Username").fill(settings.am_user)
    ui.get_by_label("Password").fill(settings.am_password)
    ui.get_by_text("Log in", exact=True).click()
    expect(ui).to_have_url(re.compile(r"/transfer/?$"))


@when(parsers.parse('the user selects "{choice}" at the "{decision}" job'))
def select_job_choice(
    ui: Page,
    dashboard_ui: DashboardUI,
    am: AMClient,
    ss: SSClient,
    settings: Settings,
    evidence: Evidence,
    run: UnitRun,
    state: dict[str, Any],
    choice: str,
    decision: str,
) -> None:
    """Answer the decision the SIP waits at from the Ingest tab, then follow the SIP."""
    sip = run.sip_uuid
    assert sip and run.final_status == STATUS_USER_INPUT, f"the SIP is not waiting: {run.describe()}"
    waiting = next(job for job in run.jobs.get(sip, []) if job.get("status") == JOB_AWAITING)
    assert waiting.get("name") == decision, f"the SIP waits at {waiting.get('name')!r}, not at {decision!r}"
    ui.goto("/ingest/")
    row = ui.locator(f"#sip-row-{sip}")
    expect(row).to_be_visible(timeout=60000)
    dashboard_ui.show_jobs(row)
    job_row = dashboard_ui.decision_job(sip, decision)
    select = job_row.locator("select").first
    expect(select).to_be_visible(timeout=30000)
    evidence.screenshot(f"choices of {decision}")
    # The Ingest tab lists the choices as "- <label>".
    select.select_option(label=f"- {choice}")
    wait_for_answer(am, run, str(waiting["uuid"]), interval=settings.poll_interval)
    state.setdefault("answered", []).append(decision)
    evidence.note(f"selected {choice!r} at {decision!r} from the Ingest tab")
    follow_transfer(am, ss, settings, evidence, run)


@when("the user opens Administration > Version")
def open_version_page(ui: Page) -> None:
    ui.goto("/administration/version/")
    expect(ui.get_by_text("Agent code")).to_be_visible()


def _version_page_values(ui: Page) -> tuple[str, str]:
    text = ui.locator("body").inner_text()
    version = re.search(r"Version\s+(\d+\.\d+\.\d+\S*)", text)
    agent = re.search(r"Agent code\s+(\S+)", text)
    assert version and agent, f"could not find the version and agent code on the page: {text[:300]!r}"
    return version.group(1), agent.group(1)


@then("the version number on the page matches the X-Archivematica-Version header")
def version_matches_header(ui: Page, am: AMClient, evidence: Evidence) -> None:
    shown, _ = _version_page_values(ui)
    header = am.version()
    evidence.note(f"page shows {shown}, API header says {header}")
    assert shown == header, f"the page shows {shown!r} but the API reports {header!r}"


@then("the agent code corresponds to the version")
def agent_code_matches_version(ui: Page, evidence: Evidence) -> None:
    shown, agent = _version_page_values(ui)
    major_minor = ".".join(shown.split(".")[:2])
    evidence.note(f"agent code {agent}")
    assert agent == f"Archivematica-{major_minor}", f"agent code {agent!r} does not match version {shown!r}"
