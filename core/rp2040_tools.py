"""RP2040-specific wrappers over the generic MicroPython workflow."""

from __future__ import annotations

from typing import Any, Callable

from core.micropython_tools import (
    micropython_auto_sync_cycle,
    micropython_compile,
    micropython_connect,
    micropython_flash,
    micropython_hardware_status,
    micropython_list_files_tool,
)
from core.platforms import canonical_target_name, detect_target_platform
from core.state import get_context


def _ensure_rp2040_context() -> str:
    ctx = get_context()
    if detect_target_platform(ctx.chip) != "rp2040":
        ctx.chip = canonical_target_name("RP2040")
    return ctx.chip


def rp2040_connect(
    chip: str | None = None,
    *,
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    return micropython_connect(chip or "RP2040", port=port, baud=baud, console=console)


def rp2040_hardware_status(*, console: Any = None) -> dict[str, Any]:
    _ensure_rp2040_context()
    return micropython_hardware_status(console=console)


def rp2040_compile(
    code: str,
    *,
    chip: str | None = None,
    console: Any = None,
    record_success_memory: Callable[..., None] | None = None,
    log_error: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    return micropython_compile(
        code,
        chip=chip or "RP2040",
        console=console,
        record_success_memory=record_success_memory,
        log_error=log_error,
    )


def rp2040_flash(
    *,
    file_path: str | None = None,
    code: str | None = None,
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
    capture_timeout: float = 4.0,
) -> dict[str, Any]:
    _ensure_rp2040_context()
    return micropython_flash(
        file_path=file_path,
        code=code,
        port=port,
        baud=baud,
        console=console,
        capture_timeout=capture_timeout,
    )


def rp2040_auto_sync_cycle(
    code: str,
    *,
    request: str = "",
    baud: int = 115200,
    console: Any = None,
    max_attempts: int = 8,
    record_success_memory: Callable[..., None] | None = None,
    log_error: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    _ensure_rp2040_context()
    return micropython_auto_sync_cycle(
        code,
        request=request,
        baud=baud,
        console=console,
        max_attempts=max_attempts,
        record_success_memory=record_success_memory,
        log_error=log_error,
    )


def rp2040_list_files_tool(
    *,
    path: str = ".",
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    _ensure_rp2040_context()
    return micropython_list_files_tool(path=path, port=port, baud=baud, console=console)


__all__ = [
    "rp2040_auto_sync_cycle",
    "rp2040_compile",
    "rp2040_connect",
    "rp2040_flash",
    "rp2040_hardware_status",
    "rp2040_list_files_tool",
]
