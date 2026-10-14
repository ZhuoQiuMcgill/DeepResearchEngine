import { describe, expect, it } from "vitest";
import { cleanUrl, cleanUrlsInText, extractUrls, urlKey } from "../src/core/urls.js";

describe("urls", () => {
  it("removes tracking parameters only", () => {
    expect(cleanUrl("https://a.org/x?utm_source=openai")).toBe("https://a.org/x");
    expect(cleanUrl("https://a.org/x?id=3&utm_source=openai")).toBe("https://a.org/x?id=3");
    expect(cleanUrlsInText("see [S](https://a.org/x?utm_source=openai).")).toBe("see [S](https://a.org/x).");
  });

  it("compares URLs loosely", () => {
    expect(urlKey("https://www.a.org/x/")).toBe(urlKey("http://a.org/x#frag"));
  });

  it("keeps balanced parentheses inside URLs", () => {
    const u = "https://www.semanticscholar.org/paper/ENVIRONMENT-BASED-DESIGN-(EBD)-Zeng/8958";
    expect(extractUrls(`see ([Semantic Scholar](${u})).`)).toEqual([u]);
    expect(extractUrls(`(${u})`)).toEqual([u]);
    expect(cleanUrlsInText(`[S](${u}?utm_source=openai))`)).toBe(`[S](${u}))`);
  });

  it("extracts link targets and bare URLs", () => {
    expect(extractUrls("A ([Source](https://a.org/x)) and https://b.org/y.").sort()).toEqual(["https://a.org/x", "https://b.org/y"]);
  });
});
