/**
 * TreeDataProvider for the Governor side panel.
 *
 * Renders the V2 GovernorViewModel schema: session, regime, decisions, claims,
 * evidence, violations, execution, stability.
 */

import * as vscode from "vscode";
import { fetchState, GovernorOptions } from "../governor/client";
import type {
  GovernorViewModelV2,
  DecisionView,
  ClaimView,
  EvidenceView,
  ViolationView,
  ExecutionView,
  StabilityView,
} from "../governor/types";

// =========================================================================
// Internal tree node type
// =========================================================================

export interface TreeNodeData {
  kind: string;
  label: string;
  description?: string;
  tooltip?: string;
  collapsible: boolean;
  icon?: string;
  children?: TreeNodeData[];
  /** JSON detail string shown in output channel on click */
  detail?: string;
}

// =========================================================================
// Icon helpers
// =========================================================================

const REGIME_ICONS: Record<string, string> = {
  elastic: "shield",
  warm: "warning",
  ductile: "flame",
  unstable: "error",
};

const DECISION_ICONS: Record<string, string> = {
  accepted: "check-all",
  rejected: "close",
  pending: "clock",
};

const CLAIM_ICONS: Record<string, string> = {
  stabilized: "check",
  proposed: "question",
  stale: "clock",
  contradicted: "close",
};

const VIOLATION_SEVERITY_ICONS: Record<string, string> = {
  low: "info",
  medium: "warning",
  high: "error",
  critical: "alert",
};

// =========================================================================
// GovernorTreeProvider
// =========================================================================

