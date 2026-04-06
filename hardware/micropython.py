"""MicroPython serial transport helpers for serial-connected boards."""

from __future__ import annotations

import json
import time
from typing import Any

_PROBE_MARKER = "GARY_BOARD_INFO:"


def _console_print(console: Any, message: str) -> None:
    if console is None:
        return
    try:
        console.print(message)
    except Exception:
        pass


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="ignore")


def _read_all(ser: Any, duration: float) -> bytes:
    deadline = time.time() + duration
    chunks: list[bytes] = []
    while time.time() < deadline:
        chunk = ser.read(512)
        if chunk:
            chunks.append(chunk)
            continue
        time.sleep(0.05)
    return b"".join(chunks)


def _read_until_any(ser: Any, tokens: list[bytes], timeout: float = 3.0) -> bytes:
    deadline = time.time() + timeout
    data = b""
    while time.time() < deadline:
        chunk = ser.read(256)
        if chunk:
            data += chunk
            if any(token in data for token in tokens):
                break
            continue
        time.sleep(0.05)
    return data


def _raw_repl_failure_result(banner: bytes) -> dict[str, Any]:
    """Build a structured failure payload for raw REPL handshake issues."""

    decoded = _decode(banner)[:160]
    summary = (
        "进入 raw REPL 失败：设备没有正确响应 Ctrl+A。"
        "当前板子可能仍在执行上一次部署的用户脚本，例如无延时的 while True 死循环、摄像头/显示循环，"
        "或阻塞式初始化。"
    )
    recovery_suggestions = [
        "先按板载 RST 键或重新插拔 USB，让设备重新上电后再重试",
        "若用户脚本中有 while True / 摄像头采集 / 屏幕刷新循环，请加入 time.sleep_ms(5) 一类的短延时",
        "把 print('Gary:BOOT') 放到文件顶部更靠前的位置，避免初始化阶段完全无输出",
        "若串口多次失败后僵死，先物理复位，再执行 list_files / flash / auto_sync_cycle",
    ]
    suspected_causes = [
        "当前用户脚本持续占用解释器，REPL 无法接管",
        "程序阻塞在导入、外设初始化、摄像头或显示初始化阶段",
        "串口缓冲区或 USB-Serial 状态已半挂起，需要复位清理",
    ]
    payload: dict[str, Any] = {
        "success": False,
        "message": summary if not decoded else f"{summary} 原始响应: {decoded}",
        "reason": "raw_repl_unresponsive",
        "raw_repl_failure": True,
        "banner": decoded,
        "recovery_suggestions": recovery_suggestions,
        "suspected_causes": suspected_causes,
    }
    return payload


def _with_port(data: dict[str, Any], port: str) -> dict[str, Any]:
    payload = dict(data)
    payload["port"] = port
    return payload


def _open_serial(port: str, baud: int):
    try:
        import serial as pyserial  # type: ignore
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError("pyserial 未安装: pip install pyserial") from exc
    handle = pyserial.Serial(port, baudrate=baud, timeout=0.25, write_timeout=1.0)
    handle.reset_input_buffer()
    handle.reset_output_buffer()
    return handle


def _enter_raw_repl(ser: Any, *, console: Any = None) -> dict[str, Any]:
    banner = b""
    for attempt in range(2):
        ser.write(b"\r\x03\x03")
        ser.flush()
        time.sleep(0.15)
        try:
            ser.write(b"\x02")
            ser.flush()
            time.sleep(0.05)
        except Exception:
            pass
        ser.reset_input_buffer()
        ser.write(b"\r\x01")
        ser.flush()
        banner = _read_until_any(ser, [b"raw REPL; CTRL-B to exit", b"\n>"], timeout=2.0)
        ok = b"raw REPL" in banner or banner.rstrip().endswith(b">")
        if ok:
            return {"success": True, "banner": _decode(banner)}
        if attempt == 0:
            time.sleep(0.2)
    failure = _raw_repl_failure_result(banner)
    _console_print(console, f"[yellow]  MicroPython raw REPL 响应异常: {failure.get('banner', '')[:120]}[/]")
    return failure


def _exit_raw_repl(ser: Any) -> None:
    ser.write(b"\x02")
    ser.flush()
    time.sleep(0.1)


def _exec_raw(ser: Any, source: str, *, timeout: float = 8.0) -> dict[str, Any]:
    payload = source.encode("utf-8")
    ser.write(payload)
    ser.write(b"\x04")
    ser.flush()

    data = b""
    deadline = time.time() + timeout
    eot_count = 0
    while time.time() < deadline:
        chunk = ser.read(512)
        if chunk:
            data += chunk
            eot_count += chunk.count(b"\x04")
            if eot_count >= 2:
                break
            continue
        time.sleep(0.05)

    if data.startswith(b"OK"):
        data = data[2:]
    stdout, _, tail = data.partition(b"\x04")
    stderr, _, _ = tail.partition(b"\x04")
    success = not stderr.strip()
    return {
        "success": success,
        "stdout": _decode(stdout),
        "stderr": _decode(stderr),
        "raw": _decode(data),
    }


