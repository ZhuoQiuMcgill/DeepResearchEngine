/**
 * Contract checks for a request analysis (design section 5.4): the TypeScript
 * port of labs/lab2/validate.py for rev 2, plus three rules new in rev 2
 * (scan spans covered, grounding entries valid, new names grounded).
 *
 * The same function is the gate of both init modes: the fixed workflow calls it
 * after the model's reply, and the agent's submit_analysis tool calls it on
 * every submission.
 */
import type { z } from "zod";
import { AnalysisApiSchema, AnalysisFullSchema, type Analysis, type Issue, type ScanResult } from "./schema.js";
import { spanWords, words } from "./scan.js";

const GUIDELINES_FOR: Record<string, string[]> = {
  T1: ["G1"],
  T2: ["G1"],
  T3: ["G1"],
  T4: ["G3", "G4", "G5", "G6"],
  T5: ["G3", "G4", "G5", "G6"],
  T6: ["G2"],
  T7: ["G7"],
};
const ROUTE_RANK = { search: 0, synthesis: 1 } as const;
const BACK_REFERENCE = /\bQ\d+\b|\b(?:previous|earlier|first|second|preceding|above) (?:search )?questions?\b|\bthe ones identified\b/i;
const DEPENDENCY_ROUTES = { search: ["search"], synthesis: ["search", "synthesis"] } as const;

export type CheckContext = {
  request: string;
  scan: ScanResult;
  /** Every result the search tool reported in this run; undefined when search was not offered. */
  reported?: { url: string; title?: string }[];
};

export type CheckResult = {
  /** The analysis as parsed by the API schema; null when its structure is invalid. */
  analysis: Analysis | null;
  errors: Issue[];
  warnings: Issue[];
};

/** Lower-case, with typographic quotes and whitespace normalised, so verbatim checks ignore typography. */
export function norm(text: string): string {
  return text.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/\s+/g, " ").trim().toLowerCase();
}

