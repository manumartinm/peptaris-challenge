from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from route_agent.models.corpus import Provenance
from route_agent.models.verdict import RouteConflict, RouteStep, RouteVerdict
from tests.support.score import validate_schema


def _verdict(**overrides: object) -> RouteVerdict:
    payload: dict[str, object] = {
        "request_id": "REQ-09",
        "verdict": "feasible",
        "confidence": "high",
        "resolved_sequence": "HSQGTFTSDYSKYLDSRRAQDFVQWLMNT",
        "resolved_annotations": {},
        "site_map": [
            {
                "requested": "C-term",
                "resolved": "C-term",
                "residue": None,
                "note": None,
            }
        ],
        "route": [
            {
                "step": 1,
                "stage": "resin_selection",
                "operation": "Select Rink amide MBHA",
                "provenance": [
                    {
                        "kind": "inference",
                        "basis": "C-terminal amide is set by resin choice",
                    }
                ],
            }
        ],
        "conflicts": [],
        "unknowns": [],
    }
    payload.update(overrides)
    return RouteVerdict.model_validate(payload)


class TestRouteVerdict:
    def test_rejects_extra_top_level_fields(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            _verdict(cost=1.0)

    def test_keeps_null_note_and_resolution(self) -> None:
        verdict = _verdict(
            conflicts=[
                {
                    "severity": "minor",
                    "kind": "order_of_operations",
                    "description": "advisory",
                    "affected": ["C-term"],
                    "resolution": None,
                    "provenance": [
                        {
                            "kind": "corpus",
                            "ref": (
                                "ApexChem_Synthesis_Reactions_by_AminoAcid"
                                ":04_C_Term_Amidation:12"
                            ),
                        }
                    ],
                }
            ]
        )
        dumped = verdict.model_dump(mode="json")
        assert dumped["site_map"][0]["note"] is None
        assert dumped["conflicts"][0]["resolution"] is None

    def test_omits_null_provenance_fields(self) -> None:
        corpus = Provenance(
            kind="corpus",
            ref="ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:25",
        )
        inference = Provenance(
            kind="inference",
            basis="mechanism",
            refs=("ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:24",),
        )
        assert corpus.model_dump(mode="json") == {
            "kind": "corpus",
            "ref": "ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:25",
        }
        assert inference.model_dump(mode="json") == {
            "kind": "inference",
            "basis": "mechanism",
            "refs": ["ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:24"],
        }

    def test_score_py_accepts_serialized_verdict(self, tmp_path: Path) -> None:
        verdict = _verdict()
        report = validate_schema(verdict.model_dump(mode="json"), tmp_path)
        assert report["checked"] is True
        assert report["invalid"] == []

    def test_route_step_and_conflict_enums(self) -> None:
        step = RouteStep(
            step=2,
            stage="cleavage",
            operation="TFA cleavage",
            provenance=(Provenance(kind="inference", basis="standard TFA cocktail"),),
        )
        conflict = RouteConflict(
            severity="major",
            kind="protecting_group_orthogonality",
            description="Mtt collides with tBu",
            affected=("K12",),
            resolution="ivdde_lipidation",
            provenance=(Provenance(kind="inference", basis="sibling process"),),
        )
        assert step.stage == "cleavage"
        assert conflict.kind == "protecting_group_orthogonality"
