/**
 * Tests for GovernorCodeActionProvider.
 */

// Inline mock to avoid circular require issues
jest.mock("vscode", () => ({
  Position: class { constructor(public line: number, public character: number) {} },
  Range: class {
    start: any;
    end: any;
    constructor(startLineOrPos: any, startCharOrEnd: any, endLine?: number, endChar?: number) {
      // Handle both overloads: (Position, Position) or (number, number, number, number)
      if (typeof startLineOrPos === "number" && typeof endLine === "number") {
        this.start = { line: startLineOrPos, character: startCharOrEnd };
        this.end = { line: endLine, character: endChar };
      } else {
        this.start = startLineOrPos;
        this.end = startCharOrEnd;
      }
    }
    intersection(other: any) {
      const maxStartLine = Math.max(this.start.line, other.start.line);
      const minEndLine = Math.min(this.end.line, other.end.line);
      return maxStartLine <= minEndLine ? {} : undefined;
    }
    isEqual(other: any) {
      return this.start.line === other.start.line &&
             this.start.character === other.start.character &&
             this.end.line === other.end.line &&
             this.end.character === other.end.character;
    }
  },
  Uri: class {
    scheme = "file";
    constructor(public fsPath: string) {}
    toString() { return `file://${this.fsPath}`; }
    static file(path: string) { return new (this as any)(path); }
  },
  CodeAction: class {
    isPreferred?: boolean;
    edit?: any;
    command?: any;
    diagnostics?: any[];
    constructor(public title: string, public kind?: any) {}
  },
  CodeActionKind: {
    QuickFix: {
      value: "quickfix",
      append: (suffix: string) => ({ value: `quickfix.${suffix}` }),
    },
    RefactorRewrite: { value: "refactor.rewrite" },
  },
  WorkspaceEdit: class {
    private edits: any[] = [];
    replace(uri: any, range: any, newText: string) {
      this.edits.push({ uri, type: "replace", range, newText });
    }
    insert(uri: any, position: any, newText: string) {
      this.edits.push({ uri, type: "insert", position, newText });
    }
    getEdits() { return this.edits; }
  },
  languages: {
    registerCodeActionsProvider: jest.fn(() => ({ dispose: jest.fn() })),
  },
}), { virtual: true });

import {
  GovernorCodeActionProvider,
  GOVERNOR_ACTION_KIND,
  updateFindings,
  clearFindings,
} from "../../code-actions/provider";
import type { CheckFinding } from "../../governor/types";

// Helper factories - ensure toString matches
const createPosition = (line: number, character: number) => ({ line, character });
const createRange = (startLine: number, startChar: number, endLine: number, endChar: number) => {
  const start = createPosition(startLine, startChar);
  const end = createPosition(endLine, endChar);
  return {
    start,
    end,
    intersection: (other: any) => {
      const maxStartLine = Math.max(startLine, other.start.line);
      const minEndLine = Math.min(endLine, other.end.line);
      return maxStartLine <= minEndLine ? {} : undefined;
    },
    isEqual: (other: any) =>
      startLine === other.start.line &&
      startChar === other.start.character &&
      endLine === other.end.line &&
      endChar === other.end.character,
  };
};

function createMockDocument(content: string, path = "/test/file.ts"): any {
  const lines = content.split("\n");
  // Create URI that matches the format used by updateFindings
  const uri = { fsPath: path, toString: () => `file://${path}`, scheme: "file" };
  return {
    uri,
    getText: () => content,
    lineAt: (line: number) => ({
      text: lines[line] ?? "",
      firstNonWhitespaceCharacterIndex: Math.max(0, (lines[line] ?? "").search(/\S/)),
    }),
  };
}

const mockToken = { isCancellationRequested: false };