/** Page identity of a URL: host without "www.", path without a trailing slash; no query or fragment. */
export function pageKey(url: string): string {
  try {
    const u = new URL(url.trim());
    return `${u.hostname.replace(/^www\./, "").toLowerCase()}${u.pathname.replace(/\/+$/, "")}`;
  } catch {
    return url.trim().toLowerCase().replace(/[?#].*$/, "").replace(/\/+$/, "");
  }
}

function pathOf(path: readonly PropertyKey[]): string {
  return path.reduce<string>((out, key) => (typeof key === "number" ? `${out}[${key}]` : out ? `${out}.${String(key)}` : String(key)), "");
}

function zodIssues(error: z.ZodError, code: string): Issue[] {
  return error.issues.map((i) => ({ code, path: pathOf(i.path), message: i.message }));
}

// ---------------------------------------------------------------- names

const CALENDAR = new Set(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
  "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]);
// Places may be named; legal suffixes, units and common technical or business abbreviations do not introduce an entity.
const PLACES = new Set(["europe", "asia", "africa", "america", "americas", "oceania", "north", "south", "east", "west", "middle",
  "latin", "central", "united", "states", "kingdom", "us", "usa", "uk", "china", "japan", "korea", "taiwan",
  "india", "canada", "germany", "france", "britain", "american", "asian", "african", "chinese", "japanese",
  "korean", "taiwanese", "indian", "canadian", "german", "french", "british",
  // Lab 3 (2026-10-19) flagged "Philippines" and "Russia": countries and their adjectives are places.
  "european", "russia", "russian", "philippines", "filipino", "philippine", "mexico", "mexican", "brazil", "brazilian",
  "argentina", "argentine", "chile", "chilean", "colombia", "colombian", "peru", "peruvian", "australia", "australian",
  "zealand", "italy", "italian", "spain", "spanish", "portugal", "portuguese", "netherlands", "dutch", "belgium", "belgian",
  "switzerland", "swiss", "austria", "austrian", "ireland", "irish", "england", "english", "scotland", "scottish",
  "wales", "welsh", "sweden", "swedish", "norway", "norwegian", "denmark", "danish", "finland", "finnish", "poland",
  "polish", "ukraine", "ukrainian", "turkey", "turkish", "greece", "greek", "israel", "israeli", "iran", "iranian",
  "iraq", "iraqi", "egypt", "egyptian", "saudi", "arabia", "arabian", "emirates", "uae", "qatar", "singapore",
  "singaporean", "malaysia", "malaysian", "indonesia", "indonesian", "thailand", "thai", "vietnam", "vietnamese",
  "pakistan", "pakistani", "bangladesh", "nigeria", "nigerian", "kenya", "kenyan", "ethiopia", "morocco", "hong", "kong"]);
const GENERIC = new Set(["i", "ai", "url", "pdf", "csv", "api", "corporation", "inc", "ltd", "company", "group", "b2b", "b2c",
  "fp8", "fp16", "fp32", "fp64", "int8", "tdp", "tco", "roi", "kpi", "gdp", "cpi", "ceo", "msrp", "usd",
  "eur", "gbp", "cad", "kb", "mb", "gb", "tb", "flops", "tflops", "pflops", "tops", "fps", "ghz", "mhz",
  "nm", "w", "kw", "kwh", "vram", "ram", "hbm", "cpu", "gpu", "tpu", "npu"]);

/** Words of a capitalised run whose initials spell an acronym the request uses ("European Union" for "EU"). */
function acronymExpansions(text: string, acronyms: Set<string>): Set<string> {
  const ws = text.match(/[A-Za-z][A-Za-z'-]*/g) ?? [];
  const found = new Set<string>();
  for (let i = 0; i < ws.length; i++) {
    for (let j = i + 2; j <= Math.min(i + 6, ws.length); j++) {
      const run = ws.slice(i, j);
      if (run.every((w) => /^[A-Z]/.test(w)) && acronyms.has(run.map((w) => w[0]).join("").toUpperCase())) {
        for (const w of run) found.add(norm(w).replace(/'s?$/, "")); // "Union's" in "the European Union's"
      }
    }
  }
  return found;
}

function commonPrefix(a: string, b: string): number {
  let n = 0;
  while (n < a.length && n < b.length && a[n] === b[n]) n++;
  return n;
}

/** A form of a request word ("Europe" for "European"): long shared prefix, at least 5 letters. */
function sameStem(word: string, requestWords: string[]): boolean {
  return requestWords.some((r) => commonPrefix(word, r) >= Math.max(5, Math.min(word.length, r.length) - 2));
}

/**
 * Capitalised words, not at the start of a sentence, that name something the
 * request does not: a maker, a rival, a law. Not counted: the request's own
 * words in any singular, plural or derived form, expansions of its acronyms,
 * calendar words, places, common abbreviations, IDs, and allowed (grounded) names.
 */
export function newNames(analysis: Analysis, request: string, allow: string[] = []): string[] {
  const requestWords = norm(request).match(/[a-z0-9][a-z0-9'-]*/g) ?? [];
  const known = new Set<string>([
    ...requestWords,
    ...requestWords.map((w) => w.split("'")[0]!),
    ...allow.flatMap((a) => [norm(a), ...norm(a).split(/[\s-]+/)]),
    ...CALENDAR,
    ...PLACES,
    ...GENERIC,
  ]);
  for (const w of [...known]) {
    known.add(w.replace(/s$/, ""));
    known.add(`${w}s`);
  }
  const acronyms = new Set<string>([
    ...(request.match(/\b[A-Z][A-Z0-9]+s?\b/g) ?? []).map((t) => t.replace(/S$/, "")),
    ...(request.match(/\b[A-Z][A-Z0-9]+s\b/g) ?? []).map((t) => t.replace(/s$/, "").toUpperCase()),
  ]);
  const texts = [analysis.restated_request, ...analysis.rom.objects.map((o) => o.meaning)];
  for (const q of analysis.questions) texts.push(q.text, q.done_when, ...q.source_hints);
  const found = new Set<string>();
  for (const text of texts) {
    const expanded = acronymExpansions(text, acronyms);
    for (const sentence of text.split(/(?<=[.?!:;(])\s+/)) {
      const caps = sentence.match(/\b[A-Z][A-Za-z0-9'’-]*/g) ?? [];
      for (const word of /^[A-Z]/.test(sentence) ? caps.slice(1) : caps) {
        const bare = norm(word).replace(/'s$/, "").replace(/'$/, ""); // "GPT-4's", "GPUs'"
        const head = bare.split("-")[0]!;
        if (known.has(bare) || known.has(head) || expanded.has(bare) || sameStem(bare, requestWords)) continue;
        if (/^[OQRACSGT]\d+(-[OQRACSGT]?\d+)?$/.test(word)) continue;
        found.add(word);
      }
    }
  }
  return [...found].sort();
}

// ---------------------------------------------------------------- order helpers

function searchLayers(analysis: Analysis): Map<string, number> {
  const layer = new Map<string, number>();
  for (const q of analysis.questions) {
    if (q.route === "search") layer.set(q.id, 1 + Math.max(0, ...q.depends_on.map((d) => layer.get(d) ?? 0)));
  }
  return layer;
}

function ancestors(id: string, byId: Map<string, Analysis["questions"][number]>): Set<string> {
  const seen = new Set<string>();
  const stack = [...(byId.get(id)?.depends_on ?? [])];
  while (stack.length) {
    const d = stack.pop()!;
    if (byId.has(d) && !seen.has(d)) {
      seen.add(d);
      stack.push(...byId.get(d)!.depends_on);
    }
  }
  return seen;
}

/** Every quoted text of an analysis: where a scan span counts as kept. */
export function quoteCorpus(a: Analysis): Set<string> {
  const texts = [
    ...a.rom.objects.map((o) => o.text),
    ...a.rom.relations.map((r) => r.via ?? ""),
    ...a.client_directives.flatMap((d) => d.evidence),
    ...a.flags.flatMap((f) => f.evidence),
    ...a.assumptions.flatMap((x) => x.evidence),
    ...[a.frame.purpose, a.frame.time_frame, a.frame.place].flatMap((f) => f.evidence),
  ];
  return new Set(texts.flatMap(words));
}

// ---------------------------------------------------------------- checks

export function checkAnalysis(input: unknown, ctx: CheckContext): CheckResult {
  const structural = AnalysisApiSchema.safeParse(input);
  if (!structural.success) return { analysis: null, errors: zodIssues(structural.error, "schema"), warnings: [] };
  const a = structural.data;
  const errors: Issue[] = [];
  const warnings: Issue[] = [];
  const err = (code: string, path: string, message: string) => errors.push({ code, path, message });
  const warn = (code: string, path: string, message: string) => warnings.push({ code, path, message });

  const full = AnalysisFullSchema.safeParse(input);
  if (!full.success) errors.push(...zodIssues(full.error, "limit"));

  const req = norm(ctx.request);
  const objects = new Map(a.rom.objects.map((o) => [o.id, o]));
  const relations = new Map(a.rom.relations.map((r) => [r.id, r]));
  const assumptions = new Map(a.assumptions.map((x) => [x.id, x]));
  const byId = new Map(a.questions.map((q) => [q.id, q]));

  // Unique IDs.
  for (const [kind, items] of [["objects", a.rom.objects], ["relations", a.rom.relations], ["assumptions", a.assumptions], ["questions", a.questions]] as const) {
    const ids = items.map((i) => i.id);
    const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
    if (dup.length) err("duplicate_id", kind, `duplicate ids: ${[...new Set(dup)].join(", ")}`);
  }

  // References resolve.
  a.rom.relations.forEach((r, i) => {
    for (const end of [r.from, r.to]) if (!objects.has(end)) err("unknown_reference", `rom.relations[${i}]`, `${r.id}: unknown object ${end}`);
  });
  for (const id of a.rom.central_object_ids) if (!objects.has(id)) err("unknown_reference", "rom.central_object_ids", `unknown object ${id}`);
  a.assumptions.forEach((x, i) => {
    for (const rid of x.relation_ids) if (!relations.has(rid)) err("unknown_reference", `assumptions[${i}]`, `${x.id}: unknown relation ${rid}`);
  });
  a.questions.forEach((q, i) => {
    for (const oid of q.object_ids) if (!objects.has(oid)) err("unknown_reference", `questions[${i}]`, `${q.id}: unknown object ${oid}`);
    for (const aid of q.verifies) if (!assumptions.has(aid)) err("unknown_reference", `questions[${i}]`, `${q.id}: unknown assumption ${aid}`);
  });

  // Quotes are copied from the request.
  const quotes: [string, string][] = a.rom.objects.map((o, i) => [`rom.objects[${i}].text`, o.text]);
  for (const name of ["purpose", "time_frame", "place"] as const) a.frame[name].evidence.forEach((e, i) => quotes.push([`frame.${name}.evidence[${i}]`, e]));
  for (const group of ["flags", "client_directives", "assumptions"] as const) {
    a[group].forEach((item, i) => item.evidence.forEach((e, j) => quotes.push([`${group}[${i}].evidence[${j}]`, e])));
  }
  for (const [path, quote] of quotes) {
    if (!req.includes(norm(quote))) err("quote_not_in_request", path, `quote not found in the request: ${JSON.stringify(quote)}`);
  }

  // Frame basis.
  for (const name of ["purpose", "time_frame", "place"] as const) {
    const f = a.frame[name];
    if ((f.basis === "explicit" || f.basis === "implied") && !f.evidence.length) err("frame_basis", `frame.${name}`, `an ${f.basis} value needs a quote`);
    if (f.basis === "default" && (f.value === null || f.evidence.length)) err("frame_basis", `frame.${name}`, "a default needs a value and no quote");
    if (f.basis === "unknown" && f.value !== null) err("frame_basis", `frame.${name}`, "an unknown value must be null");
  }

  // Ambiguity.
  a.rom.objects.forEach((o, i) => {
    if (o.readings.length === 1) err("readings", `rom.objects[${i}]`, `${o.id}: an ambiguous term needs at least two readings`);
    if (o.readings.length && o.status !== "needs_question") err("readings", `rom.objects[${i}]`, `${o.id}: an ambiguous term needs a question`);
  });

  // Questions stand alone (Lab 3, 2026-10-19: 24 questions in 15 of 81 analyses said "identified in Q1"):
  // a researcher sees only its own question, and the writer sees synthesis questions as the outline.
  a.questions.forEach((q, i) => {
    const text = q.route === "search" ? `${q.text} ${q.done_when}` : q.text;
    const ref = BACK_REFERENCE.exec(text);
    if (ref) err("question_not_self_contained", `questions[${i}]`, `${q.id} refers to another question (${JSON.stringify(ref[0])}); restate the subject in full: names, place and time`);
  });

  // Questions: templates, routes, dependencies.
  const seen = new Set<string>();
  a.questions.forEach((q, i) => {
    const path = `questions[${i}]`;
    if (!GUIDELINES_FOR[q.template]!.includes(q.guideline)) err("template_guideline", path, `${q.id}: template ${q.template} cannot use guideline ${q.guideline}`);
    for (const d of q.depends_on) {
      const dep = byId.get(d);
      if (!seen.has(d) || !dep) err("dependency", path, `${q.id}: depends on ${d}, which is not an earlier question`);
      else if (!(DEPENDENCY_ROUTES[q.route] as readonly string[]).includes(dep.route)) err("dependency", path, `${q.id}: a ${q.route} question cannot depend on the ${dep.route} question ${d}`);
      else if (q.route === "search" && q.need === "necessary" && dep.need !== "necessary") err("dependency", path, `${q.id}: a necessary search question depends on the completing question ${d}`);
    }
    seen.add(q.id);
    if (q.route === "search" && q.object_ids.some((o) => objects.get(o)?.role === "product")) err("product_searched", path, `${q.id}: a product object is left to synthesis (G6b), not searched`);
    if (q.route === "synthesis" && !q.depends_on.length) err("synthesis_without_inputs", path, `${q.id}: a synthesis question must depend on search questions`);
    if (q.verifies.length && q.route !== "search") err("verifies_route", path, `${q.id}: only search questions verify assumptions`);
    if (q.route === "synthesis" && q.source_hints.length) err("source_hints", path, `${q.id}: synthesis questions have no source hints`);
  });
  const ranks = a.questions.map((q) => ROUTE_RANK[q.route]);
  if (ranks.some((r, i) => i > 0 && r < ranks[i - 1]!)) err("question_order", "questions", "questions are not ordered search, then synthesis");
  const layer = searchLayers(a);
  const sequence = a.questions.filter((q) => q.route === "search").map((q) => layer.get(q.id) ?? 0);
  if (sequence.some((s, i) => i > 0 && s < sequence[i - 1]!)) warn("layer_order", "questions", "search questions are not listed layer by layer");

  // Status consistency.
  const search = a.questions.filter((q) => q.route === "search");
  const synthesis = a.questions.filter((q) => q.route === "synthesis");
  if (a.status === "ok") {
    if (!search.length || !synthesis.length) err("status", "questions", "status ok needs at least one search and one synthesis question");
    if (a.status_reason !== null) err("status", "status_reason", "status ok has status_reason null");
    if (!a.rom.central_object_ids.length) err("status", "rom.central_object_ids", "status ok needs central objects");
    const covered = new Set(a.questions.flatMap((q) => q.object_ids));
    a.rom.objects.forEach((o, i) => {
      if (o.status === "needs_question" && !covered.has(o.id)) err("object_uncovered", `rom.objects[${i}]`, `${o.id} (${JSON.stringify(o.text)}) needs a question but no question covers it`);
    });
    // A verification question checks a claim; it does not define the objects in it (review of 2026-10-20).
    const checked = new Set(a.questions.filter((q) => q.template === "T7").flatMap((q) => q.object_ids));
    const defined = new Set(search.filter((q) => q.template !== "T7").flatMap((q) => q.object_ids));
    a.rom.objects.forEach((o, i) => {
      if (o.status === "needs_question" && o.role === "environment" && checked.has(o.id) && !defined.has(o.id)) {
        err("object_only_verified", `rom.objects[${i}]`, `${o.id} (${JSON.stringify(o.text)}) is covered only by a verification question (T7); add it to a search question with a template from T1 to T6 that defines it (that question may also verify the claim)`);
      }
    });
    const verified = new Set(search.flatMap((q) => q.verifies));
    a.assumptions.forEach((x, i) => {
      if (!verified.has(x.id)) err("assumption_unverified", `assumptions[${i}]`, `${x.id}: no search question verifies it`);
    });
  } else {
    if (a.questions.length || a.assumptions.length) err("status", "questions", "status out_of_scope has no questions and no assumptions");
    if (!a.status_reason) err("status", "status_reason", "status out_of_scope needs a status_reason");
  }

  // Grounding entries (rev 2): only with search, and only on results the search tool reported.
  const allowed: string[] = [];
  if (a.grounding.length && !ctx.reported) err("grounding_without_search", "grounding", "no search was available in this run, so grounding must be empty");
  if (ctx.reported) {
    const byPage = new Map(ctx.reported.map((r) => [pageKey(r.url), r]));
    a.grounding.forEach((g, i) => {
      const path = `grounding[${i}]`;
      if (!objects.has(g.object_id)) err("unknown_reference", path, `unknown object ${g.object_id}`);
      const result = byPage.get(pageKey(g.url));
      if (!result) {
        err("grounding_url_not_reported", path, `the search tool did not report ${g.url} in this run`);
        return;
      }
      allowed.push(...g.names);
      const page = new Set(words(`${result.title ?? ""} ${result.url}`));
      for (const name of g.names) {
        if (!words(name).some((w) => page.has(w))) warn("grounding_name_unseen", path, `${JSON.stringify(name)} does not appear in the result's title or URL`);
      }
    });
  }

  // Names the request does not contain carry topic knowledge; grounded names are allowed.
  const names = newNames(a, ctx.request, allowed);
  if (names.length) {
    err("names_not_in_request", "names", `names that the request does not mention (name an organisation, product, law or person only if the request names it or a grounding entry lists it; otherwise use a generic category): ${names.join(", ")}`);
  }

  // Verify before explaining: a why-question about a presupposed relation waits for its check.
  a.questions.forEach((q, i) => {
    if (q.guideline !== "G5") return;
    const before = ancestors(q.id, byId);
    for (const x of a.assumptions) {
      const ends = new Set(x.relation_ids.flatMap((rid) => (relations.has(rid) ? [relations.get(rid)!.from, relations.get(rid)!.to] : [])));
      const verifiers = a.questions.filter((v) => v.verifies.includes(x.id)).map((v) => v.id);
      if (q.object_ids.some((o) => ends.has(o)) && verifiers.length && !verifiers.some((v) => before.has(v))) {
        warn("explains_before_verifying", `questions[${i}]`, `${q.id} explains ${x.id} before a question verifies it`);
      }
    }
  });

  // Never-drop spans (rev 2): every span of the scan appears in some quote.
  if (a.status === "ok") {
    const corpus = quoteCorpus(a);
    for (const span of ctx.scan.spans) {
      const missing = spanWords(span).filter((w) => !corpus.has(w));
      if (missing.length) {
        err("span_not_covered", `scan.${span.id}`, `span ${span.id} ${JSON.stringify(span.text)} (${span.kind}) is not kept: quote ${missing.map((w) => JSON.stringify(w)).join(", ")} in an object, a relation's via, or the evidence of a directive, flag, frame value or assumption`);
      }
    }
  }

  return { analysis: a, errors, warnings };
}

export function counts(a: Analysis) {
  return {
    objects: a.rom.objects.length,
    assumptions: a.assumptions.length,
    search: a.questions.filter((q) => q.route === "search").length,
    synthesis: a.questions.filter((q) => q.route === "synthesis").length,
    grounding: a.grounding.length,
  };
}

/**
 * Fallback after the last failed attempt (design section 5.3 step 5): drop the
 * questions, assumptions and grounding entries an error points to, and every
 * question that depends on a dropped one. Usable only if a search question survives.
 */
export function salvage(a: Analysis, errors: Issue[]): Analysis | null {
  if (a.status !== "ok") return errors.length ? null : a;
  const index = (prefix: string) => {
    const re = new RegExp(`^${prefix}\\[(\\d+)\\]`);
    return new Set(errors.flatMap((e) => {
      const m = re.exec(e.path);
      return m ? [Number(m[1])] : [];
    }));
  };
  const badQ = index("questions");
  const badA = index("assumptions");
  const badG = index("grounding");
  const dropped = new Set(a.questions.filter((_, i) => badQ.has(i)).map((q) => q.id));
  for (let changed = true; changed; ) {
    changed = false;
    for (const q of a.questions) {
      if (!dropped.has(q.id) && q.depends_on.some((d) => dropped.has(d))) {
        dropped.add(q.id);
        changed = true;
      }
    }
  }
  const droppedA = new Set(a.assumptions.filter((_, i) => badA.has(i)).map((x) => x.id));
  const questions = a.questions.filter((q) => !dropped.has(q.id)).map((q) => ({ ...q, verifies: q.verifies.filter((v) => !droppedA.has(v)) }));
  if (!questions.some((q) => q.route === "search")) return null;
  return {
    ...a,
    questions,
    assumptions: a.assumptions.filter((x) => !droppedA.has(x.id)),
    grounding: a.grounding.filter((_, i) => !badG.has(i)),
  };
}
