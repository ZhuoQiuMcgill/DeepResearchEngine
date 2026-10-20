import { describe, expect, it } from "vitest";
import { toolDefinitions } from "./tools.js";

type Node = Record<string, unknown>;

function walk(node: unknown, visit: (n: Node) => void): void {
  if (Array.isArray(node)) node.forEach((n) => walk(n, visit));
  else if (node && typeof node === "object") {
    visit(node as Node);
    Object.values(node).forEach((n) => walk(n, visit));
  }
}

describe("tool schemas sent to the providers (strict mode)", () => {
  const schemas = toolDefinitions().map((t) => t.function.parameters);

  it("are plain objects at the top, with every property required and no extra properties", () => {
    for (const s of schemas) {
      expect(s.type).toBe("object");
      expect(s).not.toHaveProperty("anyOf");
      expect(s).not.toHaveProperty("$schema");
      walk(s, (n) => {
        if (n.type === "object") {
          expect(n.additionalProperties).toBe(false);
          expect([...((n.required as string[]) ?? [])].sort()).toEqual(Object.keys((n.properties as Node) ?? {}).sort());
        }
      });
    }
  });

  it("set strictness per tool: the scan always, the submission only on request", () => {
    expect(toolDefinitions().map((t) => [t.function.name, t.strict, t.function.strict])).toEqual([["scan_request", true, true], ["submit_analysis", false, false]]);
    expect(toolDefinitions({ strictSubmit: true })[1]!.strict).toBe(true);
  });

  it("carry no length, count or format keywords, and few nullable fields", () => {
    let unions = 0;
    for (const s of schemas) {
      walk(s, (n) => {
        for (const k of ["minLength", "maxLength", "minItems", "maxItems", "pattern", "format"]) expect(n).not.toHaveProperty(k);
        if (Array.isArray(n.anyOf)) unions += 1;
      });
    }
    expect(unions).toBeLessThanOrEqual(16);
  });
});
