"""Steps that drive the Administration pages: processing configurations, storage, language, users, failures."""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Browser, Page, expect
from pytest_bdd import given, parsers, then, when

from rt.evidence import Evidence
from rt.pipeline.am_api import AMClient, UnitRun
from rt.pipeline.decisions import DECISIONS
from rt.pipeline.processing_config import ProcessingConfig
from rt.pipeline.web import Dashboard, Form
from rt.settings import Settings
from steps.normalization_steps import thumbnails_for_all_objects

Restore = list[tuple[str, Callable[[], None]]]

PROCESSING = "administration/processing/"
ACCOUNTS = "administration/accounts/"
FAILURES = "administration/reports/failures/"
THUMBNAIL_DECISION = "Choose thumbnail mode"
TRANSCRIBE_DECISION = "Transcribe SIP contents?"
SIZE_UNITS = {"bytes": 1, "byte": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4, "PB": 1024**5}
# Strings of the Transfer tab page in the languages the scenarios use: the label of the
# Ingest tab and the start button.
TRANSLATED_STRINGS = {"fr": ("Acquisition", "Commencer le transfert")}
_SIZE = re.compile(r"([\d.,]+)\s*(bytes?|KB|MB|GB|TB|PB)")


def _edit_path(name: str) -> str:
    return f"{PROCESSING}edit/{name}/"


def _decision_field(decision: str, choice: str) -> tuple[str, str]:
    """The form field (the decision point's link) and option value (the chain) of a choice."""
    for entry in DECISIONS[decision]:
        if choice in entry.choices:
            return entry.link_id, entry.choices[choice]
    raise KeyError(f"{decision!r} offers no choice {choice!r}")


def _snapshot_default(dashboard: Dashboard, restore: Restore, state: dict[str, Any]) -> Form:
    """The default processing configuration as it is now; it comes back at the end of the scenario."""
    if "default_form" not in state:
        form = dashboard.form(_edit_path("default"), having="name")
        state["default_form"] = form

        def restore_default() -> None:
            dashboard.post(_edit_path("default"), form.fields)

        restore.append(("the default processing configuration", restore_default))
    snapshot: Form = state["default_form"]
    return snapshot


def _parse_size(text: str) -> int:
    match = _SIZE.search(text)
    if match is None:
        raise ValueError(f"no size in {text!r}")
    number = float(match.group(1).replace(",", ""))
    unit = match.group(2)
    return int(number * SIZE_UNITS.get(unit, SIZE_UNITS.get(unit.rstrip("s"), 1)))


def _aip_storage_used(ui: Page) -> tuple[int, str]:
    row = ui.locator("tr", has_text="AIP Storage").first
    expect(row).to_be_visible()
    text = row.locator("td").nth(2).inner_text().strip()
    return _parse_size(text), text


# Processing configurations ------------------------------------------------------------


@given(
    parsers.parse('the "{decision}" decision of the default processing configuration is set to "{choice}"')
)
def default_configuration_decision(
    dashboard: Dashboard, restore: Restore, state: dict[str, Any], decision: str, choice: str
) -> None:
    _snapshot_default(dashboard, restore, state)
    link_id, target = _decision_field(decision, choice)
    # Start from the configuration as it is now, so earlier steps of the scenario are kept.
    fields = dict(dashboard.form(_edit_path("default"), having="name").fields)
    fields[link_id] = target
    dashboard.post(_edit_path("default"), fields)
    state["changed"] = (link_id, target)


@given('the default processing configuration is completed with the "automated" decisions')
def default_configuration_completed(
    am: AMClient, dashboard: Dashboard, restore: Restore, state: dict[str, Any]
) -> None:
    """Give the default configuration the automated choices, so a transfer runs through without questions."""
    form = _snapshot_default(dashboard, restore, state)
    automated = ProcessingConfig(am.processing_configuration("automated")).targets()
    fields = dict(form.fields)
    for link_id, target in automated.items():
        if link_id in form.options and any(value == target for value, _ in form.options[link_id]):
            fields[link_id] = target
    dashboard.post(_edit_path("default"), fields)


