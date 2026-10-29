"""Steps that drive the pipeline through its APIs and check jobs and packages."""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime
from typing import Any

from lxml import etree
from pytest_bdd import given, parsers, then, when

from rt.assertions import aip as aip_checks
from rt.assertions.mets import AIPMets
from rt.checklist import ChecklistItem
from rt.evidence import Evidence
from rt.pipeline.am_api import (
    JOB_AWAITING,
    JOB_COMPLETED,
    JOB_FAILED,
    STATUS_COMPLETE,
    STATUS_PROCESSING,
    STATUS_USER_INPUT,
    AMClient,
    AMError,
    TaskDetails,
    TaskOutput,
    UnitRun,
)
from rt.pipeline.container import Container
from rt.pipeline.decisions import DECISIONS
from rt.pipeline.packages import fetch_aip, fetch_dip, find_dip
from rt.pipeline.processing_config import ProcessingConfig
from rt.pipeline.ss_api import SSClient
from rt.scenario import ScenarioConfig
from rt.settings import Settings


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def processing_config_xml(am: AMClient, scenario_config: ScenarioConfig) -> str:
    """The processing configuration of a scenario: its base from the pipeline with its choices applied."""
    config = ProcessingConfig(am.processing_configuration(scenario_config.base))
    for decision, choice in scenario_config.choices:
        config.set(decision, choice)
    for decision in scenario_config.removals:
        config.remove(decision)
    for applies_to, go_to in scenario_config.targets.items():
        config.set_target(applies_to, go_to, comment=f"{applies_to}: {go_to}")
    return config.to_xml()


def write_processing_config(
    am: AMClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
) -> str:
    content = processing_config_xml(am, scenario_config)
    container.write_text(f"{settings.processing_config_dir}/{scenario_config.name}ProcessingMCP.xml", content)
    evidence.write_text(f"processing-config/{scenario_config.name}ProcessingMCP.xml", content)
    names = am.processing_configuration_names()
    assert scenario_config.name in names, (
        f"the dashboard does not list the processing configuration {scenario_config.name!r}: {names}"
    )
    return scenario_config.name


def chain_for_job(job: dict[str, Any], choice: str | None = None) -> str:
    """The chain to execute for a job awaiting a decision: the named choice, or its first one.

    A decision of the same name exists at several points of the workflow with
    different chains, so the job's own decision point is looked up by link.
    """
    decision = str(job.get("name"))
    entries = DECISIONS[decision]
    entry = next((entry for entry in entries if entry.link_id == job.get("link_uuid")), entries[0])
    if choice is None:
        return next(iter(entry.choices.values()))
    return entry.choices[choice]


def wait_for_answer(
    am: AMClient, run: UnitRun, job_uuid: str, *, timeout: float = 60, interval: float = 2
) -> None:
    """Wait until the pipeline has taken the choice made for a job that was awaiting a decision."""
    unit_uuid = run.sip_uuid or run.transfer_uuid
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = next(
            (job for job in am.unit_jobs(unit_uuid, detailed=False) if job.get("uuid") == job_uuid), None
        )
        if job is not None and job.get("status") != JOB_AWAITING:
            return
        time.sleep(interval)
    raise AssertionError(f"the choice for job {job_uuid} was not taken within {timeout:.0f}s")


def record_failed_task(am: AMClient, evidence: Evidence, task: dict[str, Any]) -> TaskOutput | None:
    """Save the details and standard streams of a task; returns the streams when they could be read."""
    uuid = str(task.get("uuid", ""))
    details: dict[str, Any] = dict(task)
    output: TaskOutput | None = None
    try:
        details.update(am.task(uuid))
    except AMError as err:
        evidence.note(f"could not fetch task {uuid}: {err}")
    try:
        output = am.task_output(uuid)
    except AMError as err:
        evidence.note(f"could not read the output of task {uuid}: {err}")
    else:
        details["stdout"] = output.stdout
        details["stderr"] = output.stderr
    evidence.write_json(f"jobs/task-{uuid}.json", details)
    return output


def job_tasks(
    am: AMClient, evidence: Evidence, run: UnitRun, job_name: str, unit_uuid: str | None = None
) -> list[TaskDetails]:
    """The tasks of the jobs with that name, in one unit or in all of them, saved in the bundle."""
    key = f"{unit_uuid or '*'}:{job_name}"
    if key in run.task_details:
        return run.task_details[key]
    jobs = run.jobs.get(unit_uuid, []) if unit_uuid else run.all_jobs()
    tasks: list[TaskDetails] = []
    for job in jobs:
        if job.get("name") != job_name:
            continue
        for task in job.get("tasks", []):
            details = am.task_details(str(task["uuid"]), job_name)
            evidence.write_json(f"jobs/task-{details.uuid}.json", details.as_dict())
            tasks.append(details)
    run.task_details[key] = tasks
    return tasks


