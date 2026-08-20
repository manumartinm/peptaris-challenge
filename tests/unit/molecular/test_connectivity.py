from __future__ import annotations

from route_agent.models.molecular import Bond
from route_agent.molecular.connectivity import (
    apply_candidate_to_state,
    build_parent_product_state,
    build_recipe,
)


class TestSeedParentProduct:
    def test_disulfide_and_acetyl_parent_features(self) -> None:
        seeded = build_parent_product_state(
            sequence="FCFWKTCX",
            annotations={"X8": "threoninol (Thr-ol)"},
            parent_c_terminus="alcohol",
            parent_features=("disulfide C2-C7", "N-terminal acetyl"),
        )

        bonds = [Bond.model_validate(item) for item in seeded["permanent_connectivity"]]
        assert (
            Bond(from_atom="C2.SG", to_fragment="C7.SG", bond_type="disulfide") in bonds
        )
        assert any(bond.to_fragment == "acetyl:1" for bond in bonds)
        assert seeded["termini"]["n"] == "acetyl"
        assert seeded["termini"]["c"] == "alcohol"
        fragments = {item["instance_id"] for item in seeded["product_fragments"]}
        assert "acetyl:1" in fragments

    def test_lactam_and_multi_disulfide(self) -> None:
        seeded = build_parent_product_state(
            sequence="XDHFRWK",
            annotations={"X1": "Nle"},
            parent_c_terminus="amide",
            parent_features=(
                "N-terminal acetyl",
                "side-chain lactam D2-K7",
            ),
        )
        bonds = [Bond.model_validate(item) for item in seeded["permanent_connectivity"]]
        assert Bond(from_atom="D2.CG", to_fragment="K7.NZ", bond_type="amide") in bonds

        linaclotide = build_parent_product_state(
            sequence="CCEYCCNPACTGCY",
            annotations={},
            parent_c_terminus="free_acid",
            parent_features=(),
        )
        assert linaclotide["permanent_connectivity"] == []

        bridged = build_parent_product_state(
            sequence="CCEYCCNPACTGCY",
            annotations={},
            parent_c_terminus="free_acid",
            parent_features=("disulfide C1-C6, C2-C10, C5-C13",),
        )
        pairs = {
            (bond["from_atom"], bond["to_fragment"])
            for bond in bridged["permanent_connectivity"]
            if bond["bond_type"] == "disulfide"
        }
        assert ("C1.SG", "C6.SG") in pairs
        assert ("C2.SG", "C10.SG") in pairs
        assert ("C5.SG", "C13.SG") in pairs


