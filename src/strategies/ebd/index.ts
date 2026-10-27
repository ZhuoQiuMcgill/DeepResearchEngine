/**
 * EBD strategy module (design DESIGN.md). Orchestration only:
 *
 * - init: request analysis (fixed or agent mode) → goal table → rank → pack briefs.
 * - observe, once per round: map notes to goals and index evidence lines →
 *   conflict checker → round analyst → settle goals, accept new goals, make goals
 *   moot, set which settle goals are necessary → stop rules → rank → pack briefs.
 * - finalize: material grouped by goal, outline from the synthesis questions,
 *   guidance with the assumption verdicts and conflicts.
 *
 * The model makes narrow, categorical judgments; code turns them into priorities
 * and stop decisions. Every step records its model calls and code actions in
 * `state.step`, which the run viewer shows (viewer/README.md).
 */
import {
  CONTRACT_VERSION,
  type Decision,
  type JsonValue,
  type ResearchResult,
  type ResearchStrategy,
  type StrategyContext,
  type StrategyModule,
  type StrategyStep,
  type SynthesisInput,
} from "../../core/index.js";
import { briefFor, selectWithReserve } from "./briefs.js";
import { goalsFromAnalysis, isComplete, isSaturated, mootDependents, rankReady, requeueOrExhaust, treeMetrics, type RoundProgress } from "./goals.js";
import { parseOptions, type EbdOptions } from "./options.js";
import { requestMessage, runAgentAnalysis, runFixedAnalysis, type AnalysisOutcome } from "./request/index.js";
import { acceptProposals, applyJudgments, runRoundAnalyst, servedGoals, verdictSummary } from "./rounds/analyst.js";
import { applyConflicts, runConflictChecker, settlePriority } from "./rounds/conflicts.js";
import { readResult } from "./rounds/evidence.js";
import { isSettled, type CallRecord, type EbdState, type EvidenceLine, type StepLog } from "./state.js";
import { buildSynthesis } from "./synthesis.js";

/** The request analysis's model turns as call records, with each turn's check result. */
export function analysisCalls(out: AnalysisOutcome, question: string, today: string): CallRecord[] {
  const calls: CallRecord[] = [];
  for (const e of out.trace) {
    if (e.type === "model_turn") {
      calls.push({
        role: "request_analyst",
        attempt: e.turn,
        accepted: false,
        errors: [],
        warnings: [],
        input: e.turn === 1 ? requestMessage(question, today, out.scan) : `(turn ${e.turn}: the previous messages plus ${out.mode === "fixed" ? "the numbered errors" : "the tool results"})`,
        reply: [e.toolCalls.length ? `[tool calls: ${e.toolCalls.join(", ")}]` : "", e.text].filter(Boolean).join("\n"),
        inputTokens: e.inputTokens,
        outputTokens: e.outputTokens,
        ms: e.ms,
      });
    } else if (e.type === "check" || (e.type === "tool_result" && e.name === "submit_analysis")) {
      const last = calls.at(-1);
      if (!last) continue;
      if (e.type === "check") {
        last.accepted = e.accepted;
        last.errors = e.errors;
        last.warnings = e.warnings;
      } else {
        const r = e.result as { accepted?: boolean; errors?: CallRecord["errors"]; warnings?: CallRecord["warnings"] };
        last.accepted = Boolean(r.accepted);
        last.errors = r.errors ?? [];
        last.warnings = r.warnings ?? [];
      }
    }
  }
  return calls;
}

function emptyStep(phase: StepLog["phase"], round: number): StepLog {
  return { phase, round, calls: [], events: [] };
}

class EbdStrategy implements ResearchStrategy<EbdState> {
  readonly name = "ebd";

  constructor(private readonly options: EbdOptions) {}