def record_units(
    am: AMClient, evidence: Evidence, run: UnitRun, *, settle_timeout: float = 30, interval: float = 2
) -> None:
    """Save the status, jobs and failed task output of every unit of the run.

    The jobs are read once none of them is processing any more, so the snapshot
    of a finished unit does not catch its last job half way. A job that failed
    without stopping the unit becomes a warning of the scenario.
    """
    for kind, status in (("transfer", run.transfer), ("sip", run.sip)):
        if status is None:
            continue
        ref = next((unit for unit in evidence.units if unit.uuid == status.uuid), None)
        if ref is None:
            ref = evidence.add_unit(kind, status.uuid)
        ref.name = status.name
        ref.status = status.status
        ref.microservice = status.microservice
        timeout = 0 if status.status == STATUS_PROCESSING else settle_timeout
        try:
            jobs = am.settled_jobs(status.uuid, timeout=timeout, interval=interval)
        except AMError as err:
            evidence.note(f"could not list the jobs of {kind} {status.uuid}: {err}")
            jobs = []
        run.jobs[status.uuid] = jobs
        evidence.write_json(f"jobs/{kind}-{status.uuid}.json", jobs)
        for job in jobs:
            if job.get("status") != JOB_FAILED:
                continue
            outputs = [record_failed_task(am, evidence, task) for task in list(job.get("tasks", []))[:20]]
            detail = next((output.last_line for output in outputs if output and output.last_line), "")
            text = f"job {job.get('name')!r} ({job.get('microservice')}) of {kind} {status.uuid} failed" + (
                f": {detail}" if detail else ""
            )
            if evidence.extra.get("expected_failure"):
                evidence.note(text)
            else:
                evidence.warn(text)


def process_transfer(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    *,
    transfer_type: str,
    path: str,
    name: str | None = None,
    accession: str = "",
    access_system_id: str = "",
    processing_config_name: str | None = None,
) -> UnitRun:
    config = processing_config_name or write_processing_config(
        am, container, settings, evidence, scenario_config
    )
    transfer_name = name or f"rt-{item.id if item else 'x'}-{_run_id()}"
    source_path = path.strip("/")
    full_path = f"{settings.transfer_source_root}/{source_path}"
    transfer_uuid = am.start_transfer(
        name=transfer_name,
        path=full_path,
        transfer_type=transfer_type,
        accession=accession,
        access_system_id=access_system_id,
        processing_config=config,
    )
    run = UnitRun(
        transfer_uuid=transfer_uuid,
        name=transfer_name,
        transfer_type=transfer_type,
        source_path=source_path,
        processing_config=config,
    )
    evidence.add_unit("transfer", transfer_uuid, transfer_name)
    evidence.note(
        f"{transfer_type} transfer {transfer_name!r} started from {full_path} "
        f"with processing configuration {config!r}"
    )
    return follow_transfer(am, ss, settings, evidence, run)


def follow_transfer(
    am: AMClient, ss: SSClient, settings: Settings, evidence: Evidence, run: UnitRun
) -> UnitRun:
    """Wait for a started transfer, record its jobs and fetch its AIP and DIP into the bundle."""
    try:
        am.wait_for_unit(run, timeout=settings.unit_timeout, interval=settings.poll_interval)
    finally:
        record_units(am, evidence, run, interval=settings.poll_interval)
    evidence.note(run.describe())
    if run.final_status == STATUS_COMPLETE and run.sip_uuid:
        run.aip = fetch_aip(
            ss,
            run.sip_uuid,
            evidence.directory / "aip",
            size_cap=settings.aip_size_cap,
            timeout=settings.package_timeout,
            interval=settings.poll_interval,
        )
        package = run.aip.package
        evidence.packages.append(
            {
                "uuid": run.aip.uuid,
                "type": package.get("package_type"),
                "status": package.get("status"),
                "size": package.get("size"),
                "current_path": package.get("current_path"),
                "downloaded": run.aip.archive is not None,
            }
        )
        # The METS is attached from the top of the aip directory so the link survives
        # the removal of the extracted copy at the end of the scenario.
        mets_copy = evidence.directory / "aip" / run.aip.mets.name
        if run.aip.mets != mets_copy:
            shutil.copyfile(run.aip.mets, mets_copy)
        evidence.attach("mets", mets_copy)
        if run.aip.pointer is not None:
            evidence.attach("pointer", run.aip.pointer)
        if run.aip.archive is not None:
            evidence.attach("aip", run.aip.archive)
        dip_package = find_dip(ss, run.aip.uuid)
        if dip_package is not None:
            run.dip = fetch_dip(
                ss,
                dip_package,
                evidence.directory / "dip",
                size_cap=settings.aip_size_cap,
                timeout=settings.package_timeout,
                interval=settings.poll_interval,
            )
            evidence.packages.append(
                {
                    "uuid": run.dip.uuid,
                    "type": run.dip.package.get("package_type"),
                    "status": run.dip.package.get("status"),
                    "size": run.dip.package.get("size"),
                    "current_path": run.dip.package.get("current_path"),
                    "downloaded": run.dip.archive is not None,
                }
            )
            if run.dip.archive is not None:
                evidence.attach("dip", run.dip.archive)
    return run


