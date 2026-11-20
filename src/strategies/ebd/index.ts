/**
 * EBD strategy module (design DESIGN.md). Orchestration only:
 *
 * - init: request analysis (fixed or agent mode) → goal table → rank → pack briefs; or, with
 *   `init: "environment"` (section 28), the whole first plan in one call.
 * - observe, once per round: map notes to goals and index evidence lines →
 *   conflict checker → round analyst → settle goals, accept new goals, make goals
 *   moot, set which settle goals are necessary → stop rules → rank → pack briefs.
 * - finalize: material grouped by goal, outline from the synthesis questions,
 *   guidance with the assumption verdicts and conflicts (with `leanGuidance`,
 *   only what the notes do not show: design section 20).
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
import { briefFor, fitBrief, isClaimCheck, pack, partsFirst, questionCount, selectWithReserve, shareChecks, shareRiders, spread, type Selection } from "./briefs.js";
import { analysisFromPlan, applyPlan, runEnvironmentAnalysis } from "./environment.js";
import { applyExtension, isSuperseded, mapSummary, runExtension } from "./extension.js";
import { applyGiven, givenClaims, recordSort, runPremiseSort } from "./premises.js";
import { endedByFailures, gatesAnswer, goalsFromAnalysis, isComplete, isSaturated, mootDependents, rankReady, releaseWaiting, requeueOrExhaust, treeMetrics, type RoundProgress } from "./goals.js";
import { parseOptions, type EbdOptions } from "./options.js";
import { minimalAnalysis, requestMessage, runAgentAnalysis, runFixedAnalysis, type AnalysisOutcome } from "./request/index.js";
import { acceptProposals, applyJudgments, runRoundAnalyst, servedGoals, verdictSummary } from "./rounds/analyst.js";
import { applyConflicts, asksCritical, resolveClaimChecks, runConflictChecker, settlePriority } from "./rounds/conflicts.js";
import { readResult } from "./rounds/evidence.js";
import { eventOf, isPlanned, isSettled, isUnaskedPart, type CallRecord, type EbdState, type EvidenceLine, type Goal, type StepLog } from "./state.js";
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

/** r1-b2 before r1-b10: round, then brief number. */
export function byBrief(a: string, b: string): number {
  const n = (id: string) => (id.match(/\d+/g) ?? []).map(Number);
  const [x, y] = [n(a), n(b)];
  return (x[0] ?? 0) - (y[0] ?? 0) || (x[1] ?? 0) - (y[1] ?? 0) || a.localeCompare(b);
}

function emptyStep(phase: StepLog["phase"], round: number): StepLog {
  return { phase, round, calls: [], events: [] };
}

class EbdStrategy implements ResearchStrategy<EbdState> {
  readonly name = "ebd";

  /** Request analyses of a run that left nothing usable, by run ID (section 24.4). */
  private readonly unusable = new Map<string, number>();

  private readonly options: EbdOptions;

  constructor(options: EbdOptions) {
    // Section 28: the main parts of an environment plan come with their key questions written in
    // full, so a brief always asks them one by one, as `partQuestions` does for life-cycle steps.
    this.options = options.init === "environment" ? { ...options, partQuestions: true } : options;
  }

