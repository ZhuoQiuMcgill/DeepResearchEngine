/**
 * Problem extension (design section 19) without network: the checks of an extension reply, the
 * environment map and its goals, and the ways the evidence overwrites an assumed part.
 */
import { describe, expect, it } from "vitest";
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { buildResearchGraph, initialState, type DecisionRecord } from "../../graph/skeleton.js";
import { briefFor, pack, spread } from "./briefs.js";
import { EXTENSION_SYSTEM, applyExtension, checkExtension, extensionMessage, validEvents, type ExtensionReply } from "./extension.js";
import { goalsFromAnalysis, isComplete, rankReady, treeMetrics } from "./goals.js";
import ebd from "./index.js";
import { parseOptions } from "./options.js";
import { EXAMPLES } from "./request/examples.js";
import { ANALYST_MAP_SECTION, ANALYST_SYSTEM, analystMessage, analystSystem, applyJudgments, checkRound, type RoundReply } from "./rounds/analyst.js";
import { CONFLICT_SYSTEM, applyConflicts, checkConflicts, conflictMessage, conflictSystem, settlePriority } from "./rounds/conflicts.js";
import { readResult } from "./rounds/evidence.js";
import type { EbdState } from "./state.js";
import { buildGuidance } from "./synthesis.js";

const E2 = EXAMPLES[1]!;
const options = parseOptions({ extend: true });

function stateOf(): EbdState {
  const analysis = structuredClone(E2.analysis);
  const goals = goalsFromAnalysis(analysis);
  return {
    question: E2.request,
    today: E2.runDate,
    init: { mode: "fixed", accepted: true, fallback: false, attempts: 1, stopReason: "accepted" },
    analysis,
    goals,
    objectsFound: [],
    map: null,
    conflicts: [],
    evidence: [],
    results: [],
    roundsObserved: 0,
    extraRoundServed: false,
    stop: null,
    tree: treeMetrics(goals),
    step: { phase: "init", round: 0, calls: [], events: [] },
    problems: [],
  };
}

/** The extension of the prompt's worked example, so the example itself is checked. */
function exampleReply(): ExtensionReply {
  const json = /^(\{"subject".*\})$/m.exec(EXTENSION_SYSTEM)?.[1];
  if (!json) throw new Error("the worked example's extension was not found in the prompt");
  return JSON.parse(json) as ExtensionReply;
}

function extended(): EbdState {
  const state = stateOf();
  applyExtension(state, exampleReply(), () => {});
  return state;
}

function serve(state: EbdState, tag: string, findings: string[], id = "r1-b1"): void {
  const round = Number(id.slice(1, 2));
  const brief: ResearchBrief = { id, round, objective: "o", keyQuestions: [`[${tag}] q`], constraints: [], sourceHints: [], tag };
  const notes = [`## [${tag}] q`, "### Cited Findings", ...findings.map((f, i) => `- ${f} — [S](https://host${i}.example/x)`), "### Gaps", "- Nothing else."].join("\n");
  const result: ResearchResult = { brief, status: "ok", notes, sources: [], queries: [], usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [] };
  const { record, evidence } = readResult(result);
  state.results.push(record);
  state.evidence.push(...evidence);
  const goal = state.goals.find((g) => g.id === tag)!;
  goal.attempts += 1;
  goal.servedRounds.push(round);
  state.roundsObserved = round;
}

