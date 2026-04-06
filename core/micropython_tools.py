"""Generic serial-MicroPython workflow helpers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

from core.platforms import (
    canonical_target_name,
    canonical_target_name_from_micropython_info,
    device_autorun_flag_path_for_target,
    device_bootstrap_path_for_target,
    device_legacy_main_path_for_target,
    device_main_path_for_target,
    device_root_for_target,
    detect_target_platform,
    is_generic_micropython_name,
)
from core.project_store import latest_workspace_main_path, save_project, sync_latest_workspace
from core.state import get_context
from hardware.micropython import (
    list_remote_files,
    probe_micropython_board,
    scan_micropython_boards,
    soft_reset_board,
    sync_text_files,
)
from hardware.serial_mon import SerialMonitor, connect_serial, detect_serial_ports, disconnect_serial


def _micropython_platform_label(chip: str | None) -> str:
    platform = detect_target_platform(chip)
    if platform == "rp2040":
        return "RP2040"
    if platform == "esp":
        return "ESP"
    if platform == "canmv":
        return "CanMV K230"
    return "MicroPython"


def _micropython_port_help(chip: str | None) -> str:
    label = _micropython_platform_label(chip)
    if detect_target_platform(chip) == "canmv":
        return (
            f"未检测到 {label} 的 REPL 串口，请确认已刷入 CanMV-K230 MicroPython 固件、TF 卡启动正常，"
            "并检查 USB 数据线；部分板卡需要同时连接两根 USB 线"
        )
    return f"未检测到 {label} 常见 USB 串口，请确认开发板已刷入 MicroPython 且 USB 数据线可传输"


def _normalize_raw_repl_error(result: dict[str, Any] | None, chip: str | None) -> dict[str, Any] | None:
    """Rewrite raw-REPL transport failures into a clearer diagnostic payload."""

    data = dict(result or {})
    if not data.get("raw_repl_failure") and data.get("reason") != "raw_repl_unresponsive":
        return None
    label = _micropython_platform_label(chip)
    banner = str(data.get("banner") or "").strip()
    suggestions = list(data.get("recovery_suggestions") or [])
    causes = list(data.get("suspected_causes") or [])
    message = (
        f"{label} 当前无法进入 raw REPL。设备很可能还在执行上一次部署的用户脚本，"
        "例如无延时的 while True 死循环、摄像头/显示循环，或阻塞式初始化。"
    )
    if banner:
        message += f" 原始响应: {banner[:160]}"
    data.update(
        {
            "raw_repl_failure": True,
            "reason": "raw_repl_unresponsive",
            "suspected_user_code_block": True,
            "message": message,
            "recovery_suggestions": suggestions,
            "suspected_causes": causes,
        }
    )
    return data


_LOOP_DELAY_CALLS = {
    "sleep",
    "sleep_ms",
    "sleep_us",
    "sleep_ns",
    "idle",
    "machine.idle",
    "time.sleep",
    "time.sleep_ms",
    "time.sleep_us",
    "utime.sleep",
    "utime.sleep_ms",
    "utime.sleep_us",
    "asyncio.sleep",
    "asyncio.sleep_ms",
}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _contains_loop_delay(node: ast.AST) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        return False
    if isinstance(node, ast.Call) and _call_name(node.func) in _LOOP_DELAY_CALLS:
        return True
    return any(_contains_loop_delay(child) for child in ast.iter_child_nodes(node))


def _while_lines_missing_delay(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.While) and not _contains_loop_delay(node):
            lines.append(int(getattr(node, "lineno", 0) or 0))
    return [line for line in lines if line > 0]


def _build_gary_bootstrap(chip: str | None) -> str:
    run_path = device_main_path_for_target(chip)
    flag_path = device_autorun_flag_path_for_target(chip)
    return (
        "print('Gary:BOOT')\n"
        "try:\n"
        " import time\n"
        "except ImportError:\n"
        " import utime as time\n"
        "try:\n"
        " import os\n"
        "except ImportError:\n"
        " import uos as os\n"
        "try:\n"
        " import sys\n"
        "except ImportError:\n"
        " sys = None\n"
        f"FLAG_PATH = {flag_path!r}\n"
        f"RUN_PATH = {run_path!r}\n"
        "should_run = False\n"
        "try:\n"
        " os.stat(FLAG_PATH)\n"
        " should_run = True\n"
        "except OSError:\n"
        " should_run = False\n"
        "if should_run:\n"
        " try:\n"
        "  os.remove(FLAG_PATH)\n"
        " except OSError:\n"
        "  pass\n"
        " try:\n"
        "  time.sleep_ms(120)\n"
        " except AttributeError:\n"
        "  time.sleep(0.12)\n"
        " print('Gary:RUN_START')\n"
        " scope = {'__name__': '__main__', '__file__': RUN_PATH}\n"
        " try:\n"
        "  exec(compile(open(RUN_PATH, 'r').read(), RUN_PATH, 'exec'), scope, scope)\n"
        " except Exception:\n"
        "  print('Gary:RUN_ERROR')\n"
        "  raise\n"
        " else:\n"
        "  print('Gary:RUN_DONE')\n"
    )


def _managed_device_files(chip: str | None, code: str) -> tuple[list[tuple[str, str]], list[str]]:
    device_main_path = device_main_path_for_target(chip)
    bootstrap_path = device_bootstrap_path_for_target(chip)
    flag_path = device_autorun_flag_path_for_target(chip)
    legacy_main_path = device_legacy_main_path_for_target(chip)
    remove_paths = [legacy_main_path] if legacy_main_path != device_main_path else []
    files = [
        (bootstrap_path, _build_gary_bootstrap(chip)),
        (device_main_path, code),
        (flag_path, "run\n"),
    ]
    return files, remove_paths


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
        "message": (
            f"已发现 {len(boards)} 个 MicroPython 设备，但暂时无法识别具体板型；"
            "请改用 /connect PICO_W、/connect ESP32 或 /connect CANMV_K230"
        ),
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
        "device_root": device_root_for_target(chip),
        "device_bootstrap_path": device_bootstrap_path_for_target(chip),
        "device_main_path": device_main_path_for_target(chip),
        "device_autorun_flag_path": device_autorun_flag_path_for_target(chip),
        "managed_bootstrap": True,
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
        tree = ast.parse(code)
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

    missing_delay_lines = _while_lines_missing_delay(tree)
    if missing_delay_lines:
        line = missing_delay_lines[0]
        return {
            "success": False,
            "message": (
                "MicroPython 安全检查失败：每个 while 循环都必须包含短延时，"
                f"例如 `time.sleep_ms(5)`；请先修复 line {line}"
            ),
            "line": line,
            "lines": missing_delay_lines,
            "platform": platform,
            "error_type": "while_loop_missing_delay",
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
    """Deploy a managed MicroPython program bundle and soft-reset it once."""

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
        if source_path.exists():
            code = source_path.read_text(encoding="utf-8")
        elif ctx.last_code:
            code = ctx.last_code
        else:
            return {"success": False, "platform": platform, "message": f"源文件不存在: {source_path}"}

    # 烧录前强制同步到 latest_workspace，保证后续运行报错时 AI 有稳定的编辑目标。
    ctx.last_code = code
    sync_result = sync_latest_workspace(code, chip=ctx.chip)
    if not sync_result.get("success"):
        return {
            "success": False,
            "platform": platform,
            "port": resolved_port,
            "message": f"烧录前保存 latest_workspace 失败: {sync_result.get('message', '')}",
        }

    disconnect_serial(ctx)
    ctx.serial_connected = False
    device_main_path = device_main_path_for_target(ctx.chip)
    device_bootstrap_path = device_bootstrap_path_for_target(ctx.chip)
    device_flag_path = device_autorun_flag_path_for_target(ctx.chip)
    files, remove_paths = _managed_device_files(ctx.chip, code)

    result = sync_text_files(
        port=resolved_port,
        files=files,
        remove_paths=remove_paths,
        baud=baud,
        console=console,
        soft_reset=True,
        capture_timeout=capture_timeout,
    )
    if not result.get("success"):
        raw_repl_error = _normalize_raw_repl_error(result, ctx.chip)
        if raw_repl_error is not None:
            raw_repl_error.update(
                {
                    "success": False,
                    "platform": platform,
                    "port": resolved_port,
                    "source_path": sync_result.get("path"),
                    "source_file": sync_result.get("source_file"),
                    "device_bootstrap_path": device_bootstrap_path,
                    "device_main_path": device_main_path,
                    "device_autorun_flag_path": device_flag_path,
                }
            )
            return raw_repl_error
        return {
            "success": False,
            "platform": platform,
            "port": resolved_port,
            "message": result.get("message", "同步 MicroPython 托管脚本失败"),
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
        "source_path": sync_result.get("path"),
        "source_file": sync_result.get("source_file"),
        "device_bootstrap_path": device_bootstrap_path,
        "device_main_path": device_main_path,
        "device_autorun_flag_path": device_flag_path,
        "managed_bootstrap": True,
        "message": f"已部署 {device_main_path}（由 {device_bootstrap_path} 托管）到 {resolved_port}",
    }


def micropython_soft_reset(
    *,
    port: str | None = None,
    baud: int = 115200,
    console: Any = None,
    capture_timeout: float = 4.0,
) -> dict[str, Any]:
    """Issue a MicroPython soft reset on the connected board."""

    ctx = get_context()
    ctx.chip = canonical_target_name(ctx.chip or "ESP32")
    platform = detect_target_platform(ctx.chip)
    resolved_port = _serial_port_for_ctx(port)
    if not resolved_port:
        return {"success": False, "platform": platform, "message": _micropython_port_help(ctx.chip)}

    disconnect_serial(ctx)
    ctx.serial_connected = False
    result = soft_reset_board(
        port=resolved_port,
        baud=baud,
        console=console,
        capture_timeout=capture_timeout,
    )
    if not result.get("success"):
        raw_repl_error = _normalize_raw_repl_error(result, ctx.chip)
        if raw_repl_error is not None:
            raw_repl_error.update({"platform": platform, "port": resolved_port})
            return raw_repl_error
        return {
            "success": False,
            "platform": platform,
            "port": resolved_port,
            "message": result.get("message", "MicroPython soft reset 失败"),
        }

    reconnect = _reconnect_monitor(resolved_port, baud, console=console)
    boot_output = result.get("boot_output", "")
    ctx.hw_connected = True
    return {
        "success": True,
        "platform": platform,
        "port": resolved_port,
        "serial_connected": reconnect.get("success", False),
        "boot_output": boot_output,
        "traceback": "Traceback" in boot_output,
        "message": "已发送 MicroPython soft reset",
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
        error_message = compile_result.get("message", "MicroPython 检查失败")
        return {
            "success": False,
            "attempt": attempt,
            "remaining": max(0, remaining),
            "give_up": False,
            "steps": steps,
            "compile_errors": error_message,
            "error": error_message
            if compile_result.get("error_type") == "while_loop_missing_delay"
            else "MicroPython 语法错误，请按行号修复",
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
        raw_repl_error = _normalize_raw_repl_error(flash_result, ctx.chip)
        if raw_repl_error is not None:
            return {
                "success": False,
                "attempt": attempt,
                "remaining": max(0, remaining),
                "give_up": False,
                "steps": steps,
                "error": raw_repl_error.get("message", f"部署到 {label} 失败"),
                "platform": platform,
                "raw_repl_failure": True,
                "suspected_user_code_block": True,
                "recovery_suggestions": raw_repl_error.get("recovery_suggestions", []),
                "suspected_causes": raw_repl_error.get("suspected_causes", []),
                "source_path": flash_result.get("source_path"),
                "source_file": flash_result.get("source_file"),
                "device_main_path": flash_result.get("device_main_path"),
            }
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
    target_path = device_root_for_target(ctx.chip) if path == "." and platform == "canmv" else path
    result = list_remote_files(port=resolved_port, path=target_path, baud=baud, console=console)
    raw_repl_error = _normalize_raw_repl_error(result, ctx.chip)
    if raw_repl_error is not None:
        raw_repl_error.update({"platform": platform, "port": resolved_port, "path": target_path})
        return raw_repl_error
    return result


__all__ = [
    "micropython_auto_sync_cycle",
    "micropython_compile",
    "micropython_connect",
    "micropython_flash",
    "micropython_hardware_status",
    "micropython_list_files_tool",
    "micropython_soft_reset",
]