  /**
   * Section 28 (`init: "environment"`): the whole first plan in one call. The reply becomes the same
   * structures the other modes build in three calls: the analysis, the claims taken as given, and the
   * environment map with one goal per main part of the answer.
   */
  private async initFromEnvironment(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<EbdState>> {
    const out = await runEnvironmentAnalysis(ctx.model, input.question, ctx.today);
    const plan = out.value;
    const faults = (out.calls.at(-1)?.errors ?? []).map((e) => e.message).join("; ").slice(0, 300);
    // As in the other modes (section 24.4): the first time a run gets no usable plan, init throws and
    // the skeleton runs the step again; the second time the plan is the request itself as one question.
    if (!plan) {
      const failures = (this.unusable.get(ctx.runId) ?? 0) + 1;
      this.unusable.set(ctx.runId, failures);
      if (failures === 1) throw new Error(`Environment analysis produced no usable plan: ${faults}`);
    }
    const a = plan ? analysisFromPlan(plan, input.question) : minimalAnalysis(input.question, ctx.today);
    const step = emptyStep("init", 0);
    step.calls = out.calls;
    const state: EbdState = {
      question: input.question,
      today: ctx.today,
      init: { mode: "environment", accepted: out.accepted, fallback: out.fallback || !plan, attempts: out.calls.length, stopReason: !plan ? "minimal plan" : out.accepted ? "accepted" : "attempts exhausted" },
      analysis: a,
      goals: goalsFromAnalysis(a),
      objectsFound: [],
      map: null,
      conflicts: [],
      evidence: [],
      results: [],
      roundsObserved: 0,
      extraRoundServed: false,
      stop: null,
      tree: treeMetrics([]),
      step,
      problems: !plan
        ? [`environment analysis gave no usable plan twice in this run (${faults}); the plan is the request itself as one question, with no main parts and no check of its claims`]
        : out.fallback
          ? [`environment analysis fell back to its valid parts after ${out.calls.length} attempts: ${faults}`]
          : [],
    };
    if (a.status === "out_of_scope") {
      state.stop = { kind: "out_of_scope", round: 0, reason: a.status_reason ?? "out of scope" };
      state.tree = treeMetrics(state.goals);
      return { state, decision: { briefs: [], stop: true, rationale: `Environment analysis (one call, ${out.calls.length} attempt(s)).
Out of scope: ${a.status_reason ?? ""}` } };
    }
    const added = plan ? applyPlan(state, plan, (line) => step.events.push(line)) : [];
    state.tree = treeMetrics(state.goals);
    const given = givenClaims(state);
    const toVerify = a.assumptions.filter((x) => !given.has(x.id));
    const taken = a.assumptions.filter((x) => given.has(x.id));
    const notStated = state.plan?.notStated ?? [];
    const intro = [
      plan
        ? `Environment analysis (one call, ${out.accepted ? "accepted" : "fallback"} after ${out.calls.length} attempt(s)): ${added.length} main part(s) of the answer with ${state.map!.events.reduce((n, e) => n + e.parts.length, 0)} key questions, ${a.assumptions.length} claim(s) of the question.`
        : "Environment analysis gave no usable plan, so the request itself is the plan.",
      state.map ? mapSummary(state.map) : "",
      toVerify.length ? `Claims to check: ${toVerify.map((x) => `${x.id} ${x.claim}`).join(" ")}` : "No claim to check.",
      taken.length ? `Taken as given, because they only restate what the question asks about: ${taken.map((x) => `${x.id} ${x.claim}`).join(" ")} The evidence can still overrule them.` : "",
      notStated.length ? `Not stated by the client: ${notStated.join(" ")}` : "",
    ].filter(Boolean);
    return this.plan(state, ctx, intro, null);
  }

  async init(input: { question: string }, ctx: StrategyContext): Promise<StrategyStep<EbdState>> {
    if (this.options.init === "environment") return this.initFromEnvironment(input, ctx);
    const args = { question: input.question, today: ctx.today, model: ctx.model };
    const out = this.options.init === "agent" ? await runAgentAnalysis(args) : await runFixedAnalysis(args);
    // Section 24.4: the first time a run's request analysis leaves nothing usable, init throws as
    // before, so the skeleton runs the whole step again (section 5.3). When that happens a second time
    // in the same run, the plan is the request itself as one question, and the record says so: a
    // request in scope always gets a plan.
    const minimal = !out.analysis;
    const faults = out.errors.map((e) => e.message).join("; ").slice(0, 300);
    if (minimal) {
      const failures = (this.unusable.get(ctx.runId) ?? 0) + 1;
      this.unusable.set(ctx.runId, failures);
      if (failures === 1) throw new Error(`Request analysis (${out.mode}) produced no usable analysis: ${faults}`);
    }
    const a = out.analysis ?? minimalAnalysis(input.question, ctx.today);
    const step = emptyStep("init", 0);
    step.calls = analysisCalls(out, input.question, ctx.today);
    const state: EbdState = {
      question: input.question,
      today: ctx.today,
      init: { mode: out.mode, accepted: out.accepted, fallback: out.fallback || minimal, attempts: out.attempts, stopReason: minimal ? "minimal plan" : out.stopReason },
      analysis: a,
      goals: goalsFromAnalysis(a),
      objectsFound: [],
      map: null,
      conflicts: [],
      evidence: [],
      results: [],
      roundsObserved: 0,
      extraRoundServed: false,
      stop: null,
      tree: treeMetrics([]),
      step,
      problems: minimal
        ? [`request analysis gave no usable plan twice in this run (${faults}); the plan is the request itself as one question, with no model of the request and no check of its assumptions`]
        : out.fallback
          ? [`request analysis fell back after ${out.attempts} attempts: ${faults}`]
          : [],
    };
    state.tree = treeMetrics(state.goals);
    const head = `Request analysis (${out.mode} mode, ${out.accepted ? "accepted" : minimal ? "nothing usable, so the request itself is the plan," : "fallback"} after ${out.attempts} attempt(s)): ${a.rom.objects.length} objects, ${a.assumptions.length} assumptions, ${state.goals.length} search goals, ${a.questions.length - state.goals.length} synthesis questions.`;
    if (a.status === "out_of_scope") {
      state.stop = { kind: "out_of_scope", round: 0, reason: a.status_reason ?? "out of scope" };
      return { state, decision: { briefs: [], stop: true, rationale: `${head}\nOut of scope: ${a.status_reason ?? ""}` } };
    }
    // Section 27: before any search, sort the claims the question takes for granted into those to check
    // and those taken as given. Without a usable reply every claim is checked, as before.
    if (this.options.premiseSort && a.assumptions.length) {
      const sorted = await runPremiseSort(ctx.model, state);
      step.calls.push(...sorted.calls);
      if (sorted.value) recordSort(state, sorted.value, (line) => step.events.push(line));
      else state.problems.push("premise sort gave no usable reply; every claim of the question is checked");
    }
    // Section 19: problem extension. Without a usable reply the plan stays the request analysis's own.
    let extended = "";
    if (this.options.extend) {
      const ext = await runExtension(ctx.model, state, this.options.completeMap);
      step.calls.push(...ext.calls);
      if (ext.value) {
        if (ext.fallback) state.problems.push("problem extension fell back to its valid events; no planned question was replaced");
        const added = applyExtension(state, ext.value, (line) => step.events.push(line));
        state.tree = treeMetrics(state.goals);
        extended = `Problem extension: ${added.length} life-cycle event goals. ${mapSummary(state.map!)}`;
      } else {
        state.problems.push("problem extension gave no usable reply; the plan is the request analysis's own");
        extended = "Problem extension gave no usable reply.";
      }
    }
    // Section 27: after the extension, so that a question that stops being a check can stand beside the life-cycle steps.
    const freed = applyGiven(state, (line) => step.events.push(line));
    if (freed.length) state.tree = treeMetrics(state.goals);
    const given = givenClaims(state);
    const toVerify = a.assumptions.filter((x) => !given.has(x.id));
    const taken = a.assumptions.filter((x) => given.has(x.id));
    const central = a.rom.objects.filter((o) => a.rom.central_object_ids.includes(o.id)).map((o) => `"${o.text}"`);
    const intro = [
      head,
      extended,
      `Central objects: ${central.join(", ") || "none"}.`,
      toVerify.length ? `Assumptions to verify: ${toVerify.map((x) => `${x.id} ${x.claim}`).join(" ")}` : "No assumptions to verify.",
      taken.length ? `Taken as given, because they only restate what the question asks about: ${taken.map((x) => `${x.id} ${x.claim}`).join(" ")} The evidence can still overrule them.` : "",
    ].filter(Boolean);
    return this.plan(state, ctx, intro, null);
  }

  async observe(previous: EbdState, arrived: ResearchResult[], ctx: StrategyContext): Promise<StrategyStep<EbdState>> {
    const state = structuredClone(previous);
    // Lab 5 review, change 4: the agents read the results in brief order, never in arrival order.
    const results = [...arrived].sort((a, b) => byBrief(a.brief.id, b.brief.id));
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
        if (record.status === "failed") g.failedAttempts += 1;
        g.servedRounds.push(round);
      }
    }
    state.roundsObserved = round;
    const anyFailed = results.some((r) => r.status === "failed");
    const failedOnly = new Set(results.filter((r) => r.status === "failed").flatMap((r) => readResult(r).record.goalIds));
    for (const r of results.filter((x) => x.status === "ok")) for (const id of readResult(r).record.goalIds) failedOnly.delete(id);
    const settledNow: string[] = [];
    for (const id of failedOnly) {
      const g = state.goals.find((x) => x.id === id);
      if (!g || isSettled(g)) continue;
      const how = requeueOrExhaust(g, round, this.options.maxAttempts, null);
      if (how === "exhausted" && g.need === "necessary") settledNow.push(g.id);
      log(`${id}: researcher failed → ${how}`);
      if (how === "exhausted" && g.failedAttempts >= g.attempts) state.problems.push(`round ${round}: ${id} ran out of attempts because its researchers failed`);
    }

