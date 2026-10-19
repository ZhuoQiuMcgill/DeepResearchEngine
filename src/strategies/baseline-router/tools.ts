/**
 * The router's custom tools. They are built for each follow-up decision over
 * the round just finished, so the ids and limits in the schemas are the real
 * ones. Calls are validated twice: by the provider against the strict schema,
 * and here against the same schema plus rules that need the round's data
 * (evidence rules). A rejected call returns an error the model can act on.
 */
import { z } from "zod";
import { tool, type StructuredToolInterface } from "@langchain/core/tools";
import { parseNotes, type BudgetView, type ResearchBriefInput, type ResearchResult } from "../../core/index.js";

export const GAP_TYPES = ["unanswered", "unsourced", "contradiction", "failed"] as const;
export type GapType = (typeof GAP_TYPES)[number];

const NOTES_CHARS = 12_000;
const SOURCES_LISTED = 40;

export type RoundContext = {
  results: ResearchResult[];
  budget: BudgetView;
  /** Most researchers the follow-up round may launch. */
  maxBriefs: number;
  /** Round the follow-up researchers would start. */
  round: number;
};

export type Outcome =
  | { kind: "launch"; briefs: ResearchBriefInput[]; rationale: string }
  | { kind: "finish"; rationale: string };

export interface RouterTools {
  /** Tool definitions to bind to the model. */
  definitions: StructuredToolInterface[];
  /** Run one call: validate, execute, and return the text the model sees. */
  run(name: string, args: unknown): { ok: boolean; text: string };
  /** Set once launch_followups or finish_research succeeds. */
  outcome(): Outcome | undefined;
}

