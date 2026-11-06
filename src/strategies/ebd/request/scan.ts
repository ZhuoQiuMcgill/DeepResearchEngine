/**
 * Never-drop scan of a request (design section 5.5): the spans an analysis
 * must keep, found with a small lexicon and patterns, with relative time
 * resolved against the run date. Deterministic and dependency-free: the same
 * request and date always give the same spans and IDs.
 *
 * The scan is a floor, not a parser. Lower-case product names, for example,
 * are not detected as names; their numbers are.
 */
import type { ScanResult, Span, SpanKind } from "./schema.js";

/** Default windows for vague recent time (decision L-4, provisional). */
export const RECENT_DEFAULTS = { days: { days: 30 }, weeks: { days: 56 }, months: { months: 6 }, years: { years: 3 } } as const;

export const SCAN_RULE =
  "Every span must appear in the analysis: quote its words in an object's text or a relation's via, or in the evidence of a directive, flag, frame value or assumption. submit_analysis rejects an ok analysis that drops a span. Windows are resolved from the run date; use them for the time frame.";

type Window = { from: string | null; to: string | null };
type Candidate = { kind: SpanKind; start: number; end: number; window: Window | null };
type Rule = { kind: SpanKind; re: RegExp; window?: (m: RegExpExecArray, d: Date) => Window | null; accept?: (m: RegExpExecArray, text: string) => [number, number] | null };

const NUMBER_WORDS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12,
};
const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
const ACRONYM_STOPWORDS = new Set(["of", "and", "for", "the", "in", "on", "to", "a", "an", "&"]);
const NAME_STOPWORDS = new Set(["i", "i'm", "i'd", "i've", "i'll", "a", "ok"]);
const CAPS_JOINERS = new Set(["TO", "THE", "OF", "AND", "FOR", "IN", "ON", "A", "AN", "OR"]);

// ---------------------------------------------------------------- dates

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function day(y: number, m: number, d: number): Date {
  return new Date(Date.UTC(y, m, d));
}
function shift(d: Date, by: { days?: number; months?: number; years?: number }, sign: 1 | -1): Date {
  const out = new Date(d.getTime());
  if (by.years) out.setUTCFullYear(out.getUTCFullYear() + sign * by.years);
  if (by.months) out.setUTCMonth(out.getUTCMonth() + sign * by.months);
  if (by.days) out.setUTCDate(out.getUTCDate() + sign * by.days);
  return out;
}
function yearWindow(y: number): Window {
  return { from: `${y}-01-01`, to: `${y}-12-31` };
}
function count(word: string): number {
  return NUMBER_WORDS[word.toLowerCase()] ?? Number(word);
}
function unitShift(n: number, unit: string): { days?: number; months?: number; years?: number } {
  const u = unit.toLowerCase().replace(/s$/, "");
  if (u === "day") return { days: n };
  if (u === "week") return { days: 7 * n };
  if (u === "month") return { months: n };
  return { years: n };
}

// ---------------------------------------------------------------- rules

const YEAR = "((?:19|20)\\d{2})";
const COUNT = "(\\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)";

