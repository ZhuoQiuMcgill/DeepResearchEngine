/**
 * Request analysis rev 2: the output contract of the EBD request analyst. It is
 * Lab 2 rev 1.3 without the client route (D-A, 2026-10-19), plus source hints
 * on search questions and grounding entries for names found by search.
 *
 * Every schema exists twice:
 * - the API schema is sent to the model and carries only types, enums and required
 *   fields, which both providers' strict modes accept;
 * - the full schema adds lengths, counts and ID formats, which code checks.
 */
import { z } from "zod";
import { toJsonSchema } from "@langchain/core/utils/json_schema";

export const LIMITS = {
  restated: 600,
  short: 300,
  long: 400,
  hint: 80,
  name: 80,
  objects: 30,
  questions: 20,
  objectsPerQuestion: 10,
  hints: 3,
  grounding: 3,
  names: 5,
} as const;

const BASIS = ["explicit", "implied", "default", "unknown"] as const;
const FLAG_TYPES = ["prompt_injection", "missing_referent", "out_of_scope_part", "internal_conflict"] as const;
const DIRECTIVE_KINDS = ["source_preference", "report_format", "scope_limit", "other"] as const;
const OBJECT_KINDS = ["noun", "proper_noun", "verb", "adjective", "adverb", "number_or_date", "question_word", "other"] as const;
const RELATION_TYPES = ["constraint", "connection", "subject_verb", "verb_object"] as const;
const STANCES = ["presupposed", "asked", "neutral"] as const;
export const TEMPLATES = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"] as const;
export const GUIDELINES = ["G1", "G2", "G3", "G4", "G5", "G6", "G7"] as const;

function analysisSchema(full: boolean) {
  const text = (max: number) => (full ? z.string().min(1).max(max) : z.string());
  const id = (prefix: string) =>
    full ? z.string().regex(new RegExp(`^${prefix}[1-9][0-9]*$`), `must be ${prefix}1, ${prefix}2, ...`) : z.string();
  const list = <T extends z.ZodType>(item: T, max?: number) => (full && max !== undefined ? z.array(item).max(max) : z.array(item));
  const quote = text(LIMITS.short).describe("Copied exactly from the request");
  const frameValue = z.object({
    value: text(LIMITS.long).nullable().describe("null when basis is unknown"),
    basis: z.enum(BASIS),
    evidence: list(quote).describe("Quotes for explicit or implied values; empty for default and unknown"),
  });

  return z.object({
    flags: list(
      z.object({
        type: z.enum(FLAG_TYPES),
        detail: text(LIMITS.short),
        evidence: list(quote),
      }),
    ),
    client_directives: list(
      z.object({
        kind: z.enum(DIRECTIVE_KINDS),
        text: text(LIMITS.short),
        evidence: list(quote),
      }),
    ),
    restated_request: text(LIMITS.restated),
    status: z.enum(["ok", "out_of_scope"]),
    status_reason: text(LIMITS.short).nullable().describe("null when status is ok"),
    frame: z.object({ purpose: frameValue, time_frame: frameValue, place: frameValue }),
    rom: z.object({
      objects: list(
        z.object({
          id: id("O"),
          text: quote,
          kind: z.enum(OBJECT_KINDS),
          role: z.enum(["product", "environment"]),
          status: z.enum(["self_evident", "needs_question"]),
          meaning: text(LIMITS.short),
          readings: list(text(LIMITS.short), 5).describe("Only for a term with two or more unrelated meanings; otherwise empty"),
        }),
        LIMITS.objects,
      ),
      relations: list(
        z.object({
          id: id("R"),
          type: z.enum(RELATION_TYPES),
          from: id("O"),
          to: id("O"),
          via: text(LIMITS.short).nullable().describe("Preposition or connecting word, if any"),
          stance: z.enum(STANCES),
        }),
      ),
      central_object_ids: list(id("O")),
    }),
    assumptions: list(
      z.object({
        id: id("A"),
        claim: text(LIMITS.short),
        kind: z.enum(["asserted", "presupposed"]),
        relation_ids: list(id("R")),
        evidence: list(quote),
      }),
    ),
    questions: list(
      z.object({
        id: id("Q"),
        object_ids: list(id("O"), LIMITS.objectsPerQuestion),
        template: z.enum(TEMPLATES),
        guideline: z.enum(GUIDELINES),
        text: text(LIMITS.long),
        route: z.enum(["search", "synthesis"]),
        need: z.enum(["necessary", "completing"]),
        depends_on: list(id("Q")),
        verifies: list(id("A")),
        done_when: text(LIMITS.long),
        source_hints: list(text(LIMITS.hint), LIMITS.hints).describe("Search questions: up to 3 generic kinds of sources. Synthesis questions: empty"),
      }),
      LIMITS.questions,
    ),
    grounding: list(
      z.object({
        object_id: id("O"),
        query: text(LIMITS.short),
        url: text(2000).describe("A result URL the search tool reported"),
        finding: text(LIMITS.short),
        names: list(text(LIMITS.name), LIMITS.names).describe("Names taken from this result that the request does not contain"),
      }),
      LIMITS.grounding,
    ).describe("One entry per search result relied on; empty when no search was made"),
  });
}

export const AnalysisApiSchema = analysisSchema(false);
export const AnalysisFullSchema = analysisSchema(true);
export type Analysis = z.infer<typeof AnalysisApiSchema>;
export type AnalysisQuestion = Analysis["questions"][number];

export const SPAN_KINDS = [
  "url",
  "quoted",
  "acronym_pair",
  "relative_time",
  "date",
  "restrictor",
  "comparison",
  "negation",
  "quantifier",
  "modality",
  "number",
  "question_word",
  "name",
] as const;
export type SpanKind = (typeof SPAN_KINDS)[number];

export const ScanInputSchema = z.object({});

export const ScanOutputSchema = z.object({
  run_date: z.string(),
  spans: z.array(
    z.object({
      id: z.string(),
      kind: z.enum(SPAN_KINDS),
      text: z.string(),
      start: z.number().int().nonnegative(),
      end: z.number().int().nonnegative(),
      window: z.object({ from: z.string().nullable(), to: z.string().nullable() }).nullable(),
    }),
  ),
  rule: z.string(),
});
export type ScanResult = z.infer<typeof ScanOutputSchema>;
export type Span = ScanResult["spans"][number];

export const IssueSchema = z.object({ code: z.string(), path: z.string(), message: z.string() });
export type Issue = z.infer<typeof IssueSchema>;

export const SubmitOutputSchema = z.object({
  accepted: z.boolean(),
  submission: z.number().int().positive(),
  submissions_left: z.number().int().nonnegative(),
  errors: z.array(IssueSchema.extend({ n: z.number().int().positive() })),
  warnings: z.array(IssueSchema),
  counts: z
    .object({ objects: z.number(), assumptions: z.number(), search: z.number(), synthesis: z.number(), grounding: z.number() })
    .nullable(),
});
export type SubmitOutput = z.infer<typeof SubmitOutputSchema>;

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
