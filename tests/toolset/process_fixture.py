"""Actual process fixtures for bounded-drain and descendant acceptance."""
import os
import json
import subprocess
import sys
import time


def report_child(child):
    identity = {"pid": child.pid}
    if os.name == "nt":
        # Give the supervising test a stable identity before this root exits.
        # Looking up its PID after cleanup could observe a different process.
        import ctypes
        from ctypes import wintypes as W
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = W.HANDLE
        kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        kernel.OpenProcess.restype = W.HANDLE
        kernel.DuplicateHandle.argtypes = [W.HANDLE, W.HANDLE, W.HANDLE,
            ctypes.POINTER(W.HANDLE), W.DWORD, W.BOOL, W.DWORD]
        kernel.CloseHandle.argtypes = [W.HANDLE]
        # A virtualenv redirector can be this worker's immediate parent.
        observer_pid = int(sys.argv[sys.argv.index("--observer-pid") + 1])
        parent = kernel.OpenProcess(0x0040, False, observer_pid)
        copied = W.HANDLE()
        assert parent
        try:
            assert kernel.DuplicateHandle(kernel.GetCurrentProcess(), int(child._handle),
                parent, ctypes.byref(copied), 0x100000, False, 0)
            identity["handle"] = copied.value
        finally:
            kernel.CloseHandle(parent)
    print(json.dumps(identity), flush=True)

mode = sys.argv[1]
if mode == "echo":
    body = sys.stdin.buffer.read(); sys.stdout.buffer.write(body)
elif mode == "stdout_flood":
    while True: sys.stdout.buffer.write(b"x" * 16384); sys.stdout.buffer.flush()
elif mode == "stderr_flood":
    while True: sys.stderr.buffer.write(b"x" * 16384); sys.stderr.buffer.flush()
elif mode == "descendant":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    report_child(child)
    if "wait" in sys.argv[2:]: time.sleep(120)
elif mode == "crash_with_descendant":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    report_child(child)
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
