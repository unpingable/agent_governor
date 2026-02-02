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
