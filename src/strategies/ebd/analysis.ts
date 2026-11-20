/**
 * The analysis of a request as the strategy keeps it: the reading of the request, its frame, the
 * objects it is about, the claims it takes for granted and the questions of the first plan.
 *
 * The structure is the output contract of the request analysis of Lab 2 (rev 2), which the strategy
 * ran as its first step until 2026-11-19. Since the consolidation of design section 32 the plan is
 * made in one call (environment.ts), and `analysisFromPlan` fills this structure from that plan: one
 * object for the subject and one for each term with several meanings, the claims as assumptions, the
 * check of the claims and the client's question. Goals, briefs, rounds, the writer's input and the
 * run viewer read it unchanged.
 */
import { z } from "zod";
import { toJsonSchema } from "@langchain/core/utils/json_schema";

const BASIS = ["explicit", "implied", "default", "unknown"] as const;
const FLAG_TYPES = ["prompt_injection", "missing_referent", "out_of_scope_part", "internal_conflict"] as const;
const DIRECTIVE_KINDS = ["source_preference", "report_format", "scope_limit", "other"] as const;
const OBJECT_KINDS = ["noun", "proper_noun", "verb", "adjective", "adverb", "number_or_date", "question_word", "other"] as const;
const RELATION_TYPES = ["constraint", "connection", "subject_verb", "verb_object"] as const;
const STANCES = ["presupposed", "asked", "neutral"] as const;
/** The question templates and the guidelines for answering them (design section 4). */
export const TEMPLATES = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"] as const;
export const GUIDELINES = ["G1", "G2", "G3", "G4", "G5", "G6", "G7"] as const;

const frameValue = z.object({
  value: z.string().nullable(),
  basis: z.enum(BASIS),
  evidence: z.array(z.string()),
});

export const AnalysisSchema = z.object({
  flags: z.array(z.object({ type: z.enum(FLAG_TYPES), detail: z.string(), evidence: z.array(z.string()) })),
  client_directives: z.array(z.object({ kind: z.enum(DIRECTIVE_KINDS), text: z.string(), evidence: z.array(z.string()) })),
  restated_request: z.string(),
  status: z.enum(["ok", "out_of_scope"]),
  status_reason: z.string().nullable(),
  frame: z.object({ purpose: frameValue, time_frame: frameValue, place: frameValue }),
  rom: z.object({
    objects: z.array(
      z.object({
        id: z.string(),
        text: z.string(),
        kind: z.enum(OBJECT_KINDS),
        role: z.enum(["product", "environment"]),
        status: z.enum(["self_evident", "needs_question"]),
        meaning: z.string(),
        readings: z.array(z.string()),
      }),
    ),
    relations: z.array(
      z.object({
        id: z.string(),
        type: z.enum(RELATION_TYPES),
        from: z.string(),
        to: z.string(),
        via: z.string().nullable(),
        stance: z.enum(STANCES),
      }),
    ),
    central_object_ids: z.array(z.string()),
  }),
  assumptions: z.array(
    z.object({
      id: z.string(),
      claim: z.string(),
      kind: z.enum(["asserted", "presupposed"]),
      relation_ids: z.array(z.string()),
      evidence: z.array(z.string()),
    }),
  ),
  questions: z.array(
    z.object({
      id: z.string(),
      object_ids: z.array(z.string()),
      template: z.enum(TEMPLATES),
      guideline: z.enum(GUIDELINES),
      text: z.string(),
      route: z.enum(["search", "synthesis"]),
      need: z.enum(["necessary", "completing"]),
      depends_on: z.array(z.string()),
      verifies: z.array(z.string()),
      done_when: z.string(),
      source_hints: z.array(z.string()),
    }),
  ),
  grounding: z.array(z.object({ object_id: z.string(), query: z.string(), url: z.string(), finding: z.string(), names: z.array(z.string()) })),
});
export type Analysis = z.infer<typeof AnalysisSchema>;
export type AnalysisQuestion = Analysis["questions"][number];

/** One fault a code check found in a model's reply. */
export type Issue = { code: string; path: string; message: string };

/** A tool as it is bound to a model: one function with a JSON schema for its arguments. */
export type FunctionTool = {
  type: "function";
  strict: boolean;
  function: { name: string; description: string; parameters: Record<string, unknown>; strict: boolean };
};

/** JSON Schema as sent to a provider: the LangChain conversion without the `$schema` key. */
export function apiJsonSchema(schema: z.ZodType): Record<string, unknown> {
  const strip = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(strip);
    if (node && typeof node === "object") {
      return Object.fromEntries(Object.entries(node).filter(([k]) => k !== "$schema").map(([k, v]) => [k, strip(v)]));
    }
    return node;
  };
  return strip(toJsonSchema(schema as never)) as Record<string, unknown>;
}

/** A question or objective that points at another one instead of naming its subject. */
export const BACK_REFERENCE = /\bQ\d+\b|\b(?:previous|earlier|first|second|preceding|above) (?:search )?questions?\b|\bthe ones identified\b/i;

/** Cut a text at a limit: at the end of a sentence when one ends in the last two fifths, else at a word. */
export function cutAt(text: string, max: number): string {
  if (text.length <= max) return text;
  const head = text.slice(0, max);
  const sentence = Math.max(head.lastIndexOf(". "), head.lastIndexOf("? "));
  if (sentence >= max * 0.6) return head.slice(0, sentence + 1);
  const space = head.lastIndexOf(" ");
  return (space > 0 ? head.slice(0, space) : head).replace(/[\s,;:(]+$/, "");
}

/**
 * The plan of last resort (design section 24.4): the request itself as one question to search and
 * one to answer, with no main parts and no check of its claims. Used when a run gets no usable plan
 * twice, so that a request in scope always gets a plan.
 */
export function minimalAnalysis(question: string, today: string): Analysis {
  const none = { value: null, basis: "unknown" as const, evidence: [] };
  const shared = { object_ids: ["O1"], template: "T1" as const, guideline: "G1" as const, need: "necessary" as const, verifies: [], source_hints: [] };
  return {
    flags: [],
    client_directives: [],
    restated_request: question,
    status: "ok",
    status_reason: null,
    frame: { purpose: none, time_frame: { value: `Latest available evidence as of ${today}.`, basis: "default", evidence: [] }, place: none },
    rom: {
      objects: [{ id: "O1", text: question, kind: "other", role: "environment", status: "needs_question", meaning: "The client's request as a whole; the request analysis gave no usable model of it.", readings: [] }],
      relations: [],
      central_object_ids: ["O1"],
    },
    assumptions: [],
    questions: [
      { ...shared, id: "Q1", text: question, route: "search", depends_on: [], done_when: "Answers the request in full: each main part a reader would expect, with its sources." },
      { ...shared, id: "Q2", text: question, route: "synthesis", depends_on: ["Q1"], done_when: "Answers the request from the evidence, and says what could not be established." },
    ],
    grounding: [],
  };
}
