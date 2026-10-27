# QA Runner

QA Runner provides bounded Windows process isolation for desktop application QA. It creates a separate Win32 desktop, starts one explicitly selected disposable executable inside a Windows Job Object, assigns a per-run temporary profile, enforces memory/process/time limits, and terminates the owned process tree when stopped.

It never switches the user's desktop or injects global mouse/keyboard input. UI Automation, screenshots, browser runs, report storage and user approvals belong to the consuming application. The engine only accepts HWNDs from its current run and primary process; unsupported multi-process windows must be reported as uncovered.

## Install

```powershell
python -m pip install ".[windows]"
```

Requires Python 3.11 or later. Browser testing and the optional Codex/Only Chat integrations are supplied by consumer applications, not this package.

## Basic use

```python
from qa_runner import PrivateDesktopSession

with PrivateDesktopSession(wall_timeout_seconds=300) as run:
    pid = run.launch(r"C:\path\to\disposable-test-build.exe")
    windows = run.windows()  # HWNDs owned by this run and its primary PID
```

For repeated launches and isolated `%APPDATA%`/`%LOCALAPPDATA%`/`%TEMP%` profiles, use `WindowsRunner` and call `stop(run_id)` in a `finally` block. See [`qa_runner/README.md`](qa_runner/README.md) and [`qa_runner/CONSUMER_CONTRACT.md`](qa_runner/CONSUMER_CONTRACT.md).

## Security boundary

This protects desktop focus and bounds runner-owned processes. It is **not a security sandbox**: a target can still access files, network services, credentials outside its temporary profile, or machine-wide state. Use only disposable builds and data. A successful launch does not make a production app safe to test.

## Synthetic Windows smoke check

```powershell
python -m pip install ".[windows]"
python tests/smoke_windows_runner.py
```

The smoke check compiles a small WinForms fixture to a temporary directory. It requires the .NET Framework C# compiler and a Windows desktop session. It checks private-desktop window enumeration, that the fixture did not take foreground focus or switch the input desktop/change monitor topology, and that the Job Object stops its main and child processes.

## Status

Alpha, version 0.1.0. The source and wheel have been exercised against a synthetic WinForms app on Windows. This does not establish compatibility with every desktop framework or with production apps. Applications that cannot render on a non-current desktop, use windows from helper processes, or reject `PrintWindow`/`WM_PRINT` may remain visually uncovered.

MIT licensed. See [`LICENSE`](LICENSE).
