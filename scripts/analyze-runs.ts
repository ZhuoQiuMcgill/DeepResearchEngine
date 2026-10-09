/**
 * Recompute report diagnostics for saved runs, so rounds can be compared:
 *   npx tsx scripts/analyze-runs.ts local/runs/<runId> [...]
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { ResearchResultSchema } from "../src/core/contracts.js";
import { citationBinding, unknownCitations } from "../src/core/citations.js";
import { parseNotes } from "../src/core/notes.js";

const showExamples = process.argv.includes("--examples");
const rows: string[] = ["run | words | sections | firstPerson | notesMention | unknownUrls | unbound/checked | notesUnparsed | unlisted"];
for (const dir of process.argv.slice(2).filter((a) => !a.startsWith("--"))) {
  if (!existsSync(join(dir, "report.md"))) continue;
  const report = readFileSync(join(dir, "report.md"), "utf8");
  const results = readdirSync(join(dir, "results"))
    .filter((f) => f.endsWith(".json"))
    .map((f) => ResearchResultSchema.parse(JSON.parse(readFileSync(join(dir, "results", f), "utf8"))));
  const binding = citationBinding(report, results);
  const sections = (report.match(/^## /gm) ?? []).length;
  const firstPerson = (report.match(/\bI (searched|found|could|did)\b|\bmy search/gi) ?? []).length;
  const notesMention = (report.match(/\b(the notes|researchers?)\b/gi) ?? []).length;
  const unparsed = results.filter((r) => r.status === "ok" && !parseNotes(r.notes).parsed).length;
  const unlisted = results.reduce((n, r) => n + r.unlistedCitations.length, 0);
  const name = dir.split("/").pop()!.replace(/^\d{8}-\d{6}-baseline-/, "");
  if (showExamples) for (const e of binding.examples) rows.push(`    unbound ${JSON.stringify(e.missing)}: ${e.text.slice(0, 220)}`);
  rows.push([name, report.split(/\s+/).length, sections, firstPerson, notesMention, unknownCitations(report, results).length, `${binding.unbound}/${binding.checked}`, unparsed, unlisted].join(" | "));
}
console.log(rows.join("\n"));
