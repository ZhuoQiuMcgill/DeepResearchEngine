import { describe, it, expect } from "vitest";
import { parseSearch } from "../server/execution";
import { modelPlanToWorkflow } from "./aiPlanner";
describe("live research inputs", () => {
  it("extracts distinct public result links and plain snippets", () => {
    const html =
      '<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Freactflow.dev%2F">React Flow</a><div class="result__snippet">Node <b>editor</b></div></div>';
    expect(parseSearch(html + html, 3)).toEqual([
      {
        title: "React Flow",
        url: "https://reactflow.dev/",
        snippet: "Node editor",
      },
    ]);
    expect(parseSearch("<form>Rate limited</form>", 3)).toEqual([]);
  });
  it("refuses missing second-stage workers", () => {
    const tasks = [
      {
        id: "s",
        role: "Searcher",
        label: "Search",
        instruction: "Find sources",
        dependsOn: [],
      },
    ];
    expect(() =>
      modelPlanToWorkflow(
        { tasks },
        "use 1 subagent for search and 8 for verify",
        "Research",
        "model",
      ),
    ).toThrow("8 reading tasks");
    const readers = Array.from({ length: 8 }, (_, i) => ({
      id: `r${i}`,
      role: "Reader",
      label: `Read ${i}`,
      instruction: "Compare sources",
      dependsOn: ["s"],
    }));
    expect(
      modelPlanToWorkflow(
        { tasks: [...tasks, ...readers] },
        "use 1 subagent for search and 8 for verify",
        "Research",
        "model",
      ).nodes,
    ).toHaveLength(9);
  });
});
