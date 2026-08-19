from __future__ import annotations

import json

from route_agent.models.molecular import (
    Bond,
    ConformerEnsemble,
    MolecularIssue,
    MolecularRecipe,
    ProductFragment,
)
from route_agent.molecular.analysis import MolecularAnalyzer, MolecularConfig
from route_agent.molecular.boltz import (
    BoltzClient,
    build_structure_input,
    ensemble_from_prediction,
    failed_ensemble,
    recipe_is_cyclic,
    sequence_only_issue,
)


def _recipe(**overrides: object) -> MolecularRecipe:
    payload: dict[str, object] = {
        "sequence": "ACDE",
        "annotations": {},
        "n_terminus": "free",
        "c_terminus": "amide",
    }
    payload.update(overrides)
    return MolecularRecipe.model_validate(payload)


class FakeTransport:
    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> tuple[int, str]:
        self.calls.append((method, url))
        if not self.responses:
            raise AssertionError(f"unexpected {method} {url}")
        return self.responses.pop(0)


class FakePredictor:
    def __init__(self, ensemble: ConformerEnsemble) -> None:
        self.ensemble = ensemble
        self.seen: list[MolecularRecipe] = []

    def predict_structure(self, recipe: MolecularRecipe) -> ConformerEnsemble:
        self.seen.append(recipe)
        return self.ensemble


class TestStructureInput:
    def test_sends_sequence_as_empty_msa_protein(self) -> None:
        payload = build_structure_input(_recipe())
        assert payload["model"] == "boltz-2.1"
        entity = payload["input"]["entities"][0]
        assert entity == {
            "type": "protein",
            "value": "ACDE",
            "chain_ids": ["A"],
            "msa": {"type": "empty"},
        }
        assert payload["input"]["num_samples"] == 1
        assert "cyclic" not in entity

    def test_marks_head_to_tail_as_cyclic(self) -> None:
        recipe = _recipe(
            bonds=(Bond(from_atom="N-term", to_fragment="C-term", bond_type="amide"),)
        )
        assert recipe_is_cyclic(recipe) is True
        assert build_structure_input(recipe)["input"]["entities"][0]["cyclic"] is True

    def test_sequence_only_issue_when_ptms_present(self) -> None:
        recipe = _recipe(
            fragments=(ProductFragment(instance_id="peg:1", catalog_id="peg4"),),
            n_methyl_sites=("K2",),
        )
        issue = sequence_only_issue(recipe)
        assert issue is not None
        assert issue.code == "boltz_sequence_only"
        assert "fragments" in issue.message
        assert "n_methyl_sites" in issue.message


class TestEnsembleFromPrediction:
    def test_success_maps_confidence_and_cif(self) -> None:
        prediction = {
            "status": "succeeded",
            "output": {
                "best_sample": {
                    "metrics": {
                        "structure_confidence": 0.91,
                        "ptm": 0.8,
                        "complex_plddt": 0.7,
                    }
                }
            },
        }
        ensemble = ensemble_from_prediction(prediction, cif="data_cif")
        assert ensemble.embedding_ok is True
        assert ensemble.converged is True
        assert ensemble.forcefield == "boltz"
        assert ensemble.cif == "data_cif"
        assert ensemble.structure_confidence == 0.91
        assert ensemble.ptm == 0.8
        assert ensemble.complex_plddt == 0.7

    def test_low_confidence_is_not_converged(self) -> None:
        prediction = {
            "status": "succeeded",
            "output": {"best_sample": {"metrics": {"structure_confidence": 0.2}}},
        }
        ensemble = ensemble_from_prediction(prediction, cif="cif")
        assert ensemble.embedding_ok is True
        assert ensemble.converged is False

    def test_failed_status_is_failed_ensemble(self) -> None:
        ensemble = ensemble_from_prediction(
            {"status": "failed", "error": {"message": "boom"}},
            cif=None,
        )
        assert ensemble.embedding_ok is False
        assert ensemble.issues[0].code == "boltz_failed"
        assert "boom" in ensemble.issues[0].message

    def test_missing_cif_is_failed(self) -> None:
        ensemble = ensemble_from_prediction(
            {"status": "succeeded", "output": {"best_sample": {"metrics": {}}}},
            cif=None,
        )
        assert ensemble.embedding_ok is False
        assert ensemble.issues[0].code == "boltz_failed"


