"""Validation of an AIP METS file against its schemas and the Archivematica rules that metsrw ships.

The schemas come from local copies, so validation needs no network access;
libxml2 2.14, which lxml 6 bundles, cannot fetch schemas over HTTP anyway.
``rt/schemas`` holds PREMIS 3, xlink and xml.xsd as Archivematica bundles them
and the Dublin Core schemas of 2008-02-11; the METS schema is the one metsrw
bundles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import metsrw
from lxml import etree

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
METS_NAMESPACE = "http://www.loc.gov/METS/"
PREMIS_NAMESPACE = "http://www.loc.gov/premis/v3"
DCTERMS_NAMESPACE = "http://purl.org/dc/terms/"
XSD = "{http://www.w3.org/2001/XMLSchema}"
SCHEMA_LOCATION = "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation"
SVRL = {"svrl": "http://purl.oclc.org/dsdl/svrl"}
SCHEMATRON = {"sch": "http://purl.oclc.org/dsdl/schematron"}

_METSRW_DIR = Path(str(metsrw.__file__)).resolve().parent
METS_XSD = _METSRW_DIR / str(metsrw.METS_XSD_PATH)
ARCHIVEMATICA_SCHEMATRON = _METSRW_DIR / str(metsrw.AM_SCT_PATH)

# The schemas a METS file can reference, by the locations Archivematica writes.
LOCAL_SCHEMAS: dict[str, Path] = {
    "http://www.loc.gov/standards/premis/v3/premis.xsd": SCHEMA_DIR / "premis.xsd",
    "https://www.loc.gov/standards/premis/v3/premis.xsd": SCHEMA_DIR / "premis.xsd",
    "http://dublincore.org/schemas/xmls/qdc/2008/02/11/dcterms.xsd": SCHEMA_DIR / "dcterms.xsd",
    "https://dublincore.org/schemas/xmls/qdc/2008/02/11/dcterms.xsd": SCHEMA_DIR / "dcterms.xsd",
}
# Namespaces that the schemas themselves import from remote locations. Importing
# them first from the local copies makes libxml2 skip the remote imports.
SCHEMA_DEPENDENCIES: dict[str, Path] = {
    "http://www.w3.org/1999/xlink": SCHEMA_DIR / "xlink.xsd",
    "http://www.w3.org/XML/1998/namespace": SCHEMA_DIR / "xml.xsd",
}
# A line of a libxml2 error log: file:line:column:LEVEL:DOMAIN:TYPE: message
_LOG_LINE = re.compile(r"^.*?:(?P<line>\d+):\d+:(?P<level>[A-Z]+):[A-Z0-9_]+:[A-Z0-9_]+: (?P<message>.*)$")


@dataclass
class SchemaReport:
    valid: bool
    errors: list[str]
    # Namespaces checked against a local schema, and those without one, with the location the METS gives.
    validated: list[str]
    unavailable: dict[str, str]

    def as_text(self) -> str:
        lines = [f"valid: {self.valid}", "validated against local schemas:"]
        lines += [f"  {namespace}" for namespace in self.validated]
        lines.append("no local schema, not validated:")
        lines += [f"  {namespace} ({location})" for namespace, location in self.unavailable.items()]
        lines.append(f"errors: {len(self.errors)}")
        lines += [f"  {error}" for error in self.errors]
        return "\n".join(lines) + "\n"


def validate_against_schemas(mets: Path) -> SchemaReport:
    """Validate a METS file against the METS schema and the schemas its xsi:schemaLocation attributes name."""
    document = etree.parse(str(mets))
    imports: dict[str, Path] = dict(SCHEMA_DEPENDENCIES)
    validated: list[str] = []
    unavailable: dict[str, str] = {}
    errors: list[str] = []
    for element in document.getroot().iter("*"):
        value = element.get(SCHEMA_LOCATION)
        if not value:
            continue
        parts = value.split()
        if len(parts) % 2:
            errors.append(
                f"line {element.sourceline}: xsi:schemaLocation {value!r} does not pair each namespace with a location"
            )
            continue
        for namespace, location in zip(parts[0::2], parts[1::2], strict=True):
            if namespace == METS_NAMESPACE:
                continue
            local = LOCAL_SCHEMAS.get(location)
            if local is None:
                unavailable.setdefault(namespace, location)
            elif namespace not in imports:
                imports[namespace] = local
                validated.append(namespace)
    schema_document = etree.parse(str(METS_XSD))
    root = schema_document.getroot()
    for position, (namespace, path) in enumerate(imports.items()):
        root.insert(position, etree.Element(f"{XSD}import", namespace=namespace, schemaLocation=str(path)))
    schema = etree.XMLSchema(schema_document)
    schema_valid = schema.validate(document)
    for line in str(schema.error_log).splitlines():
        match = _LOG_LINE.match(line)
        if match is not None and match.group("level") in ("ERROR", "FATAL"):
            errors.append(f"line {match.group('line')}: {match.group('message')}")
    return SchemaReport(
        valid=schema_valid and not errors,
        errors=errors,
        validated=[METS_NAMESPACE, *validated],
        unavailable=unavailable,
    )


@dataclass(frozen=True)
class RuleFailure:
    """A failed assertion of a schematron, as its SVRL report describes it."""

    text: str
    test: str
    location: str


@dataclass
class RulesReport:
    assertions: int
    failures: list[RuleFailure]
    svrl: str


def check_archivematica_rules(mets: Path) -> RulesReport:
    """Check a METS file against the Archivematica METS schematron that metsrw ships."""
    document = etree.parse(str(mets))
    _, report = metsrw.schematron_validate(document, schematron=metsrw.AM_SCT_PATH)
    failures = [
        RuleFailure(
            text=" ".join(str(node.findtext("svrl:text", default="", namespaces=SVRL)).split()),
            test=" ".join(str(node.get("test", "")).split()),
            location=str(node.get("location", "")),
        )
        for node in report.xpath("//svrl:failed-assert", namespaces=SVRL)
    ]
    rules = etree.parse(str(ARCHIVEMATICA_SCHEMATRON))
    return RulesReport(
        assertions=len(rules.getroot().findall(".//sch:assert", SCHEMATRON)),
        failures=failures,
        svrl=etree.tostring(report, pretty_print=True, encoding="unicode"),
    )


def dangling_dmdids(mets: Path) -> list[str]:
    """The IDs that DMDID attributes of the structMap name but no dmdSec has."""
    root = etree.parse(str(mets)).getroot()
    ids = {section.get("ID") for section in root.iterfind(f"{{{METS_NAMESPACE}}}dmdSec")}
    return sorted(
        {
            reference
            for div in root.iter(f"{{{METS_NAMESPACE}}}div")
            for reference in (div.get("DMDID") or "").split()
            if reference not in ids
        }
    )
