/**
 * Writer input (design section 12). Material is whole researcher-notes lines,
 * grouped under one heading per goal and ordered by the synthesis questions they
 * feed; off-target lines are left out; nothing on-topic is dropped. The
 * analysis (assumption verdicts, conflicts, defaults, evidence status) goes to
 * the outline and the guidance, never into the material.
 */
import type { SynthesisInput } from "../../core/index.js";
import { directiveLines } from "./briefs.js";
import { assumptionVerdicts, synthesisQuestions } from "./goals.js";
import type { Analysis } from "./request/index.js";
import type { EbdState, Goal } from "./state.js";

const MAX_OUTLINE = 5;
export const DISAGREEMENT_SECTION = "Where the sources disagree";

/** Report-format words that limit the length: pages, paragraphs, sentences, a word count, or short, brief, concise. */
const LENGTH = /\b(?:pages?|paragraphs?|sentences?)\b|\b\d[\d,]*\s*words?\b|\bword (?:limit|count)\b|\b(?:short|brief|briefly|concise|succinct)\b/i;

/** The client's words for a length limit, if a report-format directive sets one (review of 2026-10-21). */
export function lengthLimit(a: Analysis): string | null {
  const d = a.client_directives.find((x) => x.kind === "report_format" && LENGTH.test([x.text, ...x.evidence].join(" ")));
  return d ? (d.evidence[0] ?? d.text) : null;
}

/** Goals in material order: by the synthesis question they feed, then table order; the rest after. */
export function materialOrder(state: EbdState): Goal[] {
  const byId = new Map(state.goals.map((g) => [g.id, g]));
  const order: Goal[] = [];
  const add = (g: Goal | undefined) => {
    if (g && !order.includes(g)) order.push(g);
  };
  for (const s of synthesisQuestions(state.analysis)) {
    const feeds = new Set<string>();
    const stack = [...s.depends_on];
    while (stack.length) {
      const id = stack.pop()!;
      if (feeds.has(id)) continue;
      feeds.add(id);
      stack.push(...(byId.get(id)?.dependsOn ?? []));
    }
    // New and settle goals feed what they lead to.
    for (let changed = true; changed; ) {
      changed = false;
      for (const g of state.goals) {
        if (!feeds.has(g.id) && g.leadsTo.some((t) => t === s.id || feeds.has(t))) {
          feeds.add(g.id);
          changed = true;
        }
      }
    }
    for (const g of state.goals) if (feeds.has(g.id)) add(g);
  }
  for (const g of state.goals) add(g);
  return order;
}

/**
 * Raw line indexes to leave out of the material, per brief: the findings an
 * off_target conflict names, unless a goal cites them as its own evidence (a goal
 * that asks which meanings a name has is answered by the other meanings).
 */
function offTargetLines(state: EbdState): Map<string, Set<number>> {
  const out = new Map<string, Set<number>>();
  const cited = new Set(state.goals.flatMap((g) => g.evidence));
  const ids = new Set(state.conflicts.filter((c) => c.type === "off_target").flatMap((c) => c.sideA).filter((id) => !cited.has(id)));
  for (const e of state.evidence) {
    if (!ids.has(e.id)) continue;
    const set = out.get(e.briefId) ?? new Set<number>();
    for (const l of e.lines) set.add(l);
    out.set(e.briefId, set);
  }
  return out;
}

