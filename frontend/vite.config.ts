import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { enginePlugin } from "./server/enginePlugin";
export default defineConfig(({ mode }) => ({
  plugins: [react(), enginePlugin(loadEnv(mode, ".", "ENGINE_"))],
  server: { host: "127.0.0.1", port: 5180, strictPort: true },
  preview: { host: "127.0.0.1", port: 5180, strictPort: true },
}));
