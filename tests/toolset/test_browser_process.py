"""Native Chromium Job cleanup; requires `uv run --locked playwright install chromium --only-shell`.

Missing browser binaries skip explicitly. Launch failures and cleanup failures do
not skip. These tests perform no external HTTP requests and never install tools.
"""
from __future__ import annotations

import os
import time

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Actual Chromium descendant ownership in a Windows Job")
@pytest.mark.parametrize("stop", ["cancel", "deadline"])
def test_actual_browser_job_stops_driver_browser_and_renderers(monkeypatch, tmp_path, record_property, stop):
    import asyncio
    import ctypes
    import sys
    from ctypes import wintypes as W
    from pathlib import Path

    from deepresearch.engine.toolset import process

    marker = tmp_path / "browser-ready"
    owners, closed_jobs, handles = [], [], []
    native_process = process._WindowsProcess

    class ObservedProcess(native_process):
        def __init__(self, *args):
            super().__init__(*args)
            owners.append(self)

        def close(self):
            if self.job:
                accounting = process.ACCOUNTING()
                ok = process.K.QueryInformationJobObject(
                    self.job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None)
                closed_jobs.append((bool(ok), accounting.TotalProcesses, accounting.ActiveProcesses))
            super().close()

    monkeypatch.setattr(process, "_WindowsProcess", ObservedProcess)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.CloseHandle.argtypes = [W.HANDLE]

    class JobProcesses(ctypes.Structure):
        _fields_ = [("assigned", W.DWORD), ("count", W.DWORD), ("pids", ctypes.c_size_t * 64)]

    async def check():
        cancelled = False
        runner = process.ProcessRunner()  # Production 512 MiB Job, unchanged.
        task = asyncio.create_task(runner.run(
            (sys.executable, str(Path(__file__).with_name("browser_process_fixture.py")), str(marker)),
            b"", timeout=6 if stop == "deadline" else 15, stdout_cap=4096,
            context_cancelled=lambda: cancelled))
        try:
            ready_until = time.monotonic() + 5
            while not marker.exists() and not task.done() and time.monotonic() < ready_until:
                await asyncio.sleep(.02)
            if not marker.exists() and task.done():
                early = task.result()
                if early.stdout.strip() == b"CHROMIUM_NOT_INSTALLED":
                    assert early.cleanup_complete
                    pytest.skip("Install bundled Chromium: uv run --locked playwright install chromium --only-shell")
            assert marker.exists(), "Chromium must reach the real capture relay before cancellation"
            assert len(owners) == 1
            members = JobProcesses()
            assert process.K.QueryInformationJobObject(
                owners[0].job, 3, ctypes.byref(members), ctypes.sizeof(members), None)
            assert 4 <= members.count <= 64  # Python, Node driver, browser, renderer (plus utilities).
            names = []
            for pid in members.pids[:members.count]:
                handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
                assert handle
                handles.append(handle)
                image_name, length = ctypes.create_unicode_buffer(32768), W.DWORD(32768)
                assert kernel.QueryFullProcessImageNameW(handle, 0, image_name, ctypes.byref(length))
                names.append(Path(image_name.value).name.lower())
                assert kernel.WaitForSingleObject(handle, 0) == 258  # STILL ACTIVE.
            assert "node.exe" in names
            assert sum("chrome" in name or "headless" in name for name in names) >= 2
            if stop == "cancel":
                cancelled = True
            outcome = await asyncio.wait_for(task, 10)
            assert outcome.termination_reason == ("cancelled" if stop == "cancel" else "deadline")
            assert outcome.cleanup_complete and outcome.peak_job_memory_bytes > 0
            record_property("peak_job_memory_bytes", outcome.peak_job_memory_bytes)
            record_property("peak_process_memory_bytes", outcome.peak_process_memory_bytes)
            record_property("observed_job_process_count", members.count)
            record_property("termination_reason", outcome.termination_reason)
            assert closed_jobs and closed_jobs[-1][0] and closed_jobs[-1][1] >= members.count
            assert closed_jobs[-1][2] == 0
            for handle in handles:
                # Job accounting can reach zero just before a terminating
                # process handle signals; verify actual exit with a bounded wait.
                assert kernel.WaitForSingleObject(handle, 1000) == 0
        finally:
            cancelled = True
            assert (await runner.close())["complete"]
            if not task.done():
                await asyncio.wait_for(task, 7)
            for handle in handles:
                kernel.CloseHandle(handle)

    asyncio.run(check())
