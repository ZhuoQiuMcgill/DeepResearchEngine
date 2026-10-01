import {
  createNode,
  executionOrder,
  roles,
  type Role,
  type Workflow,
} from "./workflow";

export function requestedWorkers(question: string): number | undefined {
  const match =
    question.match(
      /\b(\d+)\s*(?:sub[ -]?agents?|search\s+agents?|searchers?)\b/i,
    ) ||
    question.match(
      /(\d+)\s*(?:个|名)?\s*(?:搜索代理|搜索智能体|子代理|子智能体)/,
    );
  return match ? Number(match[1]) : undefined;
}
export function modelPlanToWorkflow(
  raw: unknown,
  question: string,
  title: string,
  model: string,
): Workflow {
  const plan = raw as { tasks?: unknown[] };
  if (
    !plan ||
    !Array.isArray(plan.tasks) ||
    plan.tasks.length < 1 ||
    plan.tasks.length > 64
  )
    throw new Error("The model must return 1–64 tasks. Canvas unchanged.");
  const edges: Workflow["edges"] = [];
  const nodes = plan.tasks.map((value: unknown) => {
    const t = value as {
      id: string;
      role: Role;
      label: string;
      instruction: string;
      dependsOn: string[];
    };
    if (
      !t ||
      typeof t.id !== "string" ||
      !/^[a-zA-Z0-9_-]{1,64}$/.test(t.id) ||
      !roles.includes(t.role) ||
      typeof t.label !== "string" ||
      !t.label.trim() ||
      t.label.length > 120 ||
      typeof t.instruction !== "string" ||
      !t.instruction.trim() ||
      t.instruction.length > 10000 ||
      !Array.isArray(t.dependsOn) ||
      t.dependsOn.some((id) => typeof id !== "string") ||
      new Set(t.dependsOn).size !== t.dependsOn.length
    )
      throw new Error(
        "The model returned an incomplete task. Canvas unchanged.",
      );
    for (const source of t.dependsOn)
      edges.push({
        id: `${source}>${t.id}`,
        source,
        target: t.id,
        type: "smoothstep",
      });
    const node = createNode(t.role, t.id, 0, 0);
    node.data = {
      ...node.data,
      label: t.label,
      description: t.instruction.slice(0, 160),
      prompt: `Research request:\n${question}\n\nTask:\n${t.instruction}`,
      model,
    };
    return node;
  });
  if (new Set(nodes.map((n) => n.id)).size !== nodes.length)
    throw new Error("The model repeated a task ID. Canvas unchanged.");
  const count = requestedWorkers(question);
  if (
    count !== undefined &&
    nodes.filter((n) => n.data.role === "Searcher").length !== count
  )
    throw new Error(
      `The model did not supply the requested ${count} search agents. Canvas unchanged. Try again.`,
    );
  const secondary = question.match(
    /(\d+)\s*(?:(?:sub[ -]?agents?|agents?)\s*)?(?:for\s+)?(?:verify|review|checking)\b/i,
  );
  if (
    secondary &&
    nodes.filter((n) => n.data.role === "Reader").length !==
      Number(secondary[1])
  )
    throw new Error(
      `The requested ${secondary[1]} reading tasks were not supplied. Canvas unchanged. Try planning again.`,
    );
  const order = executionOrder(nodes, edges);
  const depths = new Map<string, number>();
  const rows = new Map<number, number>();
  for (const id of order) {
    const parents = edges.filter((e) => e.target === id);
    const depth = parents.length
      ? 1 + Math.max(...parents.map((e) => depths.get(e.source)!))
      : 0;
    depths.set(id, depth);
    const row = rows.get(depth) || 0;
    rows.set(depth, row + 1);
    nodes.find((n) => n.id === id)!.position = { x: depth * 310, y: row * 230 };
  }
  return { version: 1, question, title, nodes, edges };
}
export async function requestModelPlan(
  question: string,
  title: string,
  signal: AbortSignal,
  profileRef?: string,
) {
  const response = await fetch("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, profileRef }),
    signal,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error || "Planner unavailable. Canvas unchanged.");
  const workflow = modelPlanToWorkflow(data.plan, question, title, data.model);
  const endings = workflow.nodes.filter(
    (n) => !workflow.edges.some((e) => e.source === n.id),
  );
  if (!endings.length || endings.some((n) => n.data.role !== "Writer"))
    throw new Error(
      "Every research branch must lead to a final Writer. Canvas unchanged. Try planning again.",
    );
  return {
    workflow,
    model: String(data.model),
  };
}
