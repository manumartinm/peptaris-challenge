from __future__ import annotations

import pytest

from route_agent.agent.state_categories import derive_state_categories


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"protected": {"K5": "Fmoc"}},
            {"Fmoc_must_survive"},
        ),
        (
            {"protected": {"K5": "Mtt", "C2": "Trt"}},
            {"Fmoc_must_survive", "mild_acid_labile_side_chains_present"},
        ),
        (
            {"protected": {"K12": "ivDde"}},
            {"Fmoc_must_survive", "hydrazine_labile_present"},
        ),
        (
            {"protected": {"K5": "Alloc", "E3": "OAll"}},
            {"Fmoc_must_survive", "alloc_allyl_present"},
        ),
        (
            {"protected": {"K5": "Boc", "S11": "tBu", "R17": "Pbf"}},
            {"Fmoc_must_survive", "strong_acid_labile_present"},
        ),
        (
            {"protected": {"K5": "pending"}},
            {"Fmoc_must_survive", "pending_branch_target_present"},
        ),
        (
            {"free_amines": {"K5": "exposed"}},
            {"Fmoc_must_survive", "free_amines_exposed"},
        ),
        (
            {"catalysts_used": {"Pd": "Pd(PPh3)4"}},
            {"Fmoc_must_survive", "metal_catalyst_used"},
        ),
        (
            {
                "permanent_connectivity": [
                    {
                        "from_atom": "C2.SG",
                        "to_fragment": "C7.SG",
                        "bond_type": "disulfide",
                    }
                ]
            },
            {"Fmoc_must_survive", "disulfide_in_topology"},
        ),
        (
            {
                "permanent_connectivity": [
                    {
                        "from_atom": "K5.NZ",
                        "to_fragment": "c16:1",
                        "bond_type": "amide",
                    }
                ]
            },
            {"Fmoc_must_survive", "amide_in_topology"},
        ),
        (
            {"history": [{"process": "p1a"}]},
            {"Fmoc_must_survive", "history:p1a"},
        ),
        (
            {"termini": {"n": "acetyl", "c": "amide"}},
            {"n_term_capped", "c_term_amide"},
        ),
    ],
)
def test_derive_state_categories(
    payload: dict[str, object], expected: set[str]
) -> None:
    assert derive_state_categories(payload) == frozenset(expected)


def test_equivalent_mild_acid_labels_share_categories() -> None:
    trt = derive_state_categories({"protected": {"K5": "Trt"}})
    mtt = derive_state_categories({"protected": {"K5": "Mtt"}})
    assert "mild_acid_labile_side_chains_present" in trt
    assert trt == mtt


def test_distinct_histories_do_not_share_categories() -> None:
    first = derive_state_categories({"history": [{"process": "p1a"}]})
    second = derive_state_categories({"history": [{"process": "p1b"}]})
    assert first != second
