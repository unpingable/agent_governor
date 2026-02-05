/**
 * TreeDataProvider for the Governor side panel.
 *
 * Renders the V2 GovernorViewModel schema: session, regime, decisions, claims,
 * evidence, violations, execution, stability.
 */

import * as vscode from "vscode";
import { fetchState, getIntent, listOverrides, runCodeCompare, GovernorOptions } from "../governor/client";
import type {
  GovernorViewModelV2,
  DecisionView,
  ClaimView,
  EvidenceView,
  ViolationView,
  ExecutionView,
  StabilityView,
  IntentResult,
  OverrideView,
  CodeDivergenceReportView,
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

const PROFILE_ICONS: Record<string, string> = {
  greenfield: "beaker",       // Experimenting
  established: "shield",      // Normal (default)
  production: "lock",         // Strict
  hotfix: "flame",            // Urgent
  refactor: "tools",          // Restructuring
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
  private intent: IntentResult | null = null;
  private overrides: OverrideView[] = [];
  private compareReport: CodeDivergenceReportView | null = null;
  private error: string | null = null;

  constructor(
    private outputChannel: vscode.OutputChannel,
    private getOptions: () => GovernorOptions
  ) {}

  /**
   * Get the current intent (for status bar integration).
   */
  getIntent(): IntentResult | null {
    return this.intent;
  }

  dispose(): void {
    this._onDidChangeTreeData.dispose();
  }

  async refresh(): Promise<void> {
    try {
      // Fetch all state in parallel
      const opts = this.getOptions();
      const [stateResult, intentResult, overridesResult, compareResult] = await Promise.allSettled([
        fetchState(opts),
        getIntent(opts),
        listOverrides(opts),
        runCodeCompare(opts),
      ]);

      this.state = stateResult.status === "fulfilled" ? stateResult.value : null;
      this.intent = intentResult.status === "fulfilled" ? intentResult.value : null;
      this.overrides = overridesResult.status === "fulfilled" ? overridesResult.value : [];
      this.compareReport = compareResult.status === "fulfilled" ? compareResult.value : null;

      // Only set error if state fetch failed (intent/overrides are optional)
      this.error = stateResult.status === "rejected"
        ? (stateResult.reason instanceof Error ? stateResult.reason.message : String(stateResult.reason))
        : null;
    } catch (err: unknown) {
      this.state = null;
      this.intent = null;
      this.overrides = [];
      this.compareReport = null;
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

    // Per UX spec: Problems first (expanded if any), then Intent, then Decisions
    const violationsNode = this.buildViolationsNode(this.state);
    if (violationsNode) {
      nodes.push(violationsNode);
    }

    // Code Autopilot: Intent section (prominently displayed)
    nodes.push(this.buildIntentNode());

    // Code Interferometry: Compare section (if a report exists)
    const compareNode = this.buildCompareNode();
    if (compareNode) {
      nodes.push(compareNode);
    }

    nodes.push(this.buildDecisionsNode(this.state));
    nodes.push(this.buildClaimsNode(this.state));

    // Collapsed by default: Recent, Checks, Advanced
    const evidenceNode = this.buildEvidenceNode(this.state);
    if (evidenceNode) {
      nodes.push(evidenceNode);
    }

    const executionNode = this.buildExecutionNode(this.state);
    if (executionNode) {
      nodes.push(executionNode);
    }

    // Advanced section (collapsed)
    nodes.push(this.buildSessionNode(this.state));
    nodes.push(this.buildRegimeNode(this.state));
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
    const children: TreeNodeData[] = s.decisions.map((d: DecisionView) => {
      // Human-friendly: show topic: choice, not ID
      const topic = (d.raw?.topic as string) ?? d.type;
      const choice = (d.raw?.choice as string) ?? "";
      const displayLabel = choice ? `${topic}: ${choice}` : topic;

      return {
        kind: "decision",
        label: displayLabel,
        description: d.rationale ? `"${d.rationale.slice(0, 40)}"` : undefined,
        collapsible: false,
        icon: "pin",  // More friendly than "law"
        detail: JSON.stringify(d, null, 2),
      };
    });

    // Human-friendly empty state
    if (children.length === 0) {
      children.push({
        kind: "decision-empty",
        label: "No decisions yet",
        description: "Add decisions to catch contradictions",
        collapsible: false,
        icon: "info",
      });
    }

    return {
      kind: "decisions",
      label: `Decisions (${s.decisions.length})`,
      collapsible: true,
      icon: "pin",
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
    // Rename to "Problems" for user-friendliness
    const children: TreeNodeData[] = s.violations.map((v: ViolationView) => ({
      kind: "violation",
      // Human-friendly: "You said X" framing
      label: v.rule_breached,
      description: v.detail ? v.detail.slice(0, 40) : undefined,
      collapsible: false,
      icon: VIOLATION_SEVERITY_ICONS[v.severity] ?? "warning",
      detail: JSON.stringify(v, null, 2),
    }));

    // Always show Problems section (even if empty)
    if (children.length === 0) {
      return {
        kind: "problems",
        label: "Problems (0)",
        description: "All good",
        collapsible: false,
        icon: "check",
        children: [],
      };
    }

    return {
      kind: "problems",
      label: `Problems (${s.violations.length})`,
      // Expand if there are problems
      collapsible: true,
      icon: "warning",
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

  // -----------------------------------------------------------------------
  // Code Autopilot: Intent section
  // -----------------------------------------------------------------------

  // -----------------------------------------------------------------------
  // Code Interferometry: Compare section
  // -----------------------------------------------------------------------

  buildCompareNode(): TreeNodeData | null {
    if (!this.compareReport) {
      return null;
    }

    const report = this.compareReport;
    const markers = report.risk_marker_union || [];
    const conflicts = report.anchor_conflicts || [];
    const children: TreeNodeData[] = [];

    // Tier
    children.push({
      kind: "compare-tier",
      label: `Tier: ${report.tier}`,
      collapsible: false,
      icon: report.tier >= 1 ? "warning" : "check",
    });

    // Risk markers (union lens)
    if (markers.length > 0) {
      const markerChildren: TreeNodeData[] = markers.map((m) => ({
        kind: "compare-marker",
        label: `${m.marker_type}: ${m.message}`,
        description: `(${m.model_id})`,
        collapsible: false,
        icon: m.category === "security" ? "error" : "warning",
        tooltip: `${m.category} marker at ${m.file_path}:${m.line_number}`,
      }));

      children.push({
        kind: "compare-markers",
        label: `Markers (${markers.length})`,
        collapsible: true,
        icon: "list-unordered",
        children: markerChildren,
      });
    }

    // Anchor conflicts
    if (conflicts.length > 0) {
      const conflictChildren: TreeNodeData[] = conflicts.map((c) => ({
        kind: "compare-conflict",
        label: `${c.anchor_id} (${c.conflict_type})`,
        description: c.description.slice(0, 50),
        collapsible: false,
        icon: c.conflict_type === "hard" ? "error" : "warning",
      }));

      children.push({
        kind: "compare-conflicts",
        label: `Anchor Conflicts (${conflicts.length})`,
        collapsible: true,
        icon: "alert",
        children: conflictChildren,
      });
    }

    // Tier reasons
    if (report.tier_reasons && report.tier_reasons.length > 0) {
      for (const reason of report.tier_reasons) {
        children.push({
          kind: "compare-reason",
          label: reason,
          collapsible: false,
          icon: "info",
        });
      }
    }

    return {
      kind: "compare",
      label: `Compare (${markers.length} marker${markers.length !== 1 ? "s" : ""})`,
      collapsible: true,
      icon: "git-compare",
      children,
      detail: JSON.stringify(report, null, 2),
    };
  }

  buildIntentNode(): TreeNodeData {
    const children: TreeNodeData[] = [];

    if (this.intent) {
      const intent = this.intent.intent;
      const profile = intent.profile;
      const profileIcon = PROFILE_ICONS[profile] ?? "account";

      // Profile (with switch command)
      children.push({
        kind: "intent-profile",
        label: `Profile: ${profile.toUpperCase()}`,
        description: intent.source !== "default" ? `(${intent.source})` : undefined,
        collapsible: false,
        icon: profileIcon,
        tooltip: `Click to change profile`,
      });

      // Scope (if set)
      if (intent.scope && intent.scope.length > 0) {
        children.push({
          kind: "intent-scope",
          label: `Scope: ${intent.scope.join(", ")}`,
          collapsible: false,
          icon: "folder",
        });
      }

      // Deny (if set)
      if (intent.deny && intent.deny.length > 0) {
        children.push({
          kind: "intent-deny",
          label: `Deny: ${intent.deny.join(", ")}`,
          collapsible: false,
          icon: "circle-slash",
        });
      }

      // Timebox (if set)
      if (intent.expires_at) {
        const expires = new Date(intent.expires_at);
        const now = new Date();
        const remainingMs = expires.getTime() - now.getTime();
        const remainingMins = Math.max(0, Math.round(remainingMs / 60000));

        children.push({
          kind: "intent-timebox",
          label: `Timebox: ${remainingMins}m remaining`,
          collapsible: false,
          icon: "clock",
          tooltip: `Expires at ${expires.toLocaleTimeString()}`,
        });
      }

      // Reason (if set)
      if (intent.reason) {
        children.push({
          kind: "intent-reason",
          label: `Reason: ${intent.reason}`,
          collapsible: false,
          icon: "note",
        });
      }
    } else {
      // No intent set - show default
      children.push({
        kind: "intent-default",
        label: "Profile: ESTABLISHED (default)",
        description: "Click to change",
        collapsible: false,
        icon: "shield",
      });
    }

    // Active overrides (if any)
    if (this.overrides.length > 0) {
      const overrideChildren: TreeNodeData[] = this.overrides.map((o) => {
        const expires = new Date(o.expires_at);
        const now = new Date();
        const remainingMs = expires.getTime() - now.getTime();
        const remainingMins = Math.max(0, Math.round(remainingMs / 60000));

        return {
          kind: "override",
          label: `${o.anchor_id} (${remainingMins}m)`,
          description: o.scope.join(", "),
          tooltip: o.reason,
          collapsible: false,
          icon: "pass",
          detail: JSON.stringify(o, null, 2),
        };
      });

      children.push({
        kind: "overrides",
        label: `Overrides (${this.overrides.length})`,
        collapsible: true,
        icon: "pass",
        children: overrideChildren,
      });
    }

    const profile = this.intent?.intent.profile ?? "established";
    return {
      kind: "intent",
      label: `Intent: ${profile.toUpperCase()}`,
      description: this.intent?.intent.source !== "default" ? `(${this.intent?.intent.source})` : undefined,
      collapsible: true,
      icon: PROFILE_ICONS[profile] ?? "zap",
      children,
      detail: this.intent ? JSON.stringify(this.intent.intent, null, 2) : undefined,
    };
  }
}
