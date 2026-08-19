from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from route_agent.models.molecular import Bond, MolecularRecipe, ProductFragment
from route_agent.molecular.builder import MolecularBuilder
from route_agent.molecular.fragments import FragmentCatalog


class TestFragmentCatalog:
    def test_loads_unique_ids_and_parses_smiles(self) -> None:
        catalog = FragmentCatalog()
        ids = [record.id for record in catalog.records]
        assert len(ids) == len(set(ids))
        assert catalog.get("K") is not None
        assert catalog.get("Nle") is not None
        assert catalog.get("threoninol (Thr-ol)") is not None
        assert catalog.get("not-a-residue") is None

    def test_rejects_unsupported_schema_version(self, tmp_path: Path) -> None:
        path = tmp_path / "fragments.json"
        path.write_text(
            json.dumps({"schema_version": "9.9.9", "fragments": []}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="schema_version"):
            FragmentCatalog(path)

    def test_rejects_unknown_alias_via_require(self) -> None:
        catalog = FragmentCatalog()
        with pytest.raises(KeyError):
            catalog.require("gem-diaminoalkyl")


class TestMolecularBuilder:
    def setup_method(self) -> None:
        self.builder = MolecularBuilder()

    def test_glycine_matches_free_amino_acid(self) -> None:
        recipe = MolecularRecipe(
            sequence="G", annotations={}, n_terminus="free", c_terminus="acid"
        )
        result = self.builder.build(recipe)
        glycine = Chem.MolFromSmiles("NCC(=O)O")
        assert result.two_d_validation.valid is True
        assert result.two_d_validation.formula == rdMolDescriptors.CalcMolFormula(
            glycine
        )
        assert result.two_d_validation.exact_mw == pytest.approx(
            Descriptors.ExactMolWt(glycine),  # type: ignore[attr-defined]
            abs=1e-4,
        )

    def test_c_terminal_amide_dipeptide(self) -> None:
        recipe = MolecularRecipe(
            sequence="AA", annotations={}, n_terminus="free", c_terminus="amide"
        )
        result = self.builder.build(recipe)
        expected = Chem.MolFromSmiles("C[C@@H](N)C(=O)N[C@@H](C)C(N)=O")
        assert result.two_d_validation.valid is True
        assert result.two_d_validation.formula == rdMolDescriptors.CalcMolFormula(
            expected
        )
        assert result.two_d_validation.exact_mw == pytest.approx(
            Descriptors.ExactMolWt(expected),  # type: ignore[attr-defined]
            abs=1e-3,
        )

    def test_nle_annotation_on_x(self) -> None:
        recipe = MolecularRecipe(
            sequence="GXG",
            annotations={"X2": "Nle"},
            n_terminus="free",
            c_terminus="acid",
        )
        result = self.builder.build(recipe)
        assert result.two_d_validation.valid is True
        assert result.mol is not None
        assert "CCCC" in (result.two_d_validation.smiles or "")

    def test_lysine_c16_conjugate(self) -> None:
        recipe = MolecularRecipe(
            sequence="K",
            annotations={},
            n_terminus="free",
            c_terminus="acid",
            bonds=(Bond(from_atom="K1.NZ", to_fragment="c16:1", bond_type="amide"),),
            fragments=(
                ProductFragment(instance_id="c16:1", catalog_id="c16", site="K1"),
            ),
        )
        result = self.builder.build(recipe)
        assert result.two_d_validation.valid is True
        assert result.two_d_validation.formula is not None
        assert "C16" not in (result.two_d_validation.formula or "")
        assert result.mol is not None
        assert result.mol.GetNumAtoms() > 16

    def test_disulfide_and_d_residue(self) -> None:
        recipe = MolecularRecipe(
            sequence="CFC",
            annotations={"F2": "D-Phe"},
            n_terminus="acetyl",
            c_terminus="amide",
            bonds=(
                Bond(from_atom="N-term", to_fragment="acetyl:1", bond_type="amide"),
                Bond(from_atom="C1.SG", to_fragment="C3.SG", bond_type="disulfide"),
            ),
            fragments=(
                ProductFragment(
                    instance_id="acetyl:1", catalog_id="acetyl", site="N-term"
                ),
            ),
        )
        result = self.builder.build(recipe)
        assert result.two_d_validation.valid is True
        assert result.mol is not None
        assert any(
            bond.GetBondType() == Chem.BondType.SINGLE
            and bond.GetBeginAtom().GetSymbol() == "S"
            and bond.GetEndAtom().GetSymbol() == "S"
            for bond in result.mol.GetBonds()
        )

    def test_unknown_alias_is_missing_fragment_not_conflict(self) -> None:
        recipe = MolecularRecipe(
            sequence="X",
            annotations={"X1": "gem-diaminoalkyl"},
            n_terminus="free",
            c_terminus="acid",
        )
        result = self.builder.build(recipe)
        assert result.two_d_validation.valid is False
        assert result.two_d_validation.issues[0].code == "missing_fragment"

    def test_retro_inverso_malonyl_cap_on_d_peptide(self) -> None:
        recipe = MolecularRecipe(
            sequence="VPKGWRFHEMSYS",
            annotations={
                "V1": "D-Val",
                "P2": "D-Pro",
                "K3": "D-Lys",
                "G4": "D-Gly",
                "W5": "D-Trp",
                "R6": "D-Arg",
                "F7": "D-Phe",
                "H8": "D-His",
                "E9": "D-Glu",
                "M10": "D-Met",
                "S11": "D-Ser",
                "Y12": "D-Tyr",
                "S13": "D-Ser",
            },
            n_terminus="malonyl",
            c_terminus="gem_diamino",
            bonds=(
                Bond(from_atom="N-term", to_fragment="malonyl:1", bond_type="amide"),
            ),
            fragments=(
                ProductFragment(
                    instance_id="malonyl:1", catalog_id="malonyl", site="N-term"
                ),
            ),
        )
        result = self.builder.build(recipe)
        assert result.two_d_validation.valid is True
        assert result.mol is not None

    def test_lys_asp_lactam_uses_side_chain_ports(self) -> None:
        recipe = MolecularRecipe(
            sequence="DK",
            annotations={},
            n_terminus="free",
            c_terminus="amide",
            bonds=(Bond(from_atom="D1.CG", to_fragment="K2.NZ", bond_type="amide"),),
        )
        result = self.builder.build(recipe)
        assert result.two_d_validation.valid is True
        assert result.mol is not None
