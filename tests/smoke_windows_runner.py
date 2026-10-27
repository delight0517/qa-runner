"""Run only a temporary synthetic WinForms app on a private Win32 desktop."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from ctypes import wintypes

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa_runner import WindowsRunner


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def current_input_desktop_name() -> str:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
    user32.GetThreadDesktop.restype = wintypes.HANDLE
    user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                  wintypes.LPVOID, wintypes.DWORD,
                                                  ctypes.POINTER(wintypes.DWORD)]
    user32.GetUserObjectInformationW.restype = wintypes.BOOL
    handle = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
    buffer = ctypes.create_unicode_buffer(128)
    needed = wintypes.DWORD()
    if not handle or not user32.GetUserObjectInformationW(handle, 2, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
        raise OSError(ctypes.get_last_error(), "Could not read current input desktop name")
    return buffer.value


def compile_fixture(destination: Path) -> Path:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [windir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
                  windir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe"]
    compiler = next((candidate for candidate in candidates if candidate.is_file()), None)
    require(compiler is not None, "Install the .NET Framework C# compiler to run this synthetic smoke check.")
    source = Path(__file__).parent / "fixtures" / "SyntheticWindow.cs"
    exe = destination / "QA-RUNNER-SYNTHETIC-FIXTURE.exe"
    result = subprocess.run([str(compiler), "/nologo", "/target:winexe", f"/out:{exe}", str(source)],
                            capture_output=True, text=True, timeout=30, creationflags=0x08000000)
    require(result.returncode == 0 and exe.is_file(), "Synthetic fixture compilation failed: " + result.stderr[-600:])
    return exe


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This smoke check requires Windows.")
    import win32api
    import win32con
    import win32event
    import win32gui
    import win32process

    with tempfile.TemporaryDirectory(prefix="qa-runner-smoke-") as directory:
        root = Path(directory)
        executable = compile_fixture(root)
        child_pid_file = root / "child-pid.txt"
        desktop_before = current_input_desktop_name()
        foreground_before = int(win32gui.GetForegroundWindow())
        monitors_before = tuple((tuple(map(int, rect)) for _handle, _dc, rect
                                 in win32api.EnumDisplayMonitors(None, None)))

        runner = WindowsRunner()
        pid, run_id = runner.launch("synthetic-fixture", str(executable), [str(child_pid_file)], 180)
        session = runner.get(run_id)
        require(session is not None, "The runner did not retain the owned session.")
        primary = win32api.OpenProcess(win32con.SYNCHRONIZE, False, pid)
        child = None
        try:
            windows = []
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not windows:
                windows = [window for window in session.windows() if window.pid == pid and window.visible]
                time.sleep(0.1)
            require(bool(windows), "No visible window was found on the private desktop.")
            require(child_pid_file.is_file(), "The fixture child process did not start.")
            child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())
            child = win32api.OpenProcess(win32con.SYNCHRONIZE, False, child_pid)
            titles = [win32gui.GetWindowText(window.hwnd) for window in windows]
            require("QA Runner Synthetic Private Window" in titles, f"Unexpected private windows: {titles}")

            foreground = int(win32gui.GetForegroundWindow())
            _thread, foreground_pid = win32process.GetWindowThreadProcessId(foreground) if foreground else (0, 0)
            require(int(foreground_pid) not in {pid, child_pid}, "QA-owned process took foreground focus.")
            require(current_input_desktop_name() == desktop_before == "Default",
                    "The runner changed the active input desktop.")
            monitors_after = tuple((tuple(map(int, rect)) for _handle, _dc, rect
                                    in win32api.EnumDisplayMonitors(None, None)))
            require(monitors_after == monitors_before, "The runner changed monitor topology.")
        finally:
            runner.stop(run_id)

        require(win32event.WaitForSingleObject(primary, 5000) == win32event.WAIT_OBJECT_0,
                "The runner-owned main process remained alive after stop.")
        require(child is not None and win32event.WaitForSingleObject(child, 5000) == win32event.WAIT_OBJECT_0,
                "The runner-owned child process remained alive after stop.")
        win32api.CloseHandle(primary)
        if child is not None:
            win32api.CloseHandle(child)
        print(json.dumps({"result": "passed", "target": "temporary WinForms fixture",
                          "private_desktop_window": "visible", "foreground_unchanged_by_runner": True,
                          "input_desktop": desktop_before, "monitor_topology_unchanged": True,
                          "primary_and_child_cleanup": "passed"}))


if __name__ == "__main__":
    main()
