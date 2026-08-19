from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from route_agent.corpus import CorpusRepository
from route_agent.models.request import (
    DesignRequest,
    ResolutionResult,
    SequenceResolution,
)
from route_agent.models.validation import (
    ProtectionLedger,
    ProtectionResult,
    ResinResult,
    SequenceValidation,
    SiteValidation,
    ValidationCheck,
)
from route_agent.observability import StructuredLogger
from route_agent.parser.errors import ErrorFactory
from route_agent.parser.policy import ResinSelector
from route_agent.parser.request_parser import RequestParser
from route_agent.parser.sequence import SequenceValidator
from route_agent.parser.sites import SiteValidator
from tests.support.fake_structurer import FakeStructurer
from tests.support.fake_tracer import FakeTracer

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
GLUCAGON = "HSQGTFTSDYSKYLDSRRAQDFVQWLMNT"
TERIPARATIDE = "SVSEIQLMHNLGKHLNSMERVEWLRKKLQDVHNF"
OCTREOTIDE = "FCFWKTCX"
EXENATIDE = "HGEGTFTSDLSKQMEEEAVRLFIEWLKNGGPSSGAPPPS"


class ValidationCase:
    repo_root = REPO_ROOT
    data_dir = DATA_DIR
    families_path = DATA_DIR / "extracted_families.json"
    requests_path = DATA_DIR / "design_requests.jsonl"

    def payload(
        self,
        *,
        request_id: str = "T-REQ",
        parent_name: str = "test",
        sequence: str = "ACDE",
        parent_c_terminus: str = "free_acid",
        residue_annotations: dict[str, str] | None = None,
        parent_features: list[str] | None = None,
        modifications: list[dict[str, object]] | None = None,
        intent: str = "unit test",
    ) -> dict[str, Any]:
        annotations = dict(residue_annotations or {})
        if "X" in sequence and not annotations:
            for index, letter in enumerate(sequence, start=1):
                if letter == "X":
                    annotations[f"X{index}"] = "threoninol (Thr-ol)"
        return {
            "request_id": request_id,
            "parent_name": parent_name,
            "sequence": sequence,
            "parent_c_terminus": parent_c_terminus,
            "residue_annotations": annotations,
            "parent_features": list(parent_features or []),
            "modifications": list(
                modifications or [{"family": "n_methylation", "site": "N-term"}]
            ),
            "intent": intent,
        }

    def request(self, **kwargs: Any) -> DesignRequest:
        return DesignRequest.model_validate(self.payload(**kwargs))

    def amide_acetylation_payload(self, request_id: str = "T-ACETYL") -> dict[str, Any]:
        return self.payload(
            request_id=request_id,
            sequence="ACDEK",
            parent_c_terminus="amide",
            modifications=[{"family": "n_term_acetylation", "site": "N-term"}],
        )

    def glucagon_payload(self) -> dict[str, Any]:
        return self.payload(
            request_id="REQ-01",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {
                    "family": "lipidation",
                    "site": "K12",
                    "detail": "C18-diacid via 2xAEEA-gGlu spacer",
                }
            ],
            intent="extend plasma half-life via albumin binding",
        )

    def design_request_row(self, request_id: str) -> dict[str, Any]:
        for line in self.requests_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = cast(dict[str, Any], json.loads(line))
            if row["request_id"] == request_id:
                return row
        raise AssertionError(f"{request_id} missing from design_requests.jsonl")

    def make_parser(
        self,
        structurer: FakeStructurer | Any | None = None,
        tracer: FakeTracer | None = None,
    ) -> tuple[RequestParser, FakeTracer]:
        active_tracer = tracer or FakeTracer()
        parser = RequestParser(
            families=CorpusRepository(self.families_path),
            structurer=structurer or FakeStructurer(),
            tracer=active_tracer,
            logger=StructuredLogger(),
            errors=ErrorFactory(),
        )
        return parser, active_tracer

    def validate_sequence(self, request: DesignRequest) -> SequenceValidation:
        return SequenceValidator().validate_parent_sequence(
            request.sequence, request.residue_annotations
        )

    def validate_sites(
        self,
        sequence: str,
        site: str,
        family: str = "lipidation",
        **kwargs: Any,
    ) -> SiteValidation:
        request = self.request(
            request_id="T-SITE",
            sequence=sequence,
            modifications=[{"family": family, "site": site}],
            **kwargs,
        )
        residues = self.validate_sequence(request).residues
        return SiteValidator().validate_modification_sites(request, residues)

    def remap_sites(self, request: DesignRequest) -> SiteValidation:
        parsed = self.make_parser()[0].run_validation_pipeline(request)
        return SiteValidation(
            sites_resolved=parsed.sites_resolved,
            site_map=parsed.site_map,
            errors=tuple(
                error
                for error in parsed.state.errors
                if error.check == ValidationCheck.VALIDATE_MODIFICATION_SITES
            ),
            conflicts=parsed.conflicts,
        )

    def resolve(self, **kwargs: Any) -> ResolutionResult:
        parsed = self.make_parser()[0].run_validation_pipeline(self.request(**kwargs))
        return ResolutionResult(
            resolution=SequenceResolution(
                resolved_sequence=parsed.resolved_sequence or "",
                resolved_annotations=dict(parsed.resolved_annotations),
                index_map=parsed.index_map,
            ),
            errors=tuple(
                error
                for error in parsed.state.errors
                if error.check == ValidationCheck.RESOLVE_SEQUENCE
            ),
        )

    def census(self, **kwargs: Any) -> ProtectionResult:
        parsed = self.make_parser()[0].run_validation_pipeline(self.request(**kwargs))
        provenance = tuple(
            item
            for item in parsed.state.provenance
            if item.kind == "inference" and item.basis and "Fmoc/tBu" in item.basis
        )
        return ProtectionResult(
            ledger=ProtectionLedger(
                protected=dict(parsed.state.output.get("protected") or {}),
                policy_version="fmoc-tbu-v1",
                provenance=provenance,
            ),
            errors=tuple(
                error
                for error in parsed.state.errors
                if error.check == ValidationCheck.ASSIGN_PROTECTING_GROUPS
            ),
        )

    def select_resin(
        self, terminus: str, family: str, site: str = "C-term"
    ) -> ResinResult:
        request = self.request(
            request_id="T-RESIN",
            sequence="ACDEK",
            parent_c_terminus=terminus,
            modifications=[{"family": family, "site": site}],
        )
        return ResinSelector().select_resin(request)
