/**
 * Reading results (design section 8): split each researcher's notes into
 * sections, map every section to its goals, and give every Cited Findings and
 * Gaps bullet an ID (`r2-b1-f3`, `r2-b1-g1`). The checker and the round analyst
 * cite these IDs; code resolves them to the exact raw lines, so the writer's
 * material stays whole notes lines.
 *
 * The section rules follow core's parseNotes (headings of any level; Takeaway,
 * Cited Findings, Inferences and Gaps parts), but this reader keeps raw line
 * positions, which parseNotes does not.
 */
import type { ResearchResult } from "../../../core/index.js";
import type { EvidenceLine, NotesSectionRef, ResultRecord } from "../state.js";

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

/** Goal IDs named in a brief's tag ("Q3,Q7"). */
export function tagGoals(tag: string | undefined): string[] {
  return (tag ?? "").split(",").map((s) => s.trim()).filter((s) => /^Q\d+$/.test(s));
}

/** Markdown link targets and bare URLs in a line. Parentheses inside a URL are kept when balanced. */
export function urlsIn(text: string): string[] {
  const out = new Set<string>();
  for (const m of text.matchAll(/\]\((https?:\/\/(?:[^\s()]|\([^\s()]*\))+)\)/g)) out.add(m[1]!);
  for (const m of text.matchAll(/(?<!\]\()https?:\/\/[^\s<>"')\]]+/g)) out.add(m[0]!.replace(/[.,;:]+$/, ""));
  return [...out];
}

export function hostOf(url: string): string | null {
  try {
    return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return null;
  }
}

export function hostsIn(text: string): string[] {
  return [...new Set(urlsIn(text).map(hostOf).filter((h): h is string => Boolean(h)))];
}

type RawSection = { title: string; start: number; end: number; takeaway: string[]; items: { kind: "finding" | "gap"; lines: number[] }[] };

/** Sections with raw line ranges and their finding and gap bullets. */
export function splitNotes(notes: string): RawSection[] {
  const lines = notes.split(/\r?\n/);
  const sections: RawSection[] = [];
  let current: RawSection | undefined;
  let part: Part | undefined;
  let item: RawSection["items"][number] | undefined;

  const open = (title: string, start: number) => {
    if (current) current.end = start;
    current = { title, start, end: lines.length, takeaway: [], items: [] };
    sections.push(current);
  };

  lines.forEach((raw, i) => {
    const line = raw.trim();
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      item = undefined;
      const title = heading[2]!.trim();
      const p = partOf(title);
      if (p) {
        if (!current) open("", i);
        part = p;
      } else {
        open(title.replace(/[*_`]/g, "").trim(), i);
        part = undefined;
      }
      return;
    }
    if (!current || !part || !line) return;
    if (part === "takeaway") {
      current.takeaway.push(line);
      return;
    }
    if (part === "inferences") return;
    const kind = part === "findings" ? "finding" : "gap";
    if (/^([-*+]|\d+[.)])\s+/.test(line)) {
      item = { kind, lines: [i] };
      current.items.push(item);
    } else if (item) {
      item.lines.push(i);
    } else {
      item = { kind, lines: [i] };
      current.items.push(item);
    }
  });

  // Notes without any recognised structure: one section, every bullet a finding.
  if (!sections.some((s) => s.items.length || s.takeaway.length) && notes.trim()) {
    const items = lines.flatMap((raw, i) => (/^([-*+]|\d+[.)])\s+/.test(raw.trim()) ? [{ kind: "finding" as const, lines: [i] }] : []));
    return [{ title: "", start: 0, end: lines.length, takeaway: [], items }];
  }
  return sections.filter((s) => s.items.length || s.takeaway.length);
}

/**
 * Goal IDs a section heading names: `[Q4] …` anywhere, or a bare `Q4` that opens
 * the heading ("Q4", "Q4: …"). Live runs on Haiku (2026-10-20, check X2) kept the
 * ID but often dropped the brackets.
 */
export function headingGoals(title: string): string[] {
  const bracketed = [...title.matchAll(/\[(Q\d+)\]/g)].map((m) => m[1]!);
  if (bracketed.length) return bracketed;
  const leading = /^\(?(Q\d+)\)?(?=$|[\s:.,)–—-])/.exec(title.trim());
  return leading ? [leading[1]!] : [];
}

/**
 * Map one result to goals and index its evidence. A section maps to a goal by
 * the ID in its heading; otherwise by key-question order when the counts agree;
 * otherwise to every goal of the brief.
 */
export function readResult(result: ResearchResult): { record: ResultRecord; evidence: EvidenceLine[] } {
  const goalIds = tagGoals(result.brief.tag);
  const base: ResultRecord = {
    briefId: result.brief.id,
    round: result.brief.round,
    goalIds,
    status: result.status,
    failure: result.status === "failed" ? `${result.failure?.kind ?? "failed"}: ${result.failure?.message ?? ""}`.slice(0, 300) : null,
    notes: result.status === "ok" ? result.notes : "",
    sections: [],
  };
  if (result.status !== "ok") return { record: base, evidence: [] };

  const lines = result.notes.split(/\r?\n/);
  const raw = splitNotes(result.notes);
  const byOrder = raw.length === goalIds.length;
  const sections: NotesSectionRef[] = raw.map((s, i) => {
    const known = headingGoals(s.title).filter((id) => goalIds.includes(id));
    const mapped: Pick<NotesSectionRef, "goalIds" | "mappedBy"> = known.length
      ? { goalIds: known, mappedBy: "id" }
      : byOrder
        ? { goalIds: [goalIds[i]!], mappedBy: "order" }
        : { goalIds, mappedBy: "brief" };
    return { title: s.title, ...mapped, start: s.start, end: s.end, takeaway: s.takeaway.join(" ") };
  });

  const evidence: EvidenceLine[] = [];
  let f = 0;
  let g = 0;
  raw.forEach((s, si) => {
    for (const item of s.items) {
      const id = item.kind === "finding" ? `${result.brief.id}-f${++f}` : `${result.brief.id}-g${++g}`;
      const text = item.lines.map((l) => lines[l]!.trim()).join(" ").replace(/^([-*+]|\d+[.)])\s+/, "");
      evidence.push({
        id,
        briefId: result.brief.id,
        round: result.brief.round,
        kind: item.kind,
        goalIds: sections[si]!.goalIds,
        section: si,
        text,
        lines: item.lines,
        hosts: hostsIn(text),
      });
    }
  });
  return { record: { ...base, sections }, evidence };
}

/** Distinct hosts across evidence lines: the independence measure of the evidence floor. */
export function independentHosts(lines: EvidenceLine[]): number {
  return new Set(lines.flatMap((l) => l.hosts)).size;
}
