from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from click.testing import CliRunner

from route_agent.version import PACKAGE_NAME, UNKNOWN_VERSION, package_version
from route_agent_api.app import create_app
from route_agent_cli.app import app


class TestPackageVersion:
    def test_matches_installed_metadata(self) -> None:
        assert package_version() == version(PACKAGE_NAME)
        assert package_version() != UNKNOWN_VERSION

    def test_falls_back_when_uninstalled(self, monkeypatch: object) -> None:
        def missing(_name: str) -> str:
            raise PackageNotFoundError

        monkeypatch.setattr("route_agent.version.version", missing)  # type: ignore[attr-defined]
        assert package_version() == UNKNOWN_VERSION

    def test_cli_version_matches_package(self) -> None:
        result = CliRunner().invoke(app, ["--version"])
        assert result.exit_code == 0
        assert package_version() in result.output

    def test_api_version_matches_package(self) -> None:
        assert create_app().version == package_version()