export function buildMaterial(state: EbdState): SynthesisInput["material"] {
  const skip = offTargetLines(state);
  const emitted = new Set<string>();
  const material: SynthesisInput["material"] = [];
  const results = state.results.filter((r) => r.status === "ok");

  const sectionLines = (briefId: string, notes: string, start: number, end: number): string[] => {
    const lines = notes.split(/\r?\n/);
    const drop = skip.get(briefId) ?? new Set<number>();
    return lines.slice(start, end).filter((_, i) => !drop.has(start + i));
  };

  for (const goal of materialOrder(state)) {
    const parts: string[] = [];
    for (const r of results) {
      r.sections.forEach((s, i) => {
        const key = `${r.briefId}#${i}`;
        if (emitted.has(key) || !s.goalIds.includes(goal.id)) return;
        emitted.add(key);
        parts.push(...sectionLines(r.briefId, r.notes, s.start, s.end));
      });
    }
    if (parts.some((l) => l.trim() && !l.trim().startsWith("#"))) {
      material.push({ label: goal.text, notes: [`# [${goal.id}] ${goal.text}`, ...parts].join("\n") });
    }
  }

  // Unmapped sections and unparsed notes go last, so no on-topic evidence is dropped.
  const further: string[] = [];
  for (const r of results) {
    if (!r.sections.length) {
      further.push(...sectionLines(r.briefId, r.notes, 0, r.notes.split(/\r?\n/).length));
      continue;
    }
    r.sections.forEach((s, i) => {
      if (!emitted.has(`${r.briefId}#${i}`)) further.push(...sectionLines(r.briefId, r.notes, s.start, s.end));
    });
  }
  if (further.some((l) => l.trim() && !l.trim().startsWith("#"))) material.push({ label: "Further findings", notes: ["# Further findings", ...further].join("\n") });
  return material;
}

export function buildOutline(state: EbdState): string[] {
  // Under a length limit, disagreements go where they arise, one sentence each.
  const disputed = state.conflicts.some((c) => c.status === "disputed") && !lengthLimit(state.analysis);
  const questions = synthesisQuestions(state.analysis).map((q) => q.text);
  return disputed ? [...questions.slice(0, MAX_OUTLINE - 1), DISAGREEMENT_SECTION] : questions.slice(0, MAX_OUTLINE);
}

/**
 * Text for the writer without internal IDs, which mean nothing outside the strategy:
 * evidence IDs ("r2-b1-f3") anywhere, and conflict IDs ("C4") inside a parenthesis
 * of IDs only, so that names such as "C300" survive. A comma left before a closing
 * parenthesis, or a space after an opening one, goes with the ID.
 */
