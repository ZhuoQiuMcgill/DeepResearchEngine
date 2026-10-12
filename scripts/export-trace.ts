/** Export the actual Langfuse observation tree; no credentials enter the artifact. */
import "dotenv/config";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tracingBaseURL } from "../src/observability/langfuse.js";
const dir = process.argv[2];
if (!dir) throw new Error("Provide a completed run directory.");
const summary = JSON.parse(readFileSync(join(dir, "summary.json"), "utf8"));
const traceId = summary.tracing?.traceId;
if (!traceId) throw new Error("The run has no Langfuse trace id.");
const headers = { Authorization: `Basic ${Buffer.from(`${process.env.LANGFUSE_PUBLIC_KEY}:${process.env.LANGFUSE_SECRET_KEY}`).toString("base64")}` };
const observations: any[] = [];
let cursor: string | undefined;
do {
  const query = new URLSearchParams({ traceId, limit: "100", fields: "core,basic,io,usage,metadata" });
  if (cursor) query.set("cursor", cursor);
  const r = await fetch(`${tracingBaseURL()}/api/public/v2/observations?${query}`, { headers });
  if (!r.ok) throw new Error(`Observation export returned HTTP ${r.status}.`);
  const data = await r.json() as any;
  observations.push(...data.data);
  cursor = data.meta?.cursor ?? data.meta?.nextCursor;
  if (data.data.length === 100 && !cursor) throw new Error("Cannot confirm complete pagination.");
} while (cursor);
if (!observations.some(o => o.name === "write") || !observations.some(o => !o.parentObservationId))
  throw new Error("The completed root and write node have not been ingested yet; retry shortly.");
const payload = { summary, observations, report: readFileSync(join(dir, "report.md"), "utf8") };
writeFileSync(join(dir, "langfuse-observations.json"), JSON.stringify(payload, null, 2));
const data = JSON.stringify(payload).replace(/</g, "\\u003c");
const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>INSE 691 · Baseline trace</title><style>
*{box-sizing:border-box}body{margin:0;background:#111b24;color:#dce9ef;font:14px system-ui}header,main{padding:24px;max-width:1500px;margin:auto}header{border-bottom:1px solid #30434e}h1{font-size:28px}p{color:#aac0cb}a{color:#65d1c7}button{background:#20333f;border:1px solid #3b5563;color:inherit;padding:8px;cursor:pointer}section{margin:20px 0;background:#172732;border:1px solid #30434e;border-radius:8px;padding:16px}.row{display:grid;grid-template-columns:minmax(200px,36%) 1fr 75px;gap:12px;align-items:center;cursor:pointer;border-bottom:1px solid #2b3d48;padding:9px}.row:hover{background:#223844}.lane{height:14px;background:#0c171f;position:relative}.bar{position:absolute;height:100%;background:#2bb6a4;min-width:2px}.GENERATION .bar{background:#7773dd}.TOOL .bar{background:#d8a34e}.ERROR .bar{background:#dc6f73}.kind{color:#94aab5;font-size:11px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:600px;overflow:auto;font:12px ui-monospace,monospace}#details{display:none}.stats{display:flex;gap:24px;flex-wrap:wrap}.stats b{font-size:21px;display:block}input{background:#0c171f;color:inherit;border:1px solid #3b5563;padding:9px;width:min(400px,100%)}.badge{background:#254c4b;color:#93e4db;padding:5px 9px;border-radius:4px}@media(max-width:650px){header,main{padding:12px}.row{grid-template-columns:45% 1fr 50px;font-size:12px}}
</style><header><span class="badge">Downloaded literature · offline</span><h1>Baseline · complete run</h1><p id="question"></p><a id="native">Open native Langfuse trace</a></header><main><div id="stats" class="stats"></div><section><h2>Run timeline</h2><p>Click a row for its input, output, usage and recorded status. Durations overlap; they must not be added together.</p><input id="filter" placeholder="Filter stages, models or tools"><div id="timeline"></div></section><section id="details"><h2 id="name"></h2><pre id="detail"></pre></section><section><h2>Final report</h2><pre id="report"></pre></section></main><script>
const data=${data};const s=data.summary,obs=data.observations;document.getElementById('question').textContent=s.question;const link=document.getElementById('native');link.href=s.tracing.url;link.target='_blank';link.rel='noopener noreferrer';document.getElementById('report').textContent=data.report;
for(const [label,value] of [['Status',s.status],['Research rounds',s.rounds],['Input tokens',s.totalTokens.input],['Output tokens',s.totalTokens.output],['Langfuse observations',obs.length]]){const item=document.createElement('div');const b=document.createElement('b');b.textContent=value;item.append(b,label);document.getElementById('stats').append(item)}
const starts=obs.map(o=>Date.parse(o.startTime)),begin=Math.min(...starts),end=Math.max(...obs.map(o=>Date.parse(o.endTime||o.startTime))),span=Math.max(1,end-begin),byId=new Map(obs.map(o=>[o.id,o]));function depth(o){let n=0,p=o.parentObservationId,seen=new Set();while(p&&byId.has(p)&&!seen.has(p)){seen.add(p);n++;p=byId.get(p).parentObservationId}return n}
function render(){const target=document.getElementById('timeline');target.replaceChildren();const q=document.getElementById('filter').value.toLowerCase();for(const o of [...obs].sort((a,b)=>Date.parse(a.startTime)-Date.parse(b.startTime))){if(q&&!String(o.name).toLowerCase().includes(q))continue;const row=document.createElement('div');row.className='row '+o.type+' '+o.level;const label=document.createElement('div');label.style.paddingLeft=Math.min(5,depth(o))*12+'px';label.textContent=o.name;const kind=document.createElement('div');kind.className='kind';kind.textContent=o.type;label.append(kind);const lane=document.createElement('div');lane.className='lane';const bar=document.createElement('div');bar.className='bar';bar.style.left=100*(Date.parse(o.startTime)-begin)/span+'%';bar.style.width=100*(Date.parse(o.endTime||o.startTime)-Date.parse(o.startTime))/span+'%';lane.append(bar);const time=document.createElement('div');time.textContent=((Date.parse(o.endTime||o.startTime)-Date.parse(o.startTime))/1000).toFixed(1)+'s';row.append(label,lane,time);row.onclick=()=>{document.getElementById('details').style.display='block';document.getElementById('name').textContent=o.name;document.getElementById('detail').textContent=JSON.stringify(o,null,2)};target.append(row)}}document.getElementById('filter').oninput=render;render();
</script></html>`;
writeFileSync(join(dir, "trace.html"), html);
console.log(JSON.stringify({ traceId, observations: observations.length, artifact: join(dir, "trace.html") }));
