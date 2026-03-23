"""Serial monitor helpers for STM32 runtime IO."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional


def _console_print(console: Any, message: str) -> None:
    """Print via the injected console when available."""

    if console is None:
        return
    try:
        console.print(message)
    except Exception:
        pass


def detect_serial_ports(verbose: bool = False, *, console: Any = None) -> list[str]:
    """Scan available serial ports and prioritize likely STM32 targets."""

    import glob
    import platform
    import re

    plat = platform.system()
    found: list[str] = []
    usb_set: set[str] = set()

    def _add(port: str, *, usb: bool = False) -> None:
        if port in found:
            return
        if usb:
            idx = next((i for i, item in enumerate(found) if item not in usb_set), len(found))
            found.insert(idx, port)
            usb_set.add(port)
        else:
            found.append(port)

    try:
        import serial.tools.list_ports as list_ports  # type: ignore

        skip_kw = ("bluetooth", "virtual", "rfcomm", "modem")
        for info in list_ports.comports():
            port = info.device
            desc = (info.description or "").lower()
            hwid = (info.hwid or "n/a").lower()
            if any(key in desc for key in skip_kw):
                continue
            if hwid == "n/a" and re.search(r"ttyS\d+$", port):
                continue
            is_usb = "usb" in hwid or "ch34" in hwid or "cp21" in hwid or "ft23" in hwid
            _add(port, usb=is_usb)
    except Exception:
        pass

    if plat == "Windows":
        try:
            import winreg  # type: ignore

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
            index = 0
            while True:
                try:
                    _, port, _ = winreg.EnumValue(key, index)
                    _add(port)
                    index += 1
                except OSError:
                    break
        except Exception:
            pass
    elif plat == "Darwin":
        for pattern, is_usb in [
            ("/dev/tty.usbserial*", True),
            ("/dev/tty.usbmodem*", True),
            ("/dev/tty.SLAB*", True),
            ("/dev/tty.wchusbserial*", True),
            ("/dev/cu.usbserial*", True),
            ("/dev/cu.usbmodem*", True),
            ("/dev/tty.*", False),
        ]:
            for port in sorted(glob.glob(pattern)):
                if os.access(port, os.R_OK | os.W_OK):
                    _add(port, usb=is_usb)
    else:
        for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
            for port in sorted(glob.glob(pattern)):
                real = os.path.realpath(port)
                if os.access(real, os.R_OK | os.W_OK):
                    _add(real, usb=True)
        for port in sorted(glob.glob("/dev/serial/by-id/*")):
            real = os.path.realpath(port)
            if os.access(real, os.R_OK | os.W_OK) and real not in found:
                _add(real, usb=True)

        def _has_sysfs_device(port: str) -> bool:
            name = os.path.basename(port)
            return os.path.exists(f"/sys/class/tty/{name}/device")

        for port in sorted(glob.glob("/dev/ttyAMA*")):
            if os.access(port, os.R_OK | os.W_OK) and port not in found:
                _add(port, usb=False)
        for port in sorted(glob.glob("/dev/ttyS*")):
            if port in found or not os.access(port, os.R_OK | os.W_OK):
                continue
            if _has_sysfs_device(port):
                _add(port, usb=False)

    if verbose:
        _console_print(console, f"[dim]  检测到串口: {found if found else '无'}[/]")
    return found


def auto_open_serial(baud: int = 115200, *, console: Any = None) -> tuple[Optional[str], None]:
    """Return the first usable serial port without keeping it open."""

    try:
        import serial as pyserial  # type: ignore
    except ImportError:
        return None, None

    candidates = detect_serial_ports(console=console)
    for port in candidates:
        try:
            handle = pyserial.Serial(port, baud, timeout=0.3)
            handle.close()
            return port, None
        except Exception:
            continue
    return None, None


class SerialMonitor:
    """Background serial reader with a rolling text buffer."""

    def __init__(self, *, console: Any = None) -> None:
        """Initialize the serial monitor state."""

        self.console = console
        self._serial: Any = None
        self._port: Optional[str] = None
        self._buffer = ""
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    @property
    def port(self) -> Optional[str]:
        """Return the currently opened port path."""

        return self._port

    def open(self, port: str | None = None, baud: int = 115200) -> bool:
        """Open a serial port and start the reader thread."""

        try:
            import serial as pyserial  # type: ignore
        except ImportError:
            _console_print(self.console, "[yellow]  pyserial 未安装: pip install pyserial[/]")
            return False

        if port:
            candidates = [port] + [item for item in detect_serial_ports(console=self.console) if item != port]
        else:
            candidates = detect_serial_ports(console=self.console)
            if not candidates:
                _console_print(self.console, "[yellow]  串口: 未检测到任何可用串口[/]")
                return False

        for candidate in candidates:
            try:
                self._serial = pyserial.Serial(candidate, baud, timeout=0.5)
                self._serial.reset_input_buffer()
                self._running = True
                self._thread = threading.Thread(target=self._reader, daemon=True)
                self._thread.start()
                self._port = candidate
                _console_print(self.console, f"[green]  串口: {candidate} @ {baud}[/]")
                return True
            except Exception as exc:
                if candidate == candidates[-1]:
                    import platform

                    if platform.system() == "Linux" and not os.access(candidate, os.R_OK | os.W_OK):
                        try:
                            import grp  # type: ignore

                            grp_name = grp.getgrgid(os.stat(candidate).st_gid).gr_name
                        except Exception:
                            grp_name = "dialout"
                        _console_print(
                            self.console,
                            f"[yellow]  串口: {candidate} 权限不足 → sudo usermod -aG {grp_name} $USER && newgrp {grp_name}[/]",
                        )
                    else:
                        _console_print(self.console, f"[yellow]  串口打开失败: {exc}[/]")
                continue
        return False

    def _reader(self) -> None:
        """Continuously read from the serial port into the ring buffer."""

        try:
            import serial as pyserial  # type: ignore

            serial_exception: type[BaseException] = pyserial.SerialException
        except ImportError:
            serial_exception = OSError

        consecutive_errors = 0
        while self._running and self._serial:
            try:
                data = self._serial.read(1024)
                if data:
                    consecutive_errors = 0
                    with self._lock:
                        self._buffer += data.decode("utf-8", errors="ignore")
                        if len(self._buffer) > 8192:
                            self._buffer = self._buffer[-8192:]
            except serial_exception:
                _console_print(self.console, "[yellow]  ⚠ 串口断开[/]")
                self._running = False
                break
            except Exception:
                consecutive_errors += 1
                if consecutive_errors > 10:
                    _console_print(self.console, "[yellow]  ⚠ 串口持续异常，停止读取[/]")
                    self._running = False
                    break
                time.sleep(0.1)

    def read_and_clear(self) -> str:
        """Return buffered text and clear it."""

        with self._lock:
            output = self._buffer
            self._buffer = ""
            return output

    def clear(self) -> None:
        """Clear the serial text buffer."""

        with self._lock:
            self._buffer = ""

    def wait_for(self, keyword: str, timeout: float = 5.0, clear_first: bool = True) -> str:
        """Block until a keyword appears or the timeout expires."""

        if clear_first:
            self.clear()
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self._lock:
                if keyword in self._buffer:
                    break
            time.sleep(0.1)
        time.sleep(0.3)
        return self.read_and_clear()

    def close(self) -> None:
        """Stop the reader thread and close the serial port."""

        self._running = False
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None


def wait_serial_adaptive(
    monitor: SerialMonitor,
    keyword: str,
    min_wait: float = 0.5,
    max_wait: float = 8.0,
) -> str:
    """Adaptively wait for boot output or a marker string."""

    time.sleep(min_wait)
    t0 = time.time()
    accumulated = ""
    while time.time() - t0 < (max_wait - min_wait):
        chunk = monitor.read_and_clear()
        if chunk:
            accumulated += chunk
            if keyword in accumulated:
                break
        time.sleep(0.2)
    time.sleep(0.3)
    accumulated += monitor.read_and_clear()
    return accumulated


def _prepare_monitor(ctx: Any, *, console: Any = None) -> SerialMonitor:
    """Return a configured serial monitor, reusing the context object when possible."""

    monitor = getattr(ctx, "serial", None)
    if isinstance(monitor, SerialMonitor):
        if console is not None:
            monitor.console = console
        return monitor
    return SerialMonitor(console=console)


def connect_serial(
    ctx: Any,
    port: str | None = None,
    baud: int = 115200,
    *,
    console: Any = None,
) -> dict[str, Any]:
    """Open a serial port and return the monitor object plus metadata."""

    monitor = _prepare_monitor(ctx, console=console)
    monitor.close()
    success = monitor.open(port, baud)
    actual_port = monitor.port or port or "自动检测"
    if success:
        return {
            "success": True,
            "serial": monitor,
            "port": actual_port,
            "baud": baud,
            "message": f"串口已连接: {actual_port} @ {baud}",
        }
    candidates = detect_serial_ports(console=console)
    return {
        "success": False,
        "serial": monitor,
        "port": port,
        "baud": baud,
        "message": f"串口打开失败，可用端口: {candidates if candidates else '无'}",
    }


def disconnect_serial(ctx: Any) -> dict[str, Any]:
    """Close the active serial monitor."""

    monitor = getattr(ctx, "serial", None)
    if isinstance(monitor, SerialMonitor):
        monitor.close()
    return {"success": True, "message": "串口已断开"}


def read_serial_output(
    ctx: Any,
    timeout: float = 3.0,
    wait_for: str | None = None,
) -> dict[str, Any]:
    """Read buffered serial output from the current monitor."""

    monitor = getattr(ctx, "serial", None)
    if not isinstance(monitor, SerialMonitor):
        return {"success": False, "message": "串口未连接"}
    if wait_for:
        output = monitor.wait_for(wait_for, timeout=timeout)
    else:
        time.sleep(min(timeout, 2.0))
        output = monitor.read_and_clear()
    return {"success": True, "output": output, "has_output": bool(output.strip())}


__all__ = [
    "SerialMonitor",
    "auto_open_serial",
    "connect_serial",
    "detect_serial_ports",
    "disconnect_serial",
    "read_serial_output",
    "wait_serial_adaptive",
]
