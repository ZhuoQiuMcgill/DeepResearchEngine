/**
 * Material provenance: the writer's material must be researcher notes,
 * selected, ordered or excerpted by whole lines. This keeps the evidence the
 * same kind for every strategy. Strategy analysis belongs in outline/guidance.
 */
import type { ResearchResult, SynthesisInput } from "./contracts.js";

const MARKER = / \(unverified link\)/g;

export interface MaterialProvenance {
  /** Non-empty, non-heading material lines checked. */
  lines: number;
  /** Lines that appear in no researcher's notes. */
  unmatched: number;
  examples: string[];
}

export function materialProvenance(synthesis: SynthesisInput, results: ResearchResult[]): MaterialProvenance {
  const noteLines = new Set(results.flatMap((r) => r.notes.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)));
  const out: MaterialProvenance = { lines: 0, unmatched: 0, examples: [] };
  for (const m of synthesis.material) {
    for (const raw of m.notes.split(/\r?\n/)) {
      const line = raw.replace(MARKER, "").trim();
      // Headings may be added to organise material; they carry no evidence.
      if (!line || line.startsWith("#")) continue;
      out.lines += 1;
      if (!noteLines.has(line)) {
        out.unmatched += 1;
        if (out.examples.length < 5) out.examples.push(line.slice(0, 200));
      }
    }
  }
  return out;
}
