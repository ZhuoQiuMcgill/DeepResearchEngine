/** Serve only a prepared local trace artifact; no filesystem browsing or API keys. */
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { join } from "node:path";
const dir = process.argv[2];
if (!dir) throw new Error("Provide a run directory with trace.html.");
const html = readFileSync(join(dir, "trace.html"));
createServer((req,res) => {
  if (req.url !== "/" || !["GET", "HEAD"].includes(req.method || "")) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer" });
  res.end(req.method === "HEAD" ? undefined : html);
}).listen(5182, "127.0.0.1", () => console.log("Local trace: http://127.0.0.1:5182/"));
