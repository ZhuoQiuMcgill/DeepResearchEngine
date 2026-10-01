"""Actual process fixtures for bounded-drain and descendant acceptance."""
import os
import subprocess
import sys
import time

mode = sys.argv[1]
if mode == "echo":
    body = sys.stdin.buffer.read(); sys.stdout.buffer.write(body)
elif mode == "stdout_flood":
    while True: sys.stdout.buffer.write(b"x" * 16384); sys.stdout.buffer.flush()
elif mode == "stderr_flood":
    while True: sys.stderr.buffer.write(b"x" * 16384); sys.stderr.buffer.flush()
elif mode == "descendant":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    print(child.pid, flush=True)
    if len(sys.argv) > 2: time.sleep(120)
elif mode == "crash_with_descendant":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    print(child.pid, flush=True)
    sys.stderr.buffer.write(b"worker aborted before a response\n")
    sys.stderr.buffer.flush()
    os._exit(61)
elif mode == "memory":
    chunks = []
    while True: chunks.append(bytearray(8 << 20))
elif mode == "sleep":
    time.sleep(120)
elif mode == "marker":
    from pathlib import Path
    Path(sys.argv[2]).write_text("worker executed", encoding="utf-8")
