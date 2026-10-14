/**
 * Diagnostics on how report citations relate to the notes. Neither check
 * rejects a report; both feed the run summary for comparison across runs.
 */
import type { ResearchResult } from "./contracts.js";
import { extractUrls, pageKey, urlKey } from "./urls.js";

/** Report URLs that appear in no researcher's sources or notes. */
export function unknownCitations(report: string, results: ResearchResult[]): string[] {
  const known = new Set<string>();
  for (const r of results) {
    for (const s of r.sources) known.add(pageKey(s.url));
    for (const u of extractUrls(r.notes)) known.add(pageKey(u));
  }
  return extractUrls(report).filter((u) => !known.has(pageKey(u)));
}

const NUMBER = /\d[\d,]*(?:\.\d+)?/g;
const normalize = (n: string) => n.replace(/,/g, "").replace(/\.0+$/, "");

/** Split Markdown into sentence-like units: table rows, list items, sentences. */
function units(text: string): string[] {
  return text
    .split(/\r?\n/)
    .flatMap((line) => (line.trim().startsWith("|") ? [line] : line.split(/(?<=[.!?])\s+(?=[A-Z(*])/)))
    .filter((u) => u.trim());
}

function numbersIn(unit: string): string[] {
  const withoutUrls = unit.replace(/https?:\/\/[^\s)]+/g, " ").replace(/\[[^\]]*\]/g, " ");
  return [...new Set([...withoutUrls.matchAll(NUMBER)].map((m) => normalize(m[0]!)))].filter((n) => !/^\d$/.test(n));
}

export interface BindingCheck {
  /** Report units that carry at least one citation and at least one number. */
  checked: number;
  /** Units with a number that no notes line citing the same URL contains. */
  unbound: number;
  examples: { text: string; missing: string[] }[];
}

/**
 * For each cited report sentence with numbers, check that every number appears
 * in some notes line that cites one of the same URLs. A heuristic for
 * misattributed citations, not a proof of correctness.
 */
export function citationBinding(report: string, results: ResearchResult[]): BindingCheck {
  const linesByUrl = new Map<string, string[]>();
  for (const r of results) {
    // Notes are compared by whole line: a bullet's numbers belong to the URL at its end.
    for (const line of r.notes.split(/\r?\n/)) {
      for (const u of extractUrls(line)) {
        const key = urlKey(u);
        linesByUrl.set(key, [...(linesByUrl.get(key) ?? []), line]);
      }
    }
  }
  const out: BindingCheck = { checked: 0, unbound: 0, examples: [] };
  for (const unit of units(report)) {
    const urls = extractUrls(unit);
    const nums = numbersIn(unit);
    if (!urls.length || !nums.length) continue;
    out.checked += 1;
    const noteNumbers = new Set(urls.flatMap((u) => linesByUrl.get(urlKey(u)) ?? []).flatMap(numbersIn));
    const missing = nums.filter((n) => !noteNumbers.has(n));
    if (missing.length) {
      out.unbound += 1;
      if (out.examples.length < 8) out.examples.push({ text: unit.trim().slice(0, 240), missing });
    }
  }
  return out;
}

const MD_LINK = /\[([^\]]*)\]\((https?:\/\/[^\s]+?)\)(?=$|[\s.,;:)\]])/g;

/**
 * Mark Markdown links whose page the provider's tools never reported, so the
 * writer can weigh them. Applied by the skeleton to every strategy's material.
 */
export function markUnverifiedLinks(text: string, unverified: Set<string>): { text: string; marked: number } {
  let marked = 0;
  const out = text.replace(MD_LINK, (whole, _label: string, url: string) => {
    if (!unverified.has(pageKey(url))) return whole;
    marked += 1;
    return `${whole} (unverified link)`;
  });
  return { text: out, marked };
}

/**
 * Repair report URLs the writer cut short: an unknown URL that is a prefix of
 * exactly one URL in the notes or sources is replaced by that URL. Unknown URLs
 * without a unique completion are left as they are and stay in the diagnostics.
 */
export function repairTruncatedUrls(report: string, results: ResearchResult[]): { report: string; repairs: { from: string; to: string }[] } {
  const known = new Set<string>();
  for (const r of results) {
    for (const s of r.sources) known.add(s.url);
    for (const u of extractUrls(r.notes)) known.add(u);
  }
  const knownPages = new Set([...known].map(pageKey));
  const repairs: { from: string; to: string }[] = [];
  let out = report;
  for (const url of extractUrls(report)) {
    if (knownPages.has(pageKey(url))) continue;
    const stem = url.replace(/['"]+$/, "").replace(/\/+$/, "");
    const matches = [...known].filter((k) => k.startsWith(stem) && k !== stem);
    if (matches.length !== 1) continue;
    const to = matches[0]!;
    const from = report.includes(`${url}'`) ? `${url}'` : url;
    // Replace only where the URL ends, never inside a longer URL that shares the prefix.
    const escaped = from.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    out = out.replace(new RegExp(`${escaped}(?![A-Za-z0-9/_\\-.~%?#=&+])`, "g"), to);
    repairs.push({ from, to });
  }
  return { report: out, repairs };
}
