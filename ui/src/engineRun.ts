type RecordValue = Record<string, unknown>;

export interface RunFile {
  name: string;
  webkitRelativePath?: string;
  size?: number;
  text(): Promise<string>;
}

export interface EngineBrief {
  id: string;
  objective: string;
  keyQuestions: string[];
}

export interface EngineDecision {
  phase: "init" | "observe";
  round: number;
  nextRound: number;
  rationale: string;
  stop: boolean;
  accepted: EngineBrief[];
  dropped: number;
  ignored: number;
  invalid: number;
  budgetBefore?: number;
  actions: string[];
}

export interface EngineGoal {
  id: string;
  text: string;
  status: string;
  need: string;
  doneWhen?: string;
  createdRound?: number;
  partsMet?: number;
  partsTotal?: number;
  missing: string[];
  evidenceIds: string[];
}

export interface EngineConflict {
  id: string;
  statement: string;
  type: string;
  status: string;
  sideA: string[];
  sideB: string[];
  settleGoal?: string;
  condition?: string;
}

export interface EngineEvidence {
  id: string;
  text: string;
  kind: string;
  briefId: string;
  round?: number;
  goalIds: string[];
  hosts: string[];
}

export interface EngineSource {
  url: string;
  title?: string;
  cited: boolean;
  briefIds: string[];
}

export interface EngineResult {
  id: string;
  round?: number;
  objective: string;
  status: string;
  notes?: string;
  failure?: string;
  queries: string[];
  sources: EngineSource[];
  diagnostics: string[];
}

export interface EngineRun {
  runId: string;
  reviewKey?: string;
  question: string;
  strategy: string;
  strategyName?: string;
  profile?: string;
  model?: string;
  status: "ok" | "error" | "unreported";
  commit?: string;
  stopReason?: string;
  stopKind?: string;
  researchersUsed?: number;
  researchersBudget?: number;
  roundCount?: number;
  report?: string;
  decisions: EngineDecision[];
  goals: EngineGoal[];
  conflicts: EngineConflict[];
  evidence: EngineEvidence[];
  results: EngineResult[];
  sources: EngineSource[];
  warnings: string[];
  assumptions: { id: string; claim: string; verdict?: string }[];
  writerInput?: {
    guidance?: string;
    outline: string[];
    materials: { label: string; notes: string }[];
    diagnostics: string[];
  };
  metrics: {
    searches?: number;
    pageReads?: number;
    inputTokens?: number;
    outputTokens?: number;
    costUsd?: number;
    durationMs?: number;
  };
}

const knownFiles = new Set([
  "summary.json",
  "config.json",
  "report.md",
  "events.jsonl",
  "question.txt",
  "synthesis.json",
  "guardrails.json",
  "error.txt",
]);
const resultFile = /^r\d+-b\d+\.(?:json|md)$/;
const maxBytes = 64 * 1024 * 1024;
const settledGoalStatuses = new Set([
  "answered",
  "exhausted",
  "disputed",
  "moot",
]);
const verdictPriority = ["contradicted", "unsettled", "supported"] as const;

function record(value: unknown): RecordValue {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordValue)
    : {};
}

