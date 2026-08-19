from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from route_agent.corpus import CorpusRepository
from route_agent.llm.run_context import ensure_run
from route_agent.models.agent import LLMCall
from route_agent.models.conflict import State, StateStatus, ValidationResult
from route_agent.models.corpus import Provenance
from route_agent.models.events import PipelineEvent
from route_agent.models.request import DesignRequest
from route_agent.models.validation import ValidationError
from route_agent.molecular.connectivity import build_parent_product_state
from route_agent.observability import StructuredLogger
from route_agent.observe import NoOpObserver, PipelineObserver
from route_agent.parser.errors import ErrorFactory
from route_agent.parser.policy import (
    DEFAULT_CHEMISTRY,
    ChemistryPolicy,
    ProtectingGroupCensus,
    ResinSelector,
)
from route_agent.parser.sequence import SequenceResolver, SequenceValidator
from route_agent.parser.sites import SiteValidator
from route_agent.protocols import Run, Structurer, Tracer


class RequestParser:
    def __init__(
        self,
        families: CorpusRepository,
        structurer: Structurer,
        tracer: Tracer,
        logger: StructuredLogger | None = None,
        errors: ErrorFactory | None = None,
        chemistry: ChemistryPolicy | None = None,
        observer: PipelineObserver | None = None,
    ) -> None:
        self._errors = errors or ErrorFactory()
        self._families = families
        self._structurer = structurer
        self._tracer = tracer
        self._logger = logger or StructuredLogger()
        chemistry = chemistry or DEFAULT_CHEMISTRY
        self._sequence = SequenceValidator(self._errors)
        self._sites = SiteValidator(self._errors)
        self._resolver = SequenceResolver(self._errors, chemistry)
        self._protecting = ProtectingGroupCensus(self._errors, chemistry)
        self._resin = ResinSelector(self._errors, chemistry)
        self._observer = observer or NoOpObserver()

    def run_validation_pipeline(self, request: DesignRequest) -> ValidationResult:
        with ensure_run(
            self._tracer, request.request_id, {"node_type": "validation"}
        ) as run:
            all_errors: list[ValidationError] = []
            provenance: list[Provenance] = []
            llm_calls: list[LLMCall] = []

            with self._traced_stage(run, request.request_id, "validate_sequence"):
                sequence = self._sequence.validate_parent_sequence(
                    request.sequence, request.residue_annotations
                )
            all_errors.extend(sequence.errors)

            with self._traced_stage(
                run, request.request_id, "validate_modification_sites"
            ):
                sites = self._sites.validate_modification_sites(
                    request, sequence.residues, sequence_length=len(request.sequence)
                )
            all_errors.extend(sites.errors)

            with self._traced_stage(run, request.request_id, "parent_features"):
                structured = self._structurer.structure_request(request)
            all_errors.extend(structured.errors)
            if structured.llm_call is not None:
                llm_calls.append(structured.llm_call)
            occupancy = structured.text

            with self._traced_stage(run, request.request_id, "resolve_family"):
                bindings, family_errors = self._families.bind_families(request)
            all_errors.extend(family_errors)
            for binding in bindings:
                provenance.extend(binding.provenance)

            with self._traced_stage(run, request.request_id, "resolve_sequence"):
                resolution = self._resolver.apply_sequence_transforms(
                    request, sequence.residues, sites.sites_resolved
                )
                sites = self._sites.remap_sites_to_resolved_sequence(
                    sites, resolution.resolution.index_map
                )
                sites = self._sites.flag_conflicting_site_frames(
                    request, sites, resolution.resolution.resolved_sequence
                )
            all_errors.extend(resolution.errors)
            seen_error_ids = {error.id for error in all_errors}
            all_errors.extend(
                error for error in sites.errors if error.id not in seen_error_ids
            )

            with self._traced_stage(
                run, request.request_id, "assign_protecting_groups"
            ):
                resolved_validation = self._sequence.validate_parent_sequence(
                    resolution.resolution.resolved_sequence,
                    resolution.resolution.resolved_annotations,
                )
                all_errors.extend(resolved_validation.errors)
                protection = self._protecting.census_protecting_groups(
                    request, resolved_validation.residues, sites.sites_resolved
                )
            all_errors.extend(protection.errors)
            provenance.extend(protection.ledger.provenance)

            with self._traced_stage(run, request.request_id, "select_resin"):
                resin = self._resin.select_resin(request)
            all_errors.extend(resin.errors)
            if resin.selection is not None:
                provenance.extend(resin.selection.provenance)

            status = self._determine_validation_status(all_errors)
            unknowns = tuple(
                error.message for error in all_errors if error.conflict_kind is None
            )
            resolved_annotations = resolution.resolution.resolved_annotations
            resolved_sequence = resolution.resolution.resolved_sequence
            product = build_parent_product_state(
                sequence=resolved_sequence,
                annotations=resolved_annotations,
                parent_c_terminus=request.parent_c_terminus.value,
                parent_features=request.parent_features,
            )
            state = State(
                id="state_0",
                node_type="validation",
                parents=(),
                modification_ref=None,
                status=status,
                output={
                    "protected": protection.ledger.protected,
                    "occupancy": list(occupancy.occupancy),
                    "route_seed": list(occupancy.route_seed),
                    "parent_c_terminus": request.parent_c_terminus.value,
                    "parent_features": list(request.parent_features),
                    "residue_annotations": resolved_annotations,
                    "intent": request.intent,
                    "resolved_sequence": resolved_sequence,
                    "site_map": [
                        entry.model_dump(mode="json") for entry in sites.site_map
                    ],
                    **product,
                },
                building_block=None,
                sequence_snapshot=resolution.resolution.resolved_sequence,
                route_step=resin.selection.route_step if resin.selection else None,
                errors=tuple(all_errors),
                provenance=tuple(provenance),
                llm_calls=tuple(llm_calls),
            )
            self._logger.info(
                "validation_complete",
                request_id=request.request_id,
                state_id=state.id,
                status=status,
                error_ids=[error.id for error in all_errors],
            )
            return ValidationResult(
                request_id=request.request_id,
                state=state,
                residues=sequence.residues,
                sites_resolved=sites.sites_resolved,
                parent_c_terminus=request.parent_c_terminus,
                parent_features=request.parent_features,
                residue_annotations=request.residue_annotations,
                occupancy=occupancy,
                intent=request.intent,
                family_bindings=bindings,
                resolved_sequence=resolved_sequence,
                resolved_annotations=resolved_annotations,
                index_map=resolution.resolution.index_map,
                site_map=sites.site_map,
                conflicts=sites.conflicts,
                unknowns=unknowns,
            )

    @contextmanager
    def _traced_stage(self, run: Run, request_id: str, stage: str) -> Iterator[None]:
        started = perf_counter()
        self._observer.on_event(
            PipelineEvent(
                kind="validation_stage",
                stage="validating",
                request_id=request_id,
                message=stage,
            )
        )
        with run.span(stage, {"request_id": request_id}):
            yield
        duration_ms = round((perf_counter() - started) * 1000, 3)
        self._logger.debug(
            "validation_stage",
            request_id=request_id,
            stage=stage,
            duration_ms=duration_ms,
        )
        self._observer.on_event(
            PipelineEvent(
                kind="validation_stage",
                stage="validating",
                request_id=request_id,
                message=f"{stage} done",
                duration_ms=duration_ms,
            )
        )

    def _determine_validation_status(
        self, errors: list[ValidationError]
    ) -> StateStatus:
        if any(error.conflict_kind == "site_invalid" for error in errors):
            return "fail"
        if any(error.cause_type == "sequence_invalid" for error in errors):
            return "fail"
        if errors:
            return "degraded"
        return "pass"
