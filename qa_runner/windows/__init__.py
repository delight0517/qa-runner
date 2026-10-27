"""Windows-only execution adapters for the shared QA runner."""

from .private_desktop import (
    DesktopWindow,
    PrivateDesktopError,
    PrivateDesktopSession,
    TargetAlreadyRunning,
)
from .manager import WindowsRunner

__all__ = ["DesktopWindow", "PrivateDesktopError", "PrivateDesktopSession", "TargetAlreadyRunning",
           "WindowsRunner"]
