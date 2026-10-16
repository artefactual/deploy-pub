"""Steps that check normalization: derivatives in the AIP and the DIP, thumbnails and transcription."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from pytest_bdd import then

from rt.assertions.mets import AIPMets, METSFile
from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_COMPLETED, AMClient, TaskDetails, UnitRun
from rt.pipeline.fpr import FPR
from steps.pipeline_steps import job_tasks

PRESERVATION_JOB = "Normalize for preservation"
ACCESS_JOB = "Normalize for access"
SERVICE_ACCESS_JOB = "Normalize service files for access"
NORMALIZATION_JOBS = (PRESERVATION_JOB, ACCESS_JOB, SERVICE_ACCESS_JOB)
MANUAL_NORMALIZATION_MICROSERVICE = "Process manually normalized files"
THUMBNAIL_JOB = "Normalize for thumbnails"
# The purpose of the rule that applies when a format has no thumbnail rule of its own.
DEFAULT_THUMBNAIL_PURPOSE = "default_thumbnail:"
# What the normalize script prints for a format without a thumbnail rule when default icons are off.
NO_THUMBNAIL_RULE = "Thumbnail not generated as no rule found for format"
_EMBEDDED_ICON = re.compile(r'DEFAULT_THUMBNAIL\s*=\s*"""(.*?)"""', re.DOTALL)

# Exit codes of the normalize client script.
EXIT_NORMALIZED = 0
EXIT_FAILED = 1
EXIT_NO_RULE = 2

ORIGINALS_ONLY_USES = {"original", "submissionDocumentation", "metadata"}

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_DERIVATIVE_NAME = re.compile(rf"^(?P<stem>.+)-(?P<uuid>{UUID})\.(?P<extension>[^.]+)$")
_DIP_OBJECT_NAME = re.compile(rf"^(?P<uuid>{UUID})-(?P<name>.+)$")


def _mets(run: UnitRun) -> AIPMets:
    assert run.aip is not None, "no AIP was fetched from the Storage Service"
    return AIPMets(run.aip.mets)


def _describe(task: TaskDetails) -> str:
    last = next((line.strip() for line in reversed(task.stderr.splitlines()) if line.strip()), "")
    label = f"{task.file_name or task.uuid} (exit {task.exit_code})"
    return f"{label}: {last}" if last else label


def _failed(tasks: list[TaskDetails]) -> list[str]:
    return [_describe(task) for task in tasks if task.exit_code not in (EXIT_NORMALIZED, EXIT_NO_RULE)]


def _normalized(tasks: list[TaskDetails]) -> list[TaskDetails]:
    return [task for task in tasks if task.exit_code == EXIT_NORMALIZED]


def _check_rules_applied(
    am: AMClient, evidence: Evidence, run: UnitRun, job_names: tuple[str, ...]
) -> dict[str, list[TaskDetails]]:
    """Assert that the normalization jobs ran and that every file with a rule was normalized."""
    missing = [name for name in job_names if not run.jobs_named(name)]
    assert not missing, (
        f"jobs that did not run: {missing}; jobs: {sorted({str(job.get('name')) for job in run.all_jobs()})}"
    )
    tasks = {name: job_tasks(am, evidence, run, name) for name in job_names}
    problems = [f"{name}: {failure}" for name, found in tasks.items() for failure in _failed(found)]
    if problems:
        # The later criteria can still judge the derivatives that were produced.
        evidence.fail("files whose normalization command failed:\n- " + "\n- ".join(problems))
    for name, found in tasks.items():
        without_rule = sum(1 for task in found if task.exit_code == EXIT_NO_RULE)
        evidence.note(f"{name}: {len(_normalized(found))} files normalized, {without_rule} without a rule")
        assert _normalized(found), f"no file was normalized by {name!r}"
    return tasks


def _preservation_derivatives(mets: AIPMets) -> list[tuple[METSFile, str]]:
    """Each preservation file with the UUID of its source; the file name must carry the file's UUID."""
    problems: list[str] = []
    derivatives: list[tuple[METSFile, str]] = []
    for file in mets.files("preservation"):
        match = _DERIVATIVE_NAME.match(Path(file.href).name)
        if match is None or match.group("uuid") != mets.file_uuid(file):
            problems.append(f"{file.href} is not named <original>-<its UUID>.<extension>")
            continue
        source = mets.derivation_source(file)
        if not source:
            problems.append(f"{file.href} has no derivation relationship to an original")
            continue
        derivatives.append((file, source))
    assert not problems, "preservation derivatives:\n- " + "\n- ".join(problems)
    return derivatives


