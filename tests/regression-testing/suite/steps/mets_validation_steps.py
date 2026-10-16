"""Steps that validate the AIP METS against its schemas and against the Archivematica rules of metsrw."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pytest_bdd import then, when

from rt.assertions.validation import (
    PREMIS_NAMESPACE,
    RuleFailure,
    RulesReport,
    SchemaReport,
    check_archivematica_rules,
    dangling_dmdids,
    validate_against_schemas,
)
from rt.evidence import Evidence
from rt.pipeline.am_api import UnitRun

# Rules of metsrw's schematron that no longer match the METS Archivematica writes,
# by the start of their message.
EVENT_TYPE_RULE = "A PREMIS event MUST be of a recognized eventType."
DMDID_RULE = "If a div has a DMDID attribute, then it must refer to the ID of a dmdSec."
_EVENT_TYPE = re.compile(r"\((?P<type>.+?) is not in ")


def _aip_mets(run: UnitRun) -> Path:
    assert run.aip is not None, f"no AIP was fetched from the Storage Service: {run.describe()}"
    return run.aip.mets


@when("the AIP METS is validated against the METS schema and the schemas it references")
def validate_aip_mets(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    report = validate_against_schemas(_aip_mets(run))
    evidence.attach("schema-validation", evidence.write_text("mets-validation/schemas.txt", report.as_text()))
    state["schema_report"] = report
    evidence.note(
        f"validated against the schemas of {', '.join(report.validated)}"
        + (f"; no local schema for {', '.join(report.unavailable)}" if report.unavailable else "")
    )


@then("no errors are reported")
def no_schema_errors(state: dict[str, Any]) -> None:
    report: SchemaReport = state["schema_report"]
    assert not report.errors, f"{len(report.errors)} schema errors:\n- " + "\n- ".join(report.errors[:20])


@then("the validation is successful")
def schema_validation_successful(evidence: Evidence, state: dict[str, Any]) -> None:
    report: SchemaReport = state["schema_report"]
    assert report.valid, "the METS is not valid against its schemas"
    assert PREMIS_NAMESPACE in report.validated, (
        "the PREMIS sections were not checked against the PREMIS 3 schema"
    )
    evidence.note(f"the METS is valid against the schemas of {len(report.validated)} namespaces")


@when("the AIP METS is checked against the Archivematica rules of metsrw")
def check_aip_mets_rules(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    report = check_archivematica_rules(_aip_mets(run))
    evidence.attach(
        "schematron-report", evidence.write_text("mets-validation/schematron.svrl.xml", report.svrl)
    )
    state["rules_report"] = report


def _outdated(failure: RuleFailure, mets: Path) -> bool:
    """Whether a failure comes from a rule of the schematron that predates the METS Archivematica writes."""
    if failure.text.startswith(EVENT_TYPE_RULE):
        # The rule lists the event types of its time; a typed event outside the list is not a defect.
        match = _EVENT_TYPE.search(failure.text)
        return match is not None and bool(match.group("type").strip())
    if failure.text.startswith(DMDID_RULE):
        # The rule takes a DMDID listing several dmdSecs as one ID; the references are checked here instead.
        return not dangling_dmdids(mets)
    return False


@then("the expected METS and PREMIS sections are present and they match expected values")
def archivematica_rules_hold(evidence: Evidence, run: UnitRun, state: dict[str, Any]) -> None:
    report: RulesReport = state["rules_report"]
    mets = _aip_mets(run)
    outdated = [failure for failure in report.failures if _outdated(failure, mets)]
    failures = [failure for failure in report.failures if failure not in outdated]
    by_rule: dict[str, list[str]] = {}
    for failure in outdated:
        rule = EVENT_TYPE_RULE if failure.text.startswith(EVENT_TYPE_RULE) else DMDID_RULE
        detail = failure.text[len(rule) :].strip()
        by_rule.setdefault(rule, []).append(detail)
    for rule, details in by_rule.items():
        examples = sorted(set(details))[:5]
        evidence.warn(
            f"metsrw's Archivematica schematron rule {rule!r} is out of date; it failed {len(details)} time(s): "
            + "; ".join(examples)
        )
    assert not failures, (
        f"{len(failures)} failed assertions of the Archivematica schematron:\n- "
        + "\n- ".join(f"{failure.text} (at {failure.location})" for failure in failures[:20])
    )
    evidence.note(
        f"the METS meets the {report.assertions} assertions of metsrw's Archivematica schematron"
        + (f", apart from {len(outdated)} hits of out-of-date rules" if outdated else "")
    )
