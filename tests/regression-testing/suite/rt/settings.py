"""Runtime configuration of the suite, read from ``RT_*`` environment variables.

The defaults match the Podman layout of this test directory, where the
``archivematica`` service is provisioned by the Ansible roles and exposes the
dashboard on port 8000 and the Storage Service on port 8001.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parent.parent


def _get(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


@dataclass(frozen=True)
class Settings:
    am_url: str
    am_user: str
    am_password: str
    am_api_key: str
    ss_url: str
    ss_user: str
    ss_api_key: str
    ss_password: str
    atom_url: str
    atom_api_key: str
    atom_service: str
    atom_target_slug: str
    transfer_source_root: str
    compose_command: tuple[str, ...]
    compose_dir: Path
    pipeline_service: str
    pipeline_user: str | None
    shared_directory: str
    mail_dir: str
    log_services: tuple[str, ...]
    evidence_dir: Path
    os_label: str
    poll_interval: float
    unit_timeout: float
    package_timeout: float
    aip_size_cap: int
    keep_extracted_aip: bool

    @classmethod
    def from_env(cls) -> Settings:
        pipeline_user = _get("RT_PIPELINE_USER", "archivematica")
        return cls(
            am_url=_get("RT_AM_URL", "http://localhost:8000").rstrip("/"),
            am_user=_get("RT_AM_USER", "admin"),
            am_password=_get("RT_AM_PASSWORD", "archivematica"),
            am_api_key=_get("RT_AM_API_KEY", "this_is_the_am_api_key"),
            ss_url=_get("RT_SS_URL", "http://localhost:8001").rstrip("/"),
            ss_user=_get("RT_SS_USER", "admin"),
            ss_api_key=_get("RT_SS_API_KEY", "this_is_the_ss_api_key"),
            ss_password=_get("RT_SS_PASSWORD", "archivematica"),
            # The AtoM of the atom shard: its REST API, its Compose service and the
            # description the DIP upload scenarios target (from AtoM's ISAD sample import).
            atom_url=_get("RT_ATOM_URL", "http://localhost:9000").rstrip("/"),
            atom_api_key=_get("RT_ATOM_API_KEY", "this_is_the_atom_dip_upload_api_key"),
            atom_service=_get("RT_ATOM_SERVICE", "atom"),
            atom_target_slug=_get("RT_ATOM_TARGET_SLUG", "example-item"),
            transfer_source_root=_get(
                "RT_TRANSFER_SOURCE_ROOT", "/home/ubuntu/archivematica-sampledata"
            ).rstrip("/"),
            compose_command=tuple(shlex.split(_get("RT_COMPOSE_COMMAND", "podman-compose"))),
            compose_dir=Path(_get("RT_COMPOSE_DIR", str(SUITE_DIR.parent))).expanduser().resolve(),
            pipeline_service=_get("RT_PIPELINE_SERVICE", "archivematica"),
            # "-" runs commands as the default user of the container.
            pipeline_user=None if pipeline_user == "-" else pipeline_user,
            shared_directory=_get("RT_SHARED_DIRECTORY", "/var/archivematica/sharedDirectory").rstrip("/"),
            # Where the pipeline's file email backend writes its messages; empty when the
            # pipeline prints them to its output instead.
            mail_dir=os.environ.get("RT_MAIL_DIR", "/var/archivematica/sharedDirectory/mail").rstrip("/"),
            log_services=tuple(
                service.strip()
                for service in _get("RT_LOG_SERVICES", "archivematica").split(",")
                if service.strip()
            ),
            evidence_dir=Path(_get("RT_EVIDENCE_DIR", str(SUITE_DIR / "evidence"))).expanduser().resolve(),
            os_label=_get("RT_OS_LABEL", "local"),
            poll_interval=float(_get("RT_POLL_INTERVAL", "5")),
            unit_timeout=float(_get("RT_UNIT_TIMEOUT", "1200")),
            package_timeout=float(_get("RT_PACKAGE_TIMEOUT", "300")),
            aip_size_cap=int(_get("RT_AIP_SIZE_CAP", str(256 * 1024 * 1024))),
            # The extracted copy of the AIP doubles the size of the evidence; the archive stays.
            keep_extracted_aip=_get("RT_KEEP_EXTRACTED_AIP", "0").lower() in ("1", "true", "yes"),
        )

    @property
    def processing_config_dir(self) -> str:
        return f"{self.shared_directory}/sharedMicroServiceTasksConfigs/processingMCPConfigs"
