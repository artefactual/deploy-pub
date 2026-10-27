"""Pages and forms of the dashboard and the Storage Service outside their APIs.

Both render their administration as plain Django forms; this module reads them
with the values a browser would submit and posts them back through a logged-in
web session, which is what the scenarios use to prepare and restore state
without a browser.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import requests

from rt.pipeline.am_api import AMClient
from rt.pipeline.ss_api import CSRF_COOKIES, SSClient

FieldValue = str | list[str]


class WebError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Form:
    action: str
    fields: dict[str, str] = field(default_factory=dict)
    options: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    # The submit buttons as (name, value) pairs; a browser sends the pair of the one clicked.
    buttons: list[tuple[str, str]] = field(default_factory=list)


class _FormParser(HTMLParser):
    """Collects the forms of a page with the current value of every field, as a browser would submit them."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[Form] = []
        self._form: Form | None = None
        self._select: str | None = None
        self._selected: bool = False
        self._first_option: str | None = None
        self._option: str | None = None
        self._textarea: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "form":
            self._form = Form(action=attributes.get("action") or "")
            self.forms.append(self._form)
            return
        if self._form is None:
            return
        if tag == "input":
            name = attributes.get("name")
            kind = (attributes.get("type") or "text").lower()
            if name and kind == "submit":
                self._form.buttons.append((name, attributes.get("value") or ""))
            if not name or kind in ("submit", "button", "reset", "image", "file"):
                return
            if kind in ("checkbox", "radio"):
                if "checked" in attributes:
                    self._form.fields[name] = attributes.get("value") or "on"
                return
            self._form.fields[name] = attributes.get("value") or ""
        elif tag == "select":
            self._select = attributes.get("name")
            self._selected = False
            self._first_option = None
            if self._select:
                self._form.options[self._select] = []
        elif tag == "option" and self._select:
            value = attributes.get("value") or ""
            if self._first_option is None:
                self._first_option = value
            if "selected" in attributes:
                self._form.fields[self._select] = value
                self._selected = True
            self._option = value
            self._text = []
        elif tag == "textarea":
            self._textarea = attributes.get("name")
            self._text = []
        elif tag == "button":
            name = attributes.get("name")
            if name and (attributes.get("type") or "submit").lower() == "submit":
                self._form.buttons.append((name, attributes.get("value") or ""))

    def handle_endtag(self, tag: str) -> None:
        if self._form is None:
            return
        if tag == "form":
            self._form = None
        elif tag == "option" and self._select and self._option is not None:
            self._form.options[self._select].append((self._option, "".join(self._text).strip()))
            self._option = None
        elif tag == "select" and self._select:
            if not self._selected:
                self._form.fields[self._select] = self._first_option or ""
            self._select = None
        elif tag == "textarea" and self._textarea:
            self._form.fields[self._textarea] = "".join(self._text)
            self._textarea = None

    def handle_data(self, data: str) -> None:
        if self._textarea is not None or self._option is not None:
            self._text.append(data)


def parse_forms(page: str) -> list[Form]:
    parser = _FormParser()
    parser.feed(page)
    return parser.forms


def embedded_json(page: str, script_id: str) -> object | None:
    """The JSON a page embeds in a script element of that id, as Django's json_script does; None without one."""
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>', page, re.DOTALL
    )
    if match is None:
        return None
    payload: object = json.loads(match.group(1))
    return payload


class Site:
    """The pages of a Django site outside its API, read and submitted as the logged-in user."""

    # The cookies that may hold the CSRF token, looked up in this order.
    csrf_cookies: tuple[str, ...] = ("csrftoken",)
    # A response redirected to a URL containing this is a request the session was not logged in for.
    login_marker = "/login"

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def session(self) -> requests.Session:
        raise NotImplementedError

    def url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def page(self, path: str) -> str:
        response = self.session().get(self.url(path), timeout=self.timeout)
        if not response.ok:
            raise WebError(f"GET {path} returned {response.status_code}", response.status_code)
        if self.login_marker in response.url:
            raise WebError(f"GET {path} redirected to the login page")
        return response.text

    def form(self, path: str, having: str) -> Form:
        """The form of a page that has a field of that name, with the current values of its fields."""
        for form in parse_forms(self.page(path)):
            if having in form.fields or having in form.options:
                form.fields.pop("csrfmiddlewaretoken", None)
                return form
        raise WebError(f"no form with a {having!r} field at {path}")

    def post(
        self, path: str, fields: Mapping[str, FieldValue], accepted: tuple[int, ...] = (301, 302)
    ) -> requests.Response:
        """Submit a form; the site answers a redirect when it accepted it, unless told otherwise."""
        session = self.session()
        token = next(filter(None, (session.cookies.get(name) for name in self.csrf_cookies)), "")
        url = self.url(path)
        data: dict[str, FieldValue] = {**fields, "csrfmiddlewaretoken": token}
        response = session.post(
            url,
            data=data,
            headers={"Referer": url},
            timeout=self.timeout,
            allow_redirects=False,
        )
        if response.status_code not in accepted:
            raise WebError(
                f"POST {path} returned {response.status_code}: {_errors(response.text)}", response.status_code
            )
        return response

    def download(self, path: str, dest: Path) -> Path:
        response = self.session().get(self.url(path), timeout=self.timeout)
        if not response.ok:
            raise WebError(f"GET {path} returned {response.status_code}", response.status_code)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(response.content)
        return dest


class Dashboard(Site):
    """The dashboard's own pages, read and submitted as the logged-in user."""

    login_marker = "accounts/login"

    def __init__(self, am: AMClient) -> None:
        super().__init__(am.base_url, am.timeout)
        self.am = am

    def session(self) -> requests.Session:
        return self.am.web_session()


class StorageSite(Site):
    """The Storage Service's own pages, read and submitted as the logged-in user."""

    csrf_cookies = CSRF_COOKIES
    login_marker = "/login/"

    def __init__(self, ss: SSClient) -> None:
        super().__init__(ss.base_url, ss.timeout)
        self.ss = ss

    def session(self) -> requests.Session:
        return self.ss.web_session()


def _errors(page: str) -> str:
    """The error messages of a rendered form, as the dashboard shows them."""
    found = re.findall(r'class="errorlist[^"]*"[^>]*>(.*?)</ul>', page, re.DOTALL)
    text = " ".join(re.sub(r"<[^>]+>", " ", item) for item in found)
    return re.sub(r"\s+", " ", text).strip()[:300] or page[-300:]