def _check_dip_has_access_copies(
    am: AMClient, evidence: Evidence, run: UnitRun, job_names: tuple[str, ...]
) -> None:
    assert run.dip is not None, "the Storage Service has no DIP for this AIP"
    if run.dip.root is None:
        evidence.pending(
            "the DIP was not downloaded (larger than the size cap); only its existence was checked"
        )
        return
    mets = _mets(run)
    known = {mets.file_uuid(file) for file in mets.files()}
    objects = [path.name for path in run.dip.objects()]
    evidence.note(f"DIP {run.dip.basename} objects: {', '.join(objects) or 'none'}")
    normalized = [task for name in job_names for task in _normalized(job_tasks(am, evidence, run, name))]
    assert normalized, f"no file was normalized for access by {list(job_names)}"
    unknown = [
        name
        for name in objects
        if (m := _DIP_OBJECT_NAME.match(name)) is None or m.group("uuid") not in known
    ]
    assert not unknown, f"DIP objects not named after a file of the METS: {unknown}"
    assert len(objects) >= len(normalized), (
        f"the DIP has {len(objects)} objects for {len(normalized)} files normalized for access"
    )
    missing = [
        task.file_name
        for task in normalized
        if task.job_name == ACCESS_JOB and not any(name.startswith(f"{task.file_uuid}-") for name in objects)
    ]
    assert not missing, f"files normalized for access without an access copy in the DIP: {missing}"


# Normalization choices ------------------------------------------------------------


