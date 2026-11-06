import { describe, expect, it } from "vitest";
import { scanRequest, spanWords } from "./scan.js";

const TODAY = "2026-10-19";
const find = (q: string, text: string) => scanRequest(q, TODAY).spans.find((s) => s.text === text);

describe("never-drop scan", () => {
  it("finds restrictors, date limits, number words and names (Lab 2 TC6)", () => {
    const q =
      "Compare the use, cost and performance of Nvidia and AMD flagship GPUs. I need a one-page summary for my lab's purchasing decision, using only benchmark results published in 2025 or later.";
    expect(find(q, "only")?.kind).toBe("restrictor");
    expect(find(q, "2025 or later")).toMatchObject({ kind: "relative_time", window: { from: "2025-01-01", to: TODAY } });
    expect(find(q, "one-page")?.kind).toBe("number");
    expect(find(q, "Nvidia")?.kind).toBe("name");
    expect(find(q, "AMD")?.kind).toBe("name");
    expect(scanRequest(q, TODAY).spans.some((s) => s.text === "I" || s.text === "2025")).toBe(false);
  });

  it("keeps an acronym with its expansion, in either order", () => {
    expect(find("What is EBD (Environment Based Design)?", "EBD (Environment Based Design)")?.kind).toBe("acronym_pair");
    expect(find("What is Environment Based Design (EBD)?", "Environment Based Design (EBD)")?.kind).toBe("acronym_pair");
    expect(spanWords({ text: "EBD (Environment Based Design)" })).toEqual(["ebd", "environment", "based", "design"]);
  });

  it("resolves relative time against the run date", () => {
    expect(find("How has Mercury's market share changed since 2022?", "since 2022")?.window).toEqual({ from: "2022-01-01", to: TODAY });
    expect(find("How has Mercury's market share changed since 2022?", "Mercury")?.kind).toBe("name");
    expect(find("What changed in recent days?", "in recent days")?.window).toEqual({ from: "2026-09-19", to: TODAY });
    expect(find("What happened last year?", "last year")?.window).toEqual({ from: "2025-01-01", to: "2025-12-31" });
    expect(find("Prices over the past 3 months", "the past 3 months")?.window).toEqual({ from: "2026-07-19", to: TODAY });
  });

  it("skips sentence openers but keeps acronyms and mixed-case names", () => {
    const spans = scanRequest("How do I flight from GuangZhou to Montreal?", TODAY).spans.map((s) => s.text);
    expect(spans).toEqual(["How", "GuangZhou", "Montreal"]);
    expect(find("compare meta quest 3 and apple vision pro", "3")?.kind).toBe("number");
  });

  it("is deterministic", () => {
    const q = "Why did the EU ban open-source LLMs in 2025, and how has the ban affected European AI startups?";
    expect(scanRequest(q, TODAY)).toEqual(scanRequest(q, TODAY));
  });
});
