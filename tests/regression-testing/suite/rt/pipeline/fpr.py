"""The Preservation planning pages of the dashboard: commands, rules, enabling, editing and revisions.

The dashboard has no API for the Format Policy Registry, so this module reads the
JSON payload the list pages embed for their tables and submits the same forms a
user would: the enable/disable confirmation and the edit form of a command.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any

import requests

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
_VERSION = re.compile(r"(\d+)")
_DETAIL_TOOL = re.compile(r"<dt>\s*Tool\s*</dt>\s*<dd>(.*?)</dd>", re.DOTALL)
_DETAIL_COMMAND = re.compile(r"<dt>\s*Command\s*</dt>\s*<dd><pre>(.*?)</pre></dd>", re.DOTALL)


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
        """The rows of the table of a list page."""
        page = self.page(path or f"fpr/{category}/")
        for match in _PAYLOAD.finditer(page):
            if match.group("category") == category:
                data = json.loads(match.group("json"))
                rows = data.get("rows", data) if isinstance(data, dict) else data
                return [dict(row) for row in rows]
        raise AMError(f"the page {path or category} has no {category} table payload")

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
