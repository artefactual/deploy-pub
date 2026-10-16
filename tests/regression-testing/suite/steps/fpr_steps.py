"""Steps that change the Format Policy Registry through Preservation planning and check the effect.

Every change registers an action with the ``restore`` fixture, so the pipeline
is back to its previous state when the scenario ends, whatever its outcome.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from playwright.sync_api import Page
from pytest_bdd import given, parsers, then, when

from rt.assertions.mets import AIPMets
from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_COMPLETED, AMClient, UnitRun
from rt.pipeline.fpr import FPCOMMAND, FPR, IDCOMMAND, FPREntry
from steps.pipeline_steps import job_tasks

SIEGFRIED = "Identify using Siegfried"
FIDO = "Identify using Fido"
IDENTIFY_JOB = "Identify file format"
CHARACTERIZE_JOB = "Characterize and extract metadata"
PRESERVATION_JOB = "Normalize for preservation"
CHARACTERIZATION = "characterization"
MARKER_PREFIX = "regression-testing marker"

Restore = list[tuple[str, Callable[[], None]]]


@pytest.fixture
def fpr_state() -> dict[str, Any]:
    """Facts a scenario records while it changes the registry, for its later criteria."""
    return {}


def _mets(run: UnitRun) -> AIPMets:
    assert run.aip is not None, "no AIP was fetched from the Storage Service"
    return AIPMets(run.aip.mets)


def _marker() -> str:
    return f"{MARKER_PREFIX} {datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"


def _identification_problems(mets: AIPMets, tool: str, forbidden: str | None = None) -> list[str]:
    """Originals without a positive identification event by the tool, or with one by the forbidden tool."""
    problems: list[str] = []
    for file in mets.files("original"):
        events = mets.events_of_type(file, "format identification")
        by_tool = [event for event in events if f'program="{tool}"' in event.detail]
        if not by_tool:
            problems.append(f"{file.href}: no {tool} event ({[event.detail for event in events]})")
        elif not any(event.outcome == "Positive" for event in by_tool):
            problems.append(f"{file.href}: outcome {[event.outcome for event in by_tool]}")
        if forbidden and any(f'program="{forbidden}"' in event.detail for event in events):
            problems.append(f"{file.href}: identified by {forbidden}")
    return problems


def _ensure_id_command(fpr: FPR, evidence: Evidence, restore: Restore, description: str) -> FPREntry:
    """Make an identification command the enabled one; the previous one comes back at the end."""
    previous = next((entry for entry in fpr.id_commands() if entry.enabled), None)
    wanted = fpr.id_command(description)
    if not wanted.enabled:
        if previous is not None:
            restore.append(
                (
                    f"the {previous.description!r} identification command",
                    lambda: fpr.set_enabled(IDCOMMAND, previous.uuid, True),
                )
            )
        fpr.set_enabled(IDCOMMAND, wanted.uuid, True)
    wanted = fpr.id_command(description)
    assert wanted.enabled, f"{description!r} could not be enabled"
    evidence.note(f"identification command: {description}")
    return wanted


def _register_original_revision(fpr: FPR, restore: Restore, command: FPREntry, original_command: str) -> None:
    """Bring back the content of a command's original revision at the end, unless it is current again."""

    def restore_original() -> None:
        current = fpr.fp_command(command.description, enabled=True)
        if fpr.edit_form(FPCOMMAND, current.uuid)["command"].strip() == original_command.strip():
            return
        fpr.submit_edit(FPCOMMAND, command.uuid, fpr.edit_form(FPCOMMAND, command.uuid))

    restore.append((f"the original revision of {command.description!r}", restore_original))


def _edited_fields(fields: dict[str, str], marker: str) -> dict[str, str]:
    edited = dict(fields)
    edited["command"] = f'echo "{marker}"\n' + fields["command"]
    if fields.get("script_type") == "command":
        edited["script_type"] = "bashScript"
    return edited


# Identification command -----------------------------------------------------------


