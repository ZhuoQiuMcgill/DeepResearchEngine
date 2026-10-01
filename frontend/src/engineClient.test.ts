import { afterEach, expect, it, vi } from "vitest";
import { EngineClient } from "../server/engineClient";
import { readNodeStream } from "./engineStream";
afterEach(() => vi.unstubAllGlobals());
it("registers pinned tools, drains committed events and reads saved UTF-8 report chunks", async () => {
  const calls: string[] = [];
  let eventPage = 0;
  const text = Buffer.from("研究 report");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: any) => {
      calls.push(url);
      let data: any = {};
      if (url.endsWith("/agents")) {
        const b = JSON.parse(options.body);
        expect(b.profile_ref).toBe("test");
        expect(b.allowed_tools).toEqual([{ name: "web.fetch", revision: 1 }]);
      } else if (url.endsWith("/runs")) data = { run_id: "r1" };
      else if (url.includes("/events?")) {
        eventPage++;
        data = {
          events: [
            {
              event: {
                event_id: "e1",
                kind: "tool.outcome",
                producer_timestamp: "2026-10-01T00:00:00Z",
                payload: {},
              },
              receipt: { recorded_seq: 1 },
            },
          ],
          next_after_seq: eventPage,
          has_more: eventPage === 1,
        };
      } else if (url.endsWith("/result"))
        data = {
          status: "succeeded",
          recording_status: "complete",
          persistence_state: "committed",
          available: true,
          output_ref: { artifact_id: "a1" },
        };
      else if (url.endsWith("/usage"))
        data = {
          usage: {
            known_subtotals: { input_tokens: 10, output_tokens: 2 },
            completeness: "complete",
          },
        };
      else if (url.includes("/artifacts/")) {
        const start = Number(new URL(url).searchParams.get("start"));
        const end = start === 0 ? 2 : text.length;
        data = {
          encoding: "base64",
          data: text.subarray(start, end).toString("base64"),
          start,
          next_offset: end,
          eof: end === text.length,
        };
      } else data = { active: false };
      return Response.json(data);
    }),
  );
  const events: any[] = [];
  const result = await new EngineClient("http://127.0.0.1:8765/api/v1").run(
    { profile_ref: "test", model_ref: "m", provider: "deepseek" },
    "Task",
    "Input",
    [{ name: "web.fetch", revision: 1 }],
    new AbortController().signal,
    (e) => events.push(e),
    () => {},
  );
  expect(result.output).toBe("研究 report");
  expect(events).toHaveLength(1);
  expect(result.usage.known_subtotals.input_tokens).toBe(10);
  expect(calls.filter((c) => c.includes("/artifacts/"))).toHaveLength(2);
});
it("does not display a report from incomplete storage", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      Response.json(
        url.endsWith("/runs")
          ? { run_id: "r" }
          : url.includes("/events")
            ? { events: [], next_after_seq: 0, has_more: false }
            : url.endsWith("/result")
              ? {
                  status: "succeeded",
                  recording_status: "incomplete",
                  available: false,
                }
              : { active: false },
      ),
    ),
  );
  await expect(
    new EngineClient("http://127.0.0.1:8765/api/v1").run(
      { profile_ref: "test", model_ref: "m", provider: "deepseek" },
      "Task",
      "Input",
      [],
      new AbortController().signal,
      () => {},
      () => {},
    ),
  ).rejects.toThrow("complete saved report");
});
it("streams real activities and rejects a disconnected response without a terminal", async () => {
  const rows = [
    { type: "run", runId: "r" },
    { type: "activity", activity: { event: { kind: "model.outcome" } } },
    { type: "result", output: "Done" },
  ];
  const events: any[] = [];
  const runs: string[] = [];
  const result = await readNodeStream(
    new Response(rows.map((x) => JSON.stringify(x)).join("\n")),
    (e) => events.push(e),
    (id) => runs.push(id),
  );
  expect(result.output).toBe("Done");
  expect(events).toHaveLength(1);
  expect(runs).toEqual(["r"]);
  await expect(
    readNodeStream(
      new Response("{}\n"),
      () => {},
      () => {},
    ),
  ).rejects.toThrow("before the result");
});

it('cancels a run admitted after its caller disconnected',async()=>{
 const calls:string[]=[];const controller=new AbortController();
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{calls.push(url);return Response.json(url.endsWith('/runs')?{run_id:'r-cancel'}:{});}));
 await expect(new EngineClient('http://127.0.0.1:8765/api/v1').run({profile_ref:'test',model_ref:'m',provider:'deepseek'},'Task','Input',[],controller.signal,()=>{},()=>controller.abort())).rejects.toThrow();
 expect(calls.some(url=>url.endsWith('/runs/r-cancel/cancel'))).toBe(true);
});
