import { expect, it } from "vitest";
import {
  nodePerformance,
  type Snapshot,
  type NodePerformance,
} from "./PerformancePanel";
import { freshMetrics } from "../server/telemetry";
const saved: NodePerformance = {
  model: "node-model",
  runtime: { context: 262144, slots: 1, engine: "NInfer" },
  metrics: { ...freshMetrics(), phase: "complete", outputTokens: 42 },
  config: { temperature: 0, maxOutputTokens: 6000, thinking: "off" },
};
const live: Snapshot = {
  ...saved,
  requestId: "request-b",
  busy: true,
  metrics: { ...saved.metrics, outputTokens: 99 },
  usage: { requests: 1, inputTokens: 1, outputTokens: 99 },
};
it("does not show another node or planning request as selected node performance", () => {
  expect(
    nodePerformance([{ id: "request-a", status: "running" }], live),
  ).toBeUndefined();
  expect(
    nodePerformance([{ id: "request-b", status: "running" }], live)?.metrics
      .outputTokens,
  ).toBe(99);
});
it("keeps historical metrics and leaves legacy runs empty", () => {
  expect(
    nodePerformance([{ id: "done", status: "done", performance: saved }], live)
      ?.metrics.outputTokens,
  ).toBe(42);
  expect(
    nodePerformance([{ id: "legacy", status: "done" }], live),
  ).toBeUndefined();
  expect(
    nodePerformance([{ id: "request-b", status: "running" }], null),
  ).toBeUndefined();
});
