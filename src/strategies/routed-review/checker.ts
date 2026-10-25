/**
 * Conflict checker: compares figures that different researchers report for the
 * same quantity. It runs whenever at least two researchers reported figures.
 *
 * Figures with the same quantity name are grouped in code; the model groups the
 * rest (paraphrased names). The comparison (unit conversion, tolerance,
 * qualifiers, dates) is done here in code: a model predicts digits instead of
 * computing them, and the Lab 3 router missed an ounces-against-grams conflict
 * until it was told to compute.
 */
import { z } from "zod";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { AIMessage } from "@langchain/core/messages";
import { checkerPrompt } from "./prompts.js";
import type { Figure } from "./reviewer.js";

/** Relative tolerance for figures stated exactly (rounding), and for "about". */
const TOLERANCE_EXACT = 0.01;
const TOLERANCE_ABOUT = 0.05;

export type Verdict = "agree" | "conflict" | "over_time" | "incomparable";

export type PairResult = {
  a: string;
  b: string;
  verdict: Verdict;
  /** |a - b| / max(|a|, |b|) in the base unit; null when the units are incomparable. */
  difference: number | null;
  baseUnit: string;
  aBase: number | null;
  bBase: number | null;
};

export type GroupResult = { quantity: string; figures: string[]; pairs: PairResult[] };

/** One run of the checker, kept in the strategy state. Plain JSON. */
export type CheckRecord = {
  round: number;
  ran: boolean;
  reason: string;
  figures: number;
  groups: GroupResult[];
  inputTokens: number;
  outputTokens: number;
};

const MatchSchema = z.object({
  groups: z
    .array(
      z.object({
        quantity: z.string().describe("The shared quantity, e.g. 'iPhone 18 Pro Max weight'"),
        figures: z.array(z.string()).describe("Ids of the figures that measure exactly this quantity"),
      }),
    )
    .describe("Groups of at least two figures that should agree"),
});
type Match = z.infer<typeof MatchSchema>;

/**
 * The figures worth grouping: those whose kind of unit (mass, time, USD, count, ...)
 * two or more researchers reported, sorted by kind and quantity so that candidates
 * sit next to each other. Exported for unit tests.
 */
export function candidates(figures: Figure[]): (Figure & { kind: string })[] {
  const withKind = figures.flatMap((f) => {
    const u = parseUnit(f.unit);
    return u ? [{ ...f, kind: u.dim }] : [];
  });
  const researchers = new Map<string, Set<string>>();
  for (const f of withKind) researchers.set(f.kind, (researchers.get(f.kind) ?? new Set()).add(f.briefId));
  return withKind
    .filter((f) => researchers.get(f.kind)!.size >= 2)
    .sort((a, b) => a.kind.localeCompare(b.kind) || a.quantity.toLowerCase().localeCompare(b.quantity.toLowerCase()));
}

const NAME_STOPWORDS = new Set(["the", "a", "an", "of", "for", "in", "on", "at", "per", "to", "and", "official", "manufacturer", "stated"]);

/**
 * Groups of candidates whose quantity names are the same after normalisation
 * (case, punctuation, plurals, filler words), within one kind of unit and across
 * at least two researchers. Exported for unit tests.
 */
export function nameGroups(figures: Figure[]): { quantity: string; figures: string[] }[] {
  const key = (f: Figure & { kind: string }) =>
    `${f.kind}|${f.quantity
      .toLowerCase()
      .replace(/[^a-z0-9.]+/g, " ")
      .split(" ")
      .map((w) => w.replace(/^\.+|\.+$/g, ""))
      .filter((w) => w && !NAME_STOPWORDS.has(w))
      .map((w) => (w.length > 3 ? w.replace(/s$/, "") : w))
      .sort()
      .join(" ")}`;
  const groups = new Map<string, (Figure & { kind: string })[]>();
  for (const f of candidates(figures)) groups.set(key(f), [...(groups.get(key(f)) ?? []), f]);
  return [...groups.values()]
    .filter((g) => new Set(g.map((f) => f.briefId)).size >= 2)
    .map((g) => ({ quantity: g[0]!.quantity, figures: g.map((f) => f.id) }));
}

