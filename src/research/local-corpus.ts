/** Offline documents only; never fetch URLs or execute instructions from files. */
import { readFileSync } from "node:fs";
import { z } from "zod";
export const CorpusSchema = z.array(z.object({
  id: z.string(), title: z.string(), url: z.string().url(), text: z.string().min(1),
  sha256: z.string(),
}));
export type CorpusDocument = z.infer<typeof CorpusSchema>[number];
export function loadCorpus(path: string): CorpusDocument[] {
  const docs = CorpusSchema.parse(JSON.parse(readFileSync(path, "utf8")));
  if (!docs.length || new Set(docs.map(d => d.id)).size !== docs.length) throw new Error("Corpus must contain uniquely identified documents.");
  return docs;
}
export function searchCorpus(docs: CorpusDocument[], query: string) {
  const terms = [...new Set(query.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [])].filter(t => t.length > 2);
  return docs.map(d => {
    const title = d.title.toLowerCase(), text = d.text.toLowerCase();
    const score = terms.reduce((sum, t) => sum + (title.includes(t) ? 10 : 0) + (text.includes(t) ? 1 : 0), 0);
    const pos = Math.max(0, ...terms.map(t => text.indexOf(t)).filter(p => p >= 0).slice(0, 1));
    return { id: d.id, title: d.title, url: d.url, score, excerpt: d.text.slice(Math.max(0, pos - 150), pos + 1800) };
  }).filter(d => d.score > 0).sort((a,b) => b.score - a.score).slice(0, 5);
}