@then("the files are normalized for preservation and access as per the rules")
def normalized_for_preservation_and_access(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    _check_rules_applied(am, evidence, run, (PRESERVATION_JOB, ACCESS_JOB))


@then("the files are normalized for preservation as per the rules")
def normalized_for_preservation(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    _check_rules_applied(am, evidence, run, (PRESERVATION_JOB,))


@then(
    "the preservation derivatives are added to the AIP with a UUID suffix and the appropriate file extension"
)
def preservation_derivatives_in_aip(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    mets = _mets(run)
    derivatives = _preservation_derivatives(mets)
    assert derivatives, "the METS lists no preservation derivatives"
    expected = {task.file_uuid for task in _normalized(job_tasks(am, evidence, run, PRESERVATION_JOB))}
    found = {source for _, source in derivatives}
    assert found == expected, (
        f"originals with a preservation derivative {sorted(found)} differ from the files normalized "
        f"for preservation {sorted(expected)}"
    )
    evidence.note(
        f"{len(derivatives)} preservation derivatives: "
        + ", ".join(Path(file.href).name for file, _ in derivatives)
    )


@then("the access derivatives are added to the DIP")
def access_derivatives_in_dip(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    _check_dip_has_access_copies(am, evidence, run, (ACCESS_JOB, SERVICE_ACCESS_JOB))


@then("access derivatives are created and added to the DIP")
def access_derivatives_created(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    _check_rules_applied(am, evidence, run, (ACCESS_JOB,))
    _check_dip_has_access_copies(am, evidence, run, (ACCESS_JOB,))


@then("normalization PREMIS events are added to the METS")
def normalization_events_in_mets(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    mets = _mets(run)
    # The pipeline records normalization events for preservation derivatives only;
    # access derivatives leave with the DIP and have no event in either METS.
    normalized = {task.file_uuid for task in _normalized(job_tasks(am, evidence, run, PRESERVATION_JOB))}
    assert normalized, "no file was normalized for preservation"
    missing: list[str] = []
    for uuid in sorted(normalized):
        file = mets.file_by_uuid(uuid)
        if file is None or not mets.events_of_type(file, "normalization"):
            missing.append(uuid if file is None else file.href)
    assert not missing, f"normalized files without a normalization event in the METS: {missing}"
    events = [event for event in mets.all_events() if event.type == "normalization"]
    evidence.note(f"{len(events)} normalization events in the METS")


@then("normalization does not occur")
def normalization_does_not_occur(run: UnitRun) -> None:
    ran = [name for name in NORMALIZATION_JOBS if run.jobs_named(name)]
    assert not ran, f"normalization jobs ran: {ran}"
    events = [event for event in _mets(run).all_events() if event.type == "normalization"]
    assert not events, f"the METS has {len(events)} normalization events"


@then("the AIP contains originals only")
def aip_contains_originals_only(evidence: Evidence, run: UnitRun) -> None:
    mets = _mets(run)
    extra = sorted(use for use in mets.filegrp_uses() if use not in ORIGINALS_ONLY_USES)
    assert not extra, f"the METS has file groups other than the originals: {extra}"
    assert run.aip is not None
    if run.aip.root is None:
        evidence.note("the AIP was not downloaded; only the METS was checked")
        return
    objects = run.aip.root / "data" / "objects"
    derivatives = sorted(
        str(path.relative_to(objects))
        for path in objects.rglob("*")
        if path.is_file()
        and path.relative_to(objects).parts[0] not in ("metadata", "submissionDocumentation")
        and _DERIVATIVE_NAME.match(path.name)
    )
    assert not derivatives, f"files named like derivatives in the AIP: {derivatives}"


# Thumbnails ------------------------------------------------------------------------


@then("thumbnails are created for all digital objects in the AIP")
def thumbnails_for_all_objects(evidence: Evidence, run: UnitRun) -> None:
    mets = _mets(run)
    assert run.aip is not None
    if run.aip.root is None:
        evidence.pending("the AIP was not downloaded (larger than the size cap)")
        return
    thumbnails = run.aip.root / "data" / "thumbnails"
    originals = mets.files("original")
    missing = [file.href for file in originals if not (thumbnails / f"{mets.file_uuid(file)}.jpg").is_file()]
    assert not missing, f"originals without a thumbnail under data/thumbnails: {missing}"
    evidence.note(f"{len(originals)} thumbnails under data/thumbnails")


def _default_icon(fpr: FPR) -> bytes:
    """The icon the default thumbnail rule's command writes, taken from the script of the command itself."""
    rules = [
        rule
        for rule in fpr.fp_rules()
        if rule.enabled and rule.description.startswith(DEFAULT_THUMBNAIL_PURPOSE)
    ]
    assert rules, "the Format Policy Registry has no enabled default thumbnail rule"
    command = fpr.fp_command(rules[0].command, enabled=True)
    script = fpr.command_text(command.uuid)
    match = _EMBEDDED_ICON.search(script)
    assert match, f"the command {command.description!r} embeds no DEFAULT_THUMBNAIL"
    return base64.b64decode(re.sub(r"\s", "", match.group(1)))


def _thumbnails_dir(evidence: Evidence, run: UnitRun) -> Path | None:
    assert run.aip is not None
    if run.aip.root is None:
        evidence.pending("the AIP was not downloaded (larger than the size cap)")
        return None
    return run.aip.root / "data" / "thumbnails"


@then("thumbnails are created for all digital objects in the AIP where meaningful thumbnails can be created")
def thumbnails_where_meaningful(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    thumbnails = _thumbnails_dir(evidence, run)
    if thumbnails is None:
        return
    tasks = job_tasks(am, evidence, run, THUMBNAIL_JOB)
    assert tasks, f"the job {THUMBNAIL_JOB!r} has no tasks"
    skipped = [task for task in tasks if NO_THUMBNAIL_RULE in task.stdout]
    generated = [task for task in tasks if task not in skipped and task.exit_code == 0]
    missing = [
        task.file_name or task.file_uuid
        for task in generated
        if not (thumbnails / f"{task.file_uuid}.jpg").is_file()
    ]
    assert not missing, (
        f"objects normalized for thumbnails without a thumbnail under data/thumbnails: {missing}"
    )
    unexpected = [
        task.file_name or task.file_uuid
        for task in skipped
        if (thumbnails / f"{task.file_uuid}.jpg").is_file()
    ]
    assert not unexpected, f"objects without a thumbnail rule that got a thumbnail anyway: {unexpected}"
    evidence.note(
        f"{len(generated)} thumbnails created; no thumbnail rule for "
        + (", ".join(task.file_name or task.file_uuid for task in skipped) or "no object")
    )


@then("no thumbnail is the default icon")
def no_default_icons(fpr: FPR, evidence: Evidence, run: UnitRun) -> None:
    thumbnails = _thumbnails_dir(evidence, run)
    if thumbnails is None:
        return
    icon = _default_icon(fpr)
    found = sorted(thumbnails.glob("*.jpg")) if thumbnails.is_dir() else []
    defaults = [path.name for path in found if path.read_bytes() == icon]
    assert not defaults, f"thumbnails that are the default icon: {defaults}"
    evidence.note(
        f"{len(found)} thumbnails, none equal to the default icon "
        f"({len(icon)} bytes, md5 {hashlib.md5(icon).hexdigest()})"
    )


@then("no thumbnails are created")
def no_thumbnails(evidence: Evidence, run: UnitRun) -> None:
    assert run.aip is not None
    if run.aip.root is None:
        evidence.pending("the AIP was not downloaded (larger than the size cap)")
        return
    thumbnails = run.aip.root / "data" / "thumbnails"
    found = sorted(path.name for path in thumbnails.iterdir()) if thumbnails.is_dir() else []
    assert not found, f"thumbnails were created: {found}"


# Service files ---------------------------------------------------------------------


@then("the service files are used to create the access derivatives")
def service_files_used(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    _check_rules_applied(am, evidence, run, (SERVICE_ACCESS_JOB,))
    tasks = job_tasks(am, evidence, run, SERVICE_ACCESS_JOB)
    not_service = [task.file_name or task.uuid for task in tasks if "objects/service/" not in task.stdout]
    assert not not_service, f"tasks whose output does not name a service file: {not_service}"


@then("the task output shows that the service files were used to create access copies")
def task_output_names_service_files(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    tasks = job_tasks(am, evidence, run, SERVICE_ACCESS_JOB)
    assert tasks, f"the job {SERVICE_ACCESS_JOB!r} has no tasks"
    missing = [task.file_name or task.uuid for task in tasks if "objects/service/" not in task.stdout]
    assert not missing, f"tasks whose output does not name a service file: {missing}"
    failures = _failed(tasks)
    assert not failures, "service files that could not be normalized:\n- " + "\n- ".join(failures)
    evidence.note(f"{len(_normalized(tasks))} access copies created from service files")


# Manual normalization --------------------------------------------------------------


@then("normalization does not occur during the Normalize microservice")
def no_normalization_commands(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    tasks = job_tasks(am, evidence, run, PRESERVATION_JOB)
    assert tasks, f"the job {PRESERVATION_JOB!r} did not run"
    executed = [task.file_name or task.uuid for task in tasks if "Command to execute" in task.stdout]
    assert not executed, f"normalization commands ran for: {executed}"
    # The job also visits the manually normalized copies themselves and skips them.
    originals = [task for task in tasks if "- skipping" not in task.stdout]
    assert originals, "no original was visited by the job"
    not_manual = [
        task.file_name or task.uuid for task in originals if "manually normalized into" not in task.stdout
    ]
    assert not not_manual, f"originals not recognized as manually normalized: {not_manual}"


@then(
    'the "Process manually normalized files" microservice recognizes the manualNormalization/preservation directory'
)
def manual_normalization_recognized(run: UnitRun) -> None:
    jobs = [job for job in run.all_jobs() if job.get("microservice") == MANUAL_NORMALIZATION_MICROSERVICE]
    assert jobs, f"no job of the microservice {MANUAL_NORMALIZATION_MICROSERVICE!r} ran"
    not_complete = [job.get("name") for job in jobs if job.get("status") != JOB_COMPLETED]
    assert not not_complete, f"jobs that did not complete: {not_complete}"
    assert _mets(run).files("preservation"), "the METS lists no preservation copies"


@then("UUIDs are assigned to the preservation copies and included in their filenames")
def preservation_copies_named_with_uuids(evidence: Evidence, run: UnitRun) -> None:
    derivatives = _preservation_derivatives(_mets(run))
    assert derivatives, "the METS lists no preservation copies"
    evidence.note("preservation copies: " + ", ".join(Path(file.href).name for file, _ in derivatives))


@then(
    "the AIP contains the originals and the preservation copies as if Archivematica had normalized for preservation"
)
def originals_and_preservation_copies(run: UnitRun) -> None:
    mets = _mets(run)
    originals = {mets.file_uuid(file) for file in mets.files("original")}
    sources = {source for _, source in _preservation_derivatives(mets)}
    assert sources == originals, (
        f"originals without a preservation copy: {sorted(originals - sources)}; "
        f"preservation copies of unknown files: {sorted(sources - originals)}"
    )


@then("the AIP includes normalization events")
def aip_includes_normalization_events(run: UnitRun) -> None:
    mets = _mets(run)
    missing = [file.href for file in mets.files("original") if not mets.events_of_type(file, "normalization")]
    assert not missing, f"originals without a normalization event: {missing}"


# Transcription ---------------------------------------------------------------------


@then("the AIP contains a text file of the transcribed contents in the metadata/OCRfiles directory")
def ocr_text_in_aip(evidence: Evidence, run: UnitRun) -> None:
    mets = _mets(run)
    listed = mets.files("text/ocr")
    assert listed, f"the METS has no text/ocr file group; groups: {sorted(mets.filegrp_uses())}"
    assert run.aip is not None
    if run.aip.root is None:
        evidence.pending("the AIP was not downloaded (larger than the size cap); only the METS was checked")
        return
    directory = run.aip.root / "data" / "objects" / "metadata" / "OCRfiles"
    texts = sorted(directory.glob("*.txt")) if directory.is_dir() else []
    assert texts, f"no text file under objects/metadata/OCRfiles; METS lists {[file.href for file in listed]}"
    empty = [path.name for path in texts if not path.read_text(encoding="utf-8", errors="replace").strip()]
    assert not empty, f"empty transcriptions: {empty}"
    evidence.note(f"transcriptions: {', '.join(path.name for path in texts)}")
