"""Resolve packaged resources and user-writable XDG locations.

Read-only corpus files ship inside the wheel and are opened through
``importlib.resources``. Cache, memory, and config live under the XDG
directories from ``platformdirs`` so a pipx install does not need the
git checkout. ``ROUTE_AGENT_*`` environment variables still win.
"""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

APP_NAME = "route-agent"
APP_AUTHOR = "peptaris"

_RESOURCE_FILES = (
    "extracted_families.json",
    "molecular_fragments.json",
    "ApexChem_templates_and_targets.xlsx",
    "schema.json",
    "request_schema.json",
    "score.py",
)


def development_root() -> Path | None:
    """Return the repo root when running from a source checkout, else None."""
    here = Path(__file__).resolve()
    if here.parents[1].name == "src":
        return here.parents[2]
    return None


def user_cache_root() -> Path:
    override = os.environ.get("ROUTE_AGENT_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_cache_dir(APP_NAME, APP_AUTHOR))


def user_data_root() -> Path:
    override = os.environ.get("ROUTE_AGENT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def user_config_root() -> Path:
    override = os.environ.get("ROUTE_AGENT_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def default_research_root() -> Path:
    """Writable sandbox root (cache, memory, workspace, copied skills)."""
    override = os.environ.get("ROUTE_AGENT_RESEARCH_ROOT")
    if override:
        return Path(override).expanduser()
    checkout = development_root()
    if checkout is not None:
        return checkout / "research"
    return user_cache_root()


def default_env_files() -> tuple[Path, ...]:
    """``.env`` search order: XDG config, then a development checkout."""
    files: list[Path] = []
    explicit = os.environ.get("ROUTE_AGENT_ENV_FILE")
    if explicit:
        files.append(Path(explicit).expanduser())
    files.append(user_config_root() / ".env")
    checkout = development_root()
    if checkout is not None:
        files.append(checkout / ".env")
    return tuple(files)


def packaged_resource_path(name: str) -> Path:
    """Return a filesystem path to a packaged resource.

    Unpacked wheels expose a real file. Zip installs are copied once into
    the user cache so callers can keep using ``Path.read_text``.
    """
    if name not in _RESOURCE_FILES:
        raise FileNotFoundError(f"unknown packaged resource: {name}")
    traversable = resources.files("route_agent.resources").joinpath(name)
    on_disk = _traversable_path(traversable)
    if on_disk is not None and on_disk.is_file():
        return on_disk
    checkout = development_root()
    if checkout is not None:
        fallback = checkout / "data" / name
        if fallback.is_file():
            return fallback
    if not traversable.is_file():
        raise FileNotFoundError(f"packaged resource missing: {name}")
    cached = user_cache_root() / "resources" / name
    cached.parent.mkdir(parents=True, exist_ok=True)
    if not cached.is_file():
        cached.write_bytes(traversable.read_bytes())
    return cached


def _traversable_path(traversable: object) -> Path | None:
    if isinstance(traversable, bytes):
        return Path(os.fsdecode(traversable))
    if isinstance(traversable, str | os.PathLike):
        return Path(traversable)
    return None


def extracted_families_path() -> Path:
    return _overridable_resource(
        "ROUTE_AGENT_EXTRACTED_FAMILIES", "extracted_families.json"
    )


def targets_path() -> Path:
    return _overridable_resource(
        "ROUTE_AGENT_TARGETS", "ApexChem_templates_and_targets.xlsx"
    )


def fragments_path() -> Path:
    return _overridable_resource("ROUTE_AGENT_FRAGMENTS", "molecular_fragments.json")


def schema_path() -> Path:
    return _overridable_resource("ROUTE_AGENT_SCHEMA", "schema.json")


def request_schema_path() -> Path:
    return _overridable_resource("ROUTE_AGENT_REQUEST_SCHEMA", "request_schema.json")


def score_py_path() -> Path:
    return _overridable_resource("ROUTE_AGENT_SCORE_PY", "score.py")


def ensure_writable_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return path


def _overridable_resource(env_name: str, resource_name: str) -> Path:
    override = os.environ.get(env_name)
    if override:
        return Path(override).expanduser()
    return packaged_resource_path(resource_name)
