# ─────────────────────────────────────────────────────────────────
#  Gary Dev Agent  —  Windows 一键安装脚本 (PowerShell)
#  用法：irm https://garydo.dev/install.ps1 | iex
# ─────────────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"

$GARY_URL   = "https://garydo.dev/gary.tar.gz"
$GARY_DIR   = "$env:USERPROFILE\.gary"
$GARY_VENV  = "$GARY_DIR\.venv"
$TMP_FILE   = "$env:TEMP\gary_install.tar.gz"

function ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green  }
function info($msg) { Write-Host "  --> $msg"  -ForegroundColor Cyan   }
function warn($msg) { Write-Host "  [!] $msg"  -ForegroundColor Yellow }
function die($msg)  { Write-Host "  [X] $msg"  -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "  ║         Gary Dev Agent  安装程序         ║" -ForegroundColor Magenta
Write-Host "  ║      STM32 AI 嵌入式开发助手             ║" -ForegroundColor Magenta
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# ── 1. 检查 Python ───────────────────────────────────────────────
$PYTHON = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        & $cmd -c "import sys; v=sys.version_info; exit(0 if v.major==3 and v.minor>=8 else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $PYTHON = $cmd; break }
    } catch {}
}
if (-not $PYTHON) { die "需要 Python 3.8+，请从 https://python.org 下载安装" }
$pyver = & $PYTHON --version 2>&1
ok "Python: $pyver"

# ── 检查 venv 模块是否可用 ───────────────────────────────────────
try {
    & $PYTHON -m venv --help 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw }
} catch {
    die "Python venv 模块不可用，请确认 Python 安装完整（包含 venv）"
}

# ── 2. 检查下载工具 ──────────────────────────────────────────────
# PowerShell 内置 Invoke-WebRequest，无需额外检查
ok "下载工具: Invoke-WebRequest"

# ── 3. 备份旧版本 ────────────────────────────────────────────────
if (Test-Path $GARY_DIR) {
    $bak = "$GARY_DIR.bak.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    info "发现旧版本，备份到 $bak"
    Move-Item $GARY_DIR $bak
}

# ── 4. 下载项目包 ────────────────────────────────────────────────
info "下载 Gary ($GARY_URL)..."
try {
    Invoke-WebRequest -Uri $GARY_URL -OutFile $TMP_FILE -UseBasicParsing
    ok "下载完成"
} catch {
    die "下载失败：$($_.Exception.Message)，请检查网络或访问 https://garydo.dev"
}

# ── 5. 解压 ─────────────────────────────────────────────────────
info "解压到 $GARY_DIR ..."
New-Item -ItemType Directory -Force -Path $GARY_DIR | Out-Null
# 需要 Windows 10 1803+ 内置 tar
tar -xzf $TMP_FILE -C $GARY_DIR --strip-components=1
if ($LASTEXITCODE -ne 0) { die "解压失败，请确认系统支持 tar（Windows 10 1803+）" }
Remove-Item $TMP_FILE -Force
ok "解压完成"

# ── 6. 创建虚拟环境 ──────────────────────────────────────────────
info "创建虚拟环境 ($GARY_VENV)..."
& $PYTHON -m venv $GARY_VENV
if ($LASTEXITCODE -ne 0) { die "虚拟环境创建失败" }
$VENV_PYTHON = "$GARY_VENV\Scripts\python.exe"
$VENV_PIP    = "$GARY_VENV\Scripts\pip.exe"
ok "虚拟环境创建完成"

# 升级 pip（静默）
info "升级 pip..."
& $VENV_PIP install --quiet --upgrade pip
ok "pip 已就绪"

# ── 7. 在虚拟环境中运行 setup.py ────────────────────────────────
Write-Host ""
info "开始安装依赖并配置环境（虚拟环境隔离）..."
Write-Host ""
Set-Location $GARY_DIR
& $VENV_PYTHON setup.py --auto
if ($LASTEXITCODE -ne 0) { die "setup.py 执行失败" }

# ── 8. 生成 gary 启动包装脚本 ────────────────────────────────────
$LOCAL_BIN = "$env:USERPROFILE\.local\bin"
New-Item -ItemType Directory -Force -Path $LOCAL_BIN | Out-Null

$GARY_BAT = "$LOCAL_BIN\gary.bat"
@"
@echo off
set ALL_PROXY=
set all_proxy=
set HTTP_PROXY=
set http_proxy=
set HTTPS_PROXY=
set https_proxy=
"$GARY_VENV\Scripts\python.exe" -m gary %*
"@ | Set-Content -Encoding ASCII $GARY_BAT
ok "启动脚本已写入 $GARY_BAT"

# ── 9. 添加 %USERPROFILE%\.local\bin 到用户 PATH ─────────────────
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$LOCAL_BIN*") {
    [Environment]::SetEnvironmentVariable("PATH", "$LOCAL_BIN;$currentPath", "User")
    ok "已将 $LOCAL_BIN 写入用户 PATH"
    $PATH_ADDED = $true
} else {
    $PATH_ADDED = $false
}

# ── 10. 完成提示 ─────────────────────────────────────────────────
Write-Host ""
Write-Host "  ══════════════════════════════════════" -ForegroundColor Green
Write-Host "    安装完成！"                            -ForegroundColor Green
Write-Host "  ══════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  虚拟环境位置：$GARY_VENV" -ForegroundColor Cyan
Write-Host ""
Write-Host "  使用方法："
Write-Host "    gary                    启动交互式助手"
Write-Host "    gary do `"任务描述`"    一次性执行任务"
Write-Host "    gary --connect          连接 STM32 探针后启动"
Write-Host ""
if ($PATH_ADDED) {
    warn "请重新打开终端使 PATH 生效"
} else {
    Write-Host "  如果 gary 命令未找到，请重新打开终端"
}
Write-Host ""