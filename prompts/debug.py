"""Specialized debug prompt fragments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.platforms import detect_target_platform, is_micropython_target

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_COMPILE_ERROR_PROMPT = """## 编译失败专项诊断
- 优先读取编译错误首条和未定义符号，直接修复，不做泛泛分析。
- `undefined reference to _sbrk/end`：优先排查 `sprintf/printf/malloc`。
- `undefined reference to HAL_xxx`：优先检查 HAL 源文件、头文件和系列宏。
- `No such file` / `cannot find`：优先检查 include 路径、生成文件和工具链依赖。
- 若是增量修改造成的错误，优先 `str_replace_edit` + `stm32_recompile`，不要整文件重写。"""

_I2C_FAILURE_PROMPT = """## I2C 失败专项诊断
- 优先看 `SR1.AF`、`SR1.ARLO`、`SR2.BUSY`，先判断是设备未接、地址错误还是总线锁死。
- 先确认 `HAL_I2C_IsDeviceReady()` 是否存在，传感器地址是否使用 7-bit 左移规则。
- 若串口无 `Gary:BOOT`，怀疑初始化顺序不对，UART 打印必须早于 I2C/OLED/传感器初始化。
- 若外设未接，直接说明是硬件问题，停止继续修改业务逻辑。"""

_MICROPYTHON_COMPILE_PROMPT = """## MicroPython 语法诊断
- 优先修复工具返回的 `line` / `offset` / `snippet`，不要做无关重构。
- 常见问题：缩进不一致、缺冒号、括号不配对、字符串未闭合、`try/except` 结构错误。
- 若工具提示 `while_loop_missing_delay` 或要求给 `while` 加短延时，不要争论；直接在对应循环里加入 `time.sleep_ms(5)` 一类的节流语句。
- 若 `workspace/projects/latest_workspace/main.py` 不存在，说明当前还没有缓存源码；不要调用 `str_replace_edit`，直接生成完整 `main.py` 并用对应的 compile / auto_sync_cycle 创建缓存。
- 若报错涉及陌生模块、板级专有 API、第三方库或你不确定的语法/导入写法，先用 `browser_search -> browser_open_result` 查官方文档或示例，再修改代码。
- 若是增量修改造成的错误，优先 `str_replace_edit` + `stm32_recompile`，不要整文件重写。"""

_MICROPYTHON_RUNTIME_PROMPT = """## MicroPython 运行诊断
- 优先阅读串口里的 `Traceback`，按最后一层报错直接修复。
- 若没有任何输出，先确认 USB 串口连接，再确认 `print("Gary:BOOT")` 是否放在文件顶部附近。
- 空的 `uart_output` 不等于“程序已经在运行中”；没有串口证据时，只能说“运行未确认”。
- 若只看到 `boot.py` 打印的 `Gary:BOOT`，但没有 `Gary:RUN_START`、`Gary:RUN_ERROR`、`Gary:RUN_DONE` 或用户日志，也不能确认 `gary_run.py` 已运行。
- 涉及 I2C / OLED / 传感器时，先 `scan()` 或先探测，再进入主循环。
- 若工具返回 `MicroPython raw REPL 响应异常`、`进入 raw REPL 失败` 或 `raw_repl_failure=true`，优先怀疑当前板子还在执行上一次部署的 `gary_run.py` / 用户脚本：
  例如无延时的 `while True` 死循环、摄像头/显示循环、阻塞式初始化、或启动阶段长时间同步调用。
- 遇到 raw REPL 失败时，不要把它轻描淡写成“正常现象”或“不是工具链问题”；要把它当成当前程序导致的可修复调试问题来处理。
- 这类失败时，优先建议用户先调用板卡对应的 `*_soft_reset` 工具做软件复位；若仍无响应，再按 `RST` / 重新插拔 USB。
- 同一轮里，`*_soft_reset` 最多做 1 次；复位后的 `flash` / `auto_sync_cycle` 若仍失败，就停止继续 `connect` / `list_files` / `flash` / `auto_sync_cycle` 打转，直接向用户说明需要手动复位或先改代码。
- 下一版代码要尽早 `print("Gary:BOOT")`，并确保每个 `while` 循环里都带 `time.sleep_ms(5)` 一类的短延时。
- 若 `Traceback` 指向陌生模块、属性、方法、错误码或板级专有接口，先联网搜索官方文档 / 示例验证，再下结论。
- 在你准备说“这个平台没有某模块 / 不支持某 API”之前，先联网查证，不要凭记忆断言。
- 若工具只完成了语法检查而没有检测到串口，必须明确告诉用户当前没有运行时验证。"""


def _load_template(name: str) -> str:
    """Load a markdown debug template from disk."""

    return (_TEMPLATES_DIR / name).read_text(encoding="utf-8").strip()


def _render_context(context: dict[str, Any]) -> str:
    """Render extra debug context into a compact markdown block."""

    if not context:
        return ""
    lines = ["", "### 当前上下文"]
    for key, value in context.items():
        snippet = str(value).strip()
        if not snippet:
            continue
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        lines.append(f"- {key}: {snippet}")
    return "\n".join(lines) if len(lines) > 2 else ""


def _soft_reset_tool_name(chip: Any) -> str:
    platform = detect_target_platform(chip)
    if platform == "canmv":
        return "canmv_soft_reset"
    if platform == "rp2040":
        return "rp2040_soft_reset"
    if platform == "esp":
        return "esp_soft_reset"
    return "*_soft_reset"


def get_debug_prompt(error_type: str, context: dict[str, Any]) -> str:
    """Return a specialized debug prompt fragment for the requested error type."""

    normalized = (error_type or "").strip().lower()
    platform = detect_target_platform(context.get("chip"))
    if is_micropython_target(context.get("chip")):
        if normalized in {"compile", "compile_error", "build_error"}:
            prompt = _MICROPYTHON_COMPILE_PROMPT
        else:
            prompt = _MICROPYTHON_RUNTIME_PROMPT
            prompt += f"\n- 当前板卡优先使用 `{_soft_reset_tool_name(context.get('chip'))}` 做软件复位。"
    elif normalized in {"hardfault", "fault", "crash"}:
        prompt = _load_template("debug_hardfault.md")
    elif normalized in {"i2c", "i2c_failure", "sensor_i2c"}:
        prompt = _I2C_FAILURE_PROMPT
    elif normalized in {"compile", "compile_error", "build_error"}:
        prompt = _COMPILE_ERROR_PROMPT
    else:
        prompt = "## 通用诊断\n- 优先基于工具返回值和最新寄存器/串口结果做最小修改。"
    return prompt + _render_context(context)
