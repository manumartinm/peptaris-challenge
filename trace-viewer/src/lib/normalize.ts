import type {
  AgentCandidate,
  AgentFinding,
  AgentResult,
  CandidateMolecularValidation,
  CandidatePostGraphResult,
  ConflictNodeReport,
  ConflictTreeReport,
  CostBreakdown,
  CostReport,
  DesignRequest,
  LLMCall,
  ModificationRequest,
  PipelineTrace,
  PostGraphValidationReport,
  ProcessTrace,
  Provenance,
  RouteConflict,
  RouteStep,
  RouteVerdict,
  SiteMapEntry,
  StateLedger,
  ToolCall,
  TraceState,
  TwoDValidation,
  ValidationResult,
} from "../types/trace";
import {
  asBooleanOrNull,
  asNumber,
  asObjectArray,
  asRecord,
  asString,
  asStringArray,
  asStringMap,
  asStringOrNull,
  isRecord,
} from "./guards";

function emptyCost(): CostBreakdown {
  return { cost_usd: 0, input_tokens: 0, output_tokens: 0, calls: 0 };
}

function normalizeCostBreakdown(value: unknown): CostBreakdown {
  const record = asRecord(value);
  return {
    cost_usd: asNumber(record.cost_usd),
    input_tokens: asNumber(record.input_tokens),
    output_tokens: asNumber(record.output_tokens),
    calls: asNumber(record.calls),
  };
}

export function normalizeCost(value: unknown): CostReport {
  const record = asRecord(value);
  const phases = asRecord(record.phases);
  const objectives = asRecord(record.objectives);
  return {
    phases: Object.fromEntries(
      Object.entries(phases).map(([key, item]) => [key, normalizeCostBreakdown(item)]),
    ),
    objectives: Object.fromEntries(
      Object.entries(objectives).map(([key, item]) => [key, normalizeCostBreakdown(item)]),
    ),
    total: record.total ? normalizeCostBreakdown(record.total) : emptyCost(),
  };
}

function resolveStage(objective: string, stage: unknown): string | null {
  if (typeof stage === "string" && stage.length > 0) return stage;
  if (objective === "structure_request") return "validate";
  if (objective === "check_intent" || objective === "final_judge") return "post_graph";
  if (objective === "check_compatibility") return "walk";
  return null;
}

function normalizeToolCall(value: unknown): ToolCall {
  const record = asRecord(value);
  return {
    tool: asString(record.tool, "unknown"),
    args: asRecord(record.args),
    result_snippet: asString(record.result_snippet),
    truncated: Boolean(record.truncated),
  };
}

export function normalizeLLMCall(value: unknown): LLMCall {
  const record = asRecord(value);
  const objective = asString(record.objective, "unknown");
  return {
    call_id: asString(record.call_id, "unknown"),
    model: asString(record.model, "unknown"),
    objective,
    input_tokens: asNumber(record.input_tokens),
    output_tokens: asNumber(record.output_tokens),
    cost_usd: asNumber(record.cost_usd),
    cache: asRecord(record.cache),
    tool_calls: asObjectArray(record.tool_calls).map(normalizeToolCall),
    stage: resolveStage(objective, record.stage),
  };
}

function normalizeProvenance(value: unknown): Provenance {
  const record = asRecord(value);
  return {
    kind: asString(record.kind, "unknown"),
    ref: asStringOrNull(record.ref),
    refs: Array.isArray(record.refs) ? asStringArray(record.refs) : null,
    source: asStringOrNull(record.source),
    basis: asStringOrNull(record.basis),
  };
}

function normalizeFinding(value: unknown): AgentFinding {
  const record = asRecord(value);
  return {
    kind: asString(record.kind, "unknown"),
    description: asString(record.description),
    affected: asStringArray(record.affected),
  };
}

export function normalizeAgentResult(value: unknown): AgentResult | null {
  if (!isRecord(value)) return null;
  return {
    objective: asStringOrNull(value.objective),
    passed: asBooleanOrNull(value.passed),
    resolution: asStringOrNull(value.resolution),
    findings: asObjectArray(value.findings).map(normalizeFinding),
    gaps: asStringArray(value.gaps),
    confidence: asStringOrNull(value.confidence),
    citations: asObjectArray(value.citations).map(normalizeProvenance),
    unknowns: asStringArray(value.unknowns),
    llm_call: value.llm_call ? normalizeLLMCall(value.llm_call) : null,
  };
}

function normalizeCandidate(value: unknown): AgentCandidate | null {
  if (!isRecord(value)) return null;
  return {
    family: asString(value.family, "unknown"),
    site: asString(value.site, "unknown"),
    process: asString(value.process, "unknown"),
  };
}

