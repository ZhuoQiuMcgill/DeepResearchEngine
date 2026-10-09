/**
 * Run configuration. A run is fully described by this object; it is written
 * to the run record so every run can be reproduced.
 */
export interface RunConfig {
  strategy: string;
  /** Model profile name, see src/config/models.ts. */
  profile: string;
  /** Total researchers for the whole run. */
  researchersTotal: number;
  /** Researchers running at the same time (engineering limit only). */
  concurrency: number;
  /** Safety cap on rounds against loops; not an experimental variable. */
  maxRounds: number;
  researcherTimeoutMs: number;
  /** Directory for run records. */
  outDir: string;
}

export const DEFAULT_RUN_CONFIG: Omit<RunConfig, "profile"> = {
  strategy: "baseline",
  researchersTotal: 10,
  concurrency: 4,
  maxRounds: 8,
  researcherTimeoutMs: 8 * 60_000,
  outDir: "local/runs",
};