function string(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function strings(value: unknown): string[] {
  return list(value)
    .map(string)
    .filter((item) => item !== undefined);
}

function mapRecords<T>(
  value: unknown,
  parse: (item: RecordValue) => T | undefined,
): T[] {
  return list(value).flatMap((item) => {
    const parsed = parse(record(item));
    return parsed === undefined ? [] : [parsed];
  });
}

function parseJson(raw: string): unknown {
  return JSON.parse(raw.replace(/^\uFEFF/, ""));
}

function asBrief(item: RecordValue): EngineBrief | undefined {
  const id = string(item.id);
  return id
    ? {
        id,
        objective: string(item.objective) ?? "",
        keyQuestions: strings(item.keyQuestions),
      }
    : undefined;
}

function asGoal(item: RecordValue): EngineGoal | undefined {
  const id = string(item.id);
  const text = string(item.text);
  return id && text
    ? {
        id,
        text,
        status: string(item.status) ?? "unreported",
        need: string(item.need) ?? "unreported",
        doneWhen: string(item.doneWhen),
        createdRound: number(item.createdRound),
        partsMet: number(item.partsMet),
        partsTotal: number(item.partsTotal),
        missing: strings(item.missing),
        evidenceIds: strings(item.evidence),
      }
    : undefined;
}

function asConflict(item: RecordValue): EngineConflict | undefined {
  const id = string(item.id);
  const statement = string(item.statement);
  return id && statement
    ? {
        id,
        statement,
        type: string(item.type) ?? "unreported",
        status: string(item.status) ?? "unreported",
        sideA: strings(item.sideA),
        sideB: strings(item.sideB),
        settleGoal: string(item.settleGoal),
        condition: string(item.condition),
      }
    : undefined;
}

function asEvidence(item: RecordValue): EngineEvidence | undefined {
  const id = string(item.id);
  const text = string(item.text);
  const briefId = string(item.briefId);
  return id && text && briefId
    ? {
        id,
        text,
        briefId,
        round: number(item.round),
        kind: string(item.kind) ?? "unreported",
        goalIds: strings(item.goalIds),
        hosts: strings(item.hosts),
      }
    : undefined;
}

function asSource(
  item: RecordValue,
  briefId: string,
): EngineSource | undefined {
  const raw = string(item.url);
  if (!raw) return;
  try {
    const url = new URL(raw);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password
    )
      return;
    return {
      url: url.href,
      title: string(item.title),
      cited: item.cited === true,
      briefIds: [briefId],
    };
  } catch {
    return;
  }
}

function pickFiles(files: ArrayLike<RunFile>) {
  const selected = new Map<string, RunFile>();
  const roots = new Set<string>();
  let bytes = 0;
  for (const file of Array.from(files)) {
    const path = file.webkitRelativePath || file.name;
    const segments = path.split("/");
    const inResults = segments.at(-2) === "results";
    const root = segments.slice(0, inResults ? -2 : -1).join("/");
    const name = segments.at(-1) ?? "";
    const isResult =
      resultFile.test(name) && (inResults || segments.length === 1);
    if (!isResult && (inResults || !knownFiles.has(name))) continue;
    const key = isResult ? "results/" + name : name;
    if (selected.has(key))
      throw new Error("Choose a single Engine run folder.");
    selected.set(key, file);
    if (root) roots.add(root);
    bytes += file.size ?? 0;
  }
  if (roots.size > 1)
    throw new Error(
      "Choose a single Engine run folder, not its parent folder.",
    );
  if (bytes > maxBytes)
    throw new Error("The selected run files exceed 64 MiB.");
  return { selected, folder: [...roots][0]?.split("/").at(-1) };
}

/**
 * Read one TypeScript DeepResearchEngine run directory. The app uses the
 * recorder's JSON and Markdown files and does not depend on Langfuse.
 */