function normalizeProcess(value: unknown): ProcessTrace {
  const record = asRecord(value);
  return {
    family: asString(record.family, "unknown"),
    site: asString(record.site, "unknown"),
    process: asString(record.process, "unknown"),
    modification_ref:
      typeof record.modification_ref === "number" ? record.modification_ref : null,
    passed: asBooleanOrNull(record.passed),
  };
}

function normalizeLedger(value: unknown): StateLedger {
  const record = asRecord(value);
  const ledger: StateLedger = { ...record };
  if (record.protected) ledger.protected = asStringMap(record.protected);
  if (record.free_amines) ledger.free_amines = asStringMap(record.free_amines);
  if (record.catalysts_used) ledger.catalysts_used = asStringMap(record.catalysts_used);
  if (record.termini) ledger.termini = asStringMap(record.termini);
  if (record.history) ledger.history = asObjectArray(record.history).map(normalizeProcess);
  if (record.permanent_connectivity) {
    ledger.permanent_connectivity = asObjectArray(record.permanent_connectivity);
  }
  if (record.product_fragments) {
    ledger.product_fragments = asObjectArray(record.product_fragments);
  }
  if (record.residue_overrides) {
    ledger.residue_overrides = asStringMap(record.residue_overrides);
  }
  if (record.n_methyl_sites) ledger.n_methyl_sites = asStringArray(record.n_methyl_sites);
  if (record.product_unknowns) ledger.product_unknowns = asStringArray(record.product_unknowns);
  return ledger;
}

function normalizeState(value: unknown, fallbackId: string): TraceState {
  const record = asRecord(value);
  return {
    id: asString(record.id, fallbackId),
    node_type: asString(record.node_type, "unknown"),
    parents: asStringArray(record.parents),
    modification_ref:
      typeof record.modification_ref === "number" ? record.modification_ref : null,
    status: asString(record.status, "unknown"),
    output: normalizeLedger(record.output),
    building_block: asStringOrNull(record.building_block),
    sequence_snapshot: asStringOrNull(record.sequence_snapshot),
    route_step: isRecord(record.route_step) ? record.route_step : null,
    errors: asObjectArray(record.errors),
    provenance: asObjectArray(record.provenance).map(normalizeProvenance),
    llm_calls: asObjectArray(record.llm_calls).map(normalizeLLMCall),
  };
}

function normalizeNode(value: unknown, index: number): ConflictNodeReport {
  const record = asRecord(value);
  const id = asString(record.id, `node_${index}`);
  return {
    id,
    children: asStringArray(record.children),
    state: normalizeState(record.state, id),
    candidate: normalizeCandidate(record.candidate),
    agent_result: normalizeAgentResult(record.agent_result),
  };
}

function normalizeSiteMap(value: unknown): SiteMapEntry[] {
  return asObjectArray(value).map((entry) => ({
    requested: asString(entry.requested),
    resolved: asString(entry.resolved),
    residue: asStringOrNull(entry.residue),
    note: asStringOrNull(entry.note),
  }));
}

function normalizeRequest(value: unknown, requestId: string): DesignRequest {
  const record = asRecord(value);
  return {
    request_id: asString(record.request_id, requestId),
    parent_name: asString(record.parent_name, "unknown"),
    sequence: asString(record.sequence),
    parent_c_terminus: asString(record.parent_c_terminus, "unknown"),
    residue_annotations: asStringMap(record.residue_annotations),
    parent_features: asStringArray(record.parent_features),
    modifications: asObjectArray(record.modifications).map(
      (item): ModificationRequest => ({
        family: asString(item.family, "unknown"),
        site: asString(item.site, "unknown"),
        detail: asStringOrNull(item.detail),
      }),
    ),
    intent: asString(record.intent),
  };
}

function normalizeValidation(value: unknown, requestId: string): ValidationResult {
  const record = asRecord(value);
  return {
    request_id: asString(record.request_id, requestId),
    state: normalizeState(record.state, "state_0"),
    residues: asObjectArray(record.residues),
    sites_resolved: asObjectArray(record.sites_resolved),
    parent_c_terminus: asString(record.parent_c_terminus, "unknown"),
    parent_features: asStringArray(record.parent_features),
    residue_annotations: asStringMap(record.residue_annotations),
    occupancy: record.occupancy ?? null,
    intent: asString(record.intent),
    family_bindings: asObjectArray(record.family_bindings),
    resolved_sequence: asStringOrNull(record.resolved_sequence),
    resolved_annotations: asStringMap(record.resolved_annotations),
    index_map: asObjectArray(record.index_map),
    site_map: normalizeSiteMap(record.site_map),
    conflicts: asObjectArray(record.conflicts),
    unknowns: asStringArray(record.unknowns),
  };
}

