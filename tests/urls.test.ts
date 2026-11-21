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

  it("treats percent-escapes of the same character as the same page", () => {
    const base = "https://education.designsociety.org/publication/46376/Environment-based+design+";
    const raw = `${base}(EBD):+Using`;
    expect(urlKey(`${base}%28EBD%29%3A+Using`)).toBe(urlKey(raw));
    expect(urlKey(`${base}%28EBD%29%3a+Using`)).toBe(urlKey(raw));
    expect(urlKey("https://a.org/x?q=author%3A%28Nguyen%29")).toBe(urlKey("https://a.org/x?q=author:(Nguyen)"));
    expect(urlKey("https://a.org/caf%C3%A9")).toBe(urlKey("https://a.org/café"));
  });

  it("keeps escapes that change a URL's structure", () => {
    expect(urlKey("https://a.org/a%2Fb")).not.toBe(urlKey("https://a.org/a/b"));
    expect(urlKey("https://a.org/a%2fb")).toBe(urlKey("https://a.org/a%2Fb"));
    expect(urlKey("https://a.org/x?q=a%26b")).not.toBe(urlKey("https://a.org/x?q=a&b"));
    expect(urlKey("https://a.org/x?q=1%2B1")).not.toBe(urlKey("https://a.org/x?q=1+1"));
  });

  it("keeps a malformed escape instead of failing", () => {
    // %E0%A4 is a truncated UTF-8 sequence: decodeURIComponent throws on it.
    expect(urlKey("https://a.org/bad%E0%A4x")).toBe(urlKey("https://a.org/bad%e0%a4x"));
    expect(urlKey("https://a.org/bad%E0%A4x")).toBe("a.org/bad%E0%A4x");
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
