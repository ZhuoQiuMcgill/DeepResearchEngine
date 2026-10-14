/**
 * Shared report writer, adapted from the report-writer instructions of Claude
 * Code's deep-research skill. It sees only the verbatim question and the
 * strategy's SynthesisInput.
 */
import { ChatPromptTemplate } from "@langchain/core/prompts";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { SynthesisInput } from "../core/contracts.js";
import { citationBinding, numericBindingIssues, numericSupportLedger } from "../core/citations.js";
import { extractUrls, pageKey } from "../core/urls.js";
import { HumanMessage, type BaseMessage } from "@langchain/core/messages";
import { z } from "zod";

const SYSTEM = `You synthesize research notes written by a team of researchers into a focused, well-structured report. Your top priority is a high-quality report that answers the research question as well and as completely as the notes allow. You do no research yourself: use only the notes you are given. Today's date is {today}.

## Report format
# <Title of about 6 words, with an active verb>
<Bottom-line paragraph: lead with the key finding that directly answers the question, then its significance and essential context. One paragraph of roughly 5-8 sentences; a reader who stops here should be informed.>

## <Section heading that states a specific insight>
<Dense narrative paragraphs with **bold key facts**, citing inline as ([Publisher or title](URL)). No bullet points or numbered lists in body paragraphs.>

(3-5 sections in total, as the question needs)

## Conclusion
<1-2 paragraphs of takeaways and implications only, without repeating earlier content.>

## Writing rules
- Preserve explicit names and acronym expansions in the question. Never replace its subject with a more popular acronym meaning. When identity is unsupported, state that limitation. Limited search coverage cannot establish that a named concept does not exist or that the user's wording is mistaken.
- Section headings are sentence case and act as signposts: a reader skimming only the headings should understand the report. Use specific numbers or claims rather than generic labels.
- Use tables when they make a comparison clearer.
- Match length to the question: a factual or practical question deserves a concise, decision-ready answer; a broad question may need more depth.
- Write in English, in clear, direct, active language. Synthesize how findings connect rather than listing facts. Interpret what data means.
- Be epistemically honest: state what is uncertain, unknown or contested, consider other positions, and take positions where the evidence supports them.
- The notes come from several researchers and may disagree on numbers, dates, prices or status. When they do, say so and give both sources; prefer the more authoritative or more recent source and say why. Never silently pick one.
- Write about the evidence, not about a research process: you did no research, so never write "I", "we", "searched", "retrieved" or "was not checked", and never mention notes, researchers or this process. Rewrite any process statement in the notes as a statement about the evidence, e.g. "no official source states X".
- Use all the notes. Every researcher's key findings belong in the report unless they are redundant or off the question; do not drop a whole topic, caution or safety warning.
- Attribute authors and affiliations individually. Do not attach a coauthor's affiliation to the originator, or infer biography from a paper's combined author metadata. Omit incidental biographical details that the question does not need.

## Citation rules
- The graph's source registry records origin and actual access state. Inherited support is not a new full-page read. Snippets, truncated pages and failed reads cannot support claims about unseen details. Preserve the notes' qualifications and gaps. A listed URL establishes provenance, not correctness of every associated claim.
- Cite inline with ([Publisher or title](URL)) after major findings, numbers and references to specific publications, using URLs exactly and completely as they appear in the notes.
- A link marked "(unverified link)" was not confirmed by the search tools. Do not let it be the only support for a key claim, and do not copy the marker.
- Every sentence that states a number, price, date or specification carries its citation in the same sentence, including in the opening paragraph and in tables.
- Each claim keeps the URL the notes give for that same claim. Never move a URL to a different claim, and never cite a page for a number it was not given for.
- Keep each factual number or date attached to the notes line and URL that state it. Publication years explicitly present in that URL's bibliography label may identify the paper; they cannot establish when a method originated or support a numerical quantity. Do not turn specific dated publications into an approximate decade or a coinage date. If a temporal interpretation is essential, label it as an inference and give its exact dated premises with their own citations.
- A specific finding, number or publication reference that has no source URL in the notes must not appear in the report. Five well-sourced claims beat twenty half-sourced ones.
- Never invent URLs, facts or numbers.

Output only the report in Markdown.`;

const HUMAN = `Research question:
{question}

{outline}{guidance}Research notes ({count} sets):

{material}

Graph-supplied source registry (access metadata, not additional findings):
{sourceRegistry}`;

const writerPrompt = ChatPromptTemplate.fromMessages([
  ["system", SYSTEM],
  ["human", HUMAN],
]);

export interface WriterOutput {
  report: string;
  diagnostics: string[];
}

export type WriteFn = (question: string, synthesis: SynthesisInput) => Promise<WriterOutput>;

