"""Reusable, local-first QA execution primitives shared by QA consumers."""

from .windows.private_desktop import (
    DesktopWindow,
    PrivateDesktopError,
    PrivateDesktopSession,
    TargetAlreadyRunning,
)
from .windows.manager import WindowsRunner

__version__ = "0.1.0"

__all__ = [
    "DesktopWindow",
    "PrivateDesktopError",
    "PrivateDesktopSession",
    "TargetAlreadyRunning",
    "WindowsRunner",
    "__version__",
]
