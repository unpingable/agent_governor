/**
 * Tests for RealtimeChecker.
 */

// Inline mock - must include CodeActionKind since realtime imports code-actions/provider
jest.mock("vscode", () => {
  const mockEmitters = new Map<string, Function[]>();
  let currentConfig: Record<string, any> = {
    "realtimeChecking.enabled": false,
    "realtimeChecking.debounceMs": 500,
    "realtimeChecking.excludedLanguages": ["json", "yaml", "markdown", "plaintext"],
  };

  return {
    Position: class { constructor(public line: number, public character: number) {} },
    Range: class {
      constructor(public start: any, public end: any) {}
      intersection(other: any) { return {}; }
    },
    Uri: class {
      scheme = "file";
      constructor(public fsPath: string) {}
      toString() { return this.fsPath; }
      static file(path: string) { return new (this as any)(path); }
    },
    CodeAction: class {
      isPreferred?: boolean;
      edit?: any;
      command?: any;
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
      replace(uri: any, range: any, newText: string) { this.edits.push({ uri, range, newText }); }
      insert(uri: any, position: any, newText: string) { this.edits.push({ uri, position, newText }); }
    },
    workspace: {
      onDidChangeConfiguration: (handler: Function) => {
        let handlers = mockEmitters.get("config") || [];
        handlers.push(handler);
        mockEmitters.set("config", handlers);
        return { dispose: () => {} };
      },
      onDidChangeTextDocument: (handler: Function) => {
        let handlers = mockEmitters.get("textChange") || [];
        handlers.push(handler);
        mockEmitters.set("textChange", handlers);
        return { dispose: () => {} };
      },
      getConfiguration: () => ({
        get: (key: string, def: any) => {
          const fullKey = key;
          return currentConfig[fullKey] !== undefined ? currentConfig[fullKey] : def;
        },
        update: jest.fn(),
      }),
    },
    ConfigurationTarget: { Global: 1, Workspace: 2, WorkspaceFolder: 3 },
    _testHelpers: {
      setConfig: (cfg: Record<string, any>) => { currentConfig = { ...currentConfig, ...cfg }; },
      fireConfigChange: (keys: string[]) => {
        const handlers = mockEmitters.get("config") || [];
        handlers.forEach(h => h({ affectsConfiguration: (s: string) => keys.some(k => s.includes(k)) }));
      },
      fireTextChange: (doc: any) => {
        const handlers = mockEmitters.get("textChange") || [];
        handlers.forEach(h => h({ document: doc }));
      },
      reset: () => {
        mockEmitters.clear();
        currentConfig = {
          "realtimeChecking.enabled": false,
          "realtimeChecking.debounceMs": 500,
          "realtimeChecking.excludedLanguages": ["json", "yaml", "markdown", "plaintext"],
        };
      },
    },
  };
}, { virtual: true });

import { RealtimeChecker, RealtimeCheckerOptions } from "../../realtime/checker";
import type { CheckResult } from "../../governor/types";

const vscode = require("vscode");

const sampleResult: CheckResult = {
  status: "pass",
  findings: [],
  summary: "No issues found",
};

function createMockDocument(
  content: string,
  uri = "/test/file.ts",
  languageId = "typescript",
  options: { isClosed?: boolean; isDirty?: boolean } = {}
): any {
  return {
    uri: { fsPath: uri, scheme: "file", toString: () => uri },
    languageId,
    getText: () => content,
    isClosed: options.isClosed ?? false,
    isDirty: options.isDirty ?? false,
  };
}

