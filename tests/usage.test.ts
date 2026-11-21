import { describe, expect, it } from "vitest";
import { PROFILES } from "../src/config/models.js";
import { UsageLedger } from "../src/observability/usage.js";

describe("UsageLedger", () => {
  it("prices cached input at the cache rate when the profile has one", () => {
    const ledger = new UsageLedger(PROFILES.deepseek!.pricing);
    ledger.record("researcher", { inputTokens: 1_000_000, cachedInputTokens: 400_000, outputTokens: 1_000_000, searches: 3 });
    const r = ledger.byRole.researcher!;
    expect(r.cachedInputTokens).toBe(400_000);
    expect(r.searches).toBe(3);
    expect(r.costUsd).toBeCloseTo(0.6 * 0.15 + 0.4 * 0.003 + 0.6, 10);
  });

  it("keeps the previous cost for profiles without a cache rate", () => {
    const ledger = new UsageLedger(PROFILES.haiku!.pricing);
    ledger.record("writer", { inputTokens: 1_000_000, cachedInputTokens: 500_000, outputTokens: 1_000_000, searches: 2 });
    ledger.record("writer", { inputTokens: 1_000_000, outputTokens: 0 });
    expect(ledger.total().costUsd).toBeCloseTo(0.1 + 0.5 + 2 * 0.01 + 0.1, 10);
    expect(ledger.total().cachedInputTokens).toBe(500_000);
  });
});
