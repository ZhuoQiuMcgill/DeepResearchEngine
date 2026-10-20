/**
 * EBD strategy module, v0 (Lab 3): the request analysis drives one round.
 *
 * - init runs the request analysis (option init: "fixed" or "agent"; agent mode
 *   uses the custom tools only, because strategies make no searches) and packs
 *   the first layer of search questions into briefs (design section 7).
 * - observe stops after that round.
 * - finalize passes every note to the writer, with the client's report directives
 *   and the assumptions to check as guidance.
 *
 * Each reader gets only its slice of the analysis: a researcher gets one brief
 * (objective, key questions, the frame and the client's evidence directives as
 * constraints); the writer gets the guidance.
 *
 * The EBD loop itself (goals, conflicts, round analysis, stop rules) is designed in
 * DESIGN.md and not built yet.
 */
import { z } from "zod";
import {
  CONTRACT_VERSION,
  type JsonValue,
  type ResearchBriefInput,
  type ResearchResult,
  type ResearchStrategy,
  type StrategyContext,
  type StrategyModule,
  type StrategyStep,
  type SynthesisInput,
} from "../../core/index.js";
import { runAgentAnalysis, runFixedAnalysis, type Analysis, type AnalysisQuestion } from "./request/index.js";

const OptionsSchema = z
  .object({
    /** How init runs the request analysis. */
    init: z.enum(["fixed", "agent"]).default("fixed"),
    maxPerRound: z.number().int().min(1).max(20).default(4),
    questionsPerBrief: z.number().int().min(1).max(6).default(3),
  })
  .strict();
type EbdOptions = z.infer<typeof OptionsSchema>;

type EbdState = {
  question: string;
  init: { mode: string; accepted: boolean; fallback: boolean; attempts: number; stopReason: string };
  analysis: Analysis;
  notes: { briefId: string; label: string; notes: string }[];
};

const VERIFY =
  "State whether the evidence supports, contradicts or does not settle the claim. Look specifically for evidence that contradicts it. Give each source's finding with its date and scope; report disagreements, do not resolve them.";

function frameConstraints(a: Analysis): string[] {
  const out: string[] = [];
  for (const [label, f] of [["Time frame", a.frame.time_frame], ["Place", a.frame.place]] as const) {
    if (f.value !== null && f.basis !== "unknown") out.push(`${label} (${f.basis}): ${f.value}`);
  }
  return out;
}

/**
 * Who must follow each kind of client directive (design sections 7 and 12).
 * Researchers get what limits the evidence; the writer gets what shapes the
 * report; scope limits and unclassified directives go to both, so none is lost.
 */
const DIRECTIVE_READERS: Record<Analysis["client_directives"][number]["kind"], { researchers: boolean; writer: boolean; label: string }> = {
  source_preference: { researchers: true, writer: false, label: "Client source preference" },
  scope_limit: { researchers: true, writer: true, label: "Client scope limit" },
  report_format: { researchers: false, writer: true, label: "Client report format" },
  other: { researchers: true, writer: true, label: "Client directive" },
};

