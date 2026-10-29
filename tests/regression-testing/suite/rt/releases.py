"""Matching the Archivematica version a pipeline reports against release prefixes."""

from __future__ import annotations

from collections.abc import Sequence


def matches(version: str, releases: Sequence[str]) -> bool:
    """Whether a version such as ``1.19.0`` is one of the releases, given as prefixes.

    A release matches when it equals the version or the version starts with the
    release and a dot: ``1.19`` matches ``1.19.0`` and ``1.19.1`` but not
    ``1.190.0``. No releases at all match every version.
    """
    return not releases or any(
        version == release or version.startswith(f"{release}.") for release in releases
    )
