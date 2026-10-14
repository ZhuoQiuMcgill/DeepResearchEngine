/**
 * Strategy plug-in loading. A strategy is a directory under src/strategies/
 * whose index default-exports a StrategyModule. Modules are imported lazily by
 * name, so a broken module only affects runs that select it.
 */
import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { CONTRACT_VERSION, type JsonValue, type ResearchStrategy, type StrategyModule } from "../core/strategy.js";

const STRATEGIES_DIR = fileURLToPath(new URL("../strategies/", import.meta.url));

/** Names of available strategy directories (directories starting with "_" or "." are skipped). */
export function listStrategies(): string[] {
  return readdirSync(STRATEGIES_DIR)
    .filter((d) => !d.startsWith("_") && !d.startsWith(".") && statSync(join(STRATEGIES_DIR, d)).isDirectory())
    .sort();
}

function entryFile(name: string): string {
  for (const file of ["index.ts", "index.js"]) {
    const path = join(STRATEGIES_DIR, name, file);
    if (existsSync(path)) return path;
  }
  throw new Error(`Strategy "${name}" not found. Available: ${listStrategies().join(", ") || "(none)"}`);
}

export async function loadStrategyModule(name: string): Promise<StrategyModule> {
  if (!/^[a-z0-9][a-z0-9_-]*$/i.test(name)) throw new Error(`Invalid strategy name "${name}"`);
  const mod = (await import(pathToFileURL(entryFile(name)).href)) as { default?: StrategyModule };
  const m = mod.default;
  if (!m || typeof m.create !== "function" || typeof m.name !== "string") {
    throw new Error(`src/strategies/${name}/index must default-export a StrategyModule { name, description, contractVersion, create }`);
  }
  if (m.name !== name) throw new Error(`Strategy module in "${name}/" declares name "${m.name}"; they must match`);
  if (String(m.contractVersion).split(".")[0] !== CONTRACT_VERSION) {
    throw new Error(`Strategy "${name}" targets contract ${m.contractVersion}; the platform provides ${CONTRACT_VERSION}`);
  }
  return m;
}

export async function createStrategy(name: string, options?: JsonValue): Promise<ResearchStrategy<any>> {
  return (await loadStrategyModule(name)).create(options);
}
