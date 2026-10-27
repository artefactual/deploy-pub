"""The evidence bundle written for every scenario.

One directory per checklist item holds ``result.json`` (the outcome of each
criterion, the units the scenario created and warnings about jobs that failed
without failing the scenario), the Playwright trace and screenshots when a
browser was used, the job and task output of every unit, the stored packages
and a slice of the service logs.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rt.checklist import ChecklistItem
from rt.known_failures import KnownFailures

if TYPE_CHECKING:
    from playwright.sync_api import Page

PASS = "pass"
FAIL = "fail"
KNOWN = "known"
PENDING = "pending"
NOT_RUN = "not run"


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug[:60] or "step"


@dataclass
class Criterion:
    text: str
    outcome: str = NOT_RUN
    message: str = ""
    screenshot: str | None = None


@dataclass
class UnitRef:
    kind: str
    uuid: str
    name: str = ""
    status: str = ""
    microservice: str = ""


@dataclass
class ScenarioResult:
    item_id: str | None
    area: str
    feature_text: str
    scenario: str
    feature_file: str
    os_label: str
    status: str
    started: str
    ended: str | None
    criteria: list[Criterion]
    units: list[UnitRef]
    packages: list[dict[str, Any]]
    attachments: dict[str, str]
    notes: list[str]
    versions: dict[str, str]
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class Evidence:
    def __init__(
        self,
        directory: Path,
        os_label: str,
        item: ChecklistItem | None,
        scenario_name: str,
        feature_file: str,
        known: KnownFailures | None = None,
    ) -> None:
        self.directory = directory
        self.known = known or KnownFailures([])
        self.directory.mkdir(parents=True, exist_ok=True)
        self.os_label = os_label
        self.item = item
        self.scenario_name = scenario_name
        self.feature_file = feature_file
        self.started = datetime.now(UTC)
        self.ended: datetime | None = None
        self.criteria: list[Criterion] = []
        self.units: list[UnitRef] = []
        self.packages: list[dict[str, Any]] = []
        self.attachments: dict[str, str] = {}
        self.notes: list[str] = []
        self.warnings: list[str] = []
        self.versions: dict[str, str] = {}
        self.extra: dict[str, Any] = {}
        self.error: str | None = None
        self.page: Page | None = None
        self._current: int | None = None
        self._pending_reason: str | None = None
        self._failure_reason: str | None = None
        self._screenshot_counter = 0

    # Criteria -----------------------------------------------------------

    def set_criteria(self, texts: list[str]) -> None:
        self.criteria = [Criterion(text=text) for text in texts]

    def begin_criterion(self, index: int) -> None:
        self._current = index
        self._pending_reason = None
        self._failure_reason = None
        if index >= len(self.criteria):
            self.criteria.append(Criterion(text=f"criterion {index + 1}"))

    def pending(self, reason: str) -> None:
        """Mark the criterion being checked as pending instead of passed."""
        self._pending_reason = reason

    def fail(self, reason: str) -> None:
        """Mark the criterion being checked as failed while the scenario goes on to the next one.

        The scenario still fails at the end; the later criteria are evaluated first so
        the report shows every box that can be judged.
        """
        self._failure_reason = reason

    def finish_criterion(self, outcome: str, message: str = "") -> Criterion | None:
        """Record the outcome of the criterion being checked; returns it, with known failures applied.

        The known failures are matched against the platform and the Archivematica
        version in ``versions["archivematica"]``.
        """
        if self._current is None:
            return None
        criterion = self.criteria[self._current]
        if outcome == PASS and self._failure_reason:
            outcome, message = FAIL, self._failure_reason
        elif outcome == PASS and self._pending_reason:
            outcome, message = PENDING, self._pending_reason
        known = self.known.lookup(
            self.item.id if self.item else None,
            self._current,
            self.os_label,
            self.versions.get("archivematica", ""),
        )
        if known is not None and outcome == FAIL:
            outcome = KNOWN
            message = f"{known.reason} | {message}" if message else known.reason
        elif known is not None and outcome == PASS:
            self.warn(f"known failure {known.box} passed; remove its entry from known-failures.toml")
        criterion.outcome = outcome
        criterion.message = message
        screenshot = self.screenshot(f"criterion-{self._current + 1}")
        if screenshot is not None:
            criterion.screenshot = self.relative(screenshot)
        self._current = None
        self._pending_reason = None
        self._failure_reason = None
        return criterion

    @property
    def status(self) -> str:
        outcomes = {criterion.outcome for criterion in self.criteria}
        if self.error:
            return FAIL
        if FAIL in outcomes:
            return FAIL
        if KNOWN in outcomes:
            return KNOWN
        if NOT_RUN in outcomes or not outcomes:
            return NOT_RUN
        if PENDING in outcomes:
            return PENDING
        return PASS

    # Attachments --------------------------------------------------------

    def relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.directory))
        except ValueError:
            return str(path)

    def attach(self, label: str, path: Path) -> None:
        self.attachments[label] = self.relative(path)

    def note(self, text: str) -> None:
        self.notes.append(text)

    def warn(self, text: str) -> None:
        """Record something the analysts should look at even though the criteria passed."""
        self.warnings.append(text)

    def add_unit(
        self, kind: str, uuid: str, name: str = "", status: str = "", microservice: str = ""
    ) -> UnitRef:
        unit = UnitRef(kind=kind, uuid=uuid, name=name, status=status, microservice=microservice)
        self.units.append(unit)
        return unit

    def write_json(self, name: str, data: object) -> Path:
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def screenshot(self, label: str, page: Page | None = None) -> Path | None:
        """Save a screenshot of the scenario's page, or of another page such as the Storage Service's."""
        target = page or self.page
        if target is None or target.is_closed():
            return None
        self._screenshot_counter += 1
        path = self.directory / "screenshots" / f"{self._screenshot_counter:02d}-{slugify(label)}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.screenshot(path=str(path), full_page=True)
        except Exception as err:  # noqa: BLE001 - a lost page must not hide the test outcome
            self.note(f"screenshot {label!r} failed: {err}")
            return None
        return path

    # Result -------------------------------------------------------------

    def result(self) -> ScenarioResult:
        return ScenarioResult(
            item_id=self.item.id if self.item else None,
            area=self.item.area if self.item else "",
            feature_text=self.item.feature if self.item else "",
            scenario=self.scenario_name,
            feature_file=self.feature_file,
            os_label=self.os_label,
            status=self.status,
            started=self.started.isoformat(),
            ended=self.ended.isoformat() if self.ended else None,
            criteria=self.criteria,
            units=self.units,
            packages=self.packages,
            attachments=self.attachments,
            notes=self.notes,
            versions=self.versions,
            error=self.error,
            extra=self.extra,
            warnings=self.warnings,
        )

    def write_result(self) -> Path:
        self.ended = datetime.now(UTC)
        return self.write_json("result.json", asdict(self.result()))