describe("the extension reply", () => {
  it("accepts the prompt's worked example", () => {
    const checked = checkExtension(exampleReply(), stateOf());
    expect(checked.errors).toEqual([]);
    expect(checked.warnings).toEqual([]);
  });

  it("gives the analyst the planned questions and what each checks", () => {
    const message = extensionMessage(stateOf());
    expect(message).toContain("Q1 [necessary; checks no assumption]");
    expect(message).toContain("Q3 Which electric car is best");
  });

  it("rejects a name the request does not mention, a reference to another question and too few parts", () => {
    const reply = exampleReply();
    reply.events[0]!.question = "What does buying a Tesla involve?";
    reply.events[1]!.question = "How do the cars identified in Q1 perform in the cold?";
    reply.events[2]!.parts = reply.events[2]!.parts.slice(0, 1);
    const errors = checkExtension(reply, stateOf()).errors;
    expect(errors.map((e) => e.path)).toEqual(["events[0]", "events[1]", "events[2]"]);
    expect(errors[0]!.message).toContain("Tesla");
    // The fallback needs two valid events.
    expect(validEvents(reply, errors)).toBeNull();
  });

  it("falls back to the valid events, dropping only the part that names something", () => {
    const reply = exampleReply();
    reply.events[0]!.question = "What does buying a Tesla involve?";
    reply.events[1]!.parts[2]!.text = "traction tests at the Arctic Circle";
    const checked = checkExtension(reply, stateOf());
    expect(checked.errors.map((e) => e.path)).toEqual(["events[0]", "events[1].parts[2]"]);
    const kept = validEvents(checked.value!, checked.errors)!;
    // The event whose question names a maker goes; the other keeps its four clean parts. Nothing is replaced.
    expect(kept.events.map((e) => [e.name, e.parts.length])).toEqual([["Driving in the cold", 4], ["Charging in winter", 4], ["Owning over the years", 4]]);
    expect(kept.replaces).toEqual([]);
  });

  it("cuts an event with too many parts instead of rejecting it", () => {
    const reply = exampleReply();
    reply.events[1]!.parts = [...reply.events[1]!.parts, { text: "tyre wear", kind: "economic" }, { text: "battery heating time", kind: "natural" }];
    const checked = checkExtension(reply, stateOf());
    expect(checked.errors).toEqual([]);
    expect(checked.warnings.map((w) => w.message)).toEqual(["7 parts; the first 6 are kept"]);
    expect(checked.value!.events[1]!.parts).toHaveLength(6);
  });

  it("warns about a planned question that cannot be replaced", () => {
    const state = stateOf();
    state.analysis = structuredClone(EXAMPLES[0]!.analysis);
    const reply = { ...exampleReply(), replaces: ["Q1", "Q3"] };
    const checked = checkExtension(reply, { question: EXAMPLES[0]!.request, analysis: state.analysis });
    // E1's Q1 checks the assumption A1; its Q3 checks none.
    expect(checked.warnings.map((w) => w.message).join()).toContain("Q1 cannot be replaced");
  });
});

describe("the environment map", () => {
  it("makes one goal per event, replaces the whole-subject question and rewires what waited for it", () => {
    const state = extended();
    const map = state.map!;
    expect(map.events.map((e) => [e.id, e.name, e.goalId])).toEqual([["E1", "Buying", "Q4"], ["E2", "Driving in the cold", "Q5"], ["E3", "Charging in winter", "Q6"], ["E4", "Owning over the years", "Q7"]]);
    expect(map.replaced).toEqual({ Q1: ["Q4", "Q5", "Q6", "Q7"] });
    // The replaced question stays, as a completing goal: the events are assumptions and may not carry all it asked.
    expect(state.goals.map((g) => g.id)).toEqual(["Q1", "Q2", "Q4", "Q5", "Q6", "Q7"]);
    expect(state.goals.find((g) => g.id === "Q1")).toMatchObject({ need: "completing", level: 4, origin: { type: "request" } });
    expect(state.goals.find((g) => g.id === "Q2")!.dependsOn).toEqual(["Q4", "Q5", "Q6"]);
    const q7 = state.goals.find((g) => g.id === "Q7")!;
    expect(q7).toMatchObject({ need: "completing", level: 4, origin: { type: "assumed", event: "E4" }, leadsTo: ["Q3"], partsTotal: 4, partsMet: 0 });
    expect(map.events.flatMap((e) => e.parts).every((p) => p.origin === "assumed" && p.status === "assumed")).toBe(true);
    // Width first: each necessary event goal opens the first round with its own researcher, and the
    // replaced question shares the fourth with the completing event.
    expect(rankReady(state, options).map((r) => r.goal.id)).toEqual(["Q4", "Q5", "Q6", "Q1", "Q7"]);
    expect(spread(pack(rankReady(state, options).map((r) => r.goal), options), 4, 6).map((g) => g.goals.map((x) => x.id))).toEqual([["Q4"], ["Q1", "Q7"], ["Q6"], ["Q5"]]);
  });

  it("keeps at most four necessary events and never replaces a question that checks a client assumption", () => {
    const state = stateOf();
    state.analysis.questions[0]!.verifies = ["A1"];
    const reply = exampleReply();
    reply.events.push({ ...reply.events[0]!, name: "Selling" }, { ...reply.events[0]!, name: "Importing" });
    for (const e of reply.events) e.need = "necessary";
    applyExtension(state, reply, () => {});
    expect(state.goals.filter((g) => g.origin.type === "assumed").map((g) => g.need)).toEqual(["necessary", "necessary", "necessary", "necessary", "completing", "completing"]);
    expect(state.map!.replaced).toEqual({});
    expect(state.goals.some((g) => g.id === "Q1")).toBe(true);
  });

  it("tells the researcher that the parts are expectations the sources decide", () => {
    const state = extended();
    const brief = briefFor({ key: "O2", goals: [state.goals.find((g) => g.id === "Q5")!] }, 0, state);
    expect(brief.instructions).toContain("look for what the sources report on: driving range lost at low temperatures;");
    expect(brief.instructions).toContain("not facts");
    expect(brief.instructions).not.toContain("a sufficient answer contains");
  });
});

