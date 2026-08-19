"""Construct parser, agent runtime, and the full pipeline.

CLI and API call these factories. They do not build Langfuse, walkers, or
judges themselves.
"""

from __future__ import annotations

from pathlib import Path

from route_agent.agent.prompt import SYSTEM_PROMPT
from route_agent.agent.runtime import AgentRuntime, CompatCache
from route_agent.conflict import ConflictWalker
from route_agent.corpus import CorpusRepository
from route_agent.literature.audit import AuditRef
from route_agent.literature.sandbox import FetchAndParse, LiteratureSandbox
from route_agent.llm.langfuse_tracer import LangfuseTracer
from route_agent.llm.llm_client import LlmClient
from route_agent.models.agent import AgentCandidate, AgentObjective
from route_agent.models.request import DesignRequest
from route_agent.molecular.analysis import MolecularAnalyzer
from route_agent.molecular.builder import MolecularBuilder
from route_agent.molecular.fragments import FragmentCatalog
from route_agent.observability import StructuredLogger
from route_agent.observe import NoOpObserver, PipelineObserver
from route_agent.parser.errors import ErrorFactory
from route_agent.parser.request_parser import RequestParser
from route_agent.pipeline import RoutePipeline
from route_agent.post_graph.final_judge import FinalJudgeRunner
from route_agent.post_graph.validator import PostGraphValidator
from route_agent.settings import Settings
from route_agent.trace import TraceWriter
from route_agent.verdict.assembler import RouteAssembler

_TRACERS: dict[tuple[str | None, str | None, str | None], LangfuseTracer] = {}


def build_tracer(settings: Settings) -> LangfuseTracer:
    key = (
        settings.secret_value_or_none(settings.langfuse_public_key),
        settings.secret_value_or_none(settings.langfuse_secret_key),
        settings.langfuse_host,
    )
    tracer = _TRACERS.get(key)
    if tracer is None:
        tracer = LangfuseTracer(
            public_key=key[0],
            secret_key=key[1],
            host=key[2],
        )
        _TRACERS[key] = tracer
    return tracer


def flush_tracers() -> None:
    for tracer in _TRACERS.values():
        tracer.flush()


def build_parser(
    settings: Settings,
    *,
    observer: PipelineObserver | None = None,
    logger: StructuredLogger | None = None,
) -> RequestParser:
    settings.apply_provider_credentials()
    errors = ErrorFactory()
    families = CorpusRepository(settings.extracted_families_path, errors)
    structurer = LlmClient(
        model=settings.model,
        errors=errors,
        enabled=not settings.no_model,
        api_key=settings.provider_api_key(),
        reasoning_effort=settings.reasoning_effort,
    )
    return RequestParser(
        families=families,
        structurer=structurer,
        tracer=build_tracer(settings),
        logger=logger or StructuredLogger(),
        errors=errors,
        observer=observer or NoOpObserver(),
    )


def build_agent_runtime(
    settings: Settings,
    logger: StructuredLogger | None = None,
) -> tuple[AgentRuntime, CorpusRepository]:
    settings.apply_provider_credentials()
    sandbox = LiteratureSandbox(settings.research_root)
    families = CorpusRepository(
        settings.extracted_families_path,
        targets_path=settings.targets_path,
    )
    fetch = FetchAndParse(sandbox=sandbox)
    audit = AuditRef(sandbox=sandbox, families_path=settings.extracted_families_path)
    log = logger or StructuredLogger()
    agent = None
    if not settings.no_model:
        from route_agent.agent.deep_agent import build_deep_agent

        log.info("deep_agent_build", model=settings.model)
        agent = build_deep_agent(
            sandbox=sandbox,
            families=families,
            fetch=fetch,
            audit=audit,
            model=settings.model,
            system_prompt=SYSTEM_PROMPT,
            journal_allowlist=settings.journal_allowlist,
            reasoning_effort=settings.reasoning_effort,
            api_key=settings.provider_api_key(),
        )
    runtime = AgentRuntime(
        sandbox=sandbox,
        tracer=build_tracer(settings),
        agent=agent,
        enabled=not settings.no_model,
        model=settings.model,
        logger=log,
        cache=CompatCache(),
        families=families,
    )
    return runtime, families


def build_audit_ref(settings: Settings) -> AuditRef:
    return AuditRef(
        sandbox=LiteratureSandbox(settings.research_root),
        families_path=settings.extracted_families_path,
    )


def build_conflict_walker(
    settings: Settings,
    logger: StructuredLogger | None = None,
    *,
    observer: PipelineObserver | None = None,
    runtime: AgentRuntime | None = None,
    families: CorpusRepository | None = None,
) -> tuple[ConflictWalker, AgentRuntime, CorpusRepository]:
    if runtime is None or families is None:
        runtime, families = build_agent_runtime(settings, logger=logger)
    walker = ConflictWalker(
        runtime,
        families,
        logger=logger,
        check_timeout_s=settings.check_timeout_s,
        observer=observer or NoOpObserver(),
    )
    return walker, runtime, families


def build_post_graph_validator(
    settings: Settings,
    runtime: AgentRuntime,
    logger: StructuredLogger | None = None,
    *,
    observer: PipelineObserver | None = None,
) -> PostGraphValidator:
    return PostGraphValidator(
        runtime,
        MolecularAnalyzer(
            builder=MolecularBuilder(FragmentCatalog(settings.fragments_path)),
            config=settings.molecular_config(),
        ),
        logger=logger,
        observer=observer or NoOpObserver(),
    )


def build_route_pipeline(
    settings: Settings,
    logger: StructuredLogger,
    trace_dir: Path,
    *,
    observer: PipelineObserver | None = None,
) -> RoutePipeline:
    watch = observer or NoOpObserver()
    parser = build_parser(settings, observer=watch, logger=logger)
    walker, runtime, families = build_conflict_walker(settings, logger, observer=watch)
    return RoutePipeline(
        parser=parser,
        walker=walker,
        post_graph=build_post_graph_validator(
            settings, runtime, logger, observer=watch
        ),
        judge=FinalJudgeRunner(runtime, build_audit_ref(settings), logger=logger),
        assembler=RouteAssembler(),
        families=families,
        traces=TraceWriter(trace_dir),
        logger=logger,
        observer=watch,
        tracer=build_tracer(settings),
    )


def first_candidate_from_request(
    request: DesignRequest, families: CorpusRepository
) -> AgentCandidate:
    if not request.modifications:
        raise ValueError("request.modifications must not be empty")
    modification = request.modifications[0]
    bindings, _errors = families.bind_families(request)
    process = (
        bindings[0].process_ids[0]
        if bindings and bindings[0].process_ids
        else modification.family.value
    )
    return AgentCandidate(
        family=modification.family.value,
        site=modification.site,
        process=process,
    )


def objective_from_name(name: str) -> AgentObjective:
    return name  # type: ignore[return-value]
