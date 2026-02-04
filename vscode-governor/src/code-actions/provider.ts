/**
 * Code action provider — quick fixes from governor findings.
 *
 * Provides auto-fix suggestions for security and continuity violations.
 */

import * as vscode from "vscode";
import type { CheckFinding } from "../governor/types";

/**
 * Code action kinds we provide.
 */
export const GOVERNOR_ACTION_KIND = vscode.CodeActionKind.QuickFix.append("governor");

/**
 * Store findings keyed by document URI for quick lookup.
 */
const findingsCache = new Map<string, CheckFinding[]>();

/**
 * Update cached findings for a document.
 */
export function updateFindings(uri: vscode.Uri, findings: CheckFinding[]): void {
  findingsCache.set(uri.toString(), findings);
}

/**
 * Clear cached findings for a document.
 */
export function clearFindings(uri: vscode.Uri): void {
  findingsCache.delete(uri.toString());
}

export class GovernorCodeActionProvider implements vscode.CodeActionProvider {
  static readonly providedCodeActionKinds = [GOVERNOR_ACTION_KIND];

  provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range | vscode.Selection,
    context: vscode.CodeActionContext,
    _token: vscode.CancellationToken
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    // Get findings for this document
    const findings = findingsCache.get(document.uri.toString()) ?? [];

    // Find findings that overlap with the current range
    for (const finding of findings) {
      const findingRange = new vscode.Range(
        finding.range.start.line,
        finding.range.start.character,
        finding.range.end.line,
        finding.range.end.character
      );

      // Check if finding overlaps with the selection/cursor
      if (!findingRange.intersection(range)) {
        continue;
      }

      // Add suggestion-based fix if available
      if (finding.suggestion) {
        const fixAction = this.createFixAction(document, finding, findingRange);
        if (fixAction) {
          actions.push(fixAction);
        }
      }

      // Add source-specific actions
      if (finding.source === "security") {
        actions.push(...this.createSecurityActions(document, finding, findingRange));
      } else if (finding.source === "continuity") {
        actions.push(...this.createContinuityActions(document, finding, findingRange));
      }

      // Add generic suppress action
      actions.push(this.createSuppressAction(document, finding, findingRange));
    }

    // Also check diagnostics from context (standard VS Code pattern)
    for (const diagnostic of context.diagnostics) {
      if (diagnostic.source !== "governor") {
        continue;
      }

      // Find matching finding by range
      const matchingFinding = findings.find((f) => {
        const fr = new vscode.Range(
          f.range.start.line,
          f.range.start.character,
          f.range.end.line,
          f.range.end.character
        );
        return fr.isEqual(diagnostic.range);
      });

      if (matchingFinding?.suggestion) {
        const action = this.createFixAction(document, matchingFinding, diagnostic.range);
        if (action) {
          action.diagnostics = [diagnostic];
          actions.push(action);
        }
      }
    }

    return actions;
  }

  private createFixAction(
    document: vscode.TextDocument,
    finding: CheckFinding,
    range: vscode.Range
  ): vscode.CodeAction | null {
    if (!finding.suggestion) {
      return null;
    }

    // Human-friendly: "Governor: Fix — use ORM instead" not "Fix: suggestion"
    const action = new vscode.CodeAction(
      `Governor: Fix — ${finding.suggestion}`,
      GOVERNOR_ACTION_KIND
    );
    action.isPreferred = true;

    // Create workspace edit based on suggestion type
    const edit = new vscode.WorkspaceEdit();

    // For security findings, the suggestion is usually a replacement
    if (finding.source === "security") {
      // Try to extract replacement from suggestion
      const replacement = this.extractReplacement(finding.suggestion, finding.code);
      if (replacement !== null) {
        edit.replace(document.uri, range, replacement);
        action.edit = edit;
      }
    } else {
      // For continuity findings, show as documentation only
      action.command = {
        command: "governor.showOutput",
        title: "Show Governor Output",
      };
    }

    return action;
  }

  private extractReplacement(suggestion: string, code: string): string | null {
    // Common security fix patterns
    if (code === "SEC001" || code.includes("injection")) {
      // SQL injection: suggest parameterized query
      if (suggestion.includes("parameterized")) {
        return null; // Can't auto-fix, needs manual rewrite
      }
    }

    if (code === "SEC002" || code.includes("xss")) {
      // XSS: suggest escaping
      if (suggestion.includes("escape")) {
        return null; // Can't auto-fix without context
      }
    }

    if (code === "SEC003" || code.includes("secret")) {
      // Secret detected: suggest environment variable
      return "process.env.SECRET_VALUE";
    }

    if (code === "SEC004" || code.includes("path")) {
      // Path traversal: can't auto-fix
      return null;
    }

    return null;
  }

  private createSecurityActions(
    document: vscode.TextDocument,
    finding: CheckFinding,
    range: vscode.Range
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    const lineStart = new vscode.Position(range.start.line, 0);
    const indent = document.lineAt(range.start.line).firstNonWhitespaceCharacterIndex;
    const indentStr = " ".repeat(indent);

    // Human-friendly: "Mark as reviewed"
    const reviewedAction = new vscode.CodeAction(
      "Governor: Mark as reviewed",
      vscode.CodeActionKind.QuickFix
    );
    const reviewEdit = new vscode.WorkspaceEdit();
    reviewEdit.insert(
      document.uri,
      lineStart,
      `${indentStr}// @security-reviewed: ${finding.code}\n`
    );
    reviewedAction.edit = reviewEdit;
    actions.push(reviewedAction);

    return actions;
  }

  private createContinuityActions(
    document: vscode.TextDocument,
    finding: CheckFinding,
    range: vscode.Range
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    // Human-friendly: "Change rule" action
    const changeRuleAction = new vscode.CodeAction(
      "Governor: Change rule",
      vscode.CodeActionKind.QuickFix
    );
    changeRuleAction.command = {
      command: "governor.changeRule",
      title: "Change Rule",
      arguments: [finding.code],
    };
    actions.push(changeRuleAction);

    return actions;
  }

  private createSuppressAction(
    document: vscode.TextDocument,
    finding: CheckFinding,
    range: vscode.Range
  ): vscode.CodeAction {
    // Human-friendly: "Governor: Allow here" not "Suppress"
    const action = new vscode.CodeAction(
      `Governor: Allow here`,
      vscode.CodeActionKind.QuickFix
    );

    const edit = new vscode.WorkspaceEdit();
    const lineStart = new vscode.Position(range.start.line, 0);
    const indent = document.lineAt(range.start.line).firstNonWhitespaceCharacterIndex;
    const indentStr = " ".repeat(indent);
    edit.insert(
      document.uri,
      lineStart,
      `${indentStr}// governor-allow: ${finding.code}\n`
    );
    action.edit = edit;

    return action;
  }

  /**
   * Create "Ignore in this file" action.
   */
  private createIgnoreFileAction(
    document: vscode.TextDocument,
    finding: CheckFinding
  ): vscode.CodeAction {
    const action = new vscode.CodeAction(
      `Governor: Ignore in this file`,
      vscode.CodeActionKind.QuickFix
    );

    // Add file-level disable comment at the top
    const edit = new vscode.WorkspaceEdit();
    const firstLine = new vscode.Position(0, 0);
    edit.insert(
      document.uri,
      firstLine,
      `// governor-disable-file ${finding.code}\n`
    );
    action.edit = edit;

    return action;
  }
}
