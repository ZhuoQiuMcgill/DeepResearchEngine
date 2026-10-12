import { describe, it, expect } from "vitest";
import { localProfile, createChatModel } from "../src/config/models.js";
import { searchCorpus } from "../src/research/local-corpus.js";
import { tracingBaseURL } from "../src/observability/langfuse.js";
describe("local research configuration", () => {
  it("uses Chat Completions on loopback with a 256K default and no cloud key", () => {
    const p = localProfile({});
    expect(p.contextWindowTokens).toBe(262144);
    const model = createChatModel(p) as any;
    expect(model.useResponsesApi).toBe(false);
    expect(model.clientConfig.baseURL).toBe("http://127.0.0.1:18086/v1");
    expect(p.pricing.inputPerM(100)).toBe(0);
  });
  it("rejects nonlocal model and tracing endpoints, including URL credentials", () => {
    for (const url of ["https://api.openai.com/v1", "http://user:secret@localhost:8080/v1"])
      expect(() => localProfile({ LOCAL_MODEL_BASE_URL: url })).toThrow(/loopback/);
    expect(() => tracingBaseURL({ LANGFUSE_BASE_URL: "https://cloud.langfuse.com" })).toThrow(/loopback/);
  });
  it("finds only supplied papers and does not fabricate matches", () => {
    const docs = [{ id: "a", title: "Environment Based Design", url: "https://doi.org/10.1/example",
      text: "Design proceeds through environment analysis and conflict identification.", sha256: "test" }];
    expect(searchCorpus(docs, "conflict")[0]?.id).toBe("a");
    expect(searchCorpus(docs, "football")).toEqual([]);
  });
});
