/**
 * Tests for GovernorTreeProvider.
 */

import * as vscode from "vscode";
import { GovernorTreeProvider, TreeNodeData } from "../../views/governorTree";
import type { GovernorState } from "../../governor/types";

// Mock fetchState
const mockFetchState = jest.fn();
jest.mock("../../governor/client", () => ({
  fetchState: (...args: unknown[]) => mockFetchState(...args),
  GovernorOptions: {},
}));

const defaultOpts = { executablePath: "governor", cwd: "/tmp" };

function createOutputChannel(): vscode.OutputChannel {
  return vscode.window.createOutputChannel("test");
}

function emptyState(): GovernorState {
  return {
    proposals: [],
    facts: [],
    decisions: [],
    tasks: [],
    regime: null,
    boil: null,
    autonomous: [],
  };
}

function fullState(): GovernorState {
  return {
    proposals: [
      {
        id: "abc12345-6789-0000-0000-000000000000",
        state: "verified",
        claims: [{ type: "file_exists" }],
        created_at: "2025-01-01T00:00:00Z",
        receipts: [],
      },
      {
        id: "def12345-6789-0000-0000-000000000000",
        state: "draft",
        claims: [],
        created_at: "2025-01-02T00:00:00Z",
      },
    ],
    facts: [
      {
        id: "fact-1",
        claim: { type: "file_exists", describe: "File exists: src/api.py" },
        receipt: {},
        created_at: "2025-01-01T00:00:00Z",
        file_hashes: {},
      },
    ],
    decisions: [
      {
        id: "dec-1",
        claim: { type: "decision", topic: "framework", choice: "react" },
        created_at: "2025-01-01T00:00:00Z",
        rationale: "popular choice",
        supersedes: null,
      },
    ],
    tasks: [
      {
        id: "task-1",
        task: "Implement auth",
        agent_id: "worker-1",
        scope: ["src/auth.py"],
        status: "active",
        started_at: "2025-01-01T00:00:00Z",
        expires_at: "2025-01-01T01:00:00Z",
        completed_at: null,
      },
    ],
    regime: {
      current_regime: "elastic",
      warnings: [],
    },
    boil: {
      mode: "oolong",
      regime: "elastic",
      turn: 5,
      turns_in_regime: 5,
      events_count: 3,
      preset: {
        claim_budget: 20,
        novelty_tolerance: 0.3,
        authority_posture: "Balanced",
        min_dwell: 3,
        tripwires: { high_danger: true },
      },
    },
    autonomous: [
      {
        session_id: "sess-1",
        task: "Run invariant checks",
        status: "running",
        used: { tokens: 23000, iterations: 47, elapsed_seconds: 120, cost_usd: 0.5 },
        budget: { max_tokens: 100000, max_iterations: 100 },
      },
    ],
  };
}

