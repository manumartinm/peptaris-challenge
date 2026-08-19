from __future__ import annotations

from typing import Any

from route_agent.corpus import collect_excerpt_refs
from route_agent.literature.sandbox import LiteratureSandbox
from route_agent.models.corpus import CorpusExcerptRef, ExtractedFamiliesView
from route_agent.models.frozen import FrozenModel


class AuditResult(FrozenModel):
    verified: bool
    reason: str | None = None
    path: str | None = None
    ref_row: int | None = None


class AuditRef:
    def __init__(
        self,
        sandbox: LiteratureSandbox,
        families_path: Any,
        catalog: ExtractedFamiliesView | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._families_path = families_path
        self._catalog = catalog
        self._index: dict[str, CorpusExcerptRef] | None = None

    def verify_citation(self, kind: str, ref_or_source: str, basis: str) -> AuditResult:
        if kind == "external":
            return self._verify_external_citation(ref_or_source, basis)
        if kind == "corpus":
            return self._verify_corpus_citation(ref_or_source, basis)
        return AuditResult(verified=False, reason="unknown_kind")

    def _verify_external_citation(self, source: str, basis: str) -> AuditResult:
        path = self._sandbox.cached_markdown_path(source)
        if path is None:
            return AuditResult(verified=False, reason="source_not_cached")
        terms = [term.lower() for term in basis.split() if term]
        if not terms:
            return AuditResult(verified=False, reason="basis_not_found", path=str(path))
        found = {term: False for term in terms}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                lowered = line.lower()
                for term in terms:
                    if not found[term] and term in lowered:
                        found[term] = True
                if all(found.values()):
                    return AuditResult(verified=True, path=str(path))
        return AuditResult(verified=False, reason="basis_not_found", path=str(path))

    def _verify_corpus_citation(self, ref: str, basis: str) -> AuditResult:
        excerpt = self._ref_index().get(ref)
        row = self._parse_ref_row(ref)
        if excerpt is None:
            return AuditResult(
                verified=False, reason="corpus_ref_not_found", ref_row=row
            )
        if basis and not _basis_supported(basis, excerpt.source_excerpt):
            return AuditResult(
                verified=False, reason="basis_not_found", ref_row=excerpt.ref_row or row
            )
        return AuditResult(verified=True, ref_row=excerpt.ref_row or row)

    def _parse_ref_row(self, ref: str) -> int | None:
        parts = ref.split(":")
        if len(parts) >= 3 and parts[-1].isdigit():
            return int(parts[-1])
        return None

    def _ref_index(self) -> dict[str, CorpusExcerptRef]:
        if self._index is not None:
            return self._index
        import json

        payload: Any
        if self._catalog is not None:
            payload = self._catalog.model_dump(mode="json")
        else:
            payload = json.loads(self._families_path.read_text(encoding="utf-8"))
        index: dict[str, CorpusExcerptRef] = {}
        for excerpt in collect_excerpt_refs(payload):
            current = index.get(excerpt.ref)
            if current is None or len(excerpt.source_excerpt) > len(
                current.source_excerpt
            ):
                index[excerpt.ref] = excerpt
        self._index = index
        return self._index


_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "to",
    "of",
    "and",
    "or",
    "in",
    "on",
    "for",
    "with",
    "when",
    "that",
    "this",
    "as",
    "at",
    "by",
    "from",
    "not",
    "no",
}


def _basis_supported(basis: str, excerpt: str) -> bool:
    haystack = excerpt.lower()
    terms = [
        term.strip(".,;:()/").lower()
        for term in basis.replace("/", " ").replace("-", " ").split()
        if term.strip(".,;:()/")
    ]
    content = [term for term in terms if len(term) > 2 and term not in _STOPWORDS]
    if not content:
        return True
    hits = sum(1 for term in content if term in haystack)
    return hits >= 1
