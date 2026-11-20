import { describe, expect, it } from "vitest";
import { importEngineRun, type RunFile } from "./engineRun";

function runFile(path: string, data: string): RunFile {
  return {
    name: path.split("/").at(-1)!,
    webkitRelativePath: path,
    size: data.length,
    text: async () => data,
  };
}

describe("DeepResearchEngine run import", () => {
  it("restores completed rounds and only reports settled verdicts from v2 records", async () => {
    const summary = {
      runId: "recorded-run",
      question: "When did the telescope launch?",
      strategy: { name: "ebd", label: "ebd-matched" },
      status: "ok",
      code: { commit: "d356778" },
      rounds: 1,
      researchersUsed: 2,
      researchersBudget: 2,
      totalTokens: { input: 500, output: 100 },
      citationCheck: {
        unknownUrls: ["https://unknown.example/"],
        binding: { unbound: 1 },
      },
      guardrails: [
        { phase: "research", action: "quarantine", count: 1, message: "Internal finding" },
      ],
    };
    const goal = { id: "Q1", text: "Check the launch year", need: "necessary" };
    const decision = {
      type: "decision",
      data: {
        phase: "observe",
        round: 2,
        budgetBefore: 0,
        stop: true,
        strategyState: {
          analysis: {
            assumptions: [{ id: "A1", claim: "It launched in 2018" }],
          },
          goals: [
            {
              ...goal,
              status: "answered",
              verdicts: { A1: "contradicted" },
              evidence: ["r1-b1-f1"],
            },
            {
              ...goal,
              id: "Q2",
              status: "open",
              verdicts: { A1: "supported" },
            },
          ],
          conflicts: [
            {
              id: "C1",
              statement: "Check the date",
              status: "settled",
              sideA: ["r1-b1-f1"],
              sideB: ["A1"],
            },
          ],
          evidence: [
            { id: "r1-b1-f1", text: "Launched in 2021", briefId: "r1-b1" },
          ],
          init: { fallback: true },
          stop: {
            kind: "budget",
            round: 1,
            reason: "Researcher budget reached",
          },
          step: { phase: "observe", round: 1, events: ["Settled Q1"] },
        },
      },
    };
    const result = (id: string, cited: boolean) => ({
      brief: { id, round: 1, objective: "Find a launch record" },
      status: "ok",
      notes: "Research notes",
      sources: [
        { url: "https://example.org/launch", cited },
        { url: "javascript:alert(1)", cited: true },
      ],
    });
    const unrelated: RunFile = {
      name: ".env",
      webkitRelativePath: "run/.env",
      text: async () => {
        throw new Error("Ignored files must not be read");
      },
    };

    const parsed = await importEngineRun([
      runFile("run/summary.json", JSON.stringify(summary)),
      runFile(
        "run/events.jsonl",
        JSON.stringify(decision) + "\n{interrupted write",
      ),
      runFile("run/results/r1-b1.json", JSON.stringify(result("r1-b1", false))),
      runFile("run/results/r1-b2.json", JSON.stringify(result("r1-b2", true))),
      runFile(
        "run/results/r1-b3.json",
        JSON.stringify({
          brief: { id: "r1-b3", round: 1, objective: "Cross-check the date" },
          status: "failed",
          failure: { kind: "timeout", message: "Research timed out" },
        }),
      ),
      runFile(
        "run/synthesis.json",
        JSON.stringify({
          synthesis: {
            material: [{ label: "Launch record", notes: "Launched in 2021" }],
          },
        }),
      ),
      runFile("run/report.md", "Published report"),
      unrelated,
    ]);

    expect(parsed).toMatchObject({
      runId: "recorded-run",
      strategyName: "ebd",
      strategy: "ebd-matched",
      stopKind: "budget",
      stopReason: "Researcher budget reached",
      researchersUsed: 2,
      assumptions: [{ id: "A1", verdict: "contradicted" }],
      decisions: [
        {
          phase: "observe",
          round: 1,
          nextRound: 2,
          budgetBefore: 0,
          actions: ["Settled Q1"],
        },
      ],
      conflicts: [{ id: "C1", sideB: ["A1"] }],
      evidence: [{ id: "r1-b1-f1", briefId: "r1-b1" }],
      report: "Published report",
      writerInput: {
        materials: [{ label: "Launch record", notes: "Launched in 2021" }],
      },
      metrics: { inputTokens: 500, outputTokens: 100 },
    });
    expect(parsed.sources).toEqual([
      {
        url: "https://example.org/launch",
        title: undefined,
        cited: true,
        briefIds: ["r1-b1", "r1-b2"],
      },
    ]);
    expect(parsed.warnings).toEqual([
      "Unreadable records in events.jsonl: 1.",
      "Researcher r1-b3 failed. Research timed out",
      "URL is missing from the source record: https://unknown.example/",
      "Verify the report’s numerical claims against the cited sources.",
      "Request analysis used its fallback.",
    ]);
  });

  it("accepts a partial run without marking it successful and rejects a parent of multiple runs", async () => {
    const config = JSON.stringify({
      question: "Original question",
      strategy: { name: "baseline" },
      researchersTotal: 6,
    });
    const firstRunConfig = runFile("experiments/run-a/config.json", config);
    const parsed = await importEngineRun([firstRunConfig]);
    expect(parsed).toMatchObject({
      runId: "run-a",
      reviewKey: "run-a",
      status: "unreported",
      strategy: "baseline",
      researchersBudget: 6,
      decisions: [],
      results: [],
    });
    await expect(
      importEngineRun([
        firstRunConfig,
        runFile("experiments/run-b/report.md", "A different report"),
      ]),
    ).rejects.toThrow(/single Engine run folder/);
    const noRunId = await importEngineRun([runFile("config.json", config)]);
    expect(noRunId.reviewKey).toBeUndefined();
    expect(noRunId.warnings).toEqual([]);
  });
});
