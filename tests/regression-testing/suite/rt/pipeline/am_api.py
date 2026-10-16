"""Client for the dashboard API of an Archivematica pipeline."""

from __future__ import annotations

import base64
import html
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

from rt.pipeline.cookies import PlainCookieJar
from rt.pipeline.packages import AIPBundle, DIPBundle

STATUS_PROCESSING = "PROCESSING"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED = "FAILED"
STATUS_REJECTED = "REJECTED"
STATUS_USER_INPUT = "USER_INPUT"

JOB_COMPLETED = "COMPLETE"
JOB_FAILED = "FAILED"
JOB_AWAITING = "USER_INPUT"
JOB_PROCESSING = "PROCESSING"

LOGIN_PATH = "administration/accounts/login/"

# The standard streams of a task on the dashboard page that shows them: a panel
# title ending in ``(stdout)`` or ``(stderr)`` followed by the output in a ``pre``.
_STREAM_PATTERN = re.compile(
    r'<h3 class="panel-title">[^<]*\((stdout|stderr)\)</h3>.*?<pre>(.*?)</pre>', re.DOTALL
)


class AMError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class UnitStatus:
    type: str
    uuid: str
    name: str
    directory: str
    status: str
    microservice: str
    sip_uuid: str | None
    path: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> UnitStatus:
        sip_uuid = data.get("sip_uuid")
        return cls(
            type=str(data.get("type", "")),
            uuid=str(data.get("uuid", "")),
            name=str(data.get("name", "")),
            directory=str(data.get("directory", "")),
            status=str(data.get("status", "")),
            microservice=str(data.get("microservice", "")),
            sip_uuid=str(sip_uuid) if sip_uuid else None,
            path=str(data.get("path", "")),
        )


@dataclass(frozen=True)
class TaskOutput:
    stdout: str
    stderr: str

    @property
    def last_line(self) -> str:
        """The last non-empty line of stderr, or of stdout when stderr is empty."""
        for stream in (self.stderr, self.stdout):
            lines = [line.strip() for line in stream.splitlines() if line.strip()]
            if lines:
                return lines[-1]
        return ""


@dataclass(frozen=True)
class TaskDetails:
    """A task of a job with the details and standard streams the dashboard shows for it."""

    uuid: str
    job_name: str
    file_uuid: str
    file_name: str
    exit_code: int | None
    stdout: str
    stderr: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UnitRun:
    """A transfer started by a scenario and everything the pipeline did with it."""

    transfer_uuid: str
    name: str
    transfer_type: str
    source_path: str
    processing_config: str
    transfer: UnitStatus | None = None
    sip: UnitStatus | None = None
    jobs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    aip: AIPBundle | None = None
    dip: DIPBundle | None = None
    task_details: dict[str, list[TaskDetails]] = field(default_factory=dict)

    @property
    def sip_uuid(self) -> str | None:
        if self.sip is not None:
            return self.sip.uuid
        if self.transfer is not None and self.transfer.sip_uuid not in (None, "BACKLOG"):
            return self.transfer.sip_uuid
        return None

    @property
    def final_status(self) -> str:
        if self.sip is not None:
            return self.sip.status
        if self.transfer is not None:
            return self.transfer.status
        return ""

    @property
    def current_microservice(self) -> str:
        unit = self.sip if self.sip is not None else self.transfer
        return unit.microservice if unit is not None else ""

    @property
    def unit_uuids(self) -> list[str]:
        uuids = [self.transfer_uuid] if self.transfer_uuid else []
        if self.sip_uuid:
            uuids.append(self.sip_uuid)
        return uuids

    def all_jobs(self) -> list[dict[str, Any]]:
        return [job for jobs in self.jobs.values() for job in jobs]

    def jobs_named(self, name: str) -> list[dict[str, Any]]:
        return [job for job in self.all_jobs() if job.get("name") == name]

    def describe(self) -> str:
        parts = [f"transfer {self.transfer_uuid}"] if self.transfer_uuid else []
        if self.transfer is not None:
            parts.append(f"status {self.transfer.status} at {self.transfer.microservice!r}")
        if self.sip is not None:
            parts.append(f"SIP {self.sip.uuid} status {self.sip.status} at {self.sip.microservice!r}")
        return "; ".join(parts)


