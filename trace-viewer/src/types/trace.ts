export type StateStatus = "pass" | "fail" | "degraded";

export type LLMObjective =
  | "structure_request"
  | "check_compatibility"
  | "check_intent"
  | "final_judge"
  | string;

export type LLMStage = "validate" | "walk" | "post_graph" | string;

export type JsonObject = Record<string, unknown>;

export interface ToolCall {
  tool: string;
  args: JsonObject;
  result_snippet: string;
  truncated: boolean;
}

export interface LLMCall {
  call_id: string;
  model: string;
  objective: LLMObjective;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  cache: JsonObject;
  tool_calls: ToolCall[];
  stage: LLMStage | null;
}

export interface CostBreakdown {
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  calls: number;
}

export interface CostReport {
  phases: Record<string, CostBreakdown>;
  objectives: Record<string, CostBreakdown>;
  total: CostBreakdown;
}

export interface Provenance {
  kind: string;
  ref: string | null;
  refs: string[] | null;
  source: string | null;
  basis: string | null;
}

export interface AgentFinding {
  kind: string;
  description: string;
  affected: string[];
}

export interface AgentResult {
  objective: string | null;
  passed: boolean | null;
  resolution: string | null;
  findings: AgentFinding[];
  gaps: string[];
  confidence: string | null;
  citations: Provenance[];
  unknowns: string[];
  llm_call: LLMCall | null;
}

export interface AgentCandidate {
  family: string;
  site: string;
  process: string;
}

export interface ProcessTrace {
  family: string;
  site: string;
  process: string;
  modification_ref: number | null;
  passed: boolean | null;
}

export interface StateLedger {
  protected?: Record<string, string>;
  free_amines?: Record<string, string>;
  catalysts_used?: Record<string, string>;
  termini?: Record<string, string>;
  history?: ProcessTrace[];
  applied?: ProcessTrace | JsonObject;
  permanent_connectivity?: JsonObject[];
  product_fragments?: JsonObject[];
  residue_overrides?: Record<string, string>;
  n_methyl_sites?: string[];
  product_unknowns?: string[];
  [key: string]: unknown;
}

export interface TraceState {
  id: string;
  node_type: string;
  parents: string[];
  modification_ref: number | null;
  status: StateStatus | string;
  output: StateLedger;
  building_block: string | null;
  sequence_snapshot: string | null;
  route_step: JsonObject | null;
  errors: JsonObject[];
  provenance: Provenance[];
  llm_calls: LLMCall[];
}

export interface ConflictNodeReport {
  id: string;
  children: string[];
  state: TraceState;
  candidate: AgentCandidate | null;
  agent_result: AgentResult | null;
}

export interface ConflictTreeReport {
  request_id: string;
  root_id: string;
  surviving_ids: string[];
  nodes: ConflictNodeReport[];
  cost: CostReport;
}

export interface ModificationRequest {
  family: string;
  site: string;
  detail: string | null;
}

export interface DesignRequest {
  request_id: string;
  parent_name: string;
  sequence: string;
  parent_c_terminus: string;
  residue_annotations: Record<string, string>;
  parent_features: string[];
  modifications: ModificationRequest[];
  intent: string;
}

export interface SiteMapEntry {
  requested: string;
  resolved: string;
  residue: string | null;
  note: string | null;
}

export interface ValidationResult {
  request_id: string;
  state: TraceState;
  residues: JsonObject[];
  sites_resolved: JsonObject[];
  parent_c_terminus: string;
  parent_features: string[];
  residue_annotations: Record<string, string>;
  occupancy: unknown;
  intent: string;
  family_bindings: JsonObject[];
  resolved_sequence: string | null;
  resolved_annotations: Record<string, string>;
  index_map: JsonObject[];
  site_map: SiteMapEntry[];
  conflicts: JsonObject[];
  unknowns: string[];
}

export interface RouteStep {
  step: number;
  stage: string;
  operation: string;
  provenance: Provenance[];
}

export interface RouteConflict {
  severity: string;
  kind: string;
  description: string;
  affected: string[];
  resolution: string | null;
  provenance: Provenance[];
}

export interface RouteVerdict {
  request_id: string;
  verdict: string;
  confidence: string;
  resolved_sequence: string | null;
  resolved_annotations: Record<string, string>;
  site_map: SiteMapEntry[];
  route: RouteStep[];
  conflicts: RouteConflict[];
  unknowns: string[];
}

export interface TwoDValidation {
  valid: boolean;
  formula: string | null;
  exact_mw: number | null;
  smiles: string | null;
  issues: JsonObject[];
}

export interface CandidateMolecularValidation {
  node_id: string;
  two_d: TwoDValidation | null;
  descriptors: JsonObject | null;
  ensemble: JsonObject | null;
  recipe: JsonObject | null;
  fragments: JsonObject[];
  unknowns: string[];
}

export interface CandidatePostGraphResult {
  node_id: string;
  candidate: AgentCandidate | null;
  molecular: CandidateMolecularValidation | null;
  intent: AgentResult | null;
  rank: number[];
}

export interface PostGraphValidationReport {
  request_id: string;
  surviving_ids: string[];
  selected_id: string | null;
  tied_ids: string[];
  unknowns: string[];
  candidates: CandidatePostGraphResult[];
  extra: JsonObject;
  cost?: CostReport;
}

export interface PipelineTrace {
  request_id: string;
  request: DesignRequest;
  validation: ValidationResult;
  tree: ConflictTreeReport;
  post_graph: PostGraphValidationReport;
  judge: AgentResult | null;
  verdict: RouteVerdict;
  cost: CostReport;
  llm_calls: LLMCall[];
}

export const REQUIRED_TRACE_FIELDS = [
  "request_id",
  "request",
  "validation",
  "tree",
  "post_graph",
  "verdict",
  "cost",
] as const;