# Given -------------------------------------------------------------------------


@given(parsers.parse('the processing configuration is based on "{base}"'))
def processing_configuration_base(scenario_config: ScenarioConfig, base: str) -> None:
    scenario_config.base = base


@given(parsers.parse('the "{decision}" decision is set to "{choice}"'))
def processing_configuration_choice(scenario_config: ScenarioConfig, decision: str, choice: str) -> None:
    scenario_config.choices.append((decision, choice))


@given(parsers.parse('the "{decision}" decision is left for the user'))
def processing_configuration_removal(scenario_config: ScenarioConfig, decision: str) -> None:
    scenario_config.removals.append(decision)


# When --------------------------------------------------------------------------


@when(parsers.parse('a "{transfer_type}" transfer of "{path}" is processed'), target_fixture="run")
def transfer_is_processed(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    transfer_type: str,
    path: str,
) -> UnitRun:
    return process_transfer(
        am, ss, container, settings, evidence, scenario_config, item, transfer_type=transfer_type, path=path
    )


@when(
    parsers.parse('a "{transfer_type}" transfer of "{path}" named "{name}" is processed'),
    target_fixture="run",
)
def named_transfer_is_processed(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    transfer_type: str,
    path: str,
    name: str,
) -> UnitRun:
    return process_transfer(
        am,
        ss,
        container,
        settings,
        evidence,
        scenario_config,
        item,
        transfer_type=transfer_type,
        path=path,
        name=name,
    )


@when(
    parsers.parse(
        'a "{transfer_type}" transfer of "{path}" with accession number "{accession}" is processed'
    ),
    target_fixture="run",
)
def accessioned_transfer_is_processed(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    transfer_type: str,
    path: str,
    accession: str,
) -> UnitRun:
    return process_transfer(
        am,
        ss,
        container,
        settings,
        evidence,
        scenario_config,
        item,
        transfer_type=transfer_type,
        path=path,
        accession=accession,
    )


@when(
    parsers.parse(
        'a "{transfer_type}" transfer of "{path}" is processed with the "{config}" processing configuration'
    ),
    target_fixture="run",
)
def transfer_processed_with_config(
    am: AMClient,
    ss: SSClient,
    container: Container,
    settings: Settings,
    evidence: Evidence,
    scenario_config: ScenarioConfig,
    item: ChecklistItem | None,
    transfer_type: str,
    path: str,
    config: str,
) -> UnitRun:
    """Process a transfer with one of the pipeline's own processing configurations, such as default."""
    return process_transfer(
        am,
        ss,
        container,
        settings,
        evidence,
        scenario_config,
        item,
        transfer_type=transfer_type,
        path=path,
        processing_config_name=config,
    )


# Then --------------------------------------------------------------------------


def _job_summary(jobs: list[dict[str, Any]]) -> str:
    return ", ".join(f"{job.get('name')!r}: {job.get('status')}" for job in jobs)


@then(parsers.parse('the "{job_name}" job completes successfully'))
def job_completes_successfully(run: UnitRun, job_name: str) -> None:
    jobs = run.jobs_named(job_name)
    assert jobs, f"no job named {job_name!r} ran for {run.describe()}; jobs: {_job_summary(run.all_jobs())}"
    statuses = {str(job.get("status")) for job in jobs}
    assert statuses == {JOB_COMPLETED}, f"job {job_name!r} finished with {sorted(statuses)}"


@then("all jobs complete successfully")
def all_jobs_complete_successfully(run: UnitRun) -> None:
    failed = [job for job in run.all_jobs() if job.get("status") == JOB_FAILED]
    assert not failed, f"failed jobs: {_job_summary(failed)}"
    assert run.final_status == STATUS_COMPLETE, f"the pipeline stopped with {run.describe()}"