describe("GovernorTreeProvider", () => {
  let provider: GovernorTreeProvider;

  beforeEach(() => {
    mockFetchState.mockReset();
    provider = new GovernorTreeProvider(createOutputChannel(), () => defaultOpts);
  });

  afterEach(() => {
    provider.dispose();
  });

  describe("initial state (before refresh)", () => {
    it("shows loading message", () => {
      const roots = provider.getChildren();
      expect(roots).toHaveLength(1);
      expect(roots[0].label).toBe("Loading...");
      expect(roots[0].kind).toBe("loading");
    });
  });

  describe("after successful refresh with empty state", () => {
    beforeEach(async () => {
      mockFetchState.mockResolvedValue(emptyState());
      await provider.refresh();
    });

    it("shows Status, Proposals, Decisions, Facts nodes", () => {
      const roots = provider.getChildren();
      const kinds = roots.map((r) => r.kind);
      expect(kinds).toContain("status");
      expect(kinds).toContain("proposals");
      expect(kinds).toContain("decisions");
      expect(kinds).toContain("facts");
    });

    it("does not show Tasks or Autonomous when empty", () => {
      const roots = provider.getChildren();
      const kinds = roots.map((r) => r.kind);
      expect(kinds).not.toContain("tasks");
      expect(kinds).not.toContain("autonomous");
    });

    it("proposals node shows count 0", () => {
      const roots = provider.getChildren();
      const proposals = roots.find((r) => r.kind === "proposals")!;
      expect(proposals.label).toBe("Proposals (0)");
      expect(proposals.children).toHaveLength(0);
    });
  });

  describe("after successful refresh with full state", () => {
    beforeEach(async () => {
      mockFetchState.mockResolvedValue(fullState());
      await provider.refresh();
    });

    it("shows all 6 root nodes", () => {
      const roots = provider.getChildren();
      expect(roots).toHaveLength(6);
    });

    it("proposals node has correct children", () => {
      const roots = provider.getChildren();
      const proposals = roots.find((r) => r.kind === "proposals")!;
      expect(proposals.label).toBe("Proposals (2)");
      expect(proposals.children).toHaveLength(2);
      expect(proposals.children![0].label).toContain("VERIFIED");
      expect(proposals.children![1].label).toContain("DRAFT");
    });

    it("decisions node has correct children", () => {
      const roots = provider.getChildren();
      const decisions = roots.find((r) => r.kind === "decisions")!;
      expect(decisions.label).toBe("Decisions (1)");
      expect(decisions.children![0].label).toContain("framework");
      expect(decisions.children![0].label).toContain("react");
    });

    it("facts node has correct children", () => {
      const roots = provider.getChildren();
      const facts = roots.find((r) => r.kind === "facts")!;
      expect(facts.label).toBe("Facts (1)");
      expect(facts.children![0].label).toBe("File exists: src/api.py");
    });

    it("tasks node shows when tasks exist", () => {
      const roots = provider.getChildren();
      const tasks = roots.find((r) => r.kind === "tasks")!;
      expect(tasks).toBeDefined();
      expect(tasks.label).toBe("Tasks (1)");
      expect(tasks.children![0].label).toContain("active");
      expect(tasks.children![0].label).toContain("Implement auth");
    });

    it("autonomous node shows when sessions exist", () => {
      const roots = provider.getChildren();
      const auto = roots.find((r) => r.kind === "autonomous")!;
      expect(auto).toBeDefined();
      expect(auto.label).toBe("Autonomous (1)");
      expect(auto.children![0].label).toContain("running");
      expect(auto.children![0].label).toContain("iter=47");
      expect(auto.children![0].label).toContain("tokens=23k");
    });

    it("status node has regime and boil children", () => {
      const roots = provider.getChildren();
      const status = roots.find((r) => r.kind === "status")!;
      expect(status.children).toHaveLength(2);
      expect(status.children![0].label).toBe("Regime: ELASTIC");
      expect(status.children![1].label).toBe("Boil: OOLONG");
    });
  });

  describe("after failed refresh", () => {
    it("shows error message", async () => {
      mockFetchState.mockRejectedValue(new Error("command not found"));
      await provider.refresh();

      const roots = provider.getChildren();
      expect(roots).toHaveLength(1);
      expect(roots[0].kind).toBe("error");
      expect(roots[0].description).toContain("command not found");
    });
  });

  describe("getTreeItem", () => {
    it("converts leaf node to TreeItem with no collapse", () => {
      const node: TreeNodeData = {
        kind: "fact",
        label: "Tests pass",
        collapsible: false,
        icon: "database",
        detail: '{"id": "1"}',
      };

      const item = provider.getTreeItem(node);
      expect(item.label).toBe("Tests pass");
      expect(item.collapsibleState).toBe(vscode.TreeItemCollapsibleState.None);
      expect(item.iconPath).toBeInstanceOf(vscode.ThemeIcon);
      expect((item.iconPath as vscode.ThemeIcon).id).toBe("database");
      expect(item.command).toBeDefined();
      expect(item.command!.command).toBe("governor.showDetail");
    });

    it("converts parent node to TreeItem with collapse", () => {
      const node: TreeNodeData = {
        kind: "proposals",
        label: "Proposals (3)",
        collapsible: true,
        icon: "git-pull-request",
        children: [],
      };

      const item = provider.getTreeItem(node);
      expect(item.collapsibleState).toBe(vscode.TreeItemCollapsibleState.Collapsed);
    });

    it("sets description and tooltip when present", () => {
      const node: TreeNodeData = {
        kind: "task",
        label: "Test",
        description: "desc text",
        tooltip: "tip text",
        collapsible: false,
      };

      const item = provider.getTreeItem(node);
      expect(item.description).toBe("desc text");
      expect(item.tooltip).toBe("tip text");
    });

    it("omits command when no detail", () => {
      const node: TreeNodeData = {
        kind: "loading",
        label: "Loading...",
        collapsible: false,
      };

      const item = provider.getTreeItem(node);
      expect(item.command).toBeUndefined();
    });
  });

  describe("getChildren with element", () => {
    it("returns children of a node", () => {
      const parent: TreeNodeData = {
        kind: "proposals",
        label: "Proposals",
        collapsible: true,
        children: [
          { kind: "proposal", label: "A", collapsible: false },
          { kind: "proposal", label: "B", collapsible: false },
        ],
      };

      const children = provider.getChildren(parent);
      expect(children).toHaveLength(2);
      expect(children[0].label).toBe("A");
    });

    it("returns empty array when no children", () => {
      const node: TreeNodeData = {
        kind: "fact",
        label: "Fact",
        collapsible: false,
      };

      expect(provider.getChildren(node)).toEqual([]);
    });
  });

  describe("onDidChangeTreeData", () => {
    it("fires event on refresh", async () => {
      mockFetchState.mockResolvedValue(emptyState());

      let fired = false;
      provider.onDidChangeTreeData(() => {
        fired = true;
      });

      await provider.refresh();
      expect(fired).toBe(true);
    });
  });

  describe("regime icon mapping", () => {
    const regimes: Array<[string, string]> = [
      ["elastic", "shield"],
      ["warm", "warning"],
      ["ductile", "flame"],
      ["unstable", "error"],
    ];

    for (const [regime, expectedIcon] of regimes) {
      it(`uses ${expectedIcon} icon for ${regime}`, async () => {
        const state = emptyState();
        state.regime = { current_regime: regime as any };
        mockFetchState.mockResolvedValue(state);
        await provider.refresh();

        const roots = provider.getChildren();
        const statusNode = roots.find((r) => r.kind === "status")!;
        const regimeChild = statusNode.children![0];
        expect(regimeChild.icon).toBe(expectedIcon);
      });
    }
  });

  describe("proposal icon mapping", () => {
    const states: Array<[string, string]> = [
      ["draft", "edit"],
      ["proposed", "file-text"],
      ["verified", "check"],
      ["applied", "check-all"],
      ["rejected", "close"],
    ];

    for (const [state, expectedIcon] of states) {
      it(`uses ${expectedIcon} icon for ${state}`, async () => {
        const s = emptyState();
        s.proposals = [{
          id: "test-id-00000000-0000-0000-0000-000000000000",
          state: state as any,
          claims: [],
          created_at: "2025-01-01T00:00:00Z",
        }];
        mockFetchState.mockResolvedValue(s);
        await provider.refresh();

        const roots = provider.getChildren();
        const proposalsNode = roots.find((r) => r.kind === "proposals")!;
        expect(proposalsNode.children![0].icon).toBe(expectedIcon);
      });
    }
  });
});
