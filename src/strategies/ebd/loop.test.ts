import { describe, expect, it } from "vitest";
import { AIMessage, type BaseMessage } from "@langchain/core/messages";
import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { ResearchBrief, ResearchResult } from "../../core/index.js";
import { briefFor, directiveLines, pack, selectGroups, selectWithReserve } from "./briefs.js";
import { goalsFromAnalysis, isComplete, isReady, isSaturated, levelOf, mootDependents, rankReady, treeMetrics } from "./goals.js";
import { decodeNested, structuredCall } from "./llm.js";
import { parseOptions } from "./options.js";
import type { Analysis } from "./request/index.js";
import { EXAMPLES } from "./request/examples.js";
import { applyJudgments, checkRound, repairRound, RoundApiSchema } from "./rounds/analyst.js";
import { applyConflicts, checkConflicts, settleBlock } from "./rounds/conflicts.js";
import { headingGoals, hostsIn, readResult, splitNotes } from "./rounds/evidence.js";
import type { EbdState } from "./state.js";
import { buildGuidance, buildMaterial, buildOutline, lengthLimit, plain } from "./synthesis.js";

const E1 = EXAMPLES[0]!;
const options = parseOptions({});

function stateOf(analysis: Analysis = structuredClone(E1.analysis)): EbdState {
  const goals = goalsFromAnalysis(analysis);
  return {
    question: E1.request,
    today: E1.runDate,
    init: { mode: "fixed", accepted: true, fallback: false, attempts: 1, stopReason: "accepted" },
    analysis,
    goals,
    objectsFound: [],
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

function result(tag: string, notes: string, id = "r1-b1", status: "ok" | "failed" = "ok"): ResearchResult {
  const brief: ResearchBrief = { id, round: Number(id.slice(1, 2)), objective: "o", keyQuestions: tag.split(",").map((t) => `[${t}] q`), constraints: [], sourceHints: [], tag };
  return { brief, status, notes, sources: [], queries: [], usage: { inputTokens: 0, outputTokens: 0, searches: 0, pageReads: 0 }, model: "fake", durationMs: 0, unlistedCitations: [], diagnostics: [] };
}

const NOTES = [
  "## [Q2] How are prices measured?",
  "### Takeaway",
  "Prices rose.",
  "### Cited Findings",
  "- The index rose 4% — [StatCan](https://www.statcan.gc.ca/a(1))",
  "  continued on a second line.",
  "- Dealers report higher prices — https://news.example.org/x.",
  "### Inferences",
  "- Probably tariffs.",
  "### Gaps",
  "- No regional data.",
  "",
  "## [Q1] Did the US impose tariffs?",
  "### Cited Findings",
  "- Yes, in April 2025 — [Gov](https://gov.example/t)",
].join("\n");

describe("reading results (section 8)", () => {
  it("indexes findings and gaps with brief-based IDs, keeping continuation lines", () => {
    const { record, evidence } = readResult(result("Q1,Q2", NOTES));
    expect(record.sections.map((s) => [s.goalIds, s.mappedBy])).toEqual([[["Q2"], "id"], [["Q1"], "id"]]);
    expect(evidence.map((e) => e.id)).toEqual(["r1-b1-f1", "r1-b1-f2", "r1-b1-g1", "r1-b1-f3"]);
    expect(evidence[0]).toMatchObject({ goalIds: ["Q2"], lines: [4, 5], hosts: ["statcan.gc.ca"] });
    expect(evidence[0]!.text).toContain("continued on a second line");
    expect(evidence[1]!.hosts).toEqual(["news.example.org"]);
  });

  it("maps by key-question order, and otherwise to every goal of the brief", () => {
    const plain = NOTES.replace("[Q2] ", "").replace("[Q1] ", "");
    expect(readResult(result("Q2,Q1", plain)).record.sections.map((s) => s.mappedBy)).toEqual(["order", "order"]);
    expect(readResult(result("Q2,Q1,Q3", plain)).record.sections.map((s) => s.goalIds)).toEqual([["Q2", "Q1", "Q3"], ["Q2", "Q1", "Q3"]]);
  });

  it("reads goal IDs from headings with or without brackets (live check X2)", () => {
    expect(headingGoals("[Q3] What is it?")).toEqual(["Q3"]);
    expect(headingGoals("Q4")).toEqual(["Q4"]);
    expect(headingGoals("Q2: What is the Apple Vision Pro?")).toEqual(["Q2"]);
    expect(headingGoals("Quarterly Q2 results")).toEqual([]);
  });

  it("keeps unstructured notes as one section of findings, and failed results as no evidence", () => {
    expect(splitNotes("Some text\n- a fact\n- another")).toHaveLength(1);
    expect(readResult(result("Q1", "", "r1-b1", "failed")).evidence).toEqual([]);
    expect(hostsIn("see [x](https://a.org/p_(x)) and https://b.org/q")).toEqual(["a.org", "b.org"]);
  });
});

describe("goals and order (section 6)", () => {
  it("derives kind and level from template, need and origin", () => {
    const goals = goalsFromAnalysis(E1.analysis);
    expect(goals.map((g) => `${g.id}:${g.kind}:${g.level}`)).toEqual(["Q1:verify:1", "Q2:verify:1", "Q3:define:2", "Q4:verify:1", "Q5:define:2", "Q6:relate:3"]);
    expect(levelOf("define", "completing")).toBe(4);
    expect(levelOf("settle", "completing")).toBe(1);
  });

  it("serves premise checks first (L-7), and makes them wait for their dependencies without it", () => {
    const s = stateOf();
    const byId = new Map(s.goals.map((g) => [g.id, g]));
    const q4 = byId.get("Q4")!;
    expect(isReady(q4, byId, options)).toBe(true);
    expect(isReady(q4, byId, { ...options, premiseFirst: false })).toBe(false);
    expect(rankReady(s, options).map((r) => r.goal.id)).toEqual(["Q2", "Q1", "Q4", "Q3"]);
  });

  it("makes goals moot when the premise they rely on is contradicted", () => {
    const s = stateOf();
    const q4 = s.goals.find((g) => g.id === "Q4")!;
    Object.assign(q4, { status: "answered", verdict: "contradicted", settledRound: 1 });
    expect(mootDependents(s, 1)).toEqual(["Q6"]);
  });

  it("is complete only when necessary goals, assumptions and conflicts are all settled", () => {
    const s = stateOf();
    expect(isComplete(s).complete).toBe(false);
    for (const g of s.goals) Object.assign(g, { status: "answered", verdict: g.verifies.length ? "supported" : null });
    expect(isComplete(s)).toMatchObject({ complete: true });
    s.conflicts.push({ id: "C1", type: "source_vs_source", about: "Q2", statement: "s", sideA: [], sideB: [], settleBy: "", condition: "", claim: null, status: "open", createdRound: 1, settledRound: null, settleGoal: null });
    expect(isComplete(s).reason).toContain("C1");
  });

  it("is saturated only when a round made no progress and not every researcher failed", () => {
    const none = { settled: [], advanced: [], newConflicts: 0, newNecessary: 0, allFailed: false };
    expect(isSaturated(none)).toBe(true);
    expect(isSaturated({ ...none, allFailed: true })).toBe(false);
    expect(isSaturated({ ...none, advanced: ["Q1"] })).toBe(false);
  });
});

describe("briefs (section 7)", () => {
  it("packs goals by primary object within the brief and round limits", () => {
    const s = stateOf();
    const q = (id: string) => s.goals.find((g) => g.id === id)!;
    q("Q3").objectIds = ["O4"];
    expect(pack([q("Q1"), q("Q3"), q("Q2")], { maxPerRound: 1, questionsPerBrief: 3 }).map((g) => g.goals.map((x) => x.id))).toEqual([["Q1", "Q3"]]);
  });

  it("gives one slot to the necessary goal that has waited longest", () => {
    const s = stateOf();
    s.goals.find((g) => g.id === "Q3")!.createdRound = 0;
    const { groups, reserve } = selectGroups(rankReady(s, options), { maxPerRound: 2, questionsPerBrief: 1 });
    expect(reserve).toBe("Q3");
    expect(groups.map((g) => g.goals[0]!.id)).toEqual(["Q2", "Q3"]);
  });

  it("holds back briefs of goals added during the run while first tries need the researchers (review of 2026-10-21)", () => {
    const s = stateOf();
    const q = (id: string) => s.goals.find((g) => g.id === id)!;
    for (const id of ["Q2", "Q4", "Q5", "Q6"]) Object.assign(q(id), { status: "answered" });
    Object.assign(q("Q1"), { attempts: 1 });
    Object.assign(q("Q3"), { dependsOn: ["Q1"] });
    s.goals.push({ ...structuredClone(q("Q2")), id: "Q9", kind: "settle", level: 1, status: "open", attempts: 0, depth: 1, objectIds: ["O99"], dependsOn: [], verifies: [], origin: { type: "conflict", conflict: "C1" }, settles: "C1" });
    const ids = (sel: ReturnType<typeof selectWithReserve>) => sel.groups.map((g) => g.goals.map((x) => x.id).join(","));
    // Q3 has never been served and waits for Q1: one researcher stays for it, so the settle goal Q9 waits.
    const tight = selectWithReserve(rankReady(s, options), s, 2, options);
    expect(ids(tight)).toEqual(["Q1"]);
    expect(tight).toMatchObject({ researchersKept: 1, released: false });
    expect(tight.held.map((g) => g.id)).toEqual(["Q9"]);
    expect(tight.reservedFor.map((g) => g.id)).toEqual(["Q3"]);
    expect(ids(selectWithReserve(rankReady(s, options), s, 3, options))).toContain("Q9");
    expect(ids(selectWithReserve(rankReady(s, options), s, 2, { ...options, reserveFirstTries: false }))).toContain("Q9");
    // A settle goal that a request goal waits for is never held back.
    Object.assign(q("Q2"), { status: "conflicting", waitingOn: "Q9" });
    expect(ids(selectWithReserve(rankReady(s, options), s, 2, options))).toContain("Q9");
    // When nothing else can be served, the reserve is released rather than stopping with researchers left.
    Object.assign(q("Q2"), { status: "answered", waitingOn: null });
    Object.assign(q("Q1"), { attempts: options.maxAttempts });
    const alone = selectWithReserve(rankReady(s, options), s, 1, options);
    expect(alone).toMatchObject({ released: true, held: [] });
    expect(ids(alone)).toEqual(["Q9"]);
  });

  it("writes the verification instruction, the frame and the client's evidence directives into the brief", () => {
    const s = stateOf({
      ...structuredClone(E1.analysis),
      client_directives: [
        { kind: "source_preference", text: "Use only official statistics.", evidence: ["official statistics only"] },
        { kind: "report_format", text: "A one-page briefing.", evidence: ["one-page"] },
        { kind: "scope_limit", text: "Leave out used cars.", evidence: [] },
      ],
    });
    const q1 = s.goals.find((g) => g.id === "Q1")!;
    const brief = briefFor({ key: "O4", goals: [q1] }, 0, s);
    expect(brief).toMatchObject({ tag: "Q1", priority: 90 });
    expect(brief.keyQuestions[0]).toMatch(/^\[Q1\] /);
    expect(brief.instructions).toContain("Look specifically for evidence that contradicts it.");
    expect(brief.instructions).toContain("The claim: 'The US imposed tariffs in 2025.'");
    expect(brief.sourceHints).toContain("primary records; at least two independent publishers");
    expect(brief.constraints).toContain('Client source preference: Use only official statistics. (client\'s words: "official statistics only")');
    expect(brief.constraints!.some((c) => c.startsWith("Client report format"))).toBe(false);
    expect(directiveLines(s.analysis, "writer")).toEqual(['Client report format: A one-page briefing. (client\'s words: "one-page")', "Client scope limit: Leave out used cars."]);
  });
});

describe("conflict checker and round analyst checks (sections 9 and 10)", () => {
  function withEvidence() {
    const s = stateOf();
    const { record, evidence } = readResult(result("Q2,Q1", NOTES));
    s.results.push(record);
    s.evidence.push(...evidence);
    return { s, evidence };
  }

  it("rejects conflicts without valid evidence on both sides", () => {
    const { s, evidence } = withEvidence();
    const c = { type: "source_vs_source", about: "Q2", statement: "They differ.", side_a: ["r1-b1-f1"], side_b: ["r9-b9-f9"], settle_by: "The official release.", condition: "" };
    const out = checkConflicts({ conflicts: [c, { ...c, type: "evidence_vs_assumption", side_b: ["A2"] }] }, s, evidence);
    expect(out.errors.map((e) => e.path)).toEqual(["conflicts[0]"]);
    expect(out.errors[0]!.message).toContain("r9-b9-f9");
  });

  it("rejects a disagreement whose two sides cite the same source", () => {
    const { s, evidence } = withEvidence();
    s.evidence.push({ ...evidence[0]!, id: "r1-b1-f9", text: "The index rose 5% - https://statcan.gc.ca/b", hosts: ["statcan.gc.ca"] });
    const c = { type: "source_vs_source", about: "Q2", statement: "Two figures on one site.", side_a: ["r1-b1-f1"], side_b: ["r1-b1-f9"], settle_by: "The release.", condition: "" };
    expect(checkConflicts({ conflicts: [c] }, s, evidence).errors[0]!.message).toContain("same source");
  });

  it("gives a goal at most one settle goal, within the new-goal limits, and disputes the rest", () => {
    const { s } = withEvidence();
    const c = (side: string) => ({ type: "source_vs_source" as const, about: "Q2", statement: "They differ.", side_a: ["r1-b1-f1"], side_b: [side], settle_by: "The official release.", condition: "", claim: "" });
    const log: string[] = [];
    applyConflicts(s, { conflicts: [c("r1-b1-f2"), c("r1-b1-f3")] }, 1, options, (l) => log.push(l));
    expect(s.conflicts.map((x) => x.status)).toEqual(["open", "disputed"]);
    expect(log[1]).toContain("already waits for the settle goal");
    const q3 = s.goals.find((g) => g.id === "Q3")!;
    expect(settleBlock(s, { ...q3, need: "completing" }, options, 1)).toContain("completing goal");
    expect(settleBlock(s, { ...q3, depth: 2 }, options, 1)).toContain("beyond maxDepth");
    expect(settleBlock(s, q3, { ...options, maxNewGoalsPerRound: 1 }, 1)).toContain("quota");
    expect(settleBlock(s, { ...q3, settles: "C9" }, options, 1)).toContain("itself settling a disagreement");
    expect(settleBlock(s, { ...q3, status: "exhausted" }, options, 1)).toContain("already exhausted");
    expect(settleBlock(s, { ...q3, status: "answered" }, options, 1)).toBeNull();
  });

  it("marks a goal disputed when its disagreement cannot get a settle goal", () => {
    const { s } = withEvidence();
    const q3 = s.goals.find((g) => g.id === "Q3")!;
    q3.need = "completing";
    s.conflicts.push({ id: "C1", type: "source_vs_source", about: "Q3", statement: "s", sideA: ["r1-b1-f1"], sideB: ["r1-b1-f2"], settleBy: "x", condition: "", claim: null, status: "disputed", createdRound: 1, settledRound: 1, settleGoal: null });
    const reply = { judgments: [{ goal_id: "Q3", parts: [{ part: "p", met: false, evidence: [] }], outcome: "conflicting" as const, verdict: "not_applicable" as const, missing: ["which value holds"] }], proposals: [] };
    const applied = applyJudgments(s, reply, [q3], 1, options, () => {});
    expect(q3.status).toBe("disputed");
    expect(applied.settled).toEqual(["Q3"]);
  });

  it("lets a settle goal check a claim only when the disagreement decides it (review of 2026-10-21)", () => {
    const { s, evidence } = withEvidence();
    const c = { type: "source_vs_source" as const, about: "Q2", statement: "They differ.", side_a: ["r1-b1-f1"], side_b: ["r1-b1-f2"], settle_by: "The official release.", condition: "" };
    // A reply without the claim field decides no assumption.
    expect(checkConflicts({ conflicts: [c] }, s, evidence).errors).toEqual([]);
    expect(checkConflicts({ conflicts: [{ ...c, claim: "A9" }] }, s, evidence).errors[0]!.message).toContain("unknown assumption A9");
    applyConflicts(s, { conflicts: [{ ...c, claim: "" }] }, 1, options, () => {});
    expect(s.goals.find((g) => g.id === s.conflicts[0]!.settleGoal)!.verifies).toEqual([]);
    const other = stateOf();
    applyConflicts(other, { conflicts: [{ ...c, claim: "A2" }, { ...c, type: "evidence_vs_assumption", about: "Q1", side_b: ["A1"], claim: "" }] }, 1, options, () => {});
    expect(other.conflicts.map((x) => x.claim)).toEqual(["A2", "A1"]);
    expect(other.goals.filter((g) => g.settles).map((g) => g.verifies)).toEqual([["A2"], ["A1"]]);
  });

  it("changes the waiting goal's verdict only when its settle goal judged the claim", () => {
    for (const [claim, verdict] of [["", "supported"], ["A2", "unsettled"]] as const) {
      const { s } = withEvidence();
      const c = { type: "source_vs_source" as const, about: "Q2", statement: "They differ.", side_a: ["r1-b1-f1"], side_b: ["r1-b1-f2"], settle_by: "The official release.", condition: "", claim };
      applyConflicts(s, { conflicts: [c] }, 1, options, () => {});
      const settleGoal = s.goals.find((g) => g.id === s.conflicts[0]!.settleGoal)!;
      const q2 = s.goals.find((g) => g.id === "Q2")!;
      Object.assign(q2, { status: "conflicting", waitingOn: settleGoal.id, verdict: "supported" });
      settleGoal.attempts = options.maxAttempts;
      const judged = claim ? ("unsettled" as const) : ("not_applicable" as const);
      const reply = { judgments: [{ goal_id: settleGoal.id, parts: [{ part: "which value holds", met: false, evidence: [] }], outcome: "not_found" as const, verdict: judged, missing: ["the official release"] }], proposals: [] };
      applyJudgments(s, reply, [settleGoal], 2, options, () => {});
      expect(q2).toMatchObject({ status: "disputed", verdict });
    }
  });

  it("keeps the valid parts of a judgment when the retry fails too", () => {
    const { s } = withEvidence();
    const served = s.goals.filter((g) => g.id === "Q1" || g.id === "Q2");
    const repaired = repairRound({
      judgments: [
        { goal_id: "Q1", parts: [{ part: "a", met: true, evidence: ["r1-b1-f3"] }, { part: "b", met: true, evidence: ["r1-b1-g1"] }], outcome: "answered", verdict: "supported", missing: [] },
        { goal_id: "Q6", parts: [{ part: "x", met: true, evidence: ["r1-b1-f1"] }], outcome: "answered", verdict: "not_applicable", missing: [] },
      ],
      proposals: [],
    }, s, served);
    expect(repaired.judgments).toEqual([
      { goal_id: "Q1", parts: [{ part: "a", met: true, evidence: ["r1-b1-f3"] }, { part: "b", met: false, evidence: [] }], outcome: "partial", verdict: "supported", missing: ["b"] },
    ]);
  });

  it("treats a reply without proposals as proposing nothing", () => {
    const { s } = withEvidence();
    const served = s.goals.filter((g) => g.id === "Q3");
    const out = checkRound({ judgments: [{ goal_id: "Q3", parts: [{ part: "p", met: false, evidence: [] }], outcome: "not_found", verdict: "not_applicable", missing: ["p"] }] }, s, served);
    expect(out).toMatchObject({ errors: [], value: { proposals: [] } });
  });

  it("requires cited findings for met parts, a verdict for claims, and a judgment for every served goal", () => {
    const { s } = withEvidence();
    const served = s.goals.filter((g) => g.id === "Q1" || g.id === "Q2");
    const reply = {
      judgments: [{ goal_id: "Q1", parts: [{ part: "p", met: true, evidence: ["r1-b1-g1"] }], outcome: "answered", verdict: "not_applicable", missing: [] }],
      proposals: [],
    };
    const out = checkRound(reply, s, served);
    expect(out.errors.map((e) => e.message)).toEqual([
      "parts[0]: r1-b1-g1 is a gap line, which cannot meet a part",
      "a goal with a claim to verify needs a verdict: supported, contradicted or unsettled",
      "no judgment for Q2",
    ]);
  });
});

describe("structured-call helper (section 5.3)", () => {
  function scripted(replies: unknown[]) {
    const seen: BaseMessage[][] = [];
    const model = {
      bindTools: () => ({
        invoke: async (messages: BaseMessage[]) => {
          seen.push(messages);
          const args = replies.shift();
          return args === undefined ? new AIMessage("no tool") : new AIMessage({ content: "", tool_calls: [{ id: "c", name: "submit_round_analysis", args: args as Record<string, unknown>, type: "tool_call" }] });
        },
      }),
    } as unknown as BaseChatModel;
    return { model, seen };
  }
  const check = (args: unknown) => {
    const parsed = RoundApiSchema.safeParse(args);
    if (!parsed.success) return { value: null, errors: [{ code: "schema", path: "", message: "bad" }], warnings: [] };
    return { value: parsed.data, errors: parsed.data.judgments.length ? [] : [{ code: "judgment_missing", path: "judgments", message: "no judgment for Q1" }], warnings: [] };
  };
  const call = (model: BaseChatModel) =>
    structuredCall({ model, role: "round_analyst", system: "s", message: "m", tool: { name: "submit_round_analysis", description: "d", schema: RoundApiSchema }, check, fallback: (v) => v });
  const good = { judgments: [{ goal_id: "Q1", parts: [], outcome: "partial", verdict: "not_applicable", missing: ["x"] }], proposals: [] };

  it("decodes values the model sent as JSON text, and leaves other text alone", () => {
    expect(decodeNested({ judgments: '[{"goal_id":"Q1"}]', note: "[Q1] text", n: 2 })).toEqual({
      value: { judgments: [{ goal_id: "Q1" }], note: "[Q1] text", n: 2 },
      decoded: ["judgments"],
    });
  });

  it("retries once with the previous reply and the numbered errors", async () => {
    const { model, seen } = scripted([{ judgments: [], proposals: [] }, good]);
    const out = await call(model);
    expect(out).toMatchObject({ accepted: true, fallback: false });
    expect(out.calls.map((c) => c.accepted)).toEqual([false, true]);
    expect(String(seen[1]![1]!.content)).toContain("<validation_errors>\n1. judgments: no judgment for Q1");
  });

  it("falls back to the last structurally valid reply", async () => {
    const { model } = scripted([{ judgments: [], proposals: [] }, undefined]);
    const out = await call(model);
    expect(out).toMatchObject({ accepted: false, fallback: true, value: { judgments: [] } });
    expect(out.calls[1]!.errors[0]!.code).toBe("no_reply");
  });
});

describe("writer input (section 12)", () => {
  it("keeps internal IDs out of the guidance", () => {
    expect(plain("No timetable confirms it (r1-b1-g1, r2-b1-g1); see C4.")).toBe("No timetable confirms it; see C4.");
    expect(plain("Mercedes C300 (C2, C3) price r2-b1-f8 differs")).toBe("Mercedes C300 price differs");
  });

  it("tells the writer which goals were only partly established, and which found nothing", () => {
    const s = stateOf();
    Object.assign(s.goals[0]!, { status: "exhausted", partsMet: 1, partsTotal: 3, missing: ["the rates"] });
    Object.assign(s.goals[2]!, { status: "exhausted", partsMet: 0, partsTotal: 2 });
    const guidance = buildGuidance(s);
    expect(guidance).toContain(`only partly established. Use their notes, and where the report covers them, say what the evidence does not establish:
- ${s.goals[0]!.text} Not established: the rates`);
    expect(guidance).toContain(`No reliable source was found for these; say so where relevant instead of guessing:
- ${s.goals[2]!.text}`);
  });

  it("follows a length limit and passes the planned contents to the writer (review of 2026-10-21)", () => {
    const s = stateOf();
    s.conflicts.push({ id: "C1", type: "source_vs_source", about: "Q2", statement: "One source says 4%, another 1%.", sideA: [], sideB: [], settleBy: "x", condition: "", claim: null, status: "disputed", createdRound: 1, settledRound: 1, settleGoal: null });
    const q7 = s.analysis.questions.find((q) => q.id === "Q7")!;
    expect(buildGuidance(s)).toContain(`What each part of the report must contain, as planned:\n- ${q7.text} ${q7.done_when}`);
    expect(buildOutline(s)).toContain("Where the sources disagree");
    expect(buildGuidance(s)).toContain('under "Where the sources disagree"');
    s.analysis.client_directives = [{ kind: "report_format", text: "Deliver a one-page summary.", evidence: ["a one-page summary"] }];
    expect(lengthLimit(s.analysis)).toBe("a one-page summary");
    const guidance = buildGuidance(s);
    expect(guidance).toContain('The client limits the length ("a one-page summary"). This comes before everything below');
    expect(guidance).toContain("Give both sides in one sentence");
    expect(buildOutline(s)).not.toContain("Where the sources disagree");
    expect(lengthLimit({ ...s.analysis, client_directives: [{ kind: "report_format", text: "Use bullet points.", evidence: [] }] })).toBeNull();
  });

  it("keeps whole notes lines grouped by goal and leaves out off-target lines", () => {
    const s = stateOf();
    const { record, evidence } = readResult(result("Q2,Q1", NOTES));
    s.results.push(record);
    s.evidence.push(...evidence);
    s.conflicts.push({ id: "C1", type: "off_target", about: "O6", statement: "Another index.", sideA: ["r1-b1-f2"], sideB: ["O6"], settleBy: "", condition: "", claim: null, status: "settled", createdRound: 1, settledRound: 1, settleGoal: null });
    const material = buildMaterial(s);
    expect(material.map((m) => m.notes.split("\n")[0])).toEqual([expect.stringMatching(/^# \[Q1\]/), expect.stringMatching(/^# \[Q2\]/)]);
    const lines = new Set(NOTES.split("\n").map((l) => l.trim()));
    for (const m of material) for (const l of m.notes.split("\n")) if (!l.startsWith("#") && l.trim()) expect(lines.has(l.trim())).toBe(true);
    expect(material.map((m) => m.notes).join("\n")).not.toContain("Dealers report");
    expect(buildGuidance(s)).toContain("different referent");
    // A line a goal cites as its own evidence stays (live run 2026-10-20: the goal asked for the other meanings of "EBD").
    s.goals.find((g) => g.id === "Q2")!.evidence = ["r1-b1-f2"];
    expect(buildMaterial(s).map((m) => m.notes).join("\n")).toContain("Dealers report");
  });
});
