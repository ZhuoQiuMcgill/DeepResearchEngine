"""Start/status/stop the pinned local SearXNG service using Docker Compose.

Run: uv run --locked python examples/manage_web_tools.py start
Browser setup is explicit: uv run --locked playwright install chromium --only-shell
"""
from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import subprocess
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "status", "stop"))
    args = parser.parse_args()
    command = ["docker", "compose", "-f", str(ROOT / "deploy/web-tools/compose.yaml")]
    if args.command == "start":
        directory = ROOT / "local/web-tools-service"
        directory.mkdir(parents=True, exist_ok=True)
        settings = directory / "settings.yml"
        if not settings.exists():
            template = (ROOT / "deploy/web-tools/settings.yml.template").read_text(encoding="utf-8")
            with settings.open("x", encoding="utf-8") as output:
                output.write(template.replace("__LOCAL_SECRET__", secrets.token_urlsafe(32)))
        subprocess.run(command + ["up", "-d"], cwd=ROOT, check=True)
        opener = build_opener(ProxyHandler({}))
        for _ in range(30):
            try:
                with opener.open("http://127.0.0.1:18888/", timeout=1) as response:
                    if response.status == 200:
                        print("SearXNG ready: http://127.0.0.1:18888 (web.search@4)")
                        return
            except (URLError, OSError):
                pass
            time.sleep(1)
        raise RuntimeError("SearXNG did not become ready; inspect docker compose logs")
    subprocess.run(command + (["ps"] if args.command == "status" else ["down"]), cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
