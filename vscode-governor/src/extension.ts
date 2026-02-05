/**
 * Agent Governor VS Code Extension — entry point.
 *
 * Phase 1: commands, diagnostics, output channel, status bar.
 * Phase 2: TreeView side panel with live governor state.
 * Phase 4: Hover tooltips, code actions, real-time checking.
 */

import * as vscode from "vscode";
import { checkFile, checkStdin, fetchState, getIntent, setIntent, clearIntent, runCodeCompare, GovernorOptions, SetIntentOptions } from "./governor/client";
import type { CheckResult, CheckInput, GovernorViewModelV2, IntentResult } from "./governor/types";
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
let currentIntent: IntentResult | null = null;
let treeProviderRef: GovernorTreeProvider | null = null;

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

  // Include profile in status bar if available
  const profile = currentIntent?.intent.profile;
  const profileText = profile && profile !== "established" ? ` [${profile}]` : "";

  statusBarItem.text = `${icon} Governor${profileText}: ${label}`;
  statusBarItem.tooltip = result.summary + (profile ? `\nProfile: ${profile}` : "");
  statusBarItem.show();
}

async function refreshIntent(): Promise<void> {
  try {
    currentIntent = await getIntent(getOptions());
  } catch {
    currentIntent = null;
  }
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
  treeProviderRef = treeProvider;
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
    }),
    // Code Autopilot: Profile switching
    vscode.commands.registerCommand("governor.setProfile", async () => {
      const profiles = [
        { label: "greenfield", description: "New project, experimenting (warn only)" },
        { label: "established", description: "Normal development (default)" },
        { label: "production", description: "High-stakes changes (strict)" },
        { label: "hotfix", description: "Urgent targeted fix (narrow scope)" },
        { label: "refactor", description: "Restructuring code (soft anchors)" },
      ];

      const selected = await vscode.window.showQuickPick(profiles, {
        placeHolder: "Select a profile",
        title: "Governor: Set Profile",
      });

      if (!selected) {
        return;
      }

      // For hotfix, prompt for scope
      let scope: string[] | undefined;
      if (selected.label === "hotfix") {
        const scopeInput = await vscode.window.showInputBox({
          prompt: "Enter scope pattern (e.g., src/auth/**)",
          placeHolder: "src/**",
        });
        if (scopeInput) {
          scope = [scopeInput];
        }
      }

      // Prompt for optional reason
      const reason = await vscode.window.showInputBox({
        prompt: "Why are you setting this profile? (optional)",
        placeHolder: "fixing auth bug",
      });

      try {
        const intentOpts: SetIntentOptions = {
          profile: selected.label,
          scope,
          reason: reason || undefined,
        };
        await setIntent(getOptions(), intentOpts);
        await refreshIntent();
        treeProvider.refresh();
        vscode.window.showInformationMessage(`Governor: Profile set to ${selected.label}`);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`Failed to set profile: ${msg}`);
      }
    }),
    vscode.commands.registerCommand("governor.clearIntent", async () => {
      try {
        await clearIntent(getOptions());
        currentIntent = null;
        treeProvider.refresh();
        vscode.window.showInformationMessage("Governor: Intent cleared");
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`Failed to clear intent: ${msg}`);
      }
    }),
    vscode.commands.registerCommand("governor.showIntent", async () => {
      try {
        const intent = await getIntent(getOptions());
        outputChannel.appendLine("\n=== Current Intent ===");
        outputChannel.appendLine(JSON.stringify(intent.intent, null, 2));
        outputChannel.appendLine("\n=== Provenance ===");
        for (const p of intent.provenance) {
          outputChannel.appendLine(`[${p.layer}] ${p.reason || ""}`);
        }
        outputChannel.show();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel.appendLine(`Error fetching intent: ${msg}`);
        outputChannel.show();
      }
    }),
    vscode.commands.registerCommand("governor.compareModels", async () => {
      try {
        outputChannel.appendLine("Running code compare...");
        const report = await runCodeCompare(getOptions());
        outputChannel.appendLine(JSON.stringify(report, null, 2));

        if (report.tier >= 1) {
          const markerCount = (report.risk_marker_union || []).length;
          const conflictCount = (report.anchor_conflicts || []).length;
          const parts: string[] = [];
          if (markerCount) { parts.push(`${markerCount} risk marker(s)`); }
          if (conflictCount) { parts.push(`${conflictCount} anchor conflict(s)`); }
          vscode.window.showWarningMessage(
            `Models disagreed. ${parts.join(", ")}. [View Details]`,
            "View Details", "Dismiss"
          ).then((action) => {
            if (action === "View Details") {
              outputChannel.show();
            }
          });
        } else {
          vscode.window.showInformationMessage("Governor: No divergence detected.");
        }

        treeProvider.refresh();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel.appendLine(`Compare error: ${msg}`);
        vscode.window.showErrorMessage(`Governor compare failed: ${msg}`);
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

  // Initial tree load and intent fetch
  treeProvider.refresh();
  refreshIntent();

  outputChannel.appendLine("Agent Governor extension activated (Phase V5 - Code Autopilot).");
}

export function deactivate(): void {
  // Cleanup handled by disposables in context.subscriptions
}