describe("the evidence overwrites the plan", () => {
  const judgment = (parts: RoundReply["judgments"][number]["parts"], outcome: RoundReply["judgments"][number]["outcome"] = "partial"): RoundReply => ({
    judgments: [{ goal_id: "Q6", parts, outcome, verdicts: [], missing: [] }],
    proposals: [],
  });

  it("adds the map section to the prompts only when the run has a map", () => {
    expect(analystSystem(false)).toBe(ANALYST_SYSTEM);
    expect(analystSystem(true)).toContain(ANALYST_MAP_SECTION);
    expect(conflictSystem(false)).toBe(CONFLICT_SYSTEM);
    expect(conflictSystem(true)).toContain("evidence_vs_plan");
    expect(CONFLICT_SYSTEM).not.toContain("evidence_vs_plan");
  });

  it("asks for a judgment of each planned part by its ID", () => {
    const state = extended();
    serve(state, "Q6", ["Charging slows below freezing.", "No preconditioning exists on these cars."]);
    const q6 = state.goals.find((g) => g.id === "Q6")!;
    expect(analystMessage(state, 1, [q6], options)).toContain("Judge only: M10, M11, M12, M13");
    const bad = checkRound(judgment([{ part: "charging is slow", met: true, evidence: ["r1-b1-f1"] }, { part: "M11", met: false, refuted: true, evidence: [] }]), state, [q6]);
    expect(bad.errors.map((e) => e.message).join(" | ")).toMatch(/start part with the ID.*refuted but cites no finding/);
    const good = checkRound(judgment([{ part: "M10 charging speed", met: true, evidence: ["r1-b1-f1"] }, { part: "M11", met: false, refuted: true, correction: "no preconditioning", evidence: ["r1-b1-f2"] }]), state, [q6]);
    expect(good.errors).toEqual([]);
  });

  it("ignores a gap line cited for an unmet part, and an empty field left out of a conflict", () => {
    const state = extended();
    serve(state, "Q6", ["Charging slows below freezing.", "Charging takes twice as long at minus twenty."]);
    const q6 = state.goals.find((g) => g.id === "Q6")!;
    // The gap line (r1-b1-g1) is cited as the reason M13 is unmet, and next to the finding that meets M10.
    const reply = judgment([{ part: "M10", met: true, evidence: ["r1-b1-f1", "r1-b1-g1"] }, { part: "M13", met: false, evidence: ["r1-b1-g1"] }]);
    const checked = checkRound(reply, state, [q6]);
    expect(checked.errors).toEqual([]);
    expect(checked.warnings).toHaveLength(2);
    expect(checked.value!.judgments[0]!.parts.map((p) => p.evidence)).toEqual([["r1-b1-f1"], []]);
    // A gap line alone still cannot meet a part, and without a map the check is the earlier one.
    expect(checkRound(judgment([{ part: "M10", met: true, evidence: ["r1-b1-g1"] }]), state, [q6]).errors[0]!.message).toContain("gap line");
    expect(checkRound(judgment([{ part: "M13", met: false, evidence: ["r1-b1-g1"] }]), { ...state, map: null }, [q6]).errors.length).toBeGreaterThan(0);

    const conflict = { type: "source_vs_source", about: "Q6", statement: "One source says it slows, another that it doubles.", side_a: ["r1-b1-f1"], side_b: ["r1-b1-f2"], settle_by: "A measured test." };
    expect(checkConflicts({ conflicts: [conflict] }, state, state.evidence).errors).toEqual([]);
    expect(checkConflicts({ conflicts: [conflict] }, { ...state, map: null }, state.evidence).value).toBeNull();
  });

  it("confirms, refutes and corrects parts, and settles the goal from the map", () => {
    const state = extended();
    serve(state, "Q6", ["Charging slows below freezing.", "These cars have no preconditioning; owners warm the battery by driving."]);
    const q6 = state.goals.find((g) => g.id === "Q6")!;
    const log: string[] = [];
    applyJudgments(state, judgment([{ part: "M10", met: true, evidence: ["r1-b1-f1"] }, { part: "M11", met: false, refuted: true, correction: "the battery is warmed by driving", evidence: ["r1-b1-f2"] }]), [q6], 1, options, (l) => log.push(l));
    const parts = state.map!.events[2]!.parts;
    // Two of the four parts still planned are confirmed, so the event is researched: the rest is unfound.
    expect(parts.map((p) => [p.id, p.origin, p.status])).toEqual([["M10", "assumed", "confirmed"], ["M11", "assumed", "refuted"], ["M12", "assumed", "unfound"], ["M13", "assumed", "unfound"], ["M18", "found", "confirmed"]]);
    expect(parts[4]).toMatchObject({ text: "the battery is warmed by driving", replaces: "M11", evidence: ["r1-b1-f2"] });
    // The refuted part leaves the plan, and the goal is answered without the floor for checked facts.
    expect(q6).toMatchObject({ status: "answered", partsMet: 2, partsTotal: 4, missing: [] });
    expect(q6.doneWhen).not.toContain("battery preconditioning");
    expect(log.join("\n")).toMatch(/planned part M11[\s\S]*not searched again: M12/);
  });

  it("retries an event only while fewer than half of its parts are confirmed", () => {
    const state = extended();
    const q5 = state.goals.find((g) => g.id === "Q5")!;
    const one = (parts: RoundReply["judgments"][number]["parts"]): RoundReply => ({ judgments: [{ goal_id: "Q5", parts, outcome: "partial", verdicts: [], missing: [] }], proposals: [] });
    serve(state, "Q5", ["Range drops by a third at minus ten degrees."]);
    applyJudgments(state, one([{ part: "M5", met: true, evidence: ["r1-b1-f1"] }]), [q5], 1, options, () => {});
    expect(q5).toMatchObject({ status: "open", partsMet: 1, partsTotal: 5 });
    expect(q5.missing).toHaveLength(4);
    expect(briefFor({ key: "O2", goals: [q5] }, 0, state).keyQuestions[0]).toContain("Still missing: cabin heating system and its energy use;");

    serve(state, "Q5", ["Heat pumps halve the heating load.", "Winter tyres matter more than drive type."], "r2-b1");
    applyJudgments(state, one([{ part: "M6", met: true, evidence: ["r2-b1-f1"] }, { part: "M7", met: true, evidence: ["r2-b1-f2"] }]), [q5], 2, options, () => {});
    expect(q5).toMatchObject({ status: "answered", partsMet: 3, partsTotal: 5, missing: [] });
    expect(state.map!.events[1]!.parts.map((p) => p.status)).toEqual(["confirmed", "confirmed", "confirmed", "unfound", "unfound"]);
  });

  it("does not hold an event open for a disagreement about one fact", () => {
    const state = extended();
    serve(state, "Q6", ["Charging takes 30 minutes in the cold.", "Charging takes 60 minutes in the cold.", "A home charger is needed.", "Public chargers are sparse."]);
    const q6 = state.goals.find((g) => g.id === "Q6")!;
    const conflict = { type: "source_vs_source", about: "Q6", statement: "One source says 30 minutes, another 60.", side_a: ["r1-b1-f1"], side_b: ["r1-b1-f2"], settle_by: "A measured test.", condition: "", claim: "" };
    applyConflicts(state, checkConflicts({ conflicts: [conflict] }, state, state.evidence).value!, 1, options, () => {});
    const settleGoal = state.goals.find((g) => g.settles === "C1")!;
    expect(settleGoal.need).toBe("necessary");
    const all = state.map!.events[2]!.parts.map((p, i) => ({ part: p.id, met: true, evidence: [`r1-b1-f${i + 1}`] }));
    applyJudgments(state, judgment(all, "conflicting"), [q6], 1, options, () => {});
    expect(q6).toMatchObject({ status: "answered", waitingOn: null, partsMet: 4 });
    // No goal waits for the settle goal and it decides no client claim, so it does not hold up the stop.
    settlePriority(state, () => {});
    expect(settleGoal).toMatchObject({ need: "completing", level: 4 });
    expect(isComplete(state).reason).not.toContain("C1");
  });

  it("drops an event whose every part the evidence refutes", () => {
    const state = extended();
    serve(state, "Q6", ["None of this applies."]);
    const q6 = state.goals.find((g) => g.id === "Q6")!;
    const all = state.map!.events[2]!.parts.map((p) => ({ part: p.id, met: false, refuted: true, evidence: ["r1-b1-f1"] }));
    applyJudgments(state, judgment(all), [q6], 1, options, () => {});
    expect(q6.status).toBe("moot");
    expect(buildGuidance(state)).not.toContain("not pursued");
  });

  it("lets a conflict overwrite a planned part of another goal, and keeps it from the writer", () => {
    const state = extended();
    serve(state, "Q5", ["Electric cars are sold without any battery warranty."]);
    expect(conflictMessage(state, state.evidence)).toContain('M14 [Q7, step "Owning over the years"] battery ageing in cold climates');
    const reply = { conflicts: [{ type: "evidence_vs_plan", about: "Q5", statement: "The plan expected battery warranty terms; a finding states there is no battery warranty.", side_a: ["r1-b1-f1"], side_b: ["M15"], settle_by: "", condition: "", claim: "" }] };
    const checked = checkConflicts(reply, state, state.evidence);
    expect(checked.errors).toEqual([]);
    const log: string[] = [];
    const added = applyConflicts(state, checked.value!, 1, options, (l) => log.push(l));
    expect(added[0]).toMatchObject({ type: "evidence_vs_plan", about: "Q7", status: "settled" });
    const part = state.map!.events[3]!.parts[1]!;
    expect(part).toMatchObject({ id: "M15", status: "refuted", by: "C1", evidence: ["r1-b1-f1"] });
    expect(state.goals.find((g) => g.id === "Q7")!.partsTotal).toBe(3);
    expect(buildGuidance(state)).not.toContain("battery warranty");
    // A part that is no longer an assumption cannot be the other side again.
    expect(checkConflicts(reply, state, state.evidence).errors[0]!.message).toContain("planned part ID");
  });

  it("names to the writer only the events that findings confirmed", () => {
    const state = extended();
    serve(state, "Q6", ["Charging slows below freezing."]);
    const q6 = state.goals.find((g) => g.id === "Q6")!;
    applyJudgments(state, judgment([{ part: "M10", met: true, evidence: ["r1-b1-f1"] }]), [q6], 1, options, () => {});
    q6.status = "exhausted";
    const guidance = buildGuidance(state);
    expect(guidance).toContain("The notes cover these parts of the subject.");
    expect(guidance).toContain("- Charging in winter");
    expect(guidance).not.toContain("- Buying");
    // An unconfirmed assumption is not reported to the client as a gap.
    expect(guidance).not.toContain("Not established");
  });
});

