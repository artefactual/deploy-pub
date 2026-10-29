"""The regression testing checklist, loaded from the CSV of the testing-checklists repository.

The items the repository retired when Archivematica 1.19 dropped the features
they test, the Backlog and Appraisal tabs, live on in a second CSV next to it
with the releases they still apply to, so the lines that ship those features
keep testing them.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from rt import releases

CHECKLIST_DIR = Path(__file__).resolve().parent.parent / "checklist"
CHECKLIST_CSV = CHECKLIST_DIR / "regression-testing-checklist.csv"
RETIRED_CSV = CHECKLIST_DIR / "retired-items.csv"

_CHECKBOX = re.compile(r"^\s*-\s*\[[ xX]\]\s*(.*\S)\s*$")
_AREA_NUMBER = re.compile(r"^\s*(\d+)\s*-\s*(.*\S)\s*$")


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    area: str
    feature: str
    criteria: tuple[str, ...]
    notes: tuple[str, ...]
    external_tools: str
    # The Archivematica releases the item applies to, as version prefixes; none for every release.
    releases: tuple[str, ...] = ()

    @property
    def area_number(self) -> int:
        match = _AREA_NUMBER.match(self.area)
        return int(match.group(1)) if match else 0

    @property
    def area_name(self) -> str:
        match = _AREA_NUMBER.match(self.area)
        return match.group(2) if match else self.area

    @property
    def sort_key(self) -> tuple[int, ...]:
        return tuple(int(part) for part in self.id.split("."))

    def applies_to(self, version: str) -> bool:
        """Whether the item is part of the checklist of the Archivematica ``version``."""
        return releases.matches(version, self.releases)


def parse_then(then: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the "Then" column into checkbox criteria and free-text notes."""
    criteria: list[str] = []
    notes: list[str] = []
    for line in then.splitlines():
        match = _CHECKBOX.match(line)
        if match:
            criteria.append(match.group(1))
        elif line.strip():
            notes.append(line.strip())
    return tuple(criteria), tuple(notes)


def _read_items(path: Path, retired: bool) -> dict[str, ChecklistItem]:
    """The items of a CSV; a retired item must name the releases it applies to."""
    items: dict[str, ChecklistItem] = {}
    with path.open(newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            identifier = (row.get("ID") or "").strip()
            if not identifier:
                continue
            applicable = tuple((row.get("Releases") or "").split())
            if retired and not applicable:
                raise ValueError(f"{path}: the retired item {identifier} names no releases")
            criteria, notes = parse_then(row.get("Then") or "")
            items[identifier] = ChecklistItem(
                id=identifier,
                area=(row.get("Functional Area") or "").strip(),
                feature=(row.get("Feature") or "").strip(),
                criteria=criteria,
                notes=notes,
                external_tools=(row.get("External tools") or "").strip(),
                releases=applicable,
            )
    return items


def load_checklist(
    path: Path = CHECKLIST_CSV, retired: Path | None = RETIRED_CSV
) -> dict[str, ChecklistItem]:
    """The items of the checklist and, when a retired items CSV is given, those of the retired items."""
    items = _read_items(path, retired=False)
    if retired is not None and retired.is_file():
        for identifier, item in _read_items(retired, retired=True).items():
            if identifier in items:
                raise ValueError(f"{retired}: the retired item {identifier} is also in {path}")
            items[identifier] = item
    return items
