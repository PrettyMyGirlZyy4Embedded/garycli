"""Tests for TUI status rendering."""

from __future__ import annotations

from tui.ui import _print_status_bar


def test_status_bar_shows_remaining_context_percent(monkeypatch):
    """The status bar should show remaining context percentage."""

    printed: list[str | None] = []

    monkeypatch.setattr(
        "tui.ui.console.print",
        lambda *args, **kwargs: printed.append(args[0] if args else None),
    )
    monkeypatch.setattr("tui.ui.console.rule", lambda *args, **kwargs: None)

    _print_status_bar(
        chip="STM32F103C8T6",
        model="qwen3.6-plus",
        hw_connected=False,
        serial_connected=False,
        tokens=87720,
        context_left_percent=66,
        cli_text=lambda zh, en: zh,
    )

    assert printed
    assert "66% left" in str(printed[0])
