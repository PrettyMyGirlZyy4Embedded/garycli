"""Tests for project persistence helpers."""

from __future__ import annotations

import json

from core import project_store


def test_latest_workspace_dir_lives_under_projects_dir():
    """Latest workspace should live under the same projects root as saved snapshots."""

    assert project_store.LATEST_WORKSPACE_DIR == project_store.PROJECTS_DIR / "latest_workspace"


def test_sync_latest_workspace_uses_main_py_for_rp2040(tmp_path, monkeypatch):
    """RP2040 latest workspace should cache source as main.py."""

    monkeypatch.setattr(project_store, "LATEST_WORKSPACE_DIR", tmp_path / "latest_workspace")

    result = project_store.sync_latest_workspace("print('Gary:BOOT')\n", chip="PICO_W")

    assert result["success"] is True
    assert result["source_file"] == "main.py"
    assert (tmp_path / "latest_workspace" / "main.py").read_text(
        encoding="utf-8"
    ) == "print('Gary:BOOT')\n"


def test_save_and_read_project_for_rp2040(tmp_path, monkeypatch):
    """RP2040 projects should persist and reload main.py transparently."""

    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(project_store, "LATEST_WORKSPACE_DIR", tmp_path / "latest_workspace")

    project_dir = project_store.save_project(
        "print('Gary:BOOT')\n",
        {"bin_path": None, "bin_size": 19},
        "rp2040 blink",
        chip="PICO",
    )

    config = json.loads((project_dir / "config.json").read_text(encoding="utf-8"))
    result = project_store.read_project(project_dir.name)

    assert config["chip"] == "PICO"
    assert config["platform"] == "rp2040"
    assert config["source_file"] == "main.py"
    assert (project_dir / "main.py").exists()
    assert result["success"] is True
    assert result["source_file"] == "main.py"
    assert "Gary:BOOT" in result["code"]


def test_save_and_read_project_for_esp(tmp_path, monkeypatch):
    """ESP MicroPython projects should also persist and reload main.py."""

    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(project_store, "LATEST_WORKSPACE_DIR", tmp_path / "latest_workspace")

    project_dir = project_store.save_project(
        "print('Gary:BOOT')\n",
        {"bin_path": None, "bin_size": 19},
        "esp blink",
        chip="ESP32",
    )

    config = json.loads((project_dir / "config.json").read_text(encoding="utf-8"))
    result = project_store.read_project(project_dir.name)

    assert config["chip"] == "ESP32"
    assert config["platform"] == "esp"
    assert config["source_file"] == "main.py"
    assert (project_dir / "main.py").exists()
    assert result["success"] is True
    assert result["source_file"] == "main.py"


def test_save_and_read_project_for_canmv(tmp_path, monkeypatch):
    """CanMV MicroPython projects should also persist and reload main.py."""

    monkeypatch.setattr(project_store, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(project_store, "LATEST_WORKSPACE_DIR", tmp_path / "latest_workspace")

    project_dir = project_store.save_project(
        "print('Gary:BOOT')\n",
        {"bin_path": None, "bin_size": 19},
        "canmv blink",
        chip="CANMV_K230",
    )

    config = json.loads((project_dir / "config.json").read_text(encoding="utf-8"))
    result = project_store.read_project(project_dir.name)

    assert config["chip"] == "CANMV_K230"
    assert config["platform"] == "canmv"
    assert config["source_file"] == "main.py"
    assert (project_dir / "main.py").exists()
    assert result["success"] is True
    assert result["source_file"] == "main.py"
