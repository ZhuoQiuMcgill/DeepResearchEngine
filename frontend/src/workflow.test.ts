import { describe, it, expect } from "vitest";
import {
  initial,
  parseWorkflow,
  executionOrder,
  clean,
  demoOutput,
} from "./workflow";
describe("workflow integrity", () => {
  it("executes every dependency before its consumer", () => {
    const w = initial();
    const order = executionOrder(w.nodes, w.edges);
    for (const e of w.edges)
      expect(order.indexOf(e.source)).toBeLessThan(order.indexOf(e.target));
  });
  it("rejects cycles and dangling edges", () => {
    const w = initial();
    expect(() =>
      executionOrder(w.nodes, [
        ...w.edges,
        { id: "cycle", source: "n5", target: "n0" },
      ]),
    ).toThrow("circular");
    expect(() =>
      executionOrder(w.nodes, [{ id: "bad", source: "missing", target: "n0" }]),
    ).toThrow("missing");
  });
  it("supports multiple independent branches and empty editor import", () => {
    const w = initial();
    expect(executionOrder(w.nodes, [])).toHaveLength(6);
    expect(
      parseWorkflow(JSON.stringify({ ...w, nodes: [], edges: [] })).nodes,
    ).toHaveLength(0);
    expect(() => executionOrder([], [])).toThrow("Add");
  });
  it("round trips exported topology and node instructions", () => {
    const w = initial();
    w.nodes[1].data.prompt = "Use only primary sources";
    const got = parseWorkflow(JSON.stringify(w));
    expect(got).toEqual(w);
  });
  it("rejects duplicate IDs, invalid roles and duplicate links", () => {
    const w = initial();
    expect(() =>
      parseWorkflow(JSON.stringify({ ...w, nodes: [...w.nodes, w.nodes[0]] })),
    ).toThrow("unique");
    const invalid = structuredClone(w);
    (invalid.nodes[0].data as any).role = "unknown";
    expect(() => parseWorkflow(JSON.stringify(invalid))).toThrow(
      "configuration",
    );
    expect(() =>
      parseWorkflow(
        JSON.stringify({
          ...w,
          edges: [...w.edges, { ...w.edges[0], id: "extra" }],
        }),
      ),
    ).toThrow("Duplicate");
  });
  it("rejects nonfinite coordinates and out of range budgets", () => {
    const w = initial();
    w.nodes[0].data.budget = -1;
    expect(() => parseWorkflow(JSON.stringify(w))).toThrow("configuration");
    w.nodes[0].data.budget = 20;
    w.nodes[0].position.x = Infinity;
    expect(() => parseWorkflow(JSON.stringify(w))).toThrow("configuration");
  });
  it("clears execution artifacts from editable exports", () => {
    const w = initial();
    w.nodes[0].data.status = "done";
    w.nodes[0].data.output = "Old data";
    expect(clean(w).nodes[0].data.status).toBe("idle");
    expect(clean(w).nodes[0].data.output).toBeUndefined();
    expect(w.nodes[0].data.status).toBe("done");
  });
  it("labels demonstration output and carries configured instructions", () => {
    const w = initial();
    w.nodes[0].data.prompt = "Distinct instruction";
    const output = demoOutput(w.nodes[0], "Example question", ["evidence"]);
    expect(output).toContain("SIMULATED");
    expect(output).toContain("Distinct instruction");
    expect(output).toContain("received: 1");
  });
});

it("preserves resized node dimensions through save and import", () => {
  const graph = initial();
  graph.nodes[0].width = 360;
  graph.nodes[0].height = 240;
  const restored = parseWorkflow(JSON.stringify(clean(graph)));
  expect(restored.nodes[0].width).toBe(360);
  expect(restored.nodes[0].height).toBe(240);
  expect(restored.nodes[0].style).toEqual({ width: 360, height: 240 });
});