// ---------------------------------------------------------------- the whole loop, without network

const E1 = EXAMPLES[0]!;

/** An extension of E1 (tariffs and new-car prices): two events, replacing the mechanism question Q6. */
const E1_EXTENSION: ExtensionReply = {
  subject: "2025 US tariffs and new-car prices in Canada",
  subject_object_ids: ["O4"],
  events: [
    {
      name: "Passing the cost on",
      need: "necessary",
      question: "How do importers and dealers pass the cost of the 2025 US tariffs on to buyers of new cars in Canada?",
      parts: [{ text: "importer and dealer margins", kind: "economic" }, { text: "a rebate for buyers", kind: "built_digital" }, { text: "delivery delays at the border", kind: "economic" }],
      source_hints: ["industry analyses"],
      feeds: ["Q7"],
    },
    {
      name: "Buyers' response",
      need: "completing",
      question: "How did buyers of new cars in Canada respond to price changes after the 2025 US tariffs?",
      parts: [{ text: "sales volumes", kind: "economic" }, { text: "shift to used cars", kind: "social" }],
      source_hints: [],
      feeds: ["Q7"],
    },
  ],
  replaces: ["Q6"],
};

const LOOP_NOTES: Record<string, [string, string][]> = {
  Q3: [["Two banks publish forecasts.", "bank-a.example"], ["Customs reported that vehicles were not delayed at the border (NODELAY).", "customs-b.example"]],
  Q9: [["Dealers kept their margins and passed the cost on (MARGINS).", "trade-a.example"], ["No rebate for buyers exists: the proposal was never adopted (NOREBATE).", "gov-b.example"]],
};

