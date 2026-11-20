/**
 * Writer input (design section 12). Material is whole researcher-notes lines,
 * grouped under one heading per goal and ordered by the synthesis questions they
 * feed; off-target lines are left out; nothing on-topic is dropped. The
 * analysis (assumption verdicts, conflicts, defaults, evidence status) goes to
 * the outline and the guidance, never into the material.
 *
 * The writer is told only what the notes do not show (design section 20):
 * premises the evidence contradicts or leaves open, and at most three critical
 * conflicts, each treated where it arises.
 */
import type { SynthesisInput } from "../../core/index.js";
import { directiveLines } from "./briefs.js";
import { assumptionVerdicts, endedByFailures, synthesisQuestions } from "./goals.js";
import type { Analysis } from "./analysis.js";
import { eventOf, isCritical, type Conflict, type EbdState, type Goal } from "./state.js";

const MAX_OUTLINE = 5;
/** The writer is told about at most this many critical conflicts (section 20). */
export const MAX_CRITICAL_LINES = 3;
export const READING_LABEL = "The question was read as:";
/**
 * "In at most three sentences": in the live batch of 2026-11-11 a disagreement about one battery
 * figure, marked critical, got a section of its own although the line asked for none.
 */
export const CRITICAL_HEADING =
  "The answer depends on these points, on which the sources disagree. Treat each one where it arises in the report, in at most three sentences, not in a section of its own:";

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

/** Every researcher of the run failed, so there is no evidence at all (live failure test, 2026-11-05). */
export function nothingResearched(state: EbdState): boolean {
  return state.results.length > 0 && state.results.every((r) => r.status === "failed");
}

