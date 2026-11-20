import { defineConfig, loadEnv } from "vite";
import { plannerPlugin } from "./server/planner";
import { officialEnginePlugin } from "./server/officialEngine";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
const engineRoot = fileURLToPath(new URL("..", import.meta.url));
export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    plannerPlugin(loadEnv(mode, ".", "PLANNER_")),
    officialEnginePlugin(
      engineRoot,
      loadEnv(mode, engineRoot, ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]),
    ),
  ],
  server: { host: "127.0.0.1", port: 5178, strictPort: true },
  preview: { host: "127.0.0.1", port: 5178, strictPort: true },
}));
