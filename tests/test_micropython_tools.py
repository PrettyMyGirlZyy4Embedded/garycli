"""Tests for generic MicroPython workflow helpers."""

from __future__ import annotations

from core.micropython_tools import (
    _build_gary_bootstrap,
    micropython_compile,
    micropython_connect,
    micropython_flash,
    micropython_list_files_tool,
    micropython_soft_reset,
)
from core.state import get_context


def test_micropython_connect_autodetects_board(monkeypatch):
    """Generic MICROPYTHON connect should probe, infer chip, and connect serial."""

    ctx = get_context()
    old_chip = ctx.chip
    old_hw = ctx.hw_connected
    old_serial_connected = ctx.serial_connected
    old_serial = ctx.serial

    monkeypatch.setattr(
        "core.micropython_tools._autodetect_micropython_board",
        lambda **kwargs: {
            "success": True,
            "port": "/dev/ttyACM0",
            "chip": "PICO_W",
            "platform": "rp2040",
            "info": {
                "platform": "rp2",
                "machine": "Raspberry Pi Pico W with RP2040",
            },
        },
    )
    monkeypatch.setattr(
        "core.micropython_tools._reconnect_monitor",
        lambda port, baud, console=None: {"success": True, "port": port},
    )

    try:
        result = micropython_connect("MICROPYTHON")
        assert result["success"] is True
        assert result["chip"] == "PICO_W"
        assert result["platform"] == "rp2040"
        assert result["port"] == "/dev/ttyACM0"
        assert result["detected_info"]["platform"] == "rp2"
        assert ctx.chip == "PICO_W"
    finally:
        ctx.chip = old_chip
        ctx.hw_connected = old_hw
        ctx.serial_connected = old_serial_connected
        ctx.serial = old_serial


def test_micropython_connect_autodetect_returns_clear_error(monkeypatch):
    """Generic MICROPYTHON connect should surface scan failures cleanly."""

    monkeypatch.setattr(
        "core.micropython_tools._autodetect_micropython_board",
        lambda **kwargs: {
            "success": False,
            "candidate_ports": ["/dev/ttyACM0"],
            "message": "未扫描到可自动识别的 MicroPython 设备",
        },
    )

    result = micropython_connect("MIRCOPYTHON")
    assert result["success"] is False
    assert result["chip"] == "MICROPYTHON"
    assert result["candidate_ports"] == ["/dev/ttyACM0"]


def test_canmv_flash_deploys_managed_bundle(monkeypatch):
    """CanMV K230 deployment should use boot.py + gary_run.py instead of main.py."""

    ctx = get_context()
    old_chip = ctx.chip
    old_hw = ctx.hw_connected
    old_serial_connected = ctx.serial_connected
    old_serial = ctx.serial

    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "core.micropython_tools.sync_text_files",
        lambda **kwargs: calls.append(kwargs) or {"success": True, "boot_output": "Gary:BOOT\n"},
    )
    monkeypatch.setattr(
        "core.micropython_tools._reconnect_monitor",
        lambda port, baud, console=None: {"success": True, "port": port},
    )

    try:
        ctx.chip = "CANMV_K230"
        result = micropython_flash(code="print('Gary:BOOT')\n", port="/dev/ttyACM0")
        assert result["success"] is True
        assert result["device_bootstrap_path"] == "/sdcard/boot.py"
        assert result["device_main_path"] == "/sdcard/gary_run.py"
        files = calls[0]["files"]
        assert files[0][0] == "/sdcard/boot.py"
        assert files[1][0] == "/sdcard/gary_run.py"
        assert files[2][0] == "/sdcard/gary_autorun.flag"
        assert "Gary:RUN_START" in files[0][1]
        assert "Gary:RUN_ERROR" in files[0][1]
        assert "raise" in files[0][1]
        assert calls[0]["remove_paths"] == ["/sdcard/main.py"]
    finally:
        ctx.chip = old_chip
        ctx.hw_connected = old_hw
        ctx.serial_connected = old_serial_connected
        ctx.serial = old_serial


