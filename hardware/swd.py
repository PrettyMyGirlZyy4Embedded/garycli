"""SWD / pyOCD hardware helpers."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional


def _console_print(console: Any, message: str) -> None:
    """Print via the injected console when available."""

    if console is None:
        return
    try:
        console.print(message)
    except Exception:
        pass


class PyOCDBridge:
    """Thin wrapper around pyOCD probe/session operations."""

    _pyocd_target_cache: Optional[tuple[float, set[str]]] = None
    _CACHE_TTL = 60.0

    def __init__(
        self,
        *,
        console: Any = None,
        reg_map_factory: Optional[Callable[[str], dict[str, int]]] = None,
        register_read_delay: float = 0.3,
        default_chip: str = "",
    ) -> None:
        """Initialize the SWD bridge state."""

        self.console = console
        self.reg_map_factory = reg_map_factory or (lambda _family: {})
        self.register_read_delay = register_read_delay
        self.default_chip = default_chip
        self._session: Any = None
        self._target: Any = None
        self.connected = False
        self.chip_info: dict[str, Any] = {}
        self._family = "f1"
        self._reg_map: dict[str, int] = self.reg_map_factory("f1")

    def configure(
        self,
        *,
        console: Any = None,
        reg_map_factory: Optional[Callable[[str], dict[str, int]]] = None,
        register_read_delay: Optional[float] = None,
        default_chip: Optional[str] = None,
    ) -> None:
        """Refresh runtime dependencies without recreating the instance."""

        if console is not None:
            self.console = console
        if reg_map_factory is not None:
            self.reg_map_factory = reg_map_factory
            self._reg_map = self.reg_map_factory(self._family)
        if register_read_delay is not None:
            self.register_read_delay = register_read_delay
        if default_chip is not None:
            self.default_chip = default_chip

    def _chip_to_pyocd_target(self, chip: str) -> str:
        """Convert `STM32F103C8T6` to a pyOCD target-like name."""

        name = chip.lower().strip()
        return re.sub(r"[a-z]\d$", "", name)

    @classmethod
    def _get_all_pyocd_targets(cls) -> set[str]:
        """Return known pyOCD targets, reusing a short-lived cache."""

        now = time.time()
        if cls._pyocd_target_cache is not None:
            ts, cached = cls._pyocd_target_cache
            if now - ts < cls._CACHE_TTL:
                return cached

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pyocd", "list", "--targets"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            known = set()
            for line in result.stdout.splitlines():
                parts = line.split()
                if parts and parts[0].startswith("stm32"):
                    known.add(parts[0].lower())
            cls._pyocd_target_cache = (now, known)
            return known
        except Exception:
            return set()

    def _resolve_best_target(self, target_name: str) -> str:
        """Resolve the best pyOCD target name available in the environment."""

        known = self._get_all_pyocd_targets()
        if not known:
            try:
                from pyocd.target import TARGET  # type: ignore

                known = {key.lower() for key in TARGET}
            except ImportError:
                return target_name

        if target_name in known:
            return target_name

        candidates = [key for key in known if key.startswith(target_name)]
        if candidates:
            best = max(candidates, key=lambda key: len(os.path.commonprefix([target_name, key])))
            _console_print(self.console, f"[yellow]  目标映射: {target_name} → {best}[/]")
            return best

        for trim in range(1, 4):
            prefix = target_name[:-trim]
            if len(prefix) < 8:
                break
            candidates = [key for key in known if key.startswith(prefix)]
            if candidates:
                best = max(
                    candidates,
                    key=lambda key: len(os.path.commonprefix([target_name, key])),
                )
                _console_print(self.console, f"[yellow]  目标近似匹配: {target_name} → {best}[/]")
                return best

        return target_name

    def _auto_install_pack(self, target_name: str) -> bool:
        """Try to install a missing CMSIS pack for the requested target."""

        _console_print(
            self.console,
            f"[yellow]  未找到目标 {target_name}，正在自动安装支持包...[/]",
        )
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pyocd", "pack", "install", target_name],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except Exception as exc:
            _console_print(self.console, f"[red]  支持包安装出错: {exc}[/]")
            return False

        if result.returncode == 0:
            _console_print(self.console, "[green]  支持包安装成功[/]")
            return True

        _console_print(
            self.console,
            f"[red]  支持包安装失败: {result.stderr.strip()}[/]",
        )
        return False

    def _detect_family(self, chip: str) -> str:
        """Infer the register map family from the chip name."""

        chip_up = (chip or "").upper()
        if "F0" in chip_up:
            return "f0"
        if "F3" in chip_up:
            return "f3"
        if "F4" in chip_up or "F7" in chip_up or "H7" in chip_up:
            return "f4"
        return "f1"

    def set_family(self, family: str) -> None:
        """Switch the active register map family."""

        self._family = family
        self._reg_map = self.reg_map_factory(family)

    def start(self, chip: str | None = None) -> bool:
        """Connect the first available SWD probe."""

        self.stop()
        try:
            from pyocd.core.helpers import ConnectHelper  # type: ignore
        except ImportError:
            _console_print(self.console, "[red]pyocd 未安装，请运行: pip install pyocd[/]")
            return False

        requested_chip = chip or self.default_chip
        explicit_chip = bool(requested_chip and requested_chip.upper() != "AUTO")
        family = self._detect_family(requested_chip) if explicit_chip else "f1"
        self.set_family(family)

        if explicit_chip:
            raw_target = self._chip_to_pyocd_target(requested_chip)
            target_name = self._resolve_best_target(raw_target)
        else:
            target_name = None

        probe_hint = f"目标: {target_name}" if target_name else "自动检测目标"
        _console_print(self.console, f"[dim]  连接探针（{probe_hint}）...[/]")

        def _do_connect(target_override: str | None) -> Any:
            return ConnectHelper.session_with_chosen_probe(
                target_override=target_override,
                auto_unlock=True,
                connect_mode="halt",
                blocking=False,
                return_first=True,
                options={"frequency": 1000000},
            )

        try:
            self._session = _do_connect(target_name)
        except Exception as exc:
            err_str = str(exc)
            if explicit_chip and ("not recognized" in err_str or "Target type" in err_str):
                raw_target = self._chip_to_pyocd_target(requested_chip)
                if self._auto_install_pack(raw_target):
                    target_name = self._resolve_best_target(raw_target)
                    _console_print(self.console, f"[dim]  重新连接（{target_name}）...[/]")
                    try:
                        self._session = _do_connect(target_name)
                    except Exception as retry_exc:
                        _console_print(self.console, f"[red]  连接失败: {retry_exc}[/]")
                        self._session = None
                        self._target = None
                        return False
                else:
                    _console_print(self.console, f"[red]  连接失败: {exc}[/]")
                    self._session = None
                    self._target = None
                    return False
            else:
                _console_print(self.console, f"[red]  连接失败: {exc}[/]")
                self._session = None
                self._target = None
                return False

        try:
            if self._session is None:
                _console_print(self.console, "[red]  未找到调试探针，请检查 USB 连接[/]")
                return False
            self._session.open()
            self._target = self._session.board.target
            detected = getattr(self._target, "target_type", None) or (target_name or "unknown")
            resolved_chip = requested_chip.upper() if explicit_chip else detected.upper()
            resolved_family = self._detect_family(resolved_chip)
            self.set_family(resolved_family)
            self.chip_info = {
                "device": resolved_chip,
                "pyocd_target": detected,
                "family": resolved_family,
                "probe": self._session.board.description,
            }
            self.connected = True
            _console_print(
                self.console,
                f"[green]  已连接: {resolved_chip} | 探针: {self._session.board.description}[/]",
            )
            try:
                self._target.halt()
                time.sleep(0.1)
                self._target.read32(0xE000ED00)
                time.sleep(0.05)
            except Exception:
                pass
            return True
        except Exception as exc:
            _console_print(self.console, f"[red]  连接后处理失败: {exc}[/]")
            self._session = None
            self._target = None
            return False

    def stop(self) -> None:
        """Close the active probe session."""

        if self._session:
            try:
                self._target.resume()
            except Exception:
                pass
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
            self._target = None
        self.connected = False

    def flash(self, bin_path: str) -> dict[str, Any]:
        """Program a binary image through pyOCD."""

        if not self.connected:
            return {"ok": False, "msg": "探针未连接，请先 connect"}
        binary_path = Path(bin_path)
        if not binary_path.exists():
            return {"ok": False, "msg": f"文件不存在: {bin_path}"}

        try:
            from pyocd.flash.file_programmer import FileProgrammer  # type: ignore
        except ImportError:
            return {"ok": False, "msg": "pyocd 未安装"}

        size = binary_path.stat().st_size
        t0 = time.time()
        _console_print(self.console, f"[dim]  烧录 {size} 字节...[/]")
        try:
            self._target.reset_and_halt()
            time.sleep(0.1)
        except Exception:
            try:
                self._target.halt()
                time.sleep(0.05)
            except Exception:
                pass
        try:
            programmer = FileProgrammer(self._session)
            programmer.program(str(binary_path), base_address=0x08000000)
        except Exception as exc:
            return {"ok": False, "msg": f"烧录异常: {exc}"}

        dt = time.time() - t0
        spd = size / dt / 1024 if dt > 0 else 0
        try:
            self._target.reset_and_halt()
            time.sleep(0.1)
            self._target.resume()
        except Exception as exc:
            _console_print(self.console, f"[yellow]  复位警告（固件已烧录）: {exc}[/]")
        return {"ok": True, "msg": f"烧录成功 {size}B / {dt:.1f}s ({spd:.1f} KB/s)"}

    def read_registers(self, names: Optional[list[str]] = None) -> Optional[dict[str, str]]:
        """Read a selected set of registers from the target."""

        if not self.connected:
            return None
        try:
            self._target.halt()
            time.sleep(self.register_read_delay)
            targets = names if names else list(self._reg_map.keys())
            regs: dict[str, str] = {}
            for name in targets:
                addr = self._reg_map.get(name)
                if addr is None:
                    continue
                try:
                    val = self._target.read32(addr)
                    regs[name] = f"0x{val:08X}"
                except Exception:
                    pass
            try:
                pc = self._target.read_core_register("pc")
                regs["PC"] = f"0x{pc:08X}"
            except Exception:
                pass
            self._target.resume()
            return regs
        except Exception as exc:
            _console_print(self.console, f"[red]  寄存器读取异常: {exc}[/]")
            return None

    def read_all_for_debug(self) -> Optional[dict[str, str]]:
        """Read the default debug register set."""

        return self.read_registers()

    def analyze_fault(self, regs: dict[str, str]) -> str:
        """Return a short HardFault summary based on `SCB_CFSR`."""

        cfsr_str = regs.get("SCB_CFSR", "0x00000000")
        try:
            cfsr = int(cfsr_str, 16)
        except ValueError:
            return "CFSR 格式错误"
        if cfsr == 0:
            return "无故障"
        checks = [
            (0x01, "IACCVIOL: 指令访问违规"),
            (0x02, "DACCVIOL: 数据访问违规"),
            (0x100, "IBUSERR: 指令总线错误"),
            (0x200, "PRECISERR: 精确总线错误（外设未使能时钟）"),
            (0x400, "IMPRECISERR: 非精确总线错误"),
            (0x10000, "UNDEFINSTR: 未定义指令"),
            (0x20000, "INVSTATE: 无效 EPSR 状态"),
            (0x1000000, "UNALIGNED: 非对齐访问"),
            (0x2000000, "DIVBYZERO: 除零"),
        ]
        faults = [desc for mask, desc in checks if cfsr & mask]
        return "; ".join(faults) if faults else f"未知故障 CFSR=0x{cfsr:08X}"

    def list_probes(self) -> list[dict[str, Any]]:
        """Enumerate available debug probes."""

        try:
            from pyocd.probe.aggregator import DebugProbeAggregator  # type: ignore
        except ImportError:
            return []
        try:
            probes = DebugProbeAggregator.get_all_connected_probes()
            return [{"uid": probe.unique_id, "description": probe.product_name} for probe in probes]
        except Exception:
            return []


def _prepare_bridge(
    ctx: Any,
    *,
    console: Any = None,
    reg_map_factory: Optional[Callable[[str], dict[str, int]]] = None,
    register_read_delay: float = 0.3,
    default_chip: str = "",
) -> PyOCDBridge:
    """Return a configured SWD bridge instance, reusing the context object when possible."""

    bridge = getattr(ctx, "bridge", None)
    if isinstance(bridge, PyOCDBridge):
        bridge.configure(
            console=console,
            reg_map_factory=reg_map_factory,
            register_read_delay=register_read_delay,
            default_chip=default_chip,
        )
        return bridge
    return PyOCDBridge(
        console=console,
        reg_map_factory=reg_map_factory,
        register_read_delay=register_read_delay,
        default_chip=default_chip,
    )


def list_probes(*, console: Any = None) -> list[dict[str, Any]]:
    """Return all currently visible debug probes."""

    return PyOCDBridge(console=console).list_probes()


def connect_swd(
    ctx: Any,
    chip: str | None = None,
    *,
    default_chip: str = "",
    register_read_delay: float = 0.3,
    reg_map_factory: Optional[Callable[[str], dict[str, int]]] = None,
    console: Any = None,
) -> dict[str, Any]:
    """Connect an SWD probe and return the bridge instance plus connection metadata."""

    bridge = _prepare_bridge(
        ctx,
        console=console,
        reg_map_factory=reg_map_factory,
        register_read_delay=register_read_delay,
        default_chip=default_chip,
    )
    target_chip = chip or getattr(ctx, "chip", "") or default_chip
    success = bridge.start(target_chip)
    return {
        "success": success,
        "bridge": bridge,
        "chip_info": dict(bridge.chip_info),
        "message": f"硬件已连接: {bridge.chip_info.get('device', target_chip)}"
        if success
        else "连接失败，请检查探针 USB 连接和驱动",
    }


def disconnect_swd(ctx: Any) -> dict[str, Any]:
    """Disconnect the active SWD probe."""

    bridge = getattr(ctx, "bridge", None)
    if isinstance(bridge, PyOCDBridge):
        bridge.stop()
    return {"success": True, "message": "已断开"}


def flash_via_swd(ctx: Any, bin_path: str) -> dict[str, Any]:
    """Flash a binary through the SWD bridge stored in the context."""

    bridge = getattr(ctx, "bridge", None)
    if not isinstance(bridge, PyOCDBridge) or not bridge.connected:
        return {"success": False, "message": "硬件未连接，请先调用 stm32_connect"}
    result = bridge.flash(bin_path)
    return {"success": result["ok"], "message": result["msg"]}


def read_registers(
    ctx: Any,
    names: Optional[list[str]] = None,
    *,
    debug_all: bool = False,
) -> Optional[dict[str, str]]:
    """Read registers from the active SWD bridge in the context."""

    bridge = getattr(ctx, "bridge", None)
    if not isinstance(bridge, PyOCDBridge) or not bridge.connected:
        return None
    return bridge.read_all_for_debug() if debug_all else bridge.read_registers(names)


__all__ = [
    "PyOCDBridge",
    "connect_swd",
    "disconnect_swd",
    "flash_via_swd",
    "list_probes",
    "read_registers",
]
