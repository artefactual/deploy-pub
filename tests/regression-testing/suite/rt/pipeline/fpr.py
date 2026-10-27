"""The Preservation planning pages of the dashboard: commands, rules, enabling, editing and revisions.

The dashboard has no API for the Format Policy Registry, so this module reads the
rows of the list pages and submits the same forms a user would: the enable/disable
confirmation and the edit form of a command. From 1.19 a list page embeds its rows
as the JSON payload of its Vue table; earlier releases render them as an HTML
table, whose cells this module reads into rows with the keys and value types of
that payload.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any

import lxml.html
import requests
from lxml import etree

from rt.pipeline.am_api import AMClient, AMError
from rt.pipeline.web import Dashboard, parse_forms

IDCOMMAND = "idcommand"
FPCOMMAND = "fpcommand"
FPRULE = "fprule"

_PAYLOAD = re.compile(
    r'<script id="fpr-(?P<category>[a-z]+)-list-payload" type="application/json">(?P<json>.*?)</script>',
    re.DOTALL,
)
_UUID_LINK = re.compile(r"/fpr/[a-z]+/(?P<uuid>[0-9a-f-]{36})/")
_DETAIL_LINK = re.compile(r"/fpr/(?P<category>[a-z]+)/(?P<uuid>[0-9a-f-]{36})/$")
_VERSION = re.compile(r"(\d+)")
_DETAIL_TOOL = re.compile(r"<dt>\s*Tool\s*</dt>\s*<dd>(.*?)</dd>", re.DOTALL)
_DETAIL_COMMAND = re.compile(r"<dt>\s*Command\s*</dt>\s*<dd><pre>(.*?)</pre></dd>", re.DOTALL)

# The cells of the HTML table of the rules that hold more than one value. The
# Format cell follows the description of the format version with its version,
# its PRONOM identifier or both in parentheses, when it has them. Descriptions
# can end in parentheses of their own, such as "Waveform Audio (WAVEFORMATEX)",
# so an identifier alone counts only when it looks like fmt/N or x-fmt/N. The
# Success cell counts the successful attempts out of all attempts.
_RULE_FORMAT_SUFFIX = re.compile(r" \((?:version: (?P<version>[^,]*?)(?:, .+)?|(?:[a-z]+-)?fmt/\d+)\)$")
_RULE_SUCCESS = re.compile(r"\d+ out of (?P<attempts>\d+)")

# The purposes of the rules: the HTML table shows their labels, the payload their values.
_RULE_PURPOSES = {
    "Access": "access",
    "Characterization": "characterization",
    "Extract": "extract",
    "Preservation": "preservation",
    "Thumbnail": "thumbnail",
    "Transcription": "transcription",
    "Validation": "validation",
    "Validation against a policy": "policy_check",
    "Default access": "default_access",
    "Default characterization": "default_characterization",
    "Default thumbnail": "default_thumbnail",
}


def _version_key(description: str) -> tuple[int, ...]:
    """The numbers of a description, so that "Fido 1.6.4rc1" sorts after "Fido 1.6.3rc1"."""
    return tuple(int(number) for number in _VERSION.findall(description))


@dataclass(frozen=True)
class FPREntry:
    """A row of a Preservation planning list: a command or a rule."""

    uuid: str
    description: str
    enabled: bool
    tool: str = ""
    purpose: str = ""
    command: str = ""
    attempts: int = 0


class FPR:
    def __init__(self, am: AMClient) -> None:
        self.am = am
        self.web = Dashboard(am)

    # Pages -------------------------------------------------------------------

    def _session(self) -> requests.Session:
        return self.am.web_session()

    def page(self, path: str) -> str:
        return self.web.page(path)

    def _post(self, path: str, fields: dict[str, str]) -> requests.Response:
        return self.web.post(path, fields)

    def command_text(self, uuid: str) -> str:
        """The script of a format policy command, as its detail page shows it."""
        match = _DETAIL_COMMAND.search(self.page(f"fpr/{FPCOMMAND}/{uuid}/"))
        if match is None:
            raise AMError(f"the detail page of command {uuid} shows no script")
        return html.unescape(match.group(1))

    def payload(self, category: str, path: str | None = None) -> list[dict[str, Any]]:
        """The rows of the table of a list page.

        They come from the JSON payload the page embeds for its table or, on a page
        without one, from the HTML table it renders, with the payload keys the list
        methods read.
        """
        page = self.page(path or f"fpr/{category}/")
        for match in _PAYLOAD.finditer(page):
            if match.group("category") == category:
                data = json.loads(match.group("json"))
                rows = data.get("rows", data) if isinstance(data, dict) else data
                return [dict(row) for row in rows]
        table_rows = _table_rows(page, category)
        if table_rows is None:
            raise AMError(f"the page {path or category} has neither a {category} table payload nor a table")
        return table_rows

    # Lists -------------------------------------------------------------------

    def id_commands(self) -> list[FPREntry]:
        return [
            FPREntry(
                uuid=str(row["id"]),
                description=str(row.get("command", "")),
                enabled=bool(row.get("enabled")),
                tool=str(row.get("tool", "")),
            )
            for row in self.payload(IDCOMMAND)
        ]

    def fp_commands(self, usage: str | None = None) -> list[FPREntry]:
        path = f"fpr/{FPCOMMAND}/{usage}/" if usage else None
        return [
            FPREntry(
                uuid=str(row["id"]),
                description=str(row.get("description", "")),
                enabled=bool(row.get("enabled")),
                tool=str(row.get("tool", "")),
                purpose=usage or "",
            )
            for row in self.payload(FPCOMMAND, path)
        ]

    def fp_rules(self) -> list[FPREntry]:
        return [
            FPREntry(
                uuid=str(row["id"]),
                description=f"{row.get('purpose', '')}: {row.get('format', '')} {row.get('formatVersion', '')}".strip(),
                enabled=bool(row.get("enabled")),
                purpose=str(row.get("purpose", "")),
                command=str(row.get("command", "")),
                attempts=int(row.get("successAttempts") or 0),
            )
            for row in self.payload(FPRULE)
        ]

    def id_command(self, description: str) -> FPREntry:
        return self._find(self.id_commands(), description)

    def fp_command(self, description: str, usage: str | None = None, enabled: bool | None = None) -> FPREntry:
        entries = self.fp_commands(usage)
        if enabled is not None:
            entries = [entry for entry in entries if entry.enabled == enabled]
        return self._find(entries, description)

    @staticmethod
    def _find(entries: list[FPREntry], description: str) -> FPREntry:
        """The entry with that name, or the newest of those whose name starts with it."""
        matches = [entry for entry in entries if entry.description == description]
        if not matches:
            matches = [
                entry for entry in entries if entry.description.lower().startswith(description.lower())
            ]
        if not matches:
            raise AMError(
                f"no entry named {description!r}; names: {sorted({entry.description for entry in entries})}"
            )
        return max(matches, key=lambda entry: _version_key(entry.description))

    # Changes -----------------------------------------------------------------

    def set_enabled(self, category: str, uuid: str, enabled: bool) -> None:
        """Enable or disable a command through its confirmation page, as the dashboard does."""
        self._post(f"fpr/{category}/{uuid}/delete/", {"enable" if enabled else "disable": "1"})

    def toggle_rule(self, uuid: str) -> None:
        self.page(f"fpr/{FPRULE}/{uuid}/toggle_enabled/")

    def edit_form(self, category: str, uuid: str) -> dict[str, str]:
        """The fields of the edit form of a command, with their current values.

        The dashboard renders the form without the command's tool selected, so the
        tool is filled in from the command's own entry, as a user has to do before saving.
        """
        path = f"fpr/{category}/{uuid}/edit/"
        for form in parse_forms(self.page(path)):
            if "csrfmiddlewaretoken" not in form.fields or "description" not in form.fields:
                continue
            fields = {name: value for name, value in form.fields.items() if name != "csrfmiddlewaretoken"}
            if not fields.get("tool"):
                fields["tool"] = self._tool_option(category, uuid, form.options.get("tool", []))
            return fields
        raise AMError(f"no edit form found at {path}")

    def _tool_option(self, category: str, uuid: str, options: list[tuple[str, str]]) -> str:
        entries = self.id_commands() if category == IDCOMMAND else self.fp_commands()
        tool = next((entry.tool for entry in entries if entry.uuid == uuid), "")
        if not tool:
            # Replaced revisions are not listed any more; their detail page still names the tool.
            match = _DETAIL_TOOL.search(self.page(f"fpr/{category}/{uuid}/"))
            tool = re.sub(r"<[^>]+>", "", match.group(1)).strip() if match else ""
        for value, label in options:
            if label == tool:
                return value
        raise AMError(
            f"the tool {tool!r} of {uuid} is not among the form options {[label for _, label in options]}"
        )

    def submit_edit(self, category: str, uuid: str, fields: dict[str, str]) -> None:
        """Submit the edit form of a command, which creates a new revision replacing the current one."""
        self._post(f"fpr/{category}/{uuid}/edit/", fields)

    def revisions(self, category: str, uuid: str) -> list[str]:
        """The UUIDs listed on the revision history page of a command, newest first."""
        page = self.page(f"fpr/revisions/{category}/{uuid}/")
        start = page.find("<tbody>")
        end = page.find("</tbody>", start)
        return list(dict.fromkeys(match.group("uuid") for match in _UUID_LINK.finditer(page[start:end])))


# HTML list tables ------------------------------------------------------------


def _table_rows(page: str, category: str) -> list[dict[str, str | int | bool]] | None:
    """The rows of the HTML table of a list page, with the payload keys the list methods read.

    None when the page renders no such table. Each cell is read by the header of its
    column, as its text without surrounding whitespace; the parser decodes the
    entities the page escapes.
    """
    for table in lxml.html.fromstring(page).iterfind(".//table"):
        if "datatable" not in (table.get("class") or "").split():
            continue
        headers = [_cell_text(cell) for cell in table.iterfind("thead/tr/th")]
        rows: list[dict[str, str | int | bool]] = []
        for row in table.iterfind("tbody/tr"):
            cells = dict(zip(headers, [_cell_text(cell) for cell in row.iterfind("td")], strict=False))
            try:
                rows.append(_table_row(category, _detail_uuid(row, category), cells))
            except KeyError as error:
                raise AMError(
                    f"the {category} table has no {error} column; its columns: {headers}"
                ) from error
        return rows
    return None


def _table_row(category: str, uuid: str, cells: dict[str, str]) -> dict[str, str | int | bool]:
    """The payload values of a row of an HTML list table, from its cells by column header."""
    row: dict[str, str | int | bool] = {"id": uuid, "enabled": cells["Enabled"] == "Yes"}
    if category == IDCOMMAND:
        row.update(command=cells["Command"], tool=cells["Tool"])
    elif category == FPCOMMAND:
        row.update(description=cells["Description"], tool=cells["Tool"])
    elif category == FPRULE:
        success = _RULE_SUCCESS.fullmatch(cells["Success"])
        if success is None:
            raise AMError(f"the Success cell of the rule {uuid} reads {cells['Success']!r}, not a count")
        format_description, format_version = _rule_format(cells["Format"])
        row.update(
            purpose=_RULE_PURPOSES.get(cells["Purpose"], cells["Purpose"]),
            format=format_description,
            formatVersion=format_version,
            command=cells["Command"],
            successAttempts=int(success["attempts"]),
        )
    return row


def _rule_format(cell: str) -> tuple[str, str]:
    """The description and the version of the format version in the Format cell of a rule."""
    match = _RULE_FORMAT_SUFFIX.search(cell)
    if match is None:
        return cell, ""
    return cell[: match.start()].strip(), match["version"] or ""


def _detail_uuid(row: etree._Element, category: str) -> str:
    """The UUID of the entry of a table row, from the row's link to the detail page of the entry."""
    for link in row.iterfind(".//a"):
        match = _DETAIL_LINK.search(link.get("href") or "")
        if match is not None and match["category"] == category:
            return match["uuid"]
    raise AMError(f"a row of the {category} table links to no {category} detail page")


def _cell_text(cell: etree._Element) -> str:
    return etree.tostring(cell, encoding="unicode", method="text", with_tail=False).strip()
