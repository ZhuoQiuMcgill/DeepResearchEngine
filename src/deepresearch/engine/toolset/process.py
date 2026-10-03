"""Bounded one-shot processes; Windows jobs are assigned before resume."""
from __future__ import annotations

import asyncio
import ctypes
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field

from .common import ToolFault


@dataclass
class ProcessOutcome:
    exit_code: int | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    stdin_bytes: int = 0
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    termination_reason: str | None = None
    cleanup_complete: bool = False
    pid: int | None = None
    peak_job_memory_bytes: int | None = None
    peak_process_memory_bytes: int | None = None
    duration_ms: int = 0


if os.name == "nt":
    import msvcrt
    from ctypes import wintypes as W
    K = ctypes.WinDLL("kernel32", use_last_error=True)
    SIZE_T = ctypes.c_size_t
    class STARTUPINFO(ctypes.Structure):
        _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR),
            ("lpTitle", W.LPWSTR), ("dwX", W.DWORD), ("dwY", W.DWORD),
            ("dwXSize", W.DWORD), ("dwYSize", W.DWORD), ("dwXCountChars", W.DWORD),
            ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD), ("dwFlags", W.DWORD),
            ("wShowWindow", W.WORD), ("cbReserved2", W.WORD), ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", W.HANDLE), ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE)]
    class STARTUPINFOEX(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFO), ("lpAttributeList", ctypes.c_void_p)]
    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE), ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]
    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", SIZE_T), ("MaximumWorkingSetSize", SIZE_T),
            ("ActiveProcessLimit", W.DWORD), ("Affinity", SIZE_T), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]
    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", SIZE_T), ("JobMemoryLimit", SIZE_T),
            ("PeakProcessMemoryUsed", SIZE_T), ("PeakJobMemoryUsed", SIZE_T)]
    class ACCOUNTING(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
            ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
            ("TotalPageFaultCount", W.DWORD), ("TotalProcesses", W.DWORD), ("ActiveProcesses", W.DWORD), ("TotalTerminatedProcesses", W.DWORD)]
    class COMPLETION_PORT(ctypes.Structure):
        _fields_ = [("CompletionKey", ctypes.c_void_p), ("CompletionPort", W.HANDLE)]
    K.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]; K.CreateJobObjectW.restype = W.HANDLE
    K.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
    K.QueryInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD, ctypes.c_void_p]
    K.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
    K.TerminateJobObject.argtypes = [W.HANDLE, W.UINT]
    K.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
    K.CloseHandle.argtypes = [W.HANDLE]
    K.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]; K.WaitForSingleObject.restype = W.DWORD
    K.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
    K.ResumeThread.argtypes = [W.HANDLE]; K.ResumeThread.restype = W.DWORD
    K.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, W.DWORD, W.DWORD, ctypes.POINTER(SIZE_T)]
    K.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, W.DWORD, SIZE_T, ctypes.c_void_p, SIZE_T, ctypes.c_void_p, ctypes.c_void_p]
    K.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    K.CreateProcessW.argtypes = [W.LPCWSTR, W.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, W.BOOL,
        W.DWORD, ctypes.c_void_p, W.LPCWSTR, ctypes.POINTER(STARTUPINFOEX), ctypes.POINTER(PROCESS_INFORMATION)]
    K.CreateIoCompletionPort.argtypes = [W.HANDLE, W.HANDLE, SIZE_T, W.DWORD]
    K.CreateIoCompletionPort.restype = W.HANDLE
    K.GetQueuedCompletionStatus.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD), ctypes.POINTER(SIZE_T), ctypes.POINTER(ctypes.c_void_p), W.DWORD]


