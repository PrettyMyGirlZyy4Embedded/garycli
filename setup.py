#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gary Dev Agent - 一键环境安装脚本
====================================
支持平台: Ubuntu/Debian · Arch/Manjaro · Fedora/RHEL · openSUSE · macOS · Windows

用法:
  python3 setup.py              完整安装（交互询问）
  python3 setup.py --auto       全自动安装，不询问（CI / 无人值守）
  python3 setup.py --check      仅检查环境，不安装任何东西
  python3 setup.py --hal        仅重新下载 STM32 HAL 库（全部系列）
  python3 setup.py --hal f1     仅下载 STM32F1 HAL
  python3 setup.py --hal f1 f4  下载 F1 + F4 HAL

安装完成后:
  gary                    启动交互式对话助手
  gary do "任务描述"      一次性执行单个任务后退出
  gary --connect          连接探针后启动
  gary --chip STM32F407VET6 --connect  指定芯片并连接
"""

import sys
import os
import subprocess
import platform
import shutil
import argparse
import stat
from pathlib import Path
from typing import Optional, List

# ─────────────────────────────────────────────────────────────────────────────
# Windows 控制台编码修复（必须在任何输出之前执行）
# ─────────────────────────────────────────────────────────────────────────────
if platform.system() == "Windows":
    # 1. 切换控制台代码页到 UTF-8
    os.system("chcp 65001 > nul 2>&1")

    # 2. 重定向 stdout/stderr 为 UTF-8（Python 3.7+）
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    else:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    # 3. 启用 Windows 控制台 ANSI 转义序列（Win10 1511+）
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass  # 旧版 Windows 不支持，静默忽略

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

def ok(msg: str):   print(f"  {_c('32', 'OK')} {msg}")
def info(msg: str): print(f"  {_c('36', '->')} {msg}")
def warn(msg: str): print(f"  {_c('33', '!!')} {msg}")
def err(msg: str):  print(f"  {_c('31', 'XX')} {msg}")
def step(msg: str): print(f"\n  {_c('1;36', '>>')} {msg}")

# Windows 不一定能渲染 emoji，用 ASCII 替代
if platform.system() != "Windows":
    def ok(msg: str):   print(f"  {_c('32', '✓')} {msg}")
    def warn(msg: str): print(f"  {_c('33', '⚠')} {msg}")
    def err(msg: str):  print(f"  {_c('31', '✗')} {msg}")
    def step(msg: str): print(f"\n  {_c('1;36', '▶')} {msg}")

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
SYSTEM   = platform.system()    # Linux / Darwin / Windows
MACHINE  = platform.machine()   # x86_64 / aarch64 / arm64 ...
IS_LINUX = SYSTEM == "Linux"
IS_MAC   = SYSTEM == "Darwin"
IS_WIN   = SYSTEM == "Windows"

SCRIPT_DIR   = Path(__file__).parent.resolve()
WORKSPACE    = SCRIPT_DIR / "workspace"
HAL_DIR      = WORKSPACE  / "hal"
BUILD_DIR    = WORKSPACE  / "build"
PROJECTS_DIR = WORKSPACE  / "projects"
AGENT_SCRIPT = SCRIPT_DIR / "stm32_agent.py"

PIP = [sys.executable, "-m", "pip"]

# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────
def _run(cmd, shell=False, capture=True, input_text=None, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, shell=shell,
        capture_output=capture,
        text=True,
        input=input_text,
        **kw
    )

def _which(name: str) -> Optional[str]:
    return shutil.which(name)

def _distro() -> tuple:
    """返回 (id, id_like)，全小写，如 ('ubuntu', 'debian')"""
    try:
        d = {}
        for line in Path("/etc/os-release").read_text(errors="ignore").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                d[k.strip()] = v.strip().strip('"')
        return d.get("ID", "").lower(), d.get("ID_LIKE", "").lower()
    except Exception:
        return "", ""

def _download(url: str, dest: Path, label: str = "") -> bool:
    """下载文件，显示进度条"""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and label:
                        pct = min(downloaded * 100 // total, 100)
                        bar = "#" * (pct // 5) + "." * (20 - pct // 5)
                        print(f"\r    [{bar}] {pct:3d}%  {label[:40]}", end="", flush=True)
        if label:
            print()
        return True
    except Exception as e:
        if label:
            print()
        err(f"下载失败 [{label}]: {e}")
        return False

def _detect_zip_prefix(zip_path: Path) -> str:
    """自动检测 zip 文件中的根目录前缀（兼容 master/main 分支）"""
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
    import zipfile
    import shutil as _shutil
    try:
        prefix = _detect_zip_prefix(zip_path)
        if not prefix:
            err(f"无法检测 zip 前缀: {zip_path.name}")
            return False
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            for sub in sub_paths:
                src_prefix = f"{prefix}/{sub}/"
                matched = [m for m in members if m.startswith(src_prefix)]
                for member in matched:
                    rel = member[len(src_prefix):]
                    if not rel or rel.endswith("/"):
                        continue
                    fname = Path(rel).name
                    if not fname:
                        continue
                    target = dest_dir / fname
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        _shutil.copyfileobj(src, dst)
        return True
    except Exception as e:
        err(f"解压失败 {zip_path.name}: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# STEP 0: AI 接口配置
# ─────────────────────────────────────────────────────────────────────────────

_AI_PRESETS = [
    ("OpenAI",               "https://api.openai.com/v1",                                 "gpt-4o"),
    ("DeepSeek",             "https://api.deepseek.com/v1",                               "deepseek-chat"),
    ("Kimi / Moonshot",      "https://api.moonshot.cn/v1",                                "kimi-k2.5"),
    ("Google Gemini",        "https://generativelanguage.googleapis.com/v1beta/openai/",  "gemini-2.0-flash"),
    ("通义千问 (阿里云)",     "https://dashscope.aliyuncs.com/compatible-mode/v1",          "qwen-plus"),
    ("智谱 GLM",             "https://open.bigmodel.cn/api/paas/v4/",                     "glm-4-flash"),
    ("Ollama (本地无需Key)",  "http://127.0.0.1:11434/v1",                                 "qwen2.5-coder:14b"),
    ("自定义 / Other",        "",                                                           ""),
]

def _read_current_ai_config() -> tuple:
    import re as _re
    p = SCRIPT_DIR / "config.py"
    if not p.exists():
        return "", "", ""
    text = p.read_text(encoding="utf-8")
    def _get(pattern):
        m = _re.search(pattern, text, _re.MULTILINE)
        return m.group(1).strip() if m else ""
    return (
        _get(r'^AI_API_KEY\s*=\s*["\']([^"\']*)["\']'),
        _get(r'^AI_BASE_URL\s*=\s*["\']([^"\']*)["\']'),
        _get(r'^AI_MODEL\s*=\s*["\']([^"\']*)["\']'),
    )

def _write_ai_config(api_key: str, base_url: str, model: str) -> bool:
    import re as _re
    p = SCRIPT_DIR / "config.py"
    
    # 如果文件不存在，直接初始化一个最简版
    if not p.exists():
        p.write_text('AI_API_KEY = ""\nAI_BASE_URL = ""\nAI_MODEL = ""\n', encoding="utf-8")
        
    text = p.read_text(encoding="utf-8")
    
    configs = [
        ("AI_API_KEY", api_key),
        ("AI_BASE_URL", base_url),
        ("AI_MODEL", model)
    ]

    for key, val in configs:
        pattern = rf'^({key}\s*=\s*).*$'
        # 如果能在文件中找到这一行，就替换它
        if _re.search(pattern, text, flags=_re.MULTILINE):
            text = _re.sub(pattern, f'{key} = "{val}"', text, flags=_re.MULTILINE)
        else:
            # 如果找不到这一行（比如被删了或格式不对），就强行加在文件末尾
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

    cur_key, cur_url, cur_model = _read_current_ai_config()
    placeholder = ("YOUR_API_KEY", "", "sk-YOUR")
    is_configured = bool(cur_key and not any(cur_key.startswith(p) for p in placeholder))

    if is_configured:
        ok(f"API Key  : {_mask_key(cur_key)}")
        ok(f"Base URL : {cur_url}")
        ok(f"Model    : {cur_model}")
        if auto:
            return
        if not ask("重新配置 AI 接口？", default="n"):
            return

    print()
    print(f"  {_c('1;36', '请选择 AI 服务提供商：')}")
    for i, (name, url, _) in enumerate(_AI_PRESETS, 1):
        url_hint = _c("2", f"  {url[:52]}") if url else ""
        print(f"    {_c('33', str(i))}.  {name:<24}{url_hint}")
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
    preset_name, preset_url, preset_model = _AI_PRESETS[idx]

    if preset_url:
        base_url = preset_url
        info(f"Base URL: {base_url}")
    else:
        try:
            base_url = input(f"  {_c('33', '?')} Base URL (例: https://api.openai.com/v1): ").strip()
        except (EOFError, KeyboardInterrupt):
            base_url = cur_url

    default_model = preset_model or cur_model or ""
    try:
        hint = f" [{_c('36', default_model)}]" if default_model else ""
        entered = input(f"  {_c('33', '?')} Model 名称{hint} (回车使用默认): ").strip()
        model = entered if entered else default_model
    except (EOFError, KeyboardInterrupt):
        model = default_model

    print()
    if preset_name == "Ollama (本地无需Key)":
        api_key = "ollama"
        info("Ollama 本地模式，API Key 自动设为 ollama")
    else:
        info(f"请输入 {preset_name} API Key")
        try:
            api_key = _gp.getpass(f"  {_c('33', '?')} API Key (不回显): ")
        except Exception:
            try:
                api_key = input(f"  {_c('33', '?')} API Key: ").strip()
            except (EOFError, KeyboardInterrupt):
                api_key = ""

        if not api_key:
            if cur_key and is_configured:
                warn("未输入，保留原有 API Key")
                api_key = cur_key
            else:
                warn("未输入 API Key，请稍后手动修改 config.py")
                return

    if _write_ai_config(api_key, base_url, model):
        print()
        ok(f"AI 配置已写入 config.py")
        ok(f"  服务商 : {preset_name}")
        ok(f"  API Key: {_mask_key(api_key)}")
        ok(f"  Base URL: {base_url}")
        ok(f"  Model  : {model}")
    else:
        err("写入 config.py 失败")

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
        warn(f"未知平台 {SYSTEM}，请手动安装 arm-none-eabi-gcc")
    ver2 = _gcc_ver()
    if ver2:
        ok(f"安装成功: {ver2}")
    else:
        warn("安装后仍未找到，请重新打开终端后再试（PATH 可能尚未生效）")

def _arm_gcc_linux(auto: bool):
    dist_id, dist_like = _distro()
    is_deb = dist_id in ("ubuntu","debian","linuxmint","pop","elementary","raspbian") \
             or "debian" in dist_like or "ubuntu" in dist_like
    is_arch = dist_id in ("arch","manjaro","endeavouros","artix") or "arch" in dist_like
    is_rpm  = dist_id in ("fedora","rhel","centos","rocky","almalinux") \
              or "fedora" in dist_like or "rhel" in dist_like
    is_suse = "suse" in dist_id or "suse" in dist_like

    if is_deb:
        if auto or ask("使用 apt 安装 gcc-arm-none-eabi？"):
            _run(["sudo", "apt-get", "update", "-qq"], capture=False)
            r = _run(["sudo", "apt-get", "install", "-y",
                      "gcc-arm-none-eabi", "binutils-arm-none-eabi"], capture=False)
            if r.returncode != 0:
                warn("apt 失败，改为下载预编译包...")
                _arm_gcc_download(auto)
    elif is_arch:
        if auto or ask("使用 pacman 安装？"):
            _run(["sudo", "pacman", "-S", "--noconfirm",
                  "arm-none-eabi-gcc", "arm-none-eabi-binutils"], capture=False)
    elif is_rpm:
        pm = "dnf" if _which("dnf") else "yum"
        if auto or ask(f"使用 {pm} 安装？"):
            _run(["sudo", pm, "install", "-y",
                  "arm-none-eabi-gcc-cs", "arm-none-eabi-binutils-cs"], capture=False)
    elif is_suse:
        if auto or ask("使用 zypper 安装？"):
            _run(["sudo", "zypper", "install", "-y",
                  "cross-arm-none-eabi-gcc", "cross-arm-none-eabi-binutils"], capture=False)
    else:
        _arm_gcc_download(auto)

def _arm_gcc_mac(auto: bool):
    if _which("brew"):
        if auto or ask("使用 Homebrew 安装 arm-none-eabi-gcc？"):
            _run(["brew", "install", "arm-none-eabi-gcc"], capture=False)
    else:
        warn("未检测到 Homebrew")
        if auto or ask("先安装 Homebrew 再装工具链？"):
            _run(["/bin/bash", "-c",
                  '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'],
                 capture=False)
            _run(["brew", "install", "arm-none-eabi-gcc"], capture=False)
        else:
            _arm_gcc_download(auto)

def _arm_gcc_win(auto: bool):
    if _which("winget"):
        if auto or ask("使用 winget 安装 Arm GNU Toolchain？"):
            _run(["winget", "install", "--id", "Arm.GnuArmEmbeddedToolchain",
                  "--accept-source-agreements", "--accept-package-agreements"], capture=False)
        return
    if _which("choco"):
        if auto or ask("使用 Chocolatey 安装？"):
            _run(["choco", "install", "gcc-arm-embedded", "-y"], capture=False)
        return
    _arm_gcc_download(auto)

def _arm_gcc_download(auto: bool):
    URLS = {
        ("linux",   "x86_64"):  "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-x86_64-arm-none-eabi.tar.xz",
        ("linux",   "aarch64"): "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-aarch64-arm-none-eabi.tar.xz",
        ("darwin",  "x86_64"):  "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-darwin-x86_64-arm-none-eabi.tar.xz",
        ("darwin",  "arm64"):   "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-darwin-arm64-arm-none-eabi.tar.xz",
        ("windows", "x86_64"):  "https://developer.arm.com/-/media/Files/downloads/gnu/13.2.rel1/binrel/arm-gnu-toolchain-13.2.rel1-mingw-w64-i686-arm-none-eabi.zip",
    }
    sys_k = SYSTEM.lower()
    arch = MACHINE.lower()
    arch_k = "arm64" if arch == "arm64" else "aarch64" if "aarch" in arch else "x86_64"
    key = (sys_k, arch_k)
    if key not in URLS:
        warn("没有适合此平台的预编译包，请手动下载：")
        info("  https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads")
        return
    url = URLS[key]
    install_dir = Path("/opt/arm-toolchain") if not IS_WIN else Path("C:/arm-toolchain")
    if not (auto or ask(f"从 ARM 官网下载安装到 {install_dir}（约 120 MB）？")):
        info("已跳过，请手动安装")
        return

    import tempfile, tarfile, zipfile
    tmp = Path(tempfile.mkdtemp())
    fmt = "zip" if url.endswith(".zip") else "tar.xz"
    archive = tmp / f"arm-toolchain.{fmt}"
    if not _download(url, archive, "arm-gnu-toolchain"):
        return

    info(f"解压到 {install_dir} ...")
    try:
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "tar.xz":
            with tarfile.open(archive, "r:xz") as tf:
                tf.extractall(install_dir.parent)
            extracted = [d for d in install_dir.parent.iterdir()
                         if d.is_dir() and "arm-gnu-toolchain" in d.name]
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
        info("  重新打开终端或 source ~/.bashrc 使 PATH 生效")
    shutil.rmtree(tmp, ignore_errors=True)

def _add_to_path(new_path: str):
    home = Path.home()
    if IS_MAC:
        candidates = [home / ".zshrc", home / ".bash_profile", home / ".bashrc"]
    elif IS_LINUX:
        candidates = [home / ".bashrc", home / ".zshrc", home / ".profile"]
    else:
        return
    line = f'\nexport PATH="{new_path}:$PATH"  # arm-none-eabi\n'
    for sh in candidates:
        if sh.exists():
            if new_path not in sh.read_text():
                with open(sh, "a") as f:
                    f.write(line)
            info(f"  PATH 已写入 {sh}")
            return
    if candidates:
        candidates[0].write_text(line)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Python 依赖包
# ─────────────────────────────────────────────────────────────────────────────
PYTHON_PKGS = [
    ("openai",        "openai",        True),
    ("rich",          "rich",          True),
    ("prompt_toolkit","prompt_toolkit",True),
    ("pyocd",         "pyocd",         True),
    ("serial",        "pyserial",      True),
    ("requests",      "requests",      True),
    ("bs4",           "beautifulsoup4",False),
    ("docx",          "python-docx",   False),
    ("PIL",           "Pillow",        True),
    ("pyautogui",     "pyautogui",     False),
]

def install_python_packages(auto: bool):
    header("Step 3  Python 依赖包")
    _run(PIP + ["install", "--upgrade", "pip", "-q"], capture=False)

    missing_req = []
    missing_opt = []
    for imp, pkg, required in PYTHON_PKGS:
        try:
            __import__(imp)
            ok(f"{pkg}")
        except ImportError:
            (missing_req if required else missing_opt).append(pkg)
            warn(f"{pkg}  {'[必须]' if required else '[可选]'}")

    to_install = missing_req + missing_opt
    if not to_install:
        ok("所有依赖已就绪")
        return

    prompt = f"安装 {len(missing_req)} 个必需包"
    if missing_opt:
        prompt += f" + {len(missing_opt)} 个可选包"
    prompt += "？"

    if auto or ask(prompt):
        r = _run(PIP + ["install"] + to_install, capture=False)
        if r.returncode != 0:
            warn("批量安装失败，逐个安装...")
            for pkg in to_install:
                _run(PIP + ["install", pkg], capture=False)
    elif missing_req:
        info(f"必须包未安装，程序可能无法运行：{missing_req}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: 创建工作区目录
# ─────────────────────────────────────────────────────────────────────────────
def create_workspace():
    header("Step 4  工作区目录")
    for d in [HAL_DIR / "Inc", HAL_DIR / "Src", HAL_DIR / "CMSIS" / "Include",
              BUILD_DIR, PROJECTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    ok(f"workspace -> {WORKSPACE}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: STM32 HAL 库下载
# ─────────────────────────────────────────────────────────────────────────────
HAL_REPOS = {
    "f0": ("https://github.com/STMicroelectronics/stm32f0xx-hal-driver/archive/refs/heads/master.zip",
           "https://github.com/STMicroelectronics/cmsis_device_f0/archive/refs/heads/master.zip"),
    "f1": ("https://github.com/STMicroelectronics/stm32f1xx-hal-driver/archive/refs/heads/master.zip",
           "https://github.com/STMicroelectronics/cmsis_device_f1/archive/refs/heads/master.zip"),
    "f3": ("https://github.com/STMicroelectronics/stm32f3xx-hal-driver/archive/refs/heads/master.zip",
           "https://github.com/STMicroelectronics/cmsis_device_f3/archive/refs/heads/master.zip"),
    "f4": ("https://github.com/STMicroelectronics/stm32f4xx-hal-driver/archive/refs/heads/master.zip",
           "https://github.com/STMicroelectronics/cmsis_device_f4/archive/refs/heads/master.zip"),
}

CMSIS_CORE_FILES = {
    "core_cm0.h":       "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/core_cm0.h",
    "core_cm0plus.h":   "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/core_cm0plus.h",
    "core_cm3.h":       "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/core_cm3.h",
    "core_cm4.h":       "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/core_cm4.h",
    "cmsis_version.h":  "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_version.h",
    "cmsis_compiler.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_compiler.h",
    "cmsis_gcc.h":      "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_gcc.h",
    "cmsis_armcc.h":    "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_armcc.h",
    "cmsis_armclang.h": "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/cmsis_armclang.h",
    "mpu_armv7.h":      "https://raw.githubusercontent.com/ARM-software/CMSIS_5/5.9.0/CMSIS/Core/Include/mpu_armv7.h",
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
        r = _run(["sudo", "tee", str(rules_path)],
                 capture=False, input_text=_UDEV_RULES)
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
def setup_pyocd(auto: bool):
    header("Step 7  pyocd 芯片支持包（可选）")
    try:
        import pyocd
        ok(f"pyocd {pyocd.__version__}")
    except ImportError:
        warn("pyocd 未安装，跳过（请先完成 Step 3）")
        return

    r = _run([sys.executable, "-m", "pyocd", "pack", "find", "stm32f103"])
    if r.returncode == 0 and "stm32f103" in r.stdout.lower():
        ok("STM32F1 支持包已安装")
        return

    if auto or ask("安装 pyocd STM32F1/F4 支持包（约 30 MB）？"):
        info("更新 pack 索引...")
        _run([sys.executable, "-m", "pyocd", "pack", "update"], capture=False)
        info("安装 STM32F103x8 / STM32F407xx 支持包...")
        _run([sys.executable, "-m", "pyocd", "pack", "install",
              "STM32F103x8", "STM32F407xx"], capture=False)
        ok("pyocd 支持包安装完成")
    else:
        info("已跳过，pyocd 仍可通过通用 Cortex-M 模式自动识别大部分芯片")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: 安装 gary 命令
# ─────────────────────────────────────────────────────────────────────────────
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
    gary_path   = install_dir / "gary"

    if gary_path.exists():
        existing = gary_path.read_text()
        if str(AGENT_SCRIPT) in existing:
            ok(f"gary 命令已安装: {gary_path}")
            _ensure_path(install_dir)
            return
        else:
            info("检测到旧版 gary，更新中...")

    if not (auto or ask(f"安装 gary 命令到 {install_dir}？")):
        _show_manual_gary()
        return

    install_dir.mkdir(parents=True, exist_ok=True)
    content = _GARY_SH.format(
        agent_script=str(AGENT_SCRIPT),
        python=sys.executable
    )
    gary_path.write_text(content)
    gary_path.chmod(gary_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    ok(f"gary 命令已安装: {gary_path}")
    _ensure_path(install_dir)

def _install_gary_win(auto: bool):
    scripts_dir = Path(sys.executable).parent / "Scripts"
    if not scripts_dir.exists():
        scripts_dir = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Scripts"
    gary_bat = scripts_dir / "gary.bat"

    if not (auto or ask(f"安装 gary.bat 到 {scripts_dir}？")):
        _show_manual_gary()
        return

    content = _GARY_BAT.format(
        agent_script=str(AGENT_SCRIPT),
        python=sys.executable
    )
    gary_bat.write_text(content, encoding="utf-8")
    ok(f"gary.bat 已安装: {gary_bat}")
    info(f"  确认 {scripts_dir} 已在 PATH 中")

def _ensure_path(bin_dir: Path):
    path_env = os.environ.get("PATH", "")
    if str(bin_dir) in path_env:
        return

    home = Path.home()
    if IS_MAC:
        candidates = [home / ".zshrc", home / ".bash_profile"]
    else:
        candidates = [home / ".bashrc", home / ".zshrc"]

    line = f'\nexport PATH="$HOME/.local/bin:$PATH"  # gary command\n'
    for sh in candidates:
        if sh.exists():
            if ".local/bin" not in sh.read_text():
                with open(sh, "a") as f:
                    f.write(line)
                info(f"  PATH 已写入 {sh}（重新打开终端后生效）")
            return
    if candidates:
        candidates[0].write_text(line)

    os.environ["PATH"] = str(bin_dir) + os.pathsep + path_env

def _show_manual_gary():
    info("手动安装方法（任选其一）：")
    info(f"  ln -s {AGENT_SCRIPT} ~/.local/bin/gary")
    info(f"  chmod +x ~/.local/bin/gary")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 9: 最终验证
# ─────────────────────────────────────────────────────────────────────────────
def verify():
    header("验证  环境总览")
    status = {}

    cur_key, cur_url, cur_model = _read_current_ai_config()
    placeholder = ("YOUR_API_KEY", "", "sk-YOUR")
    ai_ok = bool(cur_key and not any(cur_key.startswith(p) for p in placeholder))
    if ai_ok:
        ok(f"AI 接口: {cur_model}  ({cur_url[:50]})")
        ok(f"API Key: {_mask_key(cur_key)}")
    else:
        err("AI 接口: 未配置 API Key -> 请运行 python3 setup.py 重新配置")
    status["ai"] = ai_ok

    ver = _gcc_ver()
    if ver:
        ok(f"arm-none-eabi-gcc  {ver[:70]}")
        status["gcc"] = True
    else:
        err("arm-none-eabi-gcc  未找到")
        status["gcc"] = False

    pkg_ok = {}
    for imp, pkg, required in PYTHON_PKGS:
        try:
            __import__(imp)
            ok(f"Python: {pkg}")
            pkg_ok[pkg] = True
        except Exception:
            (warn if not required else err)(f"Python: {pkg}  {'[必须]' if required else '[可选]'}")
            pkg_ok[pkg] = False
    status["python"] = all(pkg_ok.get(pkg, True) for _, pkg, req in PYTHON_PKGS if req)

    hal_any = False
    for fam in HAL_REPOS:
        hal_h   = HAL_DIR / "Inc" / f"stm32{fam}xx_hal.h"
        src_cnt = len(list((HAL_DIR / "Src").glob(f"stm32{fam}xx_hal*.c"))) if (HAL_DIR / "Src").exists() else 0
        if hal_h.exists():
            ok(f"HAL: stm32{fam}xx  ({src_cnt} 个源文件)")
            hal_any = True
        else:
            warn(f"HAL: stm32{fam}xx  未安装")
    cmsis_ok = (HAL_DIR / "CMSIS" / "Include" / "core_cm3.h").exists()
    (ok if cmsis_ok else warn)(f"ARM CMSIS Core  {'OK' if cmsis_ok else '未找到'}")
    status["hal"] = hal_any and cmsis_ok

    gary_bin = shutil.which("gary")
    if gary_bin:
        ok(f"gary 命令  {gary_bin}")
        status["gary"] = True
    else:
        warn("gary 命令  未在 PATH 中（可能需要重新打开终端）")
        status["gary"] = False

    print()
    all_ok = status["ai"] and status["gcc"] and status["python"] and status["hal"]
    if all_ok:
        print(_c("1;32", "  +==========================================+"))
        print(_c("1;32", "  |   环境就绪！Gary Dev Agent 可以使用      |"))
        print(_c("1;32", "  +==========================================+"))
        print()
        print("  使用方式：")
        print(f"    {_c('36', 'gary')}                          启动交互式对话助手")
        print(f"    {_c('36', 'gary do \"让 PA0 LED 以 500ms 闪烁\"')}  一次性执行任务")
        print(f"    {_c('36', 'gary --connect')}                 连接探针后启动")
        print()
        if not status["gary"]:
            print(_c("33", "  !! gary 命令尚未在当前 shell 生效，请执行："))
            print(f"    {_c('36', 'source ~/.bashrc')}  或重新打开终端")
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
    parser.add_argument("--auto",  action="store_true", help="全自动，不询问")
    parser.add_argument("--check", action="store_true", help="仅检查环境")
    parser.add_argument("--hal",   nargs="*",           help="仅下载 HAL（可选: f0 f1 f3 f4）")
    args = parser.parse_args()

    print(_c("1;35", """
  +================================================+
  |      Gary Dev Agent  -  一键环境安装           |
  |  STM32 AI 嵌入式开发助手  跨平台部署脚本       |
  +================================================+"""))
    print(f"  平台: {_c('36', f'{SYSTEM} {MACHINE}')}  |  "
          f"Python: {_c('36', sys.version.split()[0])}  |  "
          f"目录: {_c('36', str(SCRIPT_DIR))}")

    try:
        if args.check:
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

        check_python()
        configure_ai(auto=args.auto)
        install_arm_gcc(auto=args.auto)
        install_python_packages(auto=args.auto)
        create_workspace()
        download_hal(auto=args.auto)
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
        # Windows 下双击运行时保持窗口不自动关闭
        if IS_WIN and sys.stdin and sys.stdin.isatty():
            print()
            input("  按回车键关闭窗口...")

if __name__ == "__main__":
    main()
