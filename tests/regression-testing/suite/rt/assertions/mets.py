"""Read-only access to an AIP METS file for assertions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

NS = {
    "mets": "http://www.loc.gov/METS/",
    "premis": "http://www.loc.gov/premis/v3",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "xlink": "http://www.w3.org/1999/xlink",
}

TRANSFER_DIRECTORY_PREFIX = "%transferDirectory%"


@dataclass(frozen=True)
class METSFile:
    id: str
    use: str
    href: str
    admids: tuple[str, ...]
    group_id: str | None


@dataclass(frozen=True)
class PremisEvent:
    type: str
    datetime: str
    detail: str
    outcome: str
    outcome_detail_note: str
    identifier_type: str
    identifier_value: str
    linking_agents: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PremisAgent:
    identifier_type: str
    identifier_value: str
    name: str
    type: str


def _text(element: etree._Element | None, path: str) -> str:
    if element is None:
        return ""
    found = element.find(path, namespaces=NS)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


class AIPMets:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.tree = etree.parse(str(path))
        self.root = self.tree.getroot()

    # Files ---------------------------------------------------------------

    def files(self, use: str | None = None) -> list[METSFile]:
        result: list[METSFile] = []
        for group in self.root.iterfind("mets:fileSec/mets:fileGrp", namespaces=NS):
            group_use = group.get("USE", "")
            if use is not None and group_use != use:
                continue
            for element in group.iterfind("mets:file", namespaces=NS):
                flocat = element.find("mets:FLocat", namespaces=NS)
                href = flocat.get(f"{{{NS['xlink']}}}href", "") if flocat is not None else ""
                result.append(
                    METSFile(
                        id=element.get("ID", ""),
                        use=group_use,
                        href=href,
                        admids=tuple((element.get("ADMID") or "").split()),
                        group_id=element.get("GROUPID"),
                    )
                )
        return result

    def filegrp_uses(self) -> set[str]:
        return {
            group.get("USE", "") for group in self.root.iterfind("mets:fileSec/mets:fileGrp", namespaces=NS)
        }

    def amdsec(self, admid: str) -> etree._Element | None:
        for section in self.root.iterfind("mets:amdSec", namespaces=NS):
            if section.get("ID") == admid:
                return section
        return None

    def amdsecs_for(self, admids: tuple[str, ...]) -> list[etree._Element]:
        sections: list[etree._Element] = []
        for admid in admids:
            section = self.amdsec(admid)
            if section is not None:
                sections.append(section)
        return sections

    def file_by_original_name(self, original_name: str, use: str = "original") -> METSFile | None:
        """Find a file by the original path recorded in its PREMIS object, e.g. ``objects/bird.mp3``."""
        wanted = original_name.strip().strip("/")
        for file in self.files(use):
            for obj in self.objects_for(file):
                if self._original_name(obj) == wanted:
                    return file
        return None

    @staticmethod
    def file_uuid(file: METSFile) -> str:
        """The UUID of a file, which the METS uses as its ID with a ``file-`` prefix."""
        return file.id.removeprefix("file-")

    def file_by_uuid(self, uuid: str) -> METSFile | None:
        for file in self.files():
            if self.file_uuid(file) == uuid:
                return file
        return None

    def derivation_source(self, file: METSFile) -> str | None:
        """The UUID of the object a derivative was made from, from the relationship of its PREMIS object."""
        for obj in self.objects_for(file):
            for relationship in obj.iterfind("premis:relationship", namespaces=NS):
                if (
                    _text(relationship, "premis:relationshipType") == "derivation"
                    and _text(relationship, "premis:relationshipSubType") == "has source"
                ):
                    return _text(
                        relationship, "premis:relatedObjectIdentifier/premis:relatedObjectIdentifierValue"
                    )
        return None

    def format_designation(self, file: METSFile) -> dict[str, str]:
        """The format name, version and registry key of the PREMIS object of a file."""
        for obj in self.objects_for(file):
            fmt = obj.find("premis:objectCharacteristics/premis:format", namespaces=NS)
            if fmt is not None:
                return {
                    "name": _text(fmt, "premis:formatDesignation/premis:formatName"),
                    "version": _text(fmt, "premis:formatDesignation/premis:formatVersion"),
                    "registry_key": _text(fmt, "premis:formatRegistry/premis:formatRegistryKey"),
                }
        return {"name": "", "version": "", "registry_key": ""}

    def characteristics_extensions(self, file: METSFile) -> list[str]:
        """The serialized objectCharacteristicsExtension elements of a file, one per tool that ran."""
        extensions: list[str] = []
        for obj in self.objects_for(file):
            for extension in obj.iterfind(
                "premis:objectCharacteristics/premis:objectCharacteristicsExtension", namespaces=NS
            ):
                extensions.append(etree.tostring(extension, encoding="unicode"))
        return extensions

    def events_of_type(self, file: METSFile, event_type: str) -> list[PremisEvent]:
        return [event for event in self.events_for(file) if event.type == event_type]

    def file_by_href(self, href: str) -> METSFile | None:
        for file in self.files():
            if file.href == href:
                return file
        return None

    # PREMIS ---------------------------------------------------------------

    def objects_for(self, file: METSFile) -> list[etree._Element]:
        return self._objects_in(self.amdsecs_for(file.admids))

    def _objects_in(self, sections: list[etree._Element]) -> list[etree._Element]:
        objects: list[etree._Element] = []
        for section in sections:
            objects.extend(
                section.iterfind("mets:techMD/mets:mdWrap/mets:xmlData/premis:object", namespaces=NS)
            )
        return objects

    def _dmd_objects(self, dmdids: tuple[str, ...]) -> list[etree._Element]:
        """PREMIS objects of directories and of the SIP, which the METS wraps in dmdSec elements."""
        objects: list[etree._Element] = []
        for dmdid in dmdids:
            section = self.dmdsec(dmdid)
            if section is None:
                continue
            for wrap in section.iterfind("mets:mdWrap", namespaces=NS):
                if wrap.get("MDTYPE") == "PREMIS:OBJECT":
                    objects.extend(wrap.iterfind("mets:xmlData/premis:object", namespaces=NS))
        return objects

    @staticmethod
    def _original_name(obj: etree._Element) -> str:
        name = _text(obj, "premis:originalName")
        if name.startswith(TRANSFER_DIRECTORY_PREFIX):
            name = name[len(TRANSFER_DIRECTORY_PREFIX) :]
        return name.strip("/")

    def object_identifiers_for(self, file: METSFile) -> list[tuple[str, str]]:
        return self._identifiers_of(self.objects_for(file))

    @staticmethod
    def _identifiers_of(objects: list[etree._Element]) -> list[tuple[str, str]]:
        identifiers: list[tuple[str, str]] = []
        for obj in objects:
            for identifier in obj.iterfind("premis:objectIdentifier", namespaces=NS):
                identifiers.append(
                    (
                        _text(identifier, "premis:objectIdentifierType"),
                        _text(identifier, "premis:objectIdentifierValue"),
                    )
                )
        return identifiers

    def all_object_identifiers(self) -> list[tuple[str, str]]:
        objects = list(
            self.root.iterfind(".//mets:techMD/mets:mdWrap/mets:xmlData/premis:object", namespaces=NS)
        )
        return self._identifiers_of(objects)

    @staticmethod
    def _parse_event(element: etree._Element) -> PremisEvent:
        agents = tuple(
            (
                _text(link, "premis:linkingAgentIdentifierType"),
                _text(link, "premis:linkingAgentIdentifierValue"),
            )
            for link in element.iterfind("premis:linkingAgentIdentifier", namespaces=NS)
        )
        return PremisEvent(
            type=_text(element, "premis:eventType"),
            datetime=_text(element, "premis:eventDateTime"),
            detail=_text(element, "premis:eventDetailInformation/premis:eventDetail"),
            outcome=_text(element, "premis:eventOutcomeInformation/premis:eventOutcome"),
            outcome_detail_note=_text(
                element,
                "premis:eventOutcomeInformation/premis:eventOutcomeDetail/premis:eventOutcomeDetailNote",
            ),
            identifier_type=_text(element, "premis:eventIdentifier/premis:eventIdentifierType"),
            identifier_value=_text(element, "premis:eventIdentifier/premis:eventIdentifierValue"),
            linking_agents=agents,
        )

    def events_for(self, file: METSFile) -> list[PremisEvent]:
        events: list[PremisEvent] = []
        for section in self.amdsecs_for(file.admids):
            for element in section.iterfind(
                "mets:digiprovMD/mets:mdWrap/mets:xmlData/premis:event", namespaces=NS
            ):
                events.append(self._parse_event(element))
        return events

    def all_events(self) -> list[PremisEvent]:
        return [
            self._parse_event(element)
            for element in self.root.iterfind(
                ".//mets:digiprovMD/mets:mdWrap/mets:xmlData/premis:event", namespaces=NS
            )
        ]

    @staticmethod
    def _parse_agent(element: etree._Element) -> PremisAgent:
        return PremisAgent(
            identifier_type=_text(element, "premis:agentIdentifier/premis:agentIdentifierType"),
            identifier_value=_text(element, "premis:agentIdentifier/premis:agentIdentifierValue"),
            name=_text(element, "premis:agentName"),
            type=_text(element, "premis:agentType"),
        )

    def agents_for(self, file: METSFile) -> list[PremisAgent]:
        agents: list[PremisAgent] = []
        for section in self.amdsecs_for(file.admids):
            for element in section.iterfind(
                "mets:digiprovMD/mets:mdWrap/mets:xmlData/premis:agent", namespaces=NS
            ):
                agents.append(self._parse_agent(element))
        return agents

    def all_agents(self) -> list[PremisAgent]:
        return [
            self._parse_agent(element)
            for element in self.root.iterfind(
                ".//mets:digiprovMD/mets:mdWrap/mets:xmlData/premis:agent", namespaces=NS
            )
        ]

    def rights_statements_for(self, file: METSFile) -> int:
        count = 0
        for section in self.amdsecs_for(file.admids):
            count += len(section.findall("mets:rightsMD", namespaces=NS))
        return count

    # Structural map and descriptive metadata ----------------------------------

    def physical_root(self) -> etree._Element | None:
        for struct_map in self.root.iterfind("mets:structMap", namespaces=NS):
            if struct_map.get("TYPE") == "physical":
                return struct_map.find("mets:div", namespaces=NS)
        return None

    def div_for_path(self, path: str) -> etree._Element | None:
        """The ``mets:div`` of a path relative to the SIP, e.g. ``objects/minutes``."""
        current = self.physical_root()
        if current is None:
            return None
        for part in [part for part in path.strip("/").split("/") if part]:
            next_div = None
            for child in current.iterfind("mets:div", namespaces=NS):
                if child.get("LABEL") == part:
                    next_div = child
                    break
            if next_div is None:
                return None
            current = next_div
        return current

    def _physical_divs(self) -> list[etree._Element]:
        for struct_map in self.root.iterfind("mets:structMap", namespaces=NS):
            if struct_map.get("TYPE") == "physical":
                return list(struct_map.iterfind(".//mets:div", namespaces=NS))
        return []

    def div_for_original(self, original: str) -> etree._Element | None:
        """The ``mets:div`` of a path as it was in the transfer, before the pipeline renamed anything.

        Files are found through the original name of their PREMIS object, directories
        through the PREMIS object in their dmdSec, and the remaining paths by label.
        """
        wanted = original.strip("/")
        if not wanted:
            return self.physical_root()
        file = self.file_by_original_name(wanted)
        if file is not None:
            for div in self._physical_divs():
                fptr = div.find("mets:fptr", namespaces=NS)
                if fptr is not None and fptr.get("FILEID") == file.id:
                    return div
        for div in self._physical_divs():
            if div.get("TYPE") != "Directory":
                continue
            for obj in self._dmd_objects(tuple((div.get("DMDID") or "").split())):
                if self._original_name(obj) == wanted:
                    return div
        return self.div_for_path(wanted)

    def dmdsec(self, dmdid: str) -> etree._Element | None:
        for section in self.root.iterfind("mets:dmdSec", namespaces=NS):
            if section.get("ID") == dmdid:
                return section
        return None

    def dmd_types_for_path(self, path: str) -> list[str]:
        """The MDTYPE values of the dmdSec elements linked from the div of a transfer path."""
        div = self.div_for_original(path)
        if div is None:
            return []
        types: list[str] = []
        for dmdid in (div.get("DMDID") or "").split():
            section = self.dmdsec(dmdid)
            if section is None:
                continue
            wrap = section.find("mets:mdWrap", namespaces=NS)
            ref = section.find("mets:mdRef", namespaces=NS)
            element = wrap if wrap is not None else ref
            if element is not None:
                types.append(element.get("MDTYPE", ""))
        return types

    def objects_for_path(self, path: str) -> list[etree._Element]:
        """The PREMIS objects of a transfer path: a file, a directory or the SIP itself (empty path)."""
        div = self.div_for_original(path)
        if div is None:
            return []
        admids = tuple((div.get("ADMID") or "").split())
        objects = self._objects_in(self.amdsecs_for(admids))
        objects += self._dmd_objects(tuple((div.get("DMDID") or "").split()))
        if objects:
            return objects
        file_id = ""
        fptr = div.find("mets:fptr", namespaces=NS)
        if fptr is not None:
            file_id = fptr.get("FILEID", "")
        for file in self.files():
            if file.id == file_id:
                return self.objects_for(file)
        return []

    def bagit_metadata(self) -> dict[str, str]:
        """The bag-info.txt fields recorded as BagIt source metadata of the objects directory.

        The pipeline writes them in the amdSec of the AIP-level objects directory, as
        a sourceMD whose mdWrap has ``OTHERMDTYPE="BagIt"``.
        """
        metadata: dict[str, str] = {}
        objects = self.div_for_path("objects")
        if objects is None:
            return metadata
        for section in self.amdsecs_for(tuple((objects.get("ADMID") or "").split())):
            for wrap in section.iterfind("mets:sourceMD/mets:mdWrap", namespaces=NS):
                if wrap.get("OTHERMDTYPE") != "BagIt":
                    continue
                for element in wrap.iterfind("mets:xmlData/transfer_metadata/*", namespaces=NS):
                    tag = etree.QName(element).localname
                    metadata[tag] = (element.text or "").strip()
        return metadata