@given("Siegfried is the enabled identification command")
def siegfried_enabled(fpr: FPR, evidence: Evidence, restore: Restore) -> None:
    _ensure_id_command(fpr, evidence, restore, SIEGFRIED)


@given("Fido is the enabled identification command")
def fido_enabled(fpr: FPR, evidence: Evidence, restore: Restore) -> None:
    _ensure_id_command(fpr, evidence, restore, FIDO)


@when("the user enables the Fido identification command in Preservation planning")
def user_enables_fido(ui: Page, fpr: FPR, evidence: Evidence, restore: Restore) -> None:
    previous = next((entry for entry in fpr.id_commands() if entry.enabled), None)
    fido = fpr.id_command(FIDO)
    if previous is not None and previous.uuid != fido.uuid:
        restore.append(
            (
                f"the {previous.description!r} identification command",
                lambda: fpr.set_enabled(IDCOMMAND, previous.uuid, True),
            )
        )
    ui.goto("/fpr/idcommand/")
    evidence.screenshot("identification commands before")
    ui.goto(f"/fpr/idcommand/{fido.uuid}/delete/")
    ui.get_by_role("button", name="Enable").click()
    ui.wait_for_url(f"**/fpr/idcommand/{fido.uuid}/")
    ui.goto("/fpr/idcommand/")
    evidence.screenshot("identification commands after")


@then("the Siegfried command is disabled")
def siegfried_disabled(fpr: FPR) -> None:
    assert not fpr.id_command(SIEGFRIED).enabled, f"{SIEGFRIED!r} is still enabled"


@then("the Fido command is enabled")
def fido_is_enabled(fpr: FPR) -> None:
    assert fpr.id_command(FIDO).enabled, f"{FIDO!r} is not enabled"


@then("the transfer is identified by Fido instead of Siegfried")
def identified_by_fido(evidence: Evidence, run: UnitRun) -> None:
    problems = _identification_problems(_mets(run), "Fido", forbidden="Siegfried")
    assert not problems, "identification:\n- " + "\n- ".join(problems)
    evidence.note("every original carries a positive Fido identification event and none by Siegfried")


@then("Fido identifies the file formats and versions accurately")
def fido_accurate(evidence: Evidence, run: UnitRun) -> None:
    mets = _mets(run)
    problems = _identification_problems(mets, "Fido")
    formats: list[str] = []
    for file in mets.files("original"):
        designation = mets.format_designation(file)
        if not designation["registry_key"]:
            problems.append(f"{file.href}: no PRONOM identifier ({designation})")
        formats.append(
            f"{file.href.rsplit('/', 1)[-1]}: {designation['registry_key']} {designation['name']}".strip()
        )
    assert not problems, "identification:\n- " + "\n- ".join(problems)
    evidence.note("formats: " + "; ".join(formats))


@then("one format identification PREMIS event per file is present in the METS")
def one_identification_event_per_file(run: UnitRun) -> None:
    mets = _mets(run)
    counts = {
        file.href: len(mets.events_of_type(file, "format identification")) for file in mets.files("original")
    }
    wrong = {href: count for href, count in counts.items() if count != 1}
    assert not wrong, f"originals without exactly one format identification event: {wrong}"


@then("the format identification event detail indicates that Fido was the tool used")
def identification_detail_names_fido(evidence: Evidence, run: UnitRun) -> None:
    mets = _mets(run)
    details = {
        file.href: [event.detail for event in mets.events_of_type(file, "format identification")]
        for file in mets.files("original")
    }
    other = {
        href: found
        for href, found in details.items()
        if not any('program="Fido"' in detail for detail in found)
    }
    assert not other, f"identification events not made with Fido: {other}"
    evidence.note(
        "identification tool: "
        + "; ".join(sorted({detail for found in details.values() for detail in found}))
    )


