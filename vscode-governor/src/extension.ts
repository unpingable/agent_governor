/**
 * Agent Governor VS Code Extension — entry point.
 *
 * Phase 1: commands, diagnostics, output channel, status bar.
 * Phase 2: TreeView side panel with live governor state.
 * Phase 4: Hover tooltips, code actions, real-time checking.
 */

import * as vscode from "vscode";
import { checkFile, checkStdin, fetchState, GovernorOptions } from "./governor/client";
import type { CheckResult, CheckInput, GovernorViewModelV2 } from "./governor/types";
import { DiagnosticProvider } from "./diagnostics/provider";
import { GovernorTreeProvider } from "./views/governorTree";
import { GovernorHoverProvider } from "./hovers/provider";
import { GovernorCodeActionProvider, updateFindings, clearFindings } from "./code-actions/provider";
import { RealtimeChecker } from "./realtime/checker";

let outputChannel: vscode.OutputChannel;
let diagnosticProvider: DiagnosticProvider;
let statusBarItem: vscode.StatusBarItem;
let realtimeChecker: RealtimeChecker | null = null;
let hoverProvider: GovernorHoverProvider | null = null;

function getOptions(): GovernorOptions {
  const config = vscode.workspace.getConfiguration("governor");
  const executablePath = config.get<string>("executablePath", "governor");
  const cwd =
    vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
  return { executablePath, cwd };
}

function updateStatusBar(result: CheckResult): void {
  const icon =
    result.status === "pass"
      ? "$(shield)"
      : result.status === "warn"
        ? "$(warning)"
        : "$(error)";
  const label =
    result.status === "pass"
      ? "Pass"
      : result.status === "warn"
        ? "Warn"
        : "Error";
  statusBarItem.text = `${icon} Governor: ${label}`;
  statusBarItem.tooltip = result.summary;
  statusBarItem.show();
}

async function runCheckFile(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("No active editor.");
    return;
  }

  const filePath = editor.document.uri.fsPath;
  outputChannel.appendLine(`Checking file: ${filePath}`);

  try {
    const result = await checkFile(filePath, getOptions());
    diagnosticProvider.update(editor.document.uri, result);
    updateFindings(editor.document.uri, result.findings);
    updateStatusBar(result);
    outputChannel.appendLine(`Result: ${result.summary}`);
    for (const f of result.findings) {
      outputChannel.appendLine(
        `  [${f.severity.toUpperCase()}] ${f.code}: ${f.message}`
      );
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    outputChannel.appendLine(`Error: ${msg}`);
    vscode.window.showErrorMessage(`Governor check failed: ${msg}`);
    statusBarItem.text = "$(error) Governor: Failed";
    statusBarItem.show();
  }
}

async function runCheckSelection(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("No active editor.");
    return;
  }

  const selection = editor.selection;
  if (selection.isEmpty) {
    vscode.window.showWarningMessage("No text selected.");
    return;
  }

  const content = editor.document.getText(selection);
  const filePath = editor.document.uri.fsPath;
  const selectionStartLine = selection.start.line;

  outputChannel.appendLine(
    `Checking selection in ${filePath} (line ${selectionStartLine + 1})`
  );

  try {
    const result = await checkStdin(
      { content, filepath: filePath },
      getOptions()
    );

    // Offset finding lines by selection start
    for (const f of result.findings) {
      f.range.start.line += selectionStartLine;
      f.range.end.line += selectionStartLine;
    }

    diagnosticProvider.update(editor.document.uri, result);
    updateFindings(editor.document.uri, result.findings);
    updateStatusBar(result);
    outputChannel.appendLine(`Result: ${result.summary}`);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    outputChannel.appendLine(`Error: ${msg}`);
    vscode.window.showErrorMessage(`Governor check failed: ${msg}`);
  }
}

async function checkContentViaStdin(content: string, filepath: string): Promise<CheckResult> {
  return checkStdin({ content, filepath }, getOptions());
}

