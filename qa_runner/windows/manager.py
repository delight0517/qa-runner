"""Lifecycle manager for runner-owned Windows QA sessions."""

from __future__ import annotations

import os
import tempfile
import threading
import uuid
from pathlib import Path

from .private_desktop import PrivateDesktopSession


class WindowsRunner:
    """Owns bounded isolated sessions for one consumer process.

    Registry reads/writes are synchronized. Session operations are not a
    cross-process lock; consumers must serialize observations and stop for one
    run. The registry is process-local. Other processes must use an
    authenticated adapter rather than sharing Python globals.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, PrivateDesktopSession] = {}
        self._profiles: dict[str, Path] = {}
        self._lock = threading.RLock()

    @property
    def sessions(self) -> dict[str, PrivateDesktopSession]:
        """Read-only-by-convention compatibility view for the UIA adapter."""
        return self._sessions

    def get(self, run_id: str) -> PrivateDesktopSession | None:
        with self._lock:
            return self._sessions.get(run_id)

    def launch(self, target_id: str, executable: str, arguments: list[str] | None = None,
               wall_timeout_seconds: int = 900) -> tuple[int, str]:
        path = Path(executable).resolve()
        if not path.is_file() or path.suffix.lower() != ".exe":
            raise ValueError("Registered executable no longer exists.")
        profile = Path(tempfile.mkdtemp(prefix=f"qaw-{target_id[:8]}-"))
        env = os.environ.copy()
        env.update({
            "APPDATA": str(profile / "Roaming"),
            "LOCALAPPDATA": str(profile / "Local"),
            "TEMP": str(profile / "Temp"),
            "TMP": str(profile / "Temp"),
        })
        for name in ("APPDATA", "LOCALAPPDATA", "TEMP"):
            Path(env[name]).mkdir(parents=True, exist_ok=True)

        run_id = str(uuid.uuid4())
        session = PrivateDesktopSession(run_id, wall_timeout_seconds=wall_timeout_seconds)
        try:
            pid = session.launch(str(path), arguments=arguments or [], env=env, cwd=str(path.parent))
            with self._lock:
                self._sessions[run_id] = session
                self._profiles[run_id] = profile
            return pid, run_id
        except Exception:
            session.close()
            raise

    def stop(self, run_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(run_id, None)
            self._profiles.pop(run_id, None)
        # Profiles remain as evidence; only runner-owned processes are closed.
        return session.close() if session else False


__all__ = ["WindowsRunner"]
