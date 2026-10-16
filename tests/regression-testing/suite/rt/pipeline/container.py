"""Access to the files and logs of the pipeline container through Compose."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from rt.settings import Settings

_READ_ZIP_MEMBER = (
    "import sys, zipfile\nsys.stdout.buffer.write(zipfile.ZipFile(sys.argv[1]).read(sys.argv[2]))\n"
)


class ContainerError(Exception):
    pass


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _compose(self, *args: str) -> list[str]:
        return [*self.settings.compose_command, *args]

    def exec(
        self,
        args: Sequence[str],
        *,
        service: str | None = None,
        user: str | None = None,
        input: bytes | None = None,
        check: bool = True,
        timeout: float = 300,
    ) -> subprocess.CompletedProcess[bytes]:
        command = self._compose("exec", "-T")
        effective_user = self.settings.pipeline_user if user is None else user
        if effective_user:
            command += ["--user", effective_user]
        command += [service or self.settings.pipeline_service, *args]
        result = subprocess.run(
            command,
            cwd=self.settings.compose_dir,
            input=input,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if check and result.returncode != 0:
            raise ContainerError(
                f"{shlex.join(command)} exited with {result.returncode}: "
                f"{result.stderr.decode('utf-8', 'replace')[-500:]}"
            )
        return result

    def read_bytes(self, path: str) -> bytes:
        return self.exec(["cat", path]).stdout

    def read_text(self, path: str) -> str:
        return self.read_bytes(path).decode("utf-8")

    def write_text(self, path: str, content: str, user: str | None = None) -> None:
        self.exec(["sh", "-c", f"cat > {shlex.quote(path)}"], user=user, input=content.encode("utf-8"))

    def exists(self, path: str) -> bool:
        return self.exec(["test", "-e", path], check=False).returncode == 0

    def listdir(self, path: str) -> list[str]:
        output = self.exec(["ls", "-1A", path]).stdout.decode("utf-8")
        return [line for line in output.splitlines() if line]

    def read_zip_member(self, zip_path: str, member: str) -> bytes:
        return self.exec(["python3", "-c", _READ_ZIP_MEMBER, zip_path, member]).stdout

    def compose_output(self, since: datetime) -> str:
        """The output of the logged services since an instant, as Compose shows it."""
        command = self._compose(
            "logs", "--no-color", "--since", str(int(since.timestamp())), *self.settings.log_services
        )
        result = subprocess.run(
            command, cwd=self.settings.compose_dir, capture_output=True, timeout=300, check=False
        )
        return result.stdout.decode("utf-8", "replace")

    def log_slice(self, since: datetime, until: datetime, dest: Path) -> list[str]:
        """Save the journal and the Compose output between two instants; returns warnings.

        The Compose output is saved only when the services wrote something to it:
        a container running systemd keeps its service logs in the journal.
        """
        warnings: list[str] = []
        dest.mkdir(parents=True, exist_ok=True)
        since_epoch = f"@{int(since.timestamp())}"
        until_epoch = f"@{int(until.timestamp()) + 1}"
        journal = self.exec(
            ["journalctl", "--no-pager", "--since", since_epoch, "--until", until_epoch],
            user="root",
            check=False,
        )
        if journal.returncode == 0:
            (dest / "journal.log").write_bytes(journal.stdout)
        else:
            warnings.append(f"journalctl unavailable: {journal.stderr.decode('utf-8', 'replace')[-200:]}")
        command = self._compose(
            "logs",
            "--no-color",
            "--since",
            str(int(since.timestamp())),
            "--until",
            str(int(until.timestamp()) + 1),
            *self.settings.log_services,
        )
        result = subprocess.run(
            command, cwd=self.settings.compose_dir, capture_output=True, timeout=300, check=False
        )
        if result.returncode == 0:
            if result.stdout.strip():
                (dest / "compose.log").write_bytes(result.stdout)
        else:
            warnings.append(f"compose logs unavailable: {result.stderr.decode('utf-8', 'replace')[-200:]}")
        return warnings
