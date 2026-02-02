/**
 * Tests for GovernorTreeProvider (V2 schema).
 */

import * as vscode from "vscode";
import { GovernorTreeProvider, TreeNodeData } from "../../views/governorTree";
import type { GovernorViewModelV2 } from "../../governor/types";

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

function emptyState(): GovernorViewModelV2 {
  return {
    schema_version: "v2",
    generated_at: "2025-01-01T00:00:00Z",
    session: null,
    regime: null,
    decisions: [],
    claims: [],
    evidence: [],
    violations: [],
    execution: null,
    stability: null,
  };
}

function fullState(): GovernorViewModelV2 {
  return {
    schema_version: "v2",
    generated_at: "2025-01-01T00:00:00Z",
    session: {
      mode: "strict",
      authority_level: "Balanced",
      active_constraints: ["strict_envelope"],
      jurisdiction: "factual",
      active_profile: "strict",
    },
    regime: {
      name: "elastic",
      setpoints: { hysteresis: 0.5 },
      telemetry: { rejection_rate: 0.18, claim_churn: 0.12 },
      boil_mode: "oolong",
      transitions: [],
    },
    decisions: [
      {
        id: "dec_a1b2c3d4e5f6",
        status: "accepted",
        type: "framework: react",
        rationale: "popular choice",
        dependencies: [],
        violations: [],
        source: "decision_ledger",
        created_at: "2025-01-01T00:00:00Z",
        raw: {},
      },
      {
        id: "dec_d4e5f6a7b8c9",
        status: "rejected",
        type: "Claim needs evidence",
        rationale: "insufficient grounding",
        dependencies: [],
        violations: [],
        source: "proposal",
        created_at: "2025-01-02T00:00:00Z",
        raw: {},
      },
    ],
    claims: [
      {
        id: "clm_test1",
        state: "stabilized",
        content: "Tests pass",
        confidence: 0.92,
        provenance: "observed",
        evidence_links: ["ev_ref1"],
        conflicting_claims: [],
        stability: {},
        created_at: "2025-01-01T00:00:00Z",
        raw: {},
      },
      {
        id: "clm_test2",
        state: "proposed",
        content: "API is RESTful",
        confidence: 0.45,
        provenance: "assumed",
        evidence_links: [],
        conflicting_claims: [],
        stability: {},
        created_at: "2025-01-01T00:00:00Z",
        raw: {},
      },
    ],
    evidence: [
      {
        id: "ev_ref1",
        type: "tool_trace",
        source: "pytest output",
        scope: "test_suite",
        linked_claims: ["clm_test1"],
        validity: 1.0,
        expiry: null,
      },
    ],
    violations: [
      {
        id: "vio_audit_ga_test123",
        rule_breached: "Missing evidence for claim",
        triggering_decision: "assert_1",
        severity: "high",
        enforced_outcome: "block",
        resolution: null,
        source_system: "audit",
        detail: "no evidence attached",
      },
    ],
    execution: {
      pending: [{ id: "p1", description: "1 claim(s)", status: "draft", detail: "proposal abc" }],
      blocked: [{ id: "b1", description: "1 claim(s)", status: "rejected", detail: "proposal def" }],
      running: [{ id: "r1", description: "Run checks", status: "running", detail: "{}" }],
      completed: [],
    },
    stability: {
      rejection_rate: 0.18,
      claim_churn: 0.12,
      contradiction_density: 0.05,
      drift_alert: "NONE",
      drift_signals: {},
    },
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

    it("shows Session, Regime, Decisions, Claims, Stability nodes", () => {
      const roots = provider.getChildren();
      const kinds = roots.map((r) => r.kind);
      expect(kinds).toContain("session");
      expect(kinds).toContain("regime-section");
      expect(kinds).toContain("decisions");
      expect(kinds).toContain("claims");
      expect(kinds).toContain("stability");
    });

    it("does not show Evidence, Violations, or Execution when empty", () => {
      const roots = provider.getChildren();
      const kinds = roots.map((r) => r.kind);
      expect(kinds).not.toContain("evidence-section");
      expect(kinds).not.toContain("violations");
      expect(kinds).not.toContain("execution");
    });

    it("decisions node shows count 0", () => {
      const roots = provider.getChildren();
      const decisions = roots.find((r) => r.kind === "decisions")!;
      expect(decisions.label).toBe("Decisions (0)");
      expect(decisions.children).toHaveLength(0);
    });

    it("claims node shows count 0", () => {
      const roots = provider.getChildren();
      const claims = roots.find((r) => r.kind === "claims")!;
      expect(claims.label).toBe("Claims (0)");
      expect(claims.children).toHaveLength(0);
    });
  });

  describe("after successful refresh with full state", () => {
    beforeEach(async () => {
      mockFetchState.mockResolvedValue(fullState());
      await provider.refresh();
    });

    it("shows all 8 root nodes", () => {
      const roots = provider.getChildren();
      // session, regime, decisions, claims, evidence, violations, execution, stability
      expect(roots).toHaveLength(8);
    });

    it("session node has mode and authority children", () => {
      const roots = provider.getChildren();
      const session = roots.find((r) => r.kind === "session")!;
      expect(session.children!.length).toBeGreaterThanOrEqual(2);
      expect(session.children![0].label).toBe("Mode: STRICT");
      expect(session.children![1].label).toBe("Authority: Balanced");
    });

    it("regime node shows regime and boil", () => {
      const roots = provider.getChildren();
      const regime = roots.find((r) => r.kind === "regime-section")!;
      expect(regime.label).toBe("Regime: ELASTIC");
      const children = regime.children!;
      expect(children.find((c) => c.kind === "regime")!.label).toBe("Regime: ELASTIC");
      expect(children.find((c) => c.kind === "boil")!.label).toBe("Boil: OOLONG");
    });

    it("decisions node has correct children", () => {
      const roots = provider.getChildren();
      const decisions = roots.find((r) => r.kind === "decisions")!;
      expect(decisions.label).toBe("Decisions (2)");
      expect(decisions.children).toHaveLength(2);
      expect(decisions.children![0].label).toContain("ACCEPTED");
      expect(decisions.children![1].label).toContain("REJECTED");
    });

    it("claims node has correct children with confidence", () => {
      const roots = provider.getChildren();
      const claims = roots.find((r) => r.kind === "claims")!;
      expect(claims.label).toBe("Claims (2)");
      expect(claims.children).toHaveLength(2);
      expect(claims.children![0].label).toContain("STABILIZED");
      expect(claims.children![0].label).toContain("Tests pass");
      expect(claims.children![0].description).toBe("(0.92)");
    });

    it("evidence node shows when evidence exists", () => {
      const roots = provider.getChildren();
      const evidence = roots.find((r) => r.kind === "evidence-section")!;
      expect(evidence).toBeDefined();
      expect(evidence.label).toBe("Evidence (1)");
      expect(evidence.children![0].label).toContain("tool_trace");
    });

    it("violations node shows when violations exist", () => {
      const roots = provider.getChildren();
      const violations = roots.find((r) => r.kind === "violations")!;
      expect(violations).toBeDefined();
      expect(violations.label).toBe("Violations (1)");
      expect(violations.children![0].label).toContain("HIGH");
    });

    it("execution node shows when actions exist", () => {
      const roots = provider.getChildren();
      const execution = roots.find((r) => r.kind === "execution")!;
      expect(execution).toBeDefined();
      expect(execution.children!.length).toBeGreaterThanOrEqual(1);
    });

    it("stability node has metrics children", () => {
      const roots = provider.getChildren();
      const stability = roots.find((r) => r.kind === "stability")!;
      expect(stability.children!.length).toBe(3);
      expect(stability.children![0].label).toContain("Rejection rate");
      expect(stability.children![1].label).toContain("Claim churn");
      expect(stability.children![2].label).toContain("Drift: NONE");
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
        kind: "claim",
        label: "Tests pass",
        collapsible: false,
        icon: "check",
        detail: '{"id": "1"}',
      };

      const item = provider.getTreeItem(node);
      expect(item.label).toBe("Tests pass");
      expect(item.collapsibleState).toBe(vscode.TreeItemCollapsibleState.None);
      expect(item.iconPath).toBeInstanceOf(vscode.ThemeIcon);
      expect((item.iconPath as vscode.ThemeIcon).id).toBe("check");
      expect(item.command).toBeDefined();
      expect(item.command!.command).toBe("governor.showDetail");
    });

    it("converts parent node to TreeItem with collapse", () => {
      const node: TreeNodeData = {
        kind: "decisions",
        label: "Decisions (3)",
        collapsible: true,
        icon: "law",
        children: [],
      };

      const item = provider.getTreeItem(node);
      expect(item.collapsibleState).toBe(vscode.TreeItemCollapsibleState.Collapsed);
    });

    it("sets description and tooltip when present", () => {
      const node: TreeNodeData = {
        kind: "claim",
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
        kind: "decisions",
        label: "Decisions",
        collapsible: true,
        children: [
          { kind: "decision", label: "A", collapsible: false },
          { kind: "decision", label: "B", collapsible: false },
        ],
      };

      const children = provider.getChildren(parent);
      expect(children).toHaveLength(2);
      expect(children[0].label).toBe("A");
    });

    it("returns empty array when no children", () => {
      const node: TreeNodeData = {
        kind: "claim",
        label: "Claim",
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
        state.regime = {
          name: regime,
          setpoints: {},
          telemetry: {},
          boil_mode: null,
          transitions: [],
        };
        mockFetchState.mockResolvedValue(state);
        await provider.refresh();

        const roots = provider.getChildren();
        const regimeNode = roots.find((r) => r.kind === "regime-section")!;
        expect(regimeNode.icon).toBe(expectedIcon);
        const regimeChild = regimeNode.children![0];
        expect(regimeChild.icon).toBe(expectedIcon);
      });
    }
  });

  describe("decision status icon mapping", () => {
    const statuses: Array<[string, string]> = [
      ["accepted", "check-all"],
      ["rejected", "close"],
      ["pending", "clock"],
    ];

    for (const [status, expectedIcon] of statuses) {
      it(`uses ${expectedIcon} icon for ${status}`, async () => {
        const state = emptyState();
        state.decisions = [
          {
            id: "dec_test",
            status: status as "accepted" | "rejected" | "pending",
            type: "test",
            rationale: "",
            dependencies: [],
            violations: [],
            source: "proposal",
            created_at: "2025-01-01T00:00:00Z",
            raw: {},
          },
        ];
        mockFetchState.mockResolvedValue(state);
        await provider.refresh();

        const roots = provider.getChildren();
        const decisionsNode = roots.find((r) => r.kind === "decisions")!;
        expect(decisionsNode.children![0].icon).toBe(expectedIcon);
      });
    }
  });

  describe("claim state icon mapping", () => {
    const states: Array<[string, string]> = [
      ["stabilized", "check"],
      ["proposed", "question"],
      ["stale", "clock"],
      ["contradicted", "close"],
    ];

    for (const [state, expectedIcon] of states) {
      it(`uses ${expectedIcon} icon for ${state}`, async () => {
        const s = emptyState();
        s.claims = [
          {
            id: "clm_test",
            state: state as "proposed" | "stabilized" | "stale" | "contradicted",
            content: "test claim",
            confidence: 0.5,
            provenance: "assumed",
            evidence_links: [],
            conflicting_claims: [],
            stability: {},
            created_at: "2025-01-01T00:00:00Z",
            raw: {},
          },
        ];
        mockFetchState.mockResolvedValue(s);
        await provider.refresh();

        const roots = provider.getChildren();
        const claimsNode = roots.find((r) => r.kind === "claims")!;
        expect(claimsNode.children![0].icon).toBe(expectedIcon);
      });
    }
  });

  describe("violation severity icon mapping", () => {
    const severities: Array<[string, string]> = [
      ["low", "info"],
      ["medium", "warning"],
      ["high", "error"],
      ["critical", "alert"],
    ];

    for (const [severity, expectedIcon] of severities) {
      it(`uses ${expectedIcon} icon for ${severity}`, async () => {
        const s = emptyState();
        s.violations = [
          {
            id: "vio_test",
            rule_breached: "test rule",
            triggering_decision: "test",
            severity: severity as "low" | "medium" | "high" | "critical",
            enforced_outcome: "block",
            resolution: null,
            source_system: "audit",
            detail: "test",
          },
        ];
        mockFetchState.mockResolvedValue(s);
        await provider.refresh();

        const roots = provider.getChildren();
        const violationsNode = roots.find((r) => r.kind === "violations")!;
        expect(violationsNode.children![0].icon).toBe(expectedIcon);
      });
    }
  });
});
