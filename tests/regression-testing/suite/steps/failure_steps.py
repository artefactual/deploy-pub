"""Steps for transfers that are meant to fail: the virus scan and the failure report email."""

from __future__ import annotations

import time

from pytest_bdd import given, then

from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_FAILED, STATUS_FAILED, AMClient, UnitRun
from rt.pipeline.container import Container
from rt.settings import Settings
from steps.pipeline_steps import job_tasks

VIRUS_SCAN_MICROSERVICE = "Scan for viruses"
FAIL_REPORT_MARKER = "Fail Report"
MAIL_ATTEMPTS = 6
MAIL_INTERVAL = 2


@given("the transfer is expected to fail")
def transfer_expected_to_fail(evidence: Evidence) -> None:
    """Jobs that fail in this scenario are part of the test, not warnings."""
    evidence.extra["expected_failure"] = True


def _virus_scan_jobs(run: UnitRun) -> list[dict[str, object]]:
    return [
        job
        for job in run.jobs.get(run.transfer_uuid, [])
        if job.get("microservice") == VIRUS_SCAN_MICROSERVICE
    ]


@then("the virus scan job fails")
def virus_scan_job_fails(evidence: Evidence, run: UnitRun) -> None:
    jobs = _virus_scan_jobs(run)
    assert jobs, f"no job of the microservice {VIRUS_SCAN_MICROSERVICE!r} ran; {run.describe()}"
    failed = [job for job in jobs if job.get("status") == JOB_FAILED]
    assert failed, f"no virus scan job failed: {[(job.get('name'), job.get('status')) for job in jobs]}"
    assert run.final_status == STATUS_FAILED, f"the transfer did not fail: {run.describe()}"
    evidence.note("failed job: " + ", ".join(str(job.get("name")) for job in failed))


@then("the standard streams report which files failed virus scanning")
def streams_report_infected_files(am: AMClient, evidence: Evidence, run: UnitRun) -> None:
    failed_jobs = [job for job in _virus_scan_jobs(run) if job.get("status") == JOB_FAILED]
    tasks = [
        task
        for job in failed_jobs
        for task in job_tasks(am, evidence, run, str(job.get("name")), unit_uuid=run.transfer_uuid)
    ]
    infected = [task for task in tasks if task.exit_code not in (0, None)]
    assert infected, "no task of the virus scan failed"
    silent = [task.file_name or task.uuid for task in infected if not (task.stdout + task.stderr).strip()]
    assert not silent, f"failed tasks with empty standard streams: {silent}"
    unnamed = [
        task.file_name or task.uuid
        for task in infected
        if not task.file_name or task.file_name not in task.stdout + task.stderr
    ]
    assert not unnamed, f"failed tasks whose standard streams do not name the file: {unnamed}"
    evidence.note("files that failed virus scanning: " + ", ".join(task.file_name for task in infected))


def _mail_file(container: Container, mail_dir: str, marker: str, evidence: Evidence) -> str | None:
    """The newest message in the pipeline's mail directory that mentions the marker."""
    for _ in range(MAIL_ATTEMPTS):
        names = container.listdir(mail_dir) if container.exists(mail_dir) else []
        for name in sorted(names, reverse=True):
            text = container.read_text(f"{mail_dir}/{name}")
            if marker in text and FAIL_REPORT_MARKER in text:
                evidence.write_text(f"mail/{name}", text)
                return text
        time.sleep(MAIL_INTERVAL)
    return None


def _console_mail(container: Container, evidence: Evidence, marker: str) -> str | None:
    """The message as printed to the service output by the console email backend."""
    for _ in range(MAIL_ATTEMPTS):
        output = container.compose_output(evidence.started)
        lines = output.splitlines()
        for index, line in enumerate(lines):
            # The subject header is folded: the unit name and UUID follow on the next line.
            header = " ".join(lines[index : index + 3])
            if "Subject:" in line and FAIL_REPORT_MARKER in line and marker in header:
                excerpt = "\n".join(lines[max(0, index - 10) : index + 60])
                evidence.write_text("mail/console-output.txt", excerpt)
                return excerpt
        time.sleep(MAIL_INTERVAL)
    return None


@then("the user receives an emailed version of the failure report")
def failure_report_email_received(
    settings: Settings, container: Container, evidence: Evidence, run: UnitRun
) -> None:
    assert run.final_status == STATUS_FAILED, f"the transfer did not fail: {run.describe()}"
    if settings.mail_dir:
        message = _mail_file(container, settings.mail_dir, run.transfer_uuid, evidence)
        source = f"the mail directory {settings.mail_dir}"
    else:
        message = _console_mail(container, evidence, run.transfer_uuid)
        source = "the service output (console email backend)"
    assert message is not None, f"no failure report for transfer {run.transfer_uuid} found in {source}"
    subject = next((line.strip() for line in message.splitlines() if "Subject:" in line), "")
    recipients = next((line.strip() for line in message.splitlines() if "To:" in line), "")
    evidence.note(f"failure report found in {source}: {subject} {recipients}".strip())
