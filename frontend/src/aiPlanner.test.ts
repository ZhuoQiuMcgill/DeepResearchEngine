import { describe, it, expect } from "vitest";
import { modelPlanToWorkflow, requestedWorkers } from "./aiPlanner";
const task = (id: string, dependsOn: string[] = []) => ({
  id,
  role: "Searcher",
  label: `Topic ${id}`,
  instruction: `Search the specific topic ${id}`,
  dependsOn,
});
describe("AI task graph", () => {
  it("uses the returned tasks rather than a fixed template", () => {
    expect(
      modelPlanToWorkflow(
        { tasks: [task("one")] },
        "use 1 subagent for search",
        "demo",
        "model-a",
      ).nodes,
    ).toHaveLength(1);
    const tasks = Array.from({ length: 7 }, (_, i) => task(`s${i}`));
    const graph = modelPlanToWorkflow(
      { tasks },
      "use 7 subagent for search",
      "demo",
      "model-a",
    );
    expect(graph.nodes).toHaveLength(7);
    expect(graph.nodes[6].position.y).toBeGreaterThan(
      graph.nodes[0].position.y,
    );
    expect(graph.nodes[0].data.model).toBe("model-a");
  });
  it("refuses ignored worker counts, malformed tasks and broken graphs", () => {
    expect(() =>
      modelPlanToWorkflow(
        { tasks: [task("a")] },
        "use 7 subagent",
        "demo",
        "x",
      ),
    ).toThrow("7");
    expect(() =>
      modelPlanToWorkflow(
        { tasks: [task("a", ["b"]), task("b", ["a"])] },
        "topic",
        "demo",
        "x",
      ),
    ).toThrow();
    expect(() =>
      modelPlanToWorkflow(
        { tasks: [task("a", ["missing"])] },
        "topic",
        "demo",
        "x",
      ),
    ).toThrow();
    expect(() =>
      modelPlanToWorkflow(
        { tasks: [task("a"), task("a")] },
        "topic",
        "demo",
        "x",
      ),
    ).toThrow();
    expect(() =>
      modelPlanToWorkflow(
        { tasks: [{ ...task("a"), instruction: "" }] },
        "topic",
        "demo",
        "x",
      ),
    ).toThrow();
  });
  it("recognizes common explicit count requests", () => {
    expect(requestedWorkers("用7个搜索智能体研究")).toBe(7);
    expect(requestedWorkers("Use 7 sub-agents")).toBe(7);
    expect(requestedWorkers("研究2026年的技术")).toBeUndefined();
  });
});
