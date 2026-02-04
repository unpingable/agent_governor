/**
 * Hover provider — shows governor context on hover.
 *
 * Displays relevant decisions, claims, and violations when hovering over code.
 */

import * as vscode from "vscode";
import type { GovernorViewModelV2, DecisionView, ClaimView, ViolationView } from "../governor/types";

export class GovernorHoverProvider implements vscode.HoverProvider, vscode.Disposable {
  private cachedState: GovernorViewModelV2 | null = null;
  private lastFetch: number = 0;
  private readonly cacheTtlMs = 5000; // 5 second cache

  constructor(
    private readonly fetchState: () => Promise<GovernorViewModelV2>,
    private readonly outputChannel: vscode.OutputChannel
  ) {}

  dispose(): void {
    this.cachedState = null;
  }

  async provideHover(
    document: vscode.TextDocument,
    position: vscode.Position,
    _token: vscode.CancellationToken
  ): Promise<vscode.Hover | null> {
    // Get word at position
    const wordRange = document.getWordRangeAtPosition(position);
    if (!wordRange) {
      return null;
    }

    const word = document.getText(wordRange);
    if (!word || word.length < 2) {
      return null;
    }

    // Get line text for context
    const lineText = document.lineAt(position.line).text;

    try {
      const state = await this.getState();
      if (!state) {
        return null;
      }

      const contents: vscode.MarkdownString[] = [];

      // Check for relevant decisions
      const relevantDecisions = this.findRelevantDecisions(state.decisions, word, lineText);
      if (relevantDecisions.length > 0) {
        contents.push(this.formatDecisions(relevantDecisions));
      }

      // Check for relevant claims
      const relevantClaims = this.findRelevantClaims(state.claims, word, lineText);
      if (relevantClaims.length > 0) {
        contents.push(this.formatClaims(relevantClaims));
      }

      // Check for violations at this location
      const relevantViolations = this.findRelevantViolations(state.violations, word, lineText);
      if (relevantViolations.length > 0) {
        contents.push(this.formatViolations(relevantViolations));
      }

      if (contents.length === 0) {
        return null;
      }

      return new vscode.Hover(contents, wordRange);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      this.outputChannel.appendLine(`Hover error: ${msg}`);
      return null;
    }
  }

  private async getState(): Promise<GovernorViewModelV2 | null> {
    const now = Date.now();
    if (this.cachedState && now - this.lastFetch < this.cacheTtlMs) {
      return this.cachedState;
    }

    try {
      this.cachedState = await this.fetchState();
      this.lastFetch = now;
      return this.cachedState;
    } catch {
      return null;
    }
  }

  private findRelevantDecisions(decisions: DecisionView[], word: string, lineText: string): DecisionView[] {
    const wordLower = word.toLowerCase();
    return decisions.filter((d) => {
      // Match by topic in raw data
      const topic = (d.raw?.topic as string) ?? "";
      const choice = (d.raw?.choice as string) ?? "";
      const rationale = d.rationale.toLowerCase();

      return (
        topic.toLowerCase().includes(wordLower) ||
        choice.toLowerCase().includes(wordLower) ||
        rationale.includes(wordLower) ||
        lineText.toLowerCase().includes(topic.toLowerCase())
      );
    });
  }

  private findRelevantClaims(claims: ClaimView[], word: string, lineText: string): ClaimView[] {
    const wordLower = word.toLowerCase();
    return claims.filter((c) => {
      const content = c.content.toLowerCase();
      return content.includes(wordLower) || lineText.toLowerCase().includes(content.slice(0, 30));
    }).slice(0, 3); // Limit to 3 claims
  }

  private findRelevantViolations(violations: ViolationView[], word: string, lineText: string): ViolationView[] {
    const wordLower = word.toLowerCase();
    return violations.filter((v) => {
      const detail = v.detail.toLowerCase();
      const rule = v.rule_breached.toLowerCase();
      return detail.includes(wordLower) || rule.includes(wordLower);
    });
  }

  private formatDecisions(decisions: DecisionView[]): vscode.MarkdownString {
    const md = new vscode.MarkdownString();
    md.isTrusted = true;

    for (const d of decisions.slice(0, 3)) {
      const topic = (d.raw?.topic as string) ?? d.type;
      const choice = (d.raw?.choice as string) ?? "";
      // Human-friendly: "You decided" not "Decision:"
      md.appendMarkdown(`**You decided:** ${topic}: ${choice}\n\n`);
      if (d.rationale) {
        md.appendMarkdown(`> _"${d.rationale}"_\n\n`);
      }
      // Minimal actions
      md.appendMarkdown(`[Edit](command:governor.editDecision) [Remove](command:governor.removeDecision)\n\n`);
    }

    return md;
  }

  private formatClaims(claims: ClaimView[]): vscode.MarkdownString {
    const md = new vscode.MarkdownString();
    md.isTrusted = true;

    for (const c of claims) {
      const stateIcon =
        c.state === "stabilized"
          ? "$(verified)"
          : c.state === "stale"
            ? "$(warning)"
            : c.state === "contradicted"
              ? "$(error)"
              : "$(question)";
      // Human-friendly
      md.appendMarkdown(`${stateIcon} **Tracked:** ${c.content}\n\n`);
      md.appendMarkdown(`_Confidence: ${(c.confidence * 100).toFixed(0)}%_\n\n`);
    }

    return md;
  }

  private formatViolations(violations: ViolationView[]): vscode.MarkdownString {
    const md = new vscode.MarkdownString();
    md.isTrusted = true;

    for (const v of violations) {
      // Human-friendly: "You said X" not "Violation:"
      md.appendMarkdown(`$(warning) **You said:** ${v.rule_breached}\n\n`);
      md.appendMarkdown(`${v.detail}\n\n`);
      if (v.resolution) {
        md.appendMarkdown(`_Suggestion: ${v.resolution}_\n\n`);
      }
      // Human-friendly actions
      md.appendMarkdown(`[Fix](command:governor.fix) [Change Rule](command:governor.changeRule) [Allow Here](command:governor.allowHere)\n\n`);
    }

    return md;
  }

  /**
   * Invalidate the cache (call after state changes).
   */
  invalidateCache(): void {
    this.cachedState = null;
    this.lastFetch = 0;
  }
}
