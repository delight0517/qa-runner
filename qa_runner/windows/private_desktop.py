from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PrivateDesktopError(RuntimeError):
    pass


class TargetAlreadyRunning(PrivateDesktopError):
    pass


@dataclass
class DesktopWindow:
    hwnd: int
    pid: int
    visible: bool


class PrivateDesktopSession:
    """Run one GUI target on a separate Win32 desktop without switching to it.

    This keeps the target's windows and its own default-window activation on a
    non-current desktop in the interactive window station. It does not make
    the target a security sandbox: use a disposable build/profile and never
    register a production app with live credentials.
    """

    DESKTOP_CREATEWINDOW = 0x0002
    DESKTOP_ENUMERATE = 0x0040
    DESKTOP_READOBJECTS = 0x0001
    DESKTOP_WRITEOBJECTS = 0x0080
    CREATE_SUSPENDED = 0x00000004
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    PROCESS_MEMORY_LIMIT = 0x00000100
    JOB_MEMORY_LIMIT = 0x00000200
    ACTIVE_PROCESS_LIMIT = 0x00000008
    KILL_ON_JOB_CLOSE = 0x00002000
    MAX_NATIVE_MEMORY_BYTES = 6 * 1024 * 1024 * 1024
    MAX_PROCESSES = 32

    def __init__(self, run_id: str | None = None, wall_timeout_seconds: int = 900):
        if os.name != "nt":
            raise PrivateDesktopError("Private Win32 desktops are available only on Windows.")
        if not 30 <= int(wall_timeout_seconds) <= 3600:
            raise ValueError("Wall timeout must be between 30 and 3600 seconds.")
        try:
            import win32api
            import win32event
            import win32job
            import win32process
        except ImportError as exc:
            raise PrivateDesktopError("pywin32 is required for isolated Windows desktop runs.") from exc

        self._win32api = win32api
        self._win32event = win32event
        self._win32job = win32job
        self._win32process = win32process
        self.run_id = run_id or str(uuid.uuid4())
        self.desktop_name = f"QAWorkbench-{self.run_id.replace('-', '')[:20]}"
        self.desktop_path = f"winsta0\\{self.desktop_name}"
        self.wall_timeout_seconds = int(wall_timeout_seconds)
        self.started_at: float | None = None
        self.process_handle = None
        self.thread_handle = None
        self.pid: int | None = None
        self.job_handle = None
        self.desktop_handle = None
        self.executable: Path | None = None
        self._closed = False
        self._lock = threading.RLock()
        self._timeout_timer: threading.Timer | None = None
        self.timeout_reached = False
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_apis()
        self._create_desktop()
        try:
            self._create_job()
        except Exception:
            self._close_desktop()
            raise

    def _configure_apis(self) -> None:
        self._user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPVOID,
                                                wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
        self._user32.CreateDesktopW.restype = wintypes.HANDLE
        self._user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        self._user32.CloseDesktop.restype = wintypes.BOOL

    def _create_desktop(self) -> None:
        access = self.DESKTOP_CREATEWINDOW | self.DESKTOP_ENUMERATE | self.DESKTOP_READOBJECTS | self.DESKTOP_WRITEOBJECTS
        handle = self._user32.CreateDesktopW(self.desktop_name, None, None, 0, access, None)
        if not handle:
            code = ctypes.get_last_error()
            raise PrivateDesktopError(f"Could not create the isolated QA desktop (Win32 {code}).")
        self.desktop_handle = int(handle)

    def _create_job(self) -> None:
        job = self._win32job.CreateJobObject(None, "")
        try:
            info = self._win32job.QueryInformationJobObject(
                job, self._win32job.JobObjectExtendedLimitInformation
            )
            info["BasicLimitInformation"]["LimitFlags"] |= (
                self.KILL_ON_JOB_CLOSE | self.ACTIVE_PROCESS_LIMIT | self.JOB_MEMORY_LIMIT
            )
            info["BasicLimitInformation"]["ActiveProcessLimit"] = self.MAX_PROCESSES
            info["JobMemoryLimit"] = self.MAX_NATIVE_MEMORY_BYTES
            self._win32job.SetInformationJobObject(
                job, self._win32job.JobObjectExtendedLimitInformation, info
            )
        except Exception:
            self._win32api.CloseHandle(job)
            raise
        self.job_handle = job

    def launch(self, executable: str, arguments: list[str] | None = None,
               env: dict[str, str] | None = None, cwd: str | None = None) -> int:
        if self._closed or self.pid is not None:
            raise PrivateDesktopError("A private desktop session can launch exactly one target process.")
        path = Path(executable).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".exe":
            raise ValueError("Registered executable no longer exists.")
        args = [str(arg) for arg in (arguments or [])]
        if len(args) > 48 or any(len(arg) > 2048 or "\0" in arg for arg in args):
            raise ValueError("Native launch arguments exceed the bounded allowlist.")
        if self._same_executable_running(path):
            raise TargetAlreadyRunning("The same executable is already running; refusing a possible single-instance handoff.")

        startup = self._win32process.STARTUPINFO()
        startup.lpDesktop = self.desktop_path
        startup.dwFlags |= 0x00000001  # STARTF_USESHOWWINDOW
        startup.wShowWindow = 1  # SW_SHOWNORMAL on the private desktop only
        command_line = subprocess.list2cmdline([str(path), *args])
        child_env = dict(os.environ if env is None else env)
        flags = self.CREATE_SUSPENDED | self.CREATE_NEW_PROCESS_GROUP | self.CREATE_UNICODE_ENVIRONMENT
        try:
            hprocess, hthread, pid, _tid = self._win32process.CreateProcess(
                str(path), command_line, None, None, False, flags,
                child_env, cwd or str(path.parent), startup,
            )
        except Exception as exc:
            raise PrivateDesktopError(f"Target process creation failed ({type(exc).__name__}).") from exc

        self.process_handle, self.thread_handle, self.pid = hprocess, hthread, int(pid)
        self.executable = path
        try:
            # Assign before resume so descendants inherit job ownership.
            self._win32job.AssignProcessToJobObject(self.job_handle, self.process_handle)
            self._win32process.ResumeThread(self.thread_handle)
            self.started_at = time.monotonic()
            self._timeout_timer = threading.Timer(self.wall_timeout_seconds, self._enforce_wall_timeout)
            self._timeout_timer.daemon = True
            self._timeout_timer.start()
            if self._same_executable_running(path, exclude_pid=self.pid):
                raise TargetAlreadyRunning("Another same-name process appeared during launch; terminating the isolated run.")
            return self.pid
        except Exception:
            try:
                self._win32process.TerminateProcess(self.process_handle, 1)
            except Exception:
                pass
            self.terminate()
            raise
        finally:
            if self.thread_handle is not None:
                self._win32api.CloseHandle(self.thread_handle)
                self.thread_handle = None

    @staticmethod
    def _same_executable_running(path: Path, exclude_pid: int | None = None) -> bool:
        """Conservative basename check; it avoids attaching to known single-instance apps."""
        try:
            result = subprocess.run(
                ["tasklist.exe", "/FI", f"IMAGENAME eq {path.name}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5, check=False, creationflags=0x08000000,
            )
        except Exception:
            # If the preflight cannot establish whether the target is already
            # running, fail closed rather than risk a single-instance handoff.
            raise PrivateDesktopError("Could not verify whether the target is already running.")
        if result.returncode != 0:
            raise PrivateDesktopError("Could not verify whether the target is already running.")
        for row in result.stdout.splitlines():
            if not row.strip() or row.startswith("INFO:"):
                continue
            try:
                columns = next(__import__("csv").reader([row]))
                if len(columns) < 2:
                    continue
                pid = int(columns[1])
                if pid != exclude_pid and columns[0].casefold() == path.name.casefold():
                    return True
            except (ValueError, StopIteration):
                continue
        return False

    def poll(self) -> int | None:
        if self.process_handle is None:
            return None
        if self._win32event.WaitForSingleObject(self.process_handle, 0) != 0:
            return None
        try:
            return int(self._win32process.GetExitCodeProcess(self.process_handle))
        except Exception:
            return -1

    def windows(self) -> list[DesktopWindow]:
        if not self.desktop_handle or not self.pid:
            return []
        import win32gui
        import win32process

        windows: list[DesktopWindow] = []

        def collect(hwnd: int, _extra: Any) -> bool:
            try:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                # The primary process is the only accepted owner in v0.1.
                # Modern multi-process apps are marked uncovered until their
                # job-owned descendant window enumeration is verified.
                if int(pid) == self.pid:
                    windows.append(DesktopWindow(int(hwnd), int(pid), bool(win32gui.IsWindowVisible(hwnd))))
            except Exception:
                return True
            return True

        win32gui.EnumDesktopWindows(self.desktop_handle, collect, None)
        return windows

    def _enforce_wall_timeout(self) -> None:
        self.timeout_reached = True
        self.terminate()

    def terminate(self) -> bool:
        with self._lock:
            if self._closed:
                return True
            if self._timeout_timer is not None and threading.current_thread() is not self._timeout_timer:
                self._timeout_timer.cancel()
            terminated = True
            if self.job_handle is not None:
                try:
                    self._win32job.TerminateJobObject(self.job_handle, 1)
                except Exception:
                    terminated = False
            if self.process_handle is not None:
                try:
                    self._win32event.WaitForSingleObject(self.process_handle, 5000)
                except Exception:
                    terminated = False
                try:
                    self._win32api.CloseHandle(self.process_handle)
                except Exception:
                    terminated = False
                self.process_handle = None
            if self.thread_handle is not None:
                try:
                    self._win32api.CloseHandle(self.thread_handle)
                except Exception:
                    pass
                self.thread_handle = None
            if self.job_handle is not None:
                try:
                    self._win32api.CloseHandle(self.job_handle)
                except Exception:
                    terminated = False
                self.job_handle = None
            self._close_desktop()
            self._closed = True
            return terminated

    def _close_desktop(self) -> None:
        if self.desktop_handle:
            self._user32.CloseDesktop(self.desktop_handle)
            self.desktop_handle = None

    def close(self) -> bool:
        return self.terminate()

    def __enter__(self) -> "PrivateDesktopSession":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
