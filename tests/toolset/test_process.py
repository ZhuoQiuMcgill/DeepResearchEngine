from __future__ import annotations

import asyncio
import ctypes
import os
import sys
from pathlib import Path

import pytest

from ebd.toolset.process import ProcessRunner

FIXTURE = str(Path(__file__).with_name("process_fixture.py"))


def run(mode, *, timeout=3, stdout_cap=65536, extra=()):
    async def check():
        runner = ProcessRunner()
        result = await runner.run((sys.executable, FIXTURE, mode, *extra), '{"hello":"中"}'.encode(), timeout=timeout, stdout_cap=stdout_cap)
        assert (await runner.close())["complete"]
        return result
    return asyncio.run(check())


def test_real_echo_and_job_measurement():
    result = run("echo")
    assert result.exit_code == 0 and result.stdout == '{"hello":"中"}'.encode()
    assert result.cleanup_complete
    if os.name == "nt": assert result.peak_job_memory_bytes > 0


@pytest.mark.parametrize("mode", ["stdout_flood", "stderr_flood"])
def test_actual_stream_flood_terminates_tree(mode):
    result = run(mode, stdout_cap=1024)
    assert result.termination_reason == "stream_limit" and result.cleanup_complete
    assert len(result.stdout) <= 1024 and len(result.stderr) <= 65536


@pytest.mark.parametrize("root_wait", [False, True])
def test_sleeping_descendant_and_inherited_pipes_are_removed(root_wait):
    result = run("descendant", timeout=.3, extra=("wait",) if root_wait else ())
    assert result.cleanup_complete
    child_pid = int(result.stdout.strip())
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x100000 | 0x1000, False, child_pid)
        if handle:
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            assert kernel.WaitForSingleObject(handle, 0) == 0
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]; kernel.CloseHandle(handle)
    else:
        with pytest.raises(ProcessLookupError): os.kill(child_pid, 0)


def test_python_cancellation_settles_actual_worker():
    async def check():
        runner = ProcessRunner()
        task = asyncio.create_task(runner.run((sys.executable, FIXTURE, "sleep"), b"", timeout=30, stdout_cap=1024))
        await asyncio.sleep(.1); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert (await runner.close())["complete"]
    asyncio.run(check())


@pytest.mark.skipif(os.name != "nt", reason="Windows Job committed-memory gate")
def test_actual_job_memory_limit_is_observed_and_tree_settles():
    async def check():
        runner = ProcessRunner(memory_bytes=64 << 20)
        result = await runner.run((sys.executable, FIXTURE, "memory"), b"", timeout=5, stdout_cap=1024)
        assert result.termination_reason == "memory_limit"
        assert result.cleanup_complete
        # Windows accounting can report a peak above the allocation ceiling;
        # the gate proves observed denial and cleanup, not exact RSS/peak bound.
        assert result.peak_job_memory_bytes > 0
        await runner.close()
    asyncio.run(check())


@pytest.mark.skipif(os.name != "nt", reason="Windows pre-resume assignment gate")
def test_failed_assignment_terminates_suspended_child_before_tool_code(monkeypatch, tmp_path):
    from ebd.toolset import process as process_module
    marker = tmp_path / "must-not-exist.txt"
    monkeypatch.setattr(process_module.K, "AssignProcessToJobObject", lambda *_: 0)
    result = run("marker", extra=(str(marker),))
    assert result.termination_reason == "spawn_failed" and result.cleanup_complete
    assert not marker.exists()