    // Section 9: conflicts, before the round analyst.
    let newConflicts = 0;
    if (this.options.conflicts && fresh.some((e) => e.kind === "finding")) {
      const checked = await runConflictChecker(ctx.model, state, fresh, asksCritical(this.options), this.options.strictFollowUp);
      step.calls.push(...checked.calls);
      if (checked.fallback) state.problems.push(`round ${round}: conflict checker fell back to its valid items`);
      if (checked.value) newConflicts = applyConflicts(state, checked.value, round, this.options, log).length;
      else if (!checked.accepted) state.problems.push(`round ${round}: conflict checker gave no usable reply`);
    }

    // Section 10: judgments and new goals.
    const served = servedGoals(state, round).filter((g) => !isSettled(g) && !failedOnly.has(g.id));
    let progress: RoundProgress = { settled: settledNow, advanced: [], newConflicts, newNecessary: 0, anyFailed };
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
    if (this.options.conflicts) resolveClaimChecks(state, round, this.options, log);
    for (const line of releaseWaiting(state, round)) log(line);
    const mooted = mootDependents(state, round);
    if (mooted.length) log(`moot after a contradicted premise: ${mooted.join(", ")}`);
    // Section 9: a settle goal stays necessary only while it decides a claim or a goal waits for it.
    settlePriority(state, log, this.options.focusFollowUp);
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
    return buildSynthesis(state, this.options);
  }

  /** Section 11 stop rules, then sections 6 and 7: rank the ready goals and pack them into briefs. */
  private plan(state: EbdState, ctx: StrategyContext, lines: string[], progress: RoundProgress | null): StrategyStep<EbdState> {
    const log = (line: string) => state.step.events.push(line);
    // A necessary goal that ended only through researcher failures was never researched, so the run
    // is not complete on EBD's own terms (live failure test, 2026-11-05).
    const stopOf = (stopKind: "complete" | "saturated", stopReason: string): NonNullable<EbdState["stop"]> => {
      const failed = state.goals.filter((g) => g.need === "necessary" && endedByFailures(g)).map((g) => g.id);
      if (stopKind !== "complete" || !failed.length) return { kind: stopKind, round: state.roundsObserved, reason: stopReason };
      return { kind: "researcher_failures", round: state.roundsObserved, reason: `every necessary goal is settled, but ${failed.join(", ")} ended only because their researchers failed` };
    };
    const done = (stopKind: "complete" | "saturated", stopReason: string): StrategyStep<EbdState> => {
      const next = stopOf(stopKind, stopReason);
      const { kind, reason } = next;
      state.stop = state.stop?.kind === kind ? state.stop : next;
      log(`stop: ${kind} (${reason})`);
      return { state, decision: { briefs: [], stop: true, rationale: [...lines, `Stop: ${kind}. ${reason}.`].join("\n") } };
    };

    let ranked = rankReady(state, this.options);
    // Section 20: a replaced question is not served once its event goals have been researched.
    if (this.options.focusFollowUp) {
      const superseded = ranked.filter((r) => isSuperseded(state, r.goal)).map((r) => r.goal.id);
      if (superseded.length) {
        ranked = ranked.filter((r) => !superseded.includes(r.goal.id));
        log(`not served: ${superseded.join(", ")}, because the event goals that replaced ${superseded.length > 1 ? "them" : "it"} have been researched`);
      }
    }
    if (progress) {
      const complete = isComplete(state);
      if (complete.complete) {
        const completing = ranked.filter((r) => r.goal.need === "completing");
        // Section 29: with `strictFollowUp` a complete run stops; no round is spent on details.
        const mainOnly = this.options.focusFollowUp && this.options.strictFollowUp;
        // Section 30: a main part of the plan that no researcher has been asked about is not a detail.
        const unasked = mainOnly ? completing.filter((r) => isUnaskedPart(state, r.goal)) : [];
        if (!mainOnly && this.options.extraRound && !state.extraRoundServed && completing.length && ctx.budget.researchersRemaining > 0) {
          state.extraRoundServed = true;
          state.stop = stopOf("complete", complete.reason);
          log("complete; one extra round serves completing goals");
          ranked = completing;
          lines = [...lines, "Complete: every necessary goal is settled. One extra round serves completing goals."];
        } else if (unasked.length && ctx.budget.researchersRemaining > 0) {
          state.stop = stopOf("complete", complete.reason);
          log(`every necessary goal is settled; ${unasked.map((r) => r.goal.id).join(", ")} of the plan has not been asked yet and gets a researcher`);
          ranked = unasked;
          lines = [...lines, `Every necessary goal is settled. A main part of the plan that no researcher was asked about is served: ${unasked.map((r) => r.goal.id).join(", ")}.`];
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

    // Section 20: in a follow-up round with focusFollowUp, the researchers go to the necessary goals
    // first, one goal each while researchers last. A brief of completing goals is added only for a
    // researcher that no necessary goal can use, so a detail never shares the researcher sent for a main
    // part. In the recorded runs follow-up briefs held up to three goals, and the necessary one among
    // them often ended with nothing found (Lab 4 flight run, section 9; batch of 2026-11-11).
    const apart = this.options.focusFollowUp && state.roundsObserved > 0;
    // Section 25 (decided on 2026-11-18): in a follow-up round a missing part of the answer comes
    // before a disagreement. The goals that settle a disagreement leave the first pass and are served
    // with the researchers that the necessary goals for content leave free, one settle goal to a
    // researcher, before any completing goal. A settle goal that a part of the answer waits behind
    // stays in the first pass. In the 12 runs on new questions of 2026-11-18, 9 of the 20 follow-up
    // researchers went to a settle goal, 6 of the 9 settled nothing, and parts of the answer stayed unserved.
    const settling = apart && this.options.mainPartsFirst ? ranked.map((r) => r.goal).filter((g) => g.need === "necessary" && g.settles && !gatesAnswer(g, state, this.options)) : [];
    // Section 29 (`strictFollowUp`): after the first round a researcher goes only to a main part of the
    // answer or to a claim of the question. A completing goal is never served in a follow-up round. In
    // the live run of 2026-11-19 every planned part was answered in round 1, and the sixth researcher
    // went to a completing goal raised from a gap (how the telephone changed news gathering).
    // Section 30: a main part of the plan that no researcher has been asked about is not such a detail.
    const strict = apart && this.options.strictFollowUp;
    const first = apart ? ranked.filter((r) => (r.goal.need === "necessary" || (strict && isUnaskedPart(state, r.goal))) && !settling.includes(r.goal)) : ranked;
    if (strict && !first.length && !settling.length) {
      return done("saturated", "no main part of the answer and no claim of the question is left to research, and details are not researched after the first round");
    }
    // Section 21: with partQuestions, a necessary goal gets a researcher before a brief of completing goals does.
    // Section 27 (option `stepsFirst`): a researcher that would sit idle goes to a life-cycle step first.
    const stepsFirst = this.options.stepsFirst;
    const regroup = this.options.partQuestions
      ? { within: this.options.questionsPerBrief, load: (g: Selection["groups"][number]) => questionCount(g, state, this.options), ...(stepsFirst ? { step: (g: Goal) => eventOf(state, g) !== null } : {}) }
      : null;
    const allocate = (candidates: typeof first, view: EbdState) => {
      const picked = selectWithReserve(candidates, view, ctx.budget.researchersRemaining, this.options);
      // Lab 5 review, change 3: researchers that would sit idle this round take goals out of shared briefs.
      const room = ctx.budget.researchersRemaining - picked.researchersKept;
      const most = Math.min(this.options.maxPerRound, room);
      return { picked, room, most, spreadGroups: this.options.spread ? spread(picked.groups, most, room, regroup) : picked.groups };
    };
    // Section 27 (option `stepsFirst`): in the first round a planned question that the life-cycle steps
    // stand in for only rides along: a question the steps replaced (section 19), or one that stopped
    // being a check because its claims are taken as given. The briefs are made without it, and it joins
    // one that has room. Planned like any goal, such a question could take a researcher to itself with
    // one key question while two steps shared one (replays of 2026-11-19, the back-pain plan).
    const replaced = state.map?.replaced ?? {};
    const standIns = stepsFirst && state.roundsObserved === 0 ? first.filter((r) => r.goal.origin.type === "request" && r.goal.need === "completing" && Boolean(replaced[r.goal.id])).map((r) => r.goal) : [];
    const riders = standIns.length && first.some((r) => !standIns.includes(r.goal)) ? standIns : [];
    const main = riders.length ? first.filter((r) => !riders.includes(r.goal)) : first;
    let allocation = allocate(main, state);
    // Section 30: the first round of a plan of key questions. Every researcher of the round goes to a
    // main part of the answer, the necessary parts first, and none is kept for a second try; the check
    // of the claims leads a brief on a necessary part, and a completing part that has no brief is
    // asked as one question where a brief has room.
    let ownPlan = false;
    if (state.roundsObserved === 0 && state.map?.questions && this.options.spread) {
      const goals = main.map((r) => r.goal);
      const checks = goals.filter(isClaimCheck);
      const parts = goals.filter((g) => eventOf(state, g) !== null);
      const most = Math.min(this.options.maxPerRound, ctx.budget.researchersRemaining);
      if (parts.length && parts.length + checks.length === goals.length && most > 0) {
        const dealt = partsFirst(parts, most);
        let groups = dealt.groups;
        if (checks.length) {
          const shared = shareChecks(groups, checks, state, this.options);
          if (shared) {
            groups = shared;
          } else {
            // No brief has room for one more key question. The check is still asked first: it leads the
            // brief that asks the fewest key questions, whose parts may then be asked as one question each.
            groups = groups.map((g) => ({ key: g.key, goals: [...g.goals] }));
            const target = [...groups].sort((a, b) => questionCount(a, state, this.options) - questionCount(b, state, this.options))[0]!;
            target.goals.unshift(...checks);
            log(`no brief has room for one more key question: claim check(s) ${checks.map((g) => g.id).join(", ")} lead the brief ${target.goals.filter((g) => !checks.includes(g)).map((g) => g.id).join(", ")} all the same`);
          }
          log(`claim check(s) ${checks.map((g) => g.id).join(", ")} asked in a brief that asks for content, with no researcher of their own`);
        }
        const joined = shareRiders(groups, dealt.riders, state, this.options);
        ownPlan = true;
        allocation = { picked: { groups: joined.groups, reserve: null, held: [], reservedFor: [], researchersKept: 0, released: false }, room: ctx.budget.researchersRemaining, most, spreadGroups: joined.groups };
        const holdSeveral = joined.groups.filter((g) => g.goals.filter((x) => parts.includes(x)).length > 1).length;
        log(`first round of the plan: ${joined.groups.length} researcher(s) for ${parts.length} main part(s)${holdSeveral ? `; ${holdSeveral} brief(s) hold more than one part, because the round has fewer researchers than the plan has parts` : ""}`);
        const placed = dealt.riders.filter((g) => !joined.waiting.includes(g)).map((g) => g.id);
        if (placed.length) log(`${placed.join(", ")} asked as one question in the brief of a necessary part: the round has no researcher left for ${placed.length > 1 ? "them" : "it"}`);
        if (joined.waiting.length) log(`${joined.waiting.map((g) => g.id).join(", ")} not asked this round: no researcher is left, and no brief has room for one more key question`);
      }
    }
    // Section 26 (option `premiseRides`): in the first round a goal that only checks a claim of the
    // question is asked in the brief of a necessary goal that asks for content, and takes no researcher
    // of its own. It is still asked in round 1 (`premiseFirst`). In the 17 saved runs with the five
    // options, 10 of the 68 first-round researchers served only such a check, and 7 of the 10 confirmed
    // a claim that restates the question ("Slavery was important", for "why was slavery important").
    if (!ownPlan && this.options.premiseRides && state.roundsObserved === 0) {
      const checks = main.filter((r) => isClaimCheck(r.goal)).map((r) => r.goal);
      const content = main.filter((r) => !isClaimCheck(r.goal));
      if (checks.length && content.some((r) => r.goal.need === "necessary")) {
        // The checks are served this round, so no researcher is kept back for them.
        const trial = allocate(content, { ...state, goals: state.goals.filter((g) => !checks.includes(g)) });
        const shared = shareChecks(trial.spreadGroups, checks, state, this.options);
        if (shared) {
          allocation = { ...trial, spreadGroups: shared };
          log(`claim check(s) ${checks.map((g) => g.id).join(", ")} asked in a brief that asks for content, with no researcher of their own`);
        } else {
          log(`claim check(s) ${checks.map((g) => g.id).join(", ")} keep a researcher of their own: no brief that asks for content has room for one more key question`);
        }
      }
    }
    const selection = allocation.picked;
    const { reserve, held, reservedFor, researchersKept, released } = selection;
    const free = allocation.room;
    const slots = allocation.most;
    let groups = allocation.spreadGroups;
    if (groups.length > selection.groups.length) log(`spread over ${groups.length} brief(s) instead of ${selection.groups.length}: researchers would otherwise sit idle`);
    else if (this.options.spread && groups.some((g, i) => g.goals.length !== selection.groups[i]?.goals.length)) log("briefs regrouped: completing goals share a researcher, so that each necessary goal has one");
    if (riders.length) {
      const joined = shareRiders(groups, riders, state, this.options);
      groups = joined.groups;
      const placed = riders.filter((g) => !joined.waiting.includes(g)).map((g) => g.id);
      if (placed.length) log(`${placed.join(", ")} asked along in a brief with room: the life-cycle steps stand in for ${placed.length > 1 ? "them" : "it"}, so no researcher of ${placed.length > 1 ? "their" : "its"} own`);
      if (joined.waiting.length) log(`${joined.waiting.map((g) => g.id).join(", ")} not asked this round: the life-cycle steps stand in for ${joined.waiting.length > 1 ? "them" : "it"}, and no brief has room for one more key question`);
    }
    if (settling.length && groups.length < slots) {
      const later = pack(settling, { maxPerRound: slots - groups.length, questionsPerBrief: 1 });
      groups = [...groups, ...later];
      log(`${later.length} brief(s) to settle a disagreement, for researchers that no missing part of the answer can use this round`);
    }
    if (apart && !strict && groups.length < slots) {
      const completing = pack(ranked.filter((r) => r.goal.need !== "necessary").map((r) => r.goal), { ...this.options, maxPerRound: slots - groups.length });
      if (completing.length) {
        groups = [...groups, ...completing];
        log(`${completing.length} brief(s) of completing goals, for researchers that no necessary goal can use this round`);
      }
    }
    // Section 21: a completing goal waits when it keeps a necessary goal of its brief from being asked part by part.
    const fitted = groups.map((g) => fitBrief(g, state, this.options));
    const left = fitted.flatMap((f) => f.left);
    if (left.length) {
      groups = fitted.map((f) => f.group);
      log(`left for a later round: ${left.map((g) => g.id).join(", ")}, so that the necessary goal sharing the brief is asked part by part`);
    }
    const briefs = groups.map((g, i) => briefFor(g, i, state, this.options));
    const decision: Decision = { briefs, stop: false, rationale: "" };
    const served = groups.flatMap((g) => g.goals);
    const why = served.map((g) => {
      const r = ranked.find((x) => x.goal.id === g.id)!;
      return `${g.id} (level ${g.level} ${g.kind}${r.reach ? `, reach ${r.reach}` : ""}${g.id === reserve ? ", reserve slot" : ""})`;
    });
    const waiting = ranked.filter((r) => !served.includes(r.goal)).map((r) => r.goal.id);
    const settleWaits = settling.filter((g) => !served.includes(g)).map((g) => g.id);
    const settleNote = settleWaits.length ? `Settling a disagreement waits (${settleWaits.join(", ")}): the researchers of this round go first to the parts of the answer that are still missing.` : "";
    if (settleWaits.length) log(`settle goals wait: ${settleWaits.join(", ")}; the researchers of this round go first to the missing parts of the answer`);
    // With nothing reserved, held goals lost to briefs that carry request goals (GPU rerun, 2026-10-21).
    // Without a researcher kept, the held goals simply did not fit in the budget (live round of 2026-11-05:
    // the rationale called a goal beyond the last researcher "held back for first tries").
    const protectedFirst = groups.some((g) => g.goals.some(isPlanned));
    const heldWhy = researchersKept
      ? `${researchersKept} researcher(s) kept for ${reservedFor.map((g) => g.id).join(", ")}`
      : protectedFirst
        ? "the researchers left go to briefs with request goals"
        : "no researcher is left for them this round";
    const heldLabel = researchersKept || protectedFirst ? "Held back for first tries" : "Not served for lack of researchers";
    const heldNote = held.length ? `${heldLabel}: ${held.map((g) => g.id).join(", ")} (${heldWhy}).` : "";
    if (held.length) log(`${heldLabel.toLowerCase()}: ${held.map((g) => g.id).join(", ")}; ${heldWhy}`);
    if (released) log("first-try reserve released: no other brief can be served this round");
    const budgetNote = ctx.budget.researchersRemaining === 0 ? "No researcher budget is left; these briefs record the unmet demand." : "";
    if (ctx.budget.researchersRemaining === 0) {
      state.stop = state.stop ?? { kind: "budget", round: state.roundsObserved, reason: "researchersRemaining is 0" };
      log("budget exhausted: returning the wanted briefs with stop: false");
    }
    log(`serve ${briefs.length} brief(s): ${briefs.map((b) => b.tag).join(" | ")}${waiting.length ? `; ready but waiting: ${waiting.join(", ")}` : ""}`);
    decision.rationale = [...lines, `Next: ${briefs.length} brief(s) serving ${why.join(", ")}.`, waiting.length ? `Ready but not served this round: ${waiting.join(", ")}.` : "", settleNote, heldNote, budgetNote]
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