export function buildOutline(state: EbdState): string[] {
  if (nothingResearched(state)) return [];
  const questions = synthesisQuestions(state.analysis).map((q) => q.text);
  // Section 20: a single synthesis question restates the request, which the writer already has, so it
  // is no outline; and a disagreement is treated where it arises, never in a section of its own. In
  // the batch of 2026-11-11 the whole outline of one run was "Where the sources disagree".
  return questions.length > 1 ? questions.slice(0, MAX_OUTLINE) : [];
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

/**
 * Section 20: the conflicts the writer is told about. Critical ones only, those
 * with a client claim at stake first, at most MAX_CRITICAL_LINES. A conflict whose claim has a
 * verdict is left to the premise line. Records made without the critical mark count as critical
 * when their settle goal is necessary (section 9).
 */
export function criticalForWriter(state: EbdState): Conflict[] {
  const verdicts = assumptionVerdicts(state);
  const marked = state.conflicts.some((c) => typeof c.critical === "boolean");
  const necessarySettle = new Set(state.goals.filter((g) => g.settles && g.need === "necessary").map((g) => g.id));
  const critical = (c: Conflict) => isCritical(c) || (!marked && c.settleGoal !== null && necessarySettle.has(c.settleGoal));
  const decided = (c: Conflict) => c.claim !== null && (verdicts[c.claim] === "supported" || verdicts[c.claim] === "contradicted");
  const kinds: Conflict["type"][] = ["source_vs_source", "evidence_vs_assumption", "time_dependent"];
  return state.conflicts
    .filter((c) => kinds.includes(c.type) && critical(c) && !decided(c))
    .sort((x, y) => Number(y.claim !== null) - Number(x.claim !== null))
    .slice(0, MAX_CRITICAL_LINES);
}

export function buildGuidance(state: EbdState): string {
  const a = state.analysis;
  if (a.status === "out_of_scope") {
    // Lab 4 review (2026-10-26): with no material, the writer's usual 3–5 sections became generic advice.
    const reason = a.status_reason?.trim() || "the request is out of scope";
    return `Nothing was researched: ${reason}${/[.!?]$/.test(reason) ? "" : "."} Write only the title and one paragraph of at most four sentences: why the question cannot be answered yet and what the client could provide. Add no other sections and no general advice.`;
  }
  // Live failure test (2026-11-05): with every researcher failed, the usual plan gave 431–773 words of nothing.
  if (nothingResearched(state)) {
    return "Nothing could be researched: every researcher failed for technical reasons, so there is no evidence. Write only the title and one paragraph of at most four sentences: say that the research could not be carried out, so the question is not answered, and that it should be run again. Do not answer from general knowledge, and do not judge the question's premises.";
  }
  const out: string[] = [];

  const directives = directiveLines(a, "writer");
  if (directives.length) out.push(`Follow the client's directives:\n${directives.map((d) => `- ${d}`).join("\n")}`);
  const limit = lengthLimit(a);
  if (limit) out.push(`The client limits the length ("${limit}"). This comes before everything below: answer the question first, give each disagreement and each gap at most one sentence, and leave out detail the client did not ask for.`);

  // Section 20: the writer gets the analysis's reading of the question in one
  // sentence, and not the planned contents, and only when the question cannot be taken at its word:
  // a premise that the evidence does not support, or a term with several meanings. Rewrites from the
  // saved notes of 2026-11-11: without the reading, the report on "Why did NASA launch ... in 2018?"
  // explained the date and left out the mission's purposes. Where the premises hold, the client's own
  // words are the reading; with the line added anyway, the five reports came out 16% shorter (one
  // rewrite of each).
  const verdicts = assumptionVerdicts(state);
  // Section 27: a claim taken as given was not checked, so its missing verdict says nothing against
  // it. It counts here, and gets a line below, only when the evidence contradicted it after all.
  const given = new Set((state.premises?.given ?? []).map((g) => g.id));
  const silent = (id: string) => given.has(id) && verdicts[id] !== "contradicted";
  const reread = a.assumptions.some((x) => !silent(x.id) && verdicts[x.id] !== "supported") || a.rom.objects.some((o) => o.readings.length > 0);
  if (reread && a.restated_request.trim()) out.push(`${READING_LABEL} ${a.restated_request.trim()}`);

  // Section 20: the writer gets neither the planned contents of each part nor a list of the parts the
  // notes cover. The plan named the first planned questions as the evidence to use, and in the batch
  // of 2026-11-11 the report on EBD left out what another goal's notes covered; a list of the covered
  // parts made the writer give every part a section. The labels of the material show the parts.
  const premises = a.assumptions.flatMap((x) => {
    if (silent(x.id)) return [];
    switch (verdicts[x.id]) {
      case "contradicted":
        return [`- The question presupposes: "${x.claim}" The evidence contradicts this; say so plainly early in the report.`];
      case "unsettled":
        // Section 20: the report does not have to say so. In the live batch of 2026-11-11 the analyst
        // left "EBD stands for Environment Based Design" unsettled, and the report opened by doubting
        // what the question itself spells out.
        return [`- The question presupposes: "${x.claim}" The evidence neither confirms nor contradicts this; do not present it as established.`];
      case "supported":
        // Section 20: a premise that holds needs no instruction.
        return [];
      default:
        return [`- The question presupposes: "${x.claim}" This could not be checked; do not present it as established.`];
    }
  });
  if (premises.length) out.push(`What the evidence shows about the question's premises:\n${premises.join("\n")}`);

  // Section 20: only the critical conflicts get a line, each treated where it arises. Every other
  // disagreement is left to the writer's own rule for notes that disagree. A finding against the
  // plan's own assumption changed the plan, not the report.
  const critical = criticalForWriter(state).map((c) => {
    if (c.type === "time_dependent") return `- ${plain(c.statement)} Both hold, at different times: ${plain(c.condition)}`;
    if (c.status === "settled") return `- ${plain(c.statement)} This was researched further, and the notes show which account holds and why.`;
    // "The source the notes cite": in the live run of 2026-11-11 the writer gave a publisher that the
    // statement named, and that the notes cite without a link, an invented address.
    return `- ${plain(c.statement)} Give both sides, each with the source the notes cite for it${hostsOf(state, [...c.sideA, ...c.sideB])}, and say which one the report follows and why, or that the evidence does not decide it.`;
  });
  if (critical.length) out.push(`${CRITICAL_HEADING}\n${critical.join("\n")}`);
  const apart = state.conflicts.flatMap((c) =>
    c.type === "off_target"
      ? [`- Some sources concern a different referent with the same name (${plain(c.statement)}). Leave them out, and distinguish the terms only where needed.`]
      : c.type === "evidence_vs_frame"
        ? [`- Some evidence falls outside the question's ${c.sideB[0]?.replace("_", " ") ?? "frame"}: ${plain(c.statement)} Use it only as context and say so.`]
        : [],
  );
  if (apart.length) out.push(`Evidence to keep apart:\n${apart.join("\n")}`);

  const defaults = (["purpose", "time_frame", "place"] as const)
    .filter((k) => a.frame[k].basis === "default" && a.frame[k].value !== null)
    .map((k) => `- ${k.replace("_", " ")}: ${a.frame[k].value}`);
  if (defaults.length) out.push(`The client did not state these; they were assumed. Mention them only where they change the answer:\n${defaults.join("\n")}`);

  // Evidence status of necessary goals the research could not complete.
  // Lab 5 review, change 8: a goal ended only by researcher failures is a failure, not an absence of sources.
  const failed = state.goals.filter((g) => g.need === "necessary" && !g.settles && endedByFailures(g));
  // A goal of the plan's map asked for parts the analyst assumed; a part nobody found is not something the client was promised.
  const unfinished = state.goals.filter((g) => g.need === "necessary" && (g.status === "exhausted" || g.status === "disputed") && !g.settles && !failed.includes(g) && !eventOf(state, g));
  const none = unfinished.filter((g) => g.partsMet === 0);
  if (none.length) out.push(`No reliable source was found for these; say so where relevant instead of guessing:\n${none.map((g) => `- ${g.text}`).join("\n")}`);
  // Section 20: a partly established goal gets no line. Its notes show what was found, the
  // researchers' own gap lines show what was not, and the analyst's notes on what is missing are
  // written for the next researcher (a source to look for, a conflict ID), not for the writer.

  if (failed.length) {
    out.push(`These questions could not be researched because of technical failures, not for lack of sources. Do not claim that no source exists; where relevant, say only that the report does not cover them:\n${failed.map((g) => `- ${plain(g.text)}`).join("\n")}`);
  }

  // Section 20: no line for the goals a contradicted premise cancelled. The premise line says what
  // was contradicted, and the notes show what was researched: in the live batch of 2026-11-11 such a
  // line named the question about NASA's reasons as not pursued, although a goal had researched them.

  out.push("Do not open the report with these notes, and do not mention the research process.");
  return out.join("\n\n");
}

export function buildSynthesis(state: EbdState): SynthesisInput {
  const outline = buildOutline(state);
  return { material: buildMaterial(state), ...(outline.length ? { outline } : {}), guidance: buildGuidance(state) };
}
