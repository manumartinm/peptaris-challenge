from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

from route_agent.models.frozen import FrozenModel

MAX_GREP_BYTES = 2_000_000
PREVIEW_CHARS = 400
THIN_CONTENT_CHARS = 500


@lru_cache(maxsize=64)
def _compile_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


class LiteratureSandbox:
    """Path confinement under research_root. Not a process or network sandbox."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._cache_dir = root / "cache"
        self._memory_dir = root / "memory"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def memory_dir(self) -> Path:
        return self._memory_dir

    def cache_key_for_url(self, url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]

    def cache_markdown_path(self, url: str) -> Path:
        return self.cache_dir / f"{self.cache_key_for_url(url)}.md"

    def cache_meta_path(self, url: str) -> Path:
        return self.cache_dir / f"{self.cache_key_for_url(url)}.meta.json"

    def cached_markdown_path(self, url: str) -> Path | None:
        path = self.cache_markdown_path(url)
        return path if path.is_file() else None

    def write_cache_markdown(
        self,
        url: str,
        title: str,
        markdown: str,
        citations: tuple[str, ...] = (),
    ) -> Path:
        markdown_path = self.cache_markdown_path(url)
        markdown_path.write_text(markdown, encoding="utf-8")
        self.cache_meta_path(url).write_text(
            json.dumps(
                {
                    "url": url,
                    "title": title,
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "citations": list(citations),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return markdown_path

    def cache_citations(self, url: str) -> tuple[str, ...]:
        path = self.cache_meta_path(url)
        if not path.is_file():
            return ()
        payload = json.loads(path.read_text(encoding="utf-8"))
        citations = payload.get("citations") or []
        if not isinstance(citations, list):
            return ()
        return tuple(str(item) for item in citations)

    def write_memory(self, request_id: str, name: str, content: str) -> Path:
        directory = self.memory_dir / request_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / Path(name).name
        path.write_text(content, encoding="utf-8")
        return path

    def write_shared_memory(self, name: str, content: str) -> Path:
        path = self.memory_dir / Path(name).name
        path.write_text(content, encoding="utf-8")
        return path

    def resolve_path_under_root(self, relative: str) -> Path:
        if Path(relative).is_absolute():
            candidate = Path(relative).resolve()
        else:
            candidate = (self.root / relative).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"{relative} is outside the literature sandbox")
        return candidate

    def list_files(self, relative: str = "") -> list[str]:
        base = self.resolve_path_under_root(relative) if relative else self.root
        if not base.exists():
            return []
        return [
            str(path.relative_to(self.root))
            for path in sorted(base.rglob("*"))
            if path.is_file()
        ]

    def read_file(
        self, relative: str, offset: int = 0, limit: int | None = None
    ) -> str:
        text = self.resolve_path_under_root(relative).read_text(encoding="utf-8")
        if offset == 0 and limit is None:
            return text
        lines = text.splitlines()
        end = None if limit is None else offset + limit
        return "\n".join(lines[offset:end])

    def grep_files(self, pattern: str, relative: str = "") -> list[str]:
        compiled = _compile_pattern(pattern)
        hits: list[str] = []
        for path in self.list_files(relative):
            full = self.resolve_path_under_root(path)
            if full.stat().st_size > MAX_GREP_BYTES:
                continue
            with full.open(encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if compiled.search(line):
                        hits.append(path)
                        break
        return hits


class FetchResult(FrozenModel):
    path: str
    preview: str
    cache_hit: bool
    full_text: None = None
    thin_content: bool
    citeable: bool
    citations: tuple[str, ...] = ()
    error: str | None = None


class _Converter(Protocol):
    def to_markdown(self, payload: bytes, content_type: str) -> str: ...


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return "\n".join(self._chunks)


class DocumentConverter:
    def to_markdown(self, payload: bytes, content_type: str) -> str:
        lowered = content_type.lower()
        if "pdf" in lowered or payload.startswith(b"%PDF"):
            import pymupdf4llm  # type: ignore[import-untyped]

            return str(pymupdf4llm.to_markdown(payload))
        extractor = _HtmlTextExtractor()
        extractor.feed(payload.decode("utf-8", errors="replace"))
        return extractor.text()


class FetchAndParse:
    def __init__(
        self,
        sandbox: LiteratureSandbox,
        converter: _Converter | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._converter = converter or DocumentConverter()

    def cache_document(
        self,
        url: str,
        content: str,
        citations: tuple[str, ...] = (),
        title: str | None = None,
    ) -> FetchResult:
        cached = self._sandbox.cached_markdown_path(url)
        if cached is not None:
            markdown = cached.read_text(encoding="utf-8")
            return self._build_fetch_result(
                path=cached,
                markdown=markdown,
                cache_hit=True,
                citations=self._sandbox.cache_citations(url) or citations,
            )
        markdown = self._html_to_markdown_if_needed(content)
        path = self._sandbox.write_cache_markdown(
            url,
            title=title or url,
            markdown=markdown,
            citations=citations,
        )
        return self._build_fetch_result(
            path=path, markdown=markdown, cache_hit=False, citations=citations
        )

    def convert_to_markdown(self, payload: bytes, content_type: str) -> str:
        return self._converter.to_markdown(payload, content_type)

    def _html_to_markdown_if_needed(self, content: str) -> str:
        stripped = content.lstrip()
        head = stripped[:200].lower()
        if stripped.startswith("<") or "<html" in head:
            return self._converter.to_markdown(content.encode("utf-8"), "text/html")
        return content

    def _build_fetch_result(
        self,
        path: Path,
        markdown: str,
        cache_hit: bool,
        citations: tuple[str, ...],
    ) -> FetchResult:
        thin = len(" ".join(markdown.split())) < THIN_CONTENT_CHARS
        return FetchResult(
            path=str(path),
            preview=markdown[:PREVIEW_CHARS],
            cache_hit=cache_hit,
            full_text=None,
            thin_content=thin,
            citeable=not thin,
            citations=citations,
        )