const loopResearch = async (_q: string, brief: ResearchBrief): Promise<ResearchResult> => {
  const ids = (brief.tag ?? "").split(",");
  const notes = ids
    .map((id, i) => {
      const findings = LOOP_NOTES[id] ?? [[`A finding for ${id}.`, `${id.toLowerCase()}-a.example`], [`Another finding for ${id}.`, `${id.toLowerCase()}-b.example`]];
      return [`## ${brief.keyQuestions[i]}`, "### Cited Findings", ...findings.map(([text, host]) => `- ${text} — [Source](https://${host}/${id})`), "### Gaps", `- Nothing more for ${id}.`].join("\n");
    })
    .join("\n\n");
  return { brief, status: "ok", notes, sources: [], queries: [], usage: { inputTokens: 0, outputTokens: 0, searches: 1, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [] };
};

function tagged(message: string, tag: string): string {
  return new RegExp(`<${tag}>\\n([\\s\\S]*?)\\n</${tag}>`).exec(message)?.[1] ?? "";
}

function evidenceLines(text: string): { id: string; text: string }[] {
  return text.split("\n").flatMap((l) => {
    const m = /^(r\d+-b\d+-[fg]\d+) (?:\[[^\]]*\] )?(.*)$/.exec(l);
    return m ? [{ id: m[1]!, text: m[2]! }] : [];
  });
}

