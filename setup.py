#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gary Dev Agent - 一键环境安装脚本
====================================
支持平台: Ubuntu/Debian · Arch/Manjaro · Fedora/RHEL · openSUSE · macOS · Windows

用法:
  python setup.py              完整安装（交互询问）
  python setup.py --auto       全自动安装，不询问（CI / 无人值守）
  python setup.py --check      仅检查环境，不安装任何东西
  python setup.py --hal        仅重新下载 STM32 HAL 库（全部系列）
  python setup.py --hal f1     仅下载 STM32F1 HAL
  python setup.py --hal f1 f4  下载 F1 + F4 HAL
  python setup.py --searxng    仅安装 / 启动本地 SearXNG
  python setup.py --searxng-native  仅用官方脚本原生安装 / 启动本地 SearXNG

安装完成后:
  gary                    启动交互式对话助手
  gary do "任务描述"      一次性执行单个任务后退出
  gary --connect          连接探针后启动
  gary --chip STM32F407VET6 --connect  指定芯片并连接

注意：本文件是自定义安装脚本，不是 setuptools 打包脚本。
      请直接用 python setup.py [选项] 运行，不要用 pip install。
"""

# ── 防止被 pip/setuptools 误调用 ──────────────────────────────────────────────
import sys as _sys

_FORBIDDEN_ARGS = {
    "egg_info",
    "bdist_wheel",
    "sdist",
    "install",
    "develop",
    "build",
    "build_ext",
    "dist_info",
    "--version",
}
if len(_sys.argv) > 1 and _sys.argv[1] in _FORBIDDEN_ARGS:
    print("错误：本文件是 Gary Dev Agent 自定义安装脚本，不是 setuptools 包。")
    print("请直接运行：  python setup.py --auto")
    print("不要使用：    pip install -e .")
    _sys.exit(2)
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
import subprocess
import platform
import shutil
import argparse
import shlex
import stat
import sysconfig
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse

# ─────────────────────────────────────────────────────────────────────────────
# Windows 控制台编码修复
# ─────────────────────────────────────────────────────────────────────────────
if platform.system() == "Windows":
    os.system("chcp 65001 > nul 2>&1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    else:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# 彩色终端输出
# ─────────────────────────────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def header(msg: str):
    print(f"\n{_c('1;35', '━' * 58)}")
    print(f"  {_c('1;35', msg)}")
    print(f"{_c('1;35', '━' * 58)}")


def ok(msg: str):
    print(f"  {_c('32', 'OK')} {msg}")


def info(msg: str):
    print(f"  {_c('36', '->')} {msg}")


def warn(msg: str):
    print(f"  {_c('33', '!!')} {msg}")


def err(msg: str):
    print(f"  {_c('31', 'XX')} {msg}")


def step(msg: str):
    print(f"\n  {_c('1;36', '>>')} {msg}")


if platform.system() != "Windows":

    def ok(msg: str):
        print(f"  {_c('32', '✓')} {msg}")

    def warn(msg: str):
        print(f"  {_c('33', '⚠')} {msg}")

    def err(msg: str):
        print(f"  {_c('31', '✗')} {msg}")

    def step(msg: str):
        print(f"\n  {_c('1;36', '▶')} {msg}")


def ask(msg: str, default: str = "y") -> bool:
    yn = "Y/n" if default == "y" else "y/N"
    try:
        ans = input(f"  {_c('33', '?')} {msg} [{yn}] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default == "y"
    return (ans in ("y", "yes")) if ans else (default == "y")


# ─────────────────────────────────────────────────────────────────────────────
# 平台 / 路径常量
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM = platform.system()
MACHINE = platform.machine()
IS_LINUX = SYSTEM == "Linux"
IS_MAC = SYSTEM == "Darwin"
IS_WIN = SYSTEM == "Windows"

SCRIPT_DIR = Path(__file__).parent.resolve()
WORKSPACE = SCRIPT_DIR / "workspace"
HAL_DIR = WORKSPACE / "hal"
BUILD_DIR = WORKSPACE / "build"
PROJECTS_DIR = WORKSPACE / "projects"
SERVICES_DIR = WORKSPACE / "services"
SEARXNG_DIR = SERVICES_DIR / "searxng"
VENV_DIR = SCRIPT_DIR / ".venv"
AGENT_SCRIPT = SCRIPT_DIR / "stm32_agent.py"

ACTIVE_PYTHON = Path(sys.executable).resolve()
ACTIVE_PYTHON_LABEL = "current"
PIP = [str(ACTIVE_PYTHON), "-m", "pip"]

# ─────────────────────────────────────────────────────────────────────────────
# 网络环境检测与镜像加速
# ─────────────────────────────────────────────────────────────────────────────
# 全局缓存，None 表示尚未检测
_IS_CHINA_NETWORK: Optional[bool] = None

# GitHub 代理（国内加速）
_GITHUB_PROXY = "https://ghfast.top/"  # 支持 github.com 归档/Release
_GITHUB_RAW_MIRROR = "https://raw.gitmirror.com/"  # 替换 raw.githubusercontent.com

# pip 国内镜像
_PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple/"

# 国内网络判定阈值（秒）：访问 GitHub 耗时超过此值视为国内
_CN_LATENCY_THRESHOLD = 3.0
# 检测超时（秒）
_CN_DETECT_TIMEOUT = 5


def _detect_china_network() -> bool:
    """
    通过同时探测 GitHub 和百度来判断是否处于国内网络。
    - 若 GitHub 在 _CN_LATENCY_THRESHOLD 秒内无法访问或延迟过高，返回 True（国内）。
    - 若 GitHub 访问正常（延迟低），返回 False（海外/VPN）。
    缓存于全局变量 _IS_CHINA_NETWORK，仅在首次调用时实际检测。
    """
    global _IS_CHINA_NETWORK
    if _IS_CHINA_NETWORK is not None:
        return _IS_CHINA_NETWORK

    import urllib.request
    import time

    print(f"\n  {_c('36', '->')} 检测网络环境（探测 GitHub 连通性）...", end=" ", flush=True)

    github_ok = False
    github_slow = True

    try:
        t0 = time.time()
        req = urllib.request.Request(
            "https://github.com",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=_CN_DETECT_TIMEOUT):
            elapsed = time.time() - t0
            github_ok = True
            github_slow = elapsed > _CN_LATENCY_THRESHOLD
    except Exception:
        github_ok = False
        github_slow = True

    _IS_CHINA_NETWORK = (not github_ok) or github_slow

    if _IS_CHINA_NETWORK:
        print(_c("33", "国内网络，启用镜像加速"))
    else:
        print(_c("32", "海外网络，直连 GitHub"))

    return _IS_CHINA_NETWORK


def _mirror_url(url: str) -> str:
    """
    根据网络环境将下载 URL 转换为镜像地址。
    仅在检测到国内网络时生效，海外网络直接返回原始 URL。
    支持：
      - https://github.com/...         → ghfast.top 代理
      - https://raw.githubusercontent.com/... → raw.gitmirror.com
    其他 URL（如 ARM 官网）保持不变。
    """
    if not _detect_china_network():
        return url  # 海外网络：原始地址

    # raw.githubusercontent.com → raw.gitmirror.com
    if url.startswith("https://raw.githubusercontent.com/"):
        mirrored = url.replace(
            "https://raw.githubusercontent.com/",
            _GITHUB_RAW_MIRROR,
            1,
        )
        return mirrored

    # github.com 归档 / Release → ghfast.top 前缀代理
    if url.startswith("https://github.com/"):
        return _GITHUB_PROXY + url

    return url  # 其他地址（ARM 官网等）不处理


def _pip_mirror_args() -> List[str]:
    """
    若处于国内网络，返回 pip 镜像参数列表；否则返回空列表。
    示例: ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple/",
           "--trusted-host", "pypi.tuna.tsinghua.edu.cn"]
    """
    if not _detect_china_network():
        return []
    host = _PIP_MIRROR.split("/")[2]  # 取域名
    return ["-i", _PIP_MIRROR, "--trusted-host", host]


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────
def _run(
    cmd, shell=False, capture=True, input_text=None, timeout=None, **kw
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            shell=shell,
            capture_output=capture,
            text=True,
            input=input_text,
            timeout=timeout,
            **kw,
        )
    except subprocess.TimeoutExpired:
        cmd_name = cmd[0] if isinstance(cmd, list) else str(cmd)
        warn(f"命令超时（>{timeout}s）: {cmd_name}")
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="timeout")
    except FileNotFoundError:
        cmd_name = cmd[0] if isinstance(cmd, list) else str(cmd)
        return subprocess.CompletedProcess(
            cmd, returncode=1, stdout="", stderr=f"{cmd_name}: not found"
        )


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _python_cmd(*args: str, python: Path | str | None = None) -> list[str]:
    target = Path(python or ACTIVE_PYTHON).expanduser()
    return [str(target), *args]


def _active_python_path() -> Path:
    return Path(ACTIVE_PYTHON).expanduser().resolve()


def _set_active_python(python_path: Path | str, label: str) -> Path:
    global ACTIVE_PYTHON, ACTIVE_PYTHON_LABEL, PIP

    resolved = Path(python_path).expanduser().resolve()
    ACTIVE_PYTHON = resolved
    ACTIVE_PYTHON_LABEL = label
    PIP = [str(resolved), "-m", "pip"]
    return resolved


def _venv_python_path(venv_dir: Path | None = None) -> Path:
    root = Path(venv_dir or VENV_DIR)
    return root / ("Scripts/python.exe" if IS_WIN else "bin/python")


def _inside_virtualenv() -> bool:
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    return bool(os.environ.get("VIRTUAL_ENV")) or sys.prefix != base_prefix


def _externally_managed_marker() -> Path | None:
    stdlib = sysconfig.get_path("stdlib")
    if not stdlib:
        return None
    return Path(stdlib) / "EXTERNALLY-MANAGED"


def _is_externally_managed_python() -> bool:
    if _inside_virtualenv():
        return False
    marker = _externally_managed_marker()
    return bool(marker and marker.exists())


def _python_module_available(module: str, python: Path | str | None = None) -> bool:
    code = "import importlib,sys; importlib.import_module(sys.argv[1])"
    result = _run(_python_cmd("-c", code, module, python=python), timeout=30)
    return result.returncode == 0


def _python_module_version(module: str, python: Path | str | None = None) -> str:
    code = (
        "import importlib,sys;"
        "mod=importlib.import_module(sys.argv[1]);"
        "print(getattr(mod,'__version__',''))"
    )
    result = _run(_python_cmd("-c", code, module, python=python), timeout=30)
    return result.stdout.strip() if result.returncode == 0 else ""


def _distro() -> tuple:
    try:
        d = {}
        for line in Path("/etc/os-release").read_text(errors="ignore").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                d[k.strip()] = v.strip().strip('"')
        return d.get("ID", "").lower(), d.get("ID_LIKE", "").lower()
    except Exception:
        return "", ""


def _download(url: str, dest: Path, label: str = "", retries: int = 3) -> bool:
    """
    下载文件到 dest。
    自动根据网络环境将 URL 转换为镜像地址（_mirror_url），
    若镜像下载失败则自动回退到原始地址重试。
    """
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)

    mirrored_url = _mirror_url(url)
    # 构造尝试列表：镜像优先，失败后回退原始地址
    urls_to_try: List[tuple] = []
    if mirrored_url != url:
        urls_to_try.append((mirrored_url, "[镜像]"))
        urls_to_try.append((url, "[原始]"))
    else:
        urls_to_try.append((url, ""))

    for try_url, tag in urls_to_try:
        tag_label = f"{label}{tag}" if tag else label
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(try_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    with open(dest, "wb") as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total and tag_label:
                                pct = min(downloaded * 100 // total, 100)
                                bar = "#" * (pct // 5) + "." * (20 - pct // 5)
                                print(
                                    f"\r    [{bar}] {pct:3d}%  {tag_label[:40]}",
                                    end="",
                                    flush=True,
                                )
                if tag_label:
                    print()
                return True  # 下载成功
            except Exception as e:
                if tag_label:
                    print()
                dest.unlink(missing_ok=True)
                if attempt < retries:
                    warn(f"下载失败（第 {attempt}/{retries} 次），重试中... [{tag_label}]: {e}")
                else:
                    warn(f"地址 {tag} 下载失败（已重试 {retries} 次）[{label}]: {e}")
        # 当前 URL 全部重试失败，尝试下一个地址（若有）

    err(f"所有下载地址均失败: {label}")
    return False


def _detect_zip_prefix(zip_path: Path) -> str:
    import zipfile

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if names:
                return names[0].split("/")[0]
    except Exception:
        pass
    return ""


def _extract_zip(zip_path: Path, dest_dir: Path, sub_paths: List[str]) -> bool:
    import zipfile, shutil as _sh

    try:
        prefix = _detect_zip_prefix(zip_path)
        if not prefix:
            err(f"无法检测 zip 前缀: {zip_path.name}")
            return False
        with zipfile.ZipFile(zip_path, "r") as zf:
            for sub in sub_paths:
                src_prefix = f"{prefix}/{sub}/"
                for member in zf.namelist():
                    if not member.startswith(src_prefix):
                        continue
                    rel = member[len(src_prefix) :]
                    if not rel or rel.endswith("/"):
                        continue
                    fname = Path(rel).name
                    if not fname:
                        continue
                    target = dest_dir / fname
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        _sh.copyfileobj(src, dst)
        return True
    except Exception as e:
        err(f"解压失败 {zip_path.name}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 0: AI 接口配置
# ─────────────────────────────────────────────────────────────────────────────
_AI_PRESETS = [
    ("OpenAI", "https://api.openai.com/v1", "gpt-4o", "openai"),
    ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat", "openai"),
    ("Kimi / Moonshot", "https://api.moonshot.cn/v1", "kimi-k2.5", "openai"),
    (
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta",
        "gemini-2.5-flash",
        "gemini",
    ),
    (
        "通义千问 (阿里云)",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
        "openai",
    ),
    ("智谱 GLM", "https://open.bigmodel.cn/api/paas/v4/", "glm-4-flash", "openai"),
    ("Ollama (本地无需Key)", "http://127.0.0.1:11434/v1", "qwen2.5-coder:14b", "openai"),
    ("自定义 / Other", "", "", ""),
]
_API_STYLE_OPTIONS = [
    ("openai", "OpenAI Compatible", "兼容 /v1/chat/completions 等 OpenAI 风格接口"),
    ("anthropic", "Anthropic Messages", "兼容 /v1/messages 的 Anthropic / Claude 风格接口"),
    ("gemini", "Gemini Official SDK", "Google Gemini 官方 SDK / generativelanguage.googleapis.com"),
]


def _normalize_api_style(value: str, default: str = "") -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "openai": "openai",
        "openai-compatible": "openai",
        "compatible": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "messages": "anthropic",
        "gemini": "gemini",
        "google": "gemini",
        "google-gemini": "gemini",
    }
    return aliases.get(raw, default)


def _provider_label(api_style: str) -> str:
    normalized = _normalize_api_style(api_style, "openai")
    if normalized == "gemini":
        return "Google Gemini (official SDK)"
    if normalized == "anthropic":
        return "Anthropic Messages API"
    return "OpenAI-compatible"


def _read_current_ai_config() -> tuple:
    import re as _re

    p = SCRIPT_DIR / "config.py"
    if not p.exists():
        return "", "", "", ""
    text = p.read_text(encoding="utf-8")

    def _get(pattern):
        m = _re.search(pattern, text, _re.MULTILINE)
        return m.group(1).strip() if m else ""

    return (
        _get(r'^AI_API_KEY\s*=\s*["\']([^"\']*)["\']'),
        _get(r'^AI_BASE_URL\s*=\s*["\']([^"\']*)["\']'),
        _get(r'^AI_MODEL\s*=\s*["\']([^"\']*)["\']'),
        _normalize_api_style(_get(r'^AI_API_STYLE\s*=\s*["\']([^"\']*)["\']')),
    )


def _write_ai_config(api_key: str, base_url: str, model: str, api_style: str) -> bool:
    import re as _re

    p = SCRIPT_DIR / "config.py"
    if not p.exists():
        p.write_text(
            'AI_API_KEY = ""\nAI_BASE_URL = ""\nAI_MODEL = ""\nAI_API_STYLE = ""\n',
            encoding="utf-8",
        )
    text = p.read_text(encoding="utf-8")
    for key, val in [
        ("AI_API_KEY", api_key),
        ("AI_BASE_URL", base_url),
        ("AI_MODEL", model),
        ("AI_API_STYLE", _normalize_api_style(api_style)),
    ]:
        pattern = rf"^({key}\s*=\s*).*$"
        if _re.search(pattern, text, flags=_re.MULTILINE):
            text = _re.sub(pattern, f'{key} = "{val}"', text, flags=_re.MULTILINE)
        else:
            text += f'\n{key} = "{val}"'
    try:
        p.write_text(text, encoding="utf-8")
        return True
    except Exception as e:
        print(f"写入失败: {e}")
        return False


def _mask_key(key: str) -> str:
    if not key:
        return "(未设置)"
    if len(key) <= 12:
        return "***"
    return key[:6] + "..." + key[-4:]


def configure_ai(auto: bool):
    import getpass as _gp

    header("配置  AI 后端接口")
    cur_key, cur_url, cur_model, cur_style = _read_current_ai_config()
    placeholder = ("YOUR_API_KEY", "sk-YOUR")
    is_configured = bool(cur_key and not any(cur_key.startswith(p) for p in placeholder))

    if is_configured:
        ok(f"API Key  : {_mask_key(cur_key)}")
        ok(f"Interface : {_provider_label(cur_style)}")
        ok(f"Base URL : {cur_url}")
        ok(f"Model    : {cur_model}")
        if auto:
            return
        if not ask("重新配置 AI 接口？", default="n"):
            return

    print()
    print(f"  {_c('1;36', '请选择 AI 服务提供商：')}")
    for i, (name, url, _, style) in enumerate(_AI_PRESETS, 1):
        url_hint = _c("2", f"  {url[:52]}") if url else ""
        print(f"    {_c('33', str(i))}.  {name:<24}{_c('2', _provider_label(style))}{url_hint}")
    print()

    choice = ""
    valid = [str(i) for i in range(1, len(_AI_PRESETS) + 1)]
    while choice not in valid:
        try:
            choice = input(f"  {_c('33', '?')} 输入序号 [1-{len(_AI_PRESETS)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            warn("已跳过 AI 配置，请稍后手动修改 config.py")
            return
        if not choice and is_configured:
            return

    idx = int(choice) - 1
    preset_name, preset_url, preset_model, preset_style = _AI_PRESETS[idx]

    api_style = _normalize_api_style(preset_style, "openai")
    if not preset_url:
        print(f"  {_c('1;36', '请选择接口协议类型：')}")
        for i, (_, label, desc) in enumerate(_API_STYLE_OPTIONS, 1):
            print(f"    {_c('33', str(i))}.  {label:<24}{_c('2', desc)}")
        print()
        style_choice = ""
        style_valid = [str(i) for i in range(1, len(_API_STYLE_OPTIONS) + 1)]
        while style_choice not in style_valid:
            try:
                style_choice = input(
                    f"  {_c('33', '?')} 输入协议类型 [1-{len(_API_STYLE_OPTIONS)}]: "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                warn("已跳过 AI 配置，请稍后手动修改 config.py")
                return
            if not style_choice and is_configured:
                return
        api_style = _API_STYLE_OPTIONS[int(style_choice) - 1][0]

    if preset_url:
        base_url = preset_url
    else:
        default_base_urls = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
        }
        example = default_base_urls.get(api_style, "https://api.openai.com/v1")
        entered = input(f"  {_c('33', '?')} Base URL (例: {example}): ").strip()
        base_url = entered or (cur_url if cur_url and cur_style == api_style else example)

    default_models = {
        "openai": "gpt-4o",
        "anthropic": "claude-3-7-sonnet-latest",
        "gemini": "gemini-2.5-flash",
    }
    current_model_for_style = cur_model if cur_style == api_style else ""
    default_model = (
        preset_model
        if preset_model
        else (
            current_model_for_style
            if current_model_for_style
            else default_models.get(api_style, "gpt-4o")
        )
    )
    hint = f" [{_c('36', default_model)}]"

    entered = input(f"  {_c('33', '?')} Model 名称{hint} (回车使用默认): ").strip()
    model = entered if entered else default_model

    print()
    if preset_name == "Ollama (本地无需Key)":
        api_key = "ollama"
        info("Ollama 本地模式，API Key 自动设为 ollama")
    else:
        info(f"请输入 {preset_name} API Key")
        try:
            api_key = _gp.getpass(f"  {_c('33', '?')} API Key (不回显): ")
        except Exception:
            api_key = input(f"  {_c('33', '?')} API Key: ").strip()
        if not api_key:
            if cur_key and is_configured:
                warn("未输入，保留原有 API Key")
                api_key = cur_key
            else:
                warn("未输入 API Key，请稍后手动修改 config.py")
                return

    if _write_ai_config(api_key, base_url, model, api_style):
        print()
        ok(f"AI 配置已写入 config.py")
        ok(f"  服务商 : {preset_name}")
        ok(f"  接口类型: {_provider_label(api_style)}")
        ok(f"  API Key: {_mask_key(api_key)}")
        ok(f"  Base URL: {base_url}")
        ok(f"  Model  : {model}")
    else:
        err("写入 config.py 失败")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 0b: 目标芯片配置
# ─────────────────────────────────────────────────────────────────────────────

# (显示名, pyocd pack 代表芯片, 系列描述)
_CHIP_PRESETS = [
    ("STM32F103C8", "stm32f103c8", "Blue Pill / 蓝板"),
    ("STM32F411CEU", "stm32f411ce", "Black Pill / 黑板"),
    ("STM32F407VE", "stm32f407ve", "F407 Discovery"),
    ("STM32F401CC", "stm32f401cc", "F401 Black Pill"),
    ("STM32F030C8", "stm32f030c8", "F0xx 入门系列"),
    ("STM32F303CC", "stm32f303cc", "F3xx DSP/FPU 系列"),
    ("自定义", "", "手动输入"),
]

# 芯片系列 → pyocd pack 代表芯片（用于 pack install 和已装检测）
_FAMILY_PACK_TARGET = {
    "f0": "stm32f030c8",
    "f1": "stm32f103c8",
    "f3": "stm32f303cc",
    "f4": "stm32f411ce",
}


def _detect_chip_family(chip: str) -> str:
    """从芯片型号推断系列，例如 STM32F411CEU6 → f4"""
    import re as _re

    m = _re.search(r"stm32(f\d)", chip.lower())
    return m.group(1) if m else ""


def _read_default_chip() -> str:
    import re as _re

    p = SCRIPT_DIR / "config.py"
    if not p.exists():
        return ""
    m = _re.search(
        r'^DEFAULT_CHIP\s*=\s*["\']([^"\']*)["\']', p.read_text(encoding="utf-8"), _re.MULTILINE
    )
    return m.group(1).strip() if m else ""


def _write_default_chip(chip: str) -> bool:
    import re as _re

    p = SCRIPT_DIR / "config.py"
    if not p.exists():
        return False
    text = p.read_text(encoding="utf-8")
    pattern = r"^(DEFAULT_CHIP\s*=\s*).*$"
    if _re.search(pattern, text, _re.MULTILINE):
        text = _re.sub(pattern, f'DEFAULT_CHIP = "{chip}"', text, flags=_re.MULTILINE)
    else:
        text += f'\nDEFAULT_CHIP = "{chip}"\n'
    p.write_text(text, encoding="utf-8")
    return True


def configure_chip(auto: bool):
    header("Step 0b  目标芯片配置")
    cur = _read_default_chip()
    if cur:
        ok(f"当前芯片: {cur}")
        if auto or not ask("重新选择目标芯片？", default="n"):
            return
    elif auto:
        warn("未配置目标芯片，pyocd 将以通用 Cortex-M 模式运行（可用 /chip 命令后续切换）")
        return

    print(f"\n  {_c('1;36', '请选择目标芯片：')}")
    for i, (name, _, desc) in enumerate(_CHIP_PRESETS, 1):
        print(f"    {_c('33', str(i))}.  {name:<18}{_c('2', desc)}")
    print()

    choice = ""
    valid = [str(i) for i in range(1, len(_CHIP_PRESETS) + 1)]
    while choice not in valid:
        try:
            choice = input(
                f"  {_c('33', '?')} 输入序号 [1-{len(_CHIP_PRESETS)}，回车跳过]: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            warn("已跳过芯片配置，可后续用 /chip 命令切换")
            return
        if not choice:
            warn("已跳过芯片配置，可后续用 /chip 命令切换")
            return

    idx = int(choice) - 1
    chip_name, _, _ = _CHIP_PRESETS[idx]
    if chip_name == "自定义":
        try:
            chip_name = (
                input(f"  {_c('33', '?')} 输入芯片型号（如 STM32F411CEU6）: ").strip().upper()
            )
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not chip_name:
            return

    if _write_default_chip(chip_name):
        ok(f"目标芯片已写入 config.py: {chip_name}")
    else:
        warn("写入失败，请手动修改 config.py 中的 DEFAULT_CHIP")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Python 版本
# ─────────────────────────────────────────────────────────────────────────────
def check_python():
    header("Step 1  Python 版本")
    v = sys.version_info
    if v < (3, 8):
        err(f"需要 Python >= 3.8，当前 {v.major}.{v.minor}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}  ({sys.executable})")


def ensure_python_runtime(auto: bool, allow_create: bool = True) -> Path:
    header("Step 1b  Python 包安装环境")

    if _inside_virtualenv():
        active = _set_active_python(sys.executable, "venv")
        ok(f"当前已在虚拟环境中: {active}")
        return active

    venv_python = _venv_python_path()
    if venv_python.exists():
        active = _set_active_python(venv_python, "project_venv")
        ok(f"复用项目虚拟环境: {active}")
        return active

    if not _is_externally_managed_python():
        active = _set_active_python(sys.executable, "system")
        ok(f"当前解释器可直接安装 Python 包: {active}")
        return active

    warn("检测到 PEP 668 externally-managed-environment")
    marker = _externally_managed_marker()
    if marker:
        info(f"系统 Python 受发行版管理: {marker}")

    if not allow_create:
        info(f"安装阶段会自动创建项目虚拟环境: {VENV_DIR}")
        info("这样可以避免使用 --break-system-packages 污染系统 Python")
        return _set_active_python(sys.executable, "system_managed")

    info(f"自动创建项目虚拟环境: {VENV_DIR}")
    result = _run([sys.executable, "-m", "venv", str(VENV_DIR)], capture=False, timeout=300)
    if result.returncode != 0:
        err("创建项目虚拟环境失败，无法继续安装 Python 依赖")
        if IS_LINUX:
            info("Debian / Ubuntu 可先安装: sudo apt install python3-venv python3-full")
        sys.exit(1)

    venv_python = _venv_python_path()
    if not venv_python.exists():
        err(f"虚拟环境已创建，但未找到解释器: {venv_python}")
        sys.exit(1)

    active = _set_active_python(venv_python, "project_venv")
    ok(f"后续 Python 依赖将安装到项目虚拟环境: {active}")
    return active


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: arm-none-eabi 工具链
# ─────────────────────────────────────────────────────────────────────────────
def _gcc_ver(gcc: str = "arm-none-eabi-gcc") -> str:
    try:
        r = _run([gcc, "--version"])
        if r.returncode == 0:
            return r.stdout.split("\n")[0].strip()
    except Exception:
        pass
    return ""


def install_arm_gcc(auto: bool):
    header("Step 2  ARM 交叉编译工具链")
    ver = _gcc_ver()
    if ver:
        ok(f"已安装: {ver}")
        return
    warn("未检测到 arm-none-eabi-gcc")
    if IS_LINUX:
        _arm_gcc_linux(auto)
    elif IS_MAC:
        _arm_gcc_mac(auto)
    elif IS_WIN:
        _arm_gcc_win(auto)
    else:
        warn(f"未知平台 {SYSTEM}，请手动安装")
    ver2 = _gcc_ver()
    if ver2:
        ok(f"安装成功: {ver2}")
    else:
        warn("安装后仍未找到，请重新打开终端再试（PATH 可能尚未生效）")


def _arm_gcc_linux(auto: bool):
    dist_id, dist_like = _distro()
    is_deb = (
        dist_id in ("ubuntu", "debian", "linuxmint", "pop", "elementary", "raspbian")
        or "debian" in dist_like
        or "ubuntu" in dist_like
    )
    is_arch = dist_id in ("arch", "manjaro", "endeavouros", "artix") or "arch" in dist_like
    is_rpm = (
        dist_id in ("fedora", "rhel", "centos", "rocky", "almalinux")
        or "fedora" in dist_like
        or "rhel" in dist_like
    )
    is_suse = "suse" in dist_id or "suse" in dist_like
    if is_deb:
        if auto or ask("使用 apt 安装 gcc-arm-none-eabi？"):
            _run(["sudo", "apt-get", "update", "-qq"], capture=False)
            r = _run(
                ["sudo", "apt-get", "install", "-y", "gcc-arm-none-eabi", "binutils-arm-none-eabi"],
                capture=False,
            )
            if r.returncode != 0:
                warn("apt 失败，改为下载预编译包...")
                _arm_gcc_download(auto)
    elif is_arch:
        if auto or ask("使用 pacman 安装？"):
            _run(
                [
                    "sudo",
                    "pacman",
                    "-S",
                    "--noconfirm",
                    "arm-none-eabi-gcc",
                    "arm-none-eabi-binutils",
                ],
                capture=False,
            )
    elif is_rpm:
        pm = "dnf" if _which("dnf") else "yum"
        if auto or ask(f"使用 {pm} 安装？"):
            _run(
                ["sudo", pm, "install", "-y", "arm-none-eabi-gcc-cs", "arm-none-eabi-binutils-cs"],
                capture=False,
            )
    elif is_suse:
        if auto or ask("使用 zypper 安装？"):
            _run(
                [
                    "sudo",
                    "zypper",
                    "install",
                    "-y",
                    "cross-arm-none-eabi-gcc",
                    "cross-arm-none-eabi-binutils",
                ],
                capture=False,
            )
    else:
        _arm_gcc_download(auto)


def _arm_gcc_mac(auto: bool):
    if _which("brew"):
        if auto or ask("使用 Homebrew 安装 arm-none-eabi-gcc？"):
            # 国内网络给 Homebrew 设置镜像环境变量
            brew_env = os.environ.copy()
            if _detect_china_network():
                brew_env["HOMEBREW_BREW_GIT_REMOTE"] = (
                    "https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/brew.git"
                )
                brew_env["HOMEBREW_CORE_GIT_REMOTE"] = (
                    "https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-core.git"
                )
                brew_env["HOMEBREW_BOTTLE_DOMAIN"] = (
                    "https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles"
                )
                info("国内网络：Homebrew 已切换清华镜像源")
            _run(["brew", "install", "arm-none-eabi-gcc"], capture=False, env=brew_env)
    else:
        warn("未检测到 Homebrew")
        if auto or ask("先安装 Homebrew 再装工具链？"):
            _run(
                [
                    "/bin/bash",
                    "-c",
                    '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
                ],
                capture=False,
            )
            _run(["brew", "install", "arm-none-eabi-gcc"], capture=False)
        else:
            _arm_gcc_download(auto)


def _arm_gcc_win(auto: bool):
    if _which("winget"):
        if auto or ask("使用 winget 安装 Arm GNU Toolchain？"):
            _run(
                [
                    "winget",
                    "install",
                    "--id",
                    "Arm.GnuArmEmbeddedToolchain",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ],
                capture=False,
            )
        return
    if _which("choco"):
        if auto or ask("使用 Chocolatey 安装？"):
            _run(["choco", "install", "gcc-arm-embedded", "-y"], capture=False)
        return
    _arm_gcc_download(auto)


def _arm_gcc_download(auto: bool):
    URLS = {
        (
            "linux",
            "x86_64",
        ): "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-x86_64-arm-none-eabi.tar.xz",
        (
            "linux",
            "aarch64",
        ): "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-aarch64-arm-none-eabi.tar.xz",
        (
            "darwin",
            "x86_64",
        ): "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-darwin-x86_64-arm-none-eabi.tar.xz",
        (
            "darwin",
            "arm64",
        ): "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-darwin-arm64-arm-none-eabi.tar.xz",
        (
            "windows",
            "x86_64",
        ): "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-mingw-w64-i686-arm-none-eabi.zip",
    }
    sys_k = SYSTEM.lower()
    arch_k = (
        "arm64"
        if MACHINE.lower() == "arm64"
        else "aarch64" if "aarch" in MACHINE.lower() else "x86_64"
    )
    url = URLS.get((sys_k, arch_k))
    if not url:
        warn("没有适合此平台的预编译包")
        info("  https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads")
        return
    install_dir = Path("C:/arm-toolchain") if IS_WIN else Path("/opt/arm-toolchain")
    if not (auto or ask(f"从 ARM 官网下载安装到 {install_dir}（约 120 MB）？")):
        info("已跳过，请手动安装")
        return
    import tempfile, tarfile, zipfile

    tmp = Path(tempfile.mkdtemp())
    fmt = "zip" if url.endswith(".zip") else "tar.xz"
    archive = tmp / f"arm-toolchain.{fmt}"
    # ARM 官网 URL 不走 GitHub 代理，直接下载（_download 内部对非 github.com 地址不转换）
    if not _download(url, archive, "arm-gnu-toolchain"):
        return
    info(f"解压到 {install_dir} ...")
    try:
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "tar.xz":
            with tarfile.open(archive, "r:xz") as tf:
                tf.extractall(install_dir.parent)
            extracted = [
                d
                for d in install_dir.parent.iterdir()
                if d.is_dir() and "arm-gnu-toolchain" in d.name
            ]
            if extracted:
                if install_dir.exists():
                    shutil.rmtree(install_dir)
                extracted[0].rename(install_dir)
        else:
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(install_dir.parent)
    except Exception as e:
        err(f"解压失败: {e}")
        return
    bin_dir = install_dir / "bin"
    if bin_dir.exists():
        _add_to_path(str(bin_dir))
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        ok(f"工具链已安装：{install_dir}")
    shutil.rmtree(tmp, ignore_errors=True)


def _add_to_path(new_path: str):
    home = Path.home()
    candidates = (
        [home / ".zshrc", home / ".bash_profile"] if IS_MAC else [home / ".bashrc", home / ".zshrc"]
    )
    line = f'\nexport PATH="{new_path}:$PATH"  # arm-none-eabi\n'
    for sh in candidates:
        if sh.exists():
            if new_path not in sh.read_text():
                with sh.open("a") as f:
                    f.write(line)
            info(f"  PATH 已写入 {sh}")
            return


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Python 依赖包
# ─────────────────────────────────────────────────────────────────────────────
PYTHON_PKGS = [
    ("openai", "openai", True),
    ("google.genai", "google-genai", True),
    ("rich", "rich", True),
    ("prompt_toolkit", "prompt_toolkit", True),
    ("pyocd", "pyocd", True),
    ("serial", "pyserial", True),
    ("requests", "requests", True),
    ("bs4", "beautifulsoup4", True),
    ("docx", "python-docx", False),
    ("PIL", "Pillow", True),
]


def install_python_packages(auto: bool):
    header("Step 3  Python 依赖包")
    info(f"目标 Python 环境: {_active_python_path()} [{ACTIVE_PYTHON_LABEL}]")

    mirror_args = _pip_mirror_args()
    if mirror_args:
        info(f"pip 使用国内镜像: {_PIP_MIRROR}")

    _run(PIP + ["install", "--upgrade", "pip", "-q"] + mirror_args, capture=False)

    missing_req, missing_opt = [], []
    for imp, pkg, required in PYTHON_PKGS:
        try:
            available = _python_module_available(imp)
        except Exception:
            available = False
        if available:
            ok(f"{pkg}")
        else:
            (missing_req if required else missing_opt).append(pkg)
            warn(f"{pkg}  {'[必须]' if required else '[可选]'}")
    to_install = missing_req + missing_opt
    if not to_install:
        ok("所有依赖已就绪")
        return
    prompt = f"安装 {len(missing_req)} 个必需包"
    if missing_opt:
        prompt += f" + {len(missing_opt)} 个可选包"
    if auto or ask(prompt + "？"):
        r = _run(PIP + ["install"] + to_install + mirror_args, capture=False)
        if r.returncode != 0:
            warn("批量安装失败，逐个安装...")
            for pkg in to_install:
                _run(PIP + ["install", pkg] + mirror_args, capture=False)
    elif missing_req:
        info(f"必须包未安装：{missing_req}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3b: 本地 SearXNG（网页搜索）
# ─────────────────────────────────────────────────────────────────────────────
SEARXNG_DEFAULT_URL = "http://127.0.0.1:8080"
SEARXNG_DEFAULT_IMAGE = "searxng/searxng:latest"
SEARXNG_DEFAULT_CONTAINER = "gary-searxng"
SEARXNG_DEFAULT_GIT_URL = "https://github.com/searxng/searxng.git"
SEARXNG_DEFAULT_GIT_BRANCH = "master"
SEARXNG_NATIVE_REPO_DIR = SEARXNG_DIR / "native-src"
SEARXNG_DEFAULT_WSL_DISTRO = "Ubuntu"
SEARXNG_DEFAULT_WSL_REPO_DIR = "~/.garycli/searxng"
WINDOWS_DOCKER_DESKTOP_PACKAGE = "Docker.DockerDesktop"


def _searxng_url() -> str:
    value = (os.environ.get("GARY_SEARXNG_URL") or SEARXNG_DEFAULT_URL).strip()
    return value.rstrip("/") or SEARXNG_DEFAULT_URL


def _searxng_image() -> str:
    value = (os.environ.get("GARY_SEARXNG_IMAGE") or SEARXNG_DEFAULT_IMAGE).strip()
    return value or SEARXNG_DEFAULT_IMAGE


def _searxng_container_name() -> str:
    value = (os.environ.get("GARY_SEARXNG_CONTAINER") or SEARXNG_DEFAULT_CONTAINER).strip()
    return value or SEARXNG_DEFAULT_CONTAINER


def _searxng_git_url() -> str:
    value = (os.environ.get("GARY_SEARXNG_GIT_URL") or SEARXNG_DEFAULT_GIT_URL).strip()
    return value or SEARXNG_DEFAULT_GIT_URL


def _searxng_git_branch() -> str:
    value = (os.environ.get("GARY_SEARXNG_GIT_BRANCH") or SEARXNG_DEFAULT_GIT_BRANCH).strip()
    return value or SEARXNG_DEFAULT_GIT_BRANCH


def _searxng_host_port() -> tuple[str, int]:
    parsed = urlparse(_searxng_url())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8080
    return host, port


def _searxng_wsl_distro() -> str:
    value = (os.environ.get("GARY_SEARXNG_WSL_DISTRO") or SEARXNG_DEFAULT_WSL_DISTRO).strip()
    return value or SEARXNG_DEFAULT_WSL_DISTRO


def _searxng_wsl_repo_dir() -> str:
    value = (os.environ.get("GARY_SEARXNG_WSL_REPO_DIR") or SEARXNG_DEFAULT_WSL_REPO_DIR).strip()
    return value or SEARXNG_DEFAULT_WSL_REPO_DIR


def _container_runtime() -> Optional[str]:
    if IS_WIN:
        _refresh_windows_docker_cli()
    for candidate in ("docker", "podman"):
        if _which(candidate):
            return candidate
    return None


def _wsl_runtime() -> Optional[str]:
    for candidate in ("wsl", "wsl.exe"):
        if _which(candidate):
            return candidate
    return None


def _prepend_process_path(path: Path | str):
    target = str(Path(path))
    current = os.environ.get("PATH", "")
    parts = [part for part in current.split(os.pathsep) if part]
    if target not in parts:
        os.environ["PATH"] = target + (os.pathsep + current if current else "")


def _windows_docker_cli_dir() -> Optional[Path]:
    candidates = []
    for env_name in ("ProgramFiles", "ProgramW6432"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "Docker" / "Docker" / "resources" / "bin")
    candidates.append(Path("C:/Program Files/Docker/Docker/resources/bin"))
    for candidate in candidates:
        if (candidate / "docker.exe").exists():
            return candidate
    return None


def _docker_desktop_exe_path() -> Optional[Path]:
    candidates = []
    for env_name in ("ProgramFiles", "ProgramW6432"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "Docker" / "Docker" / "Docker Desktop.exe")
    candidates.append(Path("C:/Program Files/Docker/Docker/Docker Desktop.exe"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _refresh_windows_docker_cli() -> Optional[str]:
    docker = _which("docker")
    if docker:
        return docker
    if not IS_WIN:
        return None
    cli_dir = _windows_docker_cli_dir()
    if cli_dir:
        _prepend_process_path(cli_dir)
        return _which("docker")
    return None


def _wait_for_container_runtime_ready(runtime: str, timeout_seconds: int = 180) -> bool:
    import time

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = _run([runtime, "info"], timeout=15)
        if result.returncode == 0:
            return True
        time.sleep(5)
    return False


def _install_windows_wsl_distribution() -> bool:
    runtime = _wsl_runtime()
    if not runtime:
        warn("未找到 wsl.exe，无法自动准备 Docker Desktop 依赖的 WSL 环境")
        info("请先在管理员 PowerShell 中执行: wsl --install -d Ubuntu")
        return False

    distros = _list_wsl_distros(runtime)
    if distros:
        ok(f"已检测到 WSL 发行版: {distros[0]}")
        return True

    distro = _searxng_wsl_distro()
    step(f"自动安装 WSL 发行版: {distro}")
    result = _run([runtime, "--install", "-d", distro], capture=False, timeout=None)
    if result.returncode != 0:
        warn("WSL 安装命令执行失败")
        info(f"请在管理员 PowerShell 中重试: {runtime} --install -d {distro}")
        return False

    warn("WSL 已开始安装，通常需要重启或重新登录后再继续安装 Docker Desktop / SearXNG")
    return False


def _ensure_windows_docker_desktop(auto: bool, *, explicit: bool = False) -> Optional[str]:
    docker = _refresh_windows_docker_cli()
    if docker and _wait_for_container_runtime_ready("docker", timeout_seconds=10):
        ok("Docker Desktop 已可用")
        return "docker"

    if not IS_WIN:
        return None

    if not _install_windows_wsl_distribution():
        return None

    if not (
        auto or explicit or ask("未找到 Docker Desktop，是否现在自动安装并启动？", default="y")
    ):
        info("已跳过 Docker Desktop 自动安装")
        return None

    winget = _which("winget")
    choco = _which("choco")
    if winget:
        step("使用 winget 安装 Docker Desktop")
        install_cmd = [
            winget,
            "install",
            "-e",
            "--id",
            WINDOWS_DOCKER_DESKTOP_PACKAGE,
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
    elif choco:
        step("使用 Chocolatey 安装 Docker Desktop")
        install_cmd = [choco, "install", "docker-desktop", "-y"]
    else:
        warn("未找到 winget / choco，无法自动安装 Docker Desktop")
        info(
            "请先手动安装 Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/"
        )
        return None

    result = _run(install_cmd, capture=False, timeout=None)
    if result.returncode != 0:
        warn("Docker Desktop 安装失败")
        return None

    docker = _refresh_windows_docker_cli()
    desktop_exe = _docker_desktop_exe_path()
    if desktop_exe:
        step("启动 Docker Desktop")
        _run([str(desktop_exe)], capture=False, timeout=30)
    else:
        warn("未找到 Docker Desktop.exe，可能需要用户手动首次启动一次")

    if docker and _wait_for_container_runtime_ready("docker", timeout_seconds=240):
        ok("Docker Desktop 已启动并可用")
        return "docker"

    warn("Docker Desktop 已安装，但 Docker 引擎尚未就绪")
    info("请完成 Docker Desktop 的首次初始化后，再重新执行：python setup.py --searxng")
    return None


def _container_exists(runtime: str, name: str) -> bool:
    return _run([runtime, "inspect", name], timeout=15).returncode == 0


def _container_running(runtime: str, name: str) -> bool:
    result = _run([runtime, "inspect", "-f", "{{.State.Running}}", name], timeout=15)
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def _container_image_present(runtime: str, image: str) -> bool:
    return _run([runtime, "image", "inspect", image], timeout=30).returncode == 0


def _searxng_healthcheck(base_url: str = None) -> bool:
    import urllib.request

    target = (base_url or _searxng_url()).rstrip("/")
    try:
        req = urllib.request.Request(
            f"{target}/",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read(512).decode("utf-8", errors="ignore").lower()
            return resp.status == 200 and "searxng" in body
    except Exception:
        return False


def _ensure_searxng_native_repo(repo_dir: Path) -> bool:
    git = _which("git")
    if not git:
        warn("未找到 git，无法准备官方 SearXNG 安装脚本")
        return False

    repo_url = _searxng_git_url()
    branch = _searxng_git_branch()
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    if repo_dir.exists() and not (repo_dir / ".git").exists():
        warn(f"SearXNG 源码目录已存在但不是 git 仓库: {repo_dir}")
        info("请先清理该目录，或改用新的 GARY_SEARXNG_GIT_URL / GARY_SEARXNG_GIT_BRANCH")
        return False

    if (repo_dir / ".git").exists():
        step("更新官方 SearXNG 安装源码")
        commands = [
            [git, "-C", str(repo_dir), "fetch", "--depth", "1", "origin", branch],
            [git, "-C", str(repo_dir), "checkout", branch],
            [git, "-C", str(repo_dir), "pull", "--ff-only", "origin", branch],
        ]
    else:
        step("拉取官方 SearXNG 安装源码")
        commands = [
            [git, "clone", "--depth", "1", "--branch", branch, repo_url, str(repo_dir)],
        ]

    for cmd in commands:
        result = _run(cmd, capture=False, timeout=None)
        if result.returncode != 0:
            warn(f"SearXNG 源码准备失败，请手动检查: {' '.join(cmd)}")
            return False

    return True


def _searxng_native_install_env() -> dict:
    host, port = _searxng_host_port()
    return {
        "FORCE_TIMEOUT": "0",
        "SEARXNG_URL": _searxng_url(),
        "SEARXNG_PORT": str(port),
        "SEARXNG_BIND_ADDRESS": host,
        "GIT_URL": _searxng_git_url(),
        "GIT_BRANCH": _searxng_git_branch(),
    }


def _list_wsl_distros(runtime: str) -> list[str]:
    result = _run([runtime, "-l", "-q"], timeout=30)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _pick_wsl_distro(runtime: str) -> str:
    requested = _searxng_wsl_distro()
    distros = _list_wsl_distros(runtime)
    if not distros:
        return ""
    for distro in distros:
        if distro.lower() == requested.lower():
            return distro
    return distros[0]


def setup_native_searxng(auto: bool, *, explicit: bool = False):
    header("Step 3b  本地 SearXNG（官方原生安装）")
    base_url = _searxng_url()
    if _searxng_healthcheck(base_url):
        ok(f"SearXNG 已运行: {base_url}")
        return

    if IS_WIN:
        runtime = _wsl_runtime()
        if not runtime:
            warn("未找到 WSL，无法在 Windows 上用官方脚本原生安装 SearXNG")
            info("请先执行: wsl --install -d Ubuntu")
            info("或者先手动部署 SearXNG，再设置 GARY_SEARXNG_URL")
            return

        distro = _pick_wsl_distro(runtime)
        if not distro:
            warn("未检测到可用的 WSL 发行版")
            info("请先执行: wsl --install -d Ubuntu")
            return

        if not (auto or explicit):
            if not ask(f"使用 WSL 发行版 {distro} 原生安装本地 SearXNG？", default="y"):
                info("已跳过原生安装，可稍后执行：python setup.py --searxng-native")
                return

        env_items = _searxng_native_install_env()
        repo_dir = _searxng_wsl_repo_dir()
        repo_url = _searxng_git_url()
        branch = _searxng_git_branch()
        quoted_repo_dir = shlex.quote(repo_dir)
        quoted_repo_url = shlex.quote(repo_url)
        quoted_branch = shlex.quote(branch)
        install_env = " ".join(f"{key}={shlex.quote(value)}" for key, value in env_items.items())
        shell_script = (
            "set -e; "
            f"repo_dir={quoted_repo_dir}; "
            f"repo_url={quoted_repo_url}; "
            f"branch={quoted_branch}; "
            'mkdir -p "$(dirname "$repo_dir")"; '
            'if [ -d "$repo_dir/.git" ]; then '
            'git -C "$repo_dir" fetch --depth 1 origin "$branch"; '
            'git -C "$repo_dir" checkout "$branch"; '
            'git -C "$repo_dir" pull --ff-only origin "$branch"; '
            "else "
            'git clone --depth 1 --branch "$branch" "$repo_url" "$repo_dir"; '
            "fi; "
            'cd "$repo_dir"; '
            f"sudo -H env {install_env} ./utils/searxng.sh install all"
        )

        step(f"使用 WSL({distro}) 调用官方脚本安装 SearXNG")
        info("该步骤会在 WSL 中调用 sudo，并按官方脚本安装所需系统依赖与服务")
        result = _run(
            [runtime, "-d", distro, "--", "bash", "-lc", shell_script],
            capture=False,
            timeout=None,
        )
        if result.returncode != 0:
            warn("WSL 原生安装脚本执行失败")
            info(
                "可手动重试: "
                f'{runtime} -d {distro} -- bash -lc "cd {_searxng_wsl_repo_dir()} && sudo -H ./utils/searxng.sh install all"'
            )
            return

        if _searxng_healthcheck(base_url):
            ok(f"SearXNG 已就绪: {base_url}")
            info(f"搜索工具将使用本地后端: {base_url}")
            return

        warn("WSL 安装完成，但 Windows 侧健康检查未通过")
        info("请确认 WSL 的 localhost 转发已启用，或把 GARY_SEARXNG_URL 指到 WSL 实例地址")
        return

    if not IS_LINUX:
        warn("官方 SearXNG 原生一键安装当前仅支持 Linux")
        info("macOS / Windows 建议使用已有实例，或设置 GARY_SEARXNG_URL 指向外部 SearXNG")
        return

    if not _which("sudo"):
        warn("未找到 sudo，无法调用官方 SearXNG 原生安装脚本")
        info("你也可以先手动安装 SearXNG，然后设置 GARY_SEARXNG_URL")
        return

    if not _which("git"):
        warn("未找到 git，无法拉取官方 SearXNG 安装源码")
        return

    if not (auto or explicit):
        if not ask("改用官方原生方式安装本地 SearXNG（需要 git + sudo）？", default="y"):
            info("已跳过原生安装，可稍后执行：python setup.py --searxng-native")
            return

    SERVICES_DIR.mkdir(parents=True, exist_ok=True)
    SEARXNG_DIR.mkdir(parents=True, exist_ok=True)
    repo_dir = SEARXNG_NATIVE_REPO_DIR
    if not _ensure_searxng_native_repo(repo_dir):
        return

    env_items = _searxng_native_install_env()
    install_cmd = ["sudo", "-H", "env"]
    for key, value in env_items.items():
        install_cmd.append(f"{key}={value}")
    install_cmd.extend(["./utils/searxng.sh", "install", "all"])

    step("使用官方脚本原生安装 SearXNG")
    info("该步骤会调用 sudo，并按官方脚本安装所需系统依赖与服务")
    result = _run(install_cmd, capture=False, timeout=None, cwd=repo_dir)
    if result.returncode != 0:
        warn("官方原生安装脚本执行失败")
        info(f"可进入目录后重试: cd {repo_dir} && sudo -H ./utils/searxng.sh install all")
        return

    if _searxng_healthcheck(base_url):
        ok(f"SearXNG 已就绪: {base_url}")
        info(f"搜索工具将使用本地后端: {base_url}")
        info(f"后续更新可执行: cd {repo_dir} && sudo -H ./utils/searxng.sh instance update")
        return

    warn("原生安装完成，但健康检查未通过")
    info(f"可执行排查: cd {repo_dir} && sudo -H ./utils/searxng.sh instance inspect")
    info(f"当前配置目标地址: {base_url}")


def setup_local_searxng(auto: bool, *, explicit: bool = False):
    header("Step 3b  本地 SearXNG（网页搜索可选）")
    base_url = _searxng_url()
    if _searxng_healthcheck(base_url):
        ok(f"SearXNG 已运行: {base_url}")
        return

    if auto and not explicit:
        info("默认跳过本地 SearXNG 安装；需要网页搜索时再执行：python setup.py --searxng")
        return

    runtime = _container_runtime()
    if not runtime:
        if IS_WIN:
            info("Windows 未检测到可用的 Docker 运行时，尝试自动安装 Docker Desktop")
            runtime = _ensure_windows_docker_desktop(auto or explicit, explicit=explicit)
        if runtime:
            ok(f"容器运行时已就绪: {runtime}")
        else:
            warn("未找到 docker / podman，容器一键安装不可用")
            if IS_WIN:
                info(
                    "Windows 上可重试：python setup.py --searxng，脚本会继续尝试安装 Docker Desktop"
                )
                info("若 Docker Desktop 已安装，请先完成首次启动初始化，再重新执行当前命令")
                return
            info("可改用官方原生安装：python setup.py --searxng-native")
            if (
                not auto
                and not explicit
                and ask("改用官方原生方式安装本地 SearXNG（需要 git + sudo）？", default="y")
            ):
                setup_native_searxng(auto=True, explicit=True)
            return

    if not (
        auto
        or ask(
            "安装并启动本地 SearXNG（首次需拉取 Docker 镜像，可能较慢；browser_search / web_search 需要）？",
            default="n",
        )
    ):
        info("已跳过，本地网页搜索工具将在 SearXNG 启动后可用")
        return

    image = _searxng_image()
    container_name = _searxng_container_name()
    host, port = _searxng_host_port()
    SERVICES_DIR.mkdir(parents=True, exist_ok=True)
    SEARXNG_DIR.mkdir(parents=True, exist_ok=True)

    step(f"使用 {runtime} 准备本地 SearXNG")

    if _container_exists(runtime, container_name):
        if _container_running(runtime, container_name):
            ok(f"SearXNG 容器已运行: {container_name}")
        else:
            info(f"启动已有容器: {container_name}")
            result = _run([runtime, "start", container_name], capture=False, timeout=60)
            if result.returncode != 0:
                warn(f"启动容器失败，请手动查看日志: {runtime} logs {container_name}")
                return
    else:
        if _container_image_present(runtime, image):
            ok(f"镜像已存在: {image}")
        else:
            info(f"拉取镜像: {image}")
            info("首次拉取可能较慢；已下载的层会被 Docker 缓存，重试会从断点继续")
            pull_result = _run([runtime, "pull", image], capture=False, timeout=None)
            if pull_result.returncode != 0:
                if _container_image_present(runtime, image):
                    warn("镜像拉取命令返回异常，但镜像已存在，继续创建容器")
                else:
                    warn(f"镜像拉取失败，请手动重试: {runtime} pull {image}")
                    return

        info(f"创建容器: {container_name}")
        run_result = _run(
            [
                runtime,
                "run",
                "-d",
                "--name",
                container_name,
                "--restart",
                "unless-stopped",
                "-p",
                f"{host}:{port}:8080",
                image,
            ],
            capture=False,
            timeout=120,
        )
        if run_result.returncode != 0:
            warn(f"容器创建失败，请手动查看日志或重试: {runtime} logs {container_name}")
            return

    if _searxng_healthcheck(base_url):
        ok(f"SearXNG 已就绪: {base_url}")
        info(f"搜索工具将使用本地后端: {base_url}")
        return

    warn("容器已启动，但健康检查未通过")
    info(f"查看容器日志: {runtime} logs {container_name}")
    info(f"若端口冲突，可设置环境变量后重试: export GARY_SEARXNG_URL=http://127.0.0.1:18080")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: 工作区目录
# ─────────────────────────────────────────────────────────────────────────────
def create_workspace():
    header("Step 4  工作区目录")
    for d in [
        HAL_DIR / "Inc",
        HAL_DIR / "Src",
        HAL_DIR / "CMSIS" / "Include",
        BUILD_DIR,
        PROJECTS_DIR,
        SERVICES_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)
    ok(f"workspace -> {WORKSPACE}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: STM32 HAL 库
# ─────────────────────────────────────────────────────────────────────────────
HAL_REPOS = {
    "f0": (
        "https://github.com/STMicroelectronics/stm32f0xx-hal-driver/archive/refs/heads/master.zip",
        "https://github.com/STMicroelectronics/cmsis_device_f0/archive/refs/heads/master.zip",
    ),
    "f1": (
        "https://github.com/STMicroelectronics/stm32f1xx-hal-driver/archive/refs/heads/master.zip",
        "https://github.com/STMicroelectronics/cmsis_device_f1/archive/refs/heads/master.zip",
    ),
    "f3": (
        "https://github.com/STMicroelectronics/stm32f3xx-hal-driver/archive/refs/heads/master.zip",
        "https://github.com/STMicroelectronics/cmsis_device_f3/archive/refs/heads/master.zip",
    ),
    "f4": (
        "https://github.com/STMicroelectronics/stm32f4xx-hal-driver/archive/refs/heads/master.zip",
        "https://github.com/STMicroelectronics/cmsis_device_f4/archive/refs/heads/master.zip",
    ),
}

CMSIS_CORE_FILES = {
    "core_cm0.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/core_cm0.h",
    "core_cm0plus.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/core_cm0plus.h",
    "core_cm3.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/core_cm3.h",
    "core_cm4.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/core_cm4.h",
    "cmsis_version.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_version.h",
    "cmsis_compiler.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_compiler.h",
    "cmsis_gcc.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_gcc.h",
    "cmsis_armcc.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_armcc.h",
    "cmsis_armclang.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_armclang.h",
    "mpu_armv7.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/mpu_armv7.h",
}


def download_hal(auto: bool, families: List[str] = None):
    header("Step 5  STM32 HAL 库")
    if families is None:
        families = list(HAL_REPOS.keys())

    present = [f for f in families if (HAL_DIR / "Inc" / f"stm32{f}xx_hal.h").exists()]
    missing = [f for f in families if f not in present]

    for f in present:
        src_cnt = len(list((HAL_DIR / "Src").glob(f"stm32{f}xx_hal*.c")))
        ok(f"STM32{f.upper()}xx HAL 已就绪（{src_cnt} 个源文件）")

    cmsis_ok = (HAL_DIR / "CMSIS" / "Include" / "core_cm3.h").exists()
    if cmsis_ok:
        ok("ARM CMSIS Core 已就绪")

    if not missing and cmsis_ok:
        return

    if missing:
        fam_str = " + ".join(f"STM32{f.upper()}xx" for f in missing)
        if not (auto or ask(f"从 GitHub 下载 {fam_str} HAL（约 5-15 MB/系列）？")):
            warn("跳过 HAL 下载，编译将以语法检查模式运行")
            return

    if _detect_china_network():
        info("国内网络：HAL 库将通过 ghfast.top 镜像下载")

    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="stm32_hal_"))
    try:
        for fam in missing:
            hal_url, cmsis_url = HAL_REPOS[fam]
            step(f"STM32{fam.upper()}xx  HAL 驱动...")
            hal_zip = tmp / f"hal_{fam}.zip"
            if _download(hal_url, hal_zip, f"stm32{fam}xx-hal-driver"):
                _extract_zip(hal_zip, HAL_DIR / "Inc", ["Inc"])
                _extract_zip(hal_zip, HAL_DIR / "Src", ["Src"])
                ok(f"  HAL 驱动头文件 + 源文件")
            cmsis_zip = tmp / f"cmsis_{fam}.zip"
            if _download(cmsis_url, cmsis_zip, f"cmsis_device_{fam}"):
                _extract_zip(cmsis_zip, HAL_DIR / "Inc", ["Include"])
                _extract_zip(cmsis_zip, HAL_DIR / "Src", ["Source/Templates"])
                ok(f"  CMSIS Device 头文件 + system_*.c")
        if not cmsis_ok:
            _download_cmsis_core()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok("HAL 库下载完成")


def _download_cmsis_core():
    step("ARM CMSIS Core 头文件...")
    dst_dir = HAL_DIR / "CMSIS" / "Include"
    dst_dir.mkdir(parents=True, exist_ok=True)
    if _detect_china_network():
        info("国内网络：CMSIS Core 头文件将通过 raw.gitmirror.com 镜像下载")
    failed = []
    for fname, url in CMSIS_CORE_FILES.items():
        dest = dst_dir / fname
        if dest.exists():
            continue
        if not _download(url, dest, fname):
            failed.append(fname)
    if failed:
        warn(f"  以下文件下载失败: {failed}")
        info("  可手动下载: https://github.com/ARM-software/CMSIS_5/tree/5.9.0/CMSIS/Core/Include")
    else:
        ok(f"  ARM CMSIS Core ({len(CMSIS_CORE_FILES)} 个头文件)")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5b: FreeRTOS Kernel 下载（RTOS 开发可选）
# ─────────────────────────────────────────────────────────────────────────────
FREERTOS_KERNEL_URL = "https://github.com/FreeRTOS/FreeRTOS-Kernel/archive/refs/heads/main.zip"
RTOS_DIR = WORKSPACE / "rtos"


def download_freertos(auto: bool):
    header("Step 5b  FreeRTOS Kernel（RTOS 开发可选，约 2 MB）")
    rtos_kernel_dir = RTOS_DIR / "FreeRTOS-Kernel"
    already_ok = rtos_kernel_dir.exists() and (rtos_kernel_dir / "tasks.c").exists()
    if not already_ok:
        for d in RTOS_DIR.iterdir() if RTOS_DIR.exists() else []:
            if d.is_dir() and (d / "tasks.c").exists():
                already_ok = True
                rtos_kernel_dir = d
                break
    if already_ok:
        ok(f"FreeRTOS Kernel 已就绪: {rtos_kernel_dir}")
        return

    if not (
        auto or ask("下载 FreeRTOS Kernel（RTOS 多任务开发必需，裸机项目可跳过）？", default="n")
    ):
        info("已跳过，裸机（无 RTOS）模式不受影响")
        return

    if _detect_china_network():
        info("国内网络：FreeRTOS 将通过 ghfast.top 镜像下载")

    import tempfile, zipfile as _zf

    tmp = Path(tempfile.mkdtemp(prefix="freertos_"))
    try:
        zip_path = tmp / "freertos_kernel.zip"
        if not _download(FREERTOS_KERNEL_URL, zip_path, "FreeRTOS-Kernel"):
            return
        info("解压 FreeRTOS Kernel...")
        RTOS_DIR.mkdir(parents=True, exist_ok=True)
        with _zf.ZipFile(zip_path, "r") as zf:
            prefix = zf.namelist()[0].split("/")[0] if zf.namelist() else ""
            zf.extractall(RTOS_DIR)
        extracted = RTOS_DIR / prefix
        if extracted.exists() and not rtos_kernel_dir.exists():
            extracted.rename(rtos_kernel_dir)
        if (rtos_kernel_dir / "tasks.c").exists():
            ok(f"FreeRTOS Kernel 已就绪: {rtos_kernel_dir}")
        else:
            warn("解压完成但未找到 tasks.c，请检查目录结构")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Linux udev 规则
# ─────────────────────────────────────────────────────────────────────────────
_UDEV_RULES = """\
# Gary Dev Agent - STM32 调试探针 + 串口 udev 规则
ATTRS{idVendor}=="0483", ATTRS{idProduct}=="3744", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="0483", ATTRS{idProduct}=="3748", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374b", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374e", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374f", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="0483", ATTRS{idProduct}=="3753", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="0d28", ATTRS{idProduct}=="0204", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="1366", ATTRS{idProduct}=="0101", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="1366", ATTRS{idProduct}=="0105", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="1366", ATTRS{idProduct}=="1010", MODE="0666", GROUP="plugdev", TAG+="uaccess"
ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", GROUP="dialout"
ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666", GROUP="dialout"
ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", MODE="0666", GROUP="dialout"
"""


def setup_udev(auto: bool):
    if not IS_LINUX:
        return
    header("Step 6  USB 设备权限（udev rules）")
    rules_path = Path("/etc/udev/rules.d/99-gary-stm32.rules")
    if rules_path.exists():
        ok(f"udev 规则已安装: {rules_path}")
        return
    if not (auto or ask("安装 udev 规则（ST-Link/J-Link/串口免 sudo）？")):
        warn("已跳过，烧录时可能需要 sudo")
        return
    try:
        r = _run(["sudo", "tee", str(rules_path)], capture=False, input_text=_UDEV_RULES)
        if r.returncode == 0:
            _run(["sudo", "udevadm", "control", "--reload-rules"], capture=False)
            _run(["sudo", "udevadm", "trigger"], capture=False)
            ok("udev 规则已安装")
            username = os.environ.get("USER") or os.environ.get("SUDO_USER") or ""
            if username:
                for grp in ("plugdev", "dialout"):
                    if _run(["getent", "group", grp]).returncode == 0:
                        _run(["sudo", "usermod", "-aG", grp, username], capture=False)
                        ok(f"  {username} 已加入 {grp} 组（需重新登录生效）")
        else:
            warn("写入失败，请手动运行：")
            info(f"  sudo tee {rules_path} << 'EOF'")
    except Exception as e:
        warn(f"udev 设置失败: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: pyocd 支持包
# ─────────────────────────────────────────────────────────────────────────────


def _pyocd_installed_targets() -> str:
    """返回已安装目标列表（小写），失败返回空字符串"""
    r = _run(_python_cmd("-m", "pyocd", "list", "--targets"), timeout=30)
    return r.stdout.lower() if r.returncode == 0 else ""


def _build_pack_list() -> list:
    """
    根据 DEFAULT_CHIP 决定需要安装的 pack 列表。
    返回 [(check_target, install_chip, label), ...]
    """
    chip = _read_default_chip()
    family = _detect_chip_family(chip) if chip else ""
    pack_target = _FAMILY_PACK_TARGET.get(family)

    if pack_target:
        family_label = f"STM32{family.upper()}xx"
        chip_hint = f"（{chip}）" if chip else ""
        return [(pack_target, pack_target, f"{family_label} 支持包{chip_hint}")]
    else:
        return [
            ("stm32f103c8", "stm32f103c8", "STM32F1xx 支持包"),
            ("stm32f411ce", "stm32f411ce", "STM32F4xx 支持包"),
        ]


def setup_pyocd(auto: bool):
    header("Step 7  pyocd 芯片支持包（可选）")
    version = _python_module_version("pyocd")
    if version:
        ok(f"pyocd {version}")
    else:
        warn("pyocd 未安装，跳过（请先完成 Step 3）")
        return

    packs = _build_pack_list()
    targets = _pyocd_installed_targets()
    missing = []
    for check, install, label in packs:
        if check in targets:
            ok(f"{label}已安装")
        else:
            missing.append((install, label))

    if not missing:
        return

    labels = " / ".join(lb for _, lb in missing)
    if not (auto or ask(f"安装 {labels}（约 15-30 MB）？")):
        info("已跳过，pyocd 将以通用 Cortex-M 模式运行（无法烧录 flash）")
        return

    info("更新 pack 索引...")
    r = _run(_python_cmd("-m", "pyocd", "pack", "update"), capture=False, timeout=120)
    if r.returncode != 0:
        warn("pack 索引更新失败，尝试继续安装...")

    failed = []
    for install_chip, label in missing:
        info(f"安装 {label}...")
        r = _run(
            _python_cmd("-m", "pyocd", "pack", "install", install_chip),
            capture=False,
            timeout=180,
        )
        if install_chip in _pyocd_installed_targets():
            ok(f"{label}安装成功")
        else:
            failed.append(install_chip)
            warn(f"{label}安装失败，可手动运行: pyocd pack install {install_chip}")

    if failed:
        warn("部分支持包安装失败，/connect 时将以通用 Cortex-M 模式运行（无法烧录 flash）")
    else:
        ok("pyocd 芯片支持包安装完成")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: 安装 gary 命令
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_unix_path(bin_dir: Path):
    if str(bin_dir) in os.environ.get("PATH", ""):
        return
    home = Path.home()
    candidates = (
        [home / ".zshrc", home / ".bash_profile"] if IS_MAC else [home / ".bashrc", home / ".zshrc"]
    )
    line = '\nexport PATH="$HOME/.local/bin:$PATH"  # gary command\n'
    for sh in candidates:
        if sh.exists():
            if ".local/bin" not in sh.read_text(encoding="utf-8", errors="ignore"):
                with open(sh, "a", encoding="utf-8") as f:
                    f.write(line)
                info(f"  PATH 已写入 {sh}（重新打开终端后生效）")
            return
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_GARY_SH = """\
#!/bin/sh
# gary - Gary Dev Agent 命令行入口（自动生成）
GARY_SCRIPT="{agent_script}"
unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy
case "$1" in
  do)     shift; exec "{python}" "$GARY_SCRIPT" --do "$*" ;;
  doctor) exec "{python}" "$GARY_SCRIPT" --doctor ;;
  config) exec "{python}" "$GARY_SCRIPT" --config ;;
  *)      exec "{python}" "$GARY_SCRIPT" "$@" ;;
