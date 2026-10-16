"""Checks on the structure of a stored AIP."""

from __future__ import annotations

from pathlib import Path

import bagit
import metsrw

from rt.assertions.mets import AIPMets

STANDARD_EVENT_TYPES = ("message digest calculation", "virus check", "format identification")
# Files that arrived in the transfer have an ingestion event; files extracted from a package an unpacking event.
ARRIVAL_EVENT_TYPES = ("ingestion", "unpacking")


def validate_bag(root: Path) -> list[str]:
    try:
        bagit.Bag(str(root)).validate()
    except bagit.BagError as err:
        return [f"bag validation failed: {err}"]
    return []


def check_layout(root: Path, sip_uuid: str) -> list[str]:
    problems: list[str] = []
    for required in ("bagit.txt", "data", "data/objects", "data/logs", f"data/METS.{sip_uuid}.xml"):
        if not (root / required).exists():
            problems.append(f"missing {required}")
    if not list(root.glob("manifest-*.txt")):
        problems.append("missing manifest-*.txt")
    return problems


def check_mets_parses(mets_path: Path) -> list[str]:
    try:
        document = metsrw.METSDocument.fromfile(str(mets_path))
    except Exception as err:  # noqa: BLE001 - the parser raises assorted exceptions
        return [f"metsrw cannot parse the METS: {err}"]
    if document.get_file(type="Directory", label="objects") is None:
        return ["the METS has no 'objects' directory entry"]
    return []


def check_original_objects(mets: AIPMets) -> list[str]:
    """Every original file has a PREMIS object with fixity and format, and the standard events."""
    problems: list[str] = []
    originals = mets.files("original")
    if not originals:
        problems.append("the METS lists no original files")
    for file in originals:
        objects = mets.objects_for(file)
        if not objects:
            problems.append(f"{file.href}: no PREMIS object")
            continue
        obj = objects[0]
        if obj.find(".//{http://www.loc.gov/premis/v3}messageDigest") is None:
            problems.append(f"{file.href}: no fixity in the PREMIS object")
        if obj.find(".//{http://www.loc.gov/premis/v3}formatName") is None:
            problems.append(f"{file.href}: no format in the PREMIS object")
        event_types = {event.type for event in mets.events_for(file)}
        if not event_types.intersection(ARRIVAL_EVENT_TYPES):
            problems.append(f"{file.href}: no 'ingestion' or 'unpacking' event")
        for expected in STANDARD_EVENT_TYPES:
            if expected not in event_types:
                problems.append(f"{file.href}: no {expected!r} event")
    return problems


def check_agents(mets: AIPMets) -> list[str]:
    types = {agent.type for agent in mets.all_agents()}
    missing = [agent_type for agent_type in ("software", "organization") if agent_type not in types]
    return [f"no PREMIS agent of type {agent_type!r}" for agent_type in missing]


def object_files(root: Path) -> list[Path]:
    """The files under ``data/objects`` that are not metadata or submission documentation."""
    objects = root / "data" / "objects"
    return [
        path
        for path in objects.rglob("*")
        if path.is_file() and "metadata" not in path.relative_to(objects).parts
    ]


def find_files(root: Path, name: str) -> list[Path]:
    return sorted(path for path in root.rglob(name) if path.is_file())