def test_canmv_list_files_defaults_to_sdcard(monkeypatch):
    """CanMV file listing should default to the /sdcard directory."""

    ctx = get_context()
    old_chip = ctx.chip

    monkeypatch.setattr(
        "core.micropython_tools.list_remote_files",
        lambda **kwargs: {"success": True, "path": kwargs["path"], "files": ["main.py"]},
    )

    try:
        ctx.chip = "CANMV_K230"
        result = micropython_list_files_tool(port="/dev/ttyACM0")
        assert result["success"] is True
        assert result["path"] == "/sdcard"
    finally:
        ctx.chip = old_chip


def test_micropython_flash_syncs_explicit_file_before_upload(tmp_path, monkeypatch):
    """Flashing from an explicit file should refresh latest_workspace before upload."""

    ctx = get_context()
    old_chip = ctx.chip
    old_last_code = ctx.last_code

    source_file = tmp_path / "camera.py"
    source_file.write_text("print('Gary:BOOT from file')\n", encoding="utf-8")
    sync_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "core.micropython_tools.sync_latest_workspace",
        lambda code, chip=None: (
            sync_calls.append((code, chip or "")) or {
                "success": True,
                "path": "workspace/projects/latest_workspace/main.py",
                "source_file": "main.py",
            }
        ),
    )
    monkeypatch.setattr(
        "core.micropython_tools.sync_text_files",
        lambda **kwargs: {"success": True, "boot_output": "Gary:BOOT\n"},
    )
    monkeypatch.setattr(
        "core.micropython_tools._reconnect_monitor",
        lambda port, baud, console=None: {"success": True, "port": port},
    )

    try:
        ctx.chip = "CANMV_K230"
        result = micropython_flash(file_path=str(source_file), port="/dev/ttyACM0")
        assert result["success"] is True
        assert sync_calls == [("print('Gary:BOOT from file')\n", "CANMV_K230")]
        assert result["source_file"] == "main.py"
    finally:
        ctx.chip = old_chip
        ctx.last_code = old_last_code


def test_micropython_flash_uses_last_code_when_latest_workspace_missing(monkeypatch, tmp_path):
    """If latest_workspace is missing, flashing should still save ctx.last_code before upload."""

    ctx = get_context()
    old_chip = ctx.chip
    old_last_code = ctx.last_code

    sync_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "core.micropython_tools.latest_workspace_main_path",
        lambda chip=None: tmp_path / "missing_main.py",
    )
    monkeypatch.setattr(
        "core.micropython_tools.sync_latest_workspace",
        lambda code, chip=None: (
            sync_calls.append((code, chip or "")) or {
                "success": True,
                "path": "workspace/projects/latest_workspace/main.py",
                "source_file": "main.py",
            }
        ),
    )
    monkeypatch.setattr(
        "core.micropython_tools.sync_text_files",
        lambda **kwargs: {"success": True, "boot_output": "Gary:BOOT\n"},
    )
    monkeypatch.setattr(
        "core.micropython_tools._reconnect_monitor",
        lambda port, baud, console=None: {"success": True, "port": port},
    )

    try:
        ctx.chip = "CANMV_K230"
        ctx.last_code = "print('Gary:BOOT from memory')\n"
        result = micropython_flash(port="/dev/ttyACM0")
        assert result["success"] is True
        assert sync_calls == [("print('Gary:BOOT from memory')\n", "CANMV_K230")]
    finally:
        ctx.chip = old_chip
        ctx.last_code = old_last_code


