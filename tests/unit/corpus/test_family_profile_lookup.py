from __future__ import annotations

from route_agent.corpus import CorpusRepository
from tests.support.validation_case import ValidationCase


class TestFamilyProfileLookup(ValidationCase):
    def test_projects_lipidation_process_with_cited_reagents(self) -> None:
        result = CorpusRepository(self.families_path).lookup_family_process(
            "lipidation", "alloc_lipidation"
        )

        assert result.found is True
        assert result.family == "lipidation"
        assert result.process_id == "alloc_lipidation"
        assert result.reagents
        assert all(item.ref_row is not None for item in result.reagents)
        assert any("Fmoc-Lys" in item.text for item in result.reagents)
        assert any(
            "Trt" in item.text or "trityl" in item.text.lower()
            for item in result.explicit_risks
        )
        assert any("ivDde" in item.text for item in result.explicit_alternatives)

    def test_unknown_process_is_typed_miss_not_site_invalid(self) -> None:
        result = CorpusRepository(self.families_path).lookup_family_process(
            "lipidation", "not_a_real_process"
        )

        assert result.found is False
        assert result.process_id == "not_a_real_process"
        assert result.reagents == ()

    def test_c_term_amidation_projects_conditions_and_summary(self) -> None:
        result = CorpusRepository(self.families_path).lookup_family_process(
            "c_term_amidation", "c_term_amidation_default"
        )

        assert result.found is True
        assert result.summary
        assert "Rink" in result.summary or "resin" in result.summary.lower()
        assert any("resin choice" in item.text.lower() for item in result.conditions)
        assert any(
            "post-cleavage" in item.text.lower() for item in result.explicit_risks
        )
        assert any(
            "low-yield" in item.text.lower() for item in result.explicit_alternatives
        )
