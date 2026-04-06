"""Regression tests for setup.py installer helpers."""

from __future__ import annotations

import importlib.util
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
