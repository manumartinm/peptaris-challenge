from __future__ import annotations

import pytest
from pydantic import ValidationError

from route_agent.models.molecular import Bond, PostGraphValidationReport


class TestBond:
    def test_is_frozen(self) -> None:
        bond = Bond(from_atom="C2.S", to_fragment="C7", bond_type="disulfide")
        with pytest.raises(ValidationError):
            bond.bond_type = "amide"


class TestMolecularContracts:
    def test_post_graph_report_omits_verdict_when_no_winner(self) -> None:
        report = PostGraphValidationReport(
            request_id="REQ-00",
            surviving_ids=("state_1",),
            selected_id=None,
            tied_ids=(),
            unknowns=("no 2D-valid candidate",),
            candidates=(),
        )
        dumped = report.model_dump()
        assert dumped["selected_id"] is None
        assert "verdict" not in dumped
