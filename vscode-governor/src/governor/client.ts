/**
 * CLI wrapper: spawns `governor` subcommands and parses JSON output.
 */

import { spawn } from "child_process";
import type { CheckResult, CheckInput, GovernorViewModelV2, IntentResult, OverrideView } from "./types";

const TIMEOUT_MS = 30_000;

interface GovernorOptions {
  executablePath: string;
  cwd: string;
}

function runGovernorGeneric<T>(
  opts: GovernorOptions,
  args: string[],
  stdinData?: string
): Promise<T> {
  return new Promise((resolve, reject) => {
    const proc = spawn(opts.executablePath, args, {
      cwd: opts.cwd,
      stdio: ["pipe", "pipe", "pipe"],
      timeout: TIMEOUT_MS,
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    proc.on("error", (err: Error) => {
      reject(new Error(`Failed to spawn governor: ${err.message}`));
    });

    proc.on("close", (code: number | null) => {
      if (code !== 0 && code !== null) {
        reject(
          new Error(
            `governor exited with code ${code}: ${stderr || stdout}`
          )
        );
        return;
      }

      try {
        const result: T = JSON.parse(stdout);
        resolve(result);
      } catch {
        reject(
          new Error(
            `Failed to parse governor output: ${stdout.slice(0, 200)}`
          )
        );
      }
    });

    if (stdinData !== undefined) {
      proc.stdin.write(stdinData);
      proc.stdin.end();
    } else {
      proc.stdin.end();
    }
  });
}

/**
 * Check a file on disk by path.
 */
export function checkFile(
  filePath: string,
  opts: GovernorOptions
): Promise<CheckResult> {
  return runGovernorGeneric<CheckResult>(opts, ["check", filePath, "--format", "json"]);
}

/**
 * Check content via stdin (for selections or unsaved buffers).
 */
export function checkStdin(
  input: CheckInput,
  opts: GovernorOptions
): Promise<CheckResult> {
  const payload = JSON.stringify(input);
  return runGovernorGeneric<CheckResult>(
    opts,
    ["check", "--stdin", "--format", "json"],
    payload
  );
}

/**
 * Fetch aggregated governor state (calls `governor state --json --schema v2`).
 */
export function fetchState(
  opts: GovernorOptions
): Promise<GovernorViewModelV2> {
  return runGovernorGeneric<GovernorViewModelV2>(opts, ["state", "--json", "--schema", "v2"]);
}

// =========================================================================
// Code Autopilot: Intent management
// =========================================================================

/**
 * Get current resolved intent with provenance.
 */
export function getIntent(
  opts: GovernorOptions
): Promise<IntentResult> {
  return runGovernorGeneric<IntentResult>(opts, ["intent", "show", "--json"]);
}

export interface SetIntentOptions {
  profile: string;
  scope?: string[];
  deny?: string[];
  timebox?: number;
  reason?: string;
}

/**
 * Set session intent.
 */
export async function setIntent(
  opts: GovernorOptions,
  intentOpts: SetIntentOptions
): Promise<void> {
  const args = ["intent", "set", "--profile", intentOpts.profile];

  if (intentOpts.scope) {
    for (const s of intentOpts.scope) {
      args.push("--scope", s);
    }
  }
  if (intentOpts.deny) {
    for (const d of intentOpts.deny) {
      args.push("--deny", d);
    }
  }
  if (intentOpts.timebox !== undefined) {
    args.push("--timebox", String(intentOpts.timebox));
  }
  if (intentOpts.reason) {
    args.push("--because", intentOpts.reason);
  }

  // This command doesn't return JSON, so we just run it and check for errors
  return new Promise((resolve, reject) => {
    const proc = spawn(opts.executablePath, args, {
      cwd: opts.cwd,
      stdio: ["pipe", "pipe", "pipe"],
      timeout: TIMEOUT_MS,
    });

    let stderr = "";
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    proc.on("error", (err: Error) => {
      reject(new Error(`Failed to spawn governor: ${err.message}`));
    });

    proc.on("close", (code: number | null) => {
      if (code !== 0 && code !== null) {
        reject(new Error(`governor exited with code ${code}: ${stderr}`));
        return;
      }
      resolve();
    });

    proc.stdin.end();
  });
}

/**
 * Clear session intent.
 */
export async function clearIntent(opts: GovernorOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    const proc = spawn(opts.executablePath, ["intent", "clear"], {
      cwd: opts.cwd,
      stdio: ["pipe", "pipe", "pipe"],
      timeout: TIMEOUT_MS,
    });

    let stderr = "";
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    proc.on("error", (err: Error) => {
      reject(new Error(`Failed to spawn governor: ${err.message}`));
    });

    proc.on("close", (code: number | null) => {
      if (code !== 0 && code !== null) {
        reject(new Error(`governor exited with code ${code}: ${stderr}`));
        return;
      }
      resolve();
    });

    proc.stdin.end();
  });
}

// =========================================================================
// Code Autopilot: Override management
// =========================================================================

/**
 * List active overrides.
 */
export function listOverrides(
  opts: GovernorOptions,
  includeAll = false
): Promise<OverrideView[]> {
  const args = ["override", "list", "--json"];
  if (includeAll) {
    args.push("--all");
  }
  return runGovernorGeneric<OverrideView[]>(opts, args);
}

export { GovernorOptions };
