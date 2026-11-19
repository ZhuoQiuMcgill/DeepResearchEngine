import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { HumanMessage } from '@langchain/core/messages';
import { createChatModel, getProfile } from '../config/models.js';
import { runOne } from '../platform/run.js';
import { inputFindings } from '../core/run-guardrails.js';
import { runPairedEvaluation, type ArmObservation } from './index.js';

/** A deliberately tiny boundary: no agent loop, tools, repair pass or retry. */
export async function invokeSingleTurn(model: {
  caller: object;
  invoke: (messages: HumanMessage[]) => Promise<{ content: unknown; usage_metadata?: { input_tokens?: number; output_tokens?: number }; tool_calls?: unknown[] }>;
}, prompt: string): Promise<ArmObservation> {
  // The shared factory enables retries by default. AsyncCaller reads this property
  // on each call; overriding it avoids multiple actual API attempts on failures.
  Object.assign(model.caller, { maxRetries: 0 });
  const started = Date.now();
  try {
    const message = await model.invoke([new HumanMessage(prompt)]);
    const output = typeof message.content === 'string' ? message.content : Array.isArray(message.content)
      ? message.content.filter((b): b is { type: string; text: string } => typeof b === 'object' && b !== null && 'type' in b && b.type === 'text' && 'text' in b && typeof b.text === 'string').map(b => b.text).join('\n') : '';
    if (message.tool_calls?.length) throw new Error('Unexpected tool call from a tool-free baseline.');
    return { status: 'ok', output, latencyMs: Date.now() - started, inputTokens: message.usage_metadata?.input_tokens ?? null, outputTokens: message.usage_metadata?.output_tokens ?? null, modelInvocations: 1, externalToolCalls: 0, guardrailEventCount: null };
  } catch {
    // Provider response bodies can include credentials or request internals.
    return { status: 'error', output: '', error: 'Direct model invocation failed; one invoke was attempted without retry. Actual provider execution is unknown.', latencyMs: Date.now() - started, inputTokens: null, outputTokens: null, modelInvocations: null, externalToolCalls: 0, guardrailEventCount: null };
  }
}

export async function runDirectBaseline(options: { prompt: string; profile: string }): Promise<ArmObservation> {
  const profile = getProfile(options.profile);
  const model = createChatModel(profile);
  return { ...await invokeSingleTurn(model, options.prompt), model: profile.model };
}

export async function runLiveEvaluation(options: {
  caseId: string;
  profile: string;
  researchersTotal: number;
  outDir: string;
  maxRounds?: number;
  concurrency?: number;
  researcherTimeoutMs?: number;
}) {
  getProfile(options.profile); // Validate before starting either arm.
  if (inputFindings({ question: 'evaluation', researchersTotal: options.researchersTotal, maxRounds: options.maxRounds ?? 2, concurrency: options.concurrency ?? 1, researcherTimeoutMs: options.researcherTimeoutMs ?? 180_000 }).length) {
    throw new Error('Evaluation run settings are outside supported bounds.');
  }
  const report = await runPairedEvaluation({
    caseId: options.caseId,
    profile: options.profile,
    baseline: prompt => runDirectBaseline({ prompt, profile: options.profile }),
    engine: async prompt => {
      const summary = await runOne({
        question: prompt,
        strategy: { name: 'ebd' },
        profile: options.profile,
        researchersTotal: options.researchersTotal,
        maxRounds: options.maxRounds ?? 2,
        concurrency: options.concurrency ?? 1,
        researcherTimeoutMs: options.researcherTimeoutMs ?? 180_000,
        outDir: options.outDir,
        tags: { evaluationCase: options.caseId, evaluationMode: 'live-paired' },
      });
      const output = await readFile(join(summary.dir, 'report.md'), 'utf8').catch(() => '');
      const usageObserved = Object.keys(summary.usageByRole).length > 0;
      // Guardrail telemetry is available in the defense integration overlay;
      // tolerate original pinned summaries where it does not exist.
      const guardrails = (summary as unknown as { guardrails?: unknown[] }).guardrails;
      return {
        status: summary.status,
        ...(summary.status === 'error' ? { error: 'Engine run failed; inspect its local run record.' } : {}),
        output, model: summary.model, latencyMs: summary.durationMs,
        inputTokens: usageObserved ? summary.totalTokens.input : null,
        outputTokens: usageObserved ? summary.totalTokens.output : null,
        modelInvocations: usageObserved ? Object.values(summary.usageByRole).reduce((n, u) => n + u.calls, 0) : null,
        externalToolCalls: usageObserved ? summary.searches + summary.pageReads : null,
        guardrailEventCount: guardrails?.length ?? null,
        artifacts: { runDir: summary.dir, summary: join(summary.dir, 'summary.json') },
      };
    },
  });
  await mkdir(options.outDir, { recursive: true });
  const reportPath = join(options.outDir, `evaluation-${options.caseId}-${Date.now()}.json`);
  const result = { ...report, reportPath, settings: { ...options, modelProfile: options.profile }, telemetryCaveats: ['Engine call counts come from usage-bearing completions; missing usage or failed attempts can undercount actual requests.', 'Engine external tool counts are provider-reported searches plus page reads; unavailable usage is null.'] };
  await writeFile(reportPath, JSON.stringify(result, null, 2) + '\n', 'utf8');
  return result;
}
