// E9: one live DeepSeek researcher through the real adapter and prompt.
//   npx tsx scripts/explore/e9-researcher.ts [profile]
// Saves the raw Messages response body (never headers) under
// local/explore-deepseek/ as fixture material.
import "dotenv/config";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { getProfile } from "../../src/config/models.js";
import type { ResearchBrief } from "../../src/core/contracts.js";
import { UsageLedger } from "../../src/observability/usage.js";
import { createResearcher } from "../../src/research/researcher.js";

const profile = getProfile(process.argv[2] ?? "deepseek");
const key = process.env.DEEPSEEK_API_KEY ?? "";
const redact = (s: string) => (key ? s.split(key).join("<redacted>") : s);
mkdirSync("local/explore-deepseek", { recursive: true });

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
  const file = `local/explore-deepseek/researcher-${profile.name}-${Date.now()}-${++n}.json`;
  writeFileSync(file, redact(JSON.stringify({ url: String(input), status: res.status, request, response }, null, 1)));
  return res;
}) as typeof fetch;

const ledger = new UsageLedger(profile.pricing);
const research = createResearcher({ profile, ledger, timeoutMs: 8 * 60_000, today: new Date().toISOString().slice(0, 10) });
// Optional: replay the brief of a recorded result (results/<id>.json of a run record).
const replay = process.argv[3] ? (JSON.parse(readFileSync(process.argv[3], "utf8")) as { brief: ResearchBrief }).brief : undefined;
const result = await research(
  "What is EBD (Environment Based Design)?",
  replay ?? {
    id: "r1-b1",
    round: 1,
    objective: "Establish what Environment Based Design (EBD) is, who proposed it, and its main activities.",
    keyQuestions: ["Who proposed EBD and when?", "What are the main activities of EBD?"],
    constraints: [],
    sourceHints: ["peer-reviewed papers", "author pages"],
  },
);
console.log(
  redact(
    JSON.stringify(
      {
        status: result.status,
        failure: result.failure,
        usage: result.usage,
        queries: result.queries,
        sources: result.sources.length,
        cited: result.sources.filter((s) => s.cited).map((s) => s.url),
        unlisted: result.unlistedCitations,
        diagnostics: result.diagnostics,
        durationMs: result.durationMs,
        ledger: ledger.byRole,
        notesHead: result.notes.slice(0, 600),
      },
      null,
      1,
    ),
  ),
);
