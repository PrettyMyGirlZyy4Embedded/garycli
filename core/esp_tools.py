"""ESP32 / ESP8266 wrappers over the generic MicroPython workflow."""

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


def _ensure_esp_context() -> str:
    ctx = get_context()
    if detect_target_platform(ctx.chip) != "esp":
        ctx.chip = canonical_target_name("ESP32")
    return ctx.chip


def esp_connect(
    chip: str | None = None,
    *,
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    return micropython_connect(chip or "ESP32", port=port, baud=baud, console=console)


def esp_hardware_status(*, console: Any = None) -> dict[str, Any]:
    _ensure_esp_context()
    return micropython_hardware_status(console=console)


def esp_compile(
    code: str,
    *,
    chip: str | None = None,
    console: Any = None,
    record_success_memory: Callable[..., None] | None = None,
    log_error: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    return micropython_compile(
        code,
        chip=chip or "ESP32",
        console=console,
        record_success_memory=record_success_memory,
        log_error=log_error,
    )


def esp_flash(
    *,
    file_path: str | None = None,
    code: str | None = None,
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
    capture_timeout: float = 4.0,
) -> dict[str, Any]:
    _ensure_esp_context()
    return micropython_flash(
        file_path=file_path,
        code=code,
        port=port,
        baud=baud,
        console=console,
        capture_timeout=capture_timeout,
    )


def esp_auto_sync_cycle(
    code: str,
    *,
    request: str = "",
    baud: int = 115200,
    console: Any = None,
    max_attempts: int = 8,
    record_success_memory: Callable[..., None] | None = None,
    log_error: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    _ensure_esp_context()
    return micropython_auto_sync_cycle(
        code,
        request=request,
        baud=baud,
        console=console,
        max_attempts=max_attempts,
        record_success_memory=record_success_memory,
        log_error=log_error,
    )


def esp_list_files_tool(
    *,
    path: str = ".",
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    _ensure_esp_context()
    return micropython_list_files_tool(path=path, port=port, baud=baud, console=console)


__all__ = [
    "esp_auto_sync_cycle",
    "esp_compile",
    "esp_connect",
    "esp_flash",
    "esp_hardware_status",
    "esp_list_files_tool",
]
