/** Extract downloaded papers into an ignored, reproducible offline corpus. */
import { parseArgs } from "node:util";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { PDFParse } from "pdf-parse";
import type { CorpusDocument } from "../src/research/local-corpus.js";
const { values } = parseArgs({ options: { library: { type: "string" }, out: { type: "string", default: "local/ebd-corpus.json" } } });
if (!values.library) throw new Error("Provide --library <downloaded EBD library directory>.");
const records = JSON.parse(readFileSync(join(values.library, "00_catalog/records.json"), "utf8")) as Record<string, any>[];
const selected = new Set(["EBD001", "EBD013", "EBD036", "EBD039", "EBD103", "EBD028"]);
const docs: CorpusDocument[] = [];
const paperDir = join(values.library, "01_papers");
const files = readdirSync(paperDir);
for (const record of records.filter(r => selected.has(r.id) || String(r.category).startsWith("A"))) {
  const filename = files.find(f => f.startsWith(`${record.id}_`) && f.endsWith(".pdf"));
  if (!filename) continue;
  const file = join(paperDir, filename);
  if (!existsSync(file)) continue;
  const data = readFileSync(file), parser = new PDFParse({ data });
  try {
    const text = (await parser.getText()).text;
    if (text.trim().length < 1000) { console.error(`${record.id}: no usable extracted text`); continue; }
    docs.push({ id: record.id, title: record.title, url: record.doi || record.candidate_urls?.[0] || record.source,
      text, sha256: createHash("sha256").update(data).digest("hex") });
    console.log(`${record.id}: ${text.length} extracted characters`);
  } finally { await parser.destroy(); }
}
if (!docs.length) throw new Error("No readable downloaded papers were found.");
mkdirSync(dirname(values.out!), { recursive: true });
writeFileSync(values.out!, JSON.stringify(docs, null, 2));
console.log(`Saved ${docs.length} papers to ${values.out}`);
