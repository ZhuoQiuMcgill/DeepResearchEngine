import { describe, expect, it, vi } from 'vitest';
import { evaluationCases, evaluationPrompt, runFixtureReplay, runPairedEvaluation, scoreOutput } from '../src/evaluation/index.js';
import { invokeSingleTurn } from '../src/evaluation/live.js';
import type { HumanMessage } from '@langchain/core/messages';

describe('Module 7 deterministic evaluation', () => {
  it('scores labeled references without claiming model observations', () => {
    const replay = runFixtureReplay();
    expect(replay.mode).toBe('fixture-replay');
    expect(replay.guardrailChecks.benignReportPreserved).toBe(true);
    expect(replay.guardrailChecks.directInstructionQuarantined).toBe(true);
    for (const test of replay.cases) for (const ref of test.referenceOutputs) {
      expect(ref.score.taskSuccess).toBe(ref.label === 'passing-reference');
      expect(Object.values(ref.metrics).every(v => v === null)).toBe(true);
    }
  });
  it('fails empty and partially grounded outputs', () => {
    expect(scoreOutput('dated-conflict', '').rubricScore).toBe(0);
    expect(scoreOutput('untrusted-report', '9 of 10 samples passed; one failed [S1]. The cause was contamination.').taskSuccess).toBe(false);
    expect(() => scoreOutput('unknown', '')).toThrow('Unknown evaluation case');
  });
  it('passes the exact same preserved prompt to both arms and keeps missing metrics null', async () => {
    const run = vi.fn(async (_prompt: string) => ({ output: 'test' }));
    const report = await runPairedEvaluation({ caseId: 'dated-conflict', profile: 'luna', engine: run, baseline: run });
    expect(run).toHaveBeenCalledTimes(2);
    expect(run.mock.calls[0]).toEqual(run.mock.calls[1]);
    expect(run.mock.calls[0]?.[0]).toBe(evaluationPrompt(evaluationCases[0]!));
    expect(report.arms[0]?.metrics.latencyMs).toBe(null);
  });
  it('makes one tool-free model invocation, disables retries and records reported tokens', async () => {
    const invoke = vi.fn(async (_messages: HumanMessage[]) => ({ content: 'answer', usage_metadata: { input_tokens: 11, output_tokens: 7 } }));
    const caller = { maxRetries: 2 };
    const result = await invokeSingleTurn({ caller, invoke }, 'verbatim question');
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke.mock.calls[0]?.[0]?.[0]?.content).toBe('verbatim question');
    expect(caller.maxRetries).toBe(0);
    expect(result).toMatchObject({ output: 'answer', modelInvocations: 1, externalToolCalls: 0, inputTokens: 11, outputTokens: 7 });
  });
  it('does not retry, score or fabricate tokens after model failure', async () => {
    const invoke = vi.fn(async () => { throw new Error('provider failed'); });
    const result = await invokeSingleTurn({ caller: {}, invoke }, 'test');
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(result.status).toBe('error');
    expect(result.inputTokens).toBe(null);
    const report = await runPairedEvaluation({ caseId: 'untrusted-report', profile: 'luna', engine: async () => result, baseline: async () => result });
    expect(report.arms.every(arm => arm.score === null)).toBe(true);
  });
});
