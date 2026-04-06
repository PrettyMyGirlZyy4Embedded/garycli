"""Regression tests for setup.py installer helpers."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_setup_module(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["setup.py"])
    setup_path = Path(__file__).resolve().parents[1] / "setup.py"
    spec = importlib.util.spec_from_file_location("gary_setup_module", setup_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_resolve_win_install_dir_falls_back_when_helper_missing(monkeypatch):
    """Missing _get_win_install_dir should not break Windows install."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.delitem(module.__dict__, "_get_win_install_dir", raising=False)
    monkeypatch.setattr(module.sys, "executable", str(Path("/tmp/gary-venv/Scripts/python.exe")))

    assert module._resolve_win_install_dir() == Path("/tmp/gary-venv/Scripts")


def test_default_win_install_dir_uses_existing_scripts_dir(monkeypatch):
    """If python.exe already lives in Scripts, do not append another Scripts."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.setattr(module.sys, "executable", str(Path("/tmp/gary-venv/Scripts/python.exe")))

    assert module._default_win_install_dir() == Path("/tmp/gary-venv/Scripts")


def test_searxng_url_defaults_to_loopback(monkeypatch):
    """The local search backend should default to loopback without extra config."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.delenv("GARY_SEARXNG_URL", raising=False)

    assert module._searxng_url() == "http://127.0.0.1:8080"


def test_searxng_host_port_uses_env_override(monkeypatch):
    """An explicit local SearXNG URL should drive the container port mapping."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.setenv("GARY_SEARXNG_URL", "http://127.0.0.1:18080/")

    assert module._searxng_host_port() == ("127.0.0.1", 18080)


def test_container_runtime_prefers_docker(monkeypatch):
    """Docker should be preferred over Podman when both are available."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "_which",
        lambda name: f"/usr/bin/{name}" if name in {"docker", "podman"} else None,
    )

    assert module._container_runtime() == "docker"


def test_venv_python_path_uses_project_bin_directory(monkeypatch, tmp_path):
    """Project venv helper should resolve the platform python path inside .venv."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.setattr(module, "IS_WIN", False)

    assert module._venv_python_path(tmp_path / ".venv") == tmp_path / ".venv" / "bin" / "python"


def test_externally_managed_python_detects_marker(monkeypatch, tmp_path):
    """PEP 668 marker should be treated as externally managed when not in a venv."""

    module = _load_setup_module(monkeypatch)
    marker = tmp_path / "EXTERNALLY-MANAGED"
    marker.write_text("managed", encoding="utf-8")
    monkeypatch.setattr(module, "_inside_virtualenv", lambda: False)
    monkeypatch.setattr(module, "_externally_managed_marker", lambda: marker)

    assert module._is_externally_managed_python() is True


def test_ensure_python_runtime_prefers_existing_project_venv(monkeypatch, tmp_path):
    """An existing project .venv should be reused before the system interpreter."""

    module = _load_setup_module(monkeypatch)
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setattr(module, "VENV_DIR", tmp_path / ".venv")
    monkeypatch.setattr(module, "_inside_virtualenv", lambda: False)

    selected = module.ensure_python_runtime(auto=False, allow_create=False)

    assert selected == venv_python.resolve()
    assert module.PIP[0] == str(venv_python.resolve())
    assert module.ACTIVE_PYTHON_LABEL == "project_venv"


def test_ensure_python_runtime_creates_project_venv_for_pep668(monkeypatch, tmp_path):
    """When PEP 668 blocks system installs, setup should create a project venv."""

    module = _load_setup_module(monkeypatch)
    venv_dir = tmp_path / ".venv"
    venv_python = venv_dir / "bin" / "python"
    marker = tmp_path / "EXTERNALLY-MANAGED"
    marker.write_text("managed", encoding="utf-8")

    def _fake_run(cmd, **kwargs):
        if cmd[:3] == [sys.executable, "-m", "venv"]:
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(module, "VENV_DIR", venv_dir)
    monkeypatch.setattr(module, "_inside_virtualenv", lambda: False)
    monkeypatch.setattr(module, "_externally_managed_marker", lambda: marker)
    monkeypatch.setattr(module, "_run", _fake_run)

    selected = module.ensure_python_runtime(auto=True, allow_create=True)

    assert selected == venv_python.resolve()
    assert module.PIP[0] == str(venv_python.resolve())
    assert module.ACTIVE_PYTHON_LABEL == "project_venv"
