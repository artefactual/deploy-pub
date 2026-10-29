"""Steps for the AtoM integration: DIP uploads from the Ingest tab and metadata-only uploads from the AIP page.

The results are checked in AtoM's database through its container, since the
descriptions AtoM creates for the uploaded objects get slugs of their own.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests
from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, parsers, then, when

from rt.checklist import ChecklistItem
from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_AWAITING, JOB_COMPLETED, JOB_PROCESSING, AMClient, UnitRun
from rt.pipeline.container import Container
from rt.pipeline.dashboard_ui import DashboardUI
from rt.pipeline.ss_api import SSClient
from rt.pipeline.web import Dashboard
from rt.scenario import ScenarioConfig
from rt.settings import Settings
from steps.pipeline_steps import process_transfer, record_units, wait_for_answer
from steps.storage_steps import ARCHIVAL_STORAGE, stored_aip_uuid

UPLOAD_DECISION = "Upload DIP"
UPLOAD_TO_ATOM = "Upload DIP to AtoM"
UPLOADED_JOB = "Move to the uploadedDIPs directory"
# AtoM's usage terms: a master is a file AtoM holds, an offline object only describes one.
USAGE_MASTER = "Master"
USAGE_OFFLINE = "Offline"
ATOM_SETTINGS = "administration/dips/atom/"
# How long AtoM may take to attach the objects of a deposit, as its worker processes it.
ATOM_TIMEOUT = 300
_NEW_SLUG = re.compile(r"New resource has slug:\s*(\S+)")


def atom_rows(container: Container, settings: Settings, sql: str) -> list[list[str]]:
    result = container.exec(["mysql", "atom", "-Ns", "-e", sql], service=settings.atom_service, user="root")
    return [line.split("\t") for line in result.stdout.decode().splitlines() if line.strip()]


def _count(container: Container, settings: Settings, sql: str) -> int:
    rows = atom_rows(container, settings, sql)
    return int(rows[0][0]) if rows and rows[0] else 0


def _digital_object_usages(container: Container, settings: Settings, slug: str) -> list[str]:
    """The usage of every digital object attached to the descriptions right below the one with that slug."""
    rows = atom_rows(
        container,
        settings,
        "SELECT t.name FROM digital_object d"
        " JOIN information_object io ON d.object_id = io.id"
        " JOIN slug s ON s.object_id = io.parent_id"
        " JOIN term_i18n t ON t.id = d.usage_id AND t.culture = 'en'"
        f" WHERE s.slug = '{slug}' ORDER BY d.id",
    )
    return [row[0] for row in rows if row]


def _digital_objects_under(container: Container, settings: Settings, slug: str) -> int:
    """Files AtoM holds for the descriptions right below the one with that slug."""
    return _digital_object_usages(container, settings, slug).count(USAGE_MASTER)


def _children_under(container: Container, settings: Settings, slug: str) -> int:
    return _count(
        container,
        settings,
        "SELECT COUNT(*) FROM information_object io JOIN slug s ON s.object_id = io.parent_id"
        f" WHERE s.slug = '{slug}'",
    )


def _wait_for_count(
    container: Container, settings: Settings, slug: str, above: int, timeout: float, interval: float
) -> int:
    deadline = time.monotonic() + timeout
    count = _digital_objects_under(container, settings, slug)
    while count <= above and time.monotonic() < deadline:
        time.sleep(interval)
        count = _digital_objects_under(container, settings, slug)
    return count


@given("the AtoM integration is configured")
def atom_configured(dashboard: Dashboard, settings: Settings, evidence: Evidence) -> None:
    form = dashboard.form(ATOM_SETTINGS, having="url")
    url = form.fields.get("url", "")
    assert url, "the dashboard has no AtoM URL configured"
    slug = settings.atom_target_slug
    response = requests.get(
        f"{settings.atom_url}/index.php/api/informationobjects/{slug}",
        headers={"REST-API-Key": settings.atom_api_key},
        timeout=30,
    )
    assert response.ok, f"AtoM did not answer for the description {slug!r}: {response.status_code}"
    evidence.note(f"the dashboard uploads DIPs to {url}; AtoM serves the description {slug!r}")


def _transfer_up_to_upload(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    transfer_type: str,
    path: str,
    access_system_id: str,
) -> UnitRun:
    """A transfer normalized for access that stops at the Upload DIP decision."""
    scenario_config.choices.append(("Normalize", "Normalize for preservation and access"))
    scenario_config.removals.append(UPLOAD_DECISION)
    state["atom_objects_before"] = _digital_objects_under(container, settings, settings.atom_target_slug)
    run = process_transfer(
        am,
        ss,
        container,
        settings,
        evidence,
        scenario_config,
        item,
        transfer_type=transfer_type,
        path=path,
        access_system_id=access_system_id,
    )
    # The unit reads COMPLETE once its AIP is stored; the DIP waits at the decision in parallel.
    sip = run.sip_uuid
    waiting = [
        job
        for job in run.jobs.get(sip or "", [])
        if job.get("name") == UPLOAD_DECISION and job.get("status") == JOB_AWAITING
    ]
    assert sip and waiting, f"the SIP did not stop at the Upload DIP decision: {run.describe()}"
    evidence.note(f"SIP {sip} waits at the Upload DIP decision while its AIP is stored")
    return run


def _wait_for_upload(am: AMClient, settings: Settings, evidence: Evidence, run: UnitRun) -> None:
    """Wait for the Upload DIP jobs to finish and record the jobs again; the unit status is COMPLETE already."""
    sip = run.sip_uuid
    assert sip
    deadline = time.monotonic() + settings.unit_timeout
    while True:
        jobs = am.unit_jobs(sip, detailed=False)
        group = [job for job in jobs if job.get("microservice") == UPLOAD_DECISION]
        busy = [job for job in group if job.get("status") in (JOB_PROCESSING, JOB_AWAITING)]
        done = any(job.get("name") == UPLOADED_JOB for job in group)
        failed = any(job.get("status") not in (JOB_COMPLETED, JOB_PROCESSING, JOB_AWAITING) for job in group)
        if (done and not busy) or failed:
            break
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"the DIP upload of SIP {sip} did not finish within {settings.unit_timeout:.0f}s"
            )
        time.sleep(settings.poll_interval)
    record_units(am, evidence, run, interval=settings.poll_interval)


@when(
    parsers.parse('a "{transfer_type}" transfer of "{path}" is processed up to the Upload DIP decision'),
    target_fixture="run",
)
def transfer_up_to_upload(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    transfer_type: str,
    path: str,
) -> UnitRun:
    return _transfer_up_to_upload(
        am, ss, container, settings, evidence, scenario_config, item, state, transfer_type, path, ""
    )


@when(
    parsers.parse(
        'a "{transfer_type}" transfer of "{path}" with the target description as access system ID '
        "is processed up to the Upload DIP decision"
    ),
    target_fixture="run",
)
def transfer_with_access_system_id_up_to_upload(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    state: dict[str, Any],
    transfer_type: str,
    path: str,
) -> UnitRun:
    return _transfer_up_to_upload(
        am,
        ss,
        container,
        settings,
        evidence,
        scenario_config,
        item,
        state,
        transfer_type,
        path,
        settings.atom_target_slug,
    )


def _select_upload_to_atom(
    ui: Page, dashboard_ui: DashboardUI, evidence: Evidence, run: UnitRun
) -> tuple[Locator, dict[str, Any]]:
    """Choose Upload DIP to AtoM at the decision from the Ingest tab; returns the slug dialog and the job."""
    sip = run.sip_uuid
    assert sip
    waiting = next(job for job in run.jobs.get(sip, []) if job.get("status") == JOB_AWAITING)
    assert waiting.get("name") == UPLOAD_DECISION, f"the SIP waits at {waiting.get('name')!r}"
    ui.goto("/ingest/")
    row = ui.locator(f"#sip-row-{sip}")
    expect(row).to_be_visible(timeout=60000)
    dashboard_ui.show_jobs(row)
    job_row = dashboard_ui.decision_job(sip, UPLOAD_DECISION)
    select = job_row.locator("select").first
    expect(select).to_be_visible(timeout=30000)
    evidence.screenshot("Upload DIP choices")
    select.select_option(label=f"- {UPLOAD_TO_ATOM}")
    return dashboard_ui.upload_dialog(), waiting


@when(
    'the user selects "Upload DIP to AtoM" at the Upload DIP job and enters the slug of the target description'
)
def upload_with_slug(
    ui: Page,
    dashboard_ui: DashboardUI,
    am: AMClient,
    settings: Settings,
    evidence: Evidence,
    run: UnitRun,
    state: dict[str, Any],
) -> None:
    dialog, waiting = _select_upload_to_atom(ui, dashboard_ui, evidence, run)
    expect(dialog).to_be_visible(timeout=10000)
    evidence.screenshot("slug dialog")
    dashboard_ui.submit_upload_target(dialog, settings.atom_target_slug)
    wait_for_answer(am, run, str(waiting["uuid"]), interval=settings.poll_interval)
    state["prompted"] = True
    evidence.note(f"entered the slug {settings.atom_target_slug!r} in the Upload DIP dialog")
    _wait_for_upload(am, settings, evidence, run)


@when('the user selects "Upload DIP to AtoM" at the Upload DIP job')
def upload_without_slug(
    ui: Page,
    dashboard_ui: DashboardUI,
    am: AMClient,
    settings: Settings,
    evidence: Evidence,
    run: UnitRun,
    state: dict[str, Any],
) -> None:
    dialog, waiting = _select_upload_to_atom(ui, dashboard_ui, evidence, run)
    # The dashboard executes the choice at once when the unit carries an access system ID.
    time.sleep(3)
    state["prompted"] = dialog.is_visible()
    evidence.screenshot("after choosing Upload DIP to AtoM")
    if state["prompted"]:
        evidence.note("the dashboard asked for the slug although the transfer has an access system ID")
        return
    wait_for_answer(am, run, str(waiting["uuid"]), interval=settings.poll_interval)
    _wait_for_upload(am, settings, evidence, run)


@then("Archivematica does not prompt the user for the slug")
def not_prompted(evidence: Evidence, state: dict[str, Any]) -> None:
    assert state.get("prompted") is False, "the dashboard asked for the slug"
    evidence.note("no slug dialog appeared; the access system ID was used")


@then("the digital objects are uploaded to the AtoM target description")
def digital_objects_in_atom(
    container: Container, settings: Settings, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    sip = run.sip_uuid
    assert sip
    upload_jobs = [job for job in run.jobs.get(sip, []) if job.get("name") == UPLOAD_DECISION]
    failed = [job for job in upload_jobs if job.get("status") != JOB_COMPLETED]
    assert upload_jobs and not failed, (
        f"Upload DIP jobs: {[(j.get('name'), j.get('status')) for j in upload_jobs]}"
    )
    slug = settings.atom_target_slug
    before = int(state.get("atom_objects_before", 0))
    after = _wait_for_count(container, settings, slug, before, ATOM_TIMEOUT, settings.poll_interval)
    assert after > before, f"AtoM has {after} digital objects under {slug!r}, as before the upload"
    evidence.note(f"digital objects under {slug!r} in AtoM: {before} before, {after} after the upload")


# Metadata-only upload from the AIP page -------------------------------------------------


@when("the user uploads the AIP metadata to the target description from the AIP storage page")
def upload_metadata_from_aip_page(
    ui: Page,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    run: UnitRun,
    state: dict[str, Any],
) -> None:
    uuid = stored_aip_uuid(run)
    slug = settings.atom_target_slug
    response = ui.goto(f"/{ARCHIVAL_STORAGE}{uuid}/")
    state["aip_page_status"] = response.status if response is not None else 0
    expect(ui.get_by_text(uuid).first).to_be_visible()
    evidence.screenshot("AIP storage page")
    ui.get_by_role("tab", name="Upload DIP").click()
    ui.fill("input[name='upload-slug']", slug)
    evidence.screenshot("metadata-only upload form")
    ui.locator("button[name='submit-upload-form']").click()
    message = ui.locator(".alert").filter(has_text=re.compile("slug|upload", re.I)).first
    expect(message).to_be_visible(timeout=120000)
    text = message.inner_text().strip()
    evidence.screenshot("metadata-only upload result")
    match = _NEW_SLUG.search(text)
    state["upload_message"] = text
    state["new_slug"] = match.group(1) if match else ""
    evidence.note(f"metadata-only upload to {slug!r}: {text}")


@then("the user can navigate to the AIP information page")
def aip_page_reachable(evidence: Evidence, state: dict[str, Any]) -> None:
    assert state.get("aip_page_status") == 200, f"the AIP page answered {state.get('aip_page_status')}"
    evidence.note("the AIP information page opened")


@then("the Upload DIP action of the page accepts the slug of the target description")
def upload_accepted(evidence: Evidence, state: dict[str, Any]) -> None:
    assert state.get("new_slug"), f"the upload did not report a new resource: {state.get('upload_message')!r}"
    evidence.note(f"AtoM created the resource {state['new_slug']!r}")


@then("archival descriptions with the digital object metadata but no digital objects are created in AtoM")
def descriptions_without_objects(
    container: Container, settings: Settings, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    new_slug = str(state.get("new_slug") or "")
    assert new_slug, "no resource was created in AtoM"
    children = _children_under(container, settings, new_slug)
    objects = _digital_objects_under(container, settings, new_slug)
    assert children > 0, f"the resource {new_slug!r} has no child descriptions"
    assert objects == 0, f"the resource {new_slug!r} has {objects} digital objects"
    evidence.note(f"resource {new_slug!r}: {children} child descriptions, {objects} digital objects")