export async function importEngineRun(
  files: ArrayLike<RunFile>,
): Promise<EngineRun> {
  const { selected, folder } = pickFiles(files);
  const data = new Map(
    await Promise.all(
      [...selected].map(
        async ([name, file]) => [name, await file.text()] as const,
      ),
    ),
  );
  const warnings: string[] = [];
  function json(name: string) {
    const raw = data.get(name);
    if (raw === undefined) return {};
    try {
      return record(parseJson(raw));
    } catch {
      warnings.push(name + " could not be read.");
      return {};
    }
  }

  const summary = json("summary.json");
  const config = json("config.json");
  const settings = record(config.profile);
  const strategy = { ...record(config.strategy), ...record(summary.strategy) };
  const code = { ...record(config.code), ...record(summary.code) };
  const question =
    string(summary.question) ??
    string(config.question) ??
    string(data.get("question.txt"));
  const strategyName = string(strategy.name);
  const strategyLabel = string(strategy.label) ?? strategyName;
  if (!question || !strategyLabel) {
    throw new Error(
      "Choose an Engine run folder containing summary.json or config.json with the question and strategy.",
    );
  }

  const decisions: EngineDecision[] = [];
  let latestState: RecordValue = {};
  let malformedEvents = 0;
  for (const line of (data.get("events.jsonl") ?? "").split(/\r?\n/)) {
    if (!line.trim()) continue;
    let event: RecordValue;
    try {
      event = record(parseJson(line));
    } catch {
      malformedEvents++;
      continue;
    }
    if (event.type !== "decision") continue;
    const decision = record(event.data);
    const phase = decision.phase;
    const nextRound = number(decision.round);
    if ((phase !== "init" && phase !== "observe") || nextRound === undefined) {
      malformedEvents++;
      continue;
    }
    const state = record(decision.strategyState);
    const step = record(state.step);
    if (Object.keys(state).length) latestState = state;
    decisions.push({
      phase,
      round:
        phase === "init"
          ? 0
          : (number(step.round) ?? Math.max(0, nextRound - 1)),
      nextRound,
      rationale: string(decision.rationale) ?? "",
      stop: decision.stop === true,
      accepted: mapRecords(decision.accepted, asBrief),
      dropped: list(decision.dropped).length,
      ignored: list(decision.ignored).length,
      invalid: list(decision.invalid).length,
      budgetBefore: number(decision.budgetBefore),
      actions: strings(step.events),
    });
  }
  if (malformedEvents)
    warnings.push(
      "Unreadable records in events.jsonl: " + malformedEvents + ".",
    );

  const results: EngineResult[] = [];
  const sources = new Map<string, EngineSource>();
  for (const name of data.keys()) {
    if (!name.startsWith("results/") || !name.endsWith(".json")) continue;
    const result = json(name);
    const brief = record(result.brief);
    const id = string(brief.id);
    if (!id) continue;
    const found = mapRecords(result.sources, (item) => asSource(item, id));
    for (const source of found) {
      const saved = sources.get(source.url);
      if (saved) {
        saved.cited ||= source.cited;
        saved.title ??= source.title;
        if (!saved.briefIds.includes(id)) saved.briefIds.push(id);
      } else {
        sources.set(source.url, { ...source, briefIds: [id] });
      }
    }
    results.push({
      id,
      round: number(brief.round),
      objective: string(brief.objective) ?? "",
      status: string(result.status) ?? "unreported",
      notes:
        string(result.notes) ??
        string(data.get(name.replace(/\.json$/, ".md"))),
      failure: string(record(result.failure).message),
      queries: strings(result.queries),
      sources: found,
      diagnostics: strings(result.diagnostics),
    });
  }
  results.sort((a, b) =>
    a.id.localeCompare(b.id, undefined, { numeric: true }),
  );

  const error =
    string(summary.error) ??
    string(data.get("error.txt"))?.split(/\r?\n/, 1)[0];
  if (error) warnings.push(error);
  const failedResults = results.filter((result) => result.status === "failed");
  const failuresReported = number(record(summary.results).failed) ?? 0;
  if (failuresReported > failedResults.length) {
    warnings.push("Researcher failures recorded: " + failuresReported + ".");
  }
  for (const result of failedResults) {
    warnings.push(
      "Researcher " +
        result.id +
        " failed." +
        (result.failure ? " " + result.failure : ""),
    );
  }
  for (const unknownUrl of strings(record(summary.citationCheck).unknownUrls)) {
    warnings.push("URL is missing from the source record: " + unknownUrl);
  }
  const guardrails = summary.guardrails ?? json("guardrails.json");
  for (const item of list(guardrails)) {
    const finding = record(item);
    const action = string(finding.action);
    const phase = string(finding.phase);
    const message = string(finding.message);
    const count = number(finding.count);
    if (action && phase && message && count) {
      warnings.push(`Guardrail (${phase}, ${action}, ${count}): ${message}`);
    }
  }
  warnings.push(
    ...strings(summary.diagnostics),
    ...strings(latestState.problems),
  );
  const analysis = record(latestState.analysis);
  if (record(latestState.init).fallback === true) {
    warnings.push("Request analysis used its fallback.");
  }
  for (const flag of list(analysis.flags)) {
    const item = record(flag);
    const type = string(item.type);
    const detail = string(item.detail);
    if (type && detail)
      warnings.push(type.replaceAll("_", " ") + ": " + detail);
  }

  const verdicts = new Map<string, Set<string>>();
  for (const value of list(latestState.goals)) {
    const goal = record(value);
    const status = string(goal.status);
    if (!status || !settledGoalStatuses.has(status)) continue;
    const byAssumption =
      goal.verdicts == null
        ? Object.fromEntries(
            strings(goal.verifies).map((id) => [id, goal.verdict]),
          )
        : record(goal.verdicts);
    for (const [id, value] of Object.entries(byAssumption)) {
      const verdict = string(value);
      if (!verdict) continue;
      const existing = verdicts.get(id) ?? new Set<string>();
      existing.add(verdict);
      verdicts.set(id, existing);
    }
  }
  const assumptions = mapRecords(analysis.assumptions, (item) => {
    const id = string(item.id);
    const claim = string(item.claim);
    return id && claim
      ? {
          id,
          claim,
          verdict: verdictPriority.find((value) =>
            verdicts.get(id)?.has(value),
          ),
        }
      : undefined;
  });
  const synthesis = json("synthesis.json");
  const writer = record(synthesis.synthesis);
  const materials = mapRecords(writer.material, (item) => {
    const label = string(item.label);
    const notes = string(item.notes);
    return label && notes ? { label, notes } : undefined;
  });
  const stop = record(latestState.stop);
  const tokens = record(summary.totalTokens);
  const status =
    summary.status === "ok"
      ? "ok"
      : summary.status === "error" || error
        ? "error"
        : "unreported";
  const reviewKey = string(summary.runId) ?? string(config.runId) ?? folder;
  return {
    runId: reviewKey ?? "Imported run",
    reviewKey,
    question,
    strategy: strategyLabel,
    strategyName,
    profile:
      string(summary.profile) ??
      string(settings.name) ??
      string(config.profile),
    model: string(summary.model) ?? string(settings.model),
    status,
    commit: string(code.commit),
    stopReason: string(stop.reason) ?? string(summary.stopReason),
    stopKind: string(stop.kind) ?? string(summary.stopReason),
    researchersUsed: number(summary.researchersUsed),
    researchersBudget:
      number(summary.researchersBudget) ?? number(config.researchersTotal),
    roundCount: number(summary.rounds) ?? number(latestState.roundsObserved),
    report: string(data.get("report.md")),
    decisions,
    goals: mapRecords(latestState.goals, asGoal),
    conflicts: mapRecords(latestState.conflicts, asConflict),
    evidence: mapRecords(latestState.evidence, asEvidence),
    results,
    sources: [...sources.values()],
    warnings: [...new Set(warnings)],
    assumptions,
    writerInput:
      data.has("synthesis.json") && Object.keys(writer).length
        ? {
            guidance: string(writer.guidance),
            outline: strings(writer.outline),
            materials,
            diagnostics: strings(synthesis.diagnostics),
          }
        : undefined,
    metrics: {
      searches: number(summary.searches),
      pageReads: number(summary.pageReads),
      inputTokens: number(tokens.input),
      outputTokens: number(tokens.output),
      costUsd: number(summary.costUsdEstimate),
      durationMs: number(summary.durationMs),
    },
  };
}