/** The trigger rule: compare only when two or more researchers reported the same kind of figure. */
export function shouldCheck(figures: Figure[]): { run: boolean; reason: string } {
  const researchers = new Set(figures.map((f) => f.briefId)).size;
  if (researchers < 2) return { run: false, reason: `figures from ${researchers} researcher(s); nothing to compare across researchers` };
  const n = candidates(figures).length;
  if (!n) return { run: false, reason: `no kind of figure was reported by two researchers` };
  return { run: true, reason: `${n} of ${figures.length} figures from ${researchers} researchers share a kind of unit` };
}

export async function checkFigures(
  model: BaseChatModel,
  input: { question: string; figures: Figure[]; round: number },
): Promise<CheckRecord> {
  const trigger = shouldCheck(input.figures);
  const record: CheckRecord = { round: input.round, ran: false, reason: trigger.reason, figures: input.figures.length, groups: [], inputTokens: 0, outputTokens: 0 };
  if (!trigger.run) return record;
  try {
    const matcher = checkerPrompt.pipe(model.withStructuredOutput(MatchSchema, { method: "jsonSchema", name: "figure_groups", includeRaw: true }));
    const out = (await matcher.invoke({
      question: input.question,
      figures: candidates(input.figures)
        .map((f) => `${f.id} | ${f.kind} | ${f.quantity} | ${f.value} ${f.unit} | ${f.qualifier} | ${f.asOf || "no date"} | "${f.quote}"`)
        .join("\n"),
    })) as { raw: AIMessage; parsed: Match | null };
    record.inputTokens = out.raw.usage_metadata?.input_tokens ?? 0;
    record.outputTokens = out.raw.usage_metadata?.output_tokens ?? 0;
    if (!out.parsed) throw new Error("the grouping did not match its schema");
    // Same-name matches first: they need no judgement, and the model misses some of them.
    record.groups = compareGroups([...nameGroups(input.figures), ...out.parsed.groups], input.figures);
    record.ran = true;
  } catch (e) {
    record.reason = `checker failed: ${String((e as Error).message ?? e).slice(0, 200)}`;
  }
  return record;
}

/**
 * Validate the model's groups and compare every pair of figures from different
 * researchers. A figure counts in one group at most. Exported for unit tests.
 */
export function compareGroups(groups: Match["groups"], figures: Figure[]): GroupResult[] {
  const byId = new Map(figures.map((f) => [f.id, f]));
  const used = new Set<string>();
  const out: GroupResult[] = [];
  for (const g of groups) {
    const members = [...new Set(g.figures)].filter((id) => byId.has(id) && !used.has(id));
    if (members.length < 2) continue;
    members.forEach((id) => used.add(id));
    // A group whose figures carry different dates is a series over time: a figure in it
    // that is undated, or dated less precisely than the other (2024 against 2024-08),
    // cannot be placed, so it is not compared (T6 grouped user milestones).
    const dated = members.map((id) => byId.get(id)!.asOf).filter(Boolean);
    const series = dated.some((d, i) => dated.slice(i + 1).some((e) => datesDiffer(d, e)));
    const unplaced = (a: Figure, b: Figure) => !a.asOf || !b.asOf || (dateOf(a.asOf).length !== dateOf(b.asOf).length && !datesDiffer(a.asOf, b.asOf));
    const pairs: PairResult[] = [];
    for (let i = 0; i < members.length; i++) {
      for (let j = i + 1; j < members.length; j++) {
        const a = byId.get(members[i]!)!;
        const b = byId.get(members[j]!)!;
        if (a.briefId === b.briefId) continue;
        if (series && unplaced(a, b)) {
          pairs.push({ a: a.id, b: b.id, verdict: "incomparable", difference: null, baseUnit: "", aBase: null, bBase: null });
        } else {
          pairs.push(compareFigures(a, b));
        }
      }
    }
    if (pairs.length) out.push({ quantity: g.quantity.trim(), figures: members, pairs });
  }
  return out;
}