class _WindowsProcess:
    def __init__(self, argv, memory_bytes, env):
        self.job = K.CreateJobObjectW(None, None)
        self.completion = None
        self.pi = PROCESS_INFORMATION()
        self.files = []
        if not self.job: raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = EXTENDED_LIMIT()
            limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x200  # kill-on-close, job memory
            limits.JobMemoryLimit = memory_bytes
            if not K.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.completion = K.CreateIoCompletionPort(ctypes.c_void_p(-1), None, 0, 1)
            if not self.completion: raise ctypes.WinError(ctypes.get_last_error())
            port = COMPLETION_PORT(ctypes.c_void_p(1), self.completion)
            if not K.SetInformationJobObject(self.job, 7, ctypes.byref(port), ctypes.sizeof(port)):
                raise ctypes.WinError(ctypes.get_last_error())
            ir, iw = os.pipe(); or_, ow = os.pipe(); er, ew = os.pipe()
            child_fds = [ir, ow, ew]
            for fd in child_fds: os.set_inheritable(fd, True)
            self.stdin = os.fdopen(iw, "wb", buffering=0)
            self.stdout = os.fdopen(or_, "rb", buffering=0)
            self.stderr = os.fdopen(er, "rb", buffering=0)
            self.files = [self.stdin, self.stdout, self.stderr]
            handles = (W.HANDLE * 3)(*[msvcrt.get_osfhandle(fd) for fd in child_fds])
            size = SIZE_T()
            K.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
            attrs = ctypes.create_string_buffer(size.value)
            if not K.InitializeProcThreadAttributeList(attrs, 1, 0, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not K.UpdateProcThreadAttribute(attrs, 0, 0x20002, ctypes.byref(handles), ctypes.sizeof(handles), None, None):
                    raise ctypes.WinError(ctypes.get_last_error())
                startup = STARTUPINFOEX(); startup.StartupInfo.cb = ctypes.sizeof(startup)
                startup.StartupInfo.dwFlags = 0x100
                startup.StartupInfo.hStdInput, startup.StartupInfo.hStdOutput, startup.StartupInfo.hStdError = handles
                startup.lpAttributeList = ctypes.cast(attrs, ctypes.c_void_p)
                cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
                environment = ctypes.create_unicode_buffer("\0".join(f"{k}={v}" for k, v in sorted(env.items(), key=lambda p: p[0].upper())) + "\0\0")
                flags = 0x4 | 0x08000000 | 0x80000 | 0x400  # suspended/no-window/extended/unicode
                if not K.CreateProcessW(argv[0], cmd, None, None, True, flags, environment, None, ctypes.byref(startup), ctypes.byref(self.pi)):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not K.AssignProcessToJobObject(self.job, self.pi.hProcess):
                    K.TerminateProcess(self.pi.hProcess, 1)
                    K.WaitForSingleObject(self.pi.hProcess, 5000)
                    raise ctypes.WinError(ctypes.get_last_error())
                if K.ResumeThread(self.pi.hThread) == 0xffffffff:
                    self.kill(); raise ctypes.WinError(ctypes.get_last_error())
                K.CloseHandle(self.pi.hThread); self.pi.hThread = None
            finally:
                K.DeleteProcThreadAttributeList(attrs)
                for fd in child_fds: os.close(fd)
            self.pid = self.pi.dwProcessId
        except BaseException:
            self.close(); raise

    def poll(self):
        if K.WaitForSingleObject(self.pi.hProcess, 0) == 0:
            code = W.DWORD(); K.GetExitCodeProcess(self.pi.hProcess, ctypes.byref(code)); return code.value
        return None

    def kill(self):
        if self.job: K.TerminateJobObject(self.job, 1)

    def settled(self):
        info = ACCOUNTING()
        return bool(K.QueryInformationJobObject(self.job, 1, ctypes.byref(info), ctypes.sizeof(info), None)) and info.ActiveProcesses == 0

    def peaks(self):
        info = EXTENDED_LIMIT()
        if K.QueryInformationJobObject(self.job, 9, ctypes.byref(info), ctypes.sizeof(info), None):
            return info.PeakJobMemoryUsed, info.PeakProcessMemoryUsed
        return None, None

    def memory_breached(self):
        message, key, pointer = W.DWORD(), SIZE_T(), ctypes.c_void_p()
        breached = False
        while K.GetQueuedCompletionStatus(self.completion, ctypes.byref(message), ctypes.byref(key), ctypes.byref(pointer), 0):
            if message.value in (9, 10): breached = True  # process/job memory ceiling
        return breached

    def close(self):
        for file in getattr(self, "files", []):
            try: file.close()
            except OSError: pass
        for handle in (self.pi.hThread, self.pi.hProcess, self.job, self.completion):
            if handle: K.CloseHandle(handle)
        self.job = None


def _run(argv, payload, timeout, stdout_cap, stderr_cap, cancelled, memory_bytes, env):
    start = time.monotonic()
    result = ProcessOutcome(stdin_bytes=len(payload))
    stopped = threading.Event()
    process = None
    threads = []
    try:
        if os.name == "nt": process = _WindowsProcess(argv, memory_bytes, env)
        else:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, env=env)
        result.pid = process.pid
        def stop(reason):
            if not stopped.is_set(): result.termination_reason = reason; stopped.set()
            if os.name == "nt": process.kill()
            else:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
        def pump(stream, attr, cap):
            total, chunks = 0, []
            try:
                while True:
                    chunk = stream.read(16384)
                    if not chunk: break
                    total += len(chunk)
                    remaining = cap - sum(map(len, chunks))
                    if remaining > 0: chunks.append(chunk[:remaining])
                    if total > cap: stop("stream_limit"); break
            except OSError: pass
            setattr(result, attr, b"".join(chunks)); setattr(result, attr + "_bytes", total)
        def write():
            try:
                view = memoryview(payload)
                while view:
                    sent = process.stdin.write(view)
                    if not sent: break
                    view = view[sent:]
            except (OSError, BrokenPipeError): pass
            finally:
                try: process.stdin.close()
                except OSError: pass
        for target, args in ((write, ()), (pump, (process.stdout, "stdout", stdout_cap)), (pump, (process.stderr, "stderr", stderr_cap))):
            thread = threading.Thread(target=target, args=args, daemon=True); thread.start(); threads.append(thread)
        while process.poll() is None:
            if os.name == "nt" and process.memory_breached(): stop("memory_limit")
            elif cancelled.is_set(): stop("cancelled")
            elif time.monotonic() - start >= timeout: stop("deadline")
            time.sleep(0.01)
        result.exit_code = process.poll()
        if os.name == "nt" and process.memory_breached(): stop("memory_limit")
        # Always settle descendants, including those holding inherited pipes after root exit.
        if os.name == "nt":
            if not process.settled(): process.kill()
        else:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        cleanup_until = time.monotonic() + 5
        for thread in threads: thread.join(max(0, cleanup_until - time.monotonic()))
        if os.name == "nt":
            while not process.settled() and time.monotonic() < cleanup_until: time.sleep(.01)
            result.cleanup_complete = process.settled() and all(not t.is_alive() for t in threads)
            result.peak_job_memory_bytes, result.peak_process_memory_bytes = process.peaks()
        else: result.cleanup_complete = all(not t.is_alive() for t in threads)
        if not result.cleanup_complete: result.termination_reason = result.termination_reason or "cleanup_incomplete"
    except OSError:
        result.termination_reason = "spawn_failed"
        result.cleanup_complete = process is None
    finally:
        if process is not None:
            if os.name == "nt": process.close()
            else:
                for file in (process.stdin, process.stdout, process.stderr):
                    try: file.close()
                    except OSError: pass
        result.duration_ms = int((time.monotonic() - start) * 1000)
    return result


