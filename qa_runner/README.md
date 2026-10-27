# QA Runner (local-first)

The reusable engine package is independent of the QAWorkbench web UI. It owns a bounded Windows process job and launches a registered test executable on a private Win32 desktop. Consumers provide their own presentation and UI Automation adapter, then report evidence through the shared QA result contract.

## Current capabilities

- `PrivateDesktopSession` creates a unique non-current desktop and launches one executable there.
- The target is assigned to a Windows Job Object before its main thread resumes. The job bounds process count and memory, kills descendants on close, and has a bounded wall timeout.
- It does not switch desktops, synthesize global input, or capture the user's desktop.
- `windows[].hwnd` values are only accepted for that run and primary PID. Multi-process windows remain uncovered. QAWorkbench exact-HWND capture uses `PrintWindow`/`WM_PRINT`, compensates for target DPI, and rejects empty black frames; it passed the synthetic WinForms fixture. Apps that do not support these APIs remain visually uncovered.
- This is execution isolation and focus protection, not a security sandbox. A target can still access the user's files/network unless the caller supplies OS-level containment. Never use production builds or live credentials.

## Install

```powershell
python -m pip install ".[windows]"
```

The package is Windows-only for native GUI execution. Browser automation remains a QAWorkbench consumer adapter.

## Minimal use

```python
from qa_runner import PrivateDesktopSession

with PrivateDesktopSession(wall_timeout_seconds=300) as run:
    pid = run.launch(r"C:\path\to\disposable-test-build.exe")
    windows = run.windows()
    # Inspect only these run-owned HWNDs with your UIA adapter.
    # If pixels or a control pattern are unavailable, report uncovered.
```

`WindowsRunner` supplies a process-local session registry, per-run temporary profile, launch and stop lifecycle. Registry reads/writes are synchronized, but consumers must serialize observation and stop for each run. Cross-process clients need a separate authenticated adapter; Python globals cannot be shared. `launch()` rejects an existing executable with the same basename to avoid single-instance IPC handoff. It accepts one primary executable, at most 48 bounded arguments, and fails closed when the process/job setup cannot be verified. Call `stop(run_id)` in a `finally` block. The low-level `PrivateDesktopSession` also supports a context manager.

## Project status

Alpha version 0.1.0. The package source and wheel have passed repeated synthetic WinForms launch, UIA inventory/action, exact-HWND before/after pixel capture, foreground/input-desktop/topology invariance and runner cleanup checks on Windows. No production app, OAuth/account, or provider request was used. The package includes a process-local session manager; cross-process adapters and user approval flows belong to consuming applications.
