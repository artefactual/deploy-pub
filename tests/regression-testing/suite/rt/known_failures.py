"""Boxes of the checklist that are expected to fail until a known problem is fixed."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from rt import releases

KNOWN_FAILURES_TOML = Path(__file__).resolve().parent.parent / "known-failures.toml"


@dataclass(frozen=True)
class KnownFailure:
    item: str
    reason: str
    criterion: int | None = None
    platforms: tuple[str, ...] = ()
    releases: tuple[str, ...] = ()

    def applies(self, item_id: str, index: int, os_label: str, am_version: str) -> bool:
        """Whether the entry covers the box at a 0-based index of an item on a platform and release.

        ``am_version`` is the version the pipeline reports, such as ``1.19.0``,
        matched against the releases of the entry as prefixes (see :mod:`rt.releases`).
        """
        if item_id != self.item:
            return False
        if self.criterion is not None and self.criterion != index + 1:
            return False
        if self.platforms and not any(platform in os_label for platform in self.platforms):
            return False
        return releases.matches(am_version, self.releases)

    @property
    def box(self) -> str:
        return f"{self.item} box {self.criterion}" if self.criterion is not None else f"{self.item} (any box)"


class KnownFailures:
    def __init__(self, entries: list[KnownFailure]) -> None:
        self.entries = entries

    def lookup(self, item_id: str | None, index: int, os_label: str, am_version: str) -> KnownFailure | None:
        """The first entry covering the box of an item on a platform and Archivematica version."""
        if item_id is None:
            return None
        for entry in self.entries:
            if entry.applies(item_id, index, os_label, am_version):
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
                releases=tuple(str(release) for release in raw.get("releases", [])),
            )
        )
    return KnownFailures(entries)
