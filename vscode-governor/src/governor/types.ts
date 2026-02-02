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
