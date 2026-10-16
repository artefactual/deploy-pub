"""Boxes of the checklist that are expected to fail until a known problem is fixed."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

KNOWN_FAILURES_TOML = Path(__file__).resolve().parent.parent / "known-failures.toml"


@dataclass(frozen=True)
class KnownFailure:
    item: str
    reason: str
    criterion: int | None = None
    platforms: tuple[str, ...] = ()

    def applies(self, item_id: str, index: int, os_label: str) -> bool:
        """Whether the entry covers the box at a 0-based index of an item on a platform."""
        if item_id != self.item:
            return False
        if self.criterion is not None and self.criterion != index + 1:
            return False
        return not self.platforms or any(platform in os_label for platform in self.platforms)

    @property
    def box(self) -> str:
        return f"{self.item} box {self.criterion}" if self.criterion is not None else f"{self.item} (any box)"


class KnownFailures:
    def __init__(self, entries: list[KnownFailure]) -> None:
        self.entries = entries

    def lookup(self, item_id: str | None, index: int, os_label: str) -> KnownFailure | None:
        if item_id is None:
            return None
        for entry in self.entries:
            if entry.applies(item_id, index, os_label):
                return entry
        return None


def load_known_failures(path: Path = KNOWN_FAILURES_TOML) -> KnownFailures:
    if not path.is_file():
        return KnownFailures([])
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    entries: list[KnownFailure] = []
    for raw in data.get("known", []):
        criterion = raw.get("criterion")
        entries.append(
            KnownFailure(
                item=str(raw["item"]),
                reason=str(raw.get("reason", "")).strip(),
                criterion=int(criterion) if criterion is not None else None,
                platforms=tuple(str(platform) for platform in raw.get("platforms", [])),
            )
        )
    return KnownFailures(entries)
