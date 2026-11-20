/** Deterministic defense in depth. These checks do not establish factual correctness. */
export interface GuardrailFinding {
  rule: string;
  phase: "input" | "research-notes" | "synthesis" | "report";
  action: "block" | "quarantine" | "annotate";
  brief?: string;
  count: number;
  /** Fixed descriptions only: never copy untrusted content into this field. */
  message: string;
}

export interface BoundedRunInput {
  question: string;
  researchersTotal: number;
  maxRounds: number;
  concurrency: number;
  researcherTimeoutMs: number;
}

/** Validate without trimming, normalizing, or rewriting the question or grants. */
export function inputFindings(input: BoundedRunInput): GuardrailFinding[] {
  const findings: GuardrailFinding[] = [];
  const reject = (rule: string) => findings.push({ rule, phase: "input", action: "block", count: 1, message: "Run input is outside the supported bounds." });
  if (typeof input.question !== "string" || !input.question.trim() || input.question.length > 20_000) reject("question-bounds");
  for (const [name, min, max] of [["researchersTotal", 0, 100], ["maxRounds", 1, 50], ["concurrency", 1, 100], ["researcherTimeoutMs", 1_000, 3_600_000]] as const) {
    const value = input[name];
    if (!Number.isSafeInteger(value) || value < min || value > max) reject(`${name}-bounds`);
  }
  return findings;
}

/**
 * Quarantine direct instructions to the agent at the start of an unquoted line.
 * Quotes, blockquotes, code fences and contextual discussion remain evidence.
 * This deliberately narrow screen is a heuristic, not a prompt-injection proof.
 */
export function screenNotes(text: string, phase: "research-notes" | "synthesis", brief?: string): { text: string; findings: GuardrailFinding[] } {
  let fenced = false;
  let count = 0;
  const screened = text.split(/\r?\n/).map((line) => {
    const trimmed = line.trim();
    if (/^(?:```|~~~)/.test(trimmed)) { fenced = !fenced; return line; }
    if (fenced || /^(?:>|["'“‘])/.test(trimmed)) return line;
    const candidate = trimmed.replace(/^(?:[-*+]\s+|\d+[.)]\s+)/, "").replace(/^(?:assistant|system|developer)\s*:\s*/i, "");
    if (/^(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|above|system|developer)\s+(?:instructions?|messages?|rules?)\s+(?:is|are|was|were|means|refers|appears)\b/i.test(candidate)) return line;
    const instruction = /^(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|above|system|developer)\s+(?:instructions?|messages?|rules?)\b/i.test(candidate)
      || /^(?:you\s+must|assistant\s*,?\s*(?:must|should))\s+(?:ignore|disregard|override)\s+(?:the\s+)?(?:system|developer|previous|prior)\b/i.test(candidate)
      || /^(?:system|developer)\s+(?:message|instruction)\s*:\s*(?:ignore|override|disregard)\b/i.test(candidate);
    if (!instruction) return line;
    count += 1;
    return "[Guardrail: instruction-like note line quarantined; original retained in research record.]";
  }).join("\n");
  return { text: count ? screened : text, findings: count ? [{ rule: "note-instruction-boundary", phase, action: "quarantine", ...(brief ? { brief } : {}), count, message: "Direct instruction-like note lines were withheld from downstream prompts." }] : [] };
}

/** Annotate a completed report without changing its text or citation diagnostics. */
export function reportFindings(report: string, citations: { unknownUrls: string[]; binding: { unbound: number } }): GuardrailFinding[] {
  const finding = (rule: string, count: number, message: string): GuardrailFinding => ({ rule, phase: "report", action: "annotate", count, message });
  const findings: GuardrailFinding[] = [];
  if (!report.trim()) findings.push(finding("empty-report", 1, "The writer returned no report."));
  if (citations.unknownUrls.length) findings.push(finding("unknown-report-citations", citations.unknownUrls.length, "Report citations require source review."));
  if (citations.binding.unbound) findings.push(finding("unbound-report-numbers", citations.binding.unbound, "Cited numerical claims require source review."));
  const instructions = screenNotes(report, "synthesis").findings.reduce((sum, f) => sum + f.count, 0);
  if (instructions) findings.push(finding("report-instruction-boundary", instructions, "The report contains direct instruction-like lines requiring human review."));
  return findings;
}