function reportText(msg: BaseMessage): string {
  return (typeof msg.content === "string" ? msg.content : msg.content.filter(b => b.type === "text").map(b => b.text ?? "").join("")).trim();
}

const NumericEdits = z.object({ edits: z.array(z.object({ index: z.number().int().min(0), text: z.string() })) });

export function createWriter(model: BaseChatModel, today: string): WriteFn {
  return async (question, synthesis) => {
    const outline = synthesis.outline?.length
      ? `Suggested report outline:\n${synthesis.outline.map((o) => `- ${o}`).join("\n")}\n\n`
      : "";
    const guidance = synthesis.guidance?.trim() ? `Additional guidance:\n${synthesis.guidance.trim()}\n\n` : "";
    const material = synthesis.material
      .map((m, i) => `<notes index="${i + 1}" label="${m.label.replace(/"/g, "'")}">\n${m.notes}\n</notes>`)
      .join("\n\n");
    const messages = await writerPrompt.formatMessages({
      today,
      question,
      outline,
      guidance,
      count: String(synthesis.material.length),
      material: material || "(no research notes were produced)",
      sourceRegistry: JSON.stringify(synthesis.sourceRegistry ?? []),
    });
    const msg = await model.invoke(messages);
    let report = reportText(msg);
    const diagnostics: string[] = [];
    const binding = citationBinding(report, synthesis.material);
    if (binding.unbound && report) {
      // One bounded, traced revision, using the same original source material.
      // Never alter notes, add research, or suppress a remaining diagnostic.
      diagnostics.push(`numeric citation revision attempted: ${binding.unbound} flagged unit(s)`);
      const issues = numericBindingIssues(report, synthesis.material);
      const ledger = numericSupportLedger(synthesis.material);
      const eligible = new Set((synthesis.sourceRegistry?.map(s => s.url) ?? ledger.map(s => s.url)).map(pageKey));
      let edits: z.infer<typeof NumericEdits>["edits"] = [];
      try {
        const repair = model.withStructuredOutput(NumericEdits, { method: "jsonSchema", name: "numeric_source_edits" });
        const reply = await repair.invoke([...messages, msg, new HumanMessage(
          `Return edits for ONLY these indexed statements; do not rewrite the whole report. Each statement has source-specific candidate notes below. Use their exact URLs to support each date/number separately, or remove an unnecessary unsupported date/detail. Years in bibliography labels support only the publication date of that paper. Do not preserve a numerical assertion without its citation, infer a decade or origin date, invent support, or add new facts. Return one replacement sentence/block per index, or empty text if no faithful sourced replacement is possible.\n${JSON.stringify(issues.map((issue, index) => ({ index, text: issue.text, missing: issue.missing, support: ledger.filter(l => eligible.has(pageKey(l.url)) && issue.missing.some(n => l.numbers.includes(n) || l.publicationYears.includes(n))) })))}`,
        )]);
        edits = reply.edits;
      } catch {
        diagnostics.push("numeric statement revision failed; strict source gate applied");
      }
      const audit: { before: string; after: string; action: string }[] = [];
      for (let i = issues.length - 1; i >= 0; i--) {
        const issue = issues[i]!;
        const candidate = edits.find(e => e.index === i)?.text.trim() ?? "";
        const accepted = !!candidate && citationBinding(candidate, synthesis.material).unbound === 0
          && extractUrls(candidate).every(url => eligible.has(pageKey(url)));
        // Do not publish an unsupported numerical statement merely because the
        // model repeated it. Audit omitted units; keep all unaffected prose.
        const replacement = accepted ? (issue.text.match(/^\s*/)?.[0] ?? "") + candidate : "";
        report = report.slice(0, issue.start) + replacement + report.slice(issue.end);
        audit.push({ before: issue.text.trim(), after: replacement, action: accepted ? "replaced" : "omitted" });
      }
      diagnostics.push(`numeric source edits: ${audit.filter(a => a.action === "replaced").length} replaced, ${audit.filter(a => a.action === "omitted").length} omitted`);
      diagnostics.push(`numeric source edit audit: ${JSON.stringify(audit)}`);
      const after = citationBinding(report, synthesis.material);
      if (after.unbound) diagnostics.push(`numeric citation issues remain after bounded revision: ${after.unbound} unit(s)`);
    }
    const stop = (msg.response_metadata as { stop_reason?: string; finish_reason?: string; status?: string } | undefined) ?? {};
    if (stop.stop_reason === "max_tokens" || stop.finish_reason === "length" || stop.status === "incomplete") diagnostics.push("report output truncated");
    if (!report) diagnostics.push("writer returned an empty report");
    return { report, diagnostics };
  };
}