/** The fake conflict checker: a finding that nothing was delayed contradicts the planned part about delays. */
function loopConflicts(message: string) {
  const none = evidenceLines(tagged(message, "new_evidence")).find((l) => l.text.includes("(NODELAY)"));
  const part = /^(M\d+) \[(Q\d+),[^\]]*\] delivery delays/m.exec(tagged(message, "plan"));
  if (!none || !part) return { conflicts: [] };
  return { conflicts: [{ type: "evidence_vs_plan", about: part[2]!, statement: "The plan expected delivery delays at the border; customs reported none.", side_a: [none.id], side_b: [part[1]!], settle_by: "", condition: "", claim: "" }] };
}

/** The fake round analyst: planned parts by their IDs, every other goal answered from its findings. */
function loopRound(message: string) {
  const judgments = tagged(message, "served_goals").split(/\n(?=### )/).map((g) => {
    const id = /^### (Q\d+)/.exec(g)![1]!;
    const findings = evidenceLines(g).filter((l) => l.id.includes("-f"));
    if (g.includes("Planned parts of the life-cycle step")) {
      const judge = (/^Judge only: (.*)$/m.exec(g)?.[1] ?? "").split(", ").filter((x) => /^M\d+$/.test(x));
      const text = (m: string) => new RegExp(`^- ${m} (.*)$`, "m").exec(g)?.[1] ?? "";
      const parts = judge.map((m) => {
        const margins = findings.find((l) => l.text.includes("(MARGINS)"));
        const rebate = findings.find((l) => l.text.includes("(NOREBATE)"));
        if (text(m).includes("margins") && margins) return { part: `${m} ${text(m)}`, met: true, refuted: false, correction: "", evidence: [margins.id] };
        if (text(m).includes("rebate") && rebate) return { part: `${m} ${text(m)}`, met: false, refuted: true, correction: "no rebate was adopted", evidence: [rebate.id] };
        return id === "Q10" ? { part: `${m} ${text(m)}`, met: true, refuted: false, correction: "", evidence: [findings[0]!.id] } : { part: `${m} ${text(m)}`, met: false, refuted: false, correction: "", evidence: [] };
      });
      return { goal_id: id, parts, outcome: "partial", verdicts: [], missing: ["what is left"] };
    }
    const claims = [...g.matchAll(/^- (A\d+): /gm)].map((m) => m[1]!);
    return { goal_id: id, parts: [{ part: "the answer", met: true, evidence: findings.map((l) => l.id) }], outcome: "answered", verdicts: claims.map((c) => ({ claim_id: c, verdict: "supported" })), missing: [] };
  });
  return { judgments, proposals: [] };
}

