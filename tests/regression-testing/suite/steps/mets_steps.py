"""Steps that check the contents of the AIP and its METS file against the sample transfer."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from lxml import etree
from pytest_bdd import parsers, then

from rt.assertions import aip as aip_checks
from rt.assertions.mets import NS, AIPMets, METSFile, PremisEvent
from rt.evidence import Evidence
from rt.pipeline.am_api import UnitRun
from rt.pipeline.container import Container
from rt.settings import Settings

TRANSFER_TYPES_WITH_DIRECTORIES = ("standard", "unzipped bag", "disk image", "dataverse")


def _mets(run: UnitRun) -> AIPMets:
    assert run.aip is not None, f"no AIP was fetched from the Storage Service; {run.describe()}"
    return AIPMets(run.aip.mets)


def _sample_path(settings: Settings, run: UnitRun, relative: str) -> str:
    return f"{settings.transfer_source_root}/{run.source_path}/{relative}"


def _sample_text(container: Container, settings: Settings, run: UnitRun, relative: str) -> str | None:
    """Read a file of the sample transfer, or return None when the sample does not have it."""
    if run.transfer_type not in TRANSFER_TYPES_WITH_DIRECTORIES:
        return None
    path = _sample_path(settings, run, relative)
    if not container.exists(path):
        return None
    return container.read_text(path)


def _csv_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    return [{(key or "").strip(): (value or "").strip() for key, value in row.items()} for row in reader]


# Descriptive and rights metadata -----------------------------------------------


@then(parsers.parse("the AIP METS contains descriptive metadata for each {kind} described in metadata.csv"))
def descriptive_metadata_for_each(
    run: UnitRun, container: Container, settings: Settings, evidence: Evidence, kind: str
) -> None:
    text = _sample_text(container, settings, run, "metadata/metadata.csv")
    if text is None:
        evidence.pending(f"the sample {run.source_path} has no metadata/metadata.csv to compare with")
        return
    mets = _mets(run)
    rows = _csv_rows(text)
    assert rows, "metadata.csv has no rows"
    problems: list[str] = []
    checked = 0
    for row in rows:
        path = row.get("filename") or row.get("parts") or ""
        if not path:
            continue
        checked += 1
        types = mets.dmd_types_for_path(path)
        if "DC" not in types:
            problems.append(f"{path}: dmdSec types {types or 'none'}")
    assert checked, "metadata.csv names no files or directories"
    evidence.note(f"{checked} {kind}(s) described in metadata.csv")
    assert not problems, f"{kind}s without Dublin Core descriptive metadata in the METS:\n- " + "\n- ".join(
        problems
    )


@then("the AIP METS contains rights metadata for each object described in rights.csv")
def rights_metadata_for_each_object(
    run: UnitRun, container: Container, settings: Settings, evidence: Evidence
) -> None:
    text = _sample_text(container, settings, run, "metadata/rights.csv")
    if text is None:
        evidence.pending(f"the sample {run.source_path} has no metadata/rights.csv to compare with")
        return
    mets = _mets(run)
    rows = _csv_rows(text)
    files = sorted({row.get("file", "") for row in rows if row.get("file")})
    assert files, "rights.csv names no files"
    problems: list[str] = []
    for path in files:
        file = mets.file_by_original_name(path)
        if file is None:
            problems.append(f"{path}: not found among the original files")
            continue
        count = mets.rights_statements_for(file)
        if count == 0:
            problems.append(f"{path}: no rightsMD")
    evidence.note(f"{len(files)} file(s) described in rights.csv")
    assert not problems, "files without rights metadata in the METS:\n- " + "\n- ".join(problems)


@then('submission documentation is listed in the METS with fileGrp USE="submissionDocumentation"')
def submission_documentation_is_listed(run: UnitRun, evidence: Evidence) -> None:
    mets = _mets(run)
    files = mets.files("submissionDocumentation")
    assert files, (
        f'no fileGrp USE="submissionDocumentation" entries; fileGrp uses: {sorted(mets.filegrp_uses())}'
    )
    evidence.note(f"{len(files)} submission documentation file(s): {[file.href for file in files]}")


# identifiers.json ---------------------------------------------------------------


@then("the identifiers from identifiers.json are recorded as objectIdentifiers in the METS")
def identifiers_are_recorded(
    run: UnitRun, container: Container, settings: Settings, evidence: Evidence
) -> None:
    import json

    text = _sample_text(container, settings, run, "metadata/identifiers.json")
    if text is None:
        evidence.pending(f"the sample {run.source_path} has no metadata/identifiers.json to compare with")
        return
    mets = _mets(run)
    entries = json.loads(text)
    problems: list[str] = []
    checked = 0
    for entry in entries:
        path = str(entry.get("file", ""))
        expected = [
            (str(ident["identifierType"]), str(ident["identifier"])) for ident in entry.get("identifiers", [])
        ]
        if not expected:
            continue
        checked += len(expected)
        label = "the SIP" if path == "" else path
        found = set(mets._identifiers_of(mets.objects_for_path(path)))
        if path == "" and not found:
            found = set(mets.all_object_identifiers())
        for identifier in expected:
            if identifier not in found:
                problems.append(f"{label}: {identifier[0]} {identifier[1]} not recorded")
    assert checked, "identifiers.json declares no identifiers"
    evidence.note(f"{checked} identifier(s) declared in identifiers.json")
    assert not problems, "identifiers missing from the METS:\n- " + "\n- ".join(problems)


# premis.xml ---------------------------------------------------------------------


@dataclass(frozen=True)
class SampleEvent:
    identifier_type: str
    identifier_value: str
    type: str
    datetime: str
    detail: str
    outcome: str
    outcome_detail_note: str
    agents: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SamplePremis:
    objects: dict[str, tuple[str, ...]]  # original name -> linked event identifier values
    events: dict[str, SampleEvent]  # identifier value -> event
    agents: dict[tuple[str, str], tuple[str, str]]  # (type, value) -> (name, agent type)


def _text(element: etree._Element, path: str) -> str:
    found = element.find(path, namespaces=NS)
    return (found.text or "").strip() if found is not None else ""


def parse_sample_premis(xml: str) -> SamplePremis:
    root = etree.fromstring(xml.encode("utf-8"))
    objects: dict[str, tuple[str, ...]] = {}
    for obj in root.iterfind("premis:object", namespaces=NS):
        name = _text(obj, "premis:originalName")
        links = tuple(
            _text(link, "premis:linkingEventIdentifierValue")
            for link in obj.iterfind("premis:linkingEventIdentifier", namespaces=NS)
        )
        objects[name] = links
    events: dict[str, SampleEvent] = {}
    for element in root.iterfind("premis:event", namespaces=NS):
        event = SampleEvent(
            identifier_type=_text(element, "premis:eventIdentifier/premis:eventIdentifierType"),
            identifier_value=_text(element, "premis:eventIdentifier/premis:eventIdentifierValue"),
            type=_text(element, "premis:eventType"),
            datetime=_text(element, "premis:eventDateTime"),
            detail=_text(element, "premis:eventDetailInformation/premis:eventDetail"),
            outcome=_text(element, "premis:eventOutcomeInformation/premis:eventOutcome"),
            outcome_detail_note=_text(
                element,
                "premis:eventOutcomeInformation/premis:eventOutcomeDetail/premis:eventOutcomeDetailNote",
            ),
            agents=tuple(
                (
                    _text(link, "premis:linkingAgentIdentifierType"),
                    _text(link, "premis:linkingAgentIdentifierValue"),
                )
                for link in element.iterfind("premis:linkingAgentIdentifier", namespaces=NS)
            ),
        )
        events[event.identifier_value] = event
    agents: dict[tuple[str, str], tuple[str, str]] = {}
    for element in root.iterfind("premis:agent", namespaces=NS):
        key = (
            _text(element, "premis:agentIdentifier/premis:agentIdentifierType"),
            _text(element, "premis:agentIdentifier/premis:agentIdentifierValue"),
        )
        agents[key] = (_text(element, "premis:agentName"), _text(element, "premis:agentType"))
    return SamplePremis(objects=objects, events=events, agents=agents)


def _same_instant(first: str, second: str) -> bool:
    """Compare two PREMIS datetimes to the second, ignoring formatting differences."""
    try:
        parsed_first = datetime.fromisoformat(first).replace(microsecond=0)
        parsed_second = datetime.fromisoformat(second).replace(microsecond=0)
    except ValueError:
        return first[:19] == second[:19]
    if (parsed_first.tzinfo is None) != (parsed_second.tzinfo is None):
        return parsed_first.replace(tzinfo=None) == parsed_second.replace(tzinfo=None)
    return parsed_first == parsed_second


def _match_event(candidates: list[PremisEvent], sample: SampleEvent) -> PremisEvent | None:
    """The pipeline replaces event identifiers that are not UUIDs, so match by type and time."""
    for event in candidates:
        if event.identifier_value and event.identifier_value == sample.identifier_value:
            return event
    for event in candidates:
        if event.type == sample.type and _same_instant(event.datetime, sample.datetime):
            return event
    return None


def _imported_events(
    run: UnitRun, container: Container, settings: Settings, evidence: Evidence
) -> list[tuple[str, METSFile, SampleEvent, PremisEvent | None]]:
    """Pair every event of the sample premis.xml that applies to an ingested file with its METS counterpart."""
    text = _sample_text(container, settings, run, "metadata/premis.xml")
    assert text is not None, f"the sample {run.source_path} has no metadata/premis.xml"
    sample = parse_sample_premis(text)
    mets = _mets(run)
    pairs: list[tuple[str, METSFile, SampleEvent, PremisEvent | None]] = []
    for original_name, event_ids in sample.objects.items():
        file = mets.file_by_original_name(original_name)
        if file is None:
            evidence.note(f"premis.xml describes {original_name}, which is not part of the transfer")
            continue
        candidates = mets.events_for(file)
        for event_id in event_ids:
            sample_event = sample.events.get(event_id)
            if sample_event is None:
                continue
            pairs.append((original_name, file, sample_event, _match_event(candidates, sample_event)))
    assert pairs, "premis.xml has no events for files that are part of the transfer"
    return pairs


@then("the events and agents from premis.xml are added to the AIP METS")
def premis_events_and_agents_are_added(
    run: UnitRun, container: Container, settings: Settings, evidence: Evidence
) -> None:
    pairs = _imported_events(run, container, settings, evidence)
    missing = [
        f"{name}: {sample.type} {sample.identifier_value}"
        for name, _, sample, found in pairs
        if found is None
    ]
    evidence.note(f"{len(pairs)} event(s) from premis.xml apply to ingested files")
    assert not missing, "events from premis.xml missing in the METS:\n- " + "\n- ".join(missing)
    mets = _mets(run)
    text = _sample_text(container, settings, run, "metadata/premis.xml")
    assert text is not None
    sample = parse_sample_premis(text)
    mets_agents = {(agent.identifier_type, agent.identifier_value) for agent in mets.all_agents()}
    missing_agents = [f"{key[0]} {key[1]}" for key in sample.agents if key not in mets_agents]
    assert not missing_agents, "agents from premis.xml missing in the METS:\n- " + "\n- ".join(missing_agents)


@then("the imported events retain their original field values, including the event details")
def premis_events_retain_values(
    run: UnitRun, container: Container, settings: Settings, evidence: Evidence
) -> None:
    pairs = _imported_events(run, container, settings, evidence)
    problems: list[str] = []
    for name, _, sample, found in pairs:
        if found is None:
            problems.append(f"{name}: {sample.type} {sample.identifier_value} missing")
            continue
        if not _same_instant(found.datetime, sample.datetime):
            problems.append(
                f"{name}: {sample.identifier_value} eventDateTime is {found.datetime!r}, expected {sample.datetime!r}"
            )
        for field_name, expected, actual in (
            ("eventType", sample.type, found.type),
            ("eventDetail", sample.detail, found.detail),
            ("eventOutcome", sample.outcome, found.outcome),
            ("eventOutcomeDetailNote", sample.outcome_detail_note, found.outcome_detail_note),
        ):
            if expected != actual:
                problems.append(
                    f"{name}: {sample.identifier_value} {field_name} is {actual!r}, expected {expected!r}"
                )
    assert not problems, "imported events differ from premis.xml:\n- " + "\n- ".join(problems)


@then("the imported events are linked to the same agents as in premis.xml")
def premis_events_keep_agents(
    run: UnitRun, container: Container, settings: Settings, evidence: Evidence
) -> None:
    pairs = _imported_events(run, container, settings, evidence)
    problems: list[str] = []
    for name, _, sample, found in pairs:
        if found is None:
            problems.append(f"{name}: {sample.type} {sample.identifier_value} missing")
            continue
        for agent in sample.agents:
            if agent not in found.linking_agents:
                problems.append(
                    f"{name}: {sample.identifier_value} is not linked to agent {agent[0]} {agent[1]}"
                )
    assert not problems, "imported events lost agent links:\n- " + "\n- ".join(problems)


# Filename changes and accession numbers -----------------------------------------


@then("the AIP contains a filename change log")
def aip_contains_filename_change_log(run: UnitRun, evidence: Evidence) -> None:
    assert run.aip is not None, f"no AIP was fetched; {run.describe()}"
    if run.aip.root is None:
        evidence.pending("the AIP was not downloaded (larger than the size cap)")
        return
    logs = aip_checks.find_files(run.aip.root / "data" / "logs", "filenameChanges.log")
    assert logs, "no filenameChanges.log under data/logs"
    evidence.note("filename change logs: " + ", ".join(str(log.relative_to(run.aip.root)) for log in logs))


@then("a filename change PREMIS event is present in the METS")
def filename_change_event_is_present(run: UnitRun, evidence: Evidence) -> None:
    mets = _mets(run)
    events = [event for event in mets.all_events() if event.type == "filename change"]
    assert events, "no 'filename change' event in the METS"
    evidence.note(f"{len(events)} filename change event(s)")


@then("the accession number is recorded in the METS as a registration event outcome detail note")
def accession_number_is_recorded(run: UnitRun, evidence: Evidence, item_accession: str) -> None:
    mets = _mets(run)
    originals = mets.files("original")
    assert originals, "the METS lists no original files"
    problems: list[str] = []
    for file in originals:
        events = [event for event in mets.events_for(file) if event.type == "registration"]
        notes = {event.outcome_detail_note for event in events}
        if f"accession#{item_accession}" not in notes:
            problems.append(f"{file.href}: registration notes {sorted(notes) or 'none'}")
    assert not problems, (
        f"files without a registration event noting accession#{item_accession}:\n- " + "\n- ".join(problems)
    )


# Bags ------------------------------------------------------------------------------


def parse_bag_info(text: str) -> dict[str, str]:
    """Parse bag-info.txt, joining the indented continuation lines of a value."""
    fields: dict[str, str] = {}
    key: str | None = None
    for line in text.splitlines():
        if line[:1].isspace() and key is not None:
            fields[key] = f"{fields[key]} {line.strip()}"
        elif ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            fields[key] = value.strip()
    return {key: " ".join(value.split()) for key, value in fields.items()}


@then("the contents of bag-info.txt are parsed into the METS")
def bag_info_is_parsed(run: UnitRun, container: Container, settings: Settings, evidence: Evidence) -> None:
    mets = _mets(run)
    recorded = {key: " ".join(value.split()) for key, value in mets.bagit_metadata().items()}
    assert recorded, (
        'the amdSec of the objects directory has no BagIt source metadata (sourceMD with OTHERMDTYPE="BagIt")'
    )
    evidence.note(f"BagIt metadata in the amdSec of the objects directory: {recorded}")
    source = f"{settings.transfer_source_root}/{run.source_path}"
    if run.transfer_type == "zipped bag":
        top = source.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        text = container.read_zip_member(source, f"{top}/bag-info.txt").decode("utf-8")
    elif container.exists(f"{source}/bag-info.txt"):
        text = container.read_text(f"{source}/bag-info.txt")
    else:
        text = ""
    expected = parse_bag_info(text)
    if not expected:
        evidence.pending(
            "bag-info.txt could not be read from the sample; only checked that BagIt metadata exists"
        )
        return
    problems = [
        f"{key}: METS has {recorded.get(key)!r}, bag-info.txt has {value!r}"
        for key, value in expected.items()
        if recorded.get(key) != value
    ]
    assert not problems, "bag-info.txt fields differ in the METS:\n- " + "\n- ".join(problems)
