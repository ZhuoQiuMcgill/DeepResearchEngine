/**
 * Notes reviewer: one per successful researcher, run in parallel after every
 * round. It reads that researcher's whole notes with the search provenance the
 * platform recorded, and returns a structured assessment: per key question,
 * whether it is answered and sourced, plus the figures the notes report.
 *
 * The router starts from these assessments instead of reading every note, and
 * the conflict checker compares the figures. The host drops any figure whose
 * quote is not in the notes, so a figure the model invents never reaches them.
 */
import { z } from "zod";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { AIMessage } from "@langchain/core/messages";
import type { ResearchResult } from "../../core/index.js";
import { reviewerPrompt } from "./prompts.js";

const NOTES_CHARS = 40_000;
const MAX_FIGURES = 40;
const MAX_WARNINGS = 6;

export const QUALIFIERS = ["exact", "about", "at least", "at most"] as const;

const ReviewSchema = z.object({
  keyQuestions: z
    .array(
      z.object({
        number: z.number().int().describe("1-based number of the brief's key question"),
        status: z.enum(["answered", "partial", "unanswered"]),
        sourced: z.enum(["yes", "partly", "no"]),
        gap: z.string().describe("What is missing or weak, in one sentence; empty string if nothing"),
      }),
    )
    .describe("One entry per key question of the brief, in order"),
  figures: z
    .array(
      z.object({
        quantity: z.string().describe("What is measured and for which entity"),
        value: z.number().describe("Plain number in the unit below, scale words written out"),
        unit: z.string().describe("Unit as written in the notes; empty string for a plain count"),
        qualifier: z.enum(QUALIFIERS),
        asOf: z.string().describe("YYYY-MM-DD, YYYY-MM or YYYY; empty string if none"),
        quote: z.string().describe("The phrase in the notes that states the figure, copied exactly"),
        url: z.string().describe("URL cited for the figure; empty string if none"),
      }),
    )
    .describe("Figures the notes state, including ones outside the brief, each once, at most 40, most important first"),
  warnings: z.array(z.string()).describe("Problems the coordinator must know; empty list if none"),
});
export type RawReview = z.infer<typeof ReviewSchema>;

/** A figure as the checker and router see it. `id` is `<briefId>#<n>`. */
export type Figure = {
  id: string;
  briefId: string;
  quantity: string;
  value: number;
  unit: string;
  qualifier: (typeof QUALIFIERS)[number];
  asOf: string;
  quote: string;
  url: string;
};

export type KeyQuestionReview = {
  number: number;
  question: string;
  status: "answered" | "partial" | "unanswered";
  sourced: "yes" | "partly" | "no";
  gap: string;
};

/** One reviewer's output, kept in the strategy state. Plain JSON. */
export type Review = {
  briefId: string;
  round: number;
  objective: string;
  ok: boolean;
  error: string;
  keyQuestions: KeyQuestionReview[];
  figures: Figure[];
  warnings: string[];
  droppedFigures: number;
  inputTokens: number;
  outputTokens: number;
  ms: number;
};

export async function reviewNotes(model: BaseChatModel, input: { question: string; today: string; result: ResearchResult }): Promise<Review> {
  const r = input.result;
  const started = Date.now();
  const base = { briefId: r.brief.id, round: r.brief.round, objective: r.brief.objective };
  try {
    const reviewer = reviewerPrompt.pipe(model.withStructuredOutput(ReviewSchema, { method: "jsonSchema", name: "notes_review", includeRaw: true }));
    const out = (await reviewer.invoke({
      today: input.today,
      question: input.question,
      briefId: r.brief.id,
      objective: r.brief.objective,
      keyQuestions: r.brief.keyQuestions.map((q, i) => `${i + 1}. ${q}`).join("\n"),
      reported: String(r.sources.length),
      cited: String(r.sources.filter((s) => s.cited).length),
      unlisted: r.unlistedCitations.length ? r.unlistedCitations.join(", ") : "none",
      problems: r.diagnostics.length ? r.diagnostics.join("; ") : "none",
      notes: r.notes.slice(0, NOTES_CHARS),
    })) as { raw: AIMessage; parsed: RawReview | null };
    const usage = { inputTokens: out.raw.usage_metadata?.input_tokens ?? 0, outputTokens: out.raw.usage_metadata?.output_tokens ?? 0 };
    if (!out.parsed) throw new Error("the review did not match its schema");
    return { ...base, ok: true, error: "", ...validateReview(out.parsed, r), ...usage, ms: Date.now() - started };
  } catch (e) {
    // A failed review must not fail the round: the router falls back to read_notes.
    return {
      ...base,
      ok: false,
      error: String((e as Error).message ?? e).slice(0, 300),
      keyQuestions: [],
      figures: [],
      warnings: [],
      droppedFigures: 0,
      inputTokens: 0,
      outputTokens: 0,
      ms: Date.now() - started,
    };
  }
}

/** Host-side checks on a review. Exported for unit tests. */
export function validateReview(raw: RawReview, r: ResearchResult): Pick<Review, "keyQuestions" | "figures" | "warnings" | "droppedFigures"> {
  const questions = r.brief.keyQuestions;
  const seen = new Set<number>();
  const keyQuestions = raw.keyQuestions
    .filter((k) => k.number >= 1 && k.number <= questions.length && !seen.has(k.number) && seen.add(k.number))
    .sort((a, b) => a.number - b.number)
    .map((k) => ({ number: k.number, question: questions[k.number - 1]!, status: k.status, sourced: k.sourced, gap: k.gap.trim() }));

  const notes = flat(r.notes);
  const kept = raw.figures.filter((f) => Number.isFinite(f.value) && f.quote.trim() && notes.includes(flat(f.quote))).slice(0, MAX_FIGURES);
  const figures = kept.map((f, i) => ({
    id: `${r.brief.id}#${i + 1}`,
    briefId: r.brief.id,
    quantity: f.quantity.trim(),
    value: f.value,
    unit: f.unit.trim(),
    qualifier: f.qualifier,
    asOf: f.asOf.trim(),
    quote: f.quote.trim(),
    url: f.url.trim(),
  }));

  return {
    keyQuestions,
    figures,
    warnings: raw.warnings.map((w) => w.trim()).filter(Boolean).slice(0, MAX_WARNINGS),
    droppedFigures: raw.figures.length - figures.length,
  };
}

/** Text compared without Markdown emphasis, typographic quotes, case or spacing. */
function flat(s: string): string {
  return s
    .replace(/[*_`]/g, "")
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, "-")
    .replace(/\s+/g, " ")
    .toLowerCase()
    .trim();
}
