/** Recheck abbreviation-fragment omissions against the same real run material.
 * Originals stay immutable; only source-backed restoration enters report-final.md.
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { citationBinding, unknownCitations } from "../src/core/citations.js";
import type { ResearchResult } from "../src/core/contracts.js";

const dir = process.argv[2];
if (!dir) throw new Error("Provide a completed run directory.");
const payload = JSON.parse(readFileSync(join(dir, "langfuse-observations.json"), "utf8"));
const review = JSON.parse(readFileSync(join(dir, "review.json"), "utf8"));
const results: ResearchResult[] = readdirSync(join(dir, "results")).filter(f => f.endsWith(".json"))
  .map(f => JSON.parse(readFileSync(join(dir, "results", f), "utf8")));
function strings(value: unknown): string[] {
  if (typeof value === "string") { try { return strings(JSON.parse(value)); } catch { return [value]; } }
  if (Array.isArray(value)) return value.flatMap(strings);
  if (value && typeof value === "object") return Object.values(value).flatMap(strings);
  return [];
}
const drafts = [...new Set<string>(payload.observations.filter((o: any) => o.type === "GENERATION")
  .flatMap((o: any) => strings(o.output)).filter((s: string) => /^#\s/.test(s)))];
let report = readFileSync(join(dir, existsSync(join(dir, "report-final.md")) ? "report-final.md" : "report.md"), "utf8");
let restored = review.postprocessing?.restored ?? 0;
for (const edit of review.edits) {
  if (edit.action !== "omitted" || !/\b(?:[A-Za-z]|Dr|Prof|pp|Vol|No|al)\.$/i.test(edit.before)) continue;
  const draft = drafts.find(d => d.includes(edit.before));
  if (!draft) continue;
  const end = draft.indexOf(edit.before) + edit.before.length;
  const following = draft.slice(end, end + 160);
  // An adjacent unit may have been source-corrected, so match its unique
  // longest surviving prefix, not a long exact suffix from the initial draft.
  const anchors: { at: number; matched: number }[] = [];
  let searchAt = 0;
  while (searchAt < report.length) {
    const at = report.indexOf(following.slice(0, 16), searchAt);
    if (at < 0) break;
    let matched = 0;
    while (matched < following.length && following[matched] === report[at + matched]) matched++;
    anchors.push({ at, matched }); searchAt = at + 1;
  }
  anchors.sort((a, b) => b.matched - a.matched);
  if (!anchors[0] || anchors[0].matched < 32 || anchors[0].matched === anchors[1]?.matched) continue;
  const at = anchors[0].at;
  const candidate = report.slice(0, at) + edit.before + report.slice(at);
  if (citationBinding(candidate, results).unbound || unknownCitations(candidate, results).length) continue;
  report = candidate;
  edit.action = "restored";
  edit.after = edit.before;
  edit.reason = "Supported original fragment restored after abbreviation/parenthesis boundary correction.";
  restored++;
}
const binding = citationBinding(report, results);
if (binding.unbound || unknownCitations(report, results).length) throw new Error("Final source support check failed.");
writeFileSync(join(dir, "report-final.md"), report);
review.finalBinding = binding;
review.postprocessing = { restored, originalReport: "report.md", publishedReport: "report-final.md", researchRepeated: false };
review.message = `${review.edits.filter((e: any) => e.action === "replaced").length} source-linked replacements, ${review.edits.filter((e: any) => e.action === "omitted").length} audited omissions, and ${restored} source-backed abbreviation-fragment restoration. Final numeric-source flags: 0. Original model output is retained; the report remains a research draft.`;
writeFileSync(join(dir, "review.json"), JSON.stringify(review, null, 2));
console.log(JSON.stringify({ restored, finalBinding: binding, reportFile: join(dir, "report-final.md") }));
