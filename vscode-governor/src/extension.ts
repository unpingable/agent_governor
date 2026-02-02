/**
 * Agent Governor VS Code Extension — entry point.
 *
 * Phase 1: commands, diagnostics, output channel, status bar.
 */

import * as vscode from "vscode";
import { checkFile, checkStdin, GovernorOptions } from "./governor/client";
import type { CheckResult } from "./governor/types";
import { DiagnosticProvider } from "./diagnostics/provider";

let outputChannel: vscode.OutputChannel;
let diagnosticProvider: DiagnosticProvider;
let statusBarItem: vscode.StatusBarItem;

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
    updateStatusBar(result);
    outputChannel.appendLine(`Result: ${result.summary}`);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    outputChannel.appendLine(`Error: ${msg}`);
    vscode.window.showErrorMessage(`Governor check failed: ${msg}`);
  }
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

  context.subscriptions.push(
    outputChannel,
    diagnosticProvider,
    statusBarItem,
    vscode.commands.registerCommand("governor.checkFile", runCheckFile),
    vscode.commands.registerCommand(
      "governor.checkSelection",
      runCheckSelection
    ),
    vscode.commands.registerCommand("governor.showOutput", () => {
      outputChannel.show();
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
        updateStatusBar(result);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel.appendLine(`Auto-check error: ${msg}`);
      }
    })
  );

  outputChannel.appendLine("Agent Governor extension activated.");
}

export function deactivate(): void {
  // Cleanup handled by disposables in context.subscriptions
}
