"""Generic serial-MicroPython workflow helpers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

from core.platforms import (
    canonical_target_name,
    canonical_target_name_from_micropython_info,
    detect_target_platform,
    is_generic_micropython_name,
)
from core.project_store import latest_workspace_main_path, save_project, sync_latest_workspace
from core.state import get_context
from hardware.micropython import list_remote_files, probe_micropython_board, scan_micropython_boards, upload_text_file
from hardware.serial_mon import SerialMonitor, connect_serial, detect_serial_ports, disconnect_serial


def _micropython_platform_label(chip: str | None) -> str:
    platform = detect_target_platform(chip)
    if platform == "rp2040":
        return "RP2040"
    if platform == "esp":
        return "ESP"
    return "MicroPython"


def _micropython_port_help(chip: str | None) -> str:
    label = _micropython_platform_label(chip)
    return f"未检测到 {label} 常见 USB 串口，请确认开发板已刷入 MicroPython 且 USB 数据线可传输"


def _looks_like_usb_device_port(port: str | None) -> bool:
    text = str(port or "").lower()
    return any(
        token in text
        for token in ("ttyacm", "ttyusb", "usbmodem", "usbserial", "/cu.usb", "com")
    )


def _serial_port_for_ctx(port: str | None = None) -> str | None:
    if port:
        return port
    ctx = get_context()
    monitor = getattr(ctx, "serial", None)
    active = getattr(monitor, "port", None)
    if active:
        return active
    candidates = detect_serial_ports(verbose=False)
    preferred = [candidate for candidate in candidates if _looks_like_usb_device_port(candidate)]
    return preferred[0] if preferred else None


def _reconnect_monitor(port: str | None, baud: int, *, console: Any = None) -> dict[str, Any]:
    ctx = get_context()
    result = connect_serial(ctx, port, baud, console=console)
    monitor = result.get("serial")
    if isinstance(monitor, SerialMonitor):
        ctx.serial = monitor
    ctx.serial_connected = bool(result.get("success"))
    if ctx.serial_connected:
        ctx.hw_connected = True
    return result


def _autodetect_micropython_board(
    *,
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    ctx = get_context()
    if getattr(getattr(ctx, "serial", None), "port", None):
        disconnect_serial(ctx)
        ctx.serial_connected = False

    if port:
        probe = probe_micropython_board(port=port, baud=baud, console=console)
        if not probe.get("success"):
            return probe
        info = probe.get("info") or {}
        chip = canonical_target_name_from_micropython_info(info)
        if not chip:
            return {
                "success": False,
                "port": port,
                "info": info,
                "message": f"已检测到 MicroPython 设备，但暂时无法识别板型: {info.get('machine') or info.get('platform') or port}",
            }
        return {
            "success": True,
            "port": port,
            "chip": chip,
            "platform": detect_target_platform(chip),
            "info": info,
            "scan_count": 1,
        }

    scan = scan_micropython_boards(baud=baud, console=console)
    boards = scan.get("boards") or []
    if not boards:
        candidates = detect_serial_ports(verbose=False, console=console)
        return {
            "success": False,
            "candidate_ports": candidates[:5],
            "message": "未扫描到可自动识别的 MicroPython 设备，请确认开发板已刷入 MicroPython 固件并通过 USB 数据线连接",
        }

    for board in boards:
        info = board.get("info") or {}
        chip = canonical_target_name_from_micropython_info(info)
        if not chip:
            continue
        return {
            "success": True,
            "port": board.get("port"),
            "chip": chip,
            "platform": detect_target_platform(chip),
            "info": info,
            "scan_count": len(boards),
        }

    first = boards[0]
    info = first.get("info") or {}
    return {
        "success": False,
        "port": first.get("port"),
        "info": info,
        "candidate_ports": [board.get("port") for board in boards if board.get("port")],
        "message": f"已发现 {len(boards)} 个 MicroPython 设备，但暂时无法识别具体板型；请改用 /connect PICO_W 或 /connect ESP32",
    }


def micropython_connect(
    chip: str | None = None,
    *,
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    """Connect a serial MicroPython board over USB serial."""

    ctx = get_context()
    requested_chip = chip or ctx.chip or "ESP32"
    if is_generic_micropython_name(requested_chip):
        detected = _autodetect_micropython_board(port=port, baud=baud, console=console)
        if not detected.get("success"):
            return {
                "success": False,
                "chip": "MICROPYTHON",
                "platform": "unknown",
                "serial_connected": False,
                "candidate_ports": detected.get("candidate_ports", []),
                "message": detected.get("message", "自动识别 MicroPython 开发板失败"),
            }
        ctx.chip = str(detected.get("chip") or "ESP32")
        resolved_port = str(detected.get("port") or "")
        info = detected.get("info") or {}
        result = _reconnect_monitor(resolved_port, baud, console=console)
        if result.get("success"):
            return {
                "success": True,
                "chip": ctx.chip,
                "platform": detect_target_platform(ctx.chip),
                "serial_connected": True,
                "port": result.get("port"),
                "detected_info": info,
                "message": f"已自动识别并连接: {ctx.chip} @ {result.get('port')}",
            }
        ctx.hw_connected = False
        return {
            "success": False,
            "chip": ctx.chip,
            "platform": detect_target_platform(ctx.chip),
            "serial_connected": False,
            "port": resolved_port,
            "detected_info": info,
            "message": result.get("message", "串口连接失败"),
        }

    ctx.chip = canonical_target_name(requested_chip)
    platform = detect_target_platform(ctx.chip)
    resolved_port = _serial_port_for_ctx(port)
    if port is None and resolved_port is None:
        candidates = detect_serial_ports(verbose=False)
        return {
            "success": False,
            "chip": ctx.chip,
            "platform": platform,
            "serial_connected": False,
            "candidate_ports": candidates[:5],
            "message": _micropython_port_help(ctx.chip),
        }

    result = _reconnect_monitor(resolved_port, baud, console=console)
    if result.get("success"):
        return {
            "success": True,
            "chip": ctx.chip,
            "platform": platform,
            "serial_connected": True,
            "port": result.get("port"),
            "message": f"{ctx.chip} 已连接: {ctx.chip} @ {result.get('port')}",
        }
    ctx.hw_connected = False
    return {
        "success": False,
        "chip": ctx.chip,
        "platform": platform,
        "serial_connected": False,
        "message": result.get("message", "串口连接失败"),
    }


def micropython_hardware_status(*, console: Any = None) -> dict[str, Any]:
    """Return a status snapshot for the current MicroPython workflow."""

    ctx = get_context()
    chip = canonical_target_name(ctx.chip or "ESP32")
    platform = detect_target_platform(chip)
    ports = detect_serial_ports(verbose=False, console=console)
    preferred_ports = [port for port in ports if _looks_like_usb_device_port(port)]
    serial_ok = True
    try:
        import serial  # type: ignore  # noqa: F401
    except ImportError:
        serial_ok = False
    return {
        "platform": platform,
        "runtime": "MicroPython",
        "chip": chip,
        "hw_connected": ctx.hw_connected,
        "serial_connected": ctx.serial_connected,
        "serial_ok": serial_ok,
        "candidate_ports": preferred_ports[:5] or ports[:5],
        "all_detected_ports": ports[:8],
        "source_file": "main.py",
        "deploy_transport": "raw_repl_over_usb_serial",
    }


def micropython_compile(
    code: str,
    *,
    chip: str | None = None,
    console: Any = None,
    record_success_memory: Callable[..., None] | None = None,
    log_error: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Validate MicroPython source and cache it as `main.py`."""

    del console
    ctx = get_context()
    ctx.chip = canonical_target_name(chip or ctx.chip or "ESP32")
    platform = detect_target_platform(ctx.chip)
    try:
        ast.parse(code)
    except SyntaxError as exc:
        line = exc.lineno or 0
        snippet = exc.text.strip() if exc.text else ""
        return {
            "success": False,
            "message": f"MicroPython 语法错误: line {line}: {exc.msg}",
            "line": line,
            "offset": exc.offset,
            "snippet": snippet,
            "platform": platform,
        }

    ctx.last_code = code
    ctx.last_bin_path = None
    sync_result = sync_latest_workspace(code, chip=ctx.chip)
    source_path = sync_result.get("path", "workspace/projects/latest_workspace/main.py")
    message = f"MicroPython 语法检查通过，已缓存到 {source_path}"
    if "Gary:BOOT" not in code:
        message += "；建议在 main.py 顶部尽早 print('Gary:BOOT')"
    payload = {
        "success": True,
        "message": message,
        "source_path": sync_result.get("path"),
        "source_file": sync_result.get("source_file"),
        "bin_path": None,
        "bin_size": len(code.encode("utf-8")),
        "platform": platform,
    }
    if record_success_memory is not None:
        try:
            record_success_memory(
                "compile_success",
                code=code,
                result=payload,
                chip=ctx.chip,
                log_error=log_error,
            )
        except Exception:
            pass
    return payload