async function fetchStateWrapper(): Promise<GovernorViewModelV2> {
  return fetchState(getOptions());
}

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel("Governor");
  diagnosticProvider = new DiagnosticProvider();

  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    100
  );
  statusBarItem.command = "governor.showOutput";
  statusBarItem.text = "$(shield) Governor";
  statusBarItem.tooltip = "Agent Governor";
  statusBarItem.show();

  // Tree view (Phase V2)
  const treeProvider = new GovernorTreeProvider(outputChannel, getOptions);
  const treeView = vscode.window.createTreeView("governorState", {
    treeDataProvider: treeProvider,
    showCollapseAll: true,
  });

  // Hover provider (Phase V4)
  hoverProvider = new GovernorHoverProvider(fetchStateWrapper, outputChannel);
  const hoverRegistration = vscode.languages.registerHoverProvider(
    { scheme: "file" },
    hoverProvider
  );

  // Code action provider (Phase V4)
  const codeActionProvider = new GovernorCodeActionProvider();
  const codeActionRegistration = vscode.languages.registerCodeActionsProvider(
    { scheme: "file" },
    codeActionProvider,
    {
      providedCodeActionKinds: GovernorCodeActionProvider.providedCodeActionKinds,
    }
  );

  // Real-time checker (Phase V4)
  realtimeChecker = new RealtimeChecker({
    checkFunction: checkContentViaStdin,
    onResult: (uri, result) => {
      diagnosticProvider.update(uri, result);
      updateStatusBar(result);
      // Invalidate hover cache when results change
      hoverProvider?.invalidateCache();
    },
    outputChannel,
  });

  context.subscriptions.push(
    outputChannel,
    diagnosticProvider,
    statusBarItem,
    treeView,
    treeProvider,
    hoverProvider,
    hoverRegistration,
    codeActionRegistration,
    realtimeChecker,
    vscode.commands.registerCommand("governor.checkFile", runCheckFile),
    vscode.commands.registerCommand(
      "governor.checkSelection",
      runCheckSelection
    ),
    vscode.commands.registerCommand("governor.showOutput", () => {
      outputChannel.show();
    }),
    vscode.commands.registerCommand("governor.refreshState", () => {
      treeProvider.refresh();
      hoverProvider?.invalidateCache();
    }),
    vscode.commands.registerCommand("governor.showDetail", (detail: string) => {
      outputChannel.appendLine(detail);
      outputChannel.show();
    }),
    vscode.commands.registerCommand("governor.toggleRealtime", () => {
      if (realtimeChecker) {
        const newState = !realtimeChecker.isEnabled();
        realtimeChecker.setEnabled(newState);
        vscode.window.showInformationMessage(
          `Governor: Real-time checking ${newState ? "enabled" : "disabled"}`
        );
      }
    }),
    vscode.commands.registerCommand("governor.checkNow", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("No active editor.");
        return;
      }
      if (realtimeChecker) {
        await realtimeChecker.checkNow(editor.document);
        vscode.window.showInformationMessage("Governor: Check complete");
      }
    })
  );

  // On-save handler
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (doc) => {
      const config = vscode.workspace.getConfiguration("governor");
      if (!config.get<boolean>("checkOnSave", false)) {
        return;
      }
      outputChannel.appendLine(`Auto-checking saved file: ${doc.uri.fsPath}`);
      try {
        const result = await checkFile(doc.uri.fsPath, getOptions());
        diagnosticProvider.update(doc.uri, result);
        updateFindings(doc.uri, result.findings);
        updateStatusBar(result);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel.appendLine(`Auto-check error: ${msg}`);
      }
      // Refresh tree view after check
      treeProvider.refresh();
      hoverProvider?.invalidateCache();
    })
  );

  // Clean up findings when documents close
  context.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument((doc) => {
      clearFindings(doc.uri);
    })
  );

  // Initial tree load
  treeProvider.refresh();

  outputChannel.appendLine("Agent Governor extension activated (Phase V4).");
}

export function deactivate(): void {
  // Cleanup handled by disposables in context.subscriptions
}