@then("Fido identifies the formats during the Identify file format microservice")
def fido_identifies_formats(evidence: Evidence, run: UnitRun) -> None:
    jobs = [job for job in run.jobs.get(run.transfer_uuid, []) if job.get("name") == IDENTIFY_JOB]
    assert jobs, f"the job {IDENTIFY_JOB!r} did not run on the transfer"
    not_complete = [job.get("status") for job in jobs if job.get("status") != JOB_COMPLETED]
    assert not not_complete, f"the job {IDENTIFY_JOB!r} finished with {not_complete}"
    problems = _identification_problems(_mets(run), "Fido")
    assert not problems, "identification:\n- " + "\n- ".join(problems)
    evidence.note("every original carries a positive Fido identification event")


# Disabled command -------------------------------------------------------------------


@given(parsers.parse('the "{description}" characterization command is enabled'))
def characterization_command_enabled(fpr: FPR, evidence: Evidence, description: str) -> None:
    command = fpr.fp_command(description, usage=CHARACTERIZATION, enabled=True)
    evidence.note(f"characterization command {command.description!r} ({command.uuid}) is enabled")


@when(
    parsers.parse('the user disables the "{description}" characterization command in Preservation planning')
)
def user_disables_command(
    ui: Page, fpr: FPR, evidence: Evidence, restore: Restore, fpr_state: dict[str, Any], description: str
) -> None:
    command = fpr.fp_command(description, usage=CHARACTERIZATION, enabled=True)
    rules = [rule for rule in fpr.fp_rules() if rule.command == command.description and rule.enabled]
    fpr_state["command"] = command
    fpr_state["attempts"] = {rule.uuid: rule.attempts for rule in rules}

    def restore_command_and_rules() -> None:
        # Enabling a command brings back the command only; its rules are re-enabled one by one.
        fpr.set_enabled(FPCOMMAND, command.uuid, True)
        disabled = {rule.uuid for rule in fpr.fp_rules() if not rule.enabled}
        for rule in rules:
            if rule.uuid in disabled:
                fpr.toggle_rule(rule.uuid)

    restore.append(
        (f"the {command.description!r} command and its {len(rules)} rules", restore_command_and_rules)
    )
    ui.goto(f"/fpr/fpcommand/{command.uuid}/")
    evidence.screenshot("command before disabling")
    ui.goto(f"/fpr/fpcommand/{command.uuid}/delete/")
    evidence.screenshot("disable confirmation")
    ui.get_by_role("button", name="Disable").click()
    ui.wait_for_url(f"**/fpr/fpcommand/{command.uuid}/")
    current = next(entry for entry in fpr.fp_commands(CHARACTERIZATION) if entry.uuid == command.uuid)
    assert not current.enabled, f"{command.description!r} is still enabled"
    evidence.note(f"disabled {command.description!r} and its {len(rules)} rules")


@then(parsers.parse('the "{description}" command does not run'))
def command_does_not_run(fpr: FPR, evidence: Evidence, fpr_state: dict[str, Any], description: str) -> None:
    before: dict[str, int] = fpr_state["attempts"]
    after = {rule.uuid: rule.attempts for rule in fpr.fp_rules() if rule.uuid in before}
    moved = {uuid: (before[uuid], after.get(uuid)) for uuid in before if after.get(uuid) != before[uuid]}
    assert not moved, f"rules of {description!r} whose attempt counter moved: {moved}"
    evidence.note(f"the {len(before)} rules of {description!r} kept their attempt counters")


@then(parsers.parse('the task output does not show that the "{description}" command ran'))
def task_output_without_command(
    am: AMClient, evidence: Evidence, run: UnitRun, fpr_state: dict[str, Any], description: str
) -> None:
    tasks = job_tasks(am, evidence, run, CHARACTERIZE_JOB, unit_uuid=run.transfer_uuid)
    assert tasks, f"the job {CHARACTERIZE_JOB!r} did not run on the transfer"
    tool = str(fpr_state["command"].tool or description)
    mentions = [
        task.file_name or task.uuid for task in tasks if tool.lower() in (task.stdout + task.stderr).lower()
    ]
    assert not mentions, f"tasks whose output mentions {tool!r}: {mentions}"
    evidence.note(f"{len(tasks)} characterization tasks without {tool!r} in their output")


