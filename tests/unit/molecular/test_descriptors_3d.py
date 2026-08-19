from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import Crippen, rdMolDescriptors

from route_agent.models.molecular import MolecularRecipe
from route_agent.molecular.analysis import (
    MolecularAnalyzer,
    MolecularConfig,
    compute_physchem_descriptors,
    net_charge_at_ph,
)
from route_agent.molecular.builder import MolecularBuilder


class TestDescriptors:
    def test_glycine_tpsa_matches_rdkit(self) -> None:
        built = MolecularBuilder().build(
            MolecularRecipe(
                sequence="G", annotations={}, n_terminus="free", c_terminus="acid"
            )
        )
        assert built.mol is not None
        descriptors = compute_physchem_descriptors(built.mol, built.ionizable, ph=7.4)
        glycine = Chem.MolFromSmiles("NCC(=O)O")
        assert descriptors.tpsa == pytest.approx(
            rdMolDescriptors.CalcTPSA(glycine), abs=0.5
        )
        assert descriptors.clogp == pytest.approx(
            Crippen.MolLogP(glycine),  # type: ignore[attr-defined]
            abs=0.2,
        )
        assert descriptors.heavy_atoms == 5
        assert descriptors.ph == 7.4
        # N-term + C-term: net slightly negative at 7.4 (COOH deprotonated)
        assert descriptors.net_charge == pytest.approx(-0.0, abs=0.3)
        assert 5.0 < descriptors.isoelectric_point < 7.0

    def test_lysine_is_cationic_at_ph_7_4(self) -> None:
        built = MolecularBuilder().build(
            MolecularRecipe(
                sequence="K", annotations={}, n_terminus="free", c_terminus="acid"
            )
        )
        charge = net_charge_at_ph(built.ionizable, 7.4)
        assert charge > 0.8
        acidic = net_charge_at_ph(built.ionizable, 1.0)
        basic = net_charge_at_ph(built.ionizable, 13.0)
        assert acidic > basic


class TestMolecularAnalyzer:
    def test_invalid_recipe_skips_descriptors(self) -> None:
        result = MolecularAnalyzer(config=MolecularConfig(skip_3d=True)).validate(
            MolecularRecipe(
                sequence="X",
                annotations={"X1": "unknown-ncaa"},
                n_terminus="free",
                c_terminus="acid",
            ),
            node_id="state_1",
        )
        assert result.two_d.valid is False
        assert result.descriptors is None
        assert result.ensemble is None
        assert result.node_id == "state_1"

    def test_unmapped_permanent_family_cannot_pass_two_d(self) -> None:
        result = MolecularAnalyzer(config=MolecularConfig(skip_3d=True)).validate(
            MolecularRecipe(
                sequence="N",
                annotations={},
                n_terminus="free",
                c_terminus="amide",
                unknowns=("unmapped_permanent_family:glycosylation:complex",),
            ),
            node_id="state_1",
        )
        assert result.two_d.valid is False
        assert any(issue.code == "unmapped_family" for issue in result.two_d.issues)

    def test_missing_boltz_key_skips_3d_and_keeps_two_d(self) -> None:
        result = MolecularAnalyzer(config=MolecularConfig()).validate(
            MolecularRecipe(
                sequence="G",
                annotations={},
                n_terminus="free",
                c_terminus="acid",
            ),
            node_id="state_1",
        )
        assert result.two_d.valid is True
        assert result.descriptors is not None
        assert result.ensemble is None
        assert "boltz_skipped:no_boltz_key" in result.unknowns
