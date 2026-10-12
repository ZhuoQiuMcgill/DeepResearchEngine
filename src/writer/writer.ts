/**
 * Shared report writer, adapted from the report-writer instructions of Claude
 * Code's deep-research skill. It sees only the verbatim question and the
 * strategy's SynthesisInput.
 */
import { ChatPromptTemplate } from "@langchain/core/prompts";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { SynthesisInput } from "../core/contracts.js";

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
- Section headings are sentence case and act as signposts: a reader skimming only the headings should understand the report. Use specific numbers or claims rather than generic labels.
- Use tables when they make a comparison clearer.
- Match length to the question: a factual or practical question deserves a concise, decision-ready answer; a broad question may need more depth.
- Write in English, in clear, direct, active language. Synthesize how findings connect rather than listing facts. Interpret what data means.
- Be epistemically honest: state what is uncertain, unknown or contested, consider other positions, and take positions where the evidence supports them.
- The notes come from several researchers and may disagree on numbers, dates, prices or status. When they do, say so and give both sources; prefer the more authoritative or more recent source and say why. Never silently pick one.
- Write about the evidence, not about a research process: you did no research, so never write "I", "we", "searched", "retrieved" or "was not checked", and never mention notes, researchers or this process. Rewrite any process statement in the notes as a statement about the evidence, e.g. "no official source states X".
- Use all the notes. Every researcher's key findings belong in the report unless they are redundant or off the question; do not drop a whole topic, caution or safety warning.

## Citation rules
- Cite inline with ([Publisher or title](URL)) after major findings, numbers and references to specific publications, using URLs exactly and completely as they appear in the notes.
- A link marked "(unverified link)" was not confirmed by the search tools. Do not let it be the only support for a key claim, and do not copy the marker.
- Every sentence that states a number, price, date or specification carries its citation in the same sentence, including in the opening paragraph and in tables.
- Each claim keeps the URL the notes give for that same claim. Never move a URL to a different claim, and never cite a page for a number it was not given for.
- A specific finding, number or publication reference that has no source URL in the notes must not appear in the report. Five well-sourced claims beat twenty half-sourced ones.
- Never invent URLs, facts or numbers.

Output only the report in Markdown.`;

const HUMAN = `Research question:
{question}

{outline}{guidance}Research notes ({count} sets):

{material}`;

const writerPrompt = ChatPromptTemplate.fromMessages([
  ["system", SYSTEM],
  ["human", HUMAN],
]);

export interface WriterOutput {
  report: string;
  diagnostics: string[];
}

export type WriteFn = (question: string, synthesis: SynthesisInput) => Promise<WriterOutput>;

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
    });
    const msg = await model.invoke(messages);
    const report = (typeof msg.content === "string"
      ? msg.content
      : (msg.content as { type: string; text?: string }[]).filter((b) => b.type === "text").map((b) => b.text ?? "").join("")
    ).trim();
    const diagnostics: string[] = [];
    const stop = (msg.response_metadata as { stop_reason?: string; finish_reason?: string; status?: string } | undefined) ?? {};
    if (stop.stop_reason === "max_tokens" || stop.finish_reason === "length" || stop.status === "incomplete") diagnostics.push("report output truncated");
    if (!report) diagnostics.push("writer returned an empty report");
    return { report, diagnostics };
  };
}