@then("the AIP is stored")
def aip_is_stored(run: UnitRun) -> None:
    assert run.final_status == STATUS_COMPLETE, f"the pipeline stopped with {run.describe()}"
    assert run.aip is not None, "no AIP was fetched from the Storage Service"
    assert run.aip.package.get("status") == "UPLOADED", f"package status is {run.aip.package.get('status')}"


@then("the standard AIP structure and METS structure criteria apply")
def standard_criteria_apply(run: UnitRun, evidence: Evidence) -> None:
    assert run.final_status == STATUS_COMPLETE, f"the pipeline stopped with {run.describe()}"
    assert run.aip is not None and run.sip_uuid, "no AIP was fetched from the Storage Service"
    problems: list[str] = []
    if run.aip.root is None:
        evidence.pending("the AIP was not downloaded (larger than the size cap); only the METS was checked")
    else:
        problems += aip_checks.validate_bag(run.aip.root)
        problems += aip_checks.check_layout(run.aip.root, run.sip_uuid)
    problems += aip_checks.check_mets_parses(run.aip.mets)
    mets = AIPMets(run.aip.mets)
    problems += aip_checks.check_original_objects(mets)
    problems += aip_checks.check_agents(mets)
    if run.aip.compressed and run.aip.pointer is None:
        problems.append("the Storage Service has no pointer file for the AIP")
    assert not problems, "standard AIP and METS criteria not met:\n- " + "\n- ".join(problems)


@then("the transfer name is changed to use ASCII characters")
def transfer_name_is_ascii(run: UnitRun) -> None:
    assert run.transfer is not None, "the transfer status is unknown"
    changed = run.transfer.name
    assert changed.isascii(), f"the transfer name still has non-ASCII characters: {changed!r}"
    assert changed != run.name, f"the transfer name {run.name!r} was not changed"


@then("the transfer stops awaiting a decision")
def transfer_awaits_decision(run: UnitRun) -> None:
    assert run.final_status == STATUS_USER_INPUT, (
        f"expected the pipeline to wait for a decision; {run.describe()}"
    )


@then(
    "the transfer and ingest follow the decisions of the processing configuration XML file included in the transfer"
)
def embedded_processing_configuration_is_followed(
    run: UnitRun, container: Container, settings: Settings, evidence: Evidence
) -> None:
    embedded_path = f"{settings.transfer_source_root}/{run.source_path}/processingMCP.xml"
    embedded = ProcessingConfig(container.read_bytes(embedded_path))
    targets = embedded.targets()
    evidence.note(f"the transfer ships a processingMCP.xml with {len(targets)} preconfigured choice(s)")
    if not targets:
        assert run.final_status == STATUS_USER_INPUT, (
            "the embedded processingMCP.xml has no preconfigured choices, so the pipeline should stop at "
            f"its first decision point instead of following the dashboard configuration; {run.describe()}"
        )
        return
    jobs = run.all_jobs()
    problems: list[str] = []
    for applies_to, go_to in targets.items():
        matching = [job for job in jobs if job.get("link_uuid") == applies_to]
        if not matching:
            problems.append(f"no job ran for the decision {applies_to} (target {go_to})")
            continue
        if any(job.get("status") == JOB_AWAITING for job in matching):
            problems.append(f"the decision {applies_to} is still awaiting user input")
    assert not problems, "embedded processing configuration not followed:\n- " + "\n- ".join(problems)


@then("the transfer stops at the first decision of its embedded processing configuration")
def transfer_stops_at_embedded_decision(run: UnitRun) -> None:
    assert run.final_status == STATUS_USER_INPUT, (
        f"expected the pipeline to wait for a decision; {run.describe()}"
    )


def embedded_choices(xml: bytes) -> dict[str, str]:
    root = etree.fromstring(xml)
    pairs: dict[str, str] = {}
    for choice in root.iterfind("preconfiguredChoices/preconfiguredChoice"):
        pairs[(choice.findtext("appliesTo") or "").strip()] = (choice.findtext("goToChain") or "").strip()
    return pairs


@given(parsers.parse('the accession number "{accession}"'), target_fixture="item_accession")
def accession_number(accession: str) -> str:
    return accession


@then(parsers.parse('the "{microservice}" microservice completes successfully'))
def microservice_completes_successfully(run: UnitRun, microservice: str) -> None:
    jobs = [job for job in run.all_jobs() if job.get("microservice") == microservice]
    groups = sorted({str(job.get("microservice")) for job in run.all_jobs()})
    assert jobs, (
        f"no job of the microservice {microservice!r} ran for {run.describe()}; microservices: {groups}"
    )
    not_completed = [job for job in jobs if job.get("status") != JOB_COMPLETED]
    assert not not_completed, (
        f"microservice {microservice!r} has jobs that did not complete: {_job_summary(not_completed)}"
    )
