/**
 * Lenient parser for the shared researcher notes format:
 *
 *   ## <key question>
 *   ### Takeaway / ### Cited Findings / ### Inferences / ### Gaps
 *
 * Heading levels and capitalisation may vary. Text that does not fit is kept
 * in the raw notes, which are always passed on unchanged.
 */

export interface NotesSection {
  question: string;
  takeaway: string;
  findings: string[];
  inferences: string[];
  gaps: string[];
}

export interface ParsedNotes {
  sections: NotesSection[];
  /** True when at least one key-question section with a takeaway or finding was found. */
  parsed: boolean;
}

type Part = "takeaway" | "findings" | "inferences" | "gaps";

const PARTS: [RegExp, Part][] = [
  [/^takeaways?\b/i, "takeaway"],
  [/^(cited\s+)?findings?\b/i, "findings"],
  [/^inferences?\b/i, "inferences"],
  [/^gaps?\b/i, "gaps"],
];

function partOf(heading: string): Part | undefined {
  const text = heading.replace(/[*_`:]/g, "").trim();
  return PARTS.find(([re]) => re.test(text))?.[1];
}

export function parseNotes(markdown: string): ParsedNotes {
  const sections: NotesSection[] = [];
  let current: NotesSection | undefined;
  let part: Part | undefined;
  let takeawayLines: string[] = [];

  const flushTakeaway = () => {
    if (current && takeawayLines.length) {
      current.takeaway = [current.takeaway, takeawayLines.join(" ").trim()].filter(Boolean).join(" ");
    }
    takeawayLines = [];
  };

  for (const line of markdown.split(/\r?\n/)) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(line.trim());
    if (heading) {
      flushTakeaway();
      const title = heading[2]!.trim();
      const p = partOf(title);
      if (p) {
        if (!current) {
          current = { question: "", takeaway: "", findings: [], inferences: [], gaps: [] };
          sections.push(current);
        }
        part = p;
      } else {
        current = { question: title.replace(/[*_`]/g, "").trim(), takeaway: "", findings: [], inferences: [], gaps: [] };
        sections.push(current);
        part = undefined;
      }
      continue;
    }
    if (!current || !part) continue;
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (part === "takeaway") {
      takeawayLines.push(trimmed);
      continue;
    }
    const bullet = /^([-*+]|\d+[.)])\s+(.*)$/.exec(trimmed);
    const list = current[part];
    if (bullet) list.push(bullet[2]!.trim());
    else if (list.length) list[list.length - 1] += ` ${trimmed}`;
    else list.push(trimmed);
  }
  flushTakeaway();

  const useful = sections.filter((s) => s.takeaway || s.findings.length || s.gaps.length || s.inferences.length);
  return { sections: useful, parsed: useful.some((s) => s.takeaway || s.findings.length) };
}

/** A compact view of notes for coordinators: takeaways and gaps per key question. */
export function summarizeNotes(markdown: string, fallbackChars = 1500): string {
  const { sections, parsed } = parseNotes(markdown);
  if (!parsed) return markdown.slice(0, fallbackChars);
  return sections
    .map((s) => {
      const lines = [`- Question: ${s.question || "(untitled)"}`];
      if (s.takeaway) lines.push(`  Takeaway: ${s.takeaway}`);
      lines.push(`  Cited findings: ${s.findings.length}`);
      for (const g of s.gaps) lines.push(`  Gap: ${g}`);
      return lines.join("\n");
    })
    .join("\n");
}
