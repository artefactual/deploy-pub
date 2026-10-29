"""The checklist loader, the release matching and the report with retired items."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rt import releases
from rt.checklist import CHECKLIST_CSV, ChecklistItem, load_checklist
from rt.report import load_results, render_checklist, render_summary


@pytest.mark.parametrize(
    ("version", "prefixes", "expected"),
    [
        ("1.19.0", ["1.19"], True),
        ("1.19.1", ["1.19"], True),
        ("1.190.0", ["1.19"], False),
        ("1.18.0", ["1.17", "1.18"], True),
        ("1.19.0", ["1.17", "1.18"], False),
        ("1.19.0", ["1.19.0"], True),
        ("1.19.0", [], True),
    ],
)
def test_release_matching(version: str, prefixes: list[str], expected: bool) -> None:
    assert releases.matches(version, prefixes) is expected


def test_retired_items_join_the_checklist() -> None:
    checklist = load_checklist()
    current = load_checklist(CHECKLIST_CSV, retired=None)
    retired = {identifier: item for identifier, item in checklist.items() if identifier not in current}
    assert sorted(retired) == sorted(
        ["21.1", "21.2", "21.3", "22.1", "22.2", "22.3", "22.4", "22.5", "22.6", "22.7"]
    )
    assert [item.releases for item in retired.values()] == [("1.16", "1.17", "1.18")] * len(retired)
    assert [item.releases for item in current.values()] == [()] * len(current)


@pytest.mark.parametrize(
    ("version", "expected"),
    [("1.16.0", True), ("1.17.1", True), ("1.18.0", True), ("1.19.0", False), ("1.20.0", False)],
)
def test_retired_item_applies_to_its_releases(version: str, expected: bool) -> None:
    item = load_checklist()["21.1"]
    assert item.applies_to(version) is expected


def test_current_item_applies_to_every_release() -> None:
    item = load_checklist()["1.2"]
    assert [item.applies_to(version) for version in ("1.16.0", "1.17.1", "1.19.0")] == [True] * 3


def test_retired_csv_needs_releases(tmp_path: Path) -> None:
    retired = tmp_path / "retired.csv"
    retired.write_text(
        "Functional Area,ID,Feature,Then,External tools,Severity,Releases\n"
        '21 - Backlog,21.1,Given,"- [ ] Then",,High,\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="names no releases"):
        load_checklist(CHECKLIST_CSV, retired)


def test_retired_csv_cannot_repeat_an_item(tmp_path: Path) -> None:
    retired = tmp_path / "retired.csv"
    retired.write_text(
        "Functional Area,ID,Feature,Then,External tools,Severity,Releases\n"
        '1 - Transfer Types,1.2,Given,"- [ ] Then",,High,1.18\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="also in"):
        load_checklist(CHECKLIST_CSV, retired)


def _result(evidence_dir: Path, os_label: str, item: ChecklistItem, version: str) -> None:
    directory = evidence_dir / os_label / item.id
    directory.mkdir(parents=True)
    (directory / "result.json").write_text(
        json.dumps(
            {
                "item_id": item.id,
                "os_label": os_label,
                "status": "pass",
                "scenario": f"scenario {item.id}",
                "criteria": [{"text": text, "outcome": "pass", "message": ""} for text in item.criteria],
                "versions": {"archivematica": version},
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )


def test_report_keeps_retired_items_for_their_releases_only(tmp_path: Path) -> None:
    checklist = load_checklist()
    evidence_dir = tmp_path / "evidence"
    _result(evidence_dir, "jammy-1.17", checklist["1.2"], "1.17.1")
    _result(evidence_dir, "jammy-1.17", checklist["21.1"], "1.17.1")
    _result(evidence_dir, "noble-qa", checklist["1.2"], "1.19.0")
    results = load_results(evidence_dir)
    old_line = render_checklist(checklist, results["jammy-1.17"], "jammy-1.17", evidence_dir, None)
    new_line = render_checklist(checklist, results["noble-qa"], "noble-qa", evidence_dir, None)
    assert ["### 21.1" in old_line, "## 21 - Backlog" in old_line] == [True, True]
    assert ["### 21.1" in new_line, "## 21 - Backlog" in new_line, "### 1.2" in new_line] == [
        False,
        False,
        True,
    ]


def test_summary_counts_retired_items_for_the_platforms_that_have_them(tmp_path: Path) -> None:
    checklist = load_checklist()
    current = load_checklist(CHECKLIST_CSV, retired=None)
    evidence_dir = tmp_path / "evidence"
    _result(evidence_dir, "noble-qa", checklist["1.2"], "1.19.0")
    summary = render_summary(checklist, load_results(evidence_dir))
    assert f"1 of {len(current)} checklist items have an automated result." in summary
    _result(evidence_dir, "jammy-1.18", checklist["1.2"], "1.18.0")
    summary = render_summary(checklist, load_results(evidence_dir))
    assert f"1 of {len(checklist)} checklist items have an automated result." in summary
    assert "21.1" in summary.split("Items without a result:")[1]
