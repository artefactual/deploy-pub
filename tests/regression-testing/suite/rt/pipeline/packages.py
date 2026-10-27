"""Fetching stored packages from the Storage Service into an evidence bundle."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import py7zr

if TYPE_CHECKING:
    from rt.pipeline.ss_api import SSClient

COMPRESSED_SUFFIXES = (".7z", ".tar.gz", ".tar.bz2", ".tgz", ".zip")


@dataclass
class AIPBundle:
    uuid: str
    package: dict[str, Any]
    archive: Path | None
    root: Path | None
    mets: Path
    pointer: Path | None

    @property
    def basename(self) -> str:
        return package_basename(self.package)

    @property
    def compressed(self) -> bool:
        return package_is_compressed(self.package)


@dataclass
class DIPBundle:
    uuid: str
    package: dict[str, Any]
    archive: Path | None
    root: Path | None

    @property
    def basename(self) -> str:
        return package_basename(self.package)

    def objects(self) -> list[Path]:
        """The files under ``objects/`` of a downloaded DIP, relative to its root."""
        if self.root is None or not (self.root / "objects").is_dir():
            return []
        return sorted(
            path.relative_to(self.root) for path in (self.root / "objects").rglob("*") if path.is_file()
        )


def package_basename(package: dict[str, Any]) -> str:
    name = Path(str(package.get("current_path", ""))).name
    for suffix in COMPRESSED_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def package_is_compressed(package: dict[str, Any]) -> bool:
    name = Path(str(package.get("current_path", ""))).name
    return name.endswith(COMPRESSED_SUFFIXES)


def extract_7z(archive: Path, dest_dir: Path) -> None:
    """Extract a 7z archive with the 7-Zip command line tool, or py7zr when it is not installed.

    The pipeline compresses AIPs with 7-Zip, whose archives use coder options
    that py7zr does not always accept, so the command line tool is preferred.
    """
    for executable in ("7z", "7zz", "7za"):
        path = shutil.which(executable)
        if path is None:
            continue
        subprocess.run(
            [path, "x", "-bd", "-y", f"-o{dest_dir}", str(archive)],
            check=True,
            capture_output=True,
            timeout=1800,
        )
        return
    with py7zr.SevenZipFile(archive, mode="r") as sevenzip:
        sevenzip.extractall(path=dest_dir)


def extract_tar(archive: Path, dest_dir: Path) -> None:
    with tarfile.open(archive) as tar:
        tar.extractall(dest_dir, filter="data")


def _holds(directory: Path, pattern: str) -> bool:
    """Whether ``directory`` is a directory with a path that matches the glob ``pattern``."""
    return directory.is_dir() and any(directory.glob(pattern))


def extracted_root(dest_dir: Path, basename: str, pattern: str) -> Path | None:
    """The directory of a package extracted into ``dest_dir``: the one that holds ``pattern``.

    ``pattern`` is a glob relative to that directory. The archive of a package
    holds one top-level directory, usually named after the stored package
    (``basename``), which is tried first. The other directories under
    ``dest_dir`` are searched when it does not hold ``pattern``, because the
    stored name can differ from the directory inside the archive: Storage
    Service 0.24 cuts the name of a re-ingested AIP at its last dot, so
    ``rt-13.7z`` holds ``rt-13.8-<date>-<uuid>/``. Returns None when no
    directory holds ``pattern``, and raises RuntimeError when several do,
    since only one of them can come from the archive.
    """
    named = dest_dir / basename
    if _holds(named, pattern):
        return named
    roots = [directory for directory in sorted(dest_dir.iterdir()) if _holds(directory, pattern)]
    if len(roots) > 1:
        names = ", ".join(directory.name for directory in roots)
        raise RuntimeError(f"several directories under {dest_dir} hold {pattern}: {names}")
    return roots[0] if roots else None


def find_dip(ss: SSClient, aip_uuid: str) -> dict[str, Any] | None:
    """The DIP that the Storage Service relates to an AIP, or the one stored under the same UUID."""
    for package in ss.packages(package_type="DIP", related_packages__uuid=aip_uuid):
        return package
    # The API pages its listing; limit=0 asks for every DIP, up to its maximum.
    for package in ss.packages(package_type="DIP", limit="0"):
        if aip_uuid in str(package.get("current_path", "")):
            return package
    return None


def fetch_dip(
    ss: SSClient,
    package: dict[str, Any],
    dest_dir: Path,
    *,
    size_cap: int,
    timeout: float,
    interval: float,
) -> DIPBundle:
    """Download a stored DIP once it is uploaded; the Storage Service serves it as a tar archive."""
    uuid = str(package["uuid"])
    package = ss.wait_for_package(uuid, timeout=timeout, interval=interval)
    dest_dir.mkdir(parents=True, exist_ok=True)
    basename = package_basename(package)
    archive: Path | None = None
    root: Path | None = None
    if int(package.get("size") or 0) <= size_cap:
        archive = ss.download(uuid, dest_dir / f"{basename}.tar")
        extract_tar(archive, dest_dir)
        # A DIP holds a copy of the METS of its AIP, named after the AIP's UUID.
        mets_pattern = "METS.*.xml"
        root = extracted_root(dest_dir, basename, mets_pattern)
        if root is None:
            raise FileNotFoundError(f"the extracted DIP has no METS file at {dest_dir}/*/{mets_pattern}")
    return DIPBundle(uuid=uuid, package=package, archive=archive, root=root)


def fetch_aip(
    ss: SSClient,
    uuid: str,
    dest_dir: Path,
    *,
    size_cap: int,
    timeout: float,
    interval: float,
) -> AIPBundle:
    """Download the AIP (or only its METS when it is too large) once it is stored."""
    package = ss.wait_for_package(uuid, timeout=timeout, interval=interval)
    dest_dir.mkdir(parents=True, exist_ok=True)
    basename = package_basename(package)
    mets_name = f"METS.{uuid}.xml"
    size = int(package.get("size") or 0)
    archive: Path | None = None
    root: Path | None = None
    if (
        package_is_compressed(package)
        and str(package.get("current_path", "")).endswith(".7z")
        and size <= size_cap
    ):
        archive = ss.download(uuid, dest_dir / f"{basename}.7z")
        extract_7z(archive, dest_dir)
        root = extracted_root(dest_dir, basename, f"data/{mets_name}")
        if root is None:
            raise FileNotFoundError(f"the extracted AIP has no METS file at {dest_dir}/*/data/{mets_name}")
        mets = root / "data" / mets_name
    else:
        # The archive is not at hand to look its directory up, so the path
        # assumes the directory is named like the stored package, which is not
        # the case for a compressed AIP re-ingested by Storage Service 0.24
        # (see extracted_root).
        mets = ss.extract_file(uuid, f"{basename}/data/{mets_name}", dest_dir / mets_name)
    pointer: Path | None = None
    if package_is_compressed(package):
        try:
            pointer = ss.pointer_file(uuid, dest_dir / f"pointer.{uuid}.xml")
        except Exception:  # noqa: BLE001 - a missing pointer file is reported by the criteria
            pointer = None
    return AIPBundle(uuid=uuid, package=package, archive=archive, root=root, mets=mets, pointer=pointer)
