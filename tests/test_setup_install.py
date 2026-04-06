"""Regression tests for setup.py installer helpers."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import urllib.error
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


def test_searxng_image_defaults_to_docker_hub(monkeypatch):
    """The default SearXNG image should come from Docker Hub."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.delenv("GARY_SEARXNG_IMAGE", raising=False)

    assert module._searxng_image() == "searxng/searxng:latest"


def test_searxng_git_url_defaults_to_official_repo(monkeypatch):
    """Native install should default to the official SearXNG repository."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.delenv("GARY_SEARXNG_GIT_URL", raising=False)

    assert module._searxng_git_url() == "https://github.com/searxng/searxng.git"


def test_searxng_wsl_distro_defaults_to_ubuntu(monkeypatch):
    """Windows WSL install should default to Ubuntu unless overridden."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.delenv("GARY_SEARXNG_WSL_DISTRO", raising=False)

    assert module._searxng_wsl_distro() == "Ubuntu"


def test_searxng_healthcheck_uses_homepage_not_json(monkeypatch):
    """Healthcheck should accept HTML-only SearXNG defaults."""

    module = _load_setup_module(monkeypatch)
    captured = {}

    class _DummyHandle:
        status = 200

        def read(self, size=-1):
            return b"<html><title>SearXNG</title></html>"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=5):
        captured["url"] = req.full_url
        return _DummyHandle()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    assert module._searxng_healthcheck("http://127.0.0.1:8080") is True
    assert captured["url"] == "http://127.0.0.1:8080/"


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


def test_setup_local_searxng_is_skipped_in_default_flow(monkeypatch):
    """Regular setup should not prompt for or pull SearXNG unless explicitly requested."""

    module = _load_setup_module(monkeypatch)
    asked = {"value": False}

    def _fail_if_asked(*args, **kwargs):
        asked["value"] = True
        raise AssertionError("setup_local_searxng should not ask in default flow")

    monkeypatch.setattr(module, "ask", _fail_if_asked)

    module.setup_local_searxng(auto=True, explicit=False)

    assert asked["value"] is False


def test_setup_local_searxng_offers_native_fallback_without_container_runtime(monkeypatch):
    """Interactive setup should offer the native path when Docker/Podman is unavailable."""

    module = _load_setup_module(monkeypatch)
    called = {"value": False, "auto": None, "explicit": None}

    monkeypatch.setattr(module, "_searxng_healthcheck", lambda base_url=None: False)
    monkeypatch.setattr(module, "_container_runtime", lambda: None)
    monkeypatch.setattr(module, "ask", lambda *args, **kwargs: True)

    def _mark_called(*args, **kwargs):
        called["value"] = True
        called["auto"] = kwargs.get("auto")
        called["explicit"] = kwargs.get("explicit")

    monkeypatch.setattr(module, "setup_native_searxng", _mark_called)

    module.setup_local_searxng(auto=False, explicit=False)

    assert called["value"] is True
    assert called["auto"] is True
    assert called["explicit"] is True


