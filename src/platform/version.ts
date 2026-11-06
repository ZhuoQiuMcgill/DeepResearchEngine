/**
 * Platform: the code version a run used, recorded in config.json and summary.json
 * so every report can be tied to the commit that produced it. Uncommitted changes
 * to tracked files are flagged; run records under local/ are ignored by Git.
 */
import { execFileSync } from "node:child_process";

export interface CodeVersion {
  /** Commit hash of HEAD, or null outside a Git checkout. */
  commit: string | null;
  branch: string | null;
  /** Tracked files differ from the commit; the run does not match it exactly. */
  dirty: boolean;
  /** The changed tracked files, at most 20. */
  changed: string[];
}

function git(args: string[]): string | null {
  try {
    return execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return null;
  }
}

let cached: CodeVersion | null = null;

/** Read once per process: every run of one experiment shares the same code. */
export function codeVersion(): CodeVersion {
  if (cached) return cached;
  const commit = git(["rev-parse", "HEAD"]);
  const branch = git(["rev-parse", "--abbrev-ref", "HEAD"]);
  const status = git(["status", "--porcelain", "--untracked-files=no"]);
  const changed = (status ?? "").split("\n").filter(Boolean).map((l) => l.slice(3));
  cached = { commit, branch, dirty: changed.length > 0, changed: changed.slice(0, 20) };
  return cached;
}
