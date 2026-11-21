// E9: replay one researcher brief of a recorded run through the DeepSeek adapter,
// outside the researcher's catch, so an error keeps its stack.
//   npx tsx scripts/explore/e9-replay-brief.ts <run dir> <brief id> [tag] [timeout ms]
// Request and response bodies (never headers) go to local/explore-deepseek/.
import "dotenv/config";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { getProfile, type DeepSeekProfile } from "../../src/config/models.js";
import type { ResearchBrief } from "../../src/core/contracts.js";
import { UsageLedger } from "../../src/observability/usage.js";
import { runDeepSeek } from "../../src/research/adapters/deepseek.js";
import { researcherPrompt, researcherPromptValues } from "../../src/research/prompts.js";

const [runDir, briefId, tag = "replay", timeoutArg] = process.argv.slice(2);
const timeoutMs = Number(timeoutArg ?? 8 * 60_000);
if (!runDir || !briefId) throw new Error("usage: e9-replay-brief.ts <run dir> <brief id> [tag]");
const key = process.env.DEEPSEEK_API_KEY ?? "";
const redact = (s: string) => (key ? s.split(key).join("<redacted>") : s);
const outDir = "local/explore-deepseek";
mkdirSync(outDir, { recursive: true });

const realFetch = globalThis.fetch;
let n = 0;
globalThis.fetch = (async (input: Parameters<typeof fetch>[0], init?: RequestInit) => {
  const res = await realFetch(input, init);
  const text = await res.clone().text();
  let response: unknown = text;
  try {
    response = JSON.parse(text);
  } catch {}
  let request: unknown = init?.body;
  try {
    request = JSON.parse(String(init?.body));
  } catch {}
  const file = `${outDir}/replay-${tag}-${briefId}-${process.pid}-${++n}.json`;
  writeFileSync(file, redact(JSON.stringify({ url: String(input), status: res.status, request, response }, null, 1)));
  return res;
}) as typeof fetch;

const profile = getProfile("deepseek") as DeepSeekProfile;
const question = readFileSync(join(runDir, "question.txt"), "utf8");
const brief = (JSON.parse(readFileSync(join(runDir, "results", `${briefId}.json`), "utf8")) as { brief: ResearchBrief }).brief;
const today = (JSON.parse(readFileSync(join(runDir, "config.json"), "utf8")) as { today: string }).today;
const messages = await researcherPrompt.formatMessages(researcherPromptValues(question, brief, profile.toolCallsPerResearcher, today));
const ledger = new UsageLedger(profile.pricing);
const t0 = Date.now();
try {
  const out = await runDeepSeek(profile, { messages, ledger, role: "researcher", signal: AbortSignal.timeout(timeoutMs) });
  writeFileSync(`${outDir}/replay-${tag}-${briefId}-output.json`, redact(JSON.stringify({ output: out, ledger: ledger.byRole }, null, 1)));
  console.log(
    JSON.stringify({ ok: true, ms: Date.now() - t0, searches: out.searches, pageReads: out.pageReads, notes: out.notes.length, diagnostics: out.diagnostics, calls: ledger.byRole.researcher?.calls }),
  );
} catch (err) {
  const e = err as Error;
  console.log(JSON.stringify({ ok: false, ms: Date.now() - t0, name: e?.name, message: redact(String(e?.message)), calls: ledger.byRole.researcher?.calls }));
  console.log(redact(String(e?.stack ?? err)));
}