/** Ordered by precedence: on identical ranges the earlier rule wins. */
const RULES: Rule[] = [
  { kind: "url", re: /\bhttps?:\/\/[^\s<>()"']*[^\s<>()"'.,;:!?]/gi },
  { kind: "url", re: /\b(?:[a-z0-9-]+\.)+(?:com|org|net|edu|gov|io|ai|app|dev|info|co|ca|uk|de|fr|cn|jp|example)\b(?:\/[^\s]*[^\s.,;:!?])?/gi },
  { kind: "quoted", re: /"[^"\n]{1,200}"|“[^”\n]{1,200}”/g },
  { kind: "acronym_pair", re: /\b([A-Z][A-Za-z0-9&]{1,9})\s*\(([^()]{3,100})\)/g, accept: (m) => (initialsMatch(m[1]!, m[2]!) ? [m.index, m.index + m[0].length] : null) },
  {
    kind: "acronym_pair",
    re: /\b((?:[A-Za-z][\w'-]*\s+){0,7}[A-Za-z][\w'-]*)\s*\(([A-Z][A-Za-z0-9&]{1,9})\)/g,
    accept: (m) => {
      const words = m[1]!.split(/\s+/);
      for (let k = 1; k <= words.length; k++) {
        const tail = words.slice(words.length - k).join(" ");
        if (initialsMatch(m[2]!, tail)) {
          const start = m.index + m[1]!.length - tail.length;
          return [start, m.index + m[0].length];
        }
      }
      return null;
    },
  },
  { kind: "relative_time", re: new RegExp(`\\bsince\\s+${YEAR}\\b`, "gi"), window: (m, d) => ({ from: `${m[1]}-01-01`, to: iso(d) }) },
  { kind: "relative_time", re: new RegExp(`\\b${YEAR}\\s+or\\s+later\\b`, "gi"), window: (m, d) => ({ from: `${m[1]}-01-01`, to: iso(d) }) },
  { kind: "relative_time", re: new RegExp(`\\bfrom\\s+${YEAR}\\s+on(?:wards?)?\\b`, "gi"), window: (m, d) => ({ from: `${m[1]}-01-01`, to: iso(d) }) },
  { kind: "relative_time", re: new RegExp(`\\bafter\\s+${YEAR}\\b`, "gi"), window: (m, d) => ({ from: `${Number(m[1]) + 1}-01-01`, to: iso(d) }) },
  { kind: "relative_time", re: new RegExp(`\\bbefore\\s+${YEAR}\\b`, "gi"), window: (m) => ({ from: null, to: `${Number(m[1]) - 1}-12-31` }) },
  {
    kind: "relative_time",
    re: new RegExp(`\\b(?:(?:the\\s+)?(?:last|past|previous))\\s+${COUNT}\\s+(days?|weeks?|months?|years?)\\b`, "gi"),
    window: (m, d) => ({ from: iso(shift(d, unitShift(count(m[1]!), m[2]!), -1)), to: iso(d) }),
  },
  {
    kind: "relative_time",
    re: /\b(?:last|previous)\s+(year|month|week)\b/gi,
    window: (m, d) => {
      const u = m[1]!.toLowerCase();
      if (u === "year") return yearWindow(d.getUTCFullYear() - 1);
      if (u === "month") return { from: iso(day(d.getUTCFullYear(), d.getUTCMonth() - 1, 1)), to: iso(day(d.getUTCFullYear(), d.getUTCMonth(), 0)) };
      return { from: iso(shift(d, { days: 7 }, -1)), to: iso(d) };
    },
  },
  {
    kind: "relative_time",
    re: /\bthis\s+(year|month|week)\b/gi,
    window: (m, d) => {
      const u = m[1]!.toLowerCase();
      if (u === "year") return { from: `${d.getUTCFullYear()}-01-01`, to: iso(d) };
      if (u === "month") return { from: iso(day(d.getUTCFullYear(), d.getUTCMonth(), 1)), to: iso(d) };
      return { from: iso(shift(d, { days: 6 }, -1)), to: iso(d) };
    },
  },
  {
    kind: "relative_time",
    re: /\bnext\s+(year|month|week)\b/gi,
    window: (m, d) => {
      const u = m[1]!.toLowerCase();
      if (u === "year") return yearWindow(d.getUTCFullYear() + 1);
      if (u === "month") return { from: iso(day(d.getUTCFullYear(), d.getUTCMonth() + 1, 1)), to: iso(day(d.getUTCFullYear(), d.getUTCMonth() + 2, 0)) };
      return { from: iso(shift(d, { days: 1 }, 1)), to: iso(shift(d, { days: 7 }, 1)) };
    },
  },
  {
    kind: "relative_time",
    re: /\b(?:in\s+)?(?:recent|the\s+(?:last|past)\s+few)\s+(days|weeks|months|years)\b/gi,
    window: (m, d) => ({ from: iso(shift(d, RECENT_DEFAULTS[m[1]!.toLowerCase() as keyof typeof RECENT_DEFAULTS], -1)), to: iso(d) }),
  },
  { kind: "relative_time", re: /\b(?:recently|these\s+days|nowadays|lately)\b/gi, window: (_m, d) => ({ from: iso(shift(d, RECENT_DEFAULTS.days, -1)), to: iso(d) }) },
  { kind: "relative_time", re: /\b(?:latest|current|currently|now|today|to\s+date|up[\s-]to[\s-]date)\b/gi, window: (_m, d) => ({ from: null, to: iso(d) }) },
  { kind: "date", re: /\b(?:19|20)\d{2}-\d{2}-\d{2}\b/g, window: (m) => ({ from: m[0], to: m[0] }) },
  {
    kind: "date",
    re: new RegExp(`\\bQ([1-4])\\s?${YEAR}\\b`, "g"),
    window: (m) => {
      const y = Number(m[2]);
      const q = Number(m[1]) - 1;
      return { from: iso(day(y, 3 * q, 1)), to: iso(day(y, 3 * q + 3, 0)) };
    },
  },
  {
    kind: "date",
    re: new RegExp(`\\b(January|February|March|April|May|June|July|August|September|October|November|December)(?:\\s+${YEAR})?\\b`, "g"),
    window: (m) => {
      if (!m[2]) return null;
      const y = Number(m[2]);
      const mo = MONTHS.indexOf(m[1]!.toLowerCase());
      return { from: iso(day(y, mo, 1)), to: iso(day(y, mo + 1, 0)) };
    },
  },
  { kind: "date", re: /\b(?:19|20)\d{2}\b/g, window: (m) => yearWindow(Number(m[0])) },
  { kind: "restrictor", re: /\b(?:only|solely|exclusively|at\s+least|at\s+most|no\s+more\s+than|no\s+less\s+than|more\s+than|less\s+than|fewer\s+than|exactly|up\s+to)\b/gi },
  {
    kind: "comparison",
    re: /\b(?:compare[sd]?|comparing|comparison|versus|vs\.?|better|best|worse|worst|cheaper|cheapest|faster|fastest|slower|slowest|higher|highest|lower|lowest|larger|largest|smaller|smallest|greater|greatest|newer|newest|older|oldest|stronger|strongest|weaker|weakest|(?:more|less|most|least)\s+[a-z][a-z-]*)\b/gi,
  },
  { kind: "negation", re: /\b(?:not|no|never|without|except|neither|nor|none|nothing|cannot|[a-z]+n['’]t)\b/gi },
  { kind: "quantifier", re: /\b(?:all|every|each|any|most|some|few|many|several|both|either|majority|minority)\b/gi },
  { kind: "modality", re: /\b(?:can|could|may|might|must|should|shall|would|will|need\s+to|have\s+to|has\s+to|ought\s+to)\b/g },
  { kind: "number", re: /\b\d+(?:[.,]\d+)*(?:\s?%)?/g },
  { kind: "number", re: /\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|hundred|thousand|million|billion|dozen|double|twice|triple|half)(?:-[a-z]+)?\b/gi },
  { kind: "question_word", re: /\b(?:how\s+(?:much|many|long|often|far)|what|which|who|whom|whose|when|where|why|how|whether)\b/gi },
];

function initialsMatch(acronym: string, expansion: string): boolean {
  const letters = acronym.replace(/[^A-Za-z]/g, "").toUpperCase();
  const words = expansion.split(/[\s-]+/).filter(Boolean);
  if (letters.length < 2 || words.length < 2) return false;
  const all = words.map((w) => w[0]!.toUpperCase()).join("");
  const content = words.filter((w) => !ACRONYM_STOPWORDS.has(w.toLowerCase())).map((w) => w[0]!.toUpperCase()).join("");
  return all === letters || content === letters;
}

// ---------------------------------------------------------------- names

function sentenceStart(text: string, index: number): boolean {
  const before = text.slice(0, index);
  return before.trim() === "" || /(?:[.?!:]\s+|\n\s*|-{3,}\s*)$/.test(before);
}

/** Capitalised words that are not plain sentence openers, merged into runs ("Apple Vision Pro"). */
function nameCandidates(text: string): Candidate[] {
  const tokens: { start: number; end: number; word: string }[] = [];
  const re = /\b[A-Za-z][A-Za-z0-9]*(?:['’-][A-Za-z0-9]+)*/g;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    let word = m[0];
    if (/['’]s$/i.test(word)) word = word.slice(0, -2);
    if (!/[A-Z]/.test(word) || NAME_STOPWORDS.has(word.toLowerCase())) continue;
    const allCaps = word.length >= 2 && word === word.toUpperCase() && /[A-Z]/.test(word);
    const inner = /[A-Za-z][A-Z0-9]/.test(word) || /[0-9]/.test(word);
    if (!allCaps && !inner && sentenceStart(text, m.index)) continue;
    if (allCaps && CAPS_JOINERS.has(word) && !tokens.length) continue;
    tokens.push({ start: m.index, end: m.index + word.length, word });
  }
  const runs: Candidate[] = [];
  for (const t of tokens) {
    const last = runs[runs.length - 1];
    if (last && /^[ -]$/.test(text.slice(last.end, t.start))) last.end = t.end;
    else runs.push({ kind: "name", start: t.start, end: t.end, window: null });
  }
  // A run cannot end on a joining word ("NOTE TO" + "THE"): trim trailing joiners.
  return runs
    .map((r) => {
      const words = text.slice(r.start, r.end).split(/([ -])/);
      while (words.length > 1 && CAPS_JOINERS.has(words[words.length - 1]!)) words.splice(-2, 2);
      return { ...r, end: r.start + words.join("").length };
    })
    .filter((r) => !CAPS_JOINERS.has(text.slice(r.start, r.end)));
}

// ---------------------------------------------------------------- scan

export function scanRequest(text: string, runDate: string): ScanResult {
  const d = new Date(`${runDate}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) throw new Error(`Invalid run date "${runDate}"`);
  const candidates: (Candidate & { rank: number })[] = [];
  RULES.forEach((rule, rank) => {
    const re = new RegExp(rule.re.source, rule.re.flags.includes("g") ? rule.re.flags : `${rule.re.flags}g`);
    for (let m = re.exec(text); m; m = re.exec(text)) {
      if (m[0].length === 0) {
        re.lastIndex += 1;
        continue;
      }
      const range: [number, number] | null = rule.accept ? rule.accept(m, text) : [m.index, m.index + m[0].length];
      if (!range) continue;
      candidates.push({ kind: rule.kind, start: range[0], end: range[1], window: rule.window ? rule.window(m, d) : null, rank });
    }
  });
  for (const c of nameCandidates(text)) candidates.push({ ...c, rank: RULES.length });

  // Longer spans first; on identical ranges the earlier rule wins. Drop spans inside a kept span.
  candidates.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start) || a.rank - b.rank);
  const kept: Candidate[] = [];
  for (const c of candidates) {
    if (kept.some((k) => k.start <= c.start && c.end <= k.end)) continue;
    kept.push(c);
  }
  kept.sort((a, b) => a.start - b.start || a.end - b.end);
  const spans: Span[] = kept.map((c, i) => ({ id: `S${i + 1}`, kind: c.kind, text: text.slice(c.start, c.end), start: c.start, end: c.end, window: c.window }));
  return { run_date: runDate, spans, rule: SCAN_RULE };
}

// ---------------------------------------------------------------- coverage

const COVERAGE_STOPWORDS = new Set(["a", "an", "the", "of", "and", "or", "in", "on", "at", "to", "for", "by", "with", "from", "as", "is", "are", "be", "s"]);

/** Lower-case word tokens, with typographic quotes and possessives normalised. */
export function words(text: string): string[] {
  return (text.toLowerCase().replace(/[‘’]/g, "'").replace(/'s\b/g, "").match(/[a-z0-9]+(?:[.'-][a-z0-9]+)*/g) ?? []).map((w) => w.replace(/\.$/, ""));
}

/** The words of a span that some quote in the analysis must contain. */
export function spanWords(span: Pick<Span, "text">): string[] {
  return [...new Set(words(span.text).filter((w) => !COVERAGE_STOPWORDS.has(w)))];
}