@then(parsers.parse('the METS does not show that the "{description}" command ran'))
def mets_without_command(
    evidence: Evidence, run: UnitRun, fpr_state: dict[str, Any], description: str
) -> None:
    mets = _mets(run)
    tool = str(fpr_state["command"].tool or description)
    mentions = [
        file.href
        for file in mets.files("original")
        if any(tool.lower() in extension.lower() for extension in mets.characteristics_extensions(file))
    ]
    assert not mentions, f"originals whose characteristics mention {tool!r}: {mentions}"


@then(parsers.parse('the "{description}" command can be re-enabled'))
def command_can_be_reenabled(
    ui: Page, fpr: FPR, evidence: Evidence, fpr_state: dict[str, Any], description: str
) -> None:
    command: FPREntry = fpr_state["command"]
    ui.goto(f"/fpr/fpcommand/{command.uuid}/delete/")
    ui.get_by_role("button", name="Enable").click()
    ui.wait_for_url(f"**/fpr/fpcommand/{command.uuid}/")
    evidence.screenshot("command re-enabled")
    current = next(entry for entry in fpr.fp_commands(CHARACTERIZATION) if entry.uuid == command.uuid)
    assert current.enabled, f"{command.description!r} is still disabled"


# Edited command ---------------------------------------------------------------------


@when(parsers.parse('the user edits the "{description}" command to print a marker'))
def user_edits_command(
    ui: Page, fpr: FPR, evidence: Evidence, restore: Restore, fpr_state: dict[str, Any], description: str
) -> None:
    command = fpr.fp_command(description, enabled=True)
    fields = fpr.edit_form(FPCOMMAND, command.uuid)
    marker = _marker()
    fpr_state.update(command=command, marker=marker, original_command=fields["command"])
    _register_original_revision(fpr, restore, command, fields["command"])
    ui.goto(f"/fpr/fpcommand/{command.uuid}/edit/")
    evidence.screenshot("edit form")
    edited = _edited_fields(fields, marker)
    if edited["script_type"] != fields.get("script_type"):
        ui.select_option("select[name='script_type']", edited["script_type"])
    # The form comes without the tool selected; a user has to pick it again.
    ui.select_option("select[name='tool']", label=command.tool)
    ui.fill("textarea[name='command']", edited["command"])
    ui.get_by_role("button", name="Save").click()
    ui.wait_for_url("**/fpr/fpcommand/**")
    new = fpr.fp_command(description, enabled=True)
    assert new.uuid != command.uuid, "saving the form did not create a new revision"
    fpr_state["edited"] = new
    evidence.note(
        f"edited {description!r}: revision {command.uuid} replaced by {new.uuid}; marker {marker!r}"
    )


@given(parsers.parse('the user has edited the "{description}" command'))
def command_edited(
    fpr: FPR, evidence: Evidence, restore: Restore, fpr_state: dict[str, Any], description: str
) -> None:
    command = fpr.fp_command(description, enabled=True)
    fields = fpr.edit_form(FPCOMMAND, command.uuid)
    marker = _marker()
    fpr_state.update(command=command, marker=marker, original_command=fields["command"])
    _register_original_revision(fpr, restore, command, fields["command"])
    fpr.submit_edit(FPCOMMAND, command.uuid, _edited_fields(fields, marker))
    new = fpr.fp_command(description, enabled=True)
    assert new.uuid != command.uuid, "editing the command did not create a new revision"
    fpr_state["edited"] = new
    evidence.note(
        f"edited {description!r}: revision {command.uuid} replaced by {new.uuid}; marker {marker!r}"
    )


@then(parsers.parse('the edited version of the "{description}" command runs'))
def edited_command_runs(
    am: AMClient, evidence: Evidence, run: UnitRun, fpr_state: dict[str, Any], description: str
) -> None:
    tasks = job_tasks(am, evidence, run, PRESERVATION_JOB)
    assert tasks, f"the job {PRESERVATION_JOB!r} did not run"
    marker = str(fpr_state["marker"])
    printed = [task.file_name or task.uuid for task in tasks if marker in task.stdout]
    assert printed, f"no task of {PRESERVATION_JOB!r} printed the marker {marker!r}"
    evidence.note(f"the edited command printed its marker for: {', '.join(printed)}")


