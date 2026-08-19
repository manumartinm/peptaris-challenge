"""Validate that built wheel and sdist contain the packaged runtime."""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
from collections.abc import Iterable
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

WHEEL_PATHS = (
    "route_agent/version.py",
    "route_agent/resources/extracted_families.json",
    "route_agent/resources/molecular_fragments.json",
    "route_agent/resources/schema.json",
    "route_agent/resources/request_schema.json",
    "route_agent/resources/score.py",
    "route_agent/resources/ApexChem_templates_and_targets.xlsx",
    "route_agent_cli/app.py",
    "route_agent_api/main.py",
)

SDIST_PATHS = (
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "src/route_agent/version.py",
    "src/route_agent_cli/app.py",
    "src/route_agent_api/main.py",
    "scripts/dist_smoke.sh",
    "scripts/inspect_dist.py",
)


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _missing(required: Iterable[str], names: set[str]) -> list[str]:
    return [item for item in required if not any(name.endswith(item) for name in names)]


def inspect_wheel(path: Path, expected_version: str | None) -> str:
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = _missing(WHEEL_PATHS, names)
        if missing:
            _fail(f"{path.name} is missing {missing}")
        metadata_name = next(
            (name for name in names if name.endswith(".dist-info/METADATA")),
            None,
        )
        if metadata_name is None:
            _fail(f"{path.name} has no METADATA")
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
    dist_name = metadata.get("Name", "")
    version = metadata.get("Version", "")
    license_expr = metadata.get("License-Expression", "")
    if dist_name != "peptaris-route-agent":
        _fail(f"{path.name} name {dist_name!r} is not peptaris-route-agent")
    if expected_version is not None and version != expected_version:
        _fail(f"{path.name} version {version!r} != {expected_version!r}")
    if license_expr != "LicenseRef-Proprietary":
        _fail(f"{path.name} license {license_expr!r} is not LicenseRef-Proprietary")
    print(f"wheel ok {path.name} version={version}")
    return version


def inspect_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        names = set(member.name for member in archive.getmembers())
    missing = _missing(SDIST_PATHS, names)
    if missing:
        _fail(f"{path.name} is missing {missing}")
    print(f"sdist ok {path.name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dist_dir",
        nargs="?",
        default="dist",
        type=Path,
        help="Directory containing wheel and sdist",
    )
    parser.add_argument(
        "--version",
        default=os.environ.get("EXPECT_VERSION"),
        help="Require this version in wheel metadata",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dist_dir = args.dist_dir
    wheels = sorted(dist_dir.glob("peptaris_route_agent-*.whl"))
    sdists = sorted(dist_dir.glob("peptaris_route_agent-*.tar.gz")) + sorted(
        dist_dir.glob("peptaris-route-agent-*.tar.gz")
    )
    if len(wheels) != 1:
        _fail(f"expected one wheel in {dist_dir}, found {len(wheels)}")
    if len(sdists) != 1:
        _fail(f"expected one sdist in {dist_dir}, found {len(sdists)}")
    inspect_wheel(wheels[0], args.version)
    inspect_sdist(sdists[0])


if __name__ == "__main__":
    main()
