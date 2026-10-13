/**
 * One researcher: renders the shared prompt for a brief, runs the provider
 * adapter and normalises the outcome into a ResearchResult. Failures are
 * returned as results, never thrown.
 */
import type { Callbacks } from "@langchain/core/callbacks/manager";
import type { ModelProfile } from "../config/models.js";
import type { ResearchBrief, ResearchResult, Source } from "../core/contracts.js";
import { parseNotes } from "../core/notes.js";
import { extractUrls, pageKey, urlKey } from "../core/urls.js";
import type { UsageLedger } from "../observability/usage.js";
import { runAnthropic } from "./adapters/anthropic.js";
import { runOpenAI } from "./adapters/openai.js";
import { runLocal } from "./adapters/local.js";
import type { AdapterOutput } from "./adapters/types.js";
import { researcherPrompt, researcherPromptValues } from "./prompts.js";

export interface ResearcherDeps {
  profile: ModelProfile;
  ledger: UsageLedger;
  callbacks?: Callbacks;
  timeoutMs: number;
  today: string;
}

export type ResearchFn = (question: string, brief: ResearchBrief, inheritedSources?: Source[]) => Promise<ResearchResult>;

export function createResearcher(deps: ResearcherDeps): ResearchFn {
  return async (question, brief, inheritedSources = []) => {
    const started = Date.now();
    const base = { brief, model: deps.profile.model, queries: [] as string[], sources: [] as Source[] };
    try {
      const messages = await researcherPrompt.formatMessages(
        researcherPromptValues(question, brief, deps.profile.toolCallsPerResearcher, deps.today, inheritedSources),
      );
      const call = {
        messages,
        ledger: deps.ledger,
        role: "researcher",
        callbacks: deps.callbacks,
        signal: AbortSignal.timeout(deps.timeoutMs),
        inheritedSources,
      };
      const out: AdapterOutput =
        deps.profile.provider === "anthropic" ? await runAnthropic(deps.profile, call) :
        deps.profile.provider === "local" ? await runLocal(deps.profile, call) : await runOpenAI(deps.profile, call);
      const usage = {
        inputTokens: out.inputTokens,
        outputTokens: out.outputTokens,
        searches: out.searches,
        pageReads: out.pageReads,
      };
      const { sources, unlisted } = mergeSources({ ...out, sources: [...inheritedSources, ...out.sources] });
      const diagnostics = [...out.diagnostics];
      if (unlisted.length) diagnostics.push(`${unlisted.length} cited URL(s) not reported by the provider's tools`);
      if (!out.notes) {
        return {
          ...base,
          status: "failed",
          failure: { kind: "empty", message: "The model returned no notes text." },
          notes: "",
          sources,
          queries: out.queries,
          usage,
          durationMs: Date.now() - started,
          unlistedCitations: unlisted,
          diagnostics,
        };
      }
      if (!parseNotes(out.notes).parsed) diagnostics.push("notes do not follow the shared format");
      if (!sources.some((s) => s.cited) && !unlisted.length) diagnostics.push("no cited source URL in notes");
      return {
        ...base,
        status: "ok",
        notes: out.notes,
        sources,
        queries: out.queries,
        usage,
        durationMs: Date.now() - started,
        unlistedCitations: unlisted,
        diagnostics,
      };
    } catch (err) {
      const e = err as { name?: string; message?: string };
      const timeout = e?.name === "TimeoutError" || e?.name === "AbortError" || /abort|timed? ?out/i.test(e?.message ?? "");
      return {
        ...base,
        status: "failed",
        failure: { kind: timeout ? "timeout" : "provider", message: String(e?.message ?? err).slice(0, 2000) },
        notes: "",
        usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 },
        durationMs: Date.now() - started,
        unlistedCitations: [],
        diagnostics: [],
      };
    }
  };
}

/**
 * Deduplicate provider sources and mark the ones the notes or citations
 * reference. Cited URLs the provider never reported (compared without query
 * strings) are returned separately and are not added to the sources.
 */
function mergeSources(out: AdapterOutput): { sources: Source[]; unlisted: string[] } {
  const noteUrls = extractUrls(out.notes);
  const cited = [...noteUrls, ...out.citedUrls];
  const citedPages = new Set(cited.map(pageKey));
  const byKey = new Map<string, Source>();
  for (const s of out.sources) {
    const key = urlKey(s.url);
    const prev = byKey.get(key);
    if (prev) {
      if (!prev.title && s.title) prev.title = s.title;
      if (s.readState) prev.readState = s.readState;
      if (!prev.originBriefId && s.originBriefId) prev.originBriefId = s.originBriefId;
    } else {
      byKey.set(key, { ...s, cited: citedPages.has(pageKey(s.url)) });
    }
  }
  const providerPages = new Set(out.sources.map((s) => pageKey(s.url)));
  const unlisted = [...new Set(noteUrls.filter((u) => !providerPages.has(pageKey(u))))];
  return { sources: [...byKey.values()], unlisted };
}