@then("the task output and the METS show that the updated command ran")
def updated_command_in_output_and_mets(
    am: AMClient, evidence: Evidence, run: UnitRun, fpr_state: dict[str, Any]
) -> None:
    marker = str(fpr_state["marker"])
    tasks = job_tasks(am, evidence, run, PRESERVATION_JOB)
    assert any(marker in task.stdout for task in tasks), f"no task output contains the marker {marker!r}"
    new_uuid = fpr_state["edited"].uuid
    events = [
        event
        for event in _mets(run).all_events()
        if event.type == "normalization" and new_uuid in event.detail
    ]
    assert events, f"no normalization event names the edited command {new_uuid}"
    evidence.note(f"{len(events)} normalization events name the edited command {new_uuid}")


# Reverted command -------------------------------------------------------------------


@when(parsers.parse('the user reverts the "{description}" command through its revision history'))
def user_reverts_command(
    ui: Page, fpr: FPR, evidence: Evidence, fpr_state: dict[str, Any], description: str
) -> None:
    edited: FPREntry = fpr_state["edited"]
    original: FPREntry = fpr_state["command"]
    ui.goto(f"/fpr/fpcommand/{edited.uuid}/")
    ui.get_by_role("link", name="Revision history").click()
    ui.wait_for_url(f"**/fpr/revisions/fpcommand/{edited.uuid}/")
    evidence.screenshot("revision history")
    fpr_state["revisions"] = fpr.revisions(FPCOMMAND, edited.uuid)
    # Each revision links to its "Replace" form, prefilled with that revision's content.
    ui.get_by_role("link", name=original.uuid).click()
    ui.wait_for_url(f"**/fpr/fpcommand/{original.uuid}/edit/")
    evidence.screenshot("replace with the previous revision")
    ui.select_option("select[name='tool']", label=original.tool)
    ui.get_by_role("button", name="Save").click()
    ui.wait_for_url("**/fpr/fpcommand/**")
    reverted = fpr.fp_command(description, enabled=True)
    assert reverted.uuid not in (edited.uuid, original.uuid), "saving did not create a new revision"
    content = fpr.edit_form(FPCOMMAND, reverted.uuid)["command"]
    assert content.strip() == str(fpr_state["original_command"]).strip(), (
        "the reverted revision differs from the original"
    )
    fpr_state["reverted"] = reverted
    evidence.note(
        f"reverted {description!r}: revision {edited.uuid} replaced by {reverted.uuid} with the original content"
    )


@then('the user can click on "Revision history"')
def revision_history_available(evidence: Evidence, fpr_state: dict[str, Any]) -> None:
    revisions: list[str] = fpr_state["revisions"]
    assert len(revisions) >= 2, f"the revision history lists {len(revisions)} revision(s)"
    evidence.note(f"revision history: {', '.join(revisions)}")


@then("the user can select the previous version to revert to")
def previous_version_selected(fpr_state: dict[str, Any]) -> None:
    assert fpr_state.get("reverted") is not None, "no revision was created from the previous version"


@then("the task output and the METS show that the reverted version of the command ran")
def reverted_command_ran(am: AMClient, evidence: Evidence, run: UnitRun, fpr_state: dict[str, Any]) -> None:
    marker = str(fpr_state["marker"])
    tasks = job_tasks(am, evidence, run, PRESERVATION_JOB)
    assert tasks, f"the job {PRESERVATION_JOB!r} did not run"
    printed = [task.file_name or task.uuid for task in tasks if marker in task.stdout]
    assert not printed, f"the edited command still printed its marker for: {printed}"
    reverted_uuid = fpr_state["reverted"].uuid
    events = [
        event
        for event in _mets(run).all_events()
        if event.type == "normalization" and reverted_uuid in event.detail
    ]
    assert events, f"no normalization event names the reverted command {reverted_uuid}"
    evidence.note(f"{len(events)} normalization events name the reverted command {reverted_uuid}")
