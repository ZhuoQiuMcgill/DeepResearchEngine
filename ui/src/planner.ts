import { createNode, type Role, type Workflow } from "./workflow";

/** Local draft builder. Does not call a model or perform searches. */
export function planRequest(
  question: string,
  title = "INSE 691 Project",
): Workflow {
  const request = question.trim();
  if (!request) throw new Error("Enter a research question first.");
  if (request.length > 6000)
    throw new Error("Keep the request under 6000 characters.");
  const chinese = /[\u3400-\u9fff]/.test(request);
  const parts = [
    ...new Set(
      request
        .split(/[;；\n]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
  if (parts.length > 8)
    throw new Error(
      "Use up to eight topics separated by semicolons or new lines.",
    );
  const topics =
    parts.length > 1
      ? parts
      : chinese
        ? ["背景与基本概念", "主要方法与代表案例", "应用条件与局限"]
        : [
            "Background and concepts",
            "Methods and examples",
            "Applications and limitations",
          ];
  const nodes: Workflow["nodes"] = [];
  const edges: Workflow["edges"] = [];
  const middle = (topics.length - 1) * 110;
  const add = (
    role: Role,
    id: string,
    x: number,
    y: number,
    label: string,
    instruction: string,
  ) => {
    const node = createNode(role, id, x, y);
    node.data.label = label;
    node.data.description = instruction;
    node.data.prompt = `${chinese ? "完整研究需求" : "Full research request"}:\n${request}\n\n${instruction}`;
    nodes.push(node);
  };
  const link = (source: string, target: string) =>
    edges.push({
      id: `${source}-${target}`,
      source,
      target,
      type: "smoothstep",
    });
  add(
    "Request",
    "request",
    0,
    middle,
    chinese ? "研究需求" : "Research request",
    chinese
      ? "保留用户的完整需求、范围和期望输出。"
      : "Preserve the full request, scope and desired output.",
  );
  add(
    "Analyst",
    "analyst",
    300,
    middle,
    chinese ? "任务规划" : "Task planning",
    chinese
      ? "整理研究目标、关键词与每个分支的任务范围。"
      : "Outline research goals, keywords and scope for each branch.",
  );
  link("request", "analyst");
  topics.forEach((topic, i) => {
    const search = `search-${i}`,
      read = `read-${i}`;
    const label = topic.length > 32 ? topic.slice(0, 32) + "…" : topic;
    add(
      "Searcher",
      search,
      600,
      i * 220,
      label,
      chinese
        ? `围绕“${topic}”搜索资料。结合完整需求生成关键词，收集相关页面的标题、网址与摘要。`
        : `Search for “${topic}” within the full request. Develop search terms and collect relevant page titles, URLs and summaries.`,
    );
    add(
      "Reader",
      read,
      900,
      i * 220,
      chinese ? `阅读分支 ${i + 1}` : `Read branch ${i + 1}`,
      chinese
        ? `阅读上游关于“${topic}”的资料，提取要点、方法、适用条件，并保留来源网址。`
        : `Read upstream material about “${topic}”; collect key points, methods and applicable conditions with source URLs.`,
    );
    link("analyst", search);
    link(search, read);
    link(read, "organizer");
  });
  add(
    "Organizer",
    "organizer",
    1200,
    middle,
    chinese ? "汇总各分支" : "Combine branches",
    chinese
      ? "合并所有阅读分支的笔记，按主题整理，合并重复内容并列出尚未回答的问题。"
      : "Combine notes from every reading branch by topic, merge duplicates and list unanswered questions.",
  );
  add(
    "Writer",
    "writer",
    1500,
    middle,
    chinese ? "撰写报告" : "Write report",
    chinese
      ? "根据整理后的笔记回应完整研究需求，形成结构清晰、带来源链接的报告。"
      : "Use the organized notes to answer the full request in a structured report with source links.",
  );
  link("organizer", "writer");
  return { version: 1, title, question: request, nodes, edges };
}