/** Compare two figures of the same quantity. Exported for unit tests. */
export function compareFigures(a: Figure, b: Figure): PairResult {
  const ua = parseUnit(a.unit);
  const ub = parseUnit(b.unit);
  if (!ua || !ub || ua.dim !== ub.dim) {
    return { a: a.id, b: b.id, verdict: "incomparable", difference: null, baseUnit: "", aBase: null, bBase: null };
  }
  const va = a.value * ua.factor;
  const vb = b.value * ub.factor;
  const scale = Math.max(Math.abs(va), Math.abs(vb));
  const difference = scale === 0 ? 0 : Math.abs(va - vb) / scale;
  const tolerance = (a.qualifier === "about" || b.qualifier === "about" ? TOLERANCE_ABOUT : TOLERANCE_EXACT) * scale;
  // Each figure is an interval: exact and about are a point, "at least" is open above, "at most" open below.
  const [loA, hiA] = interval(a.qualifier, va);
  const [loB, hiB] = interval(b.qualifier, vb);
  const consistent = loA <= hiB + tolerance && loB <= hiA + tolerance;
  const verdict: Verdict = consistent ? "agree" : datesDiffer(a.asOf, b.asOf) ? "over_time" : "conflict";
  return { a: a.id, b: b.id, verdict, difference: round(difference), baseUnit: ua.base, aBase: round(va), bBase: round(vb) };
}

function interval(qualifier: Figure["qualifier"], v: number): [number, number] {
  if (qualifier === "at least") return [v, Infinity];
  if (qualifier === "at most") return [-Infinity, v];
  return [v, v];
}

/** Two dates differ when they disagree at the precision both give (YYYY, YYYY-MM or YYYY-MM-DD). */
export function datesDiffer(a: string, b: string): boolean {
  const da = dateOf(a);
  const db = dateOf(b);
  if (!da || !db) return false;
  const n = Math.min(da.length, db.length);
  return da.slice(0, n) !== db.slice(0, n);
}

/** The date as YYYY, YYYY-MM or YYYY-MM-DD; empty when there is none. */
function dateOf(s: string): string {
  return /^\d{4}(-\d{2}){0,2}/.exec(s.trim())?.[0] ?? "";
}

type Unit = { dim: string; factor: number; base: string };

