/**
 * Strategy registry. Adding a strategy (e.g. EBD) is one entry here; the
 * skeleton, CLI and tests pick it up by name.
 */
import type { ResearchStrategy } from "../core/strategy.js";
import { BaselineStrategy } from "./baseline/index.js";

export const STRATEGIES: Record<string, () => ResearchStrategy<any>> = {
  baseline: () => new BaselineStrategy(),
};

export function createStrategy(name: string): ResearchStrategy<any> {
  const factory = STRATEGIES[name];
  if (!factory) throw new Error(`Unknown strategy "${name}". Known: ${Object.keys(STRATEGIES).join(", ")}`);
  return factory();
}