def micropython_flash(
    *,
    file_path: str | None = None,
    code: str | None = None,
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
    capture_timeout: float = 4.0,
) -> dict[str, Any]:
    """Deploy `main.py` to a serial MicroPython board and soft-reset it."""

    ctx = get_context()
    ctx.chip = canonical_target_name(ctx.chip or "ESP32")
    platform = detect_target_platform(ctx.chip)
    resolved_port = _serial_port_for_ctx(port)
    if not resolved_port:
        return {"success": False, "platform": platform, "message": _micropython_port_help(ctx.chip)}

    if code is None:
        source_path = (
            Path(file_path).expanduser().resolve()
            if file_path
            else latest_workspace_main_path(ctx.chip)
        )
        if not source_path.exists():
            return {"success": False, "platform": platform, "message": f"源文件不存在: {source_path}"}
        code = source_path.read_text(encoding="utf-8")

    disconnect_serial(ctx)
    ctx.serial_connected = False

    result = upload_text_file(
        port=resolved_port,
        device_path="main.py",
        content=code,
        baud=baud,
        console=console,
        soft_reset=True,
        capture_timeout=capture_timeout,
    )
    if not result.get("success"):
        return {
            "success": False,
            "platform": platform,
            "port": resolved_port,
            "message": result.get("message", "同步 main.py 失败"),
            "stderr": result.get("stderr", ""),
        }

    reconnect = _reconnect_monitor(resolved_port, baud, console=console)
    boot_output = result.get("boot_output", "")
    traceback_present = "Traceback (most recent call last)" in boot_output or "Traceback:" in boot_output
    ctx.hw_connected = True
    return {
        "success": True,
        "platform": platform,
        "port": resolved_port,
        "serial_connected": reconnect.get("success", False),
        "boot_output": boot_output,
        "traceback": traceback_present,
        "message": f"已部署 main.py 到 {resolved_port}",
    }