class AMClient:
    def __init__(
        self, base_url: str, username: str, api_key: str, password: str = "", timeout: float = 60
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.api_key = api_key
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"ApiKey {username}:{api_key}"
        self.web: requests.Session | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def get(self, path: str, **params: str) -> requests.Response:
        response = self.session.get(self._url(path), params=params, timeout=self.timeout)
        if not response.ok:
            raise AMError(
                f"GET {path} returned {response.status_code}: {response.text[:300]}", response.status_code
            )
        return response

    def post_json(self, path: str, payload: dict[str, Any]) -> requests.Response:
        response = self.session.post(self._url(path), json=payload, timeout=self.timeout)
        if not response.ok:
            raise AMError(
                f"POST {path} returned {response.status_code}: {response.text[:300]}", response.status_code
            )
        return response

    def version(self) -> str:
        response = self.get("api/processing-configuration/")
        return response.headers.get("X-Archivematica-Version", "")

    def pipeline_uuid(self) -> str:
        response = self.get("api/processing-configuration/")
        return response.headers.get("X-Archivematica-ID", "")

    def processing_configuration_names(self) -> list[str]:
        data = self.get("api/processing-configuration/").json()
        return [str(name) for name in data.get("processing_configurations", [])]

    def processing_configuration(self, name: str) -> str:
        return self.get(f"api/processing-configuration/{name}").text

    def start_transfer(
        self,
        *,
        name: str,
        path: str,
        transfer_type: str = "standard",
        accession: str = "",
        access_system_id: str = "",
        processing_config: str | None = None,
        auto_approve: bool = True,
        metadata_set_id: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "name": name,
            "type": transfer_type,
            "path": base64.b64encode(path.encode("utf-8")).decode("ascii"),
            "accession": accession,
            "access_system_id": access_system_id,
            "auto_approve": auto_approve,
        }
        if processing_config is not None:
            payload["processing_config"] = processing_config
        if metadata_set_id is not None:
            payload["metadata_set_id"] = metadata_set_id
        data = self.post_json("api/v2beta/package", payload).json()
        transfer_uuid = data.get("id")
        if not isinstance(transfer_uuid, str) or not transfer_uuid:
            raise AMError(f"the package endpoint did not return a transfer UUID: {data}")
        return transfer_uuid

    def transfer_status(self, transfer_uuid: str) -> UnitStatus:
        return UnitStatus.from_json(self.get(f"api/transfer/status/{transfer_uuid}").json())

    def ingest_status(self, sip_uuid: str) -> UnitStatus:
        return UnitStatus.from_json(self.get(f"api/ingest/status/{sip_uuid}").json())

    def unit_jobs(self, unit_uuid: str, detailed: bool = True) -> list[dict[str, Any]]:
        params = {"detailed": "1"} if detailed else {}
        data = self.get(f"api/v2beta/jobs/{unit_uuid}", **params).json()
        return [dict(job) for job in data] if isinstance(data, list) else []

    def settled_jobs(self, unit_uuid: str, timeout: float, interval: float) -> list[dict[str, Any]]:
        """The jobs of a unit once none of them is processing, or the last snapshot when the timeout passes."""
        deadline = time.monotonic() + timeout
        while True:
            jobs = self.unit_jobs(unit_uuid)
            processing = any(job.get("status") == JOB_PROCESSING for job in jobs)
            if not processing or time.monotonic() >= deadline:
                return jobs
            time.sleep(interval)

    def task(self, task_uuid: str) -> dict[str, Any]:
        return dict(self.get(f"api/v2beta/task/{task_uuid}").json())

    def web_session(self) -> requests.Session:
        """A session logged in through the dashboard form, for the pages outside the API."""
        if self.web is not None:
            return self.web
        session = requests.Session()
        session.cookies = PlainCookieJar()
        login_url = self._url(LOGIN_PATH)
        form = session.get(login_url, timeout=self.timeout)
        token = session.cookies.get("csrftoken")
        if not form.ok or not token:
            raise AMError(
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
            raise AMError(
                f"the dashboard did not accept the login of {self.username!r} ({response.status_code})",
                response.status_code,
            )
        self.web = session
        return session

    def task_details(self, task_uuid: str, job_name: str) -> TaskDetails:
        """The details of a task from the API together with its standard streams."""
        details = self.task(task_uuid)
        output = self.task_output(task_uuid)
        exit_code = details.get("exit_code")
        return TaskDetails(
            uuid=task_uuid,
            job_name=job_name,
            file_uuid=str(details.get("file_uuid") or ""),
            file_name=str(details.get("file_name") or ""),
            exit_code=int(exit_code) if exit_code is not None else None,
            stdout=output.stdout,
            stderr=output.stderr,
        )

    def task_output(self, task_uuid: str) -> TaskOutput:
        """The standard streams of a task, read from the dashboard page that shows them."""
        path = f"task/{task_uuid}/"
        response = self.web_session().get(self._url(path), timeout=self.timeout)
        if not response.ok:
            raise AMError(f"GET {path} returned {response.status_code}", response.status_code)
        if LOGIN_PATH in response.url:
            raise AMError(f"GET {path} redirected to the login page")
        streams = {"stdout": "", "stderr": ""}
        for stream, content in _STREAM_PATTERN.findall(response.text):
            streams[str(stream)] = html.unescape(str(content))
        return TaskOutput(stdout=streams["stdout"], stderr=streams["stderr"])

    def waiting_for_user_input(self) -> list[dict[str, Any]]:
        data = self.get("api/ingest/waiting").json()
        return [dict(unit) for unit in data.get("results", [])]

    def wait_for_unit(self, run: UnitRun, timeout: float, interval: float) -> UnitRun:
        """Poll the transfer, and the SIP it creates, until the pipeline stops working on them.

        A run without a transfer, such as a re-ingested AIP, is followed through its SIP alone.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if run.transfer_uuid:
                try:
                    run.transfer = self.transfer_status(run.transfer_uuid)
                except AMError as err:
                    # The transfer row appears a moment after the package call returns.
                    if err.status_code == 400:
                        time.sleep(interval)
                        continue
                    raise
                if run.transfer.status == STATUS_PROCESSING:
                    time.sleep(interval)
                    continue
                if run.transfer.status != STATUS_COMPLETE:
                    return run
                sip_uuid = run.transfer.sip_uuid
                if not sip_uuid or sip_uuid == "BACKLOG":
                    return run
            else:
                sip_uuid = run.sip_uuid
                if not sip_uuid:
                    raise AMError("a run without a transfer needs the UUID of its SIP")
            try:
                run.sip = self.ingest_status(sip_uuid)
            except AMError as err:
                if err.status_code == 400:
                    time.sleep(interval)
                    continue
                raise
            if run.sip.status == STATUS_PROCESSING:
                time.sleep(interval)
                continue
            return run
        raise AMError(f"timed out after {timeout:.0f}s waiting for {run.describe()}")
