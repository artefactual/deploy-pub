"""Steps for the CONTENTdm DIP upload, which only restructures the DIP for the CONTENTdm project client."""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path
from typing import Any

from pytest_bdd import then

from rt.evidence import Evidence
from rt.pipeline.am_api import JOB_COMPLETED, AMClient, UnitRun
from rt.pipeline.container import Container
from rt.pipeline.packages import fetch_dip, find_dip
from rt.pipeline.ss_api import SSClient
from rt.settings import Settings
from steps.pipeline_steps import record_units

RESTRUCTURE_JOB = "Restructure DIP for CONTENTdm upload"
PACKAGE_FILES = ("simple.txt", "compound.txt")


def _dip_root(am: AMClient, ss: SSClient, settings: Settings, evidence: Evidence, run: UnitRun) -> Path:
    """The extracted DIP; the DIP is stored after the AIP, so it may need waiting for."""
    assert run.sip_uuid, f"the transfer produced no SIP: {run.describe()}"
    if run.dip is None:
        deadline = time.monotonic() + settings.package_timeout
        package = find_dip(ss, run.sip_uuid)
        while package is None and time.monotonic() < deadline:
            time.sleep(settings.poll_interval)
            package = find_dip(ss, run.sip_uuid)
        assert package is not None, f"the Storage Service has no DIP for AIP {run.sip_uuid}"
        run.dip = fetch_dip(
            ss,
            package,
            evidence.directory / "dip",
            size_cap=settings.aip_size_cap,
            timeout=settings.package_timeout,
            interval=settings.poll_interval,
        )
        if run.dip.archive is not None:
            evidence.attach("dip", run.dip.archive)
        # The DIP jobs ran after the unit was recorded.
        record_units(am, evidence, run, interval=settings.poll_interval)
    assert run.dip.root is not None, "the DIP was not downloaded (larger than the size cap)"
    return run.dip.root


def _package_file(root: Path) -> Path:
    found = [path for name in PACKAGE_FILES for path in root.rglob(name)]
    assert found, f"the DIP has no {' or '.join(PACKAGE_FILES)}"
    return found[0]


@then("a simple.txt or compound.txt file is added to the DIP")
def package_file_in_dip(
    am: AMClient, ss: SSClient, settings: Settings, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    root = _dip_root(am, ss, settings, evidence, run)
    jobs = run.jobs_named(RESTRUCTURE_JOB)
    assert jobs and all(job.get("status") == JOB_COMPLETED for job in jobs), (
        f"{RESTRUCTURE_JOB!r} jobs: {[job.get('status') for job in jobs]}"
    )
    path = _package_file(root)
    state["package_file"] = path
    evidence.attach("contentdm-package-file", path)
    evidence.note(f"{path.relative_to(root)} in DIP {run.dip.uuid if run.dip else ''}")


@then("the simple.txt or compound.txt file contains the descriptive metadata from the CSV")
def package_file_has_csv_metadata(
    container: Container, settings: Settings, evidence: Evidence, run: UnitRun, state: dict[str, Any]
) -> None:
    path: Path = state["package_file"]
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline=""), delimiter="\t"))
    assert rows, f"{path.name} lists no objects"
    # The transfer's metadata.csv, as the pipeline read it; its dc.* columns become the file's columns.
    source = container.exec(
        ["cat", f"{settings.transfer_source_root}/{run.source_path}/metadata/metadata.csv"]
    ).stdout.decode("utf-8")
    reader = csv.reader(io.StringIO(source))
    header = next(reader)
    filename_index, title_index = header.index("filename"), header.index("dc.title")
    expected = {row[title_index]: Path(row[filename_index]).name for row in reader if row}
    # The pipeline changes file names it cannot keep (Montréal.png becomes Montreal.png), so
    # the objects are matched by title.
    titles = {row.get("title", ""): row.get("Filename", "") for row in rows}
    missing = {title: name for title, name in expected.items() if title not in titles}
    assert not missing, f"titles from metadata.csv absent from {path.name}: {missing}; file has {titles}"
    evidence.note(
        f"{path.name} columns {list(rows[0])}; the {len(expected)} titles of metadata.csv are present: "
        + ", ".join(f"{title!r} ({titles[title]})" for title in expected)
    )
