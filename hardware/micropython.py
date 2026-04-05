"""MicroPython serial transport helpers for RP2040-class boards."""

from __future__ import annotations

import time
from typing import Any


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
    ser.write(b"\r\x03\x03")
    ser.flush()
    time.sleep(0.15)
    ser.reset_input_buffer()
    ser.write(b"\r\x01")
    ser.flush()
    banner = _read_until_any(ser, [b"raw REPL; CTRL-B to exit", b"\n>"], timeout=2.0)
    ok = b"raw REPL" in banner or banner.rstrip().endswith(b">")
    if not ok:
        _console_print(console, f"[yellow]  RP2040 raw REPL 响应异常: {_decode(banner)[:120]}[/]")
        return {"success": False, "message": f"进入 raw REPL 失败: {_decode(banner)[:160]}"}
    return {"success": True, "banner": _decode(banner)}


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
            return {
                "success": False,
                "message": raw.get("message", "进入 raw REPL 失败"),
                "port": port,
            }

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
            return {
                "success": False,
                "message": raw.get("message", "进入 raw REPL 失败"),
                "port": port,
            }
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


__all__ = ["list_remote_files", "upload_text_file"]
