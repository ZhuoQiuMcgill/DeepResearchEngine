import ReactMarkdown from "react-markdown";
import { migrateLegacy } from "./legacy";
import {
  modelProfileLabels,
  requestModelPlan,
  type ModelProfile,
  type ModelProfileId,
} from "./aiPlanner";
import { Timeline } from "./Timeline";
import {
  PerformancePanel,
  usePerformanceSnapshot,
  nodePerformance,
} from "./PerformancePanel";
import { ResizeHandle } from "./ResizeHandle";
import { EngineRunReview } from "./EngineRunReview";
import { OfficialEngine } from "./OfficialEngine";
import { WorkflowPreflight } from "./WorkflowPreflight";
import { useState, useEffect, useRef, useMemo } from "react";
import {
  ReactFlow,
  NodeResizer,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  useReactFlow,
  type NodeProps,
  type Connection,
} from "@xyflow/react";
import {
  FlaskConical,
  Plus,
  Play,
  Pause,
  Square,
  SkipForward,
  Download,
  Upload,
  Trash2,
  Copy,
  Search,
  BookOpen,
  GitBranch,
  FileText,
  ScanLine,
  ArrowUpRight,
  Check,
  Clock3,
  Settings2,
  RotateCcw,
  Layers,
  ChevronRight,
  Activity,
  Moon,
  Sun,
  ClipboardList,
} from "lucide-react";
import {
  roles,
  descriptions,
  initial,
  createNode,
  clean,
  parseWorkflow,
  executionOrder,
  type Role,
  type ResearchNode,
  type Workflow,
  type RunEvent,
} from "./workflow";
const icons = {
  Request: FileText,
  Analyst: GitBranch,
  Searcher: Search,
  Reader: BookOpen,
  Organizer: ScanLine,
  Writer: FileText,
};
const colors: Record<Role, string> = {
  Request: "#718096",
  Analyst: "#087f73",
  Searcher: "#5262ca",
  Reader: "#b77726",
  Organizer: "#b56879",
  Writer: "#43889a",
};
function ResearchCard({ data, selected, draggable }: NodeProps<ResearchNode>) {
  const Icon = icons[data.role];
  return (
    <div
      className={`research-card ${selected ? "selected" : ""} ${data.status}`}
      style={{ "--accent": colors[data.role] } as React.CSSProperties}
    >
      <NodeResizer
        isVisible={selected && draggable !== false}
        minWidth={200}
        minHeight={160}
        maxWidth={700}
        maxHeight={600}
        color="#159b87"
      />
      <Handle type="target" position={Position.Left} />
      <div className="card-top">
        <span className="node-icon">
          <Icon size={17} />
        </span>
        <span className="role">{data.role}</span>
        <span className={`status-dot ${data.status}`} />
      </div>
      <strong>{data.label}</strong>
      <p>{data.description}</p>
      <div className="card-foot">
        <span>{data.model}</span>
        <span>
          {data.status === "done" ? (
            <>
              <Check size={12} />
              Complete
            </>
          ) : data.status === "running" ? (
            "Processing…"
          ) : (
            `${data.budget} pages`
          )}
        </span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { research: ResearchCard };
type SavedRun = {
  id: string;
  date: string;
  workflow: Workflow;
  events: RunEvent[];
  status: string;
  profile?: ModelProfileId;
};
const GRAPH_KEY = "ebd-studio-workflow-v1",
  RUN_KEY = "ebd-studio-runs-v1";
function load(): Workflow {
  try {
    const text = localStorage.getItem(GRAPH_KEY);
    const workflow = text ? parseWorkflow(text) : initial();
    if (workflow.title === "Evidence to insight")
      workflow.title = "INSE 691 Project";
    return workflow;
  } catch {
    return initial();
  }
}
function download(name: string, obj: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function App() {
  const nodeAbort = useRef<AbortController | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [showEngineReview, setShowEngineReview] = useState(false);
  const [showOfficialEngine, setShowOfficialEngine] = useState(false);
  const [engineJob, setEngineJob] = useState<string>();
  const [showPreflight, setShowPreflight] = useState(false);
  const offlinePreview = window.location.protocol === "file:";
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[] | null>(
    null,
  );
  const [profileId, setProfileId] = useState<ModelProfileId | null>(null);
  const [modelConfigError, setModelConfigError] = useState(false);
  const selectedProfile = modelProfiles?.find(
    (profile) => profile.id === profileId,
  );
  const telemetry = usePerformanceSnapshot(selectedProfile?.id);
  const defaults = {
    library: 226,
    inspector: 285,
    timeline: 330,
    mission: 340,
  };
  const [panels, setPanels] = useState(() => {
    try {
      const stored = JSON.parse(
        localStorage.getItem("inse-panel-sizes") || "{}",
      );
      return Object.fromEntries(
        Object.entries(defaults).map(([key, fallback]) => [
          key,
          Number.isFinite(stored[key])
            ? Math.max(160, Math.min(600, stored[key]))
            : fallback,
        ]),
      ) as typeof defaults;
    } catch {
      return defaults;
    }
  });
  const [viewport, setViewport] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });
  useEffect(() => {
    const resize = () =>
      setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem("inse-panel-sizes", JSON.stringify(panels));
    } catch {}
  }, [panels]);
  const sideMax = Math.max(170, Math.min(550, (viewport.width - 330) / 2));
  const timelineMax = Math.max(300, viewport.height - 420);
  const size = {
    library: Math.min(panels.library, sideMax),
    inspector: Math.min(panels.inspector, sideMax),
    timeline: Math.min(panels.timeline, timelineMax),
    mission: Math.min(panels.mission, Math.max(200, viewport.width * 0.4)),
  };
  function divider(
    key: keyof typeof defaults,
    min: number,
    max: number,
    horizontal = false,
    reverse = false,
  ) {
    return (
      <ResizeHandle
        label={`Resize ${key} panel`}
        value={size[key]}
        min={min}
        max={max}
        horizontal={horizontal}
        reverse={reverse}
        onChange={(value) => setPanels((p) => ({ ...p, [key]: value }))}
        onReset={() => setPanels((p) => ({ ...p, [key]: defaults[key] }))}
      />
    );
  }
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem("inse-theme") === "dark";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try {
      localStorage.setItem("inse-theme", dark ? "dark" : "light");
    } catch {
      /* Theme remains available in this session. */
    }
  }, [dark]);
  const [workflow, setWorkflow] = useState(load);
  const [selected, setSelected] = useState<string | null>("n1");
  const [tab, setTab] = useState<"configure" | "performance" | "output">(
    "configure",
  );
  const [mode, setMode] = useState<
    "idle" | "running" | "paused" | "complete" | "stopped"
  >("idle");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [replay, setReplay] = useState<number | null>(null);
  const [toast, setToast] = useState("");
  const [filter, setFilter] = useState("");
  const [runs, setRuns] = useState<SavedRun[]>(() => {
    try {
      const v = JSON.parse(localStorage.getItem(RUN_KEY) || "[]");
      return Array.isArray(v) ? migrateLegacy(v) : [];
    } catch {
      return [];
    }
  });
  const [showRuns, setShowRuns] = useState(false);
  const [beforePlan, setBeforePlan] = useState<Workflow | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planStatus, setPlanStatus] = useState("");
  const planAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    if (offlinePreview) return;
    const controller = new AbortController();
    async function loadProfiles() {
      const response = await fetch("/api/planner", {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error();
      const info = (await response.json()) as {
        profiles: ModelProfile[];
        defaultProfile: ModelProfileId | null;
      };
      const available = info.profiles.filter(
        (profile) =>
          (profile.id === "local" || profile.id === "api") &&
          typeof profile.model === "string" &&
          Boolean(profile.model),
      );
      if (controller.signal.aborted) return;
      setModelProfiles(available);
      setProfileId(
        available.find((profile) => profile.id === info.defaultProfile)?.id ??
          available[0]?.id ??
          null,
      );
    }
    void loadProfiles().catch(() => {
      if (!controller.signal.aborted) setModelConfigError(true);
    });
    return () => controller.abort();
  }, [offlinePreview]);
  useEffect(() => () => planAbort.current?.abort(), []);
  const modelAvailability = offlinePreview
    ? "Offline preview. Start the app server to use a model."
    : modelConfigError
      ? "Model settings unavailable. Reconnect to the app server."
      : modelProfiles === null
        ? "Loading model settings."
        : "No model configured. See .env.example.";
  const file = useRef<HTMLInputElement>(null);
  const run = useRef<{
    id: string;
    workflow: Workflow;
    order: string[];
    profile?: ModelProfileId;
  } | null>(null);
  const { fitView, screenToFlowPosition } = useReactFlow();
  const locked = planning || mode === "running" || mode === "paused";
  function replacePlan(next: Workflow) {
    setWorkflow(next);
    setSelected(next.nodes[0]?.id ?? null);
    setEvents([]);
    setCursor(0);
    setReplay(null);
    setMode("idle");
    setTab("configure");
    run.current = null;
    setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 100);
  }
  async function generatePlan() {
    if (locked || !selectedProfile) return;
    const controller = new AbortController();
    planAbort.current = controller;
    setPlanning(true);
    setPlanStatus("AI is reading your request and planning tasks…");
    try {
      const result = await requestModelPlan(
        workflow.question,
        workflow.title,
        controller.signal,
        selectedProfile.id,
      );
      if (controller.signal.aborted) return;
      setBeforePlan(clean(workflow));
      replacePlan(result.workflow);
      setPlanStatus(
        `Planned by ${result.model}: ${result.workflow.nodes.length} nodes, ${result.workflow.nodes.filter((n) => n.data.role === "Searcher").length} search tasks.`,
      );
      setToast("AI plan created. Each node has its own task instructions.");
    } catch (error) {
      setPlanStatus(
        controller.signal.aborted
          ? "Planning cancelled. Canvas unchanged."
          : (error as Error).message,
      );
    } finally {
      setPlanning(false);
      planAbort.current = null;
    }
  }
  useEffect(() => {
    try {
      localStorage.setItem(GRAPH_KEY, JSON.stringify(clean(workflow)));
    } catch {
      setToast("Browser storage is full. Export your workflow to keep it.");
    }
  }, [workflow]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 4500);
    return () => clearTimeout(t);
  }, [toast]);
  function archive(ev: RunEvent[], status: string) {
    if (!run.current) return;
    const value: SavedRun = {
      id: run.current.id,
      date: new Date().toLocaleString(),
      workflow: clean(run.current.workflow),
      events: ev,
      status,
      profile: run.current.profile,
    };
    setRuns((prev) => {
      const next = [value, ...prev.filter((r) => r.id !== value.id)].slice(
        0,
        5,
      );
      try {
        localStorage.setItem(RUN_KEY, JSON.stringify(next));
      } catch {
        setToast("Could not save run history. Export the events.");
      }
      return next;
    });
  }
  async function advance() {
    const current = run.current;
    if (!current || nodeAbort.current) return;
    const node = current.workflow.nodes.find(
      (n) => n.id === current.order[Math.floor(cursor / 2)],
    );
    if (!node) return;
    const controller = new AbortController();
    nodeAbort.current = controller;
    const parents = current.workflow.edges
      .filter((e) => e.target === node.id)
      .map((e) => e.source);
    const upstream = parents.map(
      (id) =>
        events.findLast((e) => e.nodeId === id && e.status === "done")
          ?.message || "",
    );
    const details = {
      input: upstream.join("\n\n"),
      instruction: node.data.prompt,
      model: node.data.model,
      upstream: parents,
    };
    const started: RunEvent = {
      id: crypto.randomUUID(),
      nodeId: node.id,
      label: node.data.label,
      status: "running",
      message:
        node.data.role === "Searcher"
          ? "Searching public web results, then sending them to the selected model…"
          : "Processing upstream results with the selected model…",
      details,
      time: new Date().toISOString(),
    };
    const pending = [...events, started];
    setEvents(pending);
    setSelected(node.id);
    setReplay(null);
    try {
      const response = await fetch("/api/node", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requestId: started.id,
          question: current.workflow.question,
          node: node.data,
          upstream,
          profile: current.profile,
        }),
        signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Node could not finish.");
      if (controller.signal.aborted) return;
      const next: RunEvent[] = [
        ...pending,
        {
          ...started,
          id: crypto.randomUUID(),
          status: "done",
          message: data.output,
          performance: data.performance,
          time: new Date().toISOString(),
        },
      ];
      setEvents(next);
      setCursor(cursor + 2);
      if (cursor + 2 === current.order.length * 2) {
        setMode("complete");
        archive(next, "complete");
        setShowReport(true);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const next: RunEvent[] = [
          ...pending,
          {
            ...started,
            id: crypto.randomUUID(),
            status: "failed",
            message: (error as Error).message,
            time: new Date().toISOString(),
          },
        ];
        setEvents(next);
        setMode("stopped");
        archive(next, "failed");
        setToast((error as Error).message);
      }
    } finally {
      if (nodeAbort.current === controller) nodeAbort.current = null;
    }
  }
  useEffect(() => {
    if (mode === "running" && !nodeAbort.current) void advance();
  }, [mode, cursor]);
  useEffect(() => () => nodeAbort.current?.abort(), []);
  function start() {
    try {
      if (!selectedProfile) throw new Error(modelAvailability);
      if (!workflow.question.trim())
        throw new Error("Enter a research question first.");
      const order = executionOrder(workflow.nodes, workflow.edges);
      run.current = {
        id: crypto.randomUUID(),
        workflow: clean({
          ...workflow,
          nodes: workflow.nodes.map((node) => ({
            ...node,
            data: { ...node.data, model: selectedProfile.model },
          })),
        }),
        order,
        profile: selectedProfile.id,
      };
      setShowReport(false);
      setEvents([]);
      setCursor(0);
      setReplay(null);
      setMode("running");
      setTab("output");
    } catch (e) {
      setToast((e as Error).message);
    }
  }
  function stop() {
    nodeAbort.current?.abort();
    nodeAbort.current = null;
    setMode("stopped");
    archive(events, "stopped");
  }
  function update(data: Partial<ResearchNode["data"]>) {
    if (locked) return;
    setWorkflow((w) => ({
      ...w,
      nodes: w.nodes.map((n) =>
        n.id === selected ? { ...n, data: { ...n.data, ...data } } : n,
      ),
    }));
  }
  const draggedRole = useRef<Role | null>(null);
  const [dropActive, setDropActive] = useState(false);
  function add(role: Role, screenPoint?: { x: number; y: number }) {
    if (locked) return;
    const point = screenToFlowPosition(
      screenPoint ?? {
        x: window.innerWidth * 0.5,
        y: window.innerHeight * 0.42,
      },
    );
    const n = createNode(role, crypto.randomUUID(), point.x, point.y);
    setWorkflow((w) => ({ ...w, nodes: [...w.nodes, n] }));
    setSelected(n.id);
    setTab("configure");
  }
  function connect(c: Connection) {
    if (locked) return;
    try {
      if (c.source === c.target)
        throw new Error("Connect two different nodes.");
      if (
        workflow.edges.some(
          (e) => e.source === c.source && e.target === c.target,
        )
      )
        return;
      const next = addEdge({ ...c, type: "smoothstep" }, workflow.edges);
      executionOrder(workflow.nodes, next);
      setWorkflow((w) => ({ ...w, edges: next }));
    } catch (e) {
      setToast((e as Error).message);
    }
  }
  const reportGraph = run.current?.workflow || workflow;
  const shown = events.slice(0, replay === null ? events.length : replay);
  const nodes = useMemo(
    () =>
      workflow.nodes.map((n) => {
        const event = shown.findLast((e) => e.nodeId === n.id);
        return {
          ...n,
          selected: selected === n.id,
          data: {
            ...n.data,
            model:
              event?.details?.model ??
              selectedProfile?.model ??
              (n.data.model === "local-model" ? "Run model" : n.data.model),
            status: event?.status || ("idle" as const),
          },
        };
      }),
    [workflow.nodes, selected, events, replay, selectedProfile],
  );
  const edges = workflow.edges.map((e) => ({
    ...e,
    animated: nodes.find((n) => n.id === e.target)?.data.status === "running",
    style: {
      stroke:
        nodes.find((n) => n.id === e.source)?.data.status === "done"
          ? "#0b8c7e"
          : "#bcc8cd",
      strokeWidth: 1.8,
    },
  }));
  const node = workflow.nodes.find((n) => n.id === selected);
  const output = shown.findLast(
    (e) => e.nodeId === selected && e.status === "done",
  );
  const completed = new Set(
    shown.filter((e) => e.status === "done").map((e) => e.nodeId),
  ).size;
  async function importFile(f: File) {
    try {
      if (f.size > 2000000)
        throw new Error("Workflow file must be smaller than 2 MB.");
      const w = parseWorkflow(await f.text());
      setWorkflow(w);
      setSelected(w.nodes[0]?.id || null);
      setEvents([]);
      setMode("idle");
      setReplay(null);
      setTimeout(() => fitView({ padding: 0.15 }), 50);
      setToast("Workflow imported.");
    } catch (e) {
      setToast((e as Error).message);
    }
  }
  return (
    <div className="app-shell">
      <aside className="rail">
        <div className="brand-symbol">
          <FlaskConical size={23} />
        </div>
        <button
          className={`rail-button ${!showEngineReview ? "active" : ""}`}
          title="Workflow canvas"
          aria-label="Workflow canvas"
          onClick={() => setShowEngineReview(false)}
        >
          <GitBranch size={21} />
        </button>
        <button
          className={`rail-button ${showEngineReview ? "active" : ""}`}
          title="Review engine runs"
          aria-label="Review engine runs"
          onClick={() => {
            setEngineJob(undefined);
            setShowEngineReview(true);
          }}
        >
          <ClipboardList size={21} />
        </button>
        <button
          className={`rail-button ${showRuns ? "active" : ""}`}
          title="Run history"
          aria-label="Run history"
          disabled={locked}
          onClick={() => setShowRuns(!showRuns)}
        >
          <Clock3 size={21} />
        </button>
        <div className="rail-bottom">
          EBD<span>LAB</span>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <div className="breadcrumb">
            INSE 691 PROJECT <ChevronRight size={13} />
            <span>Workflow studio</span>
          </div>
          <div className="header-actions">
            <span
              className="model-summary"
              title="Usage for the selected model during this app session"
            >
              {selectedProfile?.model ??
                (offlinePreview ? "Offline preview" : "No active model")}
              {telemetry.data ? (
                <small>
                  {telemetry.data.busy ? "Busy" : "Idle"} ·{" "}
                  {(
                    telemetry.data.usage.inputTokens +
                    telemetry.data.usage.outputTokens
                  ).toLocaleString()}{" "}
                  tokens this session
                </small>
              ) : telemetry.error ? (
                <small>Usage unavailable</small>
              ) : null}
            </span>
            <button
              aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={15} /> : <Moon size={15} />}
              {dark ? "Light" : "Dark"}
            </button>
            <span className="saved">
              <span />
              Saved on this device
            </span>
            <button disabled={locked} onClick={() => file.current?.click()}>
              <Upload size={15} />
              Import
            </button>
            <button
              onClick={() =>
                download("research-workflow.json", clean(workflow))
              }
            >
              <Download size={15} />
              Export
            </button>
            <input
              ref={file}
              type="file"
              accept=".json"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importFile(f);
                e.target.value = "";
              }}
            />
          </div>
        </header>
        <section className="project-heading">
          <div>
            <div className="eyebrow">ENVIRONMENT-BASED DESIGN</div>
            <input
              className="project-title"
              aria-label="Workflow title"
              value={workflow.title}
              disabled={locked}
              onChange={(e) =>
                setWorkflow({ ...workflow, title: e.target.value })
              }
            />
            <p>Build and run a research workflow.</p>
          </div>
          <div className="run-controls">
            <button onClick={() => setShowOfficialEngine(true)}>
              <FlaskConical size={16} />
              Engine &amp; evaluation
            </button>
            <button
              onClick={() => {
                setEngineJob(undefined);
                setShowEngineReview(true);
              }}
            >
              <ClipboardList size={16} />
              Review engine run
            </button>
            <label className="model-picker">
              Model
              <select
                aria-describedby="model-picker-note"
                value={selectedProfile?.id ?? ""}
                disabled={locked || !modelProfiles?.length}
                onChange={(event) => {
                  const next = modelProfiles?.find(
                    (profile) => profile.id === event.target.value,
                  );
                  if (!next) return;
                  setProfileId(next.id);
                  setPlanStatus("");
                }}
              >
                {!selectedProfile && (
                  <option value="">Model unavailable</option>
                )}
                {(["local", "api"] as const).map((id) => {
                  const profile = modelProfiles?.find(
                    (model) => model.id === id,
                  );
                  return (
                    <option key={id} value={id} disabled={!profile}>
                      {modelProfileLabels[id]}
                      {profile ? "" : " · unavailable"}
                    </option>
                  );
                })}
              </select>
              <small id="model-picker-note">
                {selectedProfile?.id === "api"
                  ? "Planning and runs send data to the API provider."
                  : (selectedProfile?.model ?? modelAvailability)}
              </small>
            </label>
            {mode === "running" || mode === "paused" ? (
              <>
                <button
                  aria-label={mode === "paused" ? "Resume run" : "Pause run"}
                  onClick={() =>
                    setMode(mode === "paused" ? "running" : "paused")
                  }
                >
                  {mode === "paused" ? <Play size={16} /> : <Pause size={16} />}
                </button>
                <button
                  aria-label="Step run"
                  disabled={mode !== "paused"}
                  onClick={advance}
                >
                  <SkipForward size={16} />
                </button>
                <button aria-label="Stop run" onClick={stop}>
                  <Square size={15} />
                </button>
              </>
            ) : (
              <button
                className="primary"
                disabled={planning}
                onClick={() => setShowPreflight(true)}
              >
                <Play size={16} />
                Run workflow
              </button>
            )}
          </div>
        </section>
        <div className="editor">
          <aside className="library" style={{ width: size.library }}>
            <div className="section-label">
              NODE LIBRARY <span>{roles.length}</span>
            </div>
            <p className="muted">Build your research team.</p>
            <div className="search-box">
              <Search size={15} />
              <input
                aria-label="Search node types"
                placeholder="Find a node…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
            <div className="library-nodes">
              {roles
                .filter((r) => r.toLowerCase().includes(filter.toLowerCase()))
                .map((role) => {
                  const Icon = icons[role];
                  return (
                    <button
                      className="library-item"
                      disabled={locked}
                      draggable={!locked}
                      onDragStart={(event) => {
                        if (locked) {
                          event.preventDefault();
                          return;
                        }
                        draggedRole.current = role;
                        event.dataTransfer.setData(
                          "application/x-inse-node",
                          role,
                        );
                        event.dataTransfer.effectAllowed = "copy";
                      }}
                      onDragEnd={() => {
                        draggedRole.current = null;
                        setDropActive(false);
                      }}
                      key={role}
                      onClick={() => add(role)}
                      title={`Add ${role} · Click or drag onto the canvas`}
                    >
                      <span
                        className="library-icon"
                        style={{ color: colors[role] }}
                      >
                        <Icon size={19} />
                      </span>
                      <span>
                        <strong>{role}</strong>
                        <small>{descriptions[role]}</small>
                      </span>
                      <Plus size={14} />
                    </button>
                  );
                })}
            </div>
            <div className="library-note">
              <Layers size={20} />
              <strong>Make it your workflow</strong>
              <p>
                Drag a node onto the canvas or click to add. Connect its ports,
                then set its instructions.
              </p>
              <small>
                Delete selected nodes or connections with Backspace.
              </small>
            </div>
          </aside>
          {divider("library", 170, sideMax)}
          <main
            className={`canvas ${dropActive ? "drop-active" : ""}`}
            onDragOver={(event) => {
              if (locked || !draggedRole.current) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = "copy";
              setDropActive(true);
            }}
            onDragLeave={(event) => {
              if (
                !event.currentTarget.contains(
                  event.relatedTarget as Node | null,
                )
              )
                setDropActive(false);
            }}
            onDrop={(event) => {
              const role = draggedRole.current;
              setDropActive(false);
              draggedRole.current = null;
              if (locked || !role) return;
              event.preventDefault();
              add(role, { x: event.clientX, y: event.clientY });
            }}
          >
            {dropActive && <div className="drop-hint">Drop to add a node</div>}
            <div className="canvas-bar">
              <span>
                <span className="teal-dot" /> Workflow canvas
              </span>
              <span>
                {workflow.nodes.length} nodes · {workflow.edges.length}{" "}
                connections
              </span>
              <button
                aria-label="Fit workflow"
                onClick={() => fitView({ padding: 0.15 })}
              >
                <ScanLine size={15} />
              </button>
            </div>
            <ReactFlow<ResearchNode>
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={(changes) => {
                if (!locked)
                  setWorkflow((w) => {
                    const next = applyNodeChanges(changes, w.nodes);
                    const ids = new Set(next.map((n) => n.id));
                    return {
                      ...w,
                      nodes: next,
                      edges: w.edges.filter(
                        (e) => ids.has(e.source) && ids.has(e.target),
                      ),
                    };
                  });
              }}
              onEdgesChange={(changes) => {
                if (!locked)
                  setWorkflow((w) => ({
                    ...w,
                    edges: applyEdgeChanges(changes, w.edges),
                  }));
              }}
              onConnect={connect}
              onNodeClick={(_, n) => {
                setSelected(n.id);
              }}
              onPaneClick={() => setSelected(null)}
              onEdgeClick={() => setSelected(null)}
              nodesDraggable={!locked}
              nodesConnectable={!locked}
              deleteKeyCode={locked ? null : ["Backspace", "Delete"]}
              fitView
              fitViewOptions={{ padding: 0.15 }}
              minZoom={0.2}
              maxZoom={1.8}
            >
              <Background
                color={dark ? "#344957" : "#d6dfe2"}
                gap={22}
                size={1}
              />
              <Controls showInteractive={false} />
              <MiniMap
                nodeColor={(n) =>
                  colors[(n.data as any).role as Role] || "#aaa"
                }
                maskColor="rgba(245,248,249,.7)"
                pannable
                zoomable
              />
            </ReactFlow>
            <div className="canvas-hint">
              Drag to arrange · Connect the dots · Scroll to zoom
            </div>
          </main>
          {divider("inspector", 170, sideMax, false, true)}
          <aside className="inspector" style={{ width: size.inspector }}>
            <div className="inspector-title">
              <Settings2 size={17} />
              Node inspector
            </div>
            <div className="tabs">
              <button
                className={tab === "configure" ? "active" : ""}
                onClick={() => setTab("configure")}
              >
                Configuration
              </button>
              <button
                className={tab === "performance" ? "active" : ""}
                onClick={() => setTab("performance")}
              >
                Performance
              </button>
              <button
                className={tab === "output" ? "active" : ""}
                onClick={() => setTab("output")}
              >
                Output {output && <span className="teal-dot" />}
              </button>
            </div>
            {node ? (
              <div className="inspector-body">
                {tab === "performance" ? (
                  <PerformancePanel
                    label={node.data.label}
                    data={nodePerformance(
                      shown.filter((e) => e.nodeId === node.id),
                      replay === null ? telemetry.data : null,
                    )}
                  />
                ) : tab === "configure" ? (
                  <>
                    <span
                      className="node-type"
                      style={{ color: colors[node.data.role] }}
                    >
                      {node.data.role}
                    </span>
                    <label>
                      Node name
                      <input
                        aria-label="Node name"
                        disabled={locked}
                        value={node.data.label}
                        onChange={(e) => update({ label: e.target.value })}
                      />
                    </label>
                    <label>
                      Description
                      <input
                        disabled={locked}
                        value={node.data.description}
                        onChange={(e) =>
                          update({ description: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Instructions
                      <textarea
                        aria-label="Node instructions"
                        disabled={locked}
                        value={node.data.prompt}
                        onChange={(e) => update({ prompt: e.target.value })}
                        rows={5}
                      />
                    </label>
                    <p className="inspector-model">
                      <strong>Run model</strong>
                      <span>
                        {selectedProfile?.model ??
                          "Configure a model to run this node"}
                      </span>
                      <small>Choose a model beside Run workflow.</small>
                    </p>
                    <label>
                      Page budget
                      <input
                        aria-label="Page budget"
                        type="number"
                        min={1}
                        max={1000}
                        disabled={locked}
                        value={node.data.budget}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          if (Number.isInteger(v) && v >= 1 && v <= 1000)
                            update({ budget: v });
                        }}
                      />
                    </label>
                    <div className="node-actions">
                      <button
                        disabled={locked}
                        onClick={() => {
                          const n = {
                            ...structuredClone(node),
                            id: crypto.randomUUID(),
                            position: {
                              x: node.position.x + 40,
                              y: node.position.y + 190,
                            },
                            data: {
                              ...node.data,
                              label: node.data.label + " copy",
                              status: "idle" as const,
                            },
                          };
                          setWorkflow((w) => ({
                            ...w,
                            nodes: [...w.nodes, n],
                          }));
                          setSelected(n.id);
                        }}
                      >
                        <Copy size={14} />
                        Duplicate
                      </button>
                      <button
                        className="danger"
                        disabled={locked}
                        onClick={() => {
                          setWorkflow((w) => ({
                            ...w,
                            nodes: w.nodes.filter((n) => n.id !== node.id),
                            edges: w.edges.filter(
                              (e) =>
                                e.source !== node.id && e.target !== node.id,
                            ),
                          }));
                          setSelected(null);
                        }}
                      >
                        <Trash2 size={14} />
                        Delete
                      </button>
                    </div>
                    {locked && (
                      <p className="muted">
                        Stop this run to edit the workflow.
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <span className="node-type">{node.data.label}</span>
                    <pre>
                      {output?.message ||
                        "No output at this point. Run the workflow or move the replay cursor."}
                    </pre>
                  </>
                )}
              </div>
            ) : (
              <div className="inspector-empty">
                <ScanLine size={30} />
                <strong>Select a node</strong>
                <p>Inspect node instructions or read its output.</p>
              </div>
            )}
          </aside>
        </div>
        {divider("timeline", 190, timelineMax, true, true)}
        <section className="activity-panel" style={{ height: size.timeline }}>
          <div className="activity-heading">
            <div>
              <Activity size={17} />
              <strong>Run timeline</strong>
              <span className={`run-status ${mode}`}>
                {mode === "idle" ? "Ready" : mode}
              </span>
            </div>
            <div>
              <span>
                {completed} / {workflow.nodes.length} completed
              </span>
              <button
                disabled={!events.length}
                onClick={() =>
                  download("run-events.json", {
                    version: 1,
                    mode: "live",
                    profile: run.current?.profile,
                    workflow: run.current?.workflow || workflow,
                    events,
                  })
                }
              >
                <Download size={14} />
                Events
              </button>
              <button
                disabled={mode !== "complete"}
                onClick={() => setShowReport(true)}
              >
                Final report
              </button>
              <button disabled={locked} onClick={() => setShowRuns(!showRuns)}>
                <Clock3 size={14} />
                History
              </button>
            </div>
          </div>
          <div className="activity-content">
            <div className="mission" style={{ width: size.mission }}>
              <label>
                RESEARCH QUESTION
                <textarea
                  aria-label="Research question"
                  disabled={locked}
                  value={workflow.question}
                  onChange={(e) =>
                    setWorkflow({ ...workflow, question: e.target.value })
                  }
                />
              </label>
              <div className="plan-actions">
                <button
                  disabled={
                    locked || !selectedProfile || !workflow.question.trim()
                  }
                  onClick={generatePlan}
                >
                  <GitBranch size={13} />{" "}
                  {planning ? "Planning…" : "Plan with AI"}
                </button>
                {planning && (
                  <button onClick={() => planAbort.current?.abort()}>
                    Cancel
                  </button>
                )}
                {beforePlan && (
                  <button
                    disabled={locked}
                    onClick={() => {
                      replacePlan(beforePlan);
                      setBeforePlan(null);
                    }}
                  >
                    Undo plan
                  </button>
                )}
              </div>
              <div className="plan-hint" role="status">
                {planStatus ||
                  (selectedProfile?.id === "api"
                    ? "Plan with AI sends the question to the API provider."
                    : selectedProfile
                      ? "Plan with AI uses Local Qwen."
                      : modelAvailability)}
              </div>
              <small>
                <span className="teal-dot" />
                Runs use public search snippets and the selected model. Tasks
                run one at a time. Pause takes effect after the active task.
              </small>
            </div>
            {divider("mission", 200, Math.max(200, viewport.width * 0.4))}
            <div className="events">
              {events.length ? (
                <>
                  <div className="replay-control">
                    <RotateCcw size={13} />
                    <span>Replay</span>
                    <input
                      aria-label="Replay position"
                      type="range"
                      min={0}
                      max={events.length}
                      value={replay ?? events.length}
                      disabled={locked}
                      onChange={(e) => setReplay(Number(e.target.value))}
                    />
                    <span>
                      {replay ?? events.length}/{events.length}
                    </span>
                  </div>
                  <Timeline
                    events={shown}
                    live={mode === "running" && replay === null}
                    onSelect={(id) => {
                      setSelected(id);
                      setTab("output");
                    }}
                  />
                </>
              ) : (
                <div className="timeline-empty">
                  <div className="empty-line">
                    <span />
                    <span />
                    <span />
                  </div>
                  <strong>A clear trail from question to conclusion</strong>
                  <p>
                    Start a run to watch each node work and inspect its output.
                  </p>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
      <EngineRunReview
        open={showEngineReview}
        jobId={engineJob}
        onClose={() => setShowEngineReview(false)}
      />
      <OfficialEngine
        open={showOfficialEngine}
        onClose={() => setShowOfficialEngine(false)}
        onOpenRun={(id) => {
          setEngineJob(id);
          setShowOfficialEngine(false);
          setShowEngineReview(true);
        }}
      />
      {showPreflight && (
        <WorkflowPreflight
          workflow={workflow}
          model={
            selectedProfile
              ? { profile: selectedProfile.id, name: selectedProfile.model }
              : undefined
          }
          onClose={() => setShowPreflight(false)}
          onStart={() => {
            setShowPreflight(false);
            start();
          }}
        />
      )}
      {toast && (
        <div role="status" className="toast">
          {toast}
        </div>
      )}
      {showReport && (
        <div className="modal-backdrop">
          <section
            className="history-modal"
            role="dialog"
            aria-label="Final report"
            style={{
              width: "min(900px, 92vw)",
              maxHeight: "85vh",
              overflow: "auto",
            }}
          >
            <h2>Final report</h2>
            <button onClick={() => setShowReport(false)}>Close</button>
            <button
              onClick={() => {
                const text = events
                  .filter(
                    (e) =>
                      e.status === "done" &&
                      !reportGraph.edges.some(
                        (edge) => edge.source === e.nodeId,
                      ),
                  )
                  .map((e) => `# ${e.label}\n\n${e.message}`)
                  .join("\n\n");
                const url = URL.createObjectURL(
                  new Blob([text], { type: "text/markdown;charset=utf-8" }),
                );
                const a = document.createElement("a");
                a.href = url;
                a.download = "research-report.md";
                a.click();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
              }}
            >
              Download report
            </button>
            {events
              .filter(
                (e) =>
                  e.status === "done" &&
                  !reportGraph.edges.some((edge) => edge.source === e.nodeId),
              )
              .map((e) => (
                <article key={e.id} className="report-content">
                  <h3>{e.label}</h3>
                  <ReactMarkdown
                    components={{
                      a: ({ children, ...props }) => (
                        <a {...props} target="_blank" rel="noopener noreferrer">
                          {children}
                        </a>
                      ),
                      img: () => null,
                    }}
                  >
                    {e.message}
                  </ReactMarkdown>
                </article>
              ))}
          </section>
        </div>
      )}
      {showRuns && (
        <div className="modal-backdrop" onClick={() => setShowRuns(false)}>
          <section
            className="history-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="activity-heading">
              <strong>Recent runs</strong>
              <button onClick={() => setShowRuns(false)}>Close</button>
            </div>
            <p className="muted">
              Last five runs saved on this device. Loading a run replaces the
              canvas.
            </p>
            {runs.length ? (
              runs.map((r) => (
                <button
                  className="history-row"
                  disabled={locked}
                  key={r.id}
                  onClick={() => {
                    try {
                      const w = parseWorkflow(JSON.stringify(r.workflow));
                      setWorkflow(w);
                      setEvents(r.events);
                      setMode(r.status === "complete" ? "complete" : "stopped");
                      setReplay(r.events.length);
                      run.current = {
                        id: r.id,
                        workflow: w,
                        order: executionOrder(w.nodes, w.edges),
                        profile: r.profile,
                      };
                      setSelected(w.nodes[0]?.id || null);
                      setTab("output");
                      setShowRuns(false);
                      setTimeout(() => fitView({ padding: 0.15 }), 50);
                    } catch {
                      setToast("This saved run could not be loaded.");
                    }
                  }}
                >
                  <span>
                    <strong>{r.workflow.title}</strong>
                    <small>
                      {r.date} · {r.events.length} events · {r.status}
                    </small>
                  </span>
                  <ChevronRight size={17} />
                </button>
              ))
            ) : (
              <p>No saved runs yet.</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
