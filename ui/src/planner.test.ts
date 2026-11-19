import { describe, it, expect } from "vitest";
import { planRequest } from "./planner";
import { executionOrder, parseWorkflow } from "./workflow";

describe("request planning", () => {
  it("branches explicit topics and joins all readers before writing", () => {
    const plan = planRequest("太阳能成本；储能方案；部署条件");
    expect(
      plan.nodes
        .filter((n) => n.data.role === "Searcher")
        .map((n) => n.data.label),
    ).toEqual(["太阳能成本", "储能方案", "部署条件"]);
    expect(plan.edges.filter((e) => e.target === "organizer")).toHaveLength(3);
    const order = executionOrder(plan.nodes, plan.edges);
    expect(order.indexOf("organizer")).toBeGreaterThan(order.indexOf("read-2"));
    expect(order.at(-1)).toBe("writer");
    expect(parseWorkflow(JSON.stringify(plan)).nodes).toHaveLength(10);
  });
  it("keeps the full request in every task and uses three default angles", () => {
    const question = "Compare urban transport options in Toronto";
    const plan = planRequest(question, "Course project");
    expect(plan.title).toBe("Course project");
    expect(plan.nodes.every((n) => n.data.prompt.includes(question))).toBe(
      true,
    );
    expect(plan.nodes.filter((n) => n.data.role === "Searcher")).toHaveLength(
      3,
    );
  });
  it("deduplicates explicit topics and refuses empty or oversized requests", () => {
    expect(
      planRequest("alpha;beta;alpha").nodes.filter(
        (n) => n.data.role === "Searcher",
      ),
    ).toHaveLength(2);
    expect(() => planRequest(" ")).toThrow();
    expect(() => planRequest("a".repeat(6001))).toThrow();
    expect(() =>
      planRequest(Array.from({ length: 9 }, (_, i) => String(i)).join(";")),
    ).toThrow();
  });
});
