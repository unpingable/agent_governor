/**
 * Tests for GovernorHoverProvider.
 */

// Inline mock to avoid circular require issues
jest.mock("vscode", () => ({
  Position: class { constructor(public line: number, public character: number) {} },
  Range: class {
    constructor(public start: any, public end: any) {}
  },
  Uri: class {
    scheme = "file";
    constructor(public fsPath: string) {}
    toString() { return this.fsPath; }
    static file(path: string) { return new (this as any)(path); }
  },
  Hover: class {
    constructor(public contents: any, public range?: any) {}
  },
  MarkdownString: class {
    isTrusted = false;
    private content = "";
    constructor(value?: string) { if (value) this.content = value; }
    appendMarkdown(value: string) { this.content += value; return this; }
    get value() { return this.content; }
  },
  languages: {
    registerHoverProvider: jest.fn(() => ({ dispose: jest.fn() })),
  },
  window: {
    createOutputChannel: () => ({ appendLine: jest.fn(), show: jest.fn(), dispose: jest.fn() }),
  },
  workspace: {
    getConfiguration: () => ({ get: (k: string, d: any) => d }),
  },
}), { virtual: true });

import { GovernorHoverProvider } from "../../hovers/provider";
import type { GovernorViewModelV2 } from "../../governor/types";

// Helper factories
const createPosition = (line: number, character: number) => ({ line, character });
const createRange = (startLine: number, startChar: number, endLine: number, endChar: number) => ({
  start: createPosition(startLine, startChar),
  end: createPosition(endLine, endChar),
});

function createMockDocument(content: string, uri = "/test/file.ts"): any {
  const lines = content.split("\n");
  return {
    uri: { fsPath: uri, toString: () => uri, scheme: "file" },
    getText: (range?: any) => {
      if (!range) return content;
      // Extract text from range
      const startLine = range.start.line;
      const endLine = range.end.line;
      if (startLine === endLine) {
        return lines[startLine]?.substring(range.start.character, range.end.character) ?? "";
      }
      // Multi-line case (not needed for these tests but included for completeness)
      let text = lines[startLine]?.substring(range.start.character) ?? "";
      for (let i = startLine + 1; i < endLine; i++) {
        text += "\n" + (lines[i] ?? "");
      }
      text += "\n" + (lines[endLine]?.substring(0, range.end.character) ?? "");
      return text;
    },
    getWordRangeAtPosition: (pos: any) => {
      const line = lines[pos.line] ?? "";
      let start = pos.character;
      let end = pos.character;
      // Expand left
      while (start > 0 && /\w/.test(line[start - 1])) start--;
      // Expand right
      while (end < line.length && /\w/.test(line[end])) end++;
      if (start === end) return undefined;
      return createRange(pos.line, start, pos.line, end);
    },
    lineAt: (line: number) => ({
      text: lines[line] ?? "",
    }),
  };
}

const mockToken = { isCancellationRequested: false, onCancellationRequested: () => ({ dispose: () => {} }) };

const sampleState: GovernorViewModelV2 = {
  schema_version: "v2",
  generated_at: "2024-01-01T00:00:00Z",
  session: {
    mode: "code",
    authority_level: "strict",
    active_constraints: [],
    jurisdiction: "factual",
    active_profile: null,
  },
  regime: null,
  decisions: [
    {
      id: "d1",
      status: "accepted",
      type: "DECISION",
      rationale: "We chose React for the frontend framework",
      dependencies: [],
      violations: [],
      source: "human",
      created_at: "2024-01-01T00:00:00Z",
      raw: { topic: "framework", choice: "react" },
    },
  ],
  claims: [
    {
      id: "c1",
      state: "stabilized",
      content: "Tests pass in CI environment",
      confidence: 0.95,
      provenance: "tool_trace",
      evidence_links: ["e1"],
      conflicting_claims: [],
      stability: {},
      created_at: "2024-01-01T00:00:00Z",
      raw: {},
    },
  ],
  evidence: [],
  violations: [],
  execution: null,
  stability: null,
};

describe("GovernorHoverProvider", () => {
  let provider: GovernorHoverProvider;
  let mockFetchState: jest.Mock;
  let mockOutputChannel: any;

  beforeEach(() => {
    mockFetchState = jest.fn().mockResolvedValue(sampleState);
    mockOutputChannel = { appendLine: jest.fn() };
    provider = new GovernorHoverProvider(mockFetchState, mockOutputChannel);
  });

  afterEach(() => {
    provider.dispose();
  });

  describe("provideHover", () => {
    it("returns null for position with no word", async () => {
      const doc = createMockDocument("   ");
      const pos = createPosition(0, 1);
      const result = await provider.provideHover(doc as any, pos as any, mockToken as any);
      expect(result).toBeNull();
    });

    it("returns null for short words", async () => {
      const doc = createMockDocument("a b c");
      const pos = createPosition(0, 0);
      const result = await provider.provideHover(doc as any, pos as any, mockToken as any);
      expect(result).toBeNull();
    });

    it("returns hover with decision info when word matches choice", async () => {
      // "react" is at position 6 in "Using react for the frontend"
      const doc = createMockDocument("Using react for the frontend");
      const pos = createPosition(0, 6);
      const result = await provider.provideHover(doc as any, pos as any, mockToken as any);
      expect(result).not.toBeNull();
      expect(mockFetchState).toHaveBeenCalled();
    });

    it("returns hover with claim info when word matches claim content", async () => {
      // "Tests" is at position 0, matches claim content "Tests pass in CI environment"
      const doc = createMockDocument("Tests pass in CI");
      const pos = createPosition(0, 0);
      const result = await provider.provideHover(doc as any, pos as any, mockToken as any);
      expect(result).not.toBeNull();
    });

    it("returns null when no relevant context found", async () => {
      const doc = createMockDocument("Random unrelated content here");
      const pos = createPosition(0, 7);
      const result = await provider.provideHover(doc as any, pos as any, mockToken as any);
      expect(result).toBeNull();
    });

    it("caches state to avoid repeated fetches", async () => {
      const doc = createMockDocument("Using react framework");
      const pos = createPosition(0, 6);
      await provider.provideHover(doc as any, pos as any, mockToken as any);
      await provider.provideHover(doc as any, pos as any, mockToken as any);
      await provider.provideHover(doc as any, pos as any, mockToken as any);
      expect(mockFetchState).toHaveBeenCalledTimes(1);
    });

    it("handles fetch errors gracefully", async () => {
      mockFetchState.mockRejectedValueOnce(new Error("Network error"));
      const doc = createMockDocument("Using react framework");
      const pos = createPosition(0, 6);
      const result = await provider.provideHover(doc as any, pos as any, mockToken as any);
      // Errors in getState are caught silently, returning null
      expect(result).toBeNull();
      expect(mockFetchState).toHaveBeenCalled();
    });
  });

  describe("invalidateCache", () => {
    it("forces re-fetch on next hover", async () => {
      const doc = createMockDocument("Using react framework");
      const pos = createPosition(0, 6);
      await provider.provideHover(doc as any, pos as any, mockToken as any);
      expect(mockFetchState).toHaveBeenCalledTimes(1);
      provider.invalidateCache();
      await provider.provideHover(doc as any, pos as any, mockToken as any);
      expect(mockFetchState).toHaveBeenCalledTimes(2);
    });
  });
});
