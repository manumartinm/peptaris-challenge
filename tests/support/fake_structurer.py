from __future__ import annotations

import re

from route_agent.models.request import DesignRequest
from route_agent.models.validation import (
    StructuredFeature,
    StructuredFreeText,
    StructuredSpan,
    StructuringResult,
)

SITE_IN_TEXT = re.compile(
    r"\b(?:both termini|whole sequence|N-term|C-term|"
    r"[A-Z]\d+(?:\s*-\s*[A-Z]\d+)?(?:,\s*[A-Z]\d+(?:\s*-\s*[A-Z]\d+)?)*)\b"
)

CLASSIFIERS: tuple[tuple[str, str], ...] = (
    ("disulfide", "disulfide"),
    ("lactam", "cyclization"),
    ("acetyl", "n_terminal_cap"),
    ("on-resin", "on_resin_modification"),
    ("peg", "conjugate"),
    ("lipid", "conjugate"),
    ("resin", "resin_context"),
)


class FakeStructurer:
    def structure_request(self, request: DesignRequest) -> StructuringResult:
        features: list[StructuredFeature] = []
        occupancy: list[str] = []
        route_seed: list[str] = []

        for raw in request.parent_features:
            feature = self._classify("parent_features", raw)
            features.append(feature)
            occupancy.append(feature.classification)

        for modification in request.modifications:
            if modification.detail:
                feature = self._classify("modifications.detail", modification.detail)
                features.append(feature)
                route_seed.append(feature.classification)

        features.append(self._classify("intent", request.intent))
        return StructuringResult(
            text=StructuredFreeText(
                features=tuple(features),
                occupancy=tuple(dict.fromkeys(occupancy)),
                route_seed=tuple(dict.fromkeys(route_seed)),
            ),
            errors=(),
            llm_call=None,
        )

    def _classify(self, source_field: str, raw_text: str) -> StructuredFeature:
        lowered = raw_text.lower()
        classification = "unmapped"
        for needle, label in CLASSIFIERS:
            if needle in lowered:
                classification = label
                break
        if source_field == "intent" and classification == "unmapped":
            classification = "design_goal"
        site_match = SITE_IN_TEXT.search(raw_text)
        evidence: tuple[StructuredSpan, ...] = ()
        if site_match:
            evidence = (
                StructuredSpan(
                    text=site_match.group(0),
                    start=site_match.start(),
                    end=site_match.end(),
                ),
            )
        return StructuredFeature(
            source_field=source_field,
            raw_text=raw_text,
            classification=classification,
            site_token=site_match.group(0) if site_match else None,
            evidence=evidence,
            unmapped=classification == "unmapped",
        )