def micropython_auto_sync_cycle(
    code: str,
    *,
    request: str = "",
    baud: int = 115200,
    console: Any = None,
    max_attempts: int = 8,
    record_success_memory: Callable[..., None] | None = None,
    log_error: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Validate, deploy, and observe a serial MicroPython program."""

    ctx = get_context()
    ctx.chip = canonical_target_name(ctx.chip or "ESP32")
    platform = detect_target_platform(ctx.chip)
    label = _micropython_platform_label(ctx.chip)
    ctx.debug_attempt += 1
    attempt = ctx.debug_attempt
    remaining = max_attempts - attempt
    steps: list[dict[str, Any]] = []

    if attempt > max_attempts:
        return {
            "success": False,
            "give_up": True,
            "attempt": attempt,
            "message": f"已达到最大调试轮次 ({max_attempts})，请检查串口连接、供电和 {label} MicroPython 固件",
            "steps": [],
            "platform": platform,
        }

    compile_result = micropython_compile(
        code,
        chip=ctx.chip,
        console=console,
        record_success_memory=record_success_memory,
        log_error=log_error,
    )
    steps.append({"step": "compile", "success": compile_result.get("success", False), "msg": compile_result.get("message", "")})
    if not compile_result.get("success"):
        return {
            "success": False,
            "attempt": attempt,
            "remaining": max(0, remaining),
            "give_up": False,
            "steps": steps,
            "compile_errors": compile_result.get("message", ""),
            "error": "MicroPython 语法错误，请按行号修复",
            "platform": platform,
        }

    ports = detect_serial_ports(verbose=False)
    if not ports and not getattr(getattr(ctx, "serial", None), "port", None):
        if request:
            save_project(code, {"bin_path": None, "bin_size": len(code.encode("utf-8"))}, request, chip=ctx.chip, console=console)
        return {
            "success": True,
            "attempt": attempt,
            "steps": steps,
            "note": f"未检测到 {label} 串口，仅完成语法检查和项目缓存",
            "platform": platform,
        }

    flash_result = micropython_flash(code=code, baud=baud, console=console)
    steps.append({"step": "deploy", "success": flash_result.get("success", False), "msg": flash_result.get("message", "")})
    if not flash_result.get("success"):
        return {
            "success": False,
            "attempt": attempt,
            "remaining": max(0, remaining),
            "give_up": False,
            "steps": steps,
            "error": flash_result.get("message", f"部署到 {label} 失败"),
            "platform": platform,
        }

    boot_output = flash_result.get("boot_output", "")
    trace_lines = [line for line in boot_output.splitlines() if line.strip()]
    steps.append(
        {
            "step": "uart",
            "output": boot_output[:800],
            "boot_ok": "Gary:BOOT" in boot_output,
            "has_traceback": flash_result.get("traceback", False),
        }
    )
    if flash_result.get("traceback"):
        return {
            "success": False,
            "attempt": attempt,
            "remaining": max(0, remaining),
            "give_up": False,
            "steps": steps,
            "error": "MicroPython 运行时抛出了 Traceback，请根据串口输出修复",
            "uart_output": boot_output[:2000],
            "platform": platform,
        }

    verified = "Gary:BOOT" in boot_output or bool(trace_lines)
    if request:
        save_project(
            code,
            {"bin_path": None, "bin_size": len(code.encode("utf-8"))},
            request,
            chip=ctx.chip,
            console=console,
        )
    if record_success_memory is not None:
        try:
            record_success_memory(
                "runtime_success",
                code=code,
                result={"bin_size": len(code.encode("utf-8"))},
                request=request,
                steps=steps,
                chip=ctx.chip,
                log_error=log_error,
            )
        except Exception:
            pass
    return {
        "success": True,
        "attempt": attempt,
        "steps": steps,
        "platform": platform,
        "verified": verified,
        "uart_output": boot_output[:2000],
        "note": (
            "已看到启动/串口输出"
            if verified
            else f"已部署到 {ctx.chip}，但未捕获到串口输出；建议在 main.py 顶部尽早打印 Gary:BOOT"
        ),
    }


def micropython_list_files_tool(
    *,
    path: str = ".",
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    """List files on the connected MicroPython device."""

    ctx = get_context()
    ctx.chip = canonical_target_name(ctx.chip or "ESP32")
    platform = detect_target_platform(ctx.chip)
    resolved_port = _serial_port_for_ctx(port)
    if not resolved_port:
        return {"success": False, "platform": platform, "message": _micropython_port_help(ctx.chip)}
    return list_remote_files(port=resolved_port, path=path, baud=baud, console=console)


__all__ = [
    "micropython_auto_sync_cycle",
    "micropython_compile",
    "micropython_connect",
    "micropython_flash",
    "micropython_hardware_status",
    "micropython_list_files_tool",
]