  async init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<EbdState>> {
    const args = { question: input.question, today: ctx.today, model: ctx.model };
    const out = this.options.init === "agent" ? await runAgentAnalysis(args) : await runFixedAnalysis(args);
    if (!out.analysis) throw new Error(`Request analysis (${out.mode}) produced no usable analysis: ${out.errors.map((e) => e.message).join("; ").slice(0, 500)}`);
    const a = out.analysis;
    const step = emptyStep("init", 0);
    step.calls = analysisCalls(out, input.question, ctx.today);
    const state: EbdState = {
      question: input.question,
      today: ctx.today,
      init: { mode: out.mode, accepted: out.accepted, fallback: out.fallback, attempts: out.attempts, stopReason: out.stopReason },
      analysis: a,
      goals: goalsFromAnalysis(a),
      objectsFound: [],
      conflicts: [],
      evidence: [],
      results: [],
      roundsObserved: 0,
      extraRoundServed: false,
      stop: null,
      tree: treeMetrics([]),
      step,
      problems: out.fallback ? [`request analysis fell back after ${out.attempts} attempts: ${out.errors.map((e) => e.message).join("; ").slice(0, 300)}`] : [],
    };
    state.tree = treeMetrics(state.goals);
    const head = `Request analysis (${out.mode} mode, ${out.accepted ? "accepted" : "fallback"} after ${out.attempts} attempt(s)): ${a.rom.objects.length} objects, ${a.assumptions.length} assumptions, ${state.goals.length} search goals, ${a.questions.length - state.goals.length} synthesis questions.`;
    if (a.status === "out_of_scope") {
      state.stop = { kind: "out_of_scope", round: 0, reason: a.status_reason ?? "out of scope" };
      return { state, decision: { briefs: [], stop: true, rationale: `${head}\nOut of scope: ${a.status_reason ?? ""}` } };
    }
    const central = a.rom.objects.filter((o) => a.rom.central_object_ids.includes(o.id)).map((o) => `"${o.text}"`);
    const intro = [
      head,
      `Central objects: ${central.join(", ") || "none"}.`,
      a.assumptions.length ? `Assumptions to verify: ${a.assumptions.map((x) => `${x.id} ${x.claim}`).join(" ")}` : "No assumptions to verify.",
    ];
    return this.plan(state, ctx, intro, null);
  }

