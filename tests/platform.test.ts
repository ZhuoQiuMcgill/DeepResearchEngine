import { describe, expect, it } from "vitest";
import { listStrategies, loadStrategyModule, createStrategy } from "../src/platform/strategies.js";
import { planJobs } from "../src/platform/experiment.js";

describe("strategy plug-ins", () => {
  it("discovers strategy directories and loads baseline as a module", async () => {
    expect(listStrategies()).toContain("baseline");
    const m = await loadStrategyModule("baseline");
    expect(m.name).toBe("baseline");
    expect(m.contractVersion).toBe("1");
    expect((await createStrategy("baseline", { maxPerRound: 4 })).name).toBe("baseline");
  });

  it("rejects unknown strategies and invalid options", async () => {
    await expect(loadStrategyModule("nope")).rejects.toThrow(/not found/);
    await expect(createStrategy("baseline", { maxPerRound: 0 })).rejects.toThrow();
    await expect(createStrategy("baseline", { unknown: true })).rejects.toThrow();
  });
});

describe("experiment specs", () => {
  it("expands tasks × strategies × models × repeats", () => {
    const { jobs } = planJobs({
      name: "t",
      tasks: ["ebd", { id: "custom", question: "Q?" }],
      strategies: ["baseline", { name: "baseline", label: "baseline-4", options: { maxPerRound: 4 } }],
      models: ["haiku", "luna"],
      repeats: 2,
    });
    expect(jobs).toHaveLength(2 * 2 * 2 * 2);
    expect(jobs.find((j) => j.taskId === "custom")!.question).toBe("Q?");
    expect(new Set(jobs.map((j) => j.strategy.label))).toEqual(new Set(["baseline", "baseline-4"]));
  });

  it("fails fast on unknown names and duplicate labels", () => {
    expect(() => planJobs({ name: "t", tasks: ["nope"], strategies: ["baseline"], models: ["haiku"] })).toThrow(/Unknown task/);
    expect(() => planJobs({ name: "t", tasks: ["ebd"], strategies: ["ebdx"], models: ["haiku"] })).toThrow(/Unknown strategy/);
    expect(() => planJobs({ name: "t", tasks: ["ebd"], strategies: ["baseline"], models: ["gpt"] })).toThrow(/Unknown model profile/);
    expect(() => planJobs({ name: "t", tasks: ["ebd"], strategies: ["baseline", "baseline"], models: ["haiku"] })).toThrow(/distinct label/);
  });
});
