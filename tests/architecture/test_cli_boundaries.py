from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = (ROOT / "src" / "route_agent_cli" / "app.py").read_text(encoding="utf-8")


def test_cli_module_only_composes_commands() -> None:
    assert "RoutePipeline" not in CLI
    assert "ConflictWalker" not in CLI
    assert "DevEvaluator" not in CLI
    assert "keyring" not in CLI
    assert "class Settings" not in CLI


def _python_sources(package: str) -> list[Path]:
    return list((ROOT / "src" / package).rglob("*.py"))


def test_core_does_not_import_adapters() -> None:
    for path in _python_sources("route_agent"):
        text = path.read_text(encoding="utf-8")
        assert "from route_agent_cli" not in text
        assert "import route_agent_cli" not in text
        assert "from route_agent_api" not in text
        assert "import route_agent_api" not in text


def test_api_does_not_import_cli() -> None:
    api_root = ROOT / "src" / "route_agent_api"
    if not api_root.exists():
        return
    for path in api_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from route_agent_cli" not in text
        assert "import route_agent_cli" not in text
