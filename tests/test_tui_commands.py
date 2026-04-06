"""Tests for TUI slash commands and completions."""

from __future__ import annotations

from types import SimpleNamespace

from tui.commands import GaryCompleter, _show_help, handle_slash_command


def test_completer_includes_enable_thinking_command():
    """The slash-command completer should expose thinking toggle commands."""

    completer = GaryCompleter(list_projects=lambda: {"projects": []}, default_chip="STM32F103C8T6")

    assert "/enable_thinking" in completer.COMMANDS
    assert "/disable_thinking" in completer.COMMANDS


def test_handle_enable_thinking_sets_session_flag(monkeypatch):
    """The slash command should enable thinking for the current session only."""

    ctx = SimpleNamespace(thinking_enabled=False)
    printed: list[str] = []

    monkeypatch.setattr("tui.commands.get_context", lambda: ctx)
    monkeypatch.setattr(
        "tui.commands.console.print", lambda *args, **kwargs: printed.append(str(args[0]))
    )

    handled = handle_slash_command(
        agent=SimpleNamespace(),
        cmd="/enable_thinking",
        theme="cyan",
        cli_text=lambda zh, en: zh,
        actions={},
        print_banner=lambda: None,
    )

    assert handled is True
    assert ctx.thinking_enabled is True
    assert any("已为当前会话开启 thinking" in line for line in printed)


def test_handle_enable_thinking_is_idempotent(monkeypatch):
    """Enabling twice should not flip the state or fail."""

    ctx = SimpleNamespace(thinking_enabled=True)
    printed: list[str] = []

    monkeypatch.setattr("tui.commands.get_context", lambda: ctx)
    monkeypatch.setattr(
        "tui.commands.console.print", lambda *args, **kwargs: printed.append(str(args[0]))
    )

    handled = handle_slash_command(
        agent=SimpleNamespace(),
        cmd="/enable_thinking",
        theme="cyan",
        cli_text=lambda zh, en: zh,
        actions={},
        print_banner=lambda: None,
    )

    assert handled is True
    assert ctx.thinking_enabled is True
    assert any("thinking 已经开启" in line for line in printed)


def test_handle_disable_thinking_sets_session_flag(monkeypatch):
    """The slash command should disable thinking for the current session only."""

    ctx = SimpleNamespace(thinking_enabled=True)
    printed: list[str] = []

    monkeypatch.setattr("tui.commands.get_context", lambda: ctx)
    monkeypatch.setattr(
        "tui.commands.console.print", lambda *args, **kwargs: printed.append(str(args[0]))
    )

    handled = handle_slash_command(
        agent=SimpleNamespace(),
        cmd="/disable_thinking",
        theme="cyan",
        cli_text=lambda zh, en: zh,
        actions={},
        print_banner=lambda: None,
    )

    assert handled is True
    assert ctx.thinking_enabled is False
    assert any("已为当前会话关闭 thinking" in line for line in printed)


def test_show_help_lists_all_runtime_commands(monkeypatch):
    """The help table should include all public slash commands and key aliases."""

    printed = []

    monkeypatch.setattr(
        "tui.commands.console.print",
        lambda *args, **kwargs: printed.append(args[0] if args else None),
    )

    _show_help("cyan", lambda zh, en: zh)

    table = printed[0]
    commands = table.columns[0]._cells

    assert "/help" in commands
    assert "/connect [chip]" in commands
    assert "/disconnect" in commands
    assert "/serial list" in commands
    assert "/serial [port] [baud]" in commands
    assert "/flash [bin]" in commands
    assert "/chip" in commands
    assert "/chip [model]" in commands
    assert "/language [en|zh]" in commands
    assert "/enable_thinking" in commands
    assert "/disable_thinking" in commands
    assert "/status" in commands
    assert "/probes" in commands
    assert "/projects" in commands
    assert "/member" in commands
    assert "/member path" in commands
    assert "/member reload" in commands
    assert "/telegram [subcommand]" in commands
    assert "/skill [subcommand]" in commands
    assert "/config" in commands
    assert "/clear" in commands
    assert "/exit" in commands
    assert "/quit" in commands
    assert "?" in commands
