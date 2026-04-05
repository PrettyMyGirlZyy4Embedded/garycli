"""Slash command handling and prompt completions for the TUI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import compiler as _compiler_module
from core.memory import _ensure_member_file, _member_preview_markdown
from core.platforms import ESP_TARGET_CHOICES, RP2040_TARGET_CHOICES, detect_target_platform
from core.state import get_context
from gary_skills import _get_manager, handle_skill_command
from hardware.serial_mon import detect_serial_ports
from integrations.telegram import get_telegram_target_candidates, handle_telegram_command
from tui.ui import Markdown, Panel, Table, box, console

try:
    from prompt_toolkit.completion import Completer, Completion
except Exception:  # pragma: no cover - optional dependency fallback

    class Completer:  # type: ignore[override]
        """Fallback base class when prompt_toolkit is unavailable."""

    class Completion:  # type: ignore[override]
        """Fallback completion object when prompt_toolkit is unavailable."""

        def __init__(self, text: str, start_position: int = 0):
            self.text = text
            self.start_position = start_position


class GaryCompleter(Completer):
    """Prompt-toolkit completer for Gary slash commands."""

    COMMANDS = (
        "/help",
        "/connect",
        "/disconnect",
        "/serial",
        "/chip",
        "/flash",
        "/status",
        "/probes",
        "/projects",
        "/member",
        "/telegram",
        "/skill",
        "/config",
        "/language",
        "/clear",
        "/exit",
        "/quit",
    )
    LANGUAGE_OPTIONS = ("en", "zh")
    MEMBER_SUBCOMMANDS = ("path", "reload")
    SKILL_SUBCOMMANDS = (
        "list",
        "install",
        "uninstall",
        "enable",
        "disable",
        "info",
        "create",
        "export",
        "reload",
        "dir",
    )
    TELEGRAM_SUBCOMMANDS = (
        "status",
        "config",
        "start",
        "stop",
        "restart",
        "allow",
        "remove",
        "allow-all",
        "whitelist",
        "reset",
    )
    SERIAL_BAUD_RATES = ("9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600")

    def __init__(
        self,
        *,
        list_projects: Callable[[], dict[str, Any]],
        default_chip: str,
    ) -> None:
        """Initialize the completer with runtime callbacks."""

        self._list_projects = list_projects
        self._default_chip = default_chip

    def _complete(self, current: str, candidates: list[str] | tuple[str, ...]):
        needle = (current or "").lower()
        seen = set()
        for candidate in candidates:
            if candidate is None:
                continue
            value = str(candidate)
            if value in seen:
                continue
            seen.add(value)
            if needle and not value.lower().startswith(needle):
                continue
            yield Completion(value, start_position=-len(current))

    def _chip_candidates(self) -> list[str]:
        ctx = get_context()
        chips = set(_compiler_module.CHIP_DB.keys())
        chips.update(RP2040_TARGET_CHOICES)
        chips.update(ESP_TARGET_CHOICES)
        for value in (self._default_chip, ctx.chip):
            if value:
                chips.add(str(value).upper())
        return sorted(chips)

    def _serial_candidates(self) -> list[str]:
        try:
            ports = detect_serial_ports(verbose=False)
        except Exception:
            ports = []
        return ["list", *ports]

    def _project_candidates(self) -> list[str]:
        try:
            result = self._list_projects()
            return [p["name"] for p in result.get("projects", [])]
        except Exception:
            return []

    def _skill_candidates(self) -> list[str]:
        try:
            mgr = _get_manager()
            result = mgr.list_skills()
            return sorted(
                {
                    s.get("name") or s.get("display_name")
                    for s in result.get("skills", [])
                    if s.get("name") or s.get("display_name")
                }
            )
        except Exception:
            return []

    def _telegram_target_candidates(self) -> list[str]:
        return get_telegram_target_candidates()

    def get_completions(self, document, complete_event):
        """Yield prompt completions for the current document."""

        text = document.text_before_cursor
        stripped = text.lstrip()
        if not stripped:
            yield from self._complete("", self.COMMANDS)
            return
        if not stripped.startswith("/"):
            return

        trailing_space = stripped.endswith(" ")
        parts = stripped.split()
        if not parts:
            yield from self._complete("", self.COMMANDS)
            return

        if len(parts) == 1 and not trailing_space:
            yield from self._complete(parts[0], self.COMMANDS)
            return

        head = parts[0].lower()
        if trailing_space:
            current = ""
            args = parts[1:]
        else:
            current = parts[-1]
            args = parts[1:-1]
        arg_index = len(args)

        if head in ("/connect", "/chip"):
            if arg_index == 0:
                yield from self._complete(current, self._chip_candidates())
            return

        if head == "/serial":
            if arg_index == 0:
                yield from self._complete(
                    current, self._serial_candidates() + list(self.SERIAL_BAUD_RATES)
                )
            elif arg_index == 1 and args and args[0] != "list":
                yield from self._complete(current, self.SERIAL_BAUD_RATES)
            return

        if head == "/language":
            if arg_index == 0:
                yield from self._complete(current, self.LANGUAGE_OPTIONS)
            return

        if head == "/projects":
            if arg_index == 0:
                yield from self._complete(current, self._project_candidates())
            return

        if head == "/member":
            if arg_index == 0:
                yield from self._complete(current, self.MEMBER_SUBCOMMANDS)
            return

        if head == "/skill":
            if arg_index == 0:
                yield from self._complete(current, self.SKILL_SUBCOMMANDS)
                return
            subcmd = (args[0] if args else "").lower()
            if subcmd in ("uninstall", "remove", "rm", "enable", "disable", "info", "export"):
                if arg_index == 1:
                    yield from self._complete(current, self._skill_candidates())
            return

        if head == "/telegram":
            if arg_index == 0:
                yield from self._complete(current, self.TELEGRAM_SUBCOMMANDS)
                return
            subcmd = (args[0] if args else "").lower()
            if subcmd in ("allow", "remove", "add", "delete", "del", "rm") and arg_index >= 1:
                yield from self._complete(current, self._telegram_target_candidates())


def _show_help(theme: str, cli_text: Callable[[str, str], str]) -> None:
    """Render the built-in slash command help table."""

    table = Table(title=cli_text("内置命令", "Built-in Commands"), box=box.SIMPLE)
    table.add_column(cli_text("命令", "Command"), style=f"bold {theme}")
    table.add_column(cli_text("说明", "Description"), style="white")
    cmds = [
        (
            "/connect [chip]",
            cli_text(
                "连接目标板（如 /connect STM32F103C8T6、/connect PICO_W 或 /connect ESP32）",
                "Connect the target board (for example: /connect STM32F103C8T6, /connect PICO_W, or /connect ESP32)",
            ),
        ),
        (
            "/serial [port] [baud]",
            cli_text(
                "连接串口（如 /serial /dev/ttyUSB0 115200）",
                "Connect serial (for example: /serial /dev/ttyUSB0 115200)",
            ),
        ),
        (
            "/flash [bin]",
            cli_text(
                "烧录/同步最近一次产物（STM32 为 bin，MicroPython 目标为 main.py）",
                "Deploy the latest artifact (STM32 bin or main.py for MicroPython targets)",
            ),
        ),
        ("/disconnect", cli_text("断开探针和串口", "Disconnect probe and serial")),
        ("/chip [model]", cli_text("查看/切换目标板型号", "Show or change the target model")),
        (
            "/language [en|zh]",
            cli_text(
                "切换 CLI 语言，默认一键切到英文",
                "Switch CLI language. `/language` switches to English immediately",
            ),
        ),
        ("/probes", cli_text("列出所有可用探针", "List all available probes")),
        ("/status", cli_text("查看硬件+工具链状态", "Show hardware and toolchain status")),
        (
            "/config",
            cli_text(
                "配置 AI 接口（API Key / Model / Base URL）",
                "Configure AI settings (API Key / Model / Base URL)",
            ),
        ),
        ("/projects", cli_text("列出历史项目", "List saved projects")),
        (
            "/member [path|reload]",
            cli_text(
                "查看经验库；`path` 显示路径；`reload` 重新载入 member.md",
                "View memory; `path` shows the file location; `reload` refreshes member.md",
            ),
        ),
        (
            "/telegram [subcommand]",
            cli_text(
                "Telegram 机器人管理: start/stop/status/allow/remove/reset",
                "Manage the Telegram bot: start/stop/status/allow/remove/reset",
            ),
        ),
        (
            "/skill [subcommand]",
            cli_text(
                "技能管理: list/install/enable/disable/create/export",
                "Manage skills: list/install/enable/disable/create/export",
            ),
        ),
        ("/clear", cli_text("清空对话历史", "Clear conversation history")),
        ("/exit", cli_text("退出并停止 Telegram", "Exit and stop Telegram")),
        ("?", cli_text("显示帮助", "Show help")),
        (
            "Tab",
            cli_text(
                "补全命令/子命令/芯片/串口/技能名，历史输入会自动预测",
                "Complete commands, subcommands, chips, serial ports, and skills; history is suggested automatically",
            ),
        ),
    ]
    for cmd, desc in cmds:
        table.add_row(cmd, desc)
    console.print(table)
    console.print()


def handle_slash_command(
    agent: Any,
    cmd: str,
    *,
    theme: str,
    cli_text: Callable[[str, str], str],
    actions: Mapping[str, Callable[..., Any]],
    print_banner: Callable[[], None],
) -> bool:
    """Handle a single slash command for the interactive TUI."""

    parts = cmd.strip().split(None, 1)
    head = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if head in ("/help", "?"):
        _show_help(theme, cli_text)
        return True

    if head == "/connect":
        chip = arg.strip() or None
        console.print(f"\n[{theme}]{cli_text('连接硬件...', 'Connecting hardware...')}[/]")
        r = actions["connect"](chip)
        if r["success"]:
            serial_state = (
                cli_text("已连接", "connected")
                if r.get("serial_connected")
                else cli_text("未连接", "disconnected")
            )
            ctx = get_context()
            msg = cli_text(
                f"硬件已连接: {r.get('chip', ctx.chip)}  串口: {serial_state}",
                f"Connected: {r.get('chip', ctx.chip)}  Serial: {serial_state}",
            )
        else:
            is_micropython = detect_target_platform(chip or get_context().chip) in {"rp2040", "esp"}
            msg = (
                cli_text(
                    "连接失败，请检查 USB 串口、数据线和 MicroPython 固件",
                    "Connection failed. Check the USB serial port, data cable, and MicroPython firmware.",
                )
                if is_micropython
                else cli_text(
                    "连接失败，请检查探针 USB 连接和驱动",
                    "Connection failed. Check the probe USB connection and driver.",
                )
            )
        console.print(f"[{'green' if r['success'] else 'red'}]{msg}[/]\n")
        return True

    if head == "/disconnect":
        actions["disconnect"]()
        console.print(f"[{theme}]{cli_text('已断开', 'Disconnected.')}[/]\n")
        return True

    if head == "/flash":
        flash_path = arg.strip() or None
        result = actions["flash"](flash_path)
        color = "green" if result.get("success") else "red"
        message = str(result.get("message") or result.get("error") or result)
        console.print(f"[{color}]{message}[/]\n")
        return True

    if head == "/skill":
        handle_skill_command(arg, agent=agent)
        return True

    if head == "/telegram":
        handle_telegram_command(arg, source="builtin")
        return True

    if head == "/serial":
        tokens = arg.split()
        if tokens and tokens[0] == "list":
            ports = detect_serial_ports()
            if ports:
                console.print(f"[green]  {cli_text('可用串口:', 'Available serial ports:')}[/]")
                try:
                    import serial.tools.list_ports as lp

                    infos = {i.device: i.description for i in lp.comports()}
                except Exception:
                    infos = {}
                for port in ports:
                    console.print(f"    {port}  {infos.get(port, '')}")
            else:
                console.print(
                    f"[yellow]  {cli_text('未检测到可用串口', 'No serial ports detected')}[/]"
                )
            console.print()
            return True
        port = tokens[0] if tokens and tokens[0].startswith("/dev/") else None
        baud = None
        for token in tokens:
            if token.isdigit():
                baud = int(token)
                break
        result = actions["serial_connect"](port, baud)
        color = "green" if result["success"] else "red"
        if result["success"]:
            msg = cli_text(
                f"串口已连接: {result.get('port')} @ {result.get('baud')}",
                f"Serial connected: {result.get('port')} @ {result.get('baud')}",
            )
        else:
            candidates = detect_serial_ports(verbose=False)
            available = ", ".join(candidates) if candidates else cli_text("无", "none")
            msg = cli_text(
                f"串口打开失败，可用端口: {available}",
                f"Failed to open serial port. Available ports: {available}",
            )
        console.print(f"[{color}]{msg}[/]\n")
        return True

    if head == "/chip":
        if not arg:
            ctx = get_context()
            console.print(f"[{theme}]{cli_text('当前目标', 'Current target')}: {ctx.chip}[/]\n")
        else:
            result = actions["set_chip"](arg)
            family = result.get("family") or result.get("platform") or "generic"
            console.print(
                f"[{theme}]{cli_text('已切换', 'Switched to')}: {result['chip']} ({family})[/]\n"
            )
        return True

    if head == "/language":
        target = actions["parse_cli_language"](arg, default="en")
        if target is None:
            console.print(
                f"[yellow]{cli_text('用法: /language [en|zh]', 'Usage: /language [en|zh]')}[/]\n"
            )
            return True
        result = agent.set_cli_language(target)
        if target == "en":
            message = "CLI language switched to English."
            message += (
                " Saved to config.py."
                if result["saved"]
                else " Running in the current session only."
            )
        else:
            message = "CLI 语言已切换为中文。"
            message += " 已保存到 config.py。" if result["saved"] else " 仅当前会话生效。"
        console.print(f"[green]{message}[/]\n")
        return True

    if head == "/status":
        status = actions["hardware_status"]()
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column(style=f"bold {theme}")
        table.add_column(style="white")
        for key, value in status.items():
            table.add_row(key, str(value))
        console.print(table)
        console.print()
        return True

    if head == "/probes":
        probes = actions["list_probes"]()
        if probes["probes"]:
            for probe in probes["probes"]:
                console.print(f"  [{theme}]{probe['description']}[/] ({probe['uid']})")
        else:
            console.print(
                f"[yellow]{probes.get('message') or cli_text('未检测到任何探针，请检查 USB 连接', 'No probes detected. Check the USB connection.')}[/]"
            )
        console.print()
        return True

    if head == "/projects":
        result = actions["list_projects"]()
        if result["projects"]:
            table = Table(title=cli_text("历史项目", "Project History"), box=box.SIMPLE)
            table.add_column(cli_text("项目名", "Project"), style=f"bold {theme}")
            table.add_column(cli_text("芯片", "Chip"), style="cyan")
            table.add_column(cli_text("描述", "Description"), style="white")
            for project in result["projects"]:
                table.add_row(project["name"], project["chip"], project["request"][:40])
            console.print(table)
        else:
            console.print(f"[dim]{cli_text('暂无历史项目', 'No project history yet')}[/]")
        console.print()
        return True

    if head == "/member":
        subcmd = arg.strip().lower()
        if subcmd == "path":
            path = _ensure_member_file()
            console.print(f"[{theme}]{cli_text('member.md 路径', 'member.md path')}: {path}[/]\n")
            return True
        if subcmd == "reload":
            agent.refresh_system_prompt()
            console.print(
                f"[green]{cli_text('member.md 已重新加载到当前会话', 'member.md reloaded into the current session')}[/]\n"
            )
            return True
        if subcmd and subcmd not in {"path", "reload"}:
            console.print(
                f"[yellow]{cli_text('用法: /member [path|reload]', 'Usage: /member [path|reload]')}[/]\n"
            )
            return True
        agent.refresh_system_prompt()
        title = cli_text("Gary 经验库", "Gary Memory")
        console.print(
            Panel(
                Markdown(_member_preview_markdown(path_label=cli_text("路径", "Path"))),
                title=f"[bold {theme}]{title}[/]",
                border_style=theme,
            )
        )
        console.print()
        return True

    if head == "/clear":
        agent.reset_conversation()
        console.clear()
        print_banner()
        return True

    if head == "/config":
        actions["configure_ai_cli"](agent=agent)
        return True

    if head in ("/exit", "/quit"):
        console.print(
            f"\n[{theme}]{cli_text('正在退出，清理硬件和 Telegram...', 'Exiting, cleaning up hardware and Telegram...')}[/]"
        )
        shutdown = actions["shutdown_runtime"](stop_telegram=True)
        tg = shutdown.get("telegram", {})
        if tg.get("message"):
            color = "green" if tg.get("success") else "yellow"
            console.print(f"[{color}]{tg['message']}[/]")
        console.print(cli_text("再见！", "Goodbye!"))
        raise SystemExit(0)

    return False


__all__ = ["GaryCompleter", "handle_slash_command"]
