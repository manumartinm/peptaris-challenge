"""Installed package version.

Release Please owns ``pyproject.toml``. Runtime callers read the installed
distribution metadata so CLI, API, and wheel stay on one number.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "peptaris-route-agent"
UNKNOWN_VERSION = "0+unknown"


def package_version() -> str:
    """Return the installed version, or ``0+unknown`` outside an install."""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return UNKNOWN_VERSION
