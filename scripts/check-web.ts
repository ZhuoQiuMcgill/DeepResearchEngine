/** One real managed-search readiness check, distinct from a baseline run. */
import "dotenv/config";
import { TavilySearch } from "@langchain/tavily";
if (!process.env.TAVILY_API_KEY?.trim()) {
  console.error("TAVILY_API_KEY is missing. Set it in the ignored project .env. No network request was made.");
  process.exit(2);
}
const result = await new TavilySearch({ maxResults: 3, searchDepth: "basic", includeRawContent: false })
  .invoke({ query: "Environment Based Design Yong Zeng" }) as unknown as { error?: unknown; results?: { url: string; title?: string }[] };
if (result.error || !result.results?.length) {
  console.error("Tavily returned no usable results. Check credentials, quota and network before running baseline.");
  process.exit(1);
}
console.log(JSON.stringify({ liveSearch: true, modelCalled: false, baselineRun: false, sources: result.results.map(r=>({ url:r.url, title:r.title })) }, null, 2));