describe("RealtimeChecker", () => {
  let checker: RealtimeChecker;
  let mockCheckFunction: jest.Mock;
  let mockOnResult: jest.Mock;
  let mockOutputChannel: any;

  beforeEach(() => {
    jest.useFakeTimers();
    vscode._testHelpers.reset();

    mockCheckFunction = jest.fn().mockResolvedValue(sampleResult);
    mockOnResult = jest.fn();
    mockOutputChannel = { appendLine: jest.fn() };

    checker = new RealtimeChecker({
      checkFunction: mockCheckFunction,
      onResult: mockOnResult,
      outputChannel: mockOutputChannel,
    });
  });

  afterEach(() => {
    checker.dispose();
    jest.useRealTimers();
  });

  describe("initialization", () => {
    it("starts disabled by default", () => {
      expect(checker.isEnabled()).toBe(false);
    });

    it("logs initial state", () => {
      expect(mockOutputChannel.appendLine).toHaveBeenCalledWith(
        expect.stringContaining("Realtime checking")
      );
    });
  });

  describe("setEnabled", () => {
    it("toggles enabled state", () => {
      expect(checker.isEnabled()).toBe(false);
      checker.setEnabled(true);
      expect(checker.isEnabled()).toBe(true);
      checker.setEnabled(false);
      expect(checker.isEnabled()).toBe(false);
    });

    it("clears pending checks when disabled", () => {
      checker.setEnabled(true);
      const doc = createMockDocument("test");
      vscode._testHelpers.fireTextChange(doc);
      expect(checker.getPendingCount()).toBe(1);
      checker.setEnabled(false);
      expect(checker.getPendingCount()).toBe(0);
    });

    it("logs state change", () => {
      checker.setEnabled(true);
      expect(mockOutputChannel.appendLine).toHaveBeenCalledWith(
        expect.stringContaining("enabled")
      );
    });

    it("no-ops when state unchanged", () => {
      const initialCalls = mockOutputChannel.appendLine.mock.calls.length;
      checker.setEnabled(false);
      expect(mockOutputChannel.appendLine).toHaveBeenCalledTimes(initialCalls);
    });
  });

  describe("checkNow", () => {
    it("runs check immediately", async () => {
      const doc = createMockDocument("immediate check");
      await checker.checkNow(doc);
      expect(mockCheckFunction).toHaveBeenCalledWith("immediate check", "/test/file.ts");
      expect(mockOnResult).toHaveBeenCalled();
    });

    it("cancels pending debounced check", async () => {
      checker.setEnabled(true);
      const doc = createMockDocument("test");
      vscode._testHelpers.fireTextChange(doc);
      expect(checker.getPendingCount()).toBe(1);
      await checker.checkNow(doc);
      expect(checker.getPendingCount()).toBe(0);
      expect(mockCheckFunction).toHaveBeenCalledTimes(1);
    });

    it("skips closed documents", async () => {
      const doc = createMockDocument("test", "/test/file.ts", "typescript", { isClosed: true });
      await checker.checkNow(doc);
      expect(mockOnResult).not.toHaveBeenCalled();
    });
  });

  describe("text change handling", () => {
    beforeEach(() => {
      checker.setEnabled(true);
    });

    it("does not check when disabled", () => {
      checker.setEnabled(false);
      const doc = createMockDocument("test");
      vscode._testHelpers.fireTextChange(doc);
      jest.advanceTimersByTime(1000);
      expect(mockCheckFunction).not.toHaveBeenCalled();
    });

    it("schedules check after debounce period", async () => {
      const doc = createMockDocument("test content");
      vscode._testHelpers.fireTextChange(doc);
      expect(mockCheckFunction).not.toHaveBeenCalled();
      expect(checker.getPendingCount()).toBe(1);
      jest.advanceTimersByTime(500);
      await Promise.resolve();
      expect(mockCheckFunction).toHaveBeenCalledWith("test content", "/test/file.ts");
    });

    it("debounces rapid changes", () => {
      const doc = createMockDocument("test");
      vscode._testHelpers.fireTextChange(doc);
      jest.advanceTimersByTime(200);
      vscode._testHelpers.fireTextChange(doc);
      jest.advanceTimersByTime(200);
      vscode._testHelpers.fireTextChange(doc);
      jest.advanceTimersByTime(200);
      expect(mockCheckFunction).not.toHaveBeenCalled();
      jest.advanceTimersByTime(300);
      expect(mockCheckFunction).toHaveBeenCalledTimes(1);
    });

    it("skips excluded languages", () => {
      const jsonDoc = createMockDocument('{"key": "value"}', "/test/config.json", "json");
      vscode._testHelpers.fireTextChange(jsonDoc);
      jest.advanceTimersByTime(1000);
      expect(mockCheckFunction).not.toHaveBeenCalled();
    });

    it("skips non-file URIs", () => {
      const doc = createMockDocument("test");
      doc.uri.scheme = "untitled";
      vscode._testHelpers.fireTextChange(doc);
      jest.advanceTimersByTime(1000);
      expect(mockCheckFunction).not.toHaveBeenCalled();
    });

    it("skips very large files", () => {
      const largeContent = "x".repeat(150_000);
      const doc = createMockDocument(largeContent);
      vscode._testHelpers.fireTextChange(doc);
      jest.advanceTimersByTime(1000);
      expect(mockCheckFunction).not.toHaveBeenCalled();
    });
  });

  describe("error handling", () => {
    it("handles check function errors gracefully", async () => {
      checker.setEnabled(true);
      mockCheckFunction.mockRejectedValue(new Error("Check failed"));
      const doc = createMockDocument("test");
      vscode._testHelpers.fireTextChange(doc);
      jest.advanceTimersByTime(500);
      await Promise.resolve();
      expect(mockOutputChannel.appendLine).toHaveBeenCalledWith(
        expect.stringContaining("Realtime check error")
      );
      expect(mockOnResult).not.toHaveBeenCalled();
    });
  });

  describe("dispose", () => {
    it("clears all pending checks", () => {
      checker.setEnabled(true);
      const doc = createMockDocument("test");
      vscode._testHelpers.fireTextChange(doc);
      expect(checker.getPendingCount()).toBe(1);
      checker.dispose();
      expect(checker.getPendingCount()).toBe(0);
    });
  });
});
