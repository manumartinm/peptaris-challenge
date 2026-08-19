from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from route_agent.models.request import DesignRequest
from route_agent.paths import request_schema_path
from tests.support.validation_case import ValidationCase


class TestDesignRequest(ValidationCase):
    def test_parses_challenge_octreotide_request(self) -> None:
        request = DesignRequest.model_validate(self.design_request_row("REQ-05"))

        assert request.request_id == "REQ-05"
        assert request.sequence == "FCFWKTCX"
        assert request.parent_c_terminus == "alcohol"
        assert request.residue_annotations["X8"] == "threoninol (Thr-ol)"
        assert request.modifications[0].family == "pegylation"
        assert request.modifications[0].site == "K5"
        assert request.modifications[0].detail == "discrete Fmoc-PEG4, on-resin"

    def test_allows_missing_optional_modification_detail(self) -> None:
        payload = self.glucagon_payload()
        payload["modifications"][0].pop("detail")

        request = DesignRequest.model_validate(payload)

        assert request.modifications[0].detail is None

    def test_rejects_extra_top_level_fields(self) -> None:
        payload = self.glucagon_payload()
        payload["unexpected"] = "nope"

        with pytest.raises(ValidationError, match="unexpected"):
            DesignRequest.model_validate(payload)

    def test_rejects_undeclared_nonstandard_x(self) -> None:
        payload = self.glucagon_payload()
        payload["sequence"] = "HSQGTFTSDYSKYLDSRRAQDFVQWLMNX"
        payload["residue_annotations"] = {}

        with pytest.raises(ValidationError, match="X29"):
            DesignRequest.model_validate(payload)

    def test_design_request_is_frozen(self) -> None:
        request = DesignRequest.model_validate(self.glucagon_payload())

        with pytest.raises(ValidationError):
            request.sequence = "AAAA"

    def test_rejects_unknown_family(self) -> None:
        payload = self.glucagon_payload()
        payload["modifications"][0]["family"] = "not_a_family"

        with pytest.raises(ValidationError, match="not_a_family"):
            DesignRequest.model_validate(payload)

    def test_public_request_schema_forbids_unknown_fields(self) -> None:
        schema_path = request_schema_path()
        published = json.loads(schema_path.read_text(encoding="utf-8"))
        generated = DesignRequest.model_json_schema()
        assert published["additionalProperties"] is False
        assert published["properties"].keys() == generated["properties"].keys()
        payload = self.glucagon_payload()
        DesignRequest.model_validate(payload)
        with pytest.raises(ValidationError):
            DesignRequest.model_validate({**payload, "unexpected": True})
