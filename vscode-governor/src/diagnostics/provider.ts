/**
 * Diagnostic collection management for governor findings.
 */

import * as vscode from "vscode";
import type { CheckResult, CheckFinding } from "../governor/types";
import { SEVERITY_MAP } from "../governor/types";

export class DiagnosticProvider {
  private collection: vscode.DiagnosticCollection;

  constructor() {
    this.collection = vscode.languages.createDiagnosticCollection("governor");
  }

  /**
   * Update diagnostics for a document from a CheckResult.
   */
  update(uri: vscode.Uri, result: CheckResult): void {
    const diagnostics = result.findings.map((f) => this.toDiagnostic(f));
    this.collection.set(uri, diagnostics);
  }

  /**
   * Clear diagnostics for a document.
   */
  clear(uri: vscode.Uri): void {
    this.collection.delete(uri);
  }

  /**
   * Clear all diagnostics.
   */
  clearAll(): void {
    this.collection.clear();
  }

  dispose(): void {
    this.collection.dispose();
  }

  private toDiagnostic(finding: CheckFinding): vscode.Diagnostic {
    const range = new vscode.Range(
      new vscode.Position(finding.range.start.line, finding.range.start.character),
      new vscode.Position(finding.range.end.line, finding.range.end.character)
    );

    const severityValue = SEVERITY_MAP[finding.severity] ?? vscode.DiagnosticSeverity.Information;

    const diagnostic = new vscode.Diagnostic(range, finding.message, severityValue);
    diagnostic.code = finding.code;
    diagnostic.source = "Governor";

    if (finding.suggestion) {
      diagnostic.message += `\n${finding.suggestion}`;
    }

    return diagnostic;
  }
}