esac
"""

_GARY_BAT = """\
@echo off
rem gary - Gary Dev Agent 命令行入口（Windows，自动生成）
set ALL_PROXY=
set all_proxy=
set HTTP_PROXY=
set http_proxy=
set HTTPS_PROXY=
set https_proxy=
set GARY_SCRIPT={agent_script}
if "%1"=="do" (
    shift
    "{python}" "%GARY_SCRIPT%" --do %*
) else if "%1"=="doctor" (
    "{python}" "%GARY_SCRIPT%" --doctor
) else if "%1"=="config" (
    "{python}" "%GARY_SCRIPT%" --config
) else (
    "{python}" "%GARY_SCRIPT%" %*
)
"""


def _default_win_install_dir() -> Path:
    """返回 Windows 下 gary.bat 的默认安装目录。"""

    exe_dir = Path(sys.executable).resolve().parent
    if exe_dir.name.lower() == "scripts":
        return exe_dir

    scripts = exe_dir / "Scripts"
    if scripts.exists():
        return scripts

    parent_scripts = exe_dir.parent / "Scripts"
    if parent_scripts.exists():
        return parent_scripts

    appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return appdata / "Programs" / "Gary"


def _get_win_install_dir() -> Path:
    """兼容旧调用名，返回 Windows 下 gary.bat 的安装目录。"""

    return _default_win_install_dir()


def _resolve_win_install_dir() -> Path:
    """解析 Windows 安装目录，并兼容旧版脚本缺少 helper 的情况。"""

    resolver = globals().get("_get_win_install_dir")
    if callable(resolver):
        try:
            install_dir = resolver()
            if install_dir:
                return Path(install_dir)
        except Exception:
            pass
    return _default_win_install_dir()


def _check_win_path(install_dir: Path):
    """检查 install_dir 是否在 PATH 中，不在则提示用户手动添加"""
    path_env = os.environ.get("PATH", "")
    if str(install_dir).lower() in path_env.lower():
        return
    warn(f"  {install_dir} 不在 PATH 中")
    info("  请将该目录添加到系统 PATH，或在 PowerShell 中执行：")
    info(f'  $env:PATH += ";{install_dir}"')


def install_gary_command(auto: bool):
    header("Step 8  安装 gary 命令")
    if not AGENT_SCRIPT.exists():
        err(f"找不到 {AGENT_SCRIPT}，请确认路径")
        return
    if IS_WIN:
        _install_gary_win(auto)
    else:
        _install_gary_unix(auto)


def _install_gary_unix(auto: bool):
    install_dir = Path.home() / ".local" / "bin"
    gary_path = install_dir / "gary"
    expected_content = _GARY_SH.format(agent_script=str(AGENT_SCRIPT), python=_active_python_path())

    if gary_path.exists():
        existing = gary_path.read_text(encoding="utf-8", errors="ignore")
        if existing == expected_content:
            ok(f"gary 命令已安装: {gary_path}")
            _ensure_unix_path(install_dir)
            return
        info("检测到旧版 gary，更新中...")

    if not (auto or ask(f"安装 gary 命令到 {install_dir}？")):
        info(f"手动安装：ln -s {AGENT_SCRIPT} ~/.local/bin/gary && chmod +x ~/.local/bin/gary")
        return

    install_dir.mkdir(parents=True, exist_ok=True)
    gary_path.write_text(expected_content, encoding="utf-8")
    gary_path.chmod(gary_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    ok(f"gary 命令已安装: {gary_path}")
    _ensure_unix_path(install_dir)


def _install_gary_win(auto: bool):
    install_dir = _resolve_win_install_dir()
    gary_bat = install_dir / "gary.bat"
    expected_content = _GARY_BAT.format(
        agent_script=str(AGENT_SCRIPT), python=_active_python_path()
    )

    if gary_bat.exists():
        existing = gary_bat.read_text(encoding="utf-8", errors="ignore")
        if existing == expected_content:
            ok(f"gary.bat 已安装: {gary_bat}")
            _check_win_path(install_dir)
            return
        info("检测到旧版 gary.bat，更新中...")

    if not (auto or ask(f"安装 gary.bat 到 {install_dir}？")):
        info(f"手动安装：将以下内容保存为 {install_dir}\\gary.bat")
        info(f'  "{_active_python_path()}" "{AGENT_SCRIPT}" %*')
        return

    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        gary_bat.write_text(expected_content, encoding="utf-8")
        ok(f"gary.bat 已安装: {gary_bat}")
        _check_win_path(install_dir)
    except Exception as e:
        err(f"写入 gary.bat 失败: {e}")
        err(f"  目标路径: {gary_bat}")
        info("请手动在 PowerShell 中执行：")
        info(f'  New-Item -Path "{install_dir}" -ItemType Directory -Force')
        info(
            f'  Set-Content "{gary_bat}" \'@echo off\\n"{_active_python_path()}" "{AGENT_SCRIPT}" %*\''
        )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 9: 最终验证
# ─────────────────────────────────────────────────────────────────────────────
def verify():
    header("验证  环境总览")
    status = {}
    ok(f"活动 Python: {_active_python_path()} [{ACTIVE_PYTHON_LABEL}]")

    # AI
    cur_key, cur_url, cur_model, cur_style = _read_current_ai_config()
    placeholder = ("YOUR_API_KEY", "sk-YOUR")
    ai_ok = bool(cur_key and not any(cur_key.startswith(p) for p in placeholder))
    if ai_ok:
        ok(f"AI 接口: {_provider_label(cur_style)} / {cur_model}  ({cur_url[:50]})")
        ok(f"API Key: {_mask_key(cur_key)}")
    else:
        err("AI 接口: 未配置 API Key -> 请运行 python setup.py 重新配置")
    status["ai"] = ai_ok

    # GCC
    ver = _gcc_ver()
    if ver:
        ok(f"arm-none-eabi-gcc  {ver[:70]}")
        status["gcc"] = True
    else:
        err("arm-none-eabi-gcc  未找到")
        status["gcc"] = False

    # Python 包
    pkg_ok = {}
    for imp, pkg, required in PYTHON_PKGS:
        if _python_module_available(imp):
            ok(f"Python: {pkg}")
            pkg_ok[pkg] = True
        else:
            (warn if not required else err)(f"Python: {pkg}  {'[必须]' if required else '[可选]'}")
            pkg_ok[pkg] = False
    status["python"] = all(pkg_ok.get(pkg, True) for _, pkg, req in PYTHON_PKGS if req)

    # HAL
    hal_any = False
    for fam in HAL_REPOS:
        hal_h = HAL_DIR / "Inc" / f"stm32{fam}xx_hal.h"
        src_cnt = (
            len(list((HAL_DIR / "Src").glob(f"stm32{fam}xx_hal*.c")))
            if (HAL_DIR / "Src").exists()
            else 0
        )
        if hal_h.exists():
            ok(f"HAL: stm32{fam}xx  ({src_cnt} 个源文件)")
            hal_any = True
        else:
            warn(f"HAL: stm32{fam}xx  未安装")
    cmsis_ok = (HAL_DIR / "CMSIS" / "Include" / "core_cm3.h").exists()
    (ok if cmsis_ok else warn)(f"ARM CMSIS Core  {'OK' if cmsis_ok else '未找到'}")
    status["hal"] = hal_any and cmsis_ok

    # 网络模式
    if _IS_CHINA_NETWORK is not None:
        mode_str = _c("33", "国内镜像模式") if _IS_CHINA_NETWORK else _c("32", "直连模式")
        ok(f"网络环境: {mode_str}")

    # gary 命令
    gary_bin = shutil.which("gary")
    if gary_bin:
        ok(f"gary 命令  {gary_bin}")
        status["gary"] = True
    else:
        warn("gary 命令  未在 PATH 中（可能需要重新打开终端）")
        status["gary"] = False

    # 本地 SearXNG
    searx_url = _searxng_url()
    if _searxng_healthcheck(searx_url):
        ok(f"本地 SearXNG  {searx_url}")
        status["searxng"] = True
    else:
        warn(f"本地 SearXNG  未运行 [可选] -> {searx_url}")
        status["searxng"] = False

    print()
    all_ok = status["ai"] and status["gcc"] and status["python"] and status["hal"]
    if all_ok:
        print(_c("1;32", "  +==========================================+"))
        print(_c("1;32", "  |   环境就绪！Gary Dev Agent 可以使用      |"))
        print(_c("1;32", "  +==========================================+"))
        print()
        print("  使用方式：")
        print(f"    {_c('36', 'gary')}                              启动交互式对话助手")
        print(f"    {_c('36', 'gary do \"让 PA0 LED 以 500ms 闪烁\"')}  一次性执行任务")
        print(f"    {_c('36', 'gary --connect')}                     连接探针后启动")
        print()
        if not status["gary"]:
            print(_c("33", "  !! gary 命令尚未在当前 shell 生效，请重新打开终端"))
            if not IS_WIN:
                print(f"     或执行: {_c('36', 'source ~/.bashrc')}")
    else:
        print(_c("1;33", "  !! 部分组件缺失："))
        if not status["ai"]:
            print(_c("33", "    - AI 接口未配置 -> 运行 gary config 配置 API Key"))
        if not status["gcc"]:
            print(_c("33", "    - arm-none-eabi-gcc 未安装 -> 无法编译固件"))
        if not status["python"]:
            print(_c("33", "    - Python 核心包缺失 -> 程序无法运行"))
        if not status["hal"]:
            print(_c("33", "    - HAL 库未安装 -> 仅语法检查模式"))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Gary Dev Agent 一键环境安装",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--auto", action="store_true", help="全自动，不询问")
    parser.add_argument("--check", action="store_true", help="仅检查环境")
    parser.add_argument("--hal", nargs="*", help="仅下载 HAL（可选: f0 f1 f3 f4）")
    parser.add_argument("--rtos", action="store_true", help="仅下载 FreeRTOS Kernel")
    parser.add_argument("--searxng", action="store_true", help="仅安装 / 启动本地 SearXNG")
    parser.add_argument(
        "--searxng-native",
        action="store_true",
        help="仅用官方脚本原生安装 / 启动本地 SearXNG（不依赖 Docker）",
    )
    args = parser.parse_args()

    print(
        _c(
            "1;35",
            """
  +================================================+
  |      Gary Dev Agent  -  一键环境安装           |
  |  STM32 / RP2040 / ESP 系列 AI 开发助手        |
  +================================================+""",
        )
    )
    print(
        f"  平台: {_c('36', f'{SYSTEM} {MACHINE}')}  |  "
        f"Python: {_c('36', sys.version.split()[0])}  |  "
        f"目录: {_c('36', str(SCRIPT_DIR))}"
    )

    try:
        # ── 网络环境检测（最先执行，结果全局缓存供后续步骤复用）──────────────
        _detect_china_network()

        if args.check:
            ensure_python_runtime(auto=False, allow_create=False)
            verify()
            return

        if args.hal is not None:
            fams = args.hal if args.hal else list(HAL_REPOS.keys())
            invalid = [f for f in fams if f not in HAL_REPOS]
            if invalid:
                err(f"未知系列: {invalid}，可选: {list(HAL_REPOS.keys())}")
                sys.exit(1)
            create_workspace()
            download_hal(auto=True, families=fams)
            return

        if args.rtos:
            create_workspace()
            download_freertos(auto=True)
            return

        if args.searxng:
            create_workspace()
            setup_local_searxng(auto=True, explicit=True)
            return

        if args.searxng_native:
            create_workspace()
            setup_native_searxng(auto=True, explicit=True)
            return

        check_python()
        ensure_python_runtime(auto=args.auto, allow_create=True)
        configure_ai(auto=args.auto)
        configure_chip(auto=args.auto)
        install_arm_gcc(auto=args.auto)
        install_python_packages(auto=args.auto)
        create_workspace()
        setup_local_searxng(auto=args.auto, explicit=False)
        download_hal(auto=args.auto)
        download_freertos(auto=args.auto)
        setup_udev(auto=args.auto)
        setup_pyocd(auto=args.auto)
        install_gary_command(auto=args.auto)
        verify()

    except KeyboardInterrupt:
        print("\n\n  已取消安装")
    except Exception as e:
        err(f"安装过程出错: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if IS_WIN and sys.stdin and sys.stdin.isatty():
            print()
            input("  按回车键关闭窗口...")


if __name__ == "__main__":
    main()