def test_setup_native_searxng_runs_official_script(monkeypatch, tmp_path):
    """Native install should clone the repo and invoke the official install script."""

    module = _load_setup_module(monkeypatch)
    repo_dir = tmp_path / "services" / "searxng" / "native-src"
    commands = []
    health = iter([False, True])

    monkeypatch.setattr(module, "IS_LINUX", True)
    monkeypatch.setattr(module, "SEARXNG_DIR", tmp_path / "services" / "searxng")
    monkeypatch.setattr(module, "SERVICES_DIR", tmp_path / "services")
    monkeypatch.setattr(module, "SEARXNG_NATIVE_REPO_DIR", repo_dir)
    monkeypatch.setattr(
        module,
        "_which",
        lambda name: f"/usr/bin/{name}" if name in {"git", "sudo"} else None,
    )
    monkeypatch.setattr(module, "_searxng_healthcheck", lambda base_url=None: next(health))

    def _fake_run(cmd, **kwargs):
        commands.append((cmd, kwargs))
        if cmd[:2] == ["/usr/bin/git", "clone"]:
            (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(module, "_run", _fake_run)

    module.setup_native_searxng(auto=True, explicit=True)

    assert commands[0][0][:7] == [
        "/usr/bin/git",
        "clone",
        "--depth",
        "1",
        "--branch",
        "master",
        "https://github.com/searxng/searxng.git",
    ]
    assert commands[0][0][7] == str(repo_dir)

    install_cmd, install_kwargs = commands[1]
    assert install_cmd[:3] == ["sudo", "-H", "env"]
    assert "FORCE_TIMEOUT=0" in install_cmd
    assert "SEARXNG_URL=http://127.0.0.1:8080" in install_cmd
    assert "SEARXNG_PORT=8080" in install_cmd
    assert "SEARXNG_BIND_ADDRESS=127.0.0.1" in install_cmd
    assert install_cmd[-3:] == ["./utils/searxng.sh", "install", "all"]
    assert install_kwargs["cwd"] == repo_dir
    assert install_kwargs["timeout"] is None


def test_setup_native_searxng_uses_wsl_on_windows(monkeypatch):
    """Windows native mode should route through WSL and still use the official script."""

    module = _load_setup_module(monkeypatch)
    commands = []
    health = iter([False, True])

    monkeypatch.setattr(module, "IS_WIN", True)
    monkeypatch.setattr(module, "IS_LINUX", False)
    monkeypatch.setattr(module, "_searxng_healthcheck", lambda base_url=None: next(health))
    monkeypatch.setattr(
        module,
        "_which",
        lambda name: "C:/Windows/System32/wsl.exe" if name in {"wsl", "wsl.exe"} else None,
    )

    def _fake_run(cmd, **kwargs):
        commands.append((cmd, kwargs))
        if cmd[:3] == ["wsl", "-l", "-q"]:
            return subprocess.CompletedProcess(cmd, 0, "Ubuntu\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(module, "_run", _fake_run)

    module.setup_native_searxng(auto=True, explicit=True)

    assert commands[0][0] == ["wsl", "-l", "-q"]
    install_cmd, install_kwargs = commands[1]
    assert install_cmd[:5] == [
        "wsl",
        "-d",
        "Ubuntu",
        "--",
        "bash",
    ]
    assert install_cmd[5] == "-lc"
    assert "./utils/searxng.sh install all" in install_cmd[6]
    assert "git clone --depth 1 --branch \"$branch\"" in install_cmd[6]
    assert install_kwargs["timeout"] is None
    assert install_kwargs["capture"] is False


def test_setup_native_searxng_windows_requires_wsl(monkeypatch):
    """Windows native mode should guide the user when WSL is unavailable."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.setattr(module, "IS_WIN", True)
    monkeypatch.setattr(module, "IS_LINUX", False)
    monkeypatch.setattr(module, "_searxng_healthcheck", lambda base_url=None: False)
    monkeypatch.setattr(module, "_which", lambda name: None)

    module.setup_native_searxng(auto=True, explicit=True)


def test_main_default_flow_calls_setup_local_searxng(monkeypatch):
    """The normal interactive installer path should still offer the SearXNG step."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.setattr(module.sys, "argv", ["setup.py"])

    called = {"value": False, "auto": None, "explicit": None}

    def _mark_called(*args, **kwargs):
        called["value"] = True
        called["auto"] = kwargs.get("auto")
        called["explicit"] = kwargs.get("explicit")

    monkeypatch.setattr(module, "_detect_china_network", lambda: False)
    monkeypatch.setattr(module, "check_python", lambda: None)
    monkeypatch.setattr(module, "ensure_python_runtime", lambda auto, allow_create=True: None)
    monkeypatch.setattr(module, "configure_ai", lambda auto: None)
    monkeypatch.setattr(module, "configure_chip", lambda auto: None)
    monkeypatch.setattr(module, "install_arm_gcc", lambda auto: None)
    monkeypatch.setattr(module, "install_python_packages", lambda auto: None)
    monkeypatch.setattr(module, "create_workspace", lambda: None)
    monkeypatch.setattr(module, "setup_local_searxng", _mark_called)
    monkeypatch.setattr(module, "download_hal", lambda auto, families=None: None)
    monkeypatch.setattr(module, "download_freertos", lambda auto: None)
    monkeypatch.setattr(module, "setup_udev", lambda auto: None)
    monkeypatch.setattr(module, "setup_pyocd", lambda auto: None)
    monkeypatch.setattr(module, "install_gary_command", lambda auto: None)
    monkeypatch.setattr(module, "verify", lambda: None)

    module.main()

    assert called["value"] is True
    assert called["auto"] is False
    assert called["explicit"] is False


def test_main_explicit_searxng_native_calls_native_setup(monkeypatch):
    """The dedicated native flag should route to the native SearXNG installer."""

    module = _load_setup_module(monkeypatch)
    monkeypatch.setattr(module.sys, "argv", ["setup.py", "--searxng-native"])

    called = {"value": False, "auto": None, "explicit": None}

    def _mark_called(*args, **kwargs):
        called["value"] = True
        called["auto"] = kwargs.get("auto")
        called["explicit"] = kwargs.get("explicit")

    monkeypatch.setattr(module, "_detect_china_network", lambda: False)
    monkeypatch.setattr(module, "create_workspace", lambda: None)
    monkeypatch.setattr(module, "setup_native_searxng", _mark_called)

    module.main()

    assert called["value"] is True
    assert called["auto"] is True
    assert called["explicit"] is True
