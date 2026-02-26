#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  Gary Dev Agent  —  一键安装脚本
#  用法：curl -fsSL https://www.garycli.com/install | bash
# ─────────────────────────────────────────────────────────────────
set -e

GARY_URL="https://www.garycli.com/gary.tar.gz"
GARY_DIR="$HOME/.gary"
GARY_VENV="$GARY_DIR/.venv"
TMP_FILE="/tmp/gary_$$.tar.gz"

# ── 颜色 ────────────────────────────────────────────────────────
if [ -t 1 ]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
  YELLOW='\033[0;33m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; GREEN=''; CYAN=''; YELLOW=''; BOLD=''; RESET=''
fi

info()  { echo -e "  ${CYAN}→${RESET} $*"; }
ok()    { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()  { echo -e "  ${YELLOW}⚠${RESET} $*"; }
die()   { echo -e "  ${RED}✗${RESET} $*" >&2; exit 1; }

echo ""
echo -e "${BOLD}  ╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}  ║         Gary Dev Agent  安装程序         ║${RESET}"
echo -e "${BOLD}  ║      STM32 AI 嵌入式开发助手             ║${RESET}"
echo -e "${BOLD}  ╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. 检查 Python ──────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)")
    MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)")
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 8 ]; then
      PYTHON="$cmd"
      ok "Python $("$cmd" --version 2>&1 | awk '{print $2}')"
      break
    fi
  fi
done
[ -z "$PYTHON" ] && die "需要 Python 3.8 或更高版本。请先安装 Python: https://python.org"

# ── 检查 venv 模块是否可用 ───────────────────────────────────────
"$PYTHON" -m venv --help &>/dev/null \
  || die "Python venv 模块不可用。请安装：sudo apt install python3-venv"

# ── 2. 检查下载工具 ──────────────────────────────────────────────
if command -v curl &>/dev/null; then
  DOWNLOADER="curl"
elif command -v wget &>/dev/null; then
  DOWNLOADER="wget"
else
  die "需要 curl 或 wget。请先安装：sudo apt install curl"
fi
ok "下载工具: $DOWNLOADER"

# ── 3. 备份旧版本 ────────────────────────────────────────────────
if [ -d "$GARY_DIR" ]; then
  BAK="${GARY_DIR}.bak.$(date +%Y%m%d_%H%M%S)"
  info "发现旧版本，备份到 $BAK"
  mv "$GARY_DIR" "$BAK"
fi

# ── 4. 下载项目包 ────────────────────────────────────────────────
info "下载 Gary ($GARY_URL)..."
if [ "$DOWNLOADER" = "curl" ]; then
  curl -fsSL --progress-bar "$GARY_URL" -o "$TMP_FILE" \
    || die "下载失败，请检查网络或访问 https://www.garycli.com"
else
  wget -q --show-progress "$GARY_URL" -O "$TMP_FILE" \
    || die "下载失败，请检查网络或访问 https://www.garycli.com"
fi
ok "下载完成"

# ── 5. 解压 ────────────────────────────────────────────────────
info "解压到 $GARY_DIR ..."
mkdir -p "$GARY_DIR"
tar -xzf "$TMP_FILE" -C "$GARY_DIR" --strip-components=1
rm -f "$TMP_FILE"
ok "解压完成"

# ── 6. 创建虚拟环境 ──────────────────────────────────────────────
info "创建虚拟环境 ($GARY_VENV)..."
"$PYTHON" -m venv "$GARY_VENV"
VENV_PYTHON="$GARY_VENV/bin/python"
VENV_PIP="$GARY_VENV/bin/pip"
ok "虚拟环境创建完成"

# 升级 pip（静默）
info "升级 pip..."
"$VENV_PIP" install --quiet --upgrade pip
ok "pip 已就绪"

# ── 7. 在虚拟环境中运行 setup.py ────────────────────────────────
echo ""
info "开始安装依赖并配置环境（虚拟环境隔离）..."
echo ""
cd "$GARY_DIR"
"$VENV_PYTHON" setup.py --auto

# ── 8. 生成 gary 启动包装脚本 ────────────────────────────────────
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
GARY_BIN="$LOCAL_BIN/gary"

# 直接用 venv 路径写入，不用 realpath 避免符号链接被解析为系统 Python
cat > "$GARY_BIN" <<EOF
#!/usr/bin/env bash
# Gary Dev Agent — 启动脚本（由安装程序自动生成）
unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy
exec "$GARY_VENV/bin/python" "$GARY_DIR/stm32_agent.py" "\$@"
EOF
chmod +x "$GARY_BIN"
ok "启动脚本已写入 $GARY_BIN"

# ── 9. 确保 ~/.local/bin 在 PATH 中 ─────────────────────────────
PATH_ADDED=false
for RC in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
  if [ -f "$RC" ] && ! grep -q '\.local/bin' "$RC" 2>/dev/null; then
    echo '' >> "$RC"
    echo '# Gary Dev Agent' >> "$RC"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
    PATH_ADDED=true
    ok "已将 ~/.local/bin 写入 $RC"
    break
  fi
done

# ── 10. 完成提示 ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  ════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}    安装完成！${RESET}"
echo -e "${BOLD}${GREEN}  ════════════════════════════════════════${RESET}"
echo ""
echo -e "  虚拟环境位置：${CYAN}$GARY_VENV${RESET}"
echo ""
echo -e "  使用方法："
echo -e "    ${BOLD}gary${RESET}                     启动交互式助手"
echo -e "    ${BOLD}gary do \"任务描述\"${RESET}       一次性执行任务"
echo -e "    ${BOLD}gary --connect${RESET}            连接 STM32 探针后启动"
echo ""
if $PATH_ADDED; then
  echo -e "  ${YELLOW}⚠  请重新打开终端，或执行：source ~/.bashrc${RESET}"
else
  echo -e "  如果 gary 命令未找到，请执行：source ~/.bashrc"
fi
echo ""