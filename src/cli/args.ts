import { parseArgs } from "node:util";
import { DEFAULT_RUN_CONFIG, type RunConfig } from "../config/run-config.js";

export const RUN_OPTIONS = {
  strategy: { type: "string" },
  researchers: { type: "string" },
  concurrency: { type: "string" },
  "max-rounds": { type: "string" },
  out: { type: "string" },
} as const;

export function runConfigFrom(values: Record<string, unknown>, profile: string): RunConfig {
  const num = (v: unknown, d: number) => (v === undefined ? d : Number(v));
  return {
    strategy: (values.strategy as string) ?? DEFAULT_RUN_CONFIG.strategy,
    profile,
    researchersTotal: num(values.researchers, DEFAULT_RUN_CONFIG.researchersTotal),
    concurrency: num(values.concurrency, DEFAULT_RUN_CONFIG.concurrency),
    maxRounds: num(values["max-rounds"], DEFAULT_RUN_CONFIG.maxRounds),
    researcherTimeoutMs: DEFAULT_RUN_CONFIG.researcherTimeoutMs,
    outDir: (values.out as string) ?? DEFAULT_RUN_CONFIG.outDir,
  };
}

export { parseArgs };
