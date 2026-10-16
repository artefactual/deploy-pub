"""Steps that check file format identification, package extraction and validation."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from pytest_bdd import then

from rt.assertions.mets import AIPMets, METSFile
from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_COMPLETED, AMClient, UnitRun
from steps.pipeline_steps import job_tasks

IDENTIFY_JOB = "Identify file format"
VALIDATE_JOB = "Validate formats"
EXTRACT_JOB = "Extract contents from compressed archives"
SKIP_MESSAGE = "Skipping file format identification"
# The extraction job reports each package it unpacked on its standard output.
_EXTRACTED = re.compile(r"^Extracted contents from (?P<package>.+?)\s*$", re.MULTILINE)
MATROSKA_SUFFIX = ".mkv"


def _mets(run: UnitRun) -> AIPMets:
    assert run.aip is not None, "no AIP was fetched from the Storage Service"
    return AIPMets(run.aip.mets)


# File format identification ---------------------------------------------------------


@then("Siegfried identifies the formats during the Identify file format microservice")
def siegfried_identifies_formats(evidence: Evidence, run: UnitRun) -> None:
    jobs = [job for job in run.jobs.get(run.transfer_uuid, []) if job.get("name") == IDENTIFY_JOB]
    assert jobs, f"the job {IDENTIFY_JOB!r} did not run on the transfer"
    not_complete = [job.get("status") for job in jobs if job.get("status") != JOB_COMPLETED]
    assert not not_complete, f"the job {IDENTIFY_JOB!r} finished with {not_complete}"
    mets = _mets(run)
    problems: list[str] = []
    tools: Counter[str] = Counter()
    for file in mets.files("original"):
        events = mets.events_of_type(file, "format identification")
        siegfried = [event for event in events if 'program="Siegfried"' in event.detail]
        if not siegfried:
            problems.append(f"{file.href}: no Siegfried identification event ({[e.detail for e in events]})")
        elif not any(event.outcome == "Positive" for event in siegfried):
            problems.append(f"{file.href}: outcome {[event.outcome for event in siegfried]}")
        else:
            tools[siegfried[0].detail] += 1
    assert not problems, "originals not identified by Siegfried:\n- " + "\n- ".join(problems)
    evidence.note(
        "identification events: " + "; ".join(f"{count} with {tool}" for tool, count in tools.items())
    )


@then('the standard output of the "Identify file format" job is "Skipping file format identification"')
def identification_skipped(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    tasks = job_tasks(am, evidence, run, IDENTIFY_JOB, unit_uuid=run.transfer_uuid)
    assert tasks, f"the job {IDENTIFY_JOB!r} did not run on the transfer or had no tasks"
    not_skipped = [task.file_name or task.uuid for task in tasks if SKIP_MESSAGE not in task.stdout]
    assert not not_skipped, f"tasks whose output does not say {SKIP_MESSAGE!r}: {not_skipped}"
    evidence.note(f"{len(tasks)} identification tasks skipped")


@then("there are no format identification PREMIS events for the transfer objects in the METS")
def no_identification_events(run: UnitRun) -> None:
    mets = _mets(run)
    with_events = [
        file.href for file in mets.files("original") if mets.events_of_type(file, "format identification")
    ]
    assert not with_events, f"originals with a format identification event: {with_events}"


# Package extraction ------------------------------------------------------------------


def _extracted_packages(am: AMClient, evidence: Evidence, run: UnitRun) -> list[str]:
    tasks = job_tasks(am, evidence, run, EXTRACT_JOB, unit_uuid=run.transfer_uuid)
    assert tasks, f"the job {EXTRACT_JOB!r} did not run on the transfer"
    names = [match.group("package") for task in tasks for match in _EXTRACTED.finditer(task.stdout)]
    assert names, f"the output of {EXTRACT_JOB!r} names no extracted package"
    evidence.note("extracted packages: " + ", ".join(names))
    return names


def _package_files(mets: AIPMets, packages: list[str]) -> list[METSFile]:
    return [file for file in mets.files() if Path(file.href).name in packages]


def _packages_in_bag(run: UnitRun, packages: list[str]) -> list[str] | None:
    assert run.aip is not None
    if run.aip.root is None:
        return None
    objects = run.aip.root / "data" / "objects"
    return sorted(str(path.relative_to(objects)) for path in objects.rglob("*") if path.name in packages)


@then("the AIP does not contain the original packages")
def aip_without_packages(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    packages = _extracted_packages(am, evidence, run)
    mets = _mets(run)
    listed = [file.href for file in _package_files(mets, packages)]
    assert not listed, f"packages still listed in the METS: {listed}"
    found = _packages_in_bag(run, packages)
    if found is None:
        evidence.pending("the AIP was not downloaded (larger than the size cap); only the METS was checked")
        return
    assert not found, f"packages still present in the AIP: {found}"


@then("the AIP contains the original packages")
def aip_with_packages(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    packages = _extracted_packages(am, evidence, run)
    mets = _mets(run)
    listed = {Path(file.href).name for file in _package_files(mets, packages)}
    missing = sorted(set(packages) - listed)
    assert not missing, f"packages missing from the METS: {missing}"
    found = _packages_in_bag(run, packages)
    if found is None:
        evidence.pending("the AIP was not downloaded (larger than the size cap); only the METS was checked")
        return
    present = {Path(name).name for name in found}
    missing = sorted(set(packages) - present)
    assert not missing, f"packages missing from the AIP: {missing}"


# Validation --------------------------------------------------------------------------


def _matroska_files(mets: AIPMets) -> list[METSFile]:
    files = [file for file in mets.files("original") if file.href.lower().endswith(MATROSKA_SUFFIX)]
    assert files, "the METS lists no Matroska original"
    return files


@then("the validation information for the Matroska files is accurate")
def matroska_validation_accurate(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    tasks = job_tasks(am, evidence, run, VALIDATE_JOB, unit_uuid=run.transfer_uuid)
    failures = [task.file_name or task.uuid for task in tasks if task.exit_code not in (0, None)]
    assert not failures, f"validation tasks that failed: {failures}"
    mets = _mets(run)
    problems: list[str] = []
    notes: list[str] = []
    for file in _matroska_files(mets):
        for event in mets.events_of_type(file, "validation"):
            if event.outcome != "pass":
                problems.append(f"{file.href}: outcome {event.outcome!r} ({event.outcome_detail_note[:160]})")
            notes.append(f"{Path(file.href).name}: {event.outcome_detail_note[:160]}")
    assert not problems, "validation outcomes:\n- " + "\n- ".join(problems)
    evidence.note("validation: " + "; ".join(notes))


@then("one validation PREMIS event per file is present in the METS")
def one_validation_event_per_file(run: UnitRun) -> None:
    mets = _mets(run)
    counts = {file.href: len(mets.events_of_type(file, "validation")) for file in _matroska_files(mets)}
    wrong = {href: count for href, count in counts.items() if count != 1}
    assert not wrong, f"files without exactly one validation event: {wrong}"


@then("the validation event detail indicates that MediaConch was the tool used")
def validation_by_mediaconch(evidence: Evidence, run: UnitRun) -> None:
    mets = _mets(run)
    details = {
        file.href: [event.detail for event in mets.events_of_type(file, "validation")]
        for file in _matroska_files(mets)
    }
    other = {
        href: found for href, found in details.items() if not any("MediaConch" in detail for detail in found)
    }
    assert not other, f"validation events not made with MediaConch: {other}"
    evidence.note("validation tools: " + "; ".join(detail for found in details.values() for detail in found))