export class GovernorTreeProvider
  implements vscode.TreeDataProvider<TreeNodeData>, vscode.Disposable
{
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeNodeData | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private state: GovernorViewModelV2 | null = null;
  private error: string | null = null;

  constructor(
    private outputChannel: vscode.OutputChannel,
    private getOptions: () => GovernorOptions
  ) {}

  dispose(): void {
    this._onDidChangeTreeData.dispose();
  }

  async refresh(): Promise<void> {
    try {
      this.state = await fetchState(this.getOptions());
      this.error = null;
    } catch (err: unknown) {
      this.state = null;
      this.error = err instanceof Error ? err.message : String(err);
    }
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: TreeNodeData): vscode.TreeItem {
    const item = new vscode.TreeItem(
      element.label,
      element.collapsible
        ? vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.None
    );

    if (element.description) {
      item.description = element.description;
    }
    if (element.tooltip) {
      item.tooltip = element.tooltip;
    }
    if (element.icon) {
      item.iconPath = new vscode.ThemeIcon(element.icon);
    }
    if (element.detail) {
      item.command = {
        command: "governor.showDetail",
        title: "Show Detail",
        arguments: [element.detail],
      };
    }

    return item;
  }

  getChildren(element?: TreeNodeData): TreeNodeData[] {
    if (element) {
      return element.children ?? [];
    }

    // Root level
    if (this.error) {
      return [
        {
          kind: "error",
          label: "Error loading state",
          description: this.error,
          collapsible: false,
          icon: "error",
        },
      ];
    }

    if (!this.state) {
      return [
        {
          kind: "loading",
          label: "Loading...",
          collapsible: false,
          icon: "loading~spin",
        },
      ];
    }

    const nodes: TreeNodeData[] = [];
    nodes.push(this.buildSessionNode(this.state));
    nodes.push(this.buildRegimeNode(this.state));
    nodes.push(this.buildDecisionsNode(this.state));
    nodes.push(this.buildClaimsNode(this.state));

    const evidenceNode = this.buildEvidenceNode(this.state);
    if (evidenceNode) {
      nodes.push(evidenceNode);
    }

    const violationsNode = this.buildViolationsNode(this.state);
    if (violationsNode) {
      nodes.push(violationsNode);
    }

    const executionNode = this.buildExecutionNode(this.state);
    if (executionNode) {
      nodes.push(executionNode);
    }

    nodes.push(this.buildStabilityNode(this.state));

    return nodes;
  }

  // -----------------------------------------------------------------------
  // V2 Builder methods
  // -----------------------------------------------------------------------

  buildSessionNode(s: GovernorViewModelV2): TreeNodeData {
    const children: TreeNodeData[] = [];

    if (s.session) {
      children.push({
        kind: "session-mode",
        label: `Mode: ${s.session.mode.toUpperCase()}`,
        collapsible: false,
        icon: s.session.mode === "strict" ? "lock" : "unlock",
      });
      children.push({
        kind: "session-authority",
        label: `Authority: ${s.session.authority_level}`,
        collapsible: false,
        icon: "shield",
      });
      if (s.session.jurisdiction) {
        children.push({
          kind: "session-jurisdiction",
          label: `Jurisdiction: ${s.session.jurisdiction.toUpperCase()}`,
          collapsible: false,
          icon: "globe",
        });
      }
      if (s.session.active_profile) {
        children.push({
          kind: "session-profile",
          label: `Profile: ${s.session.active_profile}`,
          collapsible: false,
          icon: "account",
        });
      }
      if (s.session.active_constraints.length > 0) {
        children.push({
          kind: "session-constraints",
          label: `Constraints: ${s.session.active_constraints.join(", ")}`,
          collapsible: false,
          icon: "list-filter",
        });
      }
    }

    return {
      kind: "session",
      label: "Governor Session",
      collapsible: true,
      icon: "pulse",
      children,
      detail: s.session ? JSON.stringify(s.session, null, 2) : undefined,
    };
  }

  buildRegimeNode(s: GovernorViewModelV2): TreeNodeData {
    const children: TreeNodeData[] = [];

    if (s.regime) {
      const regime = s.regime.name;
      children.push({
        kind: "regime",
        label: `Regime: ${regime.toUpperCase()}`,
        collapsible: false,
        icon: REGIME_ICONS[regime] ?? "shield",
      });

      if (s.regime.boil_mode) {
        children.push({
          kind: "boil",
          label: `Boil: ${s.regime.boil_mode.toUpperCase()}`,
          collapsible: false,
          icon: "beaker",
        });
      }

      const telemetryParts: string[] = [];
      for (const [key, val] of Object.entries(s.regime.telemetry)) {
        telemetryParts.push(`${key} ${val.toFixed(2)}`);
      }
      if (telemetryParts.length > 0) {
        children.push({
          kind: "telemetry",
          label: `Telemetry: ${telemetryParts.join(", ")}`,
          collapsible: false,
          icon: "graph-line",
        });
      }
    }

    return {
      kind: "regime-section",
      label: s.regime ? `Regime: ${s.regime.name.toUpperCase()}` : "Regime",
      collapsible: true,
      icon: s.regime ? (REGIME_ICONS[s.regime.name] ?? "shield") : "shield",
      children,
      detail: s.regime ? JSON.stringify(s.regime, null, 2) : undefined,
    };
  }

  buildDecisionsNode(s: GovernorViewModelV2): TreeNodeData {
    const children: TreeNodeData[] = s.decisions.map((d: DecisionView) => ({
      kind: "decision",
      label: `[${d.status.toUpperCase()}] ${d.id} — ${d.type}`,
      description: d.rationale ? d.rationale.slice(0, 40) : undefined,
      collapsible: false,
      icon: DECISION_ICONS[d.status] ?? "law",
      detail: JSON.stringify(d, null, 2),
    }));

    return {
      kind: "decisions",
      label: `Decisions (${s.decisions.length})`,
      collapsible: true,
      icon: "law",
      children,
    };
  }

  buildClaimsNode(s: GovernorViewModelV2): TreeNodeData {
    const children: TreeNodeData[] = s.claims.map((c: ClaimView) => ({
      kind: "claim",
      label: `[${c.state.toUpperCase()}] ${c.content}`,
      description: `(${c.confidence.toFixed(2)})`,
      collapsible: false,
      icon: CLAIM_ICONS[c.state] ?? "question",
      detail: JSON.stringify(c, null, 2),
    }));

    return {
      kind: "claims",
      label: `Claims (${s.claims.length})`,
      collapsible: true,
      icon: "symbol-string",
      children,
    };
  }

  buildEvidenceNode(s: GovernorViewModelV2): TreeNodeData | null {
    if (s.evidence.length === 0) {
      return null;
    }

    const children: TreeNodeData[] = s.evidence.map((e: EvidenceView) => ({
      kind: "evidence",
      label: `[${e.type}] ${e.source || e.scope}`,
      description: `${e.linked_claims.length} claim(s)`,
      collapsible: false,
      icon: "file-symlink-file",
      detail: JSON.stringify(e, null, 2),
    }));

    return {
      kind: "evidence-section",
      label: `Evidence (${s.evidence.length})`,
      collapsible: true,
      icon: "file-symlink-file",
      children,
    };
  }

  buildViolationsNode(s: GovernorViewModelV2): TreeNodeData | null {
    if (s.violations.length === 0) {
      return null;
    }

    const children: TreeNodeData[] = s.violations.map((v: ViolationView) => ({
      kind: "violation",
      label: `[${v.severity.toUpperCase()}] ${v.rule_breached}`,
      description: v.detail ? v.detail.slice(0, 40) : undefined,
      collapsible: false,
      icon: VIOLATION_SEVERITY_ICONS[v.severity] ?? "warning",
      detail: JSON.stringify(v, null, 2),
    }));

    return {
      kind: "violations",
      label: `Violations (${s.violations.length})`,
      collapsible: true,
      icon: "alert",
      children,
    };
  }

  buildExecutionNode(s: GovernorViewModelV2): TreeNodeData | null {
    if (!s.execution) {
      return null;
    }

    const ex = s.execution;
    const children: TreeNodeData[] = [];

    if (ex.pending.length > 0) {
      children.push({
        kind: "exec-pending",
        label: `Pending: ${ex.pending.length}`,
        collapsible: false,
        icon: "clock",
      });
    }
    if (ex.blocked.length > 0) {
      children.push({
        kind: "exec-blocked",
        label: `Blocked: ${ex.blocked.length}`,
        collapsible: false,
        icon: "close",
      });
    }
    if (ex.running.length > 0) {
      children.push({
        kind: "exec-running",
        label: `Running: ${ex.running.length}`,
        collapsible: false,
        icon: "sync~spin",
      });
    }
    if (ex.completed.length > 0) {
      children.push({
        kind: "exec-completed",
        label: `Completed: ${ex.completed.length}`,
        collapsible: false,
        icon: "check",
      });
    }

    return {
      kind: "execution",
      label: "Execution",
      collapsible: true,
      icon: "play",
      children,
      detail: JSON.stringify(ex, null, 2),
    };
  }

  buildStabilityNode(s: GovernorViewModelV2): TreeNodeData {
    const children: TreeNodeData[] = [];

    if (s.stability) {
      const st = s.stability;
      children.push({
        kind: "stability-rejection",
        label: `Rejection rate: ${st.rejection_rate.toFixed(2)}`,
        collapsible: false,
        icon: "graph-line",
      });
      children.push({
        kind: "stability-churn",
        label: `Claim churn: ${st.claim_churn.toFixed(2)}`,
        collapsible: false,
        icon: "graph-line",
      });
      children.push({
        kind: "stability-drift",
        label: `Drift: ${st.drift_alert}`,
        collapsible: false,
        icon: st.drift_alert === "NONE" ? "check" : "warning",
      });
    }

    return {
      kind: "stability",
      label: "Stability",
      collapsible: true,
      icon: "graph-line",
      children,
      detail: s.stability ? JSON.stringify(s.stability, null, 2) : undefined,
    };
  }
}
