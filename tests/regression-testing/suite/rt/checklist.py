"""The regression testing checklist, loaded from the CSV of the testing-checklists repository."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

CHECKLIST_CSV = Path(__file__).resolve().parent.parent / "checklist" / "regression-testing-checklist.csv"

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


def load_checklist(path: Path = CHECKLIST_CSV) -> dict[str, ChecklistItem]:
    items: dict[str, ChecklistItem] = {}
    with path.open(newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            identifier = (row.get("ID") or "").strip()
            if not identifier:
                continue
            criteria, notes = parse_then(row.get("Then") or "")
            items[identifier] = ChecklistItem(
                id=identifier,
                area=(row.get("Functional Area") or "").strip(),
                feature=(row.get("Feature") or "").strip(),
                criteria=criteria,
                notes=notes,
                external_tools=(row.get("External tools") or "").strip(),
            )
    return items