class TestBoltzClient:
    def test_start_poll_and_download_cif(self) -> None:
        transport = FakeTransport(
            [
                (200, json.dumps({"id": "pred_1", "status": "pending"})),
                (200, json.dumps({"id": "pred_1", "status": "running"})),
                (
                    200,
                    json.dumps(
                        {
                            "id": "pred_1",
                            "status": "succeeded",
                            "output": {
                                "best_sample": {
                                    "metrics": {"structure_confidence": 0.88},
                                    "structure": {
                                        "url": "https://files.example/sample.cif"
                                    },
                                }
                            },
                        }
                    ),
                ),
                (200, "data_block cif"),
            ]
        )
        client = BoltzClient(
            "sk_test",
            timeout_s=30,
            poll_interval_s=0,
            transport=transport,
            sleeper=lambda _seconds: None,
        )
        ensemble = client.predict_structure(_recipe())
        assert ensemble.embedding_ok is True
        assert ensemble.cif == "data_block cif"
        assert transport.calls[0][0] == "POST"
        assert transport.calls[-1] == ("GET", "https://files.example/sample.cif")

    def test_http_error_becomes_failed_ensemble(self) -> None:
        transport = FakeTransport([(503, json.dumps({"message": "busy"}))])
        client = BoltzClient(
            "sk_test",
            timeout_s=10,
            poll_interval_s=0,
            transport=transport,
            sleeper=lambda _seconds: None,
        )
        ensemble = client.predict_structure(_recipe())
        assert ensemble.embedding_ok is False
        assert ensemble.issues[0].code == "boltz_unavailable"

    def test_failed_helper_keeps_boltz_forcefield(self) -> None:
        ensemble = failed_ensemble(code="boltz_timeout", message="too slow")
        assert ensemble.forcefield == "boltz"
        assert ensemble.issues[0].code == "boltz_timeout"


class TestAnalyzerBoltz:
    def test_injected_predictor_fills_ensemble(self) -> None:
        predicted = ConformerEnsemble(
            embedding_ok=True,
            converged=True,
            n_requested=1,
            n_embedded=1,
            n_optimized=1,
            valid_fraction=1.0,
            forcefield="boltz",
            n_clashes=0,
            cif="cif",
            structure_confidence=0.9,
            issues=(
                MolecularIssue(
                    code="boltz_sequence_only",
                    message="backbone only",
                    path="product",
                ),
            ),
        )
        fake = FakePredictor(predicted)
        result = MolecularAnalyzer(
            config=MolecularConfig(boltz_api_key="sk_test"),
            boltz=fake,
        ).validate(_recipe(sequence="G"), node_id="state_1")
        assert result.ensemble is predicted
        assert fake.seen[0].sequence == "G"
        assert "backbone only" in result.unknowns

    def test_skip_3d_does_not_call_predictor(self) -> None:
        fake = FakePredictor(
            ConformerEnsemble(
                embedding_ok=True,
                converged=True,
                n_requested=1,
                n_embedded=1,
                n_optimized=1,
                valid_fraction=1.0,
                forcefield="boltz",
                n_clashes=0,
            )
        )
        result = MolecularAnalyzer(
            config=MolecularConfig(skip_3d=True, boltz_api_key="sk_test"),
            boltz=fake,
        ).validate(_recipe(sequence="G"), node_id="state_1")
        assert result.ensemble is None
        assert fake.seen == []
        assert "boltz_skipped:skip_3d" in result.unknowns
