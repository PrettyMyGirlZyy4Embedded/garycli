"""Gary core runtime, agent loop, and CLI orchestration."""

import argparse
import sys, os, json, re, time, subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Callable
from gary_skills import _get_manager

# 以项目根目录作为运行锚点，避免模块迁移后相对路径失效。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Flash 项目内部模块
import ai.client as _ai_client_module
import config as _cfg
import compiler as _compiler_module
from ai.client import (
    _ai_is_configured,
    _write_cli_language_config,
    estimate_request_tokens,
    get_ai_client,
    reload_ai_config,
    stream_chat,
)
from ai.tools import TOOL_SCHEMAS, bind_tool_implementations, dispatch_tool_call
from core.cli_config import configure_ai_cli as _configure_ai_cli_impl
from core.docx_tools import (
    append_docx_content,
    inspect_docx_structure,
    insert_docx_content_after_heading,
    read_docx,
    replace_docx_text,
)
from core.font_tools import stm32_generate_font
from core.generic_tools import (
    append_file_content,
    ask_human,
    browser_extract_links,
    browser_open,
    browser_open_result,
    browser_search,
    check_python_code,
    create_or_overwrite_file,
    edit_file_lines,
    execute_batch_commands,
    execute_command,
    fetch_url,
    get_current_time,
    git_commit,
    git_diff,
    git_status,
    grep_search,
    insert_content_by_regex,
    list_directory,
    read_file,
    run_python_code,
    search_files,
    str_replace_edit,
    web_search,
)
from core.memory import (
    _append_member_memory,
    _record_success_memory,
    gary_delete_member_memory,
    gary_save_member_memory,
)
from core.platforms import (
    canonical_target_name,
    detect_target_platform,
    is_generic_micropython_name,
    is_micropython_target,
    target_runtime_label,
)
from core.esp_tools import (
    esp_auto_sync_cycle as _esp_auto_sync_cycle_impl,
    esp_compile as _esp_compile_impl,
    esp_connect as _esp_connect_impl,
    esp_flash as _esp_flash_impl,
    esp_hardware_status as _esp_hardware_status_impl,
    esp_list_files_tool as _esp_list_files_impl,
)
from core.canmv_tools import (
    canmv_auto_sync_cycle as _canmv_auto_sync_cycle_impl,
    canmv_compile as _canmv_compile_impl,
    canmv_connect as _canmv_connect_impl,
    canmv_flash as _canmv_flash_impl,
    canmv_hardware_status as _canmv_hardware_status_impl,
    canmv_list_files_tool as _canmv_list_files_impl,
)
from core.project_store import (
    latest_workspace_main_path,
    list_projects as _list_projects_impl,
    read_project as _read_project_impl,
    save_code as _save_code_impl,
    save_project as _save_project_impl,
    sync_latest_workspace,
)
from core.rp2040_tools import (
    rp2040_auto_sync_cycle as _rp2040_auto_sync_cycle_impl,
    rp2040_compile as _rp2040_compile_impl,
    rp2040_connect as _rp2040_connect_impl,
    rp2040_flash as _rp2040_flash_impl,
    rp2040_hardware_status as _rp2040_hardware_status_impl,
    rp2040_list_files_tool as _rp2040_list_files_impl,
)
from core.state import get_context
from hardware.serial_mon import (
    SerialMonitor,
    connect_serial,
    detect_serial_ports,
    disconnect_serial,
    read_serial_output,
    wait_serial_adaptive,
)
from hardware.swd import (
    PyOCDBridge,
    connect_swd,
    disconnect_swd,
    flash_via_swd,
    list_probes as list_swd_probes,
    read_registers,
)
from hardware.uart_isp import flash_via_uart
from integrations.telegram import (
    configure_telegram_integration,
    handle_telegram_command,
    start_telegram_bot,
    stop_local_telegram_bridge,
    stop_telegram_bot,
    telegram_is_configured,
    telegram_log,
)
from prompts.debug import get_debug_prompt
from prompts.member import get_member_prompt_section_state
from prompts.system import (
    WEB_RESEARCH_HINT_HEADER,
    build_system_prompt,
    build_web_research_hint,
    should_force_web_research,
)
from tui.commands import GaryCompleter, handle_slash_command
from tui.ui import console as CONSOLE, print_banner, run_doctor, run_interactive, run_oneshot

Compiler = _compiler_module.Compiler

AI_API_KEY = _ai_client_module.AI_API_KEY
AI_BASE_URL = _ai_client_module.AI_BASE_URL
AI_MODEL = _ai_client_module.AI_MODEL
AI_TEMPERATURE = _ai_client_module.AI_TEMPERATURE

WORKSPACE = _cfg.WORKSPACE
BUILD_DIR = _cfg.BUILD_DIR
PROJECTS_DIR = _cfg.PROJECTS_DIR
DEFAULT_CHIP = _ai_client_module.DEFAULT_CHIP
DEFAULT_CLOCK = _ai_client_module.DEFAULT_CLOCK
CLI_LANGUAGE = _ai_client_module.CLI_LANGUAGE
SERIAL_PORT = _ai_client_module.SERIAL_PORT
SERIAL_BAUD = _ai_client_module.SERIAL_BAUD
POST_FLASH_DELAY = _ai_client_module.POST_FLASH_DELAY
REGISTER_READ_DELAY = _ai_client_module.REGISTER_READ_DELAY


def _parse_cli_language(value: Any, default: Optional[str] = None) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in {"en", "eng", "english", "英文"}:
        return "en"
    if raw in {"zh", "cn", "zh-cn", "zh_cn", "chinese", "中文"}:
        return "zh"
    return None


def _normalize_cli_language(value: Any) -> str:
    return _parse_cli_language(value, default="zh") or "zh"


CLI_LANGUAGE = _normalize_cli_language(CLI_LANGUAGE)
get_context().cli_language = CLI_LANGUAGE


def _is_cli_english() -> bool:
    return get_context().cli_language == "en"


def _cli_text(zh: str, en: str) -> str:
    return en if _is_cli_english() else zh


