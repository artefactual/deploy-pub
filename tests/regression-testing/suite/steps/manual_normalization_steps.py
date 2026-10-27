"""Steps for manual normalization: files inserted into the SIP by hand and the event detail form."""

from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Page
from pytest_bdd import then, when

from rt.assertions.mets import AIPMets
from rt.evidence import Evidence
from rt.pipeline.am_api import STATUS_USER_INPUT, UnitRun
from rt.pipeline.container import Container
from rt.settings import Settings

EVENT_DETAIL = "Manually normalized with ImageMagick for regression testing"
# The original of the Images/pictures sample that gets manual copies, and the copies made from it.
ORIGINAL = "MARBLES.TGA"
PRESERVATION_COPY = "MARBLES.tif"
ACCESS_COPY = "MARBLES.jpg"


def _sip_directory(run: UnitRun, settings: Settings) -> str:
    assert run.sip is not None and run.final_status == STATUS_USER_INPUT, (
        f"the SIP is not waiting: {run.describe()}"
    )
    return run.sip.path.replace("%sharedPath%", settings.shared_directory + "/").rstrip("/")


@when("the user inserts manually normalized files into the SIP")
def insert_manual_copies(container: Container, settings: Settings, evidence: Evidence, run: UnitRun) -> None:
    """Make a preservation and an access copy of the TGA with ImageMagick, where the pipeline looks for them.

    The SIP must be waiting at Approve normalization: the normalization jobs before
    it remove every file the database does not know, and the jobs after it pick the
    copies up from objects/manualNormalization.
    """
    sip_dir = _sip_directory(run, settings)
    assert run.current_microservice == "Approve normalization", (
        f"the SIP is not at Approve normalization: {run.describe()}"
    )
    objects = f"{sip_dir}/objects"
    for subdir, copy in (("preservation", PRESERVATION_COPY), ("access", ACCESS_COPY)):
        container.exec(["mkdir", "-p", f"{objects}/manualNormalization/{subdir}"])
        container.exec(
            ["convert", f"{objects}/{ORIGINAL}", f"{objects}/manualNormalization/{subdir}/{copy}"],
            service=settings.tools_service,
        )
    listing = container.exec(["find", f"{objects}/manualNormalization", "-type", "f"]).stdout.decode()
    evidence.note(
        "manually normalized files: " + ", ".join(sorted(line.rsplit("/", 1)[-1] for line in listing.split()))
    )
    evidence.write_text("manual-normalization/files.txt", listing)


@when("the user fills in the manual normalization event detail")
def fill_event_detail(ui: Page, evidence: Evidence, run: UnitRun) -> None:
    assert run.sip_uuid and run.final_status == STATUS_USER_INPUT, f"the SIP is not waiting: {run.describe()}"
    sip = run.sip_uuid
    ui.goto(f"/ingest/{sip}/")
    ui.get_by_role("link", name="Manual normalization event detail").click()
    ui.wait_for_url(f"**/ingest/{sip}/metadata/event_detail/")
    details = ui.locator("textarea[name$='-event_detail'], input[name$='-event_detail']")
    count = details.count()
    assert count, "the event detail form lists no manual normalization event"
    for index in range(count):
        details.nth(index).fill(EVENT_DETAIL)
    evidence.screenshot("manual normalization event detail form")
    ui.get_by_role("button", name="Save").click()
    ui.wait_for_url(f"**/ingest/{sip}/")
    evidence.note(f"entered the event detail for {count} manual normalization event(s)")


@then(
    "the manually normalized preservation derivative is added to the AIP "
    "with a UUID suffix and the appropriate file extension"
)
def manual_preservation_derivative_in_aip(evidence: Evidence, run: UnitRun) -> None:
    assert run.aip is not None, "no AIP was fetched from the Storage Service"
    mets = AIPMets(run.aip.mets)
    original = mets.file_by_original_name(f"objects/{ORIGINAL}")
    assert original is not None, f"the METS lists no original {ORIGINAL}"
    stem, extension = PRESERVATION_COPY.rsplit(".", 1)
    pattern = re.compile(rf"^{re.escape(stem)}-[0-9a-f-]{{36}}\.{re.escape(extension)}$")
    derivatives = [file for file in mets.files(use="preservation") if pattern.match(Path(file.href).name)]
    assert derivatives, f"the METS lists no preservation derivative named {stem}-<uuid>.{extension}"
    sources = {mets.derivation_source(file) for file in derivatives}
    assert mets.file_uuid(original) in sources, f"the derivative does not derive from {ORIGINAL}: {sources}"
    names = [Path(file.href).name for file in derivatives]
    if run.aip.root is not None:
        missing = [name for name in names if not list(run.aip.root.rglob(name))]
        assert not missing, f"derivatives listed in the METS but absent from the AIP: {missing}"
    evidence.note(f"preservation derivative(s) of {ORIGINAL}: {', '.join(names)}")


@then("the manually normalized access derivative is added to the DIP")
def manual_access_derivative_in_dip(evidence: Evidence, run: UnitRun) -> None:
    assert run.dip is not None, "the Storage Service has no DIP for this AIP"
    if run.dip.root is None:
        evidence.pending(
            "the DIP was not downloaded (larger than the size cap); only its existence was checked"
        )
        return
    stem, extension = ACCESS_COPY.rsplit(".", 1)
    pattern = re.compile(rf"^[0-9a-f-]{{36}}-{re.escape(stem)}\.{re.escape(extension)}$")
    names = [path.name for path in run.dip.objects()]
    matches = [name for name in names if pattern.match(name)]
    assert matches, f"the DIP has no object named <uuid>-{stem}.{extension}: {names}"
    evidence.note(f"access derivative(s) in the DIP: {', '.join(matches)}")


@then("the user can enter normalization event information for the manual normalization")
def event_detail_entered(evidence: Evidence) -> None:
    assert any("entered the event detail" in note for note in evidence.notes), (
        "the event detail form was not filled"
    )


@then("the event information is added to the METS")
def event_detail_in_mets(evidence: Evidence, run: UnitRun) -> None:
    assert run.aip is not None, "no AIP was fetched from the Storage Service"
    mets = AIPMets(run.aip.mets)
    events = [
        event for event in mets.all_events() if event.type == "normalization" and EVENT_DETAIL in event.detail
    ]
    assert events, "no normalization event in the METS carries the entered event detail"
    evidence.note(f"{len(events)} normalization event(s) carry the entered detail")