  async observe(previous: EbdState, results: ResearchResult[], ctx: StrategyContext): Promise<StrategyStep<EbdState>> {
    const state = structuredClone(previous);
    const round = ctx.round - 1;
    const step = emptyStep("observe", round);
    state.step = step;
    const log = (line: string) => step.events.push(line);
    const before = new Set(state.goals.map((g) => g.id));

    // Section 8: read the results; every served goal spends an attempt.
    const fresh: EvidenceLine[] = [];
    for (const r of results) {
      const { record, evidence } = readResult(r);
      state.results.push(record);
      state.evidence.push(...evidence);
      fresh.push(...evidence);
      const mapped = record.sections.map((s) => `${s.title.slice(0, 60) || "(untitled)"} → ${s.goalIds.join(",")} by ${s.mappedBy}`);
      log(`${record.briefId} ${record.status}: ${evidence.filter((e) => e.kind === "finding").length} findings, ${evidence.filter((e) => e.kind === "gap").length} gaps${mapped.length ? `; sections: ${mapped.join(" | ")}` : ""}`);
      if (record.status === "ok" && record.goalIds.length > 1 && record.sections.some((s) => s.mappedBy === "brief")) {
        state.problems.push(`round ${round} ${record.briefId}: some sections had no goal ID in the heading and were mapped to every goal of the brief`);
      }
      for (const id of record.goalIds) {
        const g = state.goals.find((x) => x.id === id);
        if (!g) continue;
        g.attempts += 1;
        g.servedRounds.push(round);
      }
    }
    state.roundsObserved = round;
    const allFailed = results.length > 0 && results.every((r) => r.status === "failed");
    const failedOnly = new Set(results.filter((r) => r.status === "failed").flatMap((r) => readResult(r).record.goalIds));
    for (const r of results.filter((x) => x.status === "ok")) for (const id of readResult(r).record.goalIds) failedOnly.delete(id);
    const settledNow: string[] = [];
    for (const id of failedOnly) {
      const g = state.goals.find((x) => x.id === id);
      if (!g || isSettled(g)) continue;
      const how = requeueOrExhaust(g, round, this.options.maxAttempts, null);
      if (how === "exhausted" && g.need === "necessary") settledNow.push(g.id);
      log(`${id}: researcher failed → ${how}`);
    }

    // Section 9: conflicts, before the round analyst.
    let newConflicts = 0;
    if (this.options.conflicts && fresh.some((e) => e.kind === "finding")) {
      const checked = await runConflictChecker(ctx.model, state, fresh);
      step.calls.push(...checked.calls);
      if (checked.fallback) state.problems.push(`round ${round}: conflict checker fell back to its valid items`);
      if (checked.value) newConflicts = applyConflicts(state, checked.value, round, this.options, log).length;
      else if (!checked.accepted) state.problems.push(`round ${round}: conflict checker gave no usable reply`);
    }

    // Section 10: judgments and new goals.
    const served = servedGoals(state, round).filter((g) => !isSettled(g) && !failedOnly.has(g.id));
    let progress: RoundProgress = { settled: settledNow, advanced: [], newConflicts, newNecessary: 0, allFailed };
    if (served.length) {
      const judged = await runRoundAnalyst(ctx.model, state, round, served, this.options);
      step.calls.push(...judged.calls);
      if (judged.fallback) state.problems.push(`round ${round}: round analyst fell back to its repaired judgments (invalid evidence IDs dropped, outcomes recomputed)`);
      if (!judged.value) state.problems.push(`round ${round}: round analyst gave no usable reply; served goals treated as partial`);
      const applied = applyJudgments(state, judged.value, served, round, this.options, log);
      const added = acceptProposals(state, judged.value, round, this.options, log);
      const necessary = new Set(state.goals.filter((g) => g.need === "necessary").map((g) => g.id));
      progress = {
        ...progress,
        settled: [...progress.settled, ...applied.settled.filter((id) => necessary.has(id))],
        advanced: applied.advanced.filter((id) => necessary.has(id)),
        newNecessary: added.filter((g) => g.need === "necessary").length,
      };
    }
    const mooted = mootDependents(state, round);
    if (mooted.length) log(`moot after a contradicted premise: ${mooted.join(", ")}`);
    // Section 9: a settle goal stays necessary only while it decides a claim or a goal waits for it.
    settlePriority(state, log);
    const newSettle = state.goals.filter((g) => !before.has(g.id) && g.settles && g.need === "necessary").length;
    progress.newNecessary += newSettle;
    state.tree = treeMetrics(state.goals);

    const summary = [
      `Round ${round}: ${results.filter((r) => r.status === "ok").length} of ${results.length} researcher(s) returned notes; ${fresh.filter((e) => e.kind === "finding").length} findings indexed.`,
      progress.settled.length || mooted.length ? `Settled: ${[...progress.settled, ...mooted].join(", ")}.` : "No necessary goal settled.",
      newConflicts ? `New conflicts: ${state.conflicts.filter((c) => c.createdRound === round).map((c) => `${c.id} (${c.type}) ${c.statement}`).join(" ")}` : "",
      state.goals.some((g) => !before.has(g.id)) ? `New goals: ${state.goals.filter((g) => !before.has(g.id)).map((g) => `${g.id} ${g.text}`).join(" ")}` : "",
      state.analysis.assumptions.length ? `Assumptions: ${verdictSummary(state).join(" ")}` : "",
    ].filter(Boolean);
    return this.plan(state, ctx, summary, progress);
  }

  async finalize(state: EbdState, _ctx: StrategyContext): Promise<SynthesisInput> {
    return buildSynthesis(state);
  }