function normalizeTree(value: unknown, requestId: string): ConflictTreeReport {
  const record = asRecord(value);
  const nodes = asObjectArray(record.nodes).map(normalizeNode);
  return {
    request_id: asString(record.request_id, requestId),
    root_id: asString(record.root_id, nodes[0]?.id ?? "state_0"),
    surviving_ids: asStringArray(record.surviving_ids),
    nodes,
    cost: normalizeCost(record.cost),
  };
}

function normalizeTwoD(value: unknown): TwoDValidation | null {
  if (!isRecord(value)) return null;
  return {
    valid: Boolean(value.valid),
    formula: asStringOrNull(value.formula),
    exact_mw: typeof value.exact_mw === "number" ? value.exact_mw : null,
    smiles: asStringOrNull(value.smiles),
    issues: asObjectArray(value.issues),
  };
}

function normalizeMolecular(value: unknown, nodeId: string): CandidateMolecularValidation | null {
  if (!isRecord(value)) return null;
  return {
    node_id: asString(value.node_id, nodeId),
    two_d: normalizeTwoD(value.two_d),
    descriptors: isRecord(value.descriptors) ? value.descriptors : null,
    ensemble: isRecord(value.ensemble) ? value.ensemble : null,
    recipe: isRecord(value.recipe) ? value.recipe : null,
    fragments: asObjectArray(value.fragments),
    unknowns: asStringArray(value.unknowns),
  };
}

function normalizePostGraph(value: unknown, requestId: string): PostGraphValidationReport {
  const record = asRecord(value);
  return {
    request_id: asString(record.request_id, requestId),
    surviving_ids: asStringArray(record.surviving_ids),
    selected_id: asStringOrNull(record.selected_id),
    tied_ids: asStringArray(record.tied_ids),
    unknowns: asStringArray(record.unknowns),
    candidates: asObjectArray(record.candidates).map((item): CandidatePostGraphResult => {
      const nodeId = asString(item.node_id, "unknown");
      return {
        node_id: nodeId,
        candidate: normalizeCandidate(item.candidate),
        molecular: normalizeMolecular(item.molecular, nodeId),
        intent: normalizeAgentResult(item.intent),
        rank: Array.isArray(item.rank)
          ? item.rank.filter((entry): entry is number => typeof entry === "number")
          : [],
      };
    }),
    extra: asRecord(record.extra),
    cost: record.cost ? normalizeCost(record.cost) : undefined,
  };
}

function normalizeVerdict(value: unknown, requestId: string): RouteVerdict {
  const record = asRecord(value);
  return {
    request_id: asString(record.request_id, requestId),
    verdict: asString(record.verdict, "unknown"),
    confidence: asString(record.confidence, "unknown"),
    resolved_sequence: asStringOrNull(record.resolved_sequence),
    resolved_annotations: asStringMap(record.resolved_annotations),
    site_map: normalizeSiteMap(record.site_map),
    route: asObjectArray(record.route).map(
      (item): RouteStep => ({
        step: asNumber(item.step),
        stage: asString(item.stage, "unknown"),
        operation: asString(item.operation),
        provenance: asObjectArray(item.provenance).map(normalizeProvenance),
      }),
    ),
    conflicts: asObjectArray(record.conflicts).map(
      (item): RouteConflict => ({
        severity: asString(item.severity, "unknown"),
        kind: asString(item.kind, "unknown"),
        description: asString(item.description),
        affected: asStringArray(item.affected),
        resolution: asStringOrNull(item.resolution),
        provenance: asObjectArray(item.provenance).map(normalizeProvenance),
      }),
    ),
    unknowns: asStringArray(record.unknowns),
  };
}

export function normalizeTrace(raw: Record<string, unknown>): PipelineTrace {
  const requestId = asString(raw.request_id, "unknown");
  return {
    request_id: requestId,
    request: normalizeRequest(raw.request, requestId),
    validation: normalizeValidation(raw.validation, requestId),
    tree: normalizeTree(raw.tree, requestId),
    post_graph: normalizePostGraph(raw.post_graph, requestId),
    judge: normalizeAgentResult(raw.judge),
    verdict: normalizeVerdict(raw.verdict, requestId),
    cost: normalizeCost(raw.cost),
    llm_calls: asObjectArray(raw.llm_calls).map(normalizeLLMCall),
  };
}
