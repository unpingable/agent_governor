/**
 * Real-time checking — debounced on-type checking.
 *
 * Provides background checking as the user types, with configurable
 * debounce delay and language filtering.
 */

import * as vscode from "vscode";
import type { CheckResult } from "../governor/types";
import { updateFindings } from "../code-actions/provider";

export interface RealtimeCheckerOptions {
  checkFunction: (content: string, filepath: string) => Promise<CheckResult>;
  onResult: (uri: vscode.Uri, result: CheckResult) => void;
  outputChannel: vscode.OutputChannel;
}

export class RealtimeChecker implements vscode.Disposable {
  private readonly disposables: vscode.Disposable[] = [];
  private readonly pendingChecks = new Map<string, NodeJS.Timeout>();
  private enabled = false;
  private debounceMs = 500;
  private excludedLanguages = new Set<string>(["json", "yaml", "markdown", "plaintext"]);

  constructor(private readonly options: RealtimeCheckerOptions) {
    // Watch for configuration changes
    this.disposables.push(
      vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration("governor.realtimeChecking")) {
          this.updateConfig();
        }
      })
    );

    // Watch for text document changes
    this.disposables.push(
      vscode.workspace.onDidChangeTextDocument((e) => {
        if (this.enabled && this.shouldCheck(e.document)) {
          this.scheduleCheck(e.document);
        }
      })
    );

    // Initial config load
    this.updateConfig();
  }

  dispose(): void {
    // Clear all pending checks
    for (const timeout of this.pendingChecks.values()) {
      clearTimeout(timeout);
    }
    this.pendingChecks.clear();

    // Dispose subscriptions
    for (const d of this.disposables) {
      d.dispose();
    }
    this.disposables.length = 0;
  }

  private updateConfig(): void {
    const config = vscode.workspace.getConfiguration("governor");
    this.enabled = config.get<boolean>("realtimeChecking.enabled", false);
    this.debounceMs = config.get<number>("realtimeChecking.debounceMs", 500);
    const excluded = config.get<string[]>("realtimeChecking.excludedLanguages", [
      "json",
      "yaml",
      "markdown",
      "plaintext",
    ]);
    this.excludedLanguages = new Set(excluded);

    this.options.outputChannel.appendLine(
      `Realtime checking: ${this.enabled ? "enabled" : "disabled"} (${this.debounceMs}ms debounce)`
    );
  }

  private shouldCheck(document: vscode.TextDocument): boolean {
    // Skip excluded languages
    if (this.excludedLanguages.has(document.languageId)) {
      return false;
    }

    // Skip non-file URIs
    if (document.uri.scheme !== "file") {
      return false;
    }

    // Skip very large files (> 100KB)
    if (document.getText().length > 100_000) {
      return false;
    }

    return true;
  }

  private scheduleCheck(document: vscode.TextDocument): void {
    const key = document.uri.toString();

    // Cancel any pending check for this document
    const existing = this.pendingChecks.get(key);
    if (existing) {
      clearTimeout(existing);
    }

    // Schedule new check
    const timeout = setTimeout(() => {
      this.pendingChecks.delete(key);
      this.runCheck(document);
    }, this.debounceMs);

    this.pendingChecks.set(key, timeout);
  }

  private async runCheck(document: vscode.TextDocument): Promise<void> {
    // Document might have been closed
    if (document.isClosed) {
      return;
    }

    try {
      const content = document.getText();
      const filepath = document.uri.fsPath;

      const result = await this.options.checkFunction(content, filepath);

      // Document might have been modified during check
      if (document.isClosed || document.isDirty) {
        // If dirty, we'll get another change event, so skip this result
        return;
      }

      // Update findings cache for code actions
      updateFindings(document.uri, result.findings);

      // Notify callback
      this.options.onResult(document.uri, result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      this.options.outputChannel.appendLine(`Realtime check error: ${msg}`);
    }
  }

  /**
   * Manually trigger a check for a document.
   */
  async checkNow(document: vscode.TextDocument): Promise<void> {
    // Cancel any pending check
    const key = document.uri.toString();
    const existing = this.pendingChecks.get(key);
    if (existing) {
      clearTimeout(existing);
      this.pendingChecks.delete(key);
    }

    await this.runCheck(document);
  }

  /**
   * Check if realtime checking is currently enabled.
   */
  isEnabled(): boolean {
    return this.enabled;
  }

  /**
   * Toggle realtime checking.
   */
  setEnabled(enabled: boolean): void {
    if (this.enabled === enabled) {
      return;
    }

    this.enabled = enabled;

    // Update configuration
    const config = vscode.workspace.getConfiguration("governor");
    config.update("realtimeChecking.enabled", enabled, vscode.ConfigurationTarget.Workspace);

    // Clear pending checks if disabling
    if (!enabled) {
      for (const timeout of this.pendingChecks.values()) {
        clearTimeout(timeout);
      }
      this.pendingChecks.clear();
    }

    this.options.outputChannel.appendLine(
      `Realtime checking ${enabled ? "enabled" : "disabled"}`
    );
  }

  /**
   * Get count of pending checks.
   */
  getPendingCount(): number {
    return this.pendingChecks.size;
  }
}