def test_micropython_flash_surfaces_raw_repl_lockup_diagnosis(monkeypatch):
    """Raw REPL handshake failures should surface actionable recovery hints."""

    ctx = get_context()
    old_chip = ctx.chip

    monkeypatch.setattr(
        "core.micropython_tools.sync_latest_workspace",
        lambda code, chip=None: {
            "success": True,
            "path": "workspace/projects/latest_workspace/main.py",
            "source_file": "main.py",
        },
    )
    monkeypatch.setattr(
        "core.micropython_tools.sync_text_files",
        lambda **kwargs: {
            "success": False,
            "reason": "raw_repl_unresponsive",
            "raw_repl_failure": True,
            "banner": "",
            "message": "进入 raw REPL 失败",
            "recovery_suggestions": ["先按 RST"],
            "suspected_causes": ["当前用户脚本持续占用解释器"],
        },
    )

    try:
        ctx.chip = "CANMV_K230"
        result = micropython_flash(code="print('Gary:BOOT')\n", port="/dev/ttyACM0")
        assert result["success"] is False
        assert result["raw_repl_failure"] is True
        assert result["suspected_user_code_block"] is True
        assert "当前无法进入 raw REPL" in result["message"]
        assert result["recovery_suggestions"] == ["先按 RST"]
    finally:
        ctx.chip = old_chip


def test_micropython_auto_sync_cycle_explains_raw_repl_failure(monkeypatch):
    """Auto sync should treat raw REPL failures as likely runtime lockups."""

    ctx = get_context()
    old_chip = ctx.chip
    old_attempt = ctx.debug_attempt

    monkeypatch.setattr(
        "core.micropython_tools.micropython_compile",
        lambda *args, **kwargs: {"success": True, "message": "ok"},
    )
    monkeypatch.setattr("core.micropython_tools.detect_serial_ports", lambda **kwargs: ["/dev/ttyACM0"])
    monkeypatch.setattr(
        "core.micropython_tools.micropython_flash",
        lambda **kwargs: {
            "success": False,
            "reason": "raw_repl_unresponsive",
            "raw_repl_failure": True,
            "message": "CanMV K230 当前无法进入 raw REPL",
            "recovery_suggestions": ["按 RST 复位"],
            "suspected_causes": ["无延时 while True 死循环"],
            "source_path": "workspace/projects/latest_workspace/main.py",
            "source_file": "main.py",
            "device_main_path": "/sdcard/gary_run.py",
        },
    )

    try:
        ctx.chip = "CANMV_K230"
        ctx.debug_attempt = 0
        from core.micropython_tools import micropython_auto_sync_cycle

        result = micropython_auto_sync_cycle("print('Gary:BOOT')\n")
        assert result["success"] is False
        assert result["raw_repl_failure"] is True
        assert result["suspected_user_code_block"] is True
        assert "无法进入 raw REPL" in result["error"]
        assert result["recovery_suggestions"] == ["按 RST 复位"]
    finally:
        ctx.chip = old_chip
        ctx.debug_attempt = old_attempt


def test_micropython_compile_rejects_while_loop_without_delay():
    """Every while loop should contain a pacing delay in MicroPython code."""

    result = micropython_compile("print('Gary:BOOT')\nwhile True:\n    pass\n", chip="ESP32")

    assert result["success"] is False
    assert result["error_type"] == "while_loop_missing_delay"
    assert result["line"] == 2
    assert "time.sleep_ms(5)" in result["message"]


def test_micropython_soft_reset_uses_raw_repl_tool(monkeypatch):
    """Soft reset should call the dedicated transport helper and reconnect the monitor."""

    ctx = get_context()
    old_chip = ctx.chip

    monkeypatch.setattr(
        "core.micropython_tools.soft_reset_board",
        lambda **kwargs: {"success": True, "boot_output": "Gary:BOOT\n"},
    )
    monkeypatch.setattr(
        "core.micropython_tools._reconnect_monitor",
        lambda port, baud, console=None: {"success": True, "port": port},
    )

    try:
        ctx.chip = "PICO_W"
        result = micropython_soft_reset(port="/dev/ttyACM0")
        assert result["success"] is True
        assert result["boot_output"] == "Gary:BOOT\n"
        assert result["serial_connected"] is True
    finally:
        ctx.chip = old_chip


def test_gary_bootstrap_reraises_user_code_errors():
    """Managed boot.py should not swallow gary_run.py exceptions."""

    script = _build_gary_bootstrap("CANMV_K230")

    assert "Gary:RUN_START" in script
    assert "Gary:RUN_ERROR" in script
    assert "sys.print_exception" not in script
    assert " except Exception:\n  print('Gary:RUN_ERROR')\n  raise\n" in script