/** One line per directive, with the client's own words next to the analyst's wording. */
export function directiveLines(a: Analysis, reader: "researchers" | "writer"): string[] {
  return a.client_directives
    .filter((d) => DIRECTIVE_READERS[d.kind][reader])
    .map((d) => `${DIRECTIVE_READERS[d.kind].label}: ${d.text}${d.evidence.length ? ` (client's words: ${d.evidence.map((e) => `"${e}"`).join("; ")})` : ""}`);
}

/** Writer guidance: out-of-scope notice, the client's report directives, and the assumptions to address. */
export function writerGuidance(a: Analysis): string {
  if (a.status === "out_of_scope") return `Nothing was researched: ${a.status_reason ?? "the request is out of scope"}`;
  const directives = directiveLines(a, "writer");
  return [
    ...(directives.length ? [`Follow the client's directives:\n${directives.map((d) => `- ${d}`).join("\n")}`] : []),
    ...(a.assumptions.length ? [`The question presupposes the following; state plainly what the evidence shows about each: ${a.assumptions.map((x) => x.claim).join(" ")}`] : []),
  ].join("\n\n");
}

/** First-layer search questions, grouped by their primary object, a few per brief. */
export function firstRoundBriefs(a: Analysis, options: EbdOptions, remaining: number): ResearchBriefInput[] {
  const groups: { key: string; questions: AnalysisQuestion[] }[] = [];
  for (const q of a.questions.filter((x) => x.route === "search" && x.depends_on.length === 0)) {
    const key = q.object_ids[0] ?? q.id;
    const open = groups.find((g) => g.key === key && g.questions.length < options.questionsPerBrief);
    if (open) open.questions.push(q);
    else groups.push({ key, questions: [q] });
  }
  const objectText = (id: string) => a.rom.objects.find((o) => o.id === id)?.text ?? id;
  return groups.slice(0, Math.min(options.maxPerRound, remaining)).map((g, i) => ({
    objective: g.questions.length === 1 ? g.questions[0]!.text : `Answer the key questions below about "${objectText(g.key)}".`,
    keyQuestions: g.questions.map((q) => `[${q.id}] ${q.text}`),
    constraints: [...frameConstraints(a), ...directiveLines(a, "researchers")],
    sourceHints: [...new Set(g.questions.flatMap((q) => q.source_hints))].slice(0, 5),
    instructions: g.questions.map((q) => `For [${q.id}], a sufficient answer contains: ${q.done_when}${q.guideline === "G7" ? ` ${VERIFY}` : ""}`).join("\n"),
    priority: 100 - i,
    tag: g.questions.map((q) => q.id).join(","),
  }));
}

class EbdStrategy implements ResearchStrategy<EbdState> {
  readonly name = "ebd";

  constructor(private readonly options: EbdOptions) {}

  async init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<EbdState>> {
    const args = { question: input.question, today: ctx.today, model: ctx.model };
    const out = this.options.init === "agent" ? await runAgentAnalysis(args) : await runFixedAnalysis(args);
    if (!out.analysis) throw new Error(`Request analysis (${out.mode}) produced no usable analysis: ${out.errors.map((e) => e.message).join("; ").slice(0, 500)}`);
    const a = out.analysis;
    const state: EbdState = {
      question: input.question,
      init: { mode: out.mode, accepted: out.accepted, fallback: out.fallback, attempts: out.attempts, stopReason: out.stopReason },
      analysis: a,
      notes: [],
    };
    if (a.status === "out_of_scope") {
      return { state, decision: { briefs: [], stop: true, rationale: `Out of scope: ${a.status_reason ?? ""}` } };
    }
    const briefs = firstRoundBriefs(a, this.options, ctx.budget.researchersRemaining);
    const served = briefs.flatMap((b) => b.keyQuestions);
    const rationale = [
      `Request analysis (${out.mode} mode, ${out.accepted ? "accepted" : "fallback"} after ${out.attempts} attempt(s)): ${a.rom.objects.length} objects, ${a.assumptions.length} assumptions, ${a.questions.length} questions.`,
      a.assumptions.length ? `Assumptions to verify: ${a.assumptions.map((x) => x.claim).join(" ")}` : "No assumptions to verify.",
      `First round serves ${served.length} question(s): ${served.join(" ")}`,
    ].join("\n");
    return { state, decision: { briefs, stop: false, rationale } };
  }

  async observe(state: EbdState, results: ResearchResult[], _ctx: StrategyContext): Promise<StrategyStep<EbdState>> {
    const notes = results.filter((r) => r.status === "ok").map((r) => ({ briefId: r.brief.id, label: r.brief.objective, notes: r.notes }));
    return {
      state: { ...state, notes: [...state.notes, ...notes] },
      decision: { briefs: [], stop: true, rationale: "v0 serves only the first layer of questions; the EBD round analysis is not built yet." },
    };
  }

  async finalize(state: EbdState, _ctx: StrategyContext): Promise<SynthesisInput> {
    const guidance = writerGuidance(state.analysis);
    return { material: state.notes.map((n) => ({ label: n.label, notes: n.notes })), ...(guidance ? { guidance } : {}) };
  }
}

const ebd: StrategyModule = {
  name: "ebd",
  description: "EBD v0: request analysis (fixed or agent mode) plans one round from its first layer of search questions.",
  contractVersion: CONTRACT_VERSION,
  create: (options?: JsonValue) => new EbdStrategy(OptionsSchema.parse(options ?? {})),
};
export default ebd;
