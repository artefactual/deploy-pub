"""Client for the Storage Service API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

from rt.pipeline.cookies import PlainCookieJar

PACKAGE_UPLOADED = "UPLOADED"
LOGIN_PATH = "login/"
CSRF_COOKIE = "storageapi_csrfid"


class SSError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SSClient:
    def __init__(
        self, base_url: str, username: str, api_key: str, password: str = "", timeout: float = 120
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"ApiKey {username}:{api_key}"
        self.web: requests.Session | None = None

    def web_session(self) -> requests.Session:
        """A session logged in through the Storage Service form, for the pages outside the API."""
        if self.web is not None:
            return self.web
        session = requests.Session()
        session.cookies = PlainCookieJar()
        login_url = self._url(LOGIN_PATH)
        form = session.get(login_url, timeout=self.timeout)
        token = session.cookies.get(CSRF_COOKIE)
        if not form.ok or not token:
            raise SSError(
                f"GET {LOGIN_PATH} returned {form.status_code} without a CSRF token", form.status_code
            )
        response = session.post(
            login_url,
            data={
                "csrfmiddlewaretoken": token,
                "username": self.username,
                "password": self.password,
                "next": "/",
            },
            headers={"Referer": login_url},
            timeout=self.timeout,
            allow_redirects=False,
        )
        if response.status_code != 302:
            raise SSError(
                f"the Storage Service did not accept the login of {self.username!r} ({response.status_code})",
                response.status_code,
            )
        self.web = session
        return session

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def get(self, path: str, params: dict[str, str] | None = None, stream: bool = False) -> requests.Response:
        response = self.session.get(self._url(path), params=params, timeout=self.timeout, stream=stream)
        if not response.ok:
            raise SSError(
                f"GET {path} returned {response.status_code}: {response.text[:300]}", response.status_code
            )
        return response

    def post_json(self, path: str, payload: dict[str, Any]) -> requests.Response:
        response = self.session.post(self._url(path), json=payload, timeout=self.timeout)
        if not response.ok:
            raise SSError(
                f"POST {path} returned {response.status_code}: {response.text[:300]}", response.status_code
            )
        return response

    def pipelines(self) -> list[dict[str, Any]]:
        return [dict(obj) for obj in self.get("api/v2/pipeline/").json().get("objects", [])]

    def spaces(self) -> list[dict[str, Any]]:
        return [dict(obj) for obj in self.get("api/v2/space/").json().get("objects", [])]

    def locations(self, **params: str) -> list[dict[str, Any]]:
        return [dict(obj) for obj in self.get("api/v2/location/", params).json().get("objects", [])]

    def request_reingest(
        self, uuid: str, pipeline_uuid: str, reingest_type: str, processing_config: str
    ) -> dict[str, Any]:
        """Send an AIP back to a pipeline for re-ingest; the SIP then waits for approval there."""
        payload = {
            "pipeline": pipeline_uuid,
            "reingest_type": reingest_type,
            "processing_config": processing_config,
        }
        return dict(self.post_json(f"api/v2/file/{uuid}/reingest/", payload).json())

    def packages(self, **params: str) -> list[dict[str, Any]]:
        return [dict(obj) for obj in self.get("api/v2/file/", params).json().get("objects", [])]

    def package(self, uuid: str) -> dict[str, Any]:
        return dict(self.get(f"api/v2/file/{uuid}/").json())

    def wait_for_package(
        self, uuid: str, timeout: float, interval: float, status: str = PACKAGE_UPLOADED
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                last = self.package(uuid)
            except SSError as err:
                if err.status_code != 404:
                    raise
            else:
                if last.get("status") == status:
                    return last
            time.sleep(interval)
        raise SSError(f"timed out after {timeout:.0f}s waiting for package {uuid} to be {status}: {last}")

    def _download(self, path: str, dest: Path, params: dict[str, str] | None = None) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self.get(path, params, stream=True) as response:
            with dest.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    handle.write(chunk)
        return dest

    def download(self, uuid: str, dest: Path) -> Path:
        return self._download(f"api/v2/file/{uuid}/download/", dest)

    def extract_file(self, uuid: str, relative_path: str, dest: Path) -> Path:
        return self._download(
            f"api/v2/file/{uuid}/extract_file/", dest, {"relative_path_to_file": relative_path}
        )

    def pointer_file(self, uuid: str, dest: Path) -> Path:
        return self._download(f"api/v2/file/{uuid}/pointer_file/", dest)

    def check_fixity(self, uuid: str) -> dict[str, Any]:
        return dict(self.get(f"api/v2/file/{uuid}/check_fixity/").json())
