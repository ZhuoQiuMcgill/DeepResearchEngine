/**
 * Minimal strategy module template. Copy this directory to
 * src/strategies/<name>/, set `name` to the directory name, and replace the
 * logic. Directories starting with "_" are never loaded by the platform.
 *
 * This template makes no model calls: one researcher answers the question,
 * then it stops and hands all notes to the writer. See ../baseline/ for a
 * full strategy that uses ctx.model.
 */
import {
  CONTRACT_VERSION,
  type JsonValue,
  type ResearchResult,
  type ResearchStrategy,
  type StrategyContext,
  type StrategyModule,
  type StrategyStep,
  type SynthesisInput,
} from "../../core/index.js";

/** Strategy state: plain JSON only. Use `type`, not `interface`. */
type TemplateState = {
  question: string;
  notes: { label: string; notes: string }[];
};

class TemplateStrategy implements ResearchStrategy<TemplateState> {
  readonly name = "_template";

  async init(input: { question: string }, _ctx: StrategyContext): Promise<StrategyStep<TemplateState>> {
    return {
      state: { question: input.question, notes: [] },
      decision: {
        briefs: [{ objective: input.question, keyQuestions: [input.question] }],
        stop: false,
        rationale: "Single researcher on the whole question.",
      },
    };
  }

  async observe(state: TemplateState, results: ResearchResult[], _ctx: StrategyContext): Promise<StrategyStep<TemplateState>> {
    const ok = results.filter((r) => r.status === "ok").map((r) => ({ label: r.brief.objective, notes: r.notes }));
    return {
      state: { ...state, notes: [...state.notes, ...ok] },
      decision: { briefs: [], stop: true, rationale: "One round is enough for the template." },
    };
  }

  async finalize(state: TemplateState, _ctx: StrategyContext): Promise<SynthesisInput> {
    return { material: state.notes };
  }
}

const template: StrategyModule = {
  name: "_template",
  description: "Minimal example: one researcher, one round.",
  contractVersion: CONTRACT_VERSION,
  create: (_options?: JsonValue) => new TemplateStrategy(),
};
export default template;
