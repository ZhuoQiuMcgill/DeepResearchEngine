import type { NodePerformance } from "./PerformancePanel";
import { migrateLegacy } from "./legacy";
import type { Node, Edge } from "@xyflow/react";
export const roles = [
  "Request",
  "Analyst",
  "Searcher",
  "Reader",
  "Organizer",
  "Writer",
] as const;
export type Role = (typeof roles)[number];
export type Status = "idle" | "running" | "done" | "failed";
export type Data = {
  label: string;
  role: Role;
  description: string;
  prompt: string;
  model: string;
  budget: number;
  status: Status;
  output?: string;
};
export type ResearchNode = Node<Data, "research">;
export type Workflow = {
  version: 1;
  title: string;
  question: string;
  nodes: ResearchNode[];
  edges: Edge[];
};
export const descriptions: Record<Role, string> = {
  Request: "Define the research question",
  Analyst: "Map objects, relations & unknowns",
  Searcher: "Find sources for each research goal",
  Reader: "Collect key points from pages",
  Organizer: "Organize notes by topic",
  Writer: "Turn research notes into a report",
};
export function createNode(
  role: Role,
  id: string,
  x: number,
  y: number,
): ResearchNode {
  return {
    id,
    type: "research",
    position: { x, y },
    data: {
      label: role,
      role,
      description: descriptions[role],
      prompt: descriptions[role] + ". State uncertainty explicitly.",
      model: "local-model",
      budget: 20,
      status: "idle",
    },
  };
}
export function initial(): Workflow {
  const positions: [[Role, number, number], ...Array<[Role, number, number]>] =
    [
      ["Request", 20, 185],
      ["Analyst", 300, 185],
      ["Searcher", 580, 45],
      ["Reader", 580, 325],
      ["Organizer", 860, 185],
      ["Writer", 1140, 185],
    ];
  const nodes = positions.map(([r, x, y], i) => createNode(r, "n" + i, x, y));
  const pairs = [
    [0, 1],
    [1, 2],
    [2, 3],
    [3, 4],
    [4, 5],
  ];
  return {
    version: 1,
    title: "INSE 691 Project",
    question: "How can environment-based design guide an AI research workflow?",
    nodes,
    edges: pairs.map(([a, b]) => ({
      id: `e${a}-${b}`,
      source: "n" + a,
      target: "n" + b,
      type: "smoothstep",
    })),
  };
}
export function executionOrder(nodes: ResearchNode[], edges: Edge[]): string[] {
  if (!nodes.length) throw new Error("Add at least one node before running.");
  const ids = new Set(nodes.map((n) => n.id));
  const indegree = new Map(nodes.map((n) => [n.id, 0]));
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target))
      throw new Error("A connection has a missing node.");
    indegree.set(e.target, indegree.get(e.target)! + 1);
  }
  const ready = nodes.filter((n) => indegree.get(n.id) === 0).map((n) => n.id);
  const order: string[] = [];
  while (ready.length) {
    const id = ready.shift()!;
    order.push(id);
    for (const e of edges.filter((e) => e.source === id)) {
      indegree.set(e.target, indegree.get(e.target)! - 1);
      if (indegree.get(e.target) === 0) ready.push(e.target);
    }
  }
  if (order.length !== nodes.length)
    throw new Error(
      "This version runs directed acyclic workflows. Remove the circular connection.",
    );
  return order;
}
export function clean(w: Workflow): Workflow {
  return {
    ...w,
    nodes: w.nodes.map((n) => ({
      ...n,
      selected: false,
      data: { ...n.data, status: "idle", output: undefined },
    })),
  };
}
export function parseWorkflow(text: string): Workflow {
  const w = migrateLegacy(JSON.parse(text));
  if (
    w.version !== 1 ||
    typeof w.title !== "string" ||
    typeof w.question !== "string" ||
    !Array.isArray(w.nodes) ||
    !Array.isArray(w.edges)
  )
    throw new Error("Invalid workflow file. Expected version 1.");
  if (w.nodes.length > 200 || w.edges.length > 1000)
    throw new Error("Maximum 200 nodes and 1000 connections.");
  const nodes: ResearchNode[] = w.nodes.map((n: any) => {
    if (
      typeof n.id !== "string" ||
      !n.id ||
      !Number.isFinite(n.position?.x) ||
      !Number.isFinite(n.position?.y) ||
      !roles.includes(n.data?.role) ||
      typeof n.data?.label !== "string" ||
      typeof n.data?.prompt !== "string" ||
      typeof n.data?.model !== "string" ||
      typeof n.data?.description !== "string" ||
      !Number.isInteger(n.data?.budget) ||
      n.data.budget < 1 ||
      n.data.budget > 1000
    )
      throw new Error("Invalid node configuration.");
    return {
      ...createNode(n.data.role, n.id, n.position.x, n.position.y),
      ...(Number.isFinite(n.width) && Number.isFinite(n.height)
        ? {
            width: Math.max(200, Math.min(700, n.width)),
            height: Math.max(160, Math.min(600, n.height)),
            style: {
              width: Math.max(200, Math.min(700, n.width)),
              height: Math.max(160, Math.min(600, n.height)),
            },
          }
        : {}),
      data: {
        label: n.data.label,
        role: n.data.role,
        description: n.data.description,
        prompt: n.data.prompt,
        model: n.data.model,
        budget: n.data.budget,
        status: "idle",
      },
    };
  });
  const ids = new Set(nodes.map((n) => n.id));
  if (ids.size !== nodes.length) throw new Error("Node IDs must be unique.");
  const edges: Edge[] = w.edges.map((e: any) => {
    if (
      typeof e.id !== "string" ||
      !ids.has(e.source) ||
      !ids.has(e.target) ||
      e.source === e.target
    )
      throw new Error("Invalid connection.");
    return { id: e.id, source: e.source, target: e.target, type: "smoothstep" };
  });
  if (
    new Set(edges.map((e) => e.id)).size !== edges.length ||
    new Set(edges.map((e) => e.source + ">" + e.target)).size !== edges.length
  )
    throw new Error("Duplicate connections.");
  if (nodes.length) executionOrder(nodes, edges);
  return { version: 1, title: w.title, question: w.question, nodes, edges };
}
export type RunEvent = {
  requestId?: string;
  performance?: NodePerformance;
  details?: {
    input: string;
    instruction: string;
    model: string;
    upstream: string[];
  };
  id: string;
  nodeId: string;
  label: string;
  status: Status;
  message: string;
  time: string;
};
export function demoOutput(
  n: ResearchNode,
  question: string,
  inputs: string[],
): string {
  return `[SIMULATED — no model or web call]\n${n.data.role}: ${n.data.label}\nResearch question: ${question}\nUpstream results received: ${inputs.length}\nConfigured model: ${n.data.model}\nPage budget: ${n.data.budget}\nInstruction: ${n.data.prompt}\n\n${n.data.role === "Writer" ? "Report placeholder: content will arrive from the research backend." : n.data.description + ". This node is ready for backend integration."}`;
}