class TestCandidateCommit:
    def test_multi_disulfide_candidate_commits_all_bridges_at_once(self) -> None:
        parent = build_parent_product_state(
            sequence="CCEYCCNPACTGCY",
            annotations={},
            parent_c_terminus="free_acid",
            parent_features=(),
        )
        child = apply_candidate_to_state(
            parent,
            family="disulfide",
            site="C1-C6, C2-C10, C5-C13",
            process="regioselective",
            detail="three-bridge folding",
        )
        pairs = {
            (bond["from_atom"], bond["to_fragment"])
            for bond in child["permanent_connectivity"]
            if bond["bond_type"] == "disulfide"
        }
        assert pairs == {
            ("C1.SG", "C6.SG"),
            ("C2.SG", "C10.SG"),
            ("C5.SG", "C13.SG"),
        }

    def test_lipidation_appends_spacer_chain_without_protecting_groups(self) -> None:
        parent = build_parent_product_state(
            sequence="HSQGTFTSDYSKYLDSRRAQDFVQWLMNT",
            annotations={},
            parent_c_terminus="free_acid",
            parent_features=(),
        )
        child = apply_candidate_to_state(
            parent,
            family="lipidation",
            site="K12",
            process="mtt_lipidation",
            detail=(
                "C18-diacid via 2xAEEA-gGlu spacer "
                "(Lys-e -> AEEA -> AEEA -> gGlu -> C18 diacid)"
            ),
        )
        bonds = child["permanent_connectivity"]
        assert parent["permanent_connectivity"] == []
        fragments = [item["catalog_id"] for item in child["product_fragments"]]
        assert fragments == ["aeea", "aeea", "gglu", "c18_diacid"]
        assert bonds[0]["from_atom"] == "K12.NZ"
        assert bonds[0]["bond_type"] == "amide"
        assert "Mtt" not in str(child)

    def test_failed_style_skip_is_caller_duty_and_acetylation_commits(self) -> None:
        parent = build_parent_product_state(
            sequence="RPKPQQFFGLM",
            annotations={},
            parent_c_terminus="amide",
            parent_features=(),
        )
        child = apply_candidate_to_state(
            parent,
            family="n_term_acetylation",
            site="N-term",
            process="n_term_acetylation_default",
            detail=None,
        )
        assert child["termini"]["n"] == "acetyl"
        assert any(
            item["catalog_id"] == "acetyl" for item in child["product_fragments"]
        )

    def test_side_chain_family_keeps_on_resin_fmoc(self) -> None:
        parent = build_parent_product_state(
            sequence="SVSEIQLMHNLGKHLNSMERVEWLRKKLQDVHNF",
            annotations={},
            parent_c_terminus="free_acid",
            parent_features=(),
        )
        parent["termini"] = {"n": "Fmoc", "c": parent["termini"]["c"]}
        child = apply_candidate_to_state(
            parent,
            family="lipidation",
            site="K13",
            process="alloc_lipidation",
            detail="C16 via gGlu",
        )
        assert child["termini"]["n"] == "Fmoc"

    def test_stapling_overrides_residues(self) -> None:
        parent = build_parent_product_state(
            sequence="SVSEIQLMHNLGKHLNSMERVEWLRKKLQDVHNF",
            annotations={},
            parent_c_terminus="free_acid",
            parent_features=(),
        )
        child = apply_candidate_to_state(
            parent,
            family="hydrocarbon_stapling",
            site="V21,R25",
            process="hydrocarbon_stapling_default",
            detail="i,i+4 all-hydrocarbon staple",
        )
        assert child["residue_overrides"]["V21"] == "s5"
        assert child["residue_overrides"]["R25"] == "s5"
        assert child["permanent_connectivity"][0]["bond_type"] == "olefin"

    def test_build_recipe_reads_n_methyl_and_termini(self) -> None:
        parent = build_parent_product_state(
            sequence="HGEGTFTSDLSKQMEEEAVRLFIEWLKNGGPSSGAPPPS",
            annotations={},
            parent_c_terminus="amide",
            parent_features=(),
        )
        child = apply_candidate_to_state(
            parent,
            family="n_methylation",
            site="S11",
            process="n_methylation_preferred_route",
            detail=None,
        )
        recipe = build_recipe(child)
        assert recipe.n_methyl_sites == ("S11",)
        assert recipe.c_terminus == "amide"
        assert recipe.n_terminus == "free"

    def test_retro_inverso_replaces_parent_acetyl_with_malonyl(self) -> None:
        parent = build_parent_product_state(
            sequence="VPKGWRFHEMSYS",
            annotations={"V1": "D-Val", "P2": "D-Pro"},
            parent_c_terminus="amide",
            parent_features=("N-terminal acetyl",),
        )
        assert any(
            item["catalog_id"] == "acetyl" for item in parent["product_fragments"]
        )
        child = apply_candidate_to_state(
            parent,
            family="retro_inverso",
            site="whole sequence",
            process="full_retro_inverso_synthesis",
            detail=None,
        )
        catalogs = [item["catalog_id"] for item in child["product_fragments"]]
        assert "acetyl" not in catalogs
        assert "malonyl" in catalogs
        assert child["termini"]["n"] == "malonyl"
        assert child["termini"]["c"] == "gem_diamino"
        assert not any(
            bond["from_atom"] == "N-term" and "acetyl" in bond["to_fragment"]
            for bond in child["permanent_connectivity"]
        )

    def test_partial_retro_inverso_does_not_install_malonyl_caps(self) -> None:
        parent = build_parent_product_state(
            sequence="RPKPQQFFGLM",
            annotations={},
            parent_c_terminus="amide",
            parent_features=("N-terminal acetyl",),
        )
        child = apply_candidate_to_state(
            parent,
            family="retro_inverso",
            site="whole sequence",
            process="partial_retro_inverso",
            detail=(
                "build the end-capped (partial) retro-inverso, "
                "not the full gem-diaminoalkyl/malonyl mimic"
            ),
        )
        catalogs = [item["catalog_id"] for item in child["product_fragments"]]
        assert "malonyl" not in catalogs
        assert child["termini"]["c"] != "gem_diamino"

    def test_unmapped_family_is_recorded_as_unknown(self) -> None:
        parent = build_parent_product_state(
            sequence="HGEGTFTSDLSKQMEEEAVRLFIEWLKNGGPSSGAPPPS",
            annotations={},
            parent_c_terminus="amide",
            parent_features=(),
        )
        child = apply_candidate_to_state(
            parent,
            family="glycosylation",
            site="N28",
            process="complex_biantennary",
            detail="complex biantennary N-glycan",
        )
        assert any(
            item.startswith("unmapped_permanent_family:glycosylation")
            for item in child["product_unknowns"]
        )

    def test_catalogued_charge_hybrid_is_noop(self) -> None:
        parent = build_parent_product_state(
            sequence="HSQGTFTSDYSKYLDSRRAQDFVQWLMNT",
            annotations={},
            parent_c_terminus="free_acid",
            parent_features=(),
        )
        child = apply_candidate_to_state(
            parent,
            family="charge_hybrids",
            site="K12",
            process="charge_hybrid_default",
            detail="K12->R",
        )
        assert not any(
            str(item).startswith("unmapped_permanent_family:charge_hybrids")
            for item in child["product_unknowns"]
        )

    def test_unknown_charge_hybrid_stays_unmapped(self) -> None:
        parent = build_parent_product_state(
            sequence="HSQGTFTSDYSKYLDSRRAQDFVQWLMNT",
            annotations={},
            parent_c_terminus="free_acid",
            parent_features=(),
        )
        child = apply_candidate_to_state(
            parent,
            family="charge_hybrids",
            site="K12",
            process="charge_hybrid_default",
            detail="Fmoc-homoArg-OH",
        )
        assert any(
            str(item).startswith("unmapped_permanent_family:charge_hybrids")
            for item in child["product_unknowns"]
        )