@given(parsers.parse('the "{decision}" decision of the default processing configuration is changed'))
def default_configuration_decision_changed(
    dashboard: Dashboard, restore: Restore, state: dict[str, Any], decision: str
) -> None:
    """Set the decision to any choice other than its current one."""
    _snapshot_default(dashboard, restore, state)
    form = dashboard.form(_edit_path("default"), having="name")
    link_id, _ = _decision_field(decision, next(iter(DECISIONS[decision][0].choices)))
    current = form.fields.get(link_id, "")
    target = next(value for value, _ in form.options[link_id] if value and value != current)
    fields = dict(form.fields)
    fields[link_id] = target
    dashboard.post(_edit_path("default"), fields)
    state["changed"] = (link_id, target)


@when('the user opens Administration > Processing configuration and selects Edit for "default"')
def open_default_configuration(
    ui: Page, dashboard: Dashboard, restore: Restore, state: dict[str, Any]
) -> None:
    _snapshot_default(dashboard, restore, state)
    ui.goto(f"/{PROCESSING}")
    ui.click(f"a[href='/{PROCESSING}edit/default/']")
    ui.wait_for_url(f"**/{PROCESSING}edit/default/")


@then("the processing configuration form opens")
def processing_form_opens(ui: Page, evidence: Evidence) -> None:
    count = ui.locator("form select").count()
    assert count > 10, f"the form shows {count} decision fields"
    assert ui.input_value("input[name='name']") == "default"
    evidence.note(f"the processing configuration form shows {count} decision fields")