export function buildRouterTools(ctx: RoundContext): RouterTools {
  const ids = ctx.results.map((r) => r.brief.id) as [string, ...string[]];
  const byId = new Map(ctx.results.map((r) => [r.brief.id, r]));
  const notesRead = new Set<string>();
  const sourcesChecked = new Set<string>();
  let decided: Outcome | undefined;

  const schemas = {
    get_round_status: z.object({}).strict(),
    read_notes: z
      .object({
        brief_id: z.enum(ids).describe("Round-1 researcher id"),
        section: z
          .number()
          .int()
          .min(1)
          .nullable()
          .describe("1-based key-question section of the notes; null for the whole notes"),
      })
      .strict(),
    check_sources: z.object({ brief_id: z.enum(ids).describe("Round-1 researcher id") }).strict(),
    launch_followups: z
      .object({
        briefs: z
          .array(
            z
              .object({
                objective: z.string().describe("What this researcher must find out; one gap only"),
                keyQuestions: z.array(z.string()).min(1).max(6).describe("Specific questions the notes must answer"),
                constraints: z.array(z.string()).describe("Bounds carried from the question: time, place, scope"),
                sourceHints: z.array(z.string()).describe("Kinds of sources to prioritise"),
                gap: z.enum(GAP_TYPES).describe("unanswered, unsourced, contradiction, or failed"),
                targets: z.array(z.enum(ids)).min(1).describe("Round-1 researchers whose results show this gap"),
                priority: z.number().int().min(1).max(10).describe("10 runs first if the budget cannot cover every brief"),
              })
              .strict(),
          )
          .min(1)
          .max(ctx.maxBriefs),
        rationale: z.string().describe("Which critical gaps remain and why each needs a researcher"),
      })
      .strict(),
    finish_research: z
      .object({ rationale: z.string().describe("Why no follow-up round is needed") })
      .strict(),
  };

  const definitions: StructuredToolInterface[] = [
    tool(async () => "", {
      name: "get_round_status",
      description:
        "The researcher budget and, for each round-1 researcher, its status, failure, usage (searches, page reads, tokens, time), source counts and problems the system observed.",
      schema: schemas.get_round_status,
    }),
    tool(async () => "", {
      name: "read_notes",
      description: "One round-1 researcher's notes: the whole notes, or one key-question section with its takeaway, cited findings, inferences and gaps.",
      schema: schemas.read_notes,
    }),
    tool(async () => "", {
      name: "check_sources",
      description:
        "One round-1 researcher's sources: every URL the search tool reported, whether the notes cite it, cited URLs the tool never reported, and source domains.",
      schema: schemas.check_sources,
    }),
    tool(async () => "", {
      name: "launch_followups",
      description: `Release the follow-up round: at most ${ctx.maxBriefs} new researchers, each targeting one gap shown by round-1 results. Ends the decision.`,
      schema: schemas.launch_followups,
    }),
    tool(async () => "", {
      name: "finish_research",
      description: "Do not launch a follow-up round; the report is written from round 1. Ends the decision.",
      schema: schemas.finish_research,
    }),
  ];

  const handlers: Record<keyof typeof schemas, (args: any) => object> = {
    get_round_status: () => roundStatus(ctx),
    read_notes: ({ brief_id, section }: { brief_id: string; section: number | null }) => {
      const r = byId.get(brief_id)!;
      notesRead.add(brief_id);
      if (r.status === "failed") return { brief_id, status: "failed", failure: r.failure ?? null };
      if (section === null) {
        const truncated = r.notes.length > NOTES_CHARS;
        return { brief_id, notes: r.notes.slice(0, NOTES_CHARS), ...(truncated ? { truncated_from_chars: r.notes.length } : {}) };
      }
      const sections = parseNotes(r.notes).sections;
      const s = sections[section - 1];
      if (!s) throw new RuleError(`${brief_id} has ${sections.length} parsed section(s); section ${section} does not exist`);
      return { brief_id, section, of: sections.length, ...s };
    },
    check_sources: ({ brief_id }: { brief_id: string }) => {
      const r = byId.get(brief_id)!;
      sourcesChecked.add(brief_id);
      const domains: Record<string, number> = {};
      for (const s of r.sources) {
        const host = hostOf(s.url);
        domains[host] = (domains[host] ?? 0) + 1;
      }
      return {
        brief_id,
        sources_reported: r.sources.length,
        cited: r.sources.filter((s) => s.cited).length,
        sources: r.sources.slice(0, SOURCES_LISTED).map((s) => ({ url: s.url, ...(s.title ? { title: s.title } : {}), cited: s.cited })),
        ...(r.sources.length > SOURCES_LISTED ? { sources_omitted: r.sources.length - SOURCES_LISTED } : {}),
        cited_but_never_reported: r.unlistedCitations,
        domains: Object.entries(domains)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 12)
          .map(([domain, count]) => ({ domain, count })),
      };
    },
    launch_followups: (args: z.infer<typeof schemas.launch_followups>) => {
      const problems = followupRules(args, ctx, byId, notesRead, sourcesChecked);
      if (problems.length) throw new RuleError(problems.join("; "));
      decided = {
        kind: "launch",
        rationale: args.rationale.trim(),
        briefs: args.briefs.map((b) => ({
          objective: b.objective.trim(),
          keyQuestions: b.keyQuestions.map((q) => q.trim()),
          constraints: b.constraints,
          sourceHints: b.sourceHints,
          priority: b.priority,
          tag: `${b.gap}:${b.targets.join(",")}`,
        })),
      };
      return { launched: args.briefs.length, round: ctx.round };
    },
    finish_research: ({ rationale }: { rationale: string }) => {
      if (rationale.trim().length < 20) throw new RuleError("rationale must say why no follow-up round is needed (at least 20 characters)");
      decided = { kind: "finish", rationale: rationale.trim() };
      return { finished: true };
    },
  };

  return {
    definitions,
    outcome: () => decided,
    run(name, args) {
      if (!(name in schemas)) return reject("unknown_tool", `no tool named ${JSON.stringify(name)}`);
      if (decided && (name === "launch_followups" || name === "finish_research")) {
        return reject("already_decided", `the decision was already made (${decided.kind})`);
      }
      const parsed = schemas[name as keyof typeof schemas].safeParse(args ?? {});
      if (!parsed.success) {
        return reject("invalid_arguments", parsed.error.issues.map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`).join("; "));
      }
      try {
        return { ok: true, text: JSON.stringify(handlers[name as keyof typeof schemas](parsed.data)) };
      } catch (e) {
        if (e instanceof RuleError) return reject("rule_violation", e.message);
        throw e;
      }
    },
  };
}

class RuleError extends Error {}

function reject(code: string, message: string) {
  return { ok: false, text: JSON.stringify({ error: { code, message } }) };
}

function roundStatus(ctx: RoundContext) {
  return {
    followup_round: ctx.round,
    budget: {
      researchers_total: ctx.budget.researchersTotal,
      researchers_used: ctx.budget.researchersUsed,
      researchers_remaining: ctx.budget.researchersRemaining,
      max_new_researchers: ctx.maxBriefs,
      tool_calls_per_researcher: ctx.budget.toolCallsPerResearcher,
    },
    researchers: ctx.results.map((r) => {
      const parsed = r.status === "ok" ? parseNotes(r.notes) : undefined;
      return {
        id: r.brief.id,
        objective: r.brief.objective,
        status: r.status,
        ...(r.failure ? { failure: `${r.failure.kind}: ${r.failure.message.slice(0, 200)}` } : {}),
        searches: r.usage.searches,
        page_reads: r.usage.pageReads,
        input_tokens: r.usage.inputTokens,
        output_tokens: r.usage.outputTokens,
        duration_s: Math.round(r.durationMs / 1000),
        sources_reported: r.sources.length,
        sources_cited: r.sources.filter((s) => s.cited).length,
        cited_but_never_reported: r.unlistedCitations.length,
        key_questions: r.brief.keyQuestions.length,
        sections_parsed: parsed?.sections.length ?? 0,
        gaps_reported: parsed?.sections.reduce((n, s) => n + s.gaps.length, 0) ?? 0,
        problems: r.diagnostics,
      };
    }),
  };
}

/** Rules a launch must meet beyond its schema. Exported for unit tests. */
export function followupRules(
  args: { briefs: { objective: string; keyQuestions: string[]; gap: GapType; targets: string[] }[]; rationale: string },
  ctx: RoundContext,
  byId: Map<string, ResearchResult>,
  notesRead: Set<string>,
  sourcesChecked: Set<string>,
): string[] {
  const problems: string[] = [];
  if (args.rationale.trim().length < 20) problems.push("rationale must name the critical gaps (at least 20 characters)");
  if (args.briefs.length > ctx.maxBriefs) problems.push(`at most ${ctx.maxBriefs} researchers may be launched`);
  const done = new Set(ctx.results.map((r) => norm(r.brief.objective)));
  const seen = new Set<string>();
  args.briefs.forEach((b, i) => {
    const at = `briefs[${i}]`;
    if (b.objective.trim().length < 10) problems.push(`${at}.objective is too short to direct a researcher`);
    if (b.keyQuestions.some((q) => q.trim().length < 5)) problems.push(`${at}.keyQuestions has an empty or trivial question`);
    const key = norm(b.objective);
    if (done.has(key)) problems.push(`${at} repeats a round-1 objective; target the gap instead`);
    if (seen.has(key)) problems.push(`${at} duplicates another new brief`);
    seen.add(key);
    // Evidence rules: the gap must have been looked at with the tool that shows it.
    if (b.gap === "failed" && !b.targets.some((t) => byId.get(t)?.status === "failed")) {
      problems.push(`${at} is a 'failed' gap but none of its targets failed`);
    }
    if (b.gap === "unanswered" && !b.targets.some((t) => notesRead.has(t))) {
      problems.push(`${at} is an 'unanswered' gap: call read_notes on ${b.targets.join(" or ")} first`);
    }
    if (b.gap === "unsourced" && !b.targets.some((t) => sourcesChecked.has(t))) {
      problems.push(`${at} is an 'unsourced' gap: call check_sources on ${b.targets.join(" or ")} first`);
    }
    if (b.gap === "contradiction") {
      if (new Set(b.targets).size < 2) problems.push(`${at} is a 'contradiction' gap: name at least two researchers`);
      else if (b.targets.filter((t) => notesRead.has(t)).length < 2) {
        problems.push(`${at} is a 'contradiction' gap: call read_notes on both sides first`);
      }
    }
  });
  return problems;
}

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "(invalid url)";
  }
}