describe("ebd with problem extension through the skeleton", () => {
  it("opens with the event goals, lets the evidence overwrite the plan and keeps the assumptions from the writer", async () => {
    const calls: string[] = [];
    const model = {
      bindTools: (tools: { function: { name: string } }[]) => ({
        invoke: async (messages: BaseMessage[]) => {
          const name = tools[0]!.function.name;
          const message = String(messages.at(-1)!.content);
          calls.push(name);
          const args = name === "submit_analysis" ? E1.analysis : name === "submit_premise_sort" ? { claims: E1.analysis.assumptions.map((x) => ({ id: x.id, verdict: "check", reason: "a specific fact" })) } : name === "submit_extension" ? E1_EXTENSION : name === "submit_conflicts" ? loopConflicts(message) : loopRound(message);
          return new AIMessage({ content: "", tool_calls: [{ id: `c${calls.length}`, name, args: args as Record<string, unknown>, type: "tool_call" }] });
        },
      }),
    } as unknown as BaseChatModel;
    const decisions: DecisionRecord[] = [];
    let synthesis: { material: { label: string; notes: string }[]; outline?: string[]; guidance?: string } | undefined;
    const graph = buildResearchGraph({
      strategy: ebd.create({ extend: true }),
      strategyModel: model,
      research: loopResearch,
      write: async (_q, s) => ((synthesis = s), { report: "report", diagnostics: [] }),
      limits: { researchersTotal: 10, toolCallsPerResearcher: 12 },
      maxRounds: 8,
      concurrency: 4,
      runId: "t",
      today: E1.runDate,
      hooks: { onDecision: (d) => void decisions.push(d) },
    });
    const final = await graph.invoke(initialState(E1.request), { recursionLimit: 100 });
    const state = final.strategyState as EbdState;

    // Init: the request analysis, then the extension; Q6 asked for the mechanism as a whole and is replaced.
    expect(calls.slice(0, 3)).toEqual(["submit_analysis", "submit_premise_sort", "submit_extension"]);
    expect((decisions[0]!.strategyState as EbdState).step.calls.map((c) => c.role)).toEqual(["request_analyst", "premise_sorter", "extension_analyst"]);
    expect(state.map!.replaced).toEqual({ Q6: ["Q9", "Q10"] });
    expect(state.goals.find((g) => g.id === "Q6")).toMatchObject({ need: "completing", level: 4 });
    expect(decisions[0]!.accepted.flatMap((b) => (b.tag ?? "").split(","))).toEqual(expect.arrayContaining(["Q9", "Q10"]));
    expect(decisions[0]!.rationale).toContain('Environment map of "2025 US tariffs and new-car prices in Canada"');

    // Round 1: a finding of another goal refutes one part through a conflict; the analyst refutes and corrects another.
    const parts = state.map!.events[0]!.parts;
    expect(parts.map((p) => [p.text, p.origin, p.status, p.by])).toEqual([
      ["importer and dealer margins", "assumed", "confirmed", "round analyst"],
      ["a rebate for buyers", "assumed", "refuted", "round analyst"],
      ["delivery delays at the border", "assumed", "refuted", "C1"],
      ["no rebate was adopted", "found", "confirmed", "round analyst"],
    ]);
    expect(state.conflicts[0]).toMatchObject({ type: "evidence_vs_plan", about: "Q9", status: "settled", settleGoal: null });
    expect(state.goals.find((g) => g.id === "Q9")).toMatchObject({ status: "answered", partsMet: 2, partsTotal: 2, attempts: 1, origin: { type: "assumed", event: "E1" } });
    expect(state.goals.find((g) => g.id === "Q10")).toMatchObject({ status: "answered", need: "completing" });
    expect(state.stop).toMatchObject({ kind: "complete" });
    expect(state.tree.byOrigin).toMatchObject({ request: 6, assumed: 2 });

    // The writer gets the event's notes and its name, and nothing of what the plan assumed wrongly.
    expect(synthesis!.material.some((m) => m.label.startsWith("How do importers and dealers pass the cost"))).toBe(true);
    expect(synthesis!.guidance).toContain("The notes cover these parts of the subject.");
    expect(synthesis!.guidance).toContain("- Passing the cost on");
    expect(synthesis!.guidance).not.toMatch(/a rebate for buyers|delivery delays|The plan expected/);
    expect(final.synthesisDiagnostics).toEqual([]);
  });
});
