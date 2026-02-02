/**
 * TreeDataProvider for the Governor side panel.
 *
 * Shows live governor state: regime, boil, proposals, decisions, facts,
 * tasks, and autonomous sessions.
 */

import * as vscode from "vscode";
import { fetchState, GovernorOptions } from "../governor/client";
import type { GovernorState } from "../governor/types";

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

const PROPOSAL_ICONS: Record<string, string> = {
  draft: "edit",
  proposed: "file-text",
  verified: "check",
  applied: "check-all",
  rejected: "close",
};

// =========================================================================
// GovernorTreeProvider
// =========================================================================

export class GovernorTreeProvider
  implements vscode.TreeDataProvider<TreeNodeData>, vscode.Disposable
{
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeNodeData | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private state: GovernorState | null = null;
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
    nodes.push(this.buildStatusNode(this.state));
    nodes.push(this.buildProposalsNode(this.state));
    nodes.push(this.buildDecisionsNode(this.state));
    nodes.push(this.buildFactsNode(this.state));

    const tasksNode = this.buildTasksNode(this.state);
    if (tasksNode) {
      nodes.push(tasksNode);
    }

    const autoNode = this.buildAutonomousNode(this.state);
    if (autoNode) {
      nodes.push(autoNode);
    }

    return nodes;
  }

  // -----------------------------------------------------------------------
  // Builder methods
  // -----------------------------------------------------------------------

  buildStatusNode(s: GovernorState): TreeNodeData {
    const children: TreeNodeData[] = [];

    if (s.regime) {
      const regime = s.regime.current_regime;
      children.push({
        kind: "regime",
        label: `Regime: ${regime.toUpperCase()}`,
        collapsible: false,
        icon: REGIME_ICONS[regime] ?? "shield",
        detail: JSON.stringify(s.regime, null, 2),
      });
    }

    if (s.boil) {
      const mode = s.boil.mode;
      const presetDesc = s.boil.preset?.authority_posture ?? "";
      children.push({
        kind: "boil",
        label: `Boil: ${mode.toUpperCase()}`,
        description: presetDesc,
        collapsible: false,
        icon: "beaker",
        detail: JSON.stringify(s.boil, null, 2),
      });
    }

    return {
      kind: "status",
      label: "Status",
      collapsible: true,
      icon: "pulse",
      children,
    };
  }

  buildProposalsNode(s: GovernorState): TreeNodeData {
    const children: TreeNodeData[] = s.proposals.map((p) => ({
      kind: "proposal",
      label: `[${p.state.toUpperCase()}] ${p.id.slice(0, 8)}...`,
      description: `${p.claims.length} claim(s)`,
      collapsible: false,
      icon: PROPOSAL_ICONS[p.state] ?? "file",
      detail: JSON.stringify(p, null, 2),
    }));

    return {
      kind: "proposals",
      label: `Proposals (${s.proposals.length})`,
      collapsible: true,
      icon: "git-pull-request",
      children,
    };
  }

  buildDecisionsNode(s: GovernorState): TreeNodeData {
    const children: TreeNodeData[] = s.decisions.map((d) => {
      const topic = d.claim?.topic ?? "unknown";
      const choice = d.claim?.choice ?? "";
      return {
        kind: "decision",
        label: `[${topic}] ${choice}`,
        collapsible: false,
        icon: "law",
        detail: JSON.stringify(d, null, 2),
      };
    });

    return {
      kind: "decisions",
      label: `Decisions (${s.decisions.length})`,
      collapsible: true,
      icon: "law",
      children,
    };
  }

  buildFactsNode(s: GovernorState): TreeNodeData {
    const children: TreeNodeData[] = s.facts.map((f) => {
      const claimType = f.claim?.type ?? "";
      const desc = (f.claim as Record<string, unknown>)?.describe as string | undefined;
      return {
        kind: "fact",
        label: desc ?? claimType,
        collapsible: false,
        icon: "database",
        detail: JSON.stringify(f, null, 2),
      };
    });

    return {
      kind: "facts",
      label: `Facts (${s.facts.length})`,
      collapsible: true,
      icon: "database",
      children,
    };
  }

  buildTasksNode(s: GovernorState): TreeNodeData | null {
    if (s.tasks.length === 0) {
      return null;
    }

    const children: TreeNodeData[] = s.tasks.map((t) => ({
      kind: "task",
      label: `[${t.status}] ${t.task}`,
      description: `agent: ${t.agent_id}`,
      collapsible: false,
      icon: t.status === "active" ? "play-circle" : t.status === "completed" ? "check" : "clock",
      detail: JSON.stringify(t, null, 2),
    }));

    return {
      kind: "tasks",
      label: `Tasks (${s.tasks.length})`,
      collapsible: true,
      icon: "tasklist",
      children,
    };
  }

  buildAutonomousNode(s: GovernorState): TreeNodeData | null {
    if (s.autonomous.length === 0) {
      return null;
    }

    const children: TreeNodeData[] = s.autonomous.map((a) => {
      const iter = a.used?.iterations ?? 0;
      const tokens = a.used?.tokens ?? 0;
      const tokensK = tokens >= 1000 ? `${(tokens / 1000).toFixed(0)}k` : `${tokens}`;
      return {
        kind: "autonomous",
        label: `[${a.status}] iter=${iter} tokens=${tokensK}`,
        description: a.task?.slice(0, 40),
        collapsible: false,
        icon: a.status === "running" ? "sync~spin" : "history",
        detail: JSON.stringify(a, null, 2),
      };
    });

    return {
      kind: "autonomous",
      label: `Autonomous (${s.autonomous.length})`,
      collapsible: true,
      icon: "robot",
      children,
    };
  }
}