describe("GovernorCodeActionProvider", () => {
  let provider: GovernorCodeActionProvider;

  beforeEach(() => {
    provider = new GovernorCodeActionProvider();
  });

  describe("static properties", () => {
    it("provides QuickFix code action kind", () => {
      expect(GovernorCodeActionProvider.providedCodeActionKinds).toEqual([
        GOVERNOR_ACTION_KIND,
      ]);
    });

    it("GOVERNOR_ACTION_KIND is a QuickFix subtype", () => {
      expect(GOVERNOR_ACTION_KIND.value).toBe("quickfix.governor");
    });
  });

  describe("findings cache", () => {
    const path = "/test/file.ts";

    afterEach(() => {
      // Use same URI format for cleanup
      const uri = { toString: () => `file://${path}` };
      clearFindings(uri as any);
    });

    it("updateFindings stores findings", () => {
      const doc = createMockDocument("SELECT * FROM users WHERE id = $input", path);
      const findings: CheckFinding[] = [
        {
          code: "SEC001",
          message: "SQL injection detected",
          severity: "error",
          source: "security",
          range: { start: { line: 0, character: 0 }, end: { line: 0, character: 10 } },
          suggestion: "Use parameterized queries",
        },
      ];
      updateFindings(doc.uri as any, findings);

      const range = createRange(0, 0, 0, 10);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      expect(actions.length).toBeGreaterThan(0);
    });

    it("clearFindings removes findings", () => {
      const doc = createMockDocument("test", path);
      const findings: CheckFinding[] = [
        {
          code: "SEC001",
          message: "Test",
          severity: "error",
          source: "security",
          range: { start: { line: 0, character: 0 }, end: { line: 0, character: 5 } },
        },
      ];
      updateFindings(doc.uri as any, findings);
      clearFindings(doc.uri as any);

      const range = createRange(0, 0, 0, 5);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      expect(actions.length).toBe(0);
    });
  });

  describe("provideCodeActions", () => {
    const path = "/test/file.ts";

    afterEach(() => {
      const uri = { toString: () => `file://${path}` };
      clearFindings(uri as any);
    });

    it("returns empty array when no findings", () => {
      const doc = createMockDocument("clean code", path);
      const range = createRange(0, 0, 0, 5);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      expect(actions).toEqual([]);
    });

    it("returns suppress action for any finding", () => {
      const doc = createMockDocument("const test = 1;", path);
      const findings: CheckFinding[] = [
        {
          code: "TEST001",
          message: "Test finding",
          severity: "warning",
          source: "continuity",
          range: { start: { line: 0, character: 0 }, end: { line: 0, character: 10 } },
        },
      ];
      updateFindings(doc.uri as any, findings);

      const range = createRange(0, 0, 0, 10);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      const suppressAction = actions.find((a) => a.title.includes("Suppress"));
      expect(suppressAction).toBeDefined();
      expect(suppressAction?.edit).toBeDefined();
    });

    it("returns security-specific actions for security findings", () => {
      const doc = createMockDocument("const secret = 'api_key';", path);
      const findings: CheckFinding[] = [
        {
          code: "SEC001",
          message: "Security issue",
          severity: "error",
          source: "security",
          range: { start: { line: 0, character: 0 }, end: { line: 0, character: 10 } },
        },
      ];
      updateFindings(doc.uri as any, findings);

      const range = createRange(0, 0, 0, 10);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      const commentAction = actions.find((a) => a.title.includes("security comment"));
      const reviewedAction = actions.find((a) => a.title.includes("reviewed"));
      expect(commentAction).toBeDefined();
      expect(reviewedAction).toBeDefined();
    });

    it("returns continuity-specific actions for continuity findings", () => {
      const doc = createMockDocument("Some violating text", path);
      const findings: CheckFinding[] = [
        {
          code: "CONT001",
          message: "Anchor violation",
          severity: "warning",
          source: "continuity",
          range: { start: { line: 0, character: 0 }, end: { line: 0, character: 10 } },
          suggestion: "Consider alternative phrasing",
        },
      ];
      updateFindings(doc.uri as any, findings);

      const range = createRange(0, 0, 0, 10);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      const detailsAction = actions.find((a) => a.title.includes("anchor details"));
      expect(detailsAction).toBeDefined();
      expect(detailsAction?.command?.command).toBe("governor.showDetail");
    });

    it("returns fix action when suggestion provided", () => {
      const doc = createMockDocument("const key = 'secret123';", path);
      const findings: CheckFinding[] = [
        {
          code: "SEC003",
          message: "Secret detected",
          severity: "error",
          source: "security",
          range: { start: { line: 0, character: 0 }, end: { line: 0, character: 20 } },
          suggestion: "Use environment variable",
        },
      ];
      updateFindings(doc.uri as any, findings);

      const range = createRange(0, 0, 0, 20);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      const fixAction = actions.find((a) => a.title.startsWith("Fix:"));
      expect(fixAction).toBeDefined();
      expect(fixAction?.isPreferred).toBe(true);
    });

    it("only returns actions for findings that overlap with range", () => {
      const doc = createMockDocument("first\nsecond\nthird", path);
      const findings: CheckFinding[] = [
        {
          code: "FINDING1",
          message: "First finding",
          severity: "warning",
          source: "continuity",
          range: { start: { line: 0, character: 0 }, end: { line: 0, character: 5 } },
        },
        {
          code: "FINDING2",
          message: "Second finding",
          severity: "error",
          source: "security",
          range: { start: { line: 2, character: 0 }, end: { line: 2, character: 10 } },
        },
      ];
      updateFindings(doc.uri as any, findings);

      const range = createRange(0, 0, 0, 5);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      const finding1Actions = actions.filter((a) => a.title.includes("FINDING1"));
      const finding2Actions = actions.filter((a) => a.title.includes("FINDING2"));
      expect(finding1Actions.length).toBeGreaterThan(0);
      expect(finding2Actions.length).toBe(0);
    });
  });

  describe("suppress action formatting", () => {
    const path = "/test/file.ts";

    afterEach(() => {
      const uri = { toString: () => `file://${path}` };
      clearFindings(uri as any);
    });

    it("includes finding code in suppress comment", () => {
      const doc = createMockDocument("test", path);
      const findings: CheckFinding[] = [
        {
          code: "SPECIFIC_CODE",
          message: "Test",
          severity: "warning",
          source: "continuity",
          range: { start: { line: 0, character: 0 }, end: { line: 0, character: 5 } },
        },
      ];
      updateFindings(doc.uri as any, findings);

      const range = createRange(0, 0, 0, 5);
      const context = { diagnostics: [] };
      const actions = provider.provideCodeActions(doc as any, range as any, context as any, mockToken as any);
      const suppressAction = actions.find((a) => a.title.includes("Suppress"));
      expect(suppressAction?.title).toContain("SPECIFIC_CODE");
    });
  });
});