@then("the user can make changes")
def user_changes_form(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    link_id, _ = _decision_field(THUMBNAIL_DECISION, "Yes")
    select = ui.locator(f"select[name='{link_id}']")
    current = select.input_value()
    options = [
        (option.get_attribute("value") or "", option.inner_text().strip())
        for option in select.locator("option").all()
    ]
    value, label = next((value, label) for value, label in options if value and value != current)
    select.select_option(value)
    state["chosen"] = (link_id, value, label)
    evidence.note(f"changed {THUMBNAIL_DECISION!r} to {label!r}")


@when(parsers.parse('the user adds a processing configuration named "{name}"'))
def add_processing_configuration(
    ui: Page, dashboard: Dashboard, restore: Restore, state: dict[str, Any], name: str
) -> None:
    def delete_configuration() -> None:
        dashboard.page(f"{PROCESSING}delete/{name}/")

    restore.append((f"the processing configuration {name!r}", delete_configuration))
    ui.goto(f"/{PROCESSING}")
    ui.get_by_role("link", name="Add", exact=True).click()
    ui.wait_for_url(f"**/{PROCESSING}add/")
    state["form_fields"] = ui.locator("form select").count()
    ui.fill("input[name='name']", name)
    chosen: dict[str, str] = {}
    for decision, choice in ((THUMBNAIL_DECISION, "No"), (TRANSCRIBE_DECISION, "No")):
        link_id, target = _decision_field(decision, choice)
        ui.select_option(f"select[name='{link_id}']", target)
        chosen[link_id] = target
    state["new_config"] = (name, chosen)


@then("a processing configuration form opens")
def new_configuration_form_opens(evidence: Evidence, state: dict[str, Any]) -> None:
    count = int(state["form_fields"])
    assert count > 10, f"the form shows {count} decision fields"
    evidence.note(f"the new configuration form shows {count} decision fields")


@then("the user can select decision points")
def user_selects_decisions(evidence: Evidence, state: dict[str, Any]) -> None:
    _, chosen = state["new_config"]
    assert chosen, "no decision point was selected"
    evidence.note(f"selected {len(chosen)} decision points")


@then("the user can save the form")
def user_saves_form(ui: Page, am: AMClient, evidence: Evidence, state: dict[str, Any]) -> None:
    ui.get_by_role("button", name="Save").click()
    ui.wait_for_url(f"**/{PROCESSING}")
    expect(ui.get_by_text("Saved!")).to_be_visible()
    if "new_config" in state:
        name, chosen = state["new_config"]
        expect(ui.locator(f"a[href='/{PROCESSING}edit/{name}/']")).to_be_visible()
        assert name in am.processing_configuration_names(), f"{name!r} is not listed by the API"
        targets = ProcessingConfig(am.processing_configuration(name)).targets()
        wrong = {
            link: (targets.get(link), target)
            for link, target in chosen.items()
            if targets.get(link) != target
        }
        assert not wrong, f"saved choices differ from the selection: {wrong}"
        evidence.note(f"configuration {name!r} saved with the selected decisions")
    else:
        link_id, value, label = state["chosen"]
        targets = ProcessingConfig(am.processing_configuration("default")).targets()
        assert targets.get(link_id) == value, (
            f"the saved configuration has {targets.get(link_id)} for the changed decision"
        )
        evidence.note(f"the default configuration now has {THUMBNAIL_DECISION!r} = {label!r}")


@then("the transfer follows the decisions set in the default processing configuration")
def transfer_follows_default(evidence: Evidence, run: UnitRun) -> None:
    thumbnails_for_all_objects(evidence, run)


@when('the user selects Download for the "default" processing configuration')
def download_default_configuration(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    ui.goto(f"/{PROCESSING}")
    with ui.expect_download() as download_info:
        ui.click(f"a[href='/{PROCESSING}download/default/']")
    dest = evidence.directory / "processing-config" / "downloaded-defaultProcessingMCP.xml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    download_info.value.save_as(dest)
    state["downloaded"] = dest
    evidence.attach("downloaded-config", dest)


@then("an XML file with the processing configuration decisions is downloaded")
def downloaded_configuration(am: AMClient, evidence: Evidence, state: dict[str, Any]) -> None:
    downloaded = ProcessingConfig(state["downloaded"].read_bytes()).targets()
    current = ProcessingConfig(am.processing_configuration("default")).targets()
    assert downloaded, "the downloaded file has no preconfigured choices"
    assert downloaded == current, (
        "the downloaded decisions differ from the configuration the dashboard serves"
    )
    evidence.note(f"downloaded configuration with {len(downloaded)} preconfigured choices")


@when('the user selects Reset for the "default" processing configuration')
def reset_default_configuration(ui: Page) -> None:
    ui.goto(f"/{PROCESSING}")
    ui.click(f"a[href='/{PROCESSING}reset/default/']")
    ui.wait_for_url(f"**/{PROCESSING}")
    expect(ui.get_by_text('Configuration "default" was reset')).to_be_visible()


@then("the configuration is reset to the standard pre-sets")
def configuration_reset(
    am: AMClient, dashboard: Dashboard, evidence: Evidence, state: dict[str, Any]
) -> None:
    link_id, target = state["changed"]
    current = ProcessingConfig(am.processing_configuration("default")).targets()
    assert current.get(link_id) != target, "the changed decision survived the reset"
    original: Form = state["default_form"]
    now = dashboard.form(_edit_path("default"), having="name")
    differences = sorted(name for name, value in original.fields.items() if now.fields.get(name) != value)
    assert not differences, f"fields that differ from the configuration before the change: {differences}"
    evidence.note("the default configuration is back to its pre-set values")


# Storage -------------------------------------------------------------------------------


@when("the user opens Administration > Storage locations")
def open_storage_locations(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    ui.goto("/administration/storage/")
    used, text = _aip_storage_used(ui)
    state["used_before"] = used
    evidence.note(f"AIP storage before: {text}")


@then("the Used storage value of the AIP storage location increases")
def used_storage_increases(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    ui.goto("/administration/storage/")
    used, text = _aip_storage_used(ui)
    before = int(state["used_before"])
    assert used > before, f"AIP storage used went from {before} to {used} bytes ({text})"
    evidence.note(f"AIP storage after: {text}")


@when('the user opens Administration > Processing storage usage and selects "Calculate disk usage"')
def calculate_disk_usage(ui: Page) -> None:
    ui.goto("/administration/usage/")
    ui.get_by_role("link", name="Calculate disk usage").click()
    ui.wait_for_url("**/administration/usage/?calculate=true")


@then("the disk usage is calculated and displayed")
def disk_usage_displayed(ui: Page, evidence: Evidence) -> None:
    expect(ui.get_by_text("Disk usage:")).to_be_visible()
    text = ui.locator("body").inner_text()
    match = re.search(r"Disk usage:\s*([\d.,]+\s*\w+)\s*/\s*([\d.,]+\s*\w+)", text)
    assert match, "the usage page shows no disk usage figures"
    assert "Clearable directories:" in text, "the usage page shows no clearable directories"
    evidence.note(f"disk usage: {match.group(1)} / {match.group(2)}")


# Language ------------------------------------------------------------------------------


@when(parsers.parse('the user changes the language to "{code}" in Administration > Language'))
def change_language(ui: Page, state: dict[str, Any], code: str) -> None:
    ui.goto("/administration/language/")
    ui.check(f"input[name='language'][value='{code}']")
    ui.get_by_role("button", name="Change").click()
    ui.wait_for_load_state()
    state["language"] = code


@then("the interface items appear in that language")
def interface_translated(ui: Page, evidence: Evidence, state: dict[str, Any]) -> None:
    code = str(state["language"])
    tab, button = TRANSLATED_STRINGS[code]
    ui.goto("/transfer/")
    # The tab label carries the count of units waiting for the user, hence the prefix match.
    expect(ui.get_by_role("link", name=re.compile(rf"^{re.escape(tab)}( \d+)?$")).first).to_be_visible()
    expect(ui.get_by_text(button, exact=True).first).to_be_visible()
    evidence.note(f"in {code!r} the Ingest tab reads {tab!r} and the start button {button!r}")


# Users ---------------------------------------------------------------------------------


def _user_id(dashboard: Dashboard, username: str) -> str | None:
    page = dashboard.page(ACCOUNTS)
    match = re.search(rf'<a href="/{ACCOUNTS}(\d+)/edit/">{re.escape(username)}</a>', page)
    return match.group(1) if match else None


def _delete_user(dashboard: Dashboard, username: str) -> None:
    user_id = _user_id(dashboard, username)
    if user_id is not None:
        dashboard.post(f"{ACCOUNTS}{user_id}/delete/", {"__confirm__": "1"})


def _create_user(dashboard: Dashboard, username: str, password: str, superuser: bool = False) -> None:
    form = dashboard.form(f"{ACCOUNTS}add/", having="username")
    fields = dict(form.fields)
    fields.update(
        {
            "username": username,
            "email": f"{username}@example.com",
            "password1": password,
            "password2": password,
        }
    )
    fields["is_active"] = "on"
    if superuser:
        fields["is_superuser"] = "on"
    else:
        fields.pop("is_superuser", None)
    dashboard.post(f"{ACCOUNTS}add/", fields)


@when(parsers.parse('the user adds, edits and deletes a user named "{username}" in Administration > Users'))
def add_edit_delete_user(
    ui: Page, dashboard: Dashboard, evidence: Evidence, restore: Restore, state: dict[str, Any], username: str
) -> None:
    restore.append((f"the user {username!r}", lambda: _delete_user(dashboard, username)))
    password = "Rt-" + secrets.token_urlsafe(12)
    ui.goto(f"/{ACCOUNTS}")
    ui.get_by_role("link", name="Add new").click()
    ui.wait_for_url(f"**/{ACCOUNTS}add/")
    ui.fill("input[name='username']", username)
    ui.fill("input[name='email']", f"{username}@example.com")
    ui.fill("input[name='password1']", password)
    ui.fill("input[name='password2']", password)
    ui.get_by_role("button", name="Create").click()
    ui.wait_for_url(f"**/{ACCOUNTS}")
    row = ui.locator("tr", has_text=username).first
    expect(row).to_be_visible()
    evidence.screenshot("user added")
    user_id = _user_id(dashboard, username)
    assert user_id is not None, f"{username!r} is not listed after being created"
    ui.goto(f"/{ACCOUNTS}{user_id}/edit/")
    ui.fill("input[name='email']", f"{username}.edited@example.com")
    ui.get_by_role("button", name="Save").click()
    expect(ui.get_by_text("Saved.", exact=True)).to_be_visible()
    ui.goto(f"/{ACCOUNTS}")
    expect(ui.locator("tr", has_text=f"{username}.edited@example.com").first).to_be_visible()
    evidence.screenshot("user edited")
    ui.goto(f"/{ACCOUNTS}{user_id}/delete/")
    ui.locator("input[type='submit'][class*='btn-primary']").click()
    ui.wait_for_url(f"**/{ACCOUNTS}")
    expect(ui.locator("tr", has_text=username)).to_have_count(0)
    evidence.screenshot("user deleted")
    state["user_actions"] = ("added", "edited", "deleted")


@then("the user can add, edit and delete users")
def user_management_works(evidence: Evidence, state: dict[str, Any]) -> None:
    actions = state.get("user_actions", ())
    assert actions == ("added", "edited", "deleted"), f"actions completed: {actions}"
    evidence.note("a user was added, edited and deleted through Administration > Users")


@given(parsers.parse('a non-administrator user named "{username}" exists'))
def non_admin_user_exists(
    dashboard: Dashboard, restore: Restore, state: dict[str, Any], username: str
) -> None:
    restore.append((f"the user {username!r}", lambda: _delete_user(dashboard, username)))
    password = "Rt-" + secrets.token_urlsafe(12)
    _create_user(dashboard, username, password, superuser=False)
    state["other_user"] = (username, password)


@when("that user logs in to the dashboard and opens the Administration tab")
def other_user_opens_administration(
    browser: Browser, settings: Settings, evidence: Evidence, state: dict[str, Any]
) -> None:
    username, password = state["other_user"]
    context = browser.new_context(viewport={"width": 1400, "height": 900}, base_url=settings.am_url)
    page = context.new_page()
    page.goto("/")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_text("Log in", exact=True).click()
    expect(page).to_have_url(re.compile(r"/transfer/?$"))
    page.goto("/administration/")
    state["other_page"] = page
    state["other_context"] = context
    main_page = evidence.page
    evidence.page = page
    try:
        evidence.screenshot(f"administration as {username}")
    finally:
        evidence.page = main_page


@then("the Users menu item is not shown")
def users_menu_hidden(evidence: Evidence, state: dict[str, Any]) -> None:
    page: Page = state["other_page"]
    try:
        assert page.locator(f"a[href='/{ACCOUNTS}']").count() == 0, (
            "the Users menu item is shown to a non-administrator"
        )
        page.goto(f"/{ACCOUNTS}")
        assert "/forbidden" in page.url, f"a non-administrator reached {page.url}"
        evidence.note("no Users entry in the Administration sidebar; the users page is forbidden")
    finally:
        state["other_context"].close()


# Failures ------------------------------------------------------------------------------


@when("the user opens Administration > Failures")
def open_failures(ui: Page) -> None:
    ui.goto(f"/{FAILURES}")


@then("the user sees a failure report")
def failure_report_listed(ui: Page, evidence: Evidence, run: UnitRun) -> None:
    row = ui.locator("tr", has_text=run.transfer_uuid).first
    expect(row).to_be_visible()
    evidence.note(f"failure report listed for transfer {run.transfer_uuid}")


@then("the user can click on the report to see which job failed")
def failure_report_detail(ui: Page, evidence: Evidence, run: UnitRun) -> None:
    ui.locator("tr", has_text=run.transfer_uuid).first.get_by_role("link").first.click()
    ui.wait_for_url(f"**/{FAILURES}*/")
    text = ui.locator("body").inner_text()
    # The report lists each job with its status code; 4 is a failed job.
    match = re.search(r"Scan for viruses in directories\s+(\d+)", text)
    assert match, "the report does not list the virus scan job"
    assert match.group(1) == "4", f"the virus scan job is listed with status {match.group(1)}, not 4 (failed)"
    evidence.note("the report lists the virus scan job with the failed status")


@then("the user can delete the failure report")
def delete_failure_report(ui: Page, evidence: Evidence, run: UnitRun) -> None:
    ui.goto(f"/{FAILURES}")
    ui.locator("tr", has_text=run.transfer_uuid).first.get_by_role("link", name="Delete").click()
    # The link leads to a confirmation page whose form carries a __confirm__ field.
    confirm = ui.locator("form:has(input[name='__confirm__']) input[type='submit']")
    expect(confirm).to_be_visible()
    evidence.screenshot("failure report deletion confirmation")
    confirm.click()
    ui.wait_for_url(f"**/{FAILURES}")
    expect(ui.locator("tr", has_text=run.transfer_uuid)).to_have_count(0)
    evidence.note("the failure report was deleted after confirming")
