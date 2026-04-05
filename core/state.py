"""Shared runtime state for Gary hardware workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import config as _cfg


@dataclass(slots=True)
class HardwareContext:
    """Mutable runtime state shared across compiler, hardware, and UI helpers."""

    chip: str = getattr(_cfg, "DEFAULT_CHIP", "")
    compiler: Any | None = None
    bridge: Any | None = None
    serial: Any | None = None
    hw_connected: bool = False
    serial_connected: bool = False
    last_bin_path: str | None = None
    last_code: str | None = None
    compiler_mtime: float = 0.0
    debug_attempt: int = 0
    cli_language: str = getattr(_cfg, "CLI_LANGUAGE", "zh")
    telegram_cli_autostart_done: bool = False


_CONTEXT = HardwareContext()


def get_context() -> HardwareContext:
    """Return the process-wide runtime context singleton."""

    return _CONTEXT
