from __future__ import annotations

from pathlib import Path

from route_agent.literature.sandbox import LiteratureSandbox


class TestLiteratureSandbox:
    def test_ls_and_grep_stay_inside_research_root(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        cache_file = sandbox.write_cache_markdown(
            url="https://example.org/a",
            title="Example",
            markdown="# Title\n\nAlloc and Pd catalyst.\n",
        )
        sandbox.write_memory("REQ-01", "notes.md", "Saw Alloc conflict.\n")

        listed = sandbox.list_files("")
        matches = sandbox.grep_files("Alloc", "")

        assert any(path.endswith(".md") for path in listed)
        assert cache_file.name in " ".join(listed) or any(
            "Alloc" in sandbox.read_file(path, offset=0, limit=20) for path in listed
        )
        assert matches
        assert all(not path.startswith("..") for path in listed)
        assert sandbox.read_file(
            "memory/REQ-01/notes.md", offset=0, limit=10
        ).startswith("Saw Alloc")

    def test_resolve_under_root_rejects_escapes(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        try:
            sandbox.resolve_path_under_root("../secret")
        except ValueError as exc:
            assert "outside" in str(exc)
        else:
            raise AssertionError("expected ValueError")
