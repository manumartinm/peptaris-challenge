from __future__ import annotations

from pathlib import Path

from deepagents import FilesystemPermission
from deepagents.backends import CompositeBackend, FilesystemBackend

from route_agent.agent.harness import DeepAgentHarness
from route_agent.literature.sandbox import LiteratureSandbox


class TestDeepAgentHarness:
    def test_backend_is_filesystem_only_under_workspace(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        harness = DeepAgentHarness(sandbox)
        backend = harness.backend()

        assert isinstance(backend, CompositeBackend)
        assert isinstance(backend.default, FilesystemBackend)
        assert (
            Path(backend.default.cwd).resolve()
            == (sandbox.root / "workspace").resolve()
        )
        assert "/cache/" in backend.routes
        assert "/memory/" in backend.routes
        assert "/skills/" in backend.routes
        assert "/workspace/" in backend.routes

    def test_permissions_cover_research_paths(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        harness = DeepAgentHarness(sandbox)
        modes = {(tuple(perm.paths), perm.mode) for perm in harness.permissions()}

        assert any(
            isinstance(perm, FilesystemPermission) and perm.mode == "deny"
            for perm in harness.permissions()
            if "/skills/" in perm.paths
        )
        assert any("/memory/" in paths and mode == "allow" for paths, mode in modes)
        assert harness.skills() == ["/skills/"]
        assert harness.memory() == ["/memory/AGENTS.md"]

    def test_permissions_are_compatible_with_filesystem_backend(
        self, tmp_path: Path
    ) -> None:
        from deepagents.middleware.filesystem import FilesystemMiddleware

        sandbox = LiteratureSandbox(tmp_path / "research")
        harness = DeepAgentHarness(sandbox)
        prefixes = tuple(harness.backend().routes)

        for perm in harness.permissions():
            for path in perm.paths:
                assert any(path.startswith(prefix) for prefix in prefixes), path

        FilesystemMiddleware(
            backend=harness.backend(),
            _permissions=harness.permissions(),
        )