export function plain(text: string): string {
  return text
    .replace(/\s*\((?:\s*(?:r\d+-b\d+-[fg]\d+|C\d+)\s*[,;]?)+\)/g, "")
    .replace(/\s*\br\d+-b\d+-[fg]\d+\b,?/g, "")
    .replace(/\s*[,;]\s*\)/g, ")")
    .replace(/\(\s+/g, "(")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function hostsOf(state: EbdState, ids: string[]): string {
  const hosts = [...new Set(ids.flatMap((id) => state.evidence.find((e) => e.id === id)?.hosts ?? []))];
  return hosts.length ? ` (${hosts.join(", ")})` : "";
}

export function buildGuidance(state: EbdState): string {
  const a = state.analysis;
  if (a.status === "out_of_scope") {
    // Lab 4 review (2026-10-26): with no material, the writer's usual 3–5 sections became generic advice.
    const reason = a.status_reason?.trim() || "the request is out of scope";
    return `Nothing was researched: ${reason}${/[.!?]$/.test(reason) ? "" : "."} Write only the title and one paragraph of at most four sentences: why the question cannot be answered yet and what the client could provide. Add no other sections and no general advice.`;
  }
  const out: string[] = [];

  const directives = directiveLines(a, "writer");
  if (directives.length) out.push(`Follow the client's directives:\n${directives.map((d) => `- ${d}`).join("\n")}`);
  const limit = lengthLimit(a);
  if (limit) out.push(`The client limits the length ("${limit}"). This comes before everything below: answer the question first, give each disagreement and each gap at most one sentence, and leave out detail the client did not ask for.`);

  // What the analysis planned for each part, including the defaults it asked the report to state.
  const planned = synthesisQuestions(a).map((q) => `- ${q.text} ${plain(q.done_when)}`);
  if (planned.length) out.push(`What each part of the report must contain, as planned:\n${planned.join("\n")}`);

  const verdicts = assumptionVerdicts(state);
  const premises = a.assumptions.map((x) => {
    switch (verdicts[x.id]) {
      case "contradicted":
        return `- The question presupposes: "${x.claim}" The evidence contradicts this; say so plainly early in the report.`;
      case "unsettled":
        return `- The question presupposes: "${x.claim}" The evidence does not establish this; state that it is not established.`;
      case "supported":
        return `- The question presupposes: "${x.claim}" The evidence supports this.`;
      default:
        return `- The question presupposes: "${x.claim}" This could not be checked; do not present it as established.`;
    }
  });
  if (premises.length) out.push(`What the evidence shows about the question's premises:\n${premises.join("\n")}`);

  const conflicts = state.conflicts.map((c) => {
    switch (c.type) {
      case "off_target":
        return `- Some sources concern a different referent with the same name (${plain(c.statement)}). Leave them out, and distinguish the terms only where needed.`;
      case "time_dependent":
        return `- The sources differ because they describe different times: ${plain(c.statement)} State the condition: ${plain(c.condition)}`;
      case "evidence_vs_frame":
        return `- Some evidence falls outside the question's ${c.sideB[0]?.replace("_", " ") ?? "frame"}: ${plain(c.statement)} Use it only as context and say so.`;
      default:
        if (c.status === "disputed" || c.status === "open") {
          const sources = hostsOf(state, [...c.sideA, ...c.sideB]);
          return limit
            ? `- The sources disagree: ${plain(c.statement)} Give both sides in one sentence, with their sources${sources}.`
            : `- The sources disagree: ${plain(c.statement)} Present both sides with their sources${sources} under "${DISAGREEMENT_SECTION}" or where it arises.`;
        }
        return `- The sources disagreed (${plain(c.statement)}); the notes for "${plain(state.goals.find((g) => g.id === c.settleGoal)?.text ?? "")}" show which account holds and why.`;
    }
  });
  if (conflicts.length) out.push(`Conflicts in the evidence:\n${conflicts.join("\n")}`);

  const defaults = (["purpose", "time_frame", "place"] as const)
    .filter((k) => a.frame[k].basis === "default" && a.frame[k].value !== null)
    .map((k) => `- ${k.replace("_", " ")}: ${a.frame[k].value}`);
  if (defaults.length) out.push(`The client did not state these; they were assumed. Mention them only where they change the answer:\n${defaults.join("\n")}`);

  // Evidence status of necessary goals the research could not complete. A goal with some parts met is
  // partly established: the writer uses its notes and says only what they leave open.
  const unfinished = state.goals.filter((g) => g.need === "necessary" && (g.status === "exhausted" || g.status === "disputed") && !g.settles);
  const none = unfinished.filter((g) => g.partsMet === 0);
  const partly = unfinished.filter((g) => g.partsMet > 0);
  if (none.length) out.push(`No reliable source was found for these; say so where relevant instead of guessing:\n${none.map((g) => `- ${g.text}`).join("\n")}`);
  if (partly.length) {
    out.push(`These were only partly established. Use their notes, and where the report covers them, say what the evidence does not establish:\n${partly.map((g) => `- ${plain(g.text)}${g.missing.length ? ` Not established: ${g.missing.map(plain).join("; ")}` : ""}`).join("\n")}`);
  }

  const moot = state.goals.filter((g) => g.status === "moot");
  if (moot.length) out.push(`These questions were not pursued because a premise they rely on was contradicted:\n${moot.map((g) => `- ${g.text}`).join("\n")}`);

  out.push("Do not open the report with these notes, and do not mention the research process.");
  return out.join("\n\n");
}

export function buildSynthesis(state: EbdState): SynthesisInput {
  const outline = buildOutline(state);
  return { material: buildMaterial(state), ...(outline.length ? { outline } : {}), guidance: buildGuidance(state) };
}