  /** Section 11 stop rules, then sections 6 and 7: rank the ready goals and pack them into briefs. */
  private plan(state: EbdState, ctx: StrategyContext, lines: string[], progress: RoundProgress | null): StrategyStep<EbdState> {
    const log = (line: string) => state.step.events.push(line);
    const done = (kind: "complete" | "saturated", reason: string): StrategyStep<EbdState> => {
      state.stop = state.stop?.kind === kind ? state.stop : { kind, round: state.roundsObserved, reason };
      log(`stop: ${kind} (${reason})`);
      return { state, decision: { briefs: [], stop: true, rationale: [...lines, `Stop: ${kind}. ${reason}.`].join("\n") } };
    };

    let ranked = rankReady(state, this.options);
    if (progress) {
      const complete = isComplete(state);
      if (complete.complete) {
        const completing = ranked.filter((r) => r.goal.need === "completing");
        if (this.options.extraRound && !state.extraRoundServed && completing.length && ctx.budget.researchersRemaining > 0) {
          state.extraRoundServed = true;
          state.stop = { kind: "complete", round: state.roundsObserved, reason: complete.reason };
          log("complete; one extra round serves completing goals");
          ranked = completing;
          lines = [...lines, "Complete: every necessary goal is settled. One extra round serves completing goals."];
        } else {
          return done("complete", complete.reason);
        }
      } else if (isSaturated(progress)) {
        return done("saturated", "the round settled or advanced no necessary goal and produced no new conflict or necessary goal");
      } else {
        log(`not complete: ${complete.reason}`);
      }
    }
    if (!ranked.length) return done("saturated", "no goal is ready to serve");

    const { groups, reserve, held, reservedFor, researchersKept, released } = selectWithReserve(ranked, state, ctx.budget.researchersRemaining, this.options);
    const briefs = groups.map((g, i) => briefFor(g, i, state));
    const decision: Decision = { briefs, stop: false, rationale: "" };
    const served = groups.flatMap((g) => g.goals);
    const why = served.map((g) => {
      const r = ranked.find((x) => x.goal.id === g.id)!;
      return `${g.id} (level ${g.level} ${g.kind}${r.reach ? `, reach ${r.reach}` : ""}${g.id === reserve ? ", reserve slot" : ""})`;
    });
    const waiting = ranked.filter((r) => !served.includes(r.goal)).map((r) => r.goal.id);
    // With nothing reserved, held goals lost to briefs that carry request goals (GPU rerun, 2026-10-21).
    const heldWhy = researchersKept ? `${researchersKept} researcher(s) kept for ${reservedFor.map((g) => g.id).join(", ")}` : "the researchers left go to briefs with request goals";
    const heldNote = held.length ? `Held back for first tries: ${held.map((g) => g.id).join(", ")} (${heldWhy}).` : "";
    if (held.length) log(`held back for first tries: ${held.map((g) => g.id).join(", ")}; ${heldWhy}`);
    if (released) log("first-try reserve released: no other brief can be served this round");
    const budgetNote = ctx.budget.researchersRemaining === 0 ? "No researcher budget is left; these briefs record the unmet demand." : "";
    if (ctx.budget.researchersRemaining === 0) {
      state.stop = state.stop ?? { kind: "budget", round: state.roundsObserved, reason: "researchersRemaining is 0" };
      log("budget exhausted: returning the wanted briefs with stop: false");
    }
    log(`serve ${briefs.length} brief(s): ${briefs.map((b) => b.tag).join(" | ")}${waiting.length ? `; ready but waiting: ${waiting.join(", ")}` : ""}`);
    decision.rationale = [...lines, `Next: ${briefs.length} brief(s) serving ${why.join(", ")}.`, waiting.length ? `Ready but not served this round: ${waiting.join(", ")}.` : "", heldNote, budgetNote]
      .filter(Boolean)
      .join("\n");
    return { state, decision };
  }
}

const ebd: StrategyModule = {
  name: "ebd",
  description: "Environment-Based Design: request analysis, a goal tree ranked by EBD's questioning rules, a conflict checker, per-goal done judgments and code stop rules.",
  contractVersion: CONTRACT_VERSION,
  create: (options?: JsonValue) => new EbdStrategy(parseOptions(options)),
};
export default ebd;
