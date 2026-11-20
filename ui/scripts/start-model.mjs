import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const script = fileURLToPath(new URL("./start-model.py", import.meta.url));
let result;
if (process.platform === "win32") {
  const path = execFileSync("wsl.exe", ["--exec", "wslpath", "-u", script], {
    encoding: "utf8",
    windowsHide: true,
  }).trim();
  result = spawnSync(
    "wsl.exe",
    ["--exec", "python3", path, ...process.argv.slice(2)],
    {
      stdio: "inherit",
      windowsHide: true,
    },
  );
} else {
  result = spawnSync("python3", [script, ...process.argv.slice(2)], {
    stdio: "inherit",
  });
}
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