def _build_write_script(device_path: str, content: str) -> str:
    data = content.encode("utf-8")
    tmp_path = f"{device_path}.gary_tmp"
    lines = [
        "try:",
        " import os",
        "except ImportError:",
        " import uos as os",
        f"f = open({tmp_path!r}, 'wb')",
    ]
    for index in range(0, len(data), 64):
        chunk = data[index : index + 64]
        lines.append(f"f.write({chunk!r})")
    lines.extend(
        [
            "f.close()",
            "try:",
            f" os.remove({device_path!r})",
            "except OSError:",
            " pass",
            f"os.rename({tmp_path!r}, {device_path!r})",
            f"print('GARY_SYNC_OK:{device_path}')",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_remove_script(paths: list[str]) -> str:
    lines = [
        "try:",
        " import os",
        "except ImportError:",
        " import uos as os",
    ]
    for item in paths:
        lines.extend(
            [
                "try:",
                f" os.remove({item!r})",
                f" print('GARY_REMOVE_OK:{item}')",
                "except OSError:",
                " pass",
            ]
        )
    return "\n".join(lines) + "\n"


def _build_probe_script() -> str:
    return "\n".join(
        [
            "try:",
            " import sys",
            "except ImportError:",
            " sys = None",
            "try:",
            " import os",
            "except ImportError:",
            " import uos as os",
            "try:",
            " import ujson as json",
            "except ImportError:",
            " import json",
            "u = os.uname()",
            "info = {",
            " 'sysname': getattr(u, 'sysname', ''),",
            " 'machine': getattr(u, 'machine', ''),",
            " 'release': getattr(u, 'release', ''),",
            " 'version': getattr(u, 'version', ''),",
            " 'platform': getattr(sys, 'platform', '') if sys else '',",
            " 'implementation': getattr(getattr(sys, 'implementation', None), 'name', '') if sys else '',",
            "}",
            f"print({_PROBE_MARKER!r} + json.dumps(info))",
            "",
        ]
    )


def _parse_probe_output(stdout: str) -> dict[str, Any] | None:
    for line in (stdout or "").splitlines():
        text = line.strip()
        if not text.startswith(_PROBE_MARKER):
            continue
        payload = text[len(_PROBE_MARKER) :]
        try:
            parsed = json.loads(payload)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def upload_text_file(
    *,
    port: str,
    device_path: str,
    content: str,
    baud: int = 115200,
    console: Any = None,
    soft_reset: bool = False,
    capture_timeout: float = 4.0,
) -> dict[str, Any]:
    """Upload one text file to a MicroPython device over raw REPL."""

    try:
        ser = _open_serial(port, baud)
    except Exception as exc:
        return {"success": False, "message": f"打开串口失败: {exc}", "port": port}

    try:
        raw = _enter_raw_repl(ser, console=console)
        if not raw.get("success"):
            return _with_port(raw, port)

        result = _exec_raw(ser, _build_write_script(device_path, content), timeout=12.0)
        if not result.get("success"):
            return {
                "success": False,
                "message": "写入设备文件失败",
                "port": port,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            }

        boot_output = ""
        if soft_reset:
            _exit_raw_repl(ser)
            ser.reset_input_buffer()
            ser.write(b"\x04")
            ser.flush()
            boot_output = _decode(_read_all(ser, capture_timeout))
        return {
            "success": True,
            "message": f"已同步到设备: {device_path}",
            "port": port,
            "device_path": device_path,
            "stdout": result.get("stdout", ""),
            "boot_output": boot_output,
        }
    except Exception as exc:
        return {"success": False, "message": str(exc), "port": port}
    finally:
        try:
            ser.close()
        except Exception:
            pass


def sync_text_files(
    *,
    port: str,
    files: list[tuple[str, str]],
    remove_paths: list[str] | None = None,
    baud: int = 115200,
    console: Any = None,
    soft_reset: bool = False,
    capture_timeout: float = 4.0,
) -> dict[str, Any]:
    """Write multiple text files in one raw-REPL session and optionally soft-reset."""

    try:
        ser = _open_serial(port, baud)
    except Exception as exc:
        return {"success": False, "message": f"打开串口失败: {exc}", "port": port}

    try:
        raw = _enter_raw_repl(ser, console=console)
        if not raw.get("success"):
            return _with_port(raw, port)

        written: list[str] = []
        for device_path, content in files:
            result = _exec_raw(ser, _build_write_script(device_path, content), timeout=12.0)
            if not result.get("success"):
                return {
                    "success": False,
                    "message": f"写入设备文件失败: {device_path}",
                    "port": port,
                    "device_path": device_path,
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                }
            written.append(device_path)

        removed: list[str] = []
        if remove_paths:
            cleanup = _exec_raw(ser, _build_remove_script(remove_paths), timeout=6.0)
            if not cleanup.get("success"):
                return {
                    "success": False,
                    "message": "清理旧启动脚本失败",
                    "port": port,
                    "stdout": cleanup.get("stdout", ""),
                    "stderr": cleanup.get("stderr", ""),
                }
            removed = list(remove_paths)

        boot_output = ""
        if soft_reset:
            _exit_raw_repl(ser)
            ser.reset_input_buffer()
            ser.write(b"\x04")
            ser.flush()
            boot_output = _decode(_read_all(ser, capture_timeout))

        return {
            "success": True,
            "message": f"已同步 {len(written)} 个设备文件",
            "port": port,
            "written_paths": written,
            "removed_paths": removed,
            "boot_output": boot_output,
        }
    except Exception as exc:
        return {"success": False, "message": str(exc), "port": port}
    finally:
        try:
            ser.close()
        except Exception:
            pass


def soft_reset_board(
    *,
    port: str,
    baud: int = 115200,
    console: Any = None,
    capture_timeout: float = 4.0,
) -> dict[str, Any]:
    """Soft-reset a MicroPython board through the serial REPL."""

    try:
        ser = _open_serial(port, baud)
    except Exception as exc:
        return {"success": False, "message": f"打开串口失败: {exc}", "port": port}

    try:
        raw = _enter_raw_repl(ser, console=console)
        if not raw.get("success"):
            return _with_port(raw, port)
        _exit_raw_repl(ser)
        ser.reset_input_buffer()
        ser.write(b"\x04")
        ser.flush()
        boot_output = _decode(_read_all(ser, capture_timeout))
        return {
            "success": True,
            "message": "已发送 MicroPython soft reset",
            "port": port,
            "boot_output": boot_output,
        }
    except Exception as exc:
        return {"success": False, "message": str(exc), "port": port}
    finally:
        try:
            ser.close()
        except Exception:
            pass


def list_remote_files(
    *,
    port: str,
    path: str = ".",
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    """List one directory on a MicroPython device."""

    script = "\n".join(
        [
            "try:",
            " import os",
            "except ImportError:",
            " import uos as os",
            f"for name in os.listdir({path!r}):",
            " print(name)",
            "",
        ]
    )

    try:
        ser = _open_serial(port, baud)
    except Exception as exc:
        return {"success": False, "message": f"打开串口失败: {exc}", "port": port}

    try:
        raw = _enter_raw_repl(ser, console=console)
        if not raw.get("success"):
            return _with_port(raw, port)
        result = _exec_raw(ser, script, timeout=6.0)
        if not result.get("success"):
            return {
                "success": False,
                "message": "读取设备目录失败",
                "port": port,
                "stderr": result.get("stderr", ""),
            }
        files = [line.strip() for line in result.get("stdout", "").splitlines() if line.strip()]
        return {"success": True, "port": port, "path": path, "files": files}
    except Exception as exc:
        return {"success": False, "message": str(exc), "port": port}
    finally:
        try:
            ser.close()
        except Exception:
            pass


def probe_micropython_board(
    *,
    port: str,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    """Probe one serial port and extract MicroPython runtime board information."""

    try:
        ser = _open_serial(port, baud)
    except Exception as exc:
        return {"success": False, "message": f"打开串口失败: {exc}", "port": port}

    try:
        raw = _enter_raw_repl(ser, console=console)
        if not raw.get("success"):
            return _with_port(raw, port)
        result = _exec_raw(ser, _build_probe_script(), timeout=6.0)
        if not result.get("success"):
            return {
                "success": False,
                "message": "读取板子信息失败",
                "port": port,
                "stderr": result.get("stderr", ""),
            }
        info = _parse_probe_output(result.get("stdout", ""))
        if not info:
            return {
                "success": False,
                "message": "未识别到有效的 MicroPython 板子信息",
                "port": port,
                "stdout": result.get("stdout", ""),
            }
        return {
            "success": True,
            "port": port,
            "baud": baud,
            "info": info,
            "message": f"已读取板子信息: {info.get('machine') or info.get('platform') or port}",
        }
    except Exception as exc:
        return {"success": False, "message": str(exc), "port": port}
    finally:
        try:
            _exit_raw_repl(ser)
        except Exception:
            pass
        try:
            ser.close()
        except Exception:
            pass


def scan_micropython_boards(
    *,
    ports: list[str] | None = None,
    baud: int = 115200,
    console: Any = None,
) -> dict[str, Any]:
    """Scan candidate serial ports and return all successfully probed MicroPython boards."""

    if ports is None:
        from hardware.serial_mon import detect_serial_ports

        ports = detect_serial_ports(verbose=False)

    boards = []
    for port in ports or []:
        result = probe_micropython_board(port=port, baud=baud, console=console)
        if result.get("success"):
            boards.append(result)
    return {
        "success": bool(boards),
        "ports": ports or [],
        "boards": boards,
        "message": f"检测到 {len(boards)} 个可识别的 MicroPython 设备" if boards else "未检测到可识别的 MicroPython 设备",
    }


__all__ = [
    "list_remote_files",
    "probe_micropython_board",
    "scan_micropython_boards",
    "soft_reset_board",
    "sync_text_files",
    "upload_text_file",
]