def _sync_ai_runtime_settings(settings: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """同步 ai.client 重载后的运行时配置到当前模块。"""

    global AI_API_KEY
    global AI_BASE_URL
    global AI_MODEL
    global AI_TEMPERATURE
    global DEFAULT_CHIP
    global DEFAULT_CLOCK
    global CLI_LANGUAGE
    global SERIAL_PORT
    global SERIAL_BAUD
    global POST_FLASH_DELAY
    global REGISTER_READ_DELAY

    data = settings or reload_ai_config()
    AI_API_KEY = str(data.get("AI_API_KEY", AI_API_KEY))
    AI_BASE_URL = str(data.get("AI_BASE_URL", AI_BASE_URL))
    AI_MODEL = str(data.get("AI_MODEL", AI_MODEL))
    AI_TEMPERATURE = data.get("AI_TEMPERATURE", AI_TEMPERATURE)
    DEFAULT_CHIP = str(data.get("DEFAULT_CHIP", DEFAULT_CHIP))
    DEFAULT_CLOCK = str(data.get("DEFAULT_CLOCK", DEFAULT_CLOCK))
    CLI_LANGUAGE = _normalize_cli_language(data.get("CLI_LANGUAGE", CLI_LANGUAGE))
    SERIAL_PORT = str(data.get("SERIAL_PORT", SERIAL_PORT))
    SERIAL_BAUD = data.get("SERIAL_BAUD", SERIAL_BAUD)
    POST_FLASH_DELAY = data.get("POST_FLASH_DELAY", POST_FLASH_DELAY)
    REGISTER_READ_DELAY = data.get("REGISTER_READ_DELAY", REGISTER_READ_DELAY)
    get_context().cli_language = CLI_LANGUAGE
    return data


# ─────────────────────────────────────────────────────────────
# Gary member.md 经验库（自动记忆 + 系统提示注入）
# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
# Telegram 机器人配置 / 守护进程 / 长轮询
# ─────────────────────────────────────────────────────────────
GARY_HOME = Path.home() / ".gary"


def _ensure_gary_home():
    GARY_HOME.mkdir(parents=True, exist_ok=True)


def _shutdown_cli_runtime(stop_telegram: bool = True) -> dict:
    """退出 CLI 时统一清理资源。"""
    results = {
        "hardware": stm32_disconnect(),
        "bridge_stopped": False,
        "telegram": {"success": True, "message": "Telegram 保持运行"},
    }
    try:
        stop_local_telegram_bridge()
        results["bridge_stopped"] = True
    except Exception as e:
        results["bridge_stopped"] = False
        results["bridge_error"] = str(e)
    if stop_telegram:
        try:
            results["telegram"] = stop_telegram_bot()
        except Exception as e:
            results["telegram"] = {"success": False, "message": f"停止 Telegram 机器人失败: {e}"}
    return results


def _ensure_cli_telegram_daemon() -> Optional[dict]:
    """在 CLI 启动时按配置自动拉起 Telegram 后台机器人。"""

    ctx = get_context()
    if ctx.telegram_cli_autostart_done:
        return None
    ctx.telegram_cli_autostart_done = True

    configured = telegram_is_configured()
    ai_ready = _ai_is_configured()
    if not configured and not ai_ready:
        return None
    if configured and not ai_ready:
        return {
            "success": False,
            "message": _cli_text(
                "已检测到 Telegram 配置，但 AI 接口未配置，未自动启动",
                "Telegram is configured, but AI is not configured, so it was not started automatically",
            ),
        }
    if not configured:
        return None

    result = start_telegram_bot()
    return {
        "success": bool(result.get("success")),
        "message": str(result.get("message", "")).strip(),
    }


# ─────────────────────────────────────────────────────────────
# UI 常量
# ─────────────────────────────────────────────────────────────
THEME = "cyan"
MAX_CONTEXT_TOKENS = 128000
MAX_TOOL_RESULT_LEN = 4000
TRUNCATED_TOOL_RESULT_NOTICE = "[结果已截断，完整内容请查看工具输出日志]"

# ─────────────────────────────────────────────────────────────
# 寄存器地址表（按系列）
# ─────────────────────────────────────────────────────────────
_REG_F1 = {
    "RCC_CR": 0x40021000,
    "RCC_CFGR": 0x40021004,
    "RCC_APB1ENR": 0x4002101C,
    "RCC_APB2ENR": 0x40021018,
    "GPIOA_CRL": 0x40010800,
    "GPIOA_CRH": 0x40010804,
    "GPIOA_IDR": 0x40010808,
    "GPIOA_ODR": 0x4001080C,
    "GPIOB_CRL": 0x40010C00,
    "GPIOB_CRH": 0x40010C04,
    "GPIOB_IDR": 0x40010C08,
    "GPIOB_ODR": 0x40010C0C,
    "GPIOC_CRL": 0x40011000,
    "GPIOC_CRH": 0x40011004,
    "TIM1_CR1": 0x40012C00,
    "TIM1_CCER": 0x40012C20,
    "TIM2_CR1": 0x40000000,
    "TIM2_CCER": 0x40000020,
    "TIM3_CR1": 0x40000400,
    "TIM3_CCER": 0x40000420,
    "ADC1_SR": 0x40012400,
    "ADC1_CR2": 0x40012408,
    "I2C1_CR1": 0x40005400,
    "I2C1_SR1": 0x40005414,
    "I2C2_CR1": 0x40005800,
    "I2C2_SR1": 0x40005814,
    "USART1_SR": 0x40013800,
    "USART1_BRR": 0x40013808,
}
_REG_F4 = {
    "RCC_CR": 0x40023800,
    "RCC_CFGR": 0x40023808,
    "RCC_AHB1ENR": 0x40023830,
    "RCC_APB1ENR": 0x40023840,
    "RCC_APB2ENR": 0x40023844,
    "GPIOA_MODER": 0x40020000,
    "GPIOA_IDR": 0x40020010,
    "GPIOA_ODR": 0x40020014,
    "GPIOB_MODER": 0x40020400,
    "GPIOB_IDR": 0x40020410,
    "GPIOB_ODR": 0x40020414,
    "GPIOC_MODER": 0x40020800,
    "GPIOC_IDR": 0x40020810,
    "GPIOC_ODR": 0x40020814,
    "TIM2_CR1": 0x40000000,
    "TIM2_CCER": 0x40000020,
    "TIM3_CR1": 0x40000400,
    "TIM3_CCER": 0x40000420,
    "I2C1_CR1": 0x40005400,
    "I2C1_SR1": 0x40005414,
    "USART1_SR": 0x40011000,
    "USART1_BRR": 0x40011008,
}
_REG_F0F3 = {
    "RCC_CR": 0x40021000,
    "RCC_CFGR": 0x40021004,
    "RCC_AHBENR": 0x40021014,
    "RCC_APB2ENR": 0x40021018,
    "RCC_APB1ENR": 0x4002101C,
    "GPIOA_MODER": 0x48000000,
    "GPIOA_IDR": 0x48000010,
    "GPIOA_ODR": 0x48000014,
    "GPIOB_MODER": 0x48000400,
    "GPIOB_IDR": 0x48000410,
    "GPIOB_ODR": 0x48000414,
    "I2C1_CR1": 0x40005400,
    "USART1_BRR": 0x40013808,
    "USART1_CR1": 0x4001380C,
}
_REG_COMMON = {
    "SCB_CFSR": 0xE000ED28,
    "SCB_HFSR": 0xE000ED2C,
    "SCB_BFAR": 0xE000ED38,
    "NVIC_ISER0": 0xE000E100,
}


def _reg_map(family: str) -> dict:
    base = {"f1": _REG_F1, "f4": _REG_F4, "f0": _REG_F0F3, "f3": _REG_F0F3}
    regs = dict(base.get(family.lower(), _REG_F1))
    regs.update(_REG_COMMON)
    return regs


# ─────────────────────────────────────────────────────────────
# PyOCDBridge / SerialMonitor 已迁移到 hardware/
# ─────────────────────────────────────────────────────────────
MAX_DEBUG_ATTEMPTS = 8  # 提高上限，一个任务最多 8 轮（含修改迭代）


def _get_compiler() -> Compiler:
    """返回 Compiler 单例；若 compiler/ 包文件已更新则自动热重载。"""
    ctx = get_context()
    import importlib

    try:
        mtime = _compiler_module.get_package_mtime()
    except Exception:
        mtime = 0.0
    if mtime > ctx.compiler_mtime:
        globals()["_compiler_module"] = importlib.reload(_compiler_module)
        if hasattr(_compiler_module, "reload_package"):
            _compiler_module.reload_package()
        globals()["Compiler"] = _compiler_module.Compiler
        ctx.compiler = None  # 旧实例作废，下方重新创建
        ctx.compiler_mtime = mtime
    if ctx.compiler is None:
        ctx.compiler = _compiler_module.Compiler()
        ctx.compiler.check(ctx.chip)  # 探测 GCC/HAL，设置 has_gcc/has_hal
    return ctx.compiler


def _get_bridge() -> PyOCDBridge:
    """Return the SWD bridge singleton stored in the runtime context."""

    ctx = get_context()
    bridge = ctx.bridge
    if not isinstance(bridge, PyOCDBridge):
        ctx.bridge = PyOCDBridge(
            console=CONSOLE,
            reg_map_factory=_reg_map,
            register_read_delay=REGISTER_READ_DELAY,
            default_chip=DEFAULT_CHIP,
        )
    else:
        bridge.configure(
            console=CONSOLE,
            reg_map_factory=_reg_map,
            register_read_delay=REGISTER_READ_DELAY,
            default_chip=DEFAULT_CHIP,
        )
    return ctx.bridge


def _get_serial() -> SerialMonitor:
    """Return the serial monitor singleton stored in the runtime context."""

    ctx = get_context()
    monitor = ctx.serial
    if not isinstance(monitor, SerialMonitor):
        ctx.serial = SerialMonitor(console=CONSOLE)
    else:
        monitor.console = CONSOLE
    return ctx.serial


def _current_target(chip: str | None = None) -> str:
    """Return the canonical target name for routing tool implementations."""

    ctx = get_context()
    fallback = ctx.chip or DEFAULT_CHIP
    return canonical_target_name(chip or fallback)


def _current_platform(chip: str | None = None) -> str:
    """Return the active platform identifier."""

    return detect_target_platform(_current_target(chip))


def _micropython_not_supported(tool_name: str, guidance: str = "") -> dict:
    """Return a consistent not-supported response for MicroPython targets."""

    target = _current_target()
    message = f"{tool_name} 不适用于 {target} MicroPython"
    if guidance:
        message += f"；{guidance}"
    return {
        "success": False,
        "platform": _current_platform(target),
        "message": message,
    }


def rp2040_connect(chip: str = None, port: str = None, baud: int = None) -> dict:
    """Connect an RP2040 board over USB serial."""

    return _rp2040_connect_impl(
        chip,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
    )


def rp2040_hardware_status() -> dict:
    """Return RP2040 + MicroPython runtime status."""

    return _rp2040_hardware_status_impl(console=CONSOLE)


def rp2040_compile(code: str, chip: str = None) -> dict:
    """Validate and cache RP2040 MicroPython source."""

    return _rp2040_compile_impl(
        code,
        chip=chip,
        console=CONSOLE,
        record_success_memory=_record_success_memory,
        log_error=telegram_log,
    )


def rp2040_flash(file_path: str = None, port: str = None, baud: int = None) -> dict:
    """Deploy `main.py` to the connected RP2040 board."""

    if file_path and str(file_path).lower().endswith(".bin"):
        return {
            "success": False,
            "platform": "rp2040",
            "message": "RP2040 MicroPython 部署的是 .py 源文件，不是 .bin 固件",
        }
    return _rp2040_flash_impl(
        file_path=file_path,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
        capture_timeout=POST_FLASH_DELAY + 1.5,
    )


def rp2040_auto_sync_cycle(code: str, request: str = "") -> dict:
    """Validate, deploy, and observe an RP2040 MicroPython program."""

    return _rp2040_auto_sync_cycle_impl(
        code,
        request=request,
        baud=SERIAL_BAUD,
        console=CONSOLE,
        max_attempts=MAX_DEBUG_ATTEMPTS,
        record_success_memory=_record_success_memory,
        log_error=telegram_log,
    )


def rp2040_list_files(path: str = ".", port: str = None, baud: int = None) -> dict:
    """List files on the connected MicroPython board."""

    return _rp2040_list_files_impl(
        path=path,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
    )


def esp_connect(chip: str = None, port: str = None, baud: int = None) -> dict:
    """Connect an ESP32 / ESP8266 board over USB serial."""

    return _esp_connect_impl(
        chip,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
    )


def esp_hardware_status() -> dict:
    """Return ESP + MicroPython runtime status."""

    return _esp_hardware_status_impl(console=CONSOLE)


def esp_compile(code: str, chip: str = None) -> dict:
    """Validate and cache ESP MicroPython source."""

    return _esp_compile_impl(
        code,
        chip=chip,
        console=CONSOLE,
        record_success_memory=_record_success_memory,
        log_error=telegram_log,
    )


def esp_flash(file_path: str = None, port: str = None, baud: int = None) -> dict:
    """Deploy `main.py` to the connected ESP MicroPython board."""

    if file_path and str(file_path).lower().endswith(".bin"):
        return {
            "success": False,
            "platform": "esp",
            "message": "ESP MicroPython 部署的是 .py 源文件，不是 .bin 固件",
        }
    return _esp_flash_impl(
        file_path=file_path,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
        capture_timeout=POST_FLASH_DELAY + 1.5,
    )


def esp_auto_sync_cycle(code: str, request: str = "") -> dict:
    """Validate, deploy, and observe an ESP MicroPython program."""

    return _esp_auto_sync_cycle_impl(
        code,
        request=request,
        baud=SERIAL_BAUD,
        console=CONSOLE,
        max_attempts=MAX_DEBUG_ATTEMPTS,
        record_success_memory=_record_success_memory,
        log_error=telegram_log,
    )


def esp_list_files(path: str = ".", port: str = None, baud: int = None) -> dict:
    """List files on the connected ESP MicroPython board."""

    return _esp_list_files_impl(
        path=path,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
    )


def canmv_connect(chip: str = None, port: str = None, baud: int = None) -> dict:
    """Connect a CanMV K230 / K230D board over USB serial."""

    return _canmv_connect_impl(
        chip,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
    )


def canmv_hardware_status() -> dict:
    """Return CanMV K230 + MicroPython runtime status."""

    return _canmv_hardware_status_impl(console=CONSOLE)


def canmv_compile(code: str, chip: str = None) -> dict:
    """Validate and cache CanMV K230 MicroPython source."""

    return _canmv_compile_impl(
        code,
        chip=chip,
        console=CONSOLE,
        record_success_memory=_record_success_memory,
        log_error=telegram_log,
    )


def canmv_flash(file_path: str = None, port: str = None, baud: int = None) -> dict:
    """Deploy `main.py` to the connected CanMV K230 MicroPython board."""

    if file_path and str(file_path).lower().endswith(".bin"):
        return {
            "success": False,
            "platform": "canmv",
            "message": "CanMV K230 MicroPython 部署的是 .py 源文件，不是 .bin 固件",
        }
    return _canmv_flash_impl(
        file_path=file_path,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
        capture_timeout=POST_FLASH_DELAY + 2.5,
    )


def canmv_auto_sync_cycle(code: str, request: str = "") -> dict:
    """Validate, deploy, and observe a CanMV K230 MicroPython program."""

    return _canmv_auto_sync_cycle_impl(
        code,
        request=request,
        baud=SERIAL_BAUD,
        console=CONSOLE,
        max_attempts=MAX_DEBUG_ATTEMPTS,
        record_success_memory=_record_success_memory,
        log_error=telegram_log,
    )


def canmv_list_files(path: str = ".", port: str = None, baud: int = None) -> dict:
    """List files on the connected CanMV K230 board."""

    return _canmv_list_files_impl(
        path=path,
        port=port,
        baud=baud or SERIAL_BAUD,
        console=CONSOLE,
    )


def _micropython_connect_for_target(
    chip: str, port: str | None = None, baud: int | None = None
) -> dict:
    platform = detect_target_platform(chip)
    if platform == "rp2040":
        return rp2040_connect(chip, port=port, baud=baud)
    if platform == "canmv":
        return canmv_connect(chip, port=port, baud=baud)
    return esp_connect(chip, port=port, baud=baud)


def _micropython_hardware_status_for_target(chip: str) -> dict:
    platform = detect_target_platform(chip)
    if platform == "rp2040":
        return rp2040_hardware_status()
    if platform == "canmv":
        return canmv_hardware_status()
    return esp_hardware_status()


def _micropython_compile_for_target(code: str, chip: str) -> dict:
    platform = detect_target_platform(chip)
    if platform == "rp2040":
        return rp2040_compile(code, chip=chip)
    if platform == "canmv":
        return canmv_compile(code, chip=chip)
    return esp_compile(code, chip=chip)


def _micropython_flash_for_target(
    chip: str,
    *,
    file_path: str | None = None,
    port: str | None = None,
    baud: int | None = None,
) -> dict:
    platform = detect_target_platform(chip)
    if platform == "rp2040":
        return rp2040_flash(file_path=file_path, port=port, baud=baud)
    if platform == "canmv":
        return canmv_flash(file_path=file_path, port=port, baud=baud)
    return esp_flash(file_path=file_path, port=port, baud=baud)


def _micropython_auto_sync_for_target(code: str, chip: str, request: str = "") -> dict:
    platform = detect_target_platform(chip)
    if platform == "rp2040":
        return rp2040_auto_sync_cycle(code, request=request)
    if platform == "canmv":
        return canmv_auto_sync_cycle(code, request=request)
    return esp_auto_sync_cycle(code, request=request)


# ─────────────────────────────────────────────────────────────
# STM32 专属工具实现
# ─────────────────────────────────────────────────────────────


def stm32_list_probes() -> dict:
    """列出所有可用的调试探针（ST-Link / CMSIS-DAP / J-Link）"""
    if is_micropython_target(_current_target()):
        ports = detect_serial_ports(verbose=False)
        return {
            "success": True,
            "platform": _current_platform(),
            "probes": [],
            "ports": ports,
            "message": (
                f"{_current_target()} MicroPython 通过 USB 串口连接，无需 SWD 探针"
                + (f"；检测到串口: {ports}" if ports else "；当前未检测到可用串口")
            ),
        }
    probes = list_swd_probes(console=CONSOLE)
    if not probes:
        return {"success": True, "probes": [], "message": "未检测到任何探针，请检查 USB 连接"}
    return {"success": True, "probes": probes}


def stm32_connect(chip: str = None) -> dict:
    """连接 STM32 硬件（pyocd 探针 + 串口监控）"""
    ctx = get_context()
    if is_generic_micropython_name(chip):
        ctx.chip = "MICROPYTHON"
        return _esp_connect_impl(
            "MICROPYTHON",
            port=None,
            baud=SERIAL_BAUD,
            console=CONSOLE,
        )
    target_chip = _current_target(chip)
    if is_micropython_target(target_chip):
        ctx.chip = target_chip
        return _micropython_connect_for_target(target_chip)
    swd_result = connect_swd(
        ctx,
        target_chip,
        default_chip=DEFAULT_CHIP,
        register_read_delay=REGISTER_READ_DELAY,
        reg_map_factory=_reg_map,
        console=CONSOLE,
    )
    bridge = swd_result.get("bridge")
    if isinstance(bridge, PyOCDBridge):
        ctx.bridge = bridge
    if swd_result["success"]:
        ctx.hw_connected = True
        ctx.chip = bridge.chip_info.get("device", target_chip)
        _get_compiler().set_chip(ctx.chip)
        serial_result = connect_serial(ctx, baud=SERIAL_BAUD, console=CONSOLE)
        monitor = serial_result.get("serial")
        if isinstance(monitor, SerialMonitor):
            ctx.serial = monitor
        ctx.serial_connected = bool(serial_result.get("success"))
        return {
            "success": True,
            "chip": ctx.chip,
            "probe": bridge.chip_info.get("probe", ""),
            "serial_connected": ctx.serial_connected,
            "message": f"硬件已连接: {ctx.chip}",
        }
    ctx.hw_connected = False
    return {"success": False, "message": str(swd_result.get("message", "连接失败"))}


def stm32_serial_connect(port: str = None, baud: int = None) -> dict:
    """
    单独连接/重连 UART 串口（不影响 pyocd 探针连接）。
    用于更换串口设备或在 stm32_connect 之后补充连接串口。
    """
    ctx = get_context()
    use_baud = baud or SERIAL_BAUD
    result = connect_serial(ctx, port or None, use_baud, console=CONSOLE)
    monitor = result.get("serial")
    if isinstance(monitor, SerialMonitor):
        ctx.serial = monitor
    ctx.serial_connected = bool(result.get("success"))
    if is_micropython_target(ctx.chip):
        ctx.hw_connected = ctx.serial_connected
    actual_port = getattr(ctx.serial, "port", None) or port or "自动检测"
    if ctx.serial_connected:
        return {
            "success": True,
            "port": actual_port,
            "baud": use_baud,
            "message": f"串口已连接: {actual_port} @ {use_baud}",
        }
    candidates = detect_serial_ports()
    return {
        "success": False,
        "port": port,
        "baud": use_baud,
        "message": f"串口打开失败，可用端口: {candidates if candidates else '无'}",
    }


def stm32_serial_disconnect() -> dict:
    """断开串口（保留 pyocd 探针连接）"""
    ctx = get_context()
    disconnect_serial(ctx)
    ctx.serial_connected = False
    if is_micropython_target(ctx.chip):
        ctx.hw_connected = False
    return {"success": True, "message": "串口已断开"}


def stm32_disconnect() -> dict:
    """断开硬件连接（释放探针和串口）"""
    ctx = get_context()
    disconnect_swd(ctx)
    disconnect_serial(ctx)
    ctx.hw_connected = False
    ctx.serial_connected = False
    return {"success": True, "message": "已断开"}


def stm32_set_chip(chip: str) -> dict:
    """切换目标芯片型号（如 STM32F103C8T6 / STM32F407VET6）"""
    ctx = get_context()
    previous_platform = detect_target_platform(ctx.chip)
    ctx.chip = canonical_target_name(chip)
    current_platform = detect_target_platform(ctx.chip)
    if previous_platform != current_platform:
        ctx.compiler = None
        ctx.last_bin_path = None
        if is_micropython_target(ctx.chip):
            disconnect_swd(ctx)
            ctx.bridge = None
    if is_micropython_target(ctx.chip):
        return {
            "success": True,
            "chip": ctx.chip,
            "family": current_platform,
            "platform": current_platform,
            "runtime": "MicroPython",
        }
    ci = _get_compiler().set_chip(ctx.chip)
    if ctx.hw_connected:
        _get_bridge().set_family(ci.get("family", "f1"))
    return {"success": True, "chip": ctx.chip, "family": ci.get("family", "f1")}


def stm32_hardware_status() -> dict:
    """获取当前硬件连接状态和工具链可用性"""
    ctx = get_context()
    if is_micropython_target(ctx.chip):
        return _micropython_hardware_status_for_target(ctx.chip)
    ci = _get_compiler().check(ctx.chip)
    return {
        "chip": ctx.chip,
        "hw_connected": ctx.hw_connected,
        "serial_connected": ctx.serial_connected,
        "gcc_ok": ci.get("gcc", False),
        "gcc_version": ci.get("gcc_version", "未找到"),
        "hal_ok": ci.get("hal", False),
        "hal_lib_ok": ci.get("hal_lib", False),
        "workspace": str(WORKSPACE),
    }


def stm32_compile(code: str, chip: str = None) -> dict:
    """编译 STM32 C 代码（完整 main.c）"""
    ctx = get_context()
    target_chip = _current_target(chip)
    ctx.chip = target_chip
    if is_micropython_target(target_chip):
        return _micropython_compile_for_target(code, target_chip)
    compiler = _get_compiler()
    if chip:
        compiler.set_chip(target_chip)
    result = compiler.compile(code)
    sync_result = {"success": False}
    if result["ok"]:
        ctx.last_code = code
        ctx.last_bin_path = result.get("bin_path")
        sync_result = sync_latest_workspace(code, chip=target_chip)
        if not sync_result.get("success"):
            CONSOLE.print(f"[dim]  ⚠ 缓存保存失败: {sync_result.get('message', '')}[/]")
    payload = {
        "success": result["ok"],
        "message": (result.get("msg") or "")[:600],
        "bin_path": result.get("bin_path"),
        "bin_size": result.get("bin_size", 0),
        "source_path": sync_result.get("path"),
        "source_file": sync_result.get("source_file"),
    }
    if payload["success"]:
        _record_success_memory(
            "compile_success",
            code=code,
            result=payload,
            chip=get_context().chip,
            log_error=telegram_log,
        )
    return payload


def stm32_compile_rtos(code: str, chip: str = None) -> dict:
    """编译带 FreeRTOS 内核的完整 main.c 代码"""
    ctx = get_context()
    target_chip = _current_target(chip)
    ctx.chip = target_chip
    if is_micropython_target(target_chip):
        return _micropython_not_supported(
            "stm32_compile_rtos", "请改用对应的 MicroPython compile 或 auto_sync_cycle 工具"
        )
    compiler = _get_compiler()
    if chip:
        compiler.set_chip(target_chip)
    result = compiler.compile_rtos(code)
    sync_result = {"success": False}
    if result["ok"]:
        ctx.last_code = code
        ctx.last_bin_path = result.get("bin_path")
        sync_result = sync_latest_workspace(code, chip=target_chip)
        if not sync_result.get("success"):
            CONSOLE.print(f"[dim]  ⚠ 缓存保存失败: {sync_result.get('message', '')}[/]")
    payload = {
        "success": result["ok"],
        "message": (result.get("msg") or "")[:600],
        "bin_path": result.get("bin_path"),
        "bin_size": result.get("bin_size", 0),
        "source_path": sync_result.get("path"),
        "source_file": sync_result.get("source_file"),
    }
    if payload["success"]:
        _record_success_memory(
            "compile_success",
            code=code,
            result=payload,
            chip=get_context().chip,
            log_error=telegram_log,
        )
    return payload


def stm32_recompile(mode: str = "auto") -> dict:
    """从 latest_workspace/main.c 直接重编译，无需 Gary 传递代码字符串。
    str_replace_edit 修改文件后调用此函数代替 read_file + stm32_compile。
    mode: "bare"(裸机) | "rtos"(FreeRTOS) | "auto"(自动检测，默认)
    """
    ctx = get_context()
    source_path = latest_workspace_main_path(ctx.chip)
    if not source_path.exists():
        fallback_paths = [
            latest_workspace_main_path("RP2040"),
            latest_workspace_main_path(DEFAULT_CHIP),
        ]
        for candidate in fallback_paths:
            if candidate.exists():
                source_path = candidate
                break
    if not source_path.exists():
        return {
            "success": False,
            "message": "latest_workspace 中不存在可重编译的 main.c / main.py，请先成功编译一次完整代码",
        }
    code = source_path.read_text(encoding="utf-8")
    if source_path.suffix == ".py" or is_micropython_target(ctx.chip):
        if mode == "rtos":
            return _micropython_not_supported(
                "stm32_recompile(mode='rtos')", "MicroPython 目标不支持 FreeRTOS 编译"
            )
        target_chip = ctx.chip if is_micropython_target(ctx.chip) else "ESP32"
        return _micropython_compile_for_target(code, target_chip)
    if mode == "auto":
        mode = (
            "rtos"
            if ("FreeRTOS.h" in code or "task.h" in code or "xTaskCreate" in code)
            else "bare"
        )
    if mode == "rtos":
        return stm32_compile_rtos(code)
    return stm32_compile(code)


def stm32_regen_bsp(chip: str = None) -> dict:
    """强制重新生成 startup.s / link.ld / FreeRTOSConfig.h。
    每次修改 compiler/ 包或切换芯片后调用一次，确保构建文件是最新版本。
    自动检查 startup.s 是否包含 FPU 使能代码（Cortex-M4 必须）。
    """
    if is_micropython_target(chip or _current_target()):
        return _micropython_not_supported("stm32_regen_bsp", "MicroPython 目标不需要 BSP 生成")
    import importlib

    # 强制重载 compiler 包，绕过进程内缓存
    globals()["_compiler_module"] = importlib.reload(_compiler_module)
    if hasattr(_compiler_module, "reload_package"):
        _compiler_module.reload_package()
    globals()["Compiler"] = _compiler_module.Compiler
    ctx = get_context()
    ctx.compiler = None
    try:
        ctx.compiler_mtime = _compiler_module.get_package_mtime()
    except Exception:
        ctx.compiler_mtime = 0.0

    compiler = _get_compiler()
    if chip:
        compiler.set_chip(chip.strip().upper())

    # 调用 set_chip 触发 startup.s / link.ld 重新生成
    chip_name = chip.strip().upper() if chip else ctx.chip
    ci = compiler.set_chip(chip_name)
    if ci is None:
        return {"success": False, "message": f"未知芯片: {chip_name}"}

    # 验证 startup.s 包含 FPU 使能
    from config import BUILD_DIR

    startup_path = BUILD_DIR / "startup.s"
    has_fpu_enable = False
    if startup_path.exists():
        content = startup_path.read_text()
        has_fpu_enable = "Enable FPU" in content or "CPACR" in content

    cpu = ci.get("cpu", "?")
    fpu = ci.get("fpu", False)
    ram_k = ci.get("ram_k", 0)
    flash_k = ci.get("flash_k", 0)

    warnings = []
    if fpu and not has_fpu_enable:
        warnings.append("⚠ startup.s 缺少 FPU 使能代码——请更新 compiler/ 包")
    if ram_k < 32 and ci.get("family") in ("f4",):
        warnings.append(f"⚠ RAM 仅 {ram_k}KB，FreeRTOS heap 可能不够")

    return {
        "success": True,
        "chip": chip_name,
        "cpu": cpu,
        "fpu_supported": fpu,
        "startup_fpu_enabled": has_fpu_enable,
        "flash_k": flash_k,
        "ram_k": ram_k,
        "files_regenerated": ["startup.s", "link.ld"],
        "warnings": warnings,
        "message": f"BSP 文件已重新生成 ({cpu}, {'有 FPU' if fpu else '无 FPU'}，{flash_k}K Flash / {ram_k}K RAM)"
        + (("；" + "；".join(warnings)) if warnings else ""),
    }


def stm32_analyze_fault_rtos() -> dict:
    """读取并分析 FreeRTOS 程序的 HardFault 寄存器。
    在普通 stm32_analyze_fault 基础上增加 FreeRTOS 专项诊断：
    - 识别 FPU 未使能导致的 PRECISERR
    - 识别 SysTick_Handler 冲突
    - 识别任务栈溢出引发的故障
    - 检查 startup.s 是否包含 FPU 初始化
    返回明确的根本原因和修复建议。
    """
    if is_micropython_target(_current_target()):
        return _micropython_not_supported(
            "stm32_analyze_fault_rtos",
            "MicroPython 目标应查看串口 Traceback，而不是 Cortex-M HardFault 寄存器",
        )
    if not get_context().hw_connected:
        return {"success": False, "message": "硬件未连接"}

    bridge = _get_bridge()
    regs = bridge.read_registers(
        ["SCB_CFSR", "SCB_HFSR", "SCB_BFAR", "PC", "SCB_MMFAR", "SCB_CPACR_FIELD"]
    )
    if not regs:
        regs = bridge.read_registers(["SCB_CFSR", "SCB_HFSR", "SCB_BFAR", "PC"])
    if not regs:
        return {"success": False, "message": "寄存器读取失败，请确认硬件已连接并已暂停"}

    cfsr = regs.get("SCB_CFSR", "0x0")
    hfsr = regs.get("SCB_HFSR", "0x0")
    bfar = regs.get("SCB_BFAR", "0x0")
    pc = regs.get("PC", "0x0")

    try:
        cfsr_v = int(cfsr, 16)
        hfsr_v = int(hfsr, 16)
        bfar_v = int(bfar, 16)
        pc_v = int(pc, 16)
    except (ValueError, TypeError):
        cfsr_v = hfsr_v = bfar_v = pc_v = 0

    # 检查 startup.s 的 FPU 使能
    from config import BUILD_DIR

    startup_path = BUILD_DIR / "startup.s"
    has_fpu_in_startup = False
    if startup_path.exists():
        txt = startup_path.read_text()
        has_fpu_in_startup = "CPACR" in txt or "Enable FPU" in txt

    # 检查 CPACR 硬件状态（读 0xE000ED88 的 bit[23:20]）
    fpu_hw_enabled = False
    try:
        cpacr = bridge._target.read32(0xE000ED88)
        fpu_hw_enabled = ((cpacr >> 20) & 0xF) == 0xF
    except Exception:
        pass

    # ── 诊断逻辑 ──────────────────────────────────────────
    root_cause = "未知"
    fix = "请读取 SCB_CFSR 后手动分析"
    severity = "unknown"

    preciserr = bool(cfsr_v & (1 << 9))
    bfarvalid = bool(cfsr_v & (1 << 15))
    iaccviol = bool(cfsr_v & (1 << 0))
    undefinstr = bool(cfsr_v & (1 << 16))
    stkovf = bool(cfsr_v & (1 << 12))  # STKOVF: 栈下溢
    unstkovf = bool(cfsr_v & (1 << 11))  # UNSTKOVF: 不稳定栈下溢

    # 判断 BFAR 是否"合理"（STM32 合法地址范围）
    bfar_valid_range = (
        0x08000000 <= bfar_v < 0x08200000
        or 0x20000000 <= bfar_v < 0x20030000
        or 0x40000000 <= bfar_v < 0x60000000
        or 0xE0000000 <= bfar_v
    )
    bfar_garbage = bfarvalid and not bfar_valid_range

    if preciserr and bfar_garbage and not fpu_hw_enabled:
        root_cause = (
            "FPU 未使能：ARM_CM4F port.c 的 PendSV_Handler 执行 vpush/vpop 时触发 PRECISERR"
        )
        fix = (
            "修复方法（已在 compiler/ 包修复，重新编译即可）：\n"
            "  1. 调用 stm32_regen_bsp() 重新生成 startup.s（含 CPACR 初始化）\n"
            "  2. 重新编译：stm32_compile_rtos(code)\n"
            "  不需要在代码里手动写 SCB->CPACR"
        )
        severity = "critical"
    elif undefinstr and not fpu_hw_enabled:
        root_cause = "FPU 指令在 FPU 禁用状态下执行（UNDEFINSTR）"
        fix = "同上，重新生成 startup.s 后重新编译"
        severity = "critical"
    elif stkovf or unstkovf:
        root_cause = "任务栈溢出（FreeRTOS 检测到栈越界）"
        fix = "增大任务的 stack_words 参数：普通任务 ≥128，FPU 任务 ≥256，含 printf 的任务 ≥384"
        severity = "high"
    elif preciserr and bfarvalid:
        root_cause = f"总线错误：精确地址 BFAR={bfar} 非法（可能是外设时钟未开启或访问了无效内存）"
        fix = "检查 PC 指向的函数，确认相关外设 RCC 时钟已 __HAL_RCC_xxx_CLK_ENABLE()"
        severity = "medium"
    elif hfsr_v & (1 << 1):
        root_cause = "向量表读取失败（VECTTBL）：中断向量地址无效"
        fix = "检查链接脚本 FLASH 地址和向量表对齐"
        severity = "critical"
    elif cfsr_v == 0 and hfsr_v == 0:
        root_cause = "无 HardFault（程序正常运行）"
        fix = "无需修复"
        severity = "none"

    # 补充 startup 检查信息
    startup_note = ""
    if not has_fpu_in_startup:
        startup_note = "⚠ 当前 startup.s 不含 FPU 使能代码，调用 stm32_regen_bsp() 后重新编译"
    elif not fpu_hw_enabled:
        startup_note = "⚠ startup.s 含 FPU 使能但硬件 CPACR 当前为 0（可能是旧固件未重新编译）"

    return {
        "success": True,
        "registers": regs,
        "fpu_hw_enabled": fpu_hw_enabled,
        "startup_has_fpu_enable": has_fpu_in_startup,
        "root_cause": root_cause,
        "severity": severity,
        "fix": fix,
        "startup_note": startup_note,
        "cfsr_bits": {
            "PRECISERR": preciserr,
            "BFARVALID": bfarvalid,
            "IACCVIOL": iaccviol,
            "UNDEFINSTR": undefinstr,
            "STKOVF": stkovf,
        },
    }


def stm32_rtos_check_code(code: str) -> dict:
    """FreeRTOS 代码静态检查 —— 编译前捕获常见 RTOS 编程错误。
    检查 SysTick 冲突、HAL_Delay 陷阱、缺少 hook 函数、栈大小、ISR 安全等。
    """
    if is_micropython_target(_current_target()):
        return _micropython_not_supported(
            "stm32_rtos_check_code", "MicroPython 目标不使用 FreeRTOS C 工程"
        )
    import re

    errors = []
    warnings = []
    suggestions = []

    # 1. SysTick_Handler 冲突
    if re.search(r"\bvoid\s+SysTick_Handler\b", code):
        errors.append(
            "❌ 禁止自定义 SysTick_Handler —— FreeRTOS 已通过 xPortSysTickHandler 接管 SysTick。"
            "删除 SysTick_Handler，改用 vApplicationTickHook() 维持 HAL_IncTick()"
        )

    # 2. HAL_Delay 在 xTaskCreate 之前
    hal_delay_pos = code.find("HAL_Delay")
    xtask_pos = code.find("xTaskCreate")
    if hal_delay_pos >= 0 and xtask_pos >= 0 and hal_delay_pos < xtask_pos:
        # 排除注释中的情况（简单排除）
        line_with_delay = code[:hal_delay_pos].rfind("\n")
        delay_line = code[line_with_delay:hal_delay_pos]
        if "//" not in delay_line and "/*" not in delay_line:
            errors.append(
                "❌ HAL_Delay() 在 xTaskCreate() 之前调用 —— SysTick 会触发 FreeRTOS tick handler，"
                "访问未初始化的任务列表导致 HardFault。"
                "把含 HAL_Delay 的初始化移到任务函数内部"
            )

    # 3. 必需 hook 函数
    required_hooks = {
        "vApplicationTickHook": "void vApplicationTickHook(void) { HAL_IncTick(); }",
        "vApplicationMallocFailedHook": "void vApplicationMallocFailedHook(void) { while(1); }",
        "vApplicationStackOverflowHook": "void vApplicationStackOverflowHook(TaskHandle_t t, char *n) { while(1); }",
        "vApplicationIdleHook": "void vApplicationIdleHook(void) {}",
    }
    for hook, template in required_hooks.items():
        if hook not in code:
            errors.append(f"❌ 缺少 {hook} —— 请添加: {template}")

    # 4. 任务栈大小检查
    task_creates = re.findall(r'xTaskCreate\s*\(\s*(\w+)\s*,\s*"[^"]*"\s*,\s*(\d+)', code)
    for func_name, stack_str in task_creates:
        stack = int(stack_str)
        # 查找任务函数体
        func_pattern = rf"void\s+{re.escape(func_name)}\s*\("
        func_match = re.search(func_pattern, code)
        if func_match:
            # 提取函数体（简单：从匹配位置到后续 2000 字符）
            func_body = code[func_match.start() : func_match.start() + 2000]
            has_float = any(
                kw in func_body
                for kw in [
                    "float ",
                    "double ",
                    "sinf(",
                    "cosf(",
                    "sqrtf(",
                    "tanf(",
                    "arm_",
                    ".0f",
                    "fabsf(",
                    "powf(",
                    "logf(",
                    "expf(",
                ]
            )
            has_printf = any(kw in func_body for kw in ["snprintf(", "sprintf(", "printf("])
            if has_printf and stack < 384:
                warnings.append(f"⚠ 任务 {func_name} 使用 snprintf 但栈仅 {stack} words，建议 ≥384")
            elif has_float and stack < 256:
                warnings.append(f"⚠ 任务 {func_name} 使用浮点运算但栈仅 {stack} words，建议 ≥256")
            elif stack < 128:
                warnings.append(f"⚠ 任务 {func_name} 栈仅 {stack} words，建议 ≥128")

    # 5. ISR 安全检查 —— 在 IRQHandler 中使用非 FromISR 的 API
    irq_funcs = re.findall(r"void\s+(\w+_IRQHandler)\s*\(void\)\s*\{", code)
    for irq_name in irq_funcs:
        # 提取 IRQ 函数体
        irq_start = code.find(f"void {irq_name}")
        if irq_start >= 0:
            irq_body = code[irq_start : irq_start + 1500]
            # 检查危险 API（非 FromISR 版本）
            unsafe_apis = [
                "xQueueSend(",
                "xQueueReceive(",
                "xSemaphoreTake(",
                "xSemaphoreGive(",
                "vTaskDelay(",
                "vTaskDelayUntil(",
                "xTaskCreate(",
                "vTaskDelete(",
                "printf(",
            ]
            for api in unsafe_apis:
                if api in irq_body and api.replace("(", "FromISR(") not in irq_body:
                    safe_api = api.replace("(", "FromISR(")
                    warnings.append(f"⚠ {irq_name} 中使用了 {api} —— ISR 中必须用 {safe_api}")

    # 6. 缺少头文件
    if "strlen(" in code or "memset(" in code or "memcpy(" in code:
        if "#include <string.h>" not in code and "#include<string.h>" not in code:
            warnings.append("⚠ 使用了 strlen/memset/memcpy 但未 #include <string.h>")
    if "sinf(" in code or "cosf(" in code or "sqrtf(" in code:
        if "#include <math.h>" not in code and "#include<math.h>" not in code:
            warnings.append("⚠ 使用了 sinf/cosf/sqrtf 但未 #include <math.h>")
    if "snprintf(" in code:
        if "#include <stdio.h>" not in code and "#include<stdio.h>" not in code:
            warnings.append("⚠ 使用了 snprintf 但未 #include <stdio.h>")

    # 7. 建议
    if "xSemaphoreCreateBinary" in code and "vTaskNotifyGive" not in code:
        suggestions.append(
            "💡 考虑用任务通知 (vTaskNotifyGive/ulTaskNotifyTake) 替代二值信号量，速度更快且更省内存"
        )
    if (
        "xEventGroupCreate" not in code
        and re.findall(r"xSemaphoreCreateBinary", code).__len__() >= 3
    ):
        suggestions.append("💡 多个二值信号量可能适合用事件组 (xEventGroupCreate) 替代")
    if "vTaskDelayUntil" not in code and "vTaskDelay" in code:
        suggestions.append(
            "💡 需要精确周期执行时用 vTaskDelayUntil 替代 vTaskDelay（避免累积漂移）"
        )

    return {
        "success": True,
        "errors": errors,
        "warnings": warnings,
        "suggestions": suggestions,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "message": (
            f"检查完成: {len(errors)} 个错误, {len(warnings)} 个警告, {len(suggestions)} 个建议"
            + (
                "\n" + "\n".join(errors + warnings + suggestions)
                if errors or warnings or suggestions
                else "\n✅ 代码通过所有 RTOS 检查"
            )
        ),
    }


def stm32_rtos_task_stats() -> dict:
    """通过 pyocd 读取 FreeRTOS 运行时任务统计信息。
    从 ELF 符号表解析全局变量地址，读取任务数、堆使用、当前任务等。
    需要先编译（有 ELF 文件）并连接硬件。
    """
    if is_micropython_target(_current_target()):
        return _micropython_not_supported(
            "stm32_rtos_task_stats", "MicroPython 目标没有这套 FreeRTOS 任务统计接口"
        )
    if not get_context().hw_connected:
        return {"success": False, "message": "硬件未连接"}

    from config import BUILD_DIR

    elf_path = BUILD_DIR / "firmware.elf"
    if not elf_path.exists():
        return {"success": False, "message": "ELF 文件不存在，请先编译"}

    bridge = _get_bridge()

    # 通过 nm 解析 ELF 符号表获取变量地址
    import subprocess

    symbols_to_find = {
        "uxCurrentNumberOfTasks": None,  # uint32_t 任务数
        "xFreeBytesRemaining": None,  # size_t heap_4 剩余
        "xMinimumEverFreeBytesRemaining": None,  # size_t 历史最低
        "pxCurrentTCB": None,  # TCB* 当前任务
    }

    try:
        r = subprocess.run(
            ["arm-none-eabi-nm", "-g", str(elf_path)], capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return {"success": False, "message": "nm 解析 ELF 失败"}

        for line in r.stdout.split("\n"):
            parts = line.strip().split()
            if len(parts) >= 3:
                addr_str, _typ, name = parts[0], parts[1], parts[2]
                if name in symbols_to_find:
                    symbols_to_find[name] = int(addr_str, 16)
    except Exception as e:
        return {"success": False, "message": f"符号解析异常: {e}"}

    result = {"success": True}

    # 读取各变量值
    try:
        addr = symbols_to_find["uxCurrentNumberOfTasks"]
        if addr:
            result["task_count"] = bridge._target.read32(addr)

        addr = symbols_to_find["xFreeBytesRemaining"]
        if addr:
            result["heap_free_bytes"] = bridge._target.read32(addr)

        addr = symbols_to_find["xMinimumEverFreeBytesRemaining"]
        if addr:
            result["heap_min_ever_free"] = bridge._target.read32(addr)

        addr = symbols_to_find["pxCurrentTCB"]
        if addr:
            tcb_ptr = bridge._target.read32(addr)
            result["current_tcb_addr"] = f"0x{tcb_ptr:08X}"

            # 尝试读取当前任务名（TCB 偏移量 52 处是 pcTaskName，长度 configMAX_TASK_NAME_LEN=16）
            try:
                name_offset = 52  # 标准 FreeRTOS TCB pcTaskName 偏移
                name_bytes = bytearray()
                for i in range(16):
                    b = bridge._target.read8(tcb_ptr + name_offset + i)
                    if b == 0:
                        break
                    name_bytes.append(b)
                result["current_task_name"] = name_bytes.decode("ascii", errors="replace")
            except Exception:
                pass

    except Exception as e:
        result["read_error"] = str(e)

    # 构造摘要消息
    parts = []
    if "task_count" in result:
        parts.append(f"任务数: {result['task_count']}")
    if "heap_free_bytes" in result:
        parts.append(f"堆剩余: {result['heap_free_bytes']}B")
    if "heap_min_ever_free" in result:
        parts.append(f"堆历史最低: {result['heap_min_ever_free']}B")
    if "current_task_name" in result:
        parts.append(f"当前任务: {result['current_task_name']}")
    result["message"] = " | ".join(parts) if parts else "读取完成（部分符号未找到）"

    return result


def stm32_rtos_suggest_config(
    task_count: int, use_fpu: bool = False, use_printf: bool = False, ram_k: int = 0
) -> dict:
    """根据用户的任务需求，计算推荐的 FreeRTOS 配置参数。
    估算堆大小、栈大小、优先级数，并检查 RAM 是否足够。
    """
    if is_micropython_target(_current_target()):
        return _micropython_not_supported(
            "stm32_rtos_suggest_config",
            "MicroPython 目标不需要 FreeRTOS heap/stack 配置估算",
        )
    compiler = _get_compiler()
    ci = compiler._chip_info
    if ci is None:
        return {"success": False, "message": "芯片未设置，请先 stm32_set_chip"}

    actual_ram_k = ram_k if ram_k > 0 else ci.get("ram_k", 64)
    has_fpu = ci.get("fpu", False)

    # 栈大小推荐
    if use_printf:
        recommended_stack = 384
        stack_reason = "含 snprintf/printf，需要 384+ words"
    elif use_fpu or has_fpu:
        recommended_stack = 256
        stack_reason = "FPU 上下文保存需要 256+ words"
    else:
        recommended_stack = 128
        stack_reason = "普通任务最小 128 words"

    # 堆大小估算
    tcb_size = 92  # TCB 约 92 字节
    stack_bytes = recommended_stack * 4  # words → bytes
    per_task = tcb_size + stack_bytes
    idle_task = per_task  # Idle 任务
    timer_task = tcb_size + (recommended_stack * 2 * 4)  # Timer 任务栈更大

    total_task_mem = per_task * task_count + idle_task + timer_task
    # 额外开销：队列/信号量/事件组 约 20%
    recommended_heap = int(total_task_mem * 1.3)
    # 对齐到 256B
    recommended_heap = ((recommended_heap + 255) // 256) * 256

    max_heap = actual_ram_k * 1024 // 2  # 最多用一半 RAM
    if recommended_heap > max_heap:
        recommended_heap = max_heap

    # RAM 使用估算
    static_overhead = 4096  # .data + .bss + ISR 栈 约 4KB
    total_ram_usage = static_overhead + recommended_heap
    ram_pct = total_ram_usage * 100 // (actual_ram_k * 1024)

    warnings = []
    if ram_pct > 85:
        warnings.append(f"⚠ RAM 使用率预估 {ram_pct}%，建议减少任务数或栈大小")
    if task_count > 7:
        warnings.append("⚠ 任务数较多，注意优先级分配避免优先级反转")
    if actual_ram_k < 16 and task_count > 2:
        warnings.append(f"⚠ RAM 仅 {actual_ram_k}KB，建议最多 2 个任务")

    config = {
        "success": True,
        "recommended_stack_words": recommended_stack,
        "stack_reason": stack_reason,
        "recommended_heap_bytes": recommended_heap,
        "recommended_priorities": min(task_count + 2, 7),
        "estimated_ram_usage_bytes": total_ram_usage,
        "estimated_ram_percent": ram_pct,
        "ram_total_kb": actual_ram_k,
        "per_task_overhead_bytes": per_task,
        "warnings": warnings,
        "message": (
            f"推荐配置: 栈={recommended_stack}words, 堆={recommended_heap}B, "
            f"优先级={min(task_count + 2, 7)}, RAM预估使用{ram_pct}%"
            + (("  " + "; ".join(warnings)) if warnings else "")
        ),
    }
    return config


def stm32_rtos_plan_project(
    description: str, peripherals: list = None, task_hints: list = None
) -> dict:
    """FreeRTOS 项目规划工具 —— 复杂 RTOS 项目的架构规划。

    根据用户需求描述，生成结构化的项目规划：
    - 任务分解（任务名、职责、栈大小、优先级）
    - 通信拓扑（任务间用什么机制通信：Queue/Semaphore/Notification/EventGroup）
    - 中断处理策略（哪些中断需要处理，如何通知任务）
    - 外设分配（哪个任务负责哪些外设）
    - 时序约束（哪些操作有实时性要求）
    - 资源估算（总堆/栈/RAM 使用）

    AI 在规划复杂 RTOS 项目时必须先调用此工具，待用户确认后再写代码。
    """
    if is_micropython_target(_current_target()):
        return _micropython_not_supported(
            "stm32_rtos_plan_project",
            "MicroPython 目标应直接规划模块/协程/定时器结构，不使用 FreeRTOS 任务划分",
        )
    import re

    compiler = _get_compiler()
    ci = compiler._chip_info
    if ci is None:
        return {"success": False, "message": "芯片未设置，请先 stm32_set_chip"}

    has_fpu = ci.get("fpu", False)
    ram_k = ci.get("ram_k", 64)
    flash_k = ci.get("flash_k", 256)
    cpu = ci.get("cpu", "cortex-m3")

    # ── 分析需求 ──────────────────────────────────────────
    desc_lower = description.lower()

    # 检测是否涉及浮点
    uses_float = any(
        kw in desc_lower
        for kw in [
            "浮点",
            "float",
            "sin",
            "cos",
            "pid",
            "温度计算",
            "dsp",
            "adc采样",
            "滤波",
            "fft",
            "角度",
            "加速度",
            "陀螺仪",
        ]
    )

    # 检测是否需要 printf/snprintf
    uses_printf = any(
        kw in desc_lower for kw in ["printf", "snprintf", "格式化", "打印浮点", "调试输出"]
    )

    # 检测外设
    detected_peripherals = []
    periph_map = {
        "uart": ["串口", "uart", "usart", "通信", "打印", "日志"],
        "i2c": ["i2c", "oled", "传感器", "bmp", "sht", "mpu", "加速度", "陀螺仪", "屏幕"],
        "spi": ["spi", "sd卡", "flash", "w25q", "tft", "lcd"],
        "adc": ["adc", "模拟", "采样", "电压", "温度", "光照"],
        "tim_pwm": ["pwm", "舵机", "电机", "蜂鸣器", "呼吸灯", "调光"],
        "tim_basic": ["定时器", "timer", "周期", "计时"],
        "gpio_out": ["led", "继电器", "数码管", "指示灯", "开关输出"],
        "gpio_in": ["按键", "按钮", "开关输入", "限位", "光电"],
        "exti": ["外部中断", "中断触发", "边沿检测"],
        "dma": ["dma", "高速传输"],
    }
    for periph, keywords in periph_map.items():
        if any(kw in desc_lower for kw in keywords):
            detected_peripherals.append(periph)

    if peripherals:
        for p in peripherals:
            if p.lower() not in detected_peripherals:
                detected_peripherals.append(p.lower())

    # ── 任务规划 ──────────────────────────────────────────
    planned_tasks = []

    # 根据需求自动推荐任务结构
    task_templates = {
        "sensor": {
            "triggers": [
                "传感器",
                "adc",
                "采样",
                "温度",
                "湿度",
                "加速度",
                "陀螺仪",
                "光照",
                "压力",
            ],
            "name": "SensorTask",
            "purpose": "传感器数据采集与处理",
            "priority": 3,
            "stack": 256 if uses_float else 128,
            "comm_out": "Queue（发送处理后的数据）",
        },
        "display": {
            "triggers": ["显示", "oled", "lcd", "tft", "数码管", "屏幕"],
            "name": "DisplayTask",
            "purpose": "显示刷新（从队列接收数据更新显示）",
            "priority": 1,
            "stack": 256,
            "comm_in": "Queue（接收要显示的数据）",
        },
        "control": {
            "triggers": ["控制", "电机", "舵机", "pid", "调节", "反馈"],
            "name": "ControlTask",
            "purpose": "控制算法执行（PID 等）",
            "priority": 4,
            "stack": 384 if uses_float else 256,
            "comm_in": "Queue（接收传感器数据）",
            "comm_out": "Queue/直接GPIO（输出控制信号）",
        },
        "comm": {
            "triggers": ["通信", "上位机", "蓝牙", "wifi", "发送", "协议"],
            "name": "CommTask",
            "purpose": "通信处理（串口/蓝牙数据收发）",
            "priority": 2,
            "stack": 384 if uses_printf else 256,
            "comm_in": "Queue（待发送的数据）",
        },
        "led": {
            "triggers": ["led", "指示灯", "呼吸灯", "闪烁"],
            "name": "LEDTask",
            "purpose": "LED 状态指示",
            "priority": 1,
            "stack": 128,
        },
        "button": {
            "triggers": ["按键", "按钮", "输入", "用户交互"],
            "name": "ButtonTask",
            "purpose": "按键扫描与事件分发",
            "priority": 2,
            "stack": 128,
            "comm_out": "TaskNotify/EventGroup（按键事件通知其他任务）",
        },
        "alarm": {
            "triggers": ["报警", "蜂鸣器", "警报", "阈值"],
            "name": "AlarmTask",
            "purpose": "报警判断与执行",
            "priority": 3,
            "stack": 128,
            "comm_in": "TaskNotify（由传感器任务触发）",
        },
        "log": {
            "triggers": ["日志", "记录", "sd卡", "存储"],
            "name": "LogTask",
            "purpose": "数据记录与存储",
            "priority": 1,
            "stack": 384,
            "comm_in": "Queue（待记录的数据）",
        },
    }

    if task_hints:
        # 用户提供了任务提示，直接使用
        for hint in task_hints:
            if isinstance(hint, dict):
                planned_tasks.append(hint)
            elif isinstance(hint, str):
                planned_tasks.append(
                    {
                        "name": hint,
                        "purpose": f"用户指定任务: {hint}",
                        "priority": 2,
                        "stack": 256 if uses_float else 128,
                    }
                )
    else:
        # 自动推荐
        for tmpl_name, tmpl in task_templates.items():
            if any(kw in desc_lower for kw in tmpl["triggers"]):
                task = {k: v for k, v in tmpl.items() if k != "triggers"}
                planned_tasks.append(task)

    # 如果没有匹配到任何任务，给一个默认的
    if not planned_tasks:
        planned_tasks.append(
            {
                "name": "MainTask",
                "purpose": "主要业务逻辑",
                "priority": 2,
                "stack": 256 if uses_float else 128,
            }
        )

    # ── 中断规划 ──────────────────────────────────────────
    interrupt_plan = []
    if "exti" in detected_peripherals or "中断" in desc_lower:
        interrupt_plan.append(
            {
                "irq": "EXTIx_IRQHandler",
                "strategy": "vTaskNotifyGiveFromISR → 唤醒处理任务",
                "note": "ISR 中仅做通知，数据处理在任务中完成",
            }
        )
    if "uart" in detected_peripherals:
        interrupt_plan.append(
            {
                "irq": "USARTx_IRQHandler",
                "strategy": "接收中断 → xQueueSendFromISR → CommTask 处理",
                "note": "使用 HAL_UART_Receive_IT 触发中断回调",
            }
        )
    if "tim_basic" in detected_peripherals or "tim_pwm" in detected_peripherals:
        interrupt_plan.append(
            {
                "irq": "TIMx_IRQHandler",
                "strategy": "定时器中断回调 → 设置标志或通知任务",
                "note": "周期性采样可用 vTaskDelayUntil 替代定时器中断",
            }
        )

    # ── 通信拓扑推荐 ──────────────────────────────────────
    comm_topology = []
    task_names = [t["name"] for t in planned_tasks]

    if "SensorTask" in task_names and "DisplayTask" in task_names:
        comm_topology.append(
            {
                "from": "SensorTask",
                "to": "DisplayTask",
                "mechanism": "xQueueSend/xQueueReceive",
                "data": "传感器数据结构体",
            }
        )
    if "SensorTask" in task_names and "ControlTask" in task_names:
        comm_topology.append(
            {
                "from": "SensorTask",
                "to": "ControlTask",
                "mechanism": "xQueueSend/xQueueReceive",
                "data": "传感器原始值",
            }
        )
    if "SensorTask" in task_names and "AlarmTask" in task_names:
        comm_topology.append(
            {
                "from": "SensorTask",
                "to": "AlarmTask",
                "mechanism": "xTaskNotifyGive（阈值触发时通知）",
                "data": "无（AlarmTask 自行读取共享数据）",
            }
        )
    if "ButtonTask" in task_names:
        for t in task_names:
            if t != "ButtonTask" and t != "LEDTask":
                comm_topology.append(
                    {
                        "from": "ButtonTask",
                        "to": t,
                        "mechanism": "xEventGroupSetBits",
                        "data": "按键事件位",
                    }
                )
                break  # 只连接一个示例

    if "CommTask" in task_names:
        data_sources = [t for t in task_names if t in ("SensorTask", "ControlTask", "LogTask")]
        for src in data_sources[:1]:
            comm_topology.append(
                {
                    "from": src,
                    "to": "CommTask",
                    "mechanism": "xQueueSend",
                    "data": "待发送的数据包",
                }
            )

    # ── 资源估算 ──────────────────────────────────────────
    total_stack_bytes = sum(t.get("stack", 128) * 4 for t in planned_tasks)
    tcb_overhead = len(planned_tasks) * 92
    idle_timer_overhead = 92 + 256 * 4 + 92 + 512 * 4  # Idle + Timer 任务
    queue_overhead = len(comm_topology) * 120  # 每个队列约 120B
    recommended_heap = int(
        (total_stack_bytes + tcb_overhead + idle_timer_overhead + queue_overhead) * 1.3
    )
    recommended_heap = ((recommended_heap + 255) // 256) * 256

    total_ram_est = recommended_heap + 4096  # heap + static
    ram_pct = total_ram_est * 100 // (ram_k * 1024)

    resource_check = {
        "total_tasks": len(planned_tasks) + 2,  # +Idle +Timer
        "total_stack_bytes": total_stack_bytes,
        "recommended_heap": recommended_heap,
        "estimated_ram_usage": total_ram_est,
        "ram_percent": ram_pct,
        "flash_k": flash_k,
        "ram_k": ram_k,
    }

    warnings = []
    if ram_pct > 85:
        warnings.append(
            f"⚠ RAM 使用率预估 {ram_pct}%（{total_ram_est}B / {ram_k*1024}B），考虑减少任务数或栈大小"
        )
    if ram_k < 16 and len(planned_tasks) > 2:
        warnings.append(f"⚠ RAM 仅 {ram_k}KB，{len(planned_tasks)} 个任务可能不够用")
    if not has_fpu and uses_float:
        warnings.append("⚠ 当前芯片无 FPU，浮点运算将使用软件模拟（较慢）")

    # ── 构造规划文档 ──────────────────────────────────────
    plan_text = f"📋 FreeRTOS 项目规划\n"
    plan_text += f"芯片: {ci.get('define','')} ({cpu}, {flash_k}K Flash, {ram_k}K RAM, {'FPU' if has_fpu else '无FPU'})\n"
    plan_text += f"需求: {description}\n\n"

    plan_text += "━━━ 任务规划 ━━━\n"
    for i, t in enumerate(planned_tasks, 1):
        plan_text += (
            f"  {i}. {t['name']} (优先级={t.get('priority',2)}, "
            f"栈={t.get('stack',128)}words)\n"
            f"     职责: {t.get('purpose','')}\n"
        )
        if "comm_in" in t:
            plan_text += f"     输入: {t['comm_in']}\n"
        if "comm_out" in t:
            plan_text += f"     输出: {t['comm_out']}\n"
    plan_text += f"  + Idle任务 + Timer任务 (系统自动创建)\n\n"

    if comm_topology:
        plan_text += "━━━ 通信拓扑 ━━━\n"
        for c in comm_topology:
            plan_text += f"  {c['from']} → {c['to']}: {c['mechanism']} ({c.get('data','')})\n"
        plan_text += "\n"

    if interrupt_plan:
        plan_text += "━━━ 中断策略 ━━━\n"
        for ip in interrupt_plan:
            plan_text += f"  {ip['irq']}: {ip['strategy']}\n"
            if ip.get("note"):
                plan_text += f"    💡 {ip['note']}\n"
        plan_text += "\n"

    plan_text += "━━━ 资源估算 ━━━\n"
    plan_text += f"  任务总数: {resource_check['total_tasks']} (含 Idle + Timer)\n"
    plan_text += f"  栈总量: {total_stack_bytes}B\n"
    plan_text += f"  推荐堆: {recommended_heap}B\n"
    plan_text += f"  RAM 预估: {total_ram_est}B / {ram_k*1024}B ({ram_pct}%)\n"

    if detected_peripherals:
        plan_text += f"\n━━━ 使用外设 ━━━\n"
        plan_text += f"  {', '.join(detected_peripherals)}\n"

    if warnings:
        plan_text += f"\n━━━ 警告 ━━━\n"
        for w in warnings:
            plan_text += f"  {w}\n"

    return {
        "success": True,
        "plan": {
            "tasks": planned_tasks,
            "communication": comm_topology,
            "interrupts": interrupt_plan,
            "peripherals": detected_peripherals,
            "resources": resource_check,
        },
        "warnings": warnings,
        "uses_fpu": uses_float and has_fpu,
        "uses_printf": uses_printf,
        "message": plan_text,
    }


def stm32_flash(bin_path: str = None) -> dict:
    """烧录固件到 STM32（需要先 connect + compile）"""
    ctx = get_context()
    if is_micropython_target(ctx.chip):
        return _micropython_flash_for_target(ctx.chip, file_path=bin_path)
    if not ctx.hw_connected:
        return {"success": False, "message": "硬件未连接，请先调用 stm32_connect"}
    path = bin_path or ctx.last_bin_path
    if not path or not Path(path).exists():
        return {"success": False, "message": f"固件文件不存在: {path}"}
    _get_serial().clear()
    return flash_via_swd(ctx, path)


def stm32_read_registers(regs: list = None) -> dict:
    """读取 STM32 硬件寄存器（RCC、GPIO、TIM、UART 等）"""
    if is_micropython_target(_current_target()):
        return _micropython_not_supported(
            "stm32_read_registers",
            "MicroPython 目标调试优先看串口输出、Traceback 和设备文件状态",
        )
    if not get_context().hw_connected:
        return {"success": False, "message": "硬件未连接"}
    result = read_registers(get_context(), regs, debug_all=not regs)
    if result is not None:
        return {"success": True, "registers": result}
    return {"success": False, "message": "寄存器读取失败"}


def stm32_analyze_fault() -> dict:
    """读取并分析 HardFault 寄存器（SCB_CFSR / SCB_HFSR）"""
    if is_micropython_target(_current_target()):
        return _micropython_not_supported(
            "stm32_analyze_fault",
            "MicroPython 目标不会返回 STM32 HardFault；请查看串口 Traceback",
        )
    if not get_context().hw_connected:
        return {"success": False, "message": "硬件未连接"}
    regs = _get_bridge().read_registers(["SCB_CFSR", "SCB_HFSR", "SCB_BFAR", "PC"])
    if not regs:
        return {"success": False, "message": "寄存器读取失败"}
    analysis = _get_bridge().analyze_fault(regs)
    return {"success": True, "registers": regs, "analysis": analysis}


def stm32_serial_read(timeout: float = 3.0, wait_for: str = None) -> dict:
    """读取 UART 串口输出（调试日志）"""
    return read_serial_output(get_context(), timeout=timeout, wait_for=wait_for)


def stm32_reset_debug_attempts() -> dict:
    """重置调试轮次计数器。开始一个全新需求时调用，确保计数从 1 开始。"""
    get_context().debug_attempt = 0
    return {"success": True, "message": "计数器已重置"}


def stm32_auto_flash_cycle(code: str, request: str = "") -> dict:
    """
    完整开发闭环（自动计轮次，最多 MAX_DEBUG_ATTEMPTS 轮）：
      编译 → 烧录（若已连接硬件）→ 等待启动 → 读串口 → 读寄存器
    返回每步结果 + 当前轮次 + 是否应放弃。
    """
    ctx = get_context()
    if is_micropython_target(ctx.chip):
        return _micropython_auto_sync_for_target(code, ctx.chip, request=request)
    ctx.debug_attempt += 1
    attempt = ctx.debug_attempt
    steps = []

    # 超出最大轮次 → 直接告知 AI 放弃
    if attempt > MAX_DEBUG_ATTEMPTS:
        return {
            "success": False,
            "give_up": True,
            "attempt": attempt,
            "message": f"已达到最大调试轮次 ({MAX_DEBUG_ATTEMPTS})，自动调试无法解决，请检查硬件接线或手动排查",
            "steps": [],
        }

    remaining = MAX_DEBUG_ATTEMPTS - attempt
    CONSOLE.print(f"[dim]  第 {attempt}/{MAX_DEBUG_ATTEMPTS} 轮[/]")

    # 1. 编译
    comp = stm32_compile(code)
    steps.append({"step": "compile", "success": comp["success"], "msg": comp["message"][:300]})
    if not comp["success"]:
        return {
            "success": False,
            "attempt": attempt,
            "remaining": remaining,
            "give_up": attempt >= MAX_DEBUG_ATTEMPTS,
            "steps": steps,
            "error": "编译失败，请根据错误信息修改代码",
            "compile_errors": comp["message"],
        }

    # 2. 烧录（失败时延迟重试，最多2次）
    if ctx.hw_connected and comp.get("bin_path"):
        fr = stm32_flash(comp["bin_path"])
        if not fr["success"]:
            for retry in range(2):
                wait_sec = 1.5 * (retry + 1)
                CONSOLE.print(
                    f"[yellow]  烧录失败（{fr['message'][:60]}），{wait_sec:.0f}s 后重连重试...[/]"
                )
                time.sleep(wait_sec)
                stm32_connect(ctx.chip)
                fr = stm32_flash(comp["bin_path"])
                if fr["success"]:
                    break
        steps.append({"step": "flash", "success": fr["success"], "msg": fr["message"]})
        if not fr["success"]:
            return {
                "success": False,
                "attempt": attempt,
                "remaining": remaining,
                "give_up": attempt >= MAX_DEBUG_ATTEMPTS,
                "steps": steps,
                "error": f"烧录失败（重试2次后仍失败）: {fr['message']}",
            }
        # 3. 串口监控
        uart_out = ""
        sensor_errors = []
        if ctx.serial_connected:
            CONSOLE.print("[dim]  等待启动...[/]")
            uart_out = wait_serial_adaptive(
                _get_serial(),
                keyword="Gary:BOOT",
                min_wait=0.5,
                max_wait=POST_FLASH_DELAY + 4.0,
            )
            boot_ok = "Gary:BOOT" in uart_out
            # 检测传感器错误关键词
            sensor_errors = [
                line.strip()
                for line in uart_out.splitlines()
                if "ERR:" in line or "Error" in line or "not found" in line.lower()
            ]
            # 打印串口输出到终端供用户查看
            if uart_out.strip():
                CONSOLE.print(f"[dim]  串口输出:[/]\n[cyan]{uart_out.strip()[:400]}[/]")
            else:
                CONSOLE.print("[yellow]  串口无输出（程序未启动或卡死）[/]")
            steps.append(
                {
                    "step": "uart",
                    "output": uart_out[:500],
                    "boot_ok": boot_ok,
                    "sensor_errors": sensor_errors,
                }
            )
        else:
            time.sleep(POST_FLASH_DELAY + 1.0)
            boot_ok = True  # 无串口跳过验证

        # 4. 读寄存器（打印到终端）
        regs = _get_bridge().read_all_for_debug()
        has_fault = False
        if regs:
            KEY_SET = (
                "SCB_CFSR",
                "PC",
                "RCC_APB2ENR",
                "RCC_APB1ENR",
                "GPIOA_CRL",
                "GPIOA_CRH",
                "GPIOA_ODR",
                "GPIOA_IDR",
                "GPIOB_CRL",
                "GPIOB_CRH",
                "GPIOB_ODR",
                "GPIOB_IDR",
                "GPIOC_CRL",
                "GPIOC_CRH",
                "GPIOC_ODR",
                "GPIOC_IDR",
                "GPIOA_MODER",
                "GPIOB_MODER",
                "GPIOC_MODER",
                "TIM2_CR1",
                "I2C1_CR1",
                "I2C1_SR1",
                "I2C2_CR1",
                "I2C2_SR1",
            )
            key_regs = {k: v for k, v in regs.items() if k in KEY_SET}
            has_fault = regs.get("SCB_CFSR", "0x00000000") not in ("0x00000000", "0x0")
            # 打印寄存器到终端
            CONSOLE.print("[dim]  关键寄存器:[/]")
            for k, v in key_regs.items():
                color = "red" if (k == "SCB_CFSR" and has_fault) else "dim"
                CONSOLE.print(f"[{color}]    {k} = {v}[/]")
            steps.append(
                {
                    "step": "registers",
                    "key_regs": key_regs,
                    "has_hardfault": has_fault,
                    "fault_analysis": _get_bridge().analyze_fault(regs) if has_fault else "",
                }
            )
        else:
            CONSOLE.print("[yellow]  寄存器读取失败（探针连接问题）[/]")

        # ── 5. 硬件缺失检测（I2C NACK/ARLO = 外设未接）──
        hw_missing = []
        if regs:
            for i2c_name in ("I2C1", "I2C2"):
                sr1_str = regs.get(f"{i2c_name}_SR1", "0x00000000")
                try:
                    sr1 = int(sr1_str, 16)
                except ValueError:
                    continue
                if sr1 & 0x0400:  # bit10 = AF (Acknowledge Failure / NACK)
                    hw_missing.append(f"{i2c_name}: AF(NACK)——设备未应答，很可能未接或地址错误")
                if sr1 & 0x0200:  # bit9 = ARLO (Arbitration Lost)
                    hw_missing.append(f"{i2c_name}: ARLO(仲裁丢失)——总线无设备响应或接线错误")
        # 串口 ERR 也算硬件问题
        if sensor_errors:
            hw_missing.extend(sensor_errors)

        if hw_missing:
            CONSOLE.print(f"[red bold]  ⚠ 检测到硬件缺失:[/]")
            for m in hw_missing:
                CONSOLE.print(f"[red]    • {m}[/]")

        runtime_ok = boot_ok and not has_fault and not hw_missing

        if runtime_ok:
            if request:
                _stm32_save_project(code, comp, request)
            _record_success_memory(
                "runtime_success",
                code=code,
                result=comp,
                request=request,
                steps=steps,
                chip=ctx.chip,
                log_error=telegram_log,
            )
            return {
                "success": True,
                "attempt": attempt,
                "steps": steps,
                "bin_size": comp.get("bin_size", 0),
            }
        elif hw_missing:
            # 硬件缺失 → 代码没问题，不要再修代码了，直接告知用户
            return {
                "success": False,
                "attempt": attempt,
                "remaining": remaining,
                "give_up": True,
                "hw_missing": hw_missing,
                "steps": steps,
                "error": (
                    "⚠ 硬件未接或接线错误（不是代码问题，停止修改代码）：\n"
                    + "\n".join(f"  • {m}" for m in hw_missing)
                    + "\n请告知用户检查硬件连接后重试。"
                ),
            }
        else:
            err_msg = "HardFault 或程序未正常启动，请根据 steps 中的寄存器和串口信息修复"
            if not boot_ok and not uart_out.strip():
                err_msg = "串口无任何输出——程序在打印 Gary: 之前就卡死了（常见原因：I2C 等待超时/传感器未接/死循环）"
            elif not boot_ok and uart_out.strip():
                err_msg = f"程序有输出但未打印 Gary: 启动标志，串口内容: {uart_out.strip()[:200]}"
            return {
                "success": False,
                "attempt": attempt,
                "remaining": remaining,
                "give_up": attempt >= MAX_DEBUG_ATTEMPTS,
                "steps": steps,
                "error": err_msg,
            }

    # 无硬件 → 仅编译
    if request:
        _stm32_save_project(code, comp, request)
    return {
        "success": True,
        "attempt": attempt,
        "steps": steps,
        "note": "硬件未连接，已完成编译",
        "bin_size": comp.get("bin_size", 0),
        "bin_path": comp.get("bin_path"),
    }


def stm32_save_code(code: str, request: str = "untitled") -> dict:
    """保存代码到项目目录"""
    ctx = get_context()
    ctx.last_code = code
    return _save_code_impl(code, request, chip=ctx.chip, console=CONSOLE)


def _stm32_save_project(code: str, comp: dict, request: str) -> Path:
    """内部：保存项目文件"""
    ctx = get_context()
    ctx.last_code = code
    return _save_project_impl(code, comp, request, chip=ctx.chip, console=CONSOLE)


def stm32_list_projects() -> dict:
    """列出最近 15 个历史项目"""
    return _list_projects_impl()


def stm32_read_project(project_name: str) -> dict:
    """读取指定项目的主源码（STM32 为 main.c，MicroPython 目标为 main.py）"""
    return _read_project_impl(project_name)


# ─────────────────────────────────────────────────────────────
# 通用文件/命令工具、Word 工具已拆分到独立模块
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# 工具注册表
# ─────────────────────────────────────────────────────────────
bind_tool_implementations(
    {
        # STM32 专属
        "stm32_list_probes": stm32_list_probes,
        "stm32_connect": stm32_connect,
        "stm32_disconnect": stm32_disconnect,
        "stm32_serial_connect": stm32_serial_connect,
        "stm32_serial_disconnect": stm32_serial_disconnect,
        "stm32_set_chip": stm32_set_chip,
        "stm32_hardware_status": stm32_hardware_status,
        "stm32_compile": stm32_compile,
        "stm32_compile_rtos": stm32_compile_rtos,
        "stm32_recompile": stm32_recompile,
        "stm32_regen_bsp": stm32_regen_bsp,
        "stm32_analyze_fault_rtos": stm32_analyze_fault_rtos,
        "stm32_rtos_check_code": stm32_rtos_check_code,
        "stm32_rtos_task_stats": stm32_rtos_task_stats,
        "stm32_rtos_suggest_config": stm32_rtos_suggest_config,
        "stm32_rtos_plan_project": stm32_rtos_plan_project,
        "stm32_flash": stm32_flash,
        "stm32_read_registers": stm32_read_registers,
        "stm32_analyze_fault": stm32_analyze_fault,
        "stm32_serial_read": stm32_serial_read,
        "stm32_auto_flash_cycle": stm32_auto_flash_cycle,
        "stm32_reset_debug_attempts": stm32_reset_debug_attempts,
        "stm32_generate_font": stm32_generate_font,
        "stm32_save_code": stm32_save_code,
        "stm32_list_projects": stm32_list_projects,
        "stm32_read_project": stm32_read_project,
        # RP2040 / MicroPython
        "rp2040_connect": rp2040_connect,
        "rp2040_hardware_status": rp2040_hardware_status,
        "rp2040_compile": rp2040_compile,
        "rp2040_flash": rp2040_flash,
        "rp2040_auto_sync_cycle": rp2040_auto_sync_cycle,
        "rp2040_list_files": rp2040_list_files,
        # ESP / MicroPython
        "esp_connect": esp_connect,
        "esp_hardware_status": esp_hardware_status,
        "esp_compile": esp_compile,
        "esp_flash": esp_flash,
        "esp_auto_sync_cycle": esp_auto_sync_cycle,
        "esp_list_files": esp_list_files,
        # CanMV / MicroPython
        "canmv_connect": canmv_connect,
        "canmv_hardware_status": canmv_hardware_status,
        "canmv_compile": canmv_compile,
        "canmv_flash": canmv_flash,
        "canmv_auto_sync_cycle": canmv_auto_sync_cycle,
        "canmv_list_files": canmv_list_files,
        "gary_save_member_memory": gary_save_member_memory,
        "gary_delete_member_memory": gary_delete_member_memory,
        # 通用
        "read_file": read_file,
        "create_or_overwrite_file": create_or_overwrite_file,
        "str_replace_edit": str_replace_edit,
        "list_directory": list_directory,
        "execute_command": execute_command,
        "search_files": search_files,
        "web_search": web_search,
        "browser_search": browser_search,
        "browser_open": browser_open,
        "browser_extract_links": browser_extract_links,
        "browser_open_result": browser_open_result,
        # 扩展通用工具
        "append_file_content": append_file_content,
        "grep_search": grep_search,
        "execute_batch_commands": execute_batch_commands,
        "fetch_url": fetch_url,
        "get_current_time": get_current_time,
        "ask_human": ask_human,
        "git_status": git_status,
        "git_diff": git_diff,
        "git_commit": git_commit,
        "edit_file_lines": edit_file_lines,
        "insert_content_by_regex": insert_content_by_regex,
        "check_python_code": check_python_code,
        "run_python_code": run_python_code,
        # Word 文档工具
        "read_docx": read_docx,
        "replace_docx_text": replace_docx_text,
        "append_docx_content": append_docx_content,
        "inspect_docx_structure": inspect_docx_structure,
        "insert_docx_content_after_heading": insert_docx_content_after_heading,
    }
)


# ─────────────────────────────────────────────────────────────
# STM32 系统提示词
# ─────────────────────────────────────────────────────────────
# Gary config — CLI 内 AI 接口配置向导
# ─────────────────────────────────────────────────────────────
def configure_ai_cli(agent: "STM32Agent | None" = None):
    """交互式配置 AI 接口（可在 CLI 内调用，也可独立运行）"""

    return _configure_ai_cli_impl(
        sync_ai_runtime_settings=_sync_ai_runtime_settings,
        agent=agent,
    )


# ─────────────────────────────────────────────────────────────
# STM32 Agent（TUI + 流式对话 + 工具框架）
# ─────────────────────────────────────────────────────────────
class STM32Agent:
    def __init__(self, interactive: bool = True):
        self.interactive = interactive
        self.thinking_log: List[Dict[str, Any]] = []
        self._static_prompt_cache = ""
        self._static_prompt_signature: tuple[Any, ...] | None = None
        self._dynamic_prompt_cache = ""
        self._dynamic_prompt_signature: tuple[Any, ...] | None = None
        self._system_prompt_cache = ""
        self._system_prompt_signature: tuple[Any, ...] | None = None
        self.messages: List[Dict] = [{"role": "system", "content": self._compose_system_prompt()}]
        self._pending_system_hint = ""
        self.client = get_ai_client(timeout=180.0)
        self.command_completer = GaryCompleter(
            list_projects=stm32_list_projects,
            default_chip=DEFAULT_CHIP,
        )
        os.environ.setdefault("no_proxy", "localhost,127.0.0.1")
        os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")

    def refresh_ai_client(self):
        self.client = get_ai_client(timeout=180.0)

    def _compose_system_prompt(self) -> str:
        """Compose the runtime system prompt from cached static/dynamic fragments."""

        ctx = get_context()
        skill_prompt = _get_manager().get_all_prompt_additions() or ""
        static_signature = (
            ctx.chip,
            ctx.cli_language,
            bool(ctx.hw_connected),
            skill_prompt,
        )
        if static_signature != self._static_prompt_signature:
            prompt = build_system_prompt(ctx.chip, ctx.cli_language, ctx.hw_connected)
            for error_type in ("compile_error", "hardfault", "i2c_failure"):
                debug_prompt = get_debug_prompt(
                    error_type,
                    {"chip": ctx.chip, "hardware_connected": ctx.hw_connected},
                )
                if debug_prompt:
                    prompt += "\n\n" + debug_prompt
            if skill_prompt:
                prompt += "\n" + skill_prompt.lstrip("\n")
            self._static_prompt_cache = prompt
            self._static_prompt_signature = static_signature

        member_prompt, member_hash = get_member_prompt_section_state(ctx.chip)
        dynamic_signature = (ctx.chip, member_hash)
        if dynamic_signature != self._dynamic_prompt_signature:
            self._dynamic_prompt_cache = member_prompt
            self._dynamic_prompt_signature = dynamic_signature

        system_signature = (self._static_prompt_signature, self._dynamic_prompt_signature)
        if system_signature != self._system_prompt_signature:
            prompt = self._static_prompt_cache
            if self._dynamic_prompt_cache:
                prompt += "\n\n" + self._dynamic_prompt_cache
            self._system_prompt_cache = prompt
            self._system_prompt_signature = system_signature

        return self._system_prompt_cache

    def reset_conversation(self):
        self.thinking_log = []
        self.messages = [{"role": "system", "content": self._compose_system_prompt()}]

    def refresh_system_prompt(self):
        prompt = self._compose_system_prompt()
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = prompt
        else:
            self.messages.insert(0, {"role": "system", "content": prompt})

    def _remove_web_research_hints(self):
        """Drop legacy transient system hints from conversation history."""

        preserved = self.messages[:1]
        remainder = [
            message
            for message in self.messages[1:]
            if not (
                message.get("role") == "system"
                and str(message.get("content", "")).startswith(WEB_RESEARCH_HINT_HEADER)
            )
        ]
        self.messages = preserved + remainder

    def _prepare_web_research_hint(self, user_input: str):
        """Prepare a one-turn research directive without adding extra system roles."""

        self._remove_web_research_hints()
        self._pending_system_hint = ""
        if not should_force_web_research(user_input):
            return
        ctx = get_context()
        self._pending_system_hint = build_web_research_hint(ctx.cli_language)

    def set_cli_language(self, language: str) -> dict:
        ctx = get_context()
        target = _normalize_cli_language(language)
        ctx.cli_language = target
        globals()["CLI_LANGUAGE"] = target
        saved = _write_cli_language_config(target)
        if saved:
            _sync_ai_runtime_settings(reload_ai_config())
        self.refresh_system_prompt()
        return {"success": True, "language": ctx.cli_language, "saved": saved}

    # ── Token 估算 ──────────────────────────────────────────
    def _tokens(self) -> int:
        ctx = get_context()
        estimate = estimate_request_tokens(
            messages=self._messages_for_api(),
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            model=AI_MODEL,
            temperature=AI_TEMPERATURE,
            enable_thinking=bool(getattr(ctx, "thinking_enabled", False)),
        )
        return int(estimate.get("total_tokens") or 0)

    def _record_thinking_trace(
        self,
        *,
        stage: str,
        thinking: str = "",
        provider_blocks: Any = None,
    ) -> None:
        """Store thinking/debug traces outside of model-visible conversation history."""

        text = str(thinking or "").strip()
        blocks = provider_blocks if provider_blocks else None
        if not text and not blocks:
            return
        if not hasattr(self, "thinking_log") or self.thinking_log is None:
            self.thinking_log = []
        entry: dict[str, Any] = {
            "stage": stage,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        if text:
            entry["thinking"] = text
        if blocks:
            entry["provider_blocks"] = blocks
        self.thinking_log.append(entry)
        if len(self.thinking_log) > 200:
            self.thinking_log = self.thinking_log[-200:]

    def _truncate_result(self, s: str, tool_name: str = "") -> str:
        """针对不同工具结果使用不同截断策略"""
        if len(s) <= MAX_TOOL_RESULT_LEN:
            return s
        separator = f"\n{TRUNCATED_TOOL_RESULT_NOTICE}\n"
        available = MAX_TOOL_RESULT_LEN - len(separator)
        if available <= 0:
            return TRUNCATED_TOOL_RESULT_NOTICE[:MAX_TOOL_RESULT_LEN]
        # 编译/串口结果：错误在末尾，保留末尾更多
        if tool_name in ("stm32_compile", "stm32_serial_read", "stm32_auto_flash_cycle"):
            head = max(1, available // 4)
            tail = max(0, available - head)
            return s[:head] + separator + (s[-tail:] if tail else "")
        head = max(1, available // 2)
        tail = max(0, available - head)
        return s[:head] + separator + (s[-tail:] if tail else "")

    def _truncate_history(self):
        """滑动窗口：保留 system prompt + 最近消息，总字符不超限"""
        MAX_CHARS = 180_000
        total = sum(len(str(m.get("content", ""))) for m in self.messages)
        removed = 0
        while total > MAX_CHARS and len(self.messages) > 3:
            # 始终保留 messages[0]（system prompt）
            victim = self.messages.pop(1)
            victim_len = len(str(victim.get("content", "")))
            total -= victim_len
            removed += 1
        if removed and self.interactive:
            CONSOLE.print(
                f"[dim]  📦 {_cli_text(f'历史压缩：移除 {removed} 条旧消息', f'History trimmed: removed {removed} old messages')}[/]"
            )

    # 原来是直接传 self.messages，改为过滤后传
    def _messages_for_api(self) -> list:
        """发送给 API 前处理消息格式：
        - 不把 thinking / reasoning 内容回灌到历史，避免后续轮次重复消耗 token
        - 仅保留对 provider 有效的普通内容与 tool_calls
        """
        sanitized_messages: list[dict[str, Any]] = []
        system_parts: list[str] = []
        pending_hint = str(getattr(self, "_pending_system_hint", "") or "").strip()

        for message in self.messages:
            role = message.get("role")
            if role == "system":
                content = str(message.get("content", "")).strip()
                if content:
                    system_parts.append(content)
                continue
            sanitized_messages.append(dict(message))

        if pending_hint:
            system_parts.append(pending_hint)

        if system_parts:
            sanitized_messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

        result = []
        for m in sanitized_messages:
            clean = {
                k: v
                for k, v in m.items()
                if k not in {"reasoning_content", "anthropic_thinking_blocks"}
            }
            result.append(clean)
        return result

    @staticmethod
    def _partial_think_tag_suffix(text: str, tags: tuple[str, ...]) -> str:
        """Return the longest suffix that could be the prefix of a think tag."""

        if not text:
            return ""
        max_len = min(len(text), max(len(tag) for tag in tags) - 1)
        for size in range(max_len, 0, -1):
            suffix = text[-size:]
            if any(tag.startswith(suffix) for tag in tags):
                return suffix
        return ""

    def _extract_think_segments(
        self,
        text: str,
        state: dict[str, Any],
    ) -> list[tuple[str, str]]:
        """Split streamed text into visible content and hidden think segments."""

        open_tag = "<think>"
        close_tag = "</think>"
        source = f"{state.get('pending', '')}{text or ''}"
        state["pending"] = ""
        segments: list[tuple[str, str]] = []

        while source:
            if state.get("inside_think", False):
                close_idx = source.find(close_tag)
                if close_idx >= 0:
                    if close_idx:
                        segments.append(("think", source[:close_idx]))
                    source = source[close_idx + len(close_tag) :]
                    state["inside_think"] = False
                    continue

                pending = self._partial_think_tag_suffix(source, (close_tag,))
                chunk = source[: -len(pending)] if pending else source
                if chunk:
                    segments.append(("think", chunk))
                state["pending"] = pending
                break

            open_idx = source.find(open_tag)
            close_idx = source.find(close_tag)

            if close_idx >= 0 and (open_idx < 0 or close_idx < open_idx):
                if close_idx:
                    segments.append(("content", source[:close_idx]))
                source = source[close_idx + len(close_tag) :]
                continue

            if open_idx >= 0:
                if open_idx:
                    segments.append(("content", source[:open_idx]))
                source = source[open_idx + len(open_tag) :]
                state["inside_think"] = True
                continue

            pending = self._partial_think_tag_suffix(source, (open_tag, close_tag))
            chunk = source[: -len(pending)] if pending else source
            if chunk:
                segments.append(("content", chunk))
            state["pending"] = pending
            break

        return segments

    @staticmethod
    def _flush_think_segments(state: dict[str, Any]) -> list[tuple[str, str]]:
        """Flush buffered partial tag text at the end of a stream."""

        pending = str(state.get("pending", "") or "")
        state["pending"] = ""
        if not pending:
            return []
        kind = "think" if state.get("inside_think", False) else "content"
        return [(kind, pending)]

    def _request_final_reply_after_tools(
        self, stream_to_console: bool = True
    ) -> dict[str, Any] | None:
        """部分模型在工具执行后会停在空回复，这里补一次只求最终答复的请求。"""
        if stream_to_console:
            CONSOLE.print(
                f"[dim]  ↺ {_cli_text('请求最终答复...', 'Requesting final reply...')}[/]"
            )
        telegram_log("chat final_reply_request start")
        try:
            ctx = get_context()
            stream = stream_chat(
                client=self.client,
                messages=self._messages_for_api()
                + [
                    {
                        "role": "system",
                        "content": _cli_text(
                            "请基于上面的工具结果直接给出最终答复，不要再调用工具，也不要只回复“已处理”。",
                            "Based on the tool results above, provide the final answer directly. Do not call more tools and do not reply with only 'done'.",
                        ),
                    }
                ],
                model=AI_MODEL,
                temperature=AI_TEMPERATURE,
                enable_thinking=bool(getattr(ctx, "thinking_enabled", False)),
            )
        except Exception as e:
            if stream_to_console:
                CONSOLE.print(
                    f"\n[red]{_cli_text('最终答复请求失败', 'Final reply request failed')}: {e}[/]"
                )
            telegram_log(f"chat final_reply_request error={str(e)[:160]}")
            return None

        content = ""
        thinking = ""
        anthropic_thinking_blocks = None
        in_think = False
        think_tag_state = {"inside_think": False, "pending": ""}
        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                chunk_thinking_blocks = getattr(chunk, "anthropic_thinking_blocks", None)
                if chunk_thinking_blocks is not None:
                    anthropic_thinking_blocks = chunk_thinking_blocks
                delta = chunk.choices[0].delta

                rc = getattr(delta, "reasoning_content", None)
                if rc:
                    if not in_think and stream_to_console:
                        CONSOLE.print(f"\n[dim {THEME}]💭 思考:[/]")
                    in_think = True
                    thinking += rc
                    if stream_to_console:
                        CONSOLE.print(rc, end="", style="dim")

                if delta.content:
                    for kind, piece in self._extract_think_segments(delta.content, think_tag_state):
                        if not piece:
                            continue
                        if kind == "think":
                            if not in_think and stream_to_console:
                                CONSOLE.print(f"\n[dim {THEME}]💭 思考:[/]")
                            in_think = True
                            thinking += piece
                            if stream_to_console:
                                CONSOLE.print(piece, end="", style="dim")
                            continue

                        if in_think and stream_to_console:
                            CONSOLE.print()
                        in_think = False
                        content += piece
                        if stream_to_console:
                            CONSOLE.print(piece, end="", style="white")

            for kind, piece in self._flush_think_segments(think_tag_state):
                if not piece:
                    continue
                if kind == "think":
                    if not in_think and stream_to_console:
                        CONSOLE.print(f"\n[dim {THEME}]💭 思考:[/]")
                    in_think = True
                    thinking += piece
                    if stream_to_console:
                        CONSOLE.print(piece, end="", style="dim")
                else:
                    if in_think and stream_to_console:
                        CONSOLE.print()
                    in_think = False
                    content += piece
                    if stream_to_console:
                        CONSOLE.print(piece, end="", style="white")

            if in_think and stream_to_console:
                CONSOLE.print()
            if content and stream_to_console:
                CONSOLE.print()
        except Exception as e:
            if stream_to_console:
                CONSOLE.print(
                    f"\n[red]{_cli_text('最终答复流式读取错误', 'Final reply stream error')}: {e}[/]"
                )
            telegram_log(f"chat final_reply_stream error={str(e)[:160]}")
            return None

        telegram_log(f"chat final_reply_request done len={len(content.strip())}")
        if not content.strip():
            return None
        self._record_thinking_trace(
            stage="final_reply",
            thinking=thinking,
            provider_blocks=anthropic_thinking_blocks,
        )
        return {"role": "assistant", "content": content.strip()}

    def _summarize_tool_result(self, tool_name: str, result_obj, preview: str) -> str:
        text = (preview or "").replace("\n", " ").strip()
        if isinstance(result_obj, dict):
            pieces = []
            if result_obj.get("message"):
                pieces.append(str(result_obj["message"]).strip())
            if result_obj.get("error"):
                pieces.append(str(result_obj["error"]).strip())
            if result_obj.get("path"):
                pieces.append(f"path={result_obj['path']}")
            if result_obj.get("chip"):
                pieces.append(f"chip={result_obj['chip']}")
            if result_obj.get("attempt") is not None:
                pieces.append(f"attempt={result_obj['attempt']}")
            if not pieces and "success" in result_obj:
                pieces.append(f"success={result_obj.get('success')}")
            if pieces:
                text = " | ".join(pieces)
        text = text or "已执行"
        if len(text) > 180:
            text = text[:177] + "..."
        return f"{tool_name}: {text}"

    def _build_tool_only_reply(self, tool_summaries: list[str], reply_parts: list[str]) -> str:
        lines = [
            _cli_text(
                "模型没有输出最终总结，我根据本次执行结果整理如下：",
                "The model did not return a final summary. Based on this run:",
            )
        ]
        if reply_parts:
            preface = (reply_parts[-1] or "").strip()
            if preface:
                if len(preface) > 240:
                    preface = preface[:237] + "..."
                lines.append(preface)
        for item in tool_summaries[-5:]:
            lines.append(f"- {item}")
        return "\n".join(lines)

    # ── 流式响应 + 工具调用 ─────────────────────────────────
    def chat(
        self,
        user_input: str,
        stream_to_console: bool = True,
        text_callback=None,
        tool_callback=None,
    ) -> str:
        self._truncate_history()
        self._prepare_web_research_hint(user_input)
        self.messages.append({"role": "user", "content": user_input})
        reply_parts: List[str] = []
        tool_summaries: List[str] = []
        used_tools = False

        while True:
            # API 调用
            try:
                ctx = get_context()
                stream = stream_chat(
                    client=self.client,
                    messages=self._messages_for_api(),
                    model=AI_MODEL,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    temperature=AI_TEMPERATURE,
                    enable_thinking=bool(getattr(ctx, "thinking_enabled", False)),
                )
            except Exception as e:
                if stream_to_console:
                    CONSOLE.print(f"\n[red]{_cli_text('API 错误', 'API error')}: {e}[/]")
                return f"{_cli_text('API 错误', 'API error')}: {e}"

            # 收集流式输出
            content = ""
            tool_calls_raw: Dict[int, dict] = {}
            thinking = ""
            anthropic_thinking_blocks = None
            in_think = False
            think_tag_state = {"inside_think": False, "pending": ""}

            try:
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    chunk_thinking_blocks = getattr(chunk, "anthropic_thinking_blocks", None)
                    if chunk_thinking_blocks is not None:
                        anthropic_thinking_blocks = chunk_thinking_blocks
                    delta = chunk.choices[0].delta

                    # Reasoning (deepseek-r1 style)
                    rc = getattr(delta, "reasoning_content", None)
                    if rc:
                        if not in_think and stream_to_console:
                            CONSOLE.print(f"\n[dim {THEME}]💭 思考:[/]")
                        in_think = True
                        thinking += rc
                        if stream_to_console:
                            CONSOLE.print(rc, end="", style="dim")

                    # 文本内容
                    if delta.content:
                        for kind, piece in self._extract_think_segments(
                            delta.content, think_tag_state
                        ):
                            if not piece:
                                continue
                            if kind == "think":
                                if not in_think and stream_to_console:
                                    CONSOLE.print(f"\n[dim {THEME}]💭 思考:[/]")
                                in_think = True
                                thinking += piece
                                if stream_to_console:
                                    CONSOLE.print(piece, end="", style="dim")
                                continue

                            if in_think and stream_to_console:
                                CONSOLE.print()
                            in_think = False
                            content += piece
                            if stream_to_console:
                                CONSOLE.print(piece, end="", style="white")
                            if text_callback:
                                preview_text = "\n\n".join(
                                    part for part in [*reply_parts, content.strip()] if part
                                ).strip()
                                text_callback(preview_text)

                    # 工具调用
                    if delta.tool_calls:
                        # 用 model_dump() 获取含 Gemini extra_content 的完整 chunk 数据
                        try:
                            _chunk_dict = chunk.model_dump()
                            _raw_tcs = (_chunk_dict.get("choices") or [{}])[0].get("delta", {}).get(
                                "tool_calls"
                            ) or []
                        except Exception:
                            _raw_tcs = []
                        for i, tc in enumerate(delta.tool_calls):
                            idx = tc.index
                            if idx not in tool_calls_raw:
                                tool_calls_raw[idx] = {
                                    "id": "",
                                    "name": "",
                                    "args": "",
                                    "thought_signature": "",
                                }
                            if tc.id:
                                tool_calls_raw[idx]["id"] = tc.id
                            if tc.function and tc.function.name:
                                tool_calls_raw[idx]["name"] = tc.function.name
                            if tc.function and tc.function.arguments:
                                tool_calls_raw[idx]["args"] += tc.function.arguments
                            # Gemini thinking models 将签名放在 extra_content.google.thought_signature
                            # 必须原样回传到 function.thought_signature，否则下次请求报 400
                            _raw_tc = _raw_tcs[i] if i < len(_raw_tcs) else {}
                            sig = (
                                (_raw_tc.get("extra_content") or {})
                                .get("google", {})
                                .get("thought_signature")
                                or (_raw_tc.get("function") or {}).get("thought_signature")
                                or _raw_tc.get("thought_signature")
                                or getattr(tc, "thought_signature", None)
                                or (
                                    getattr(tc.function, "thought_signature", None)
                                    if tc.function
                                    else None
                                )
                            )
                            if sig:
                                tool_calls_raw[idx]["thought_signature"] += sig

                for kind, piece in self._flush_think_segments(think_tag_state):
                    if not piece:
                        continue
                    if kind == "think":
                        if not in_think and stream_to_console:
                            CONSOLE.print(f"\n[dim {THEME}]💭 思考:[/]")
                        in_think = True
                        thinking += piece
                        if stream_to_console:
                            CONSOLE.print(piece, end="", style="dim")
                    else:
                        if in_think and stream_to_console:
                            CONSOLE.print()
                        in_think = False
                        content += piece
                        if stream_to_console:
                            CONSOLE.print(piece, end="", style="white")
                        if text_callback:
                            preview_text = "\n\n".join(
                                part for part in [*reply_parts, content.strip()] if part
                            ).strip()
                            text_callback(preview_text)

                if in_think and stream_to_console:
                    CONSOLE.print()
                if content and stream_to_console:
                    CONSOLE.print()

            except Exception as e:
                if stream_to_console:
                    CONSOLE.print(f"\n[red]{_cli_text('流式读取错误', 'Streaming error')}: {e}[/]")
                return f"{_cli_text('流式读取错误', 'Streaming error')}: {e}"

            # 无工具调用 → 结束
            if not tool_calls_raw:
                if content.strip():
                    self._record_thinking_trace(
                        stage="assistant_reply",
                        thinking=thinking,
                        provider_blocks=anthropic_thinking_blocks,
                    )
                    assistant_msg = {"role": "assistant", "content": content or ""}
                    self.messages.append(assistant_msg)
                    reply_parts.append(content.strip())
                    break
                if used_tools:
                    final_reply_msg = self._request_final_reply_after_tools(
                        stream_to_console=stream_to_console
                    )
                    if final_reply_msg:
                        self.messages.append(final_reply_msg)
                        reply_parts.append(str(final_reply_msg.get("content") or ""))
                        break
                    fallback_reply = self._build_tool_only_reply(tool_summaries, reply_parts)
                    self.messages.append({"role": "assistant", "content": fallback_reply})
                    reply_parts.append(fallback_reply)
                    break
                self._record_thinking_trace(
                    stage="assistant_empty_reply",
                    thinking=thinking,
                    provider_blocks=anthropic_thinking_blocks,
                )
                assistant_msg = {"role": "assistant", "content": content or ""}
                self.messages.append(assistant_msg)
                break

            # 构造 assistant tool_calls 消息
            tool_calls_list = []
            for idx in sorted(tool_calls_raw.keys()):
                tc = tool_calls_raw[idx]
                func_dict: dict = {"name": tc["name"], "arguments": tc["args"]}
                if tc.get("thought_signature"):  # Gemini 思考签名，必须原样回传
                    func_dict["thought_signature"] = tc["thought_signature"]
                tool_calls_list.append(
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": func_dict,
                    }
                )
            assistant_tool_msg = {
                "role": "assistant",
                "content": content or "",
                "tool_calls": tool_calls_list,
            }

            self._record_thinking_trace(
                stage="assistant_tool_call",
                thinking=thinking,
                provider_blocks=anthropic_thinking_blocks,
            )
            self.messages.append(assistant_tool_msg)
            used_tools = True

            # 执行工具
            tool_results = []
            for tc in tool_calls_list:
                func_name = tc["function"]["name"]
                args_str = tc["function"]["arguments"]
                result_obj = None
                telegram_log(f"chat tool_exec_start name={func_name}")

                if stream_to_console:
                    CONSOLE.print(f"[dim]  🔧 {func_name}[/]", end="")
                if tool_callback:
                    tool_callback({"phase": "start", "name": func_name, "arguments": args_str})
                try:
                    args = json.loads(args_str) if args_str.strip() else {}
                    result_obj = dispatch_tool_call(
                        func_name,
                        args,
                        get_context_fn=get_context,
                    )
                    result_str = json.dumps(result_obj, ensure_ascii=False, indent=2)
                except Exception as e:
                    result_str = f'{{"error": "{e}"}}'
                    result_obj = {"error": str(e)}
                    if tool_callback:
                        tool_callback({"phase": "error", "name": func_name, "error": str(e)})

                # 简短预览
                preview = result_str[:120].replace("\n", " ")
                if stream_to_console:
                    CONSOLE.print(f" → [dim green]{preview}[/]")
                if tool_callback:
                    tool_callback(
                        {
                            "phase": "finish",
                            "name": func_name,
                            "preview": preview,
                            "result": result_str,
                        }
                    )
                telegram_log(f"chat tool_exec_finish name={func_name} preview={preview[:80]}")
                tool_summaries.append(self._summarize_tool_result(func_name, result_obj, preview))

                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": self._truncate_result(result_str, func_name),
                    }
                )

            self.messages.extend(tool_results)
            self.refresh_system_prompt()
            self._truncate_history()
            # 继续循环，把工具结果发回 AI

            if content.strip():
                reply_parts.append(content.strip())

        return "\n\n".join(part for part in reply_parts if part).strip()

    # ── 内置命令处理 ────────────────────────────────────────
    def handle_builtin(self, cmd: str) -> bool:
        """Delegate slash command handling to the modular TUI command router."""

        return handle_slash_command(
            self,
            cmd,
            theme=THEME,
            cli_text=_cli_text,
            actions=_command_actions(),
            print_banner=_print_runtime_banner,
        )

    def run(self) -> None:
        """Run the interactive TUI loop."""

        run_interactive(
            self,
            handle_command=lambda agent, command: agent.handle_builtin(command),
            cli_text=_cli_text,
            theme=THEME,
            model=AI_MODEL,
            status_snapshot=_status_snapshot,
            ensure_cli_telegram_daemon=_ensure_cli_telegram_daemon,
            shutdown_runtime=_shutdown_cli_runtime,
            history_path=GARY_HOME / "prompt_history.txt",
            ensure_gary_home=_ensure_gary_home,
            completer=self.command_completer,
        )


def _status_snapshot() -> dict[str, Any]:
    """Return the current UI status snapshot for banner/status rendering."""

    ctx = get_context()
    return {
        "chip": ctx.chip,
        "hw_connected": ctx.hw_connected,
        "serial_connected": ctx.serial_connected,
    }


def _print_runtime_banner() -> None:
    """Render the current runtime banner using the modular TUI UI helpers."""

    print_banner(
        model=AI_MODEL,
        cli_text=_cli_text,
        theme=THEME,
        **_status_snapshot(),
    )


def _command_actions() -> dict[str, Callable[..., Any]]:
    """Build the slash-command action map for the TUI command router."""

    return {
        "connect": stm32_connect,
        "disconnect": stm32_disconnect,
        "serial_connect": stm32_serial_connect,
        "serial_disconnect": stm32_serial_disconnect,
        "set_chip": stm32_set_chip,
        "flash": stm32_flash,
        "hardware_status": stm32_hardware_status,
        "list_probes": stm32_list_probes,
        "list_projects": stm32_list_projects,
        "configure_ai_cli": configure_ai_cli,
        "shutdown_runtime": _shutdown_cli_runtime,
        "parse_cli_language": _parse_cli_language,
    }


def _configure_telegram_runtime() -> None:
    """Register stm32_agent runtime hooks for the Telegram integration."""

    configure_telegram_integration(
        console=CONSOLE,
        cli_text=_cli_text,
        is_ai_configured=_ai_is_configured,
        configure_ai_cli=lambda: configure_ai_cli(),
        agent_factory=lambda interactive=False: STM32Agent(interactive=interactive),
        hardware_status=stm32_hardware_status,
        connect=stm32_connect,
        disconnect=stm32_disconnect,
        set_chip=stm32_set_chip,
        list_projects=stm32_list_projects,
        detect_serial_ports=detect_serial_ports,
        serial_connect=stm32_serial_connect,
        get_current_chip=lambda: get_context().chip or "(未设置)",
        script_path=_PROJECT_ROOT / "stm32_agent.py",
        workdir=_PROJECT_ROOT,
    )


_configure_telegram_runtime()


def _print_startup_checks() -> None:
    """Render startup dependency checks before entering interactive mode."""

    ctx = get_context()
    ctx.chip = _current_target(ctx.chip)
    CONSOLE.print(f"[dim]{_cli_text('检查环境...', 'Checking environment...')}[/]")

    if is_micropython_target(ctx.chip):
        CONSOLE.print(
            f"[green]  {_cli_text('运行时', 'Runtime')}: {ctx.chip} / {target_runtime_label(ctx.chip)}[/]"
        )
        try:
            import serial as _serial  # type: ignore

            version = getattr(_serial, "__version__", "installed")
            CONSOLE.print(f"[green]  pyserial: {version}[/]")
        except ImportError:
            CONSOLE.print(
                f"[yellow]  pyserial: {_cli_text('未安装（pip install pyserial）', 'not installed (pip install pyserial)')}[/]"
            )

        serial_candidates = detect_serial_ports(verbose=False)
        if serial_candidates:
            CONSOLE.print(
                f"[green]  {_cli_text('串口', 'Serial')}: {_cli_text(f'检测到 {serial_candidates}（连接时自动选择）', f'detected {serial_candidates} (auto-selected on connect)')}[/]"
            )
        else:
            CONSOLE.print(
                f"[yellow]  {_cli_text('串口', 'Serial')}: {_cli_text(f'未检测到 {ctx.chip} 串口，请确认开发板已刷入 MicroPython 且 USB 数据线可传输', f'no {ctx.chip} serial port detected; ensure the board runs MicroPython and the USB cable supports data')}[/]"
            )

        try:
            import pyocd as _pyocd  # type: ignore

            CONSOLE.print(
                f"[dim]  pyocd: {_pyocd.__version__} ({_cli_text('可选，调试时备用', 'optional fallback for low-level debug')})[/]"
            )
        except ImportError:
            CONSOLE.print(
                f"[dim]  pyocd: {_cli_text('未安装（MicroPython 目标不强依赖）', 'not installed (not required for MicroPython targets)')}[/]"
            )
        CONSOLE.print()
        return

    compiler = _get_compiler()
    info = compiler.check(ctx.chip)
    if info.get("gcc"):
        CONSOLE.print(f"[green]  GCC: {info['gcc_version']}[/]")
    else:
        CONSOLE.print(
            f"[yellow]  GCC: {_cli_text('未找到 arm-none-eabi-gcc', 'arm-none-eabi-gcc not found')}[/]"
        )

    if info.get("hal"):
        CONSOLE.print(f"[green]  HAL: {_cli_text('已就绪', 'ready')}[/]")
    else:
        CONSOLE.print(
            f"[yellow]  HAL: {_cli_text('未找到，请运行 setup.sh', 'not found, run setup.sh')}[/]"
        )

    try:
        import pyocd

        CONSOLE.print(f"[green]  pyocd: {pyocd.__version__}[/]")
    except ImportError:
        CONSOLE.print(
            f"[yellow]  pyocd: {_cli_text('未安装（pip install pyocd）', 'not installed (pip install pyocd)')}[/]"
        )

    import glob as _glob
    import platform as _platform

    serial_candidates = detect_serial_ports(verbose=False)
    if serial_candidates:
        CONSOLE.print(
            f"[green]  {_cli_text('串口', 'Serial')}: {_cli_text(f'检测到 {serial_candidates}（连接时自动选择）', f'detected {serial_candidates} (auto-selected on connect)')}[/]"
        )
    else:
        platform_name = _platform.system()
        if platform_name == "Linux":
            import grp as _grp

            no_perm = [
                path
                for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS[4-9]*"]
                for path in _glob.glob(pattern)
                if os.path.exists(path) and not os.access(path, os.R_OK | os.W_OK)
            ]
            if no_perm:
                try:
                    grp_name = _grp.getgrgid(os.stat(no_perm[0]).st_gid).gr_name
                except Exception:
                    grp_name = "dialout"
                CONSOLE.print(
                    f"[yellow]  {_cli_text('串口', 'Serial')}: {_cli_text(f'发现 {no_perm} 但权限不足', f'found {no_perm} but permissions are insufficient')}[/]"
                )
                CONSOLE.print(
                    f"[yellow]    → sudo usermod -aG {grp_name} $USER && newgrp {grp_name}[/]"
                )
            else:
                CONSOLE.print(
                    f"[dim]  {_cli_text('串口', 'Serial')}: {_cli_text('未检测到串口设备（连接硬件后重试）', 'no serial device detected (connect hardware and retry)')}[/]"
                )
        elif platform_name == "Darwin":
            CONSOLE.print(
                f"[dim]  {_cli_text('串口', 'Serial')}: {_cli_text('未检测到串口设备', 'no serial device detected')}[/]"
            )
            CONSOLE.print(
                f"[dim]    {_cli_text('插上 USB 转串口后重启程序，或运行 /serial list 查看', 'Reconnect your USB serial adapter and restart, or run /serial list')}[/]"
            )
        elif platform_name == "Windows":
            CONSOLE.print(
                f"[dim]  {_cli_text('串口', 'Serial')}: {_cli_text('未检测到 COM 口', 'no COM ports detected')}[/]"
            )
            CONSOLE.print(
                f"[dim]    {_cli_text('请在设备管理器确认驱动已安装（CH340/CP210x），或运行 /serial list', 'Check the driver in Device Manager (CH340/CP210x), or run /serial list')}[/]"
            )
        else:
            CONSOLE.print(
                f"[dim]  {_cli_text('串口', 'Serial')}: {_cli_text('未检测到串口设备（连接硬件后重试）', 'no serial device detected (connect hardware and retry)')}[/]"
            )

    CONSOLE.print()


def run(args: argparse.Namespace) -> None:
    """Run the Gary CLI using parsed command-line arguments."""

    ctx = get_context()
    command = str(getattr(args, "command", "") or "").lower()
    command_args = list(getattr(args, "command_args", []) or [])
    telegram_arg = str(getattr(args, "telegram", "") or "").strip()
    ctx.thinking_enabled = bool(getattr(args, "thinking", False))

    if command == "telegram":
        handle_telegram_command(" ".join(command_args), source="cli")
        return
    if telegram_arg:
        handle_telegram_command(telegram_arg, source="cli")
        return

    if getattr(args, "doctor", False):
        run_doctor(cli_text=_cli_text)
        return

    if getattr(args, "config", False):
        configure_ai_cli()
        return

    chip_arg = str(getattr(args, "chip", "") or "").strip()
    if chip_arg:
        ctx.chip = canonical_target_name(chip_arg)
    else:
        ctx.chip = _current_target(ctx.chip)

    _print_startup_checks()

    task = str(getattr(args, "task", "") or "").strip()
    if task:
        if getattr(args, "connect", False):
            stm32_connect(chip_arg or None)
        agent = STM32Agent(interactive=False)
        run_oneshot(agent, task)
        stm32_disconnect()
        return

    if getattr(args, "connect", False):
        stm32_connect(chip_arg or None)

    agent = STM32Agent()
    agent.run()


__all__ = ["STM32Agent", "run"]
