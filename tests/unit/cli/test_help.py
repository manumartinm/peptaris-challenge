from __future__ import annotations

from pathlib import Path

from tests.support.cli import CliCase


class TestCliHelp(CliCase):
    def test_root_help_lists_public_commands_only(self) -> None:
        result = self.invoke("--help")
        assert result.exit_code == 0
        output = result.output
        assert "run" in output
        assert "validate" in output
        assert "config" in output
        assert "doctor" in output
        assert "debug" in output
        assert "  agent" not in output
        assert "  walk" not in output
        assert "  eval" not in output
        assert "Exit codes" in output

    def test_version_option(self) -> None:
        result = self.invoke("--version")
        assert result.exit_code == 0
        assert "route-agent" in result.output

    def test_run_help_mentions_no_model_and_explain(self) -> None:
        result = self.invoke("run", "--help")
        assert result.exit_code == 0
        assert "--no-model" in result.output
        assert "--explain" in result.output

    def test_debug_help_lists_technical_commands(self) -> None:
        result = self.invoke("debug", "--help")
        assert result.exit_code == 0
        assert "agent" in result.output
        assert "walk" in result.output
        assert "post-graph" in result.output
        assert "eval" in result.output

    def test_legacy_alias_warns(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, self.design_request_row("REQ-01"))
        result = self.invoke(
            "agent",
            str(request_path),
            "--objective",
            "check_compatibility",
            "--no-model",
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        assert "deprecated" in result.stderr
        assert "debug agent" in result.stderr
