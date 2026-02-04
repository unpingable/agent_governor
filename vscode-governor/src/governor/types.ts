/**
 * TypeScript interfaces mirroring Python governor.check types.
 *
 * All positions are 0-based to match VS Code conventions.
 */

export interface Position {
  line: number;
  character: number;
}

export interface Range {
  start: Position;
  end: Position;
}

export interface CheckFinding {
  code: string;
  message: string;
  severity: "error" | "warning" | "info";
  source: "security" | "continuity";
  range: Range;
  suggestion?: string;
}

export interface CheckResult {
  status: "pass" | "warn" | "error";
  findings: CheckFinding[];
  summary: string;
}

export interface CheckInput {
  content: string;
  filepath: string;
}

/**
 * Map governor severity strings to VS Code DiagnosticSeverity numeric values.
 * 0=Error, 1=Warning, 2=Information, 3=Hint
 */
export const SEVERITY_MAP: Record<string, number> = {
  error: 0,
  warning: 1,
  info: 2,
};

// =========================================================================
// Governor State types (for TreeView, matches `governor state --json`)
// =========================================================================

export interface GovernorProposal {
  id: string;
  state: "draft" | "proposed" | "verified" | "applied" | "rejected";
  claims: unknown[];
  created_at: string;
  receipts?: unknown[];
  rejection?: unknown;
  patch_path?: string | null;
}

export interface GovernorFact {
  id: string;
  claim: { type: string; describe?: string; [key: string]: unknown };
  receipt: unknown;
  created_at: string;
  file_hashes: Record<string, string>;
}

export interface GovernorDecision {
  id: string;
  claim: { type: string; topic?: string; choice?: string; [key: string]: unknown };
  created_at: string;
  rationale: string | null;
  supersedes: string | null;
}

export interface GovernorTask {
  id: string;
  task: string;
  agent_id: string;
  scope: string[];
  status: "active" | "completed" | "expired";
  started_at: string;
  expires_at: string;
  completed_at: string | null;
}

export interface GovernorRegime {
  current_regime: "elastic" | "warm" | "ductile" | "unstable";
  [key: string]: unknown;
}

export interface GovernorBoil {
  mode: string;
  regime: string;
  turn: number;
  turns_in_regime: number;
  events_count: number;
  preset: {
    claim_budget: number;
    novelty_tolerance: number;
    authority_posture: string;
    min_dwell: number;
    tripwires: Record<string, boolean>;
  };
  [key: string]: unknown;
}

export interface GovernorAutonomous {
  session_id: string;
  task: string;
  status: string;
  used: { tokens: number; iterations: number; elapsed_seconds: number; cost_usd: number };
  budget: { max_tokens?: number | null; max_iterations?: number | null; [key: string]: unknown };
  [key: string]: unknown;
}

export interface GovernorState {
  proposals: GovernorProposal[];
  facts: GovernorFact[];
  decisions: GovernorDecision[];
  tasks: GovernorTask[];
  regime: GovernorRegime | null;
  boil: GovernorBoil | null;
  autonomous: GovernorAutonomous[];
}

// =========================================================================
// Governor State V2 types (canonical ViewModel, `governor state --json --schema v2`)
// =========================================================================

export interface SessionView {
  mode: string;
  authority_level: string;
  active_constraints: string[];
  jurisdiction: string | null;
  active_profile: string | null;
}

export interface RegimeViewV2 {
  name: string;
  setpoints: Record<string, number>;
  telemetry: Record<string, number>;
  boil_mode: string | null;
  transitions: Array<{ from: string; to: string; turn?: number | null }>;
}

export interface DecisionView {
  id: string;
  status: "accepted" | "rejected" | "pending";
  type: string;
  rationale: string;
  dependencies: string[];
  violations: string[];
  source: string;
  created_at: string;
  raw: Record<string, unknown>;
}

export interface ClaimView {
  id: string;
  state: "proposed" | "stabilized" | "stale" | "contradicted";
  content: string;
  confidence: number;
  provenance: string;
  evidence_links: string[];
  conflicting_claims: string[];
  stability: Record<string, unknown>;
  created_at: string;
  raw: Record<string, unknown>;
}

export interface EvidenceView {
  id: string;
  type: string;
  source: string;
  scope: string;
  linked_claims: string[];
  validity: number;
  expiry: string | null;
}

export interface ViolationView {
  id: string;
  rule_breached: string;
  triggering_decision: string;
  severity: "low" | "medium" | "high" | "critical";
  enforced_outcome: string;
  resolution: string | null;
  source_system: string;
  detail: string;
}

export interface ExecutionActionView {
  id: string;
  description: string;
  status: string;
  detail: string;
}

export interface ExecutionView {
  pending: ExecutionActionView[];
  blocked: ExecutionActionView[];
  running: ExecutionActionView[];
  completed: ExecutionActionView[];
}

export interface StabilityView {
  rejection_rate: number;
  claim_churn: number;
  contradiction_density: number;
  drift_alert: string;
  drift_signals: Record<string, number>;
}

// =========================================================================
// Code Autopilot types (intent, profiles, overrides)
// =========================================================================

export interface IntentView {
  profile: string;
  scope: string[] | null;
  deny: string[] | null;
  timebox_minutes: number | null;
  reason: string | null;
  operator: string;
  source: string;
  set_at: string;
  expires_at: string | null;
}

export interface IntentProvenanceView {
  layer: string;
  source_path: string | null;
  value: IntentView | null;
  checked: boolean;
  reason: string | null;
}

export interface IntentResult {
  intent: IntentView;
  provenance: IntentProvenanceView[];
}

export interface OverrideView {
  id: string;
  anchor_id: string;
  reason: string;
  operator: string;
  scope: string[];
  created_at: string;
  expires_at: string;
  revoked: boolean;
  violation_snapshot: Record<string, unknown>;
}

export interface AutopilotProfile {
  name: string;
  description: string;
  violation_default: string;
  retry_budget: number;
}

export interface GovernorViewModelV2 {
  schema_version: "v2";
  generated_at: string;
  session: SessionView | null;
  regime: RegimeViewV2 | null;
  decisions: DecisionView[];
  claims: ClaimView[];
  evidence: EvidenceView[];
  violations: ViolationView[];
  execution: ExecutionView | null;
  stability: StabilityView | null;
}

/**
 * Type guard: check if state response is V2 schema.
 */
export function isV2(state: GovernorState | GovernorViewModelV2): state is GovernorViewModelV2 {
  return "schema_version" in state && (state as GovernorViewModelV2).schema_version === "v2";
}