class ProcessRunner:
    """No shell, bounded streams, minimal credential-free worker environment."""
    def __init__(self, *, memory_bytes: int = 512 << 20):
        self.memory_bytes = memory_bytes
        self._active: set[threading.Event] = set()
        self._closed = False
        self._unconfirmed = False

    async def run(self, argv, payload, *, timeout, stdout_cap, stderr_cap=65536, context_cancelled=None):
        if self._closed: raise ToolFault("EXECUTOR_CLOSED", "Tool executor is closed")
        flag = threading.Event(); self._active.add(flag)
        allowed = {"SystemRoot", "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "PYTHONPATH"}
        env = {k: v for k, v in os.environ.items() if k in allowed}
        env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
        task = asyncio.create_task(asyncio.to_thread(_run, list(argv), payload, timeout, stdout_cap, stderr_cap,
                                                    flag, self.memory_bytes, env))
        async def cancellation_watch():
            while not task.done():
                if context_cancelled is not None and context_cancelled(): flag.set(); return
                await asyncio.sleep(.02)
        watch = asyncio.create_task(cancellation_watch())
        try:
            outcome = await asyncio.shield(task)
            self._unconfirmed = self._unconfirmed or not outcome.cleanup_complete
            return outcome
        except asyncio.CancelledError:
            flag.set()
            try: await asyncio.wait_for(asyncio.shield(task), 6)
            except (asyncio.TimeoutError, Exception): pass
            raise
        finally:
            watch.cancel(); self._active.discard(flag)

    async def close(self, deadline=None):
        self._closed = True
        for flag in self._active: flag.set()
        until = time.monotonic() + 6
        while self._active and time.monotonic() < until: await asyncio.sleep(.02)
        return {"complete": not self._active and not self._unconfirmed, "pending_processes": len(self._active), "unconfirmed": self._unconfirmed}