// unit -> [dimension, factor to the base unit, base unit]
const UNITS: Record<string, [string, number, string]> = {
  g: ["mass", 1, "g"], gram: ["mass", 1, "g"], kg: ["mass", 1000, "g"], kilogram: ["mass", 1000, "g"], mg: ["mass", 0.001, "g"],
  oz: ["mass", 28.349523125, "g"], ounce: ["mass", 28.349523125, "g"], lb: ["mass", 453.59237, "g"], lbs: ["mass", 453.59237, "g"], pound: ["mass", 453.59237, "g"],
  mm: ["length", 0.001, "m"], cm: ["length", 0.01, "m"], m: ["length", 1, "m"], meter: ["length", 1, "m"], metre: ["length", 1, "m"], km: ["length", 1000, "m"],
  in: ["length", 0.0254, "m"], inch: ["length", 0.0254, "m"], inche: ["length", 0.0254, "m"], ft: ["length", 0.3048, "m"], foot: ["length", 0.3048, "m"], feet: ["length", 0.3048, "m"],
  mi: ["length", 1609.344, "m"], mile: ["length", 1609.344, "m"],
  s: ["time", 1, "s"], sec: ["time", 1, "s"], second: ["time", 1, "s"], min: ["time", 60, "s"], minute: ["time", 60, "s"],
  h: ["time", 3600, "s"], hr: ["time", 3600, "s"], hour: ["time", 3600, "s"], day: ["time", 86400, "s"], week: ["time", 604800, "s"],
  kb: ["data", 1e3, "B"], mb: ["data", 1e6, "B"], gb: ["data", 1e9, "B"], tb: ["data", 1e12, "B"],
  mah: ["charge", 1, "mAh"], ah: ["charge", 1000, "mAh"], wh: ["energy", 1, "Wh"], kwh: ["energy", 1000, "Wh"],
  w: ["power", 1, "W"], watt: ["power", 1, "W"], kw: ["power", 1000, "W"],
  hz: ["frequency", 1, "Hz"], khz: ["frequency", 1e3, "Hz"], mhz: ["frequency", 1e6, "Hz"], ghz: ["frequency", 1e9, "Hz"],
  px: ["pixels", 1, "px"], pixel: ["pixels", 1, "px"], mp: ["megapixels", 1, "MP"], megapixel: ["megapixels", 1, "MP"],
  nit: ["luminance", 1, "nits"], "°": ["angle", 1, "°"], degree: ["angle", 1, "°"],
  "%": ["percent", 1, "%"], percent: ["percent", 1, "%"], pct: ["percent", 1, "%"],
  usd: ["USD", 1, "USD"], $: ["USD", 1, "USD"], "us$": ["USD", 1, "USD"], dollar: ["USD", 1, "USD"], "us dollar": ["USD", 1, "USD"],
  eur: ["EUR", 1, "EUR"], "€": ["EUR", 1, "EUR"], euro: ["EUR", 1, "EUR"], gbp: ["GBP", 1, "GBP"], "£": ["GBP", 1, "GBP"],
  cad: ["CAD", 1, "CAD"], "c$": ["CAD", 1, "CAD"], cny: ["CNY", 1, "CNY"], rmb: ["CNY", 1, "CNY"], yuan: ["CNY", 1, "CNY"], jpy: ["JPY", 1, "JPY"], yen: ["JPY", 1, "JPY"],
};

const COUNT_WORDS = new Set([
  "", "people", "person", "user", "weekly user", "weekly active user", "monthly active user", "wau", "mau", "customer", "subscriber", "unit", "device", "download", "visit",
]);

const SCALE: Record<string, number> = { thousand: 1e3, million: 1e6, billion: 1e9, trillion: 1e12 };

/** Parse a unit as written; undefined when it is not a known unit or count. Exported for unit tests. */
export function parseUnit(raw: string): Unit | undefined {
  let s = raw.toLowerCase().replace(/\.$/, "").replace(/\s+/g, " ").trim();
  let factor = 1;
  s = s.replace(/\b(thousand|million|billion|trillion)\b/g, (w) => {
    factor *= SCALE[w]!;
    return "";
  });
  s = s.replace(/\s+/g, " ").trim();
  // The whole unit first, then its first word ("hours of video playback").
  const first = s.split(" ")[0]!;
  for (const key of [s, s.replace(/s$/, ""), first, first.replace(/s$/, "")]) {
    const u = UNITS[key];
    if (u) return { dim: u[0], factor: factor * u[1], base: u[2] };
    if (COUNT_WORDS.has(key)) return { dim: "count", factor, base: "" };
  }
  return undefined;
}

function round(n: number): number {
  return Number(n.toPrecision(6));
}

/**
 * Conflicting pairs, for the router's overview, its evidence rules and the writer's
 * guidance. Values that differ between dates are a change, not a conflict, and are
 * only counted.
 */
export function disagreements(check: CheckRecord | undefined): { group: GroupResult; pair: PairResult }[] {
  if (!check) return [];
  return check.groups.flatMap((group) => group.pairs.filter((p) => p.verdict === "conflict").map((pair) => ({ group, pair })));
}
