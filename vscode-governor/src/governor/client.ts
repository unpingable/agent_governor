/**
 * CLI wrapper: spawns `governor check` and parses JSON output.
 */

import { spawn } from "child_process";
import type { CheckResult, CheckInput } from "./types";

const TIMEOUT_MS = 30_000;

interface GovernorOptions {
  executablePath: string;
  cwd: string;
}

function runGovernor(
  opts: GovernorOptions,
  args: string[],
  stdinData?: string
): Promise<CheckResult> {
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
        const result: CheckResult = JSON.parse(stdout);
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
  return runGovernor(opts, ["check", filePath, "--format", "json"]);
}

/**
 * Check content via stdin (for selections or unsaved buffers).
 */
export function checkStdin(
  input: CheckInput,
  opts: GovernorOptions
): Promise<CheckResult> {
  const payload = JSON.stringify(input);
  return runGovernor(
    opts,
    ["check", "--stdin", "--format", "json"],
    payload
  );
}

export { GovernorOptions };
