"""Disk-backed member memory helpers for Gary."""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

MEMBER_MD_PATH = Path(__file__).resolve().parent.parent / "member.md"
MEMBER_PROMPT_CHAR_LIMIT = 12000
MEMBER_PROMPT_MAX_DYNAMIC = 24
MEMBER_MAX_FILE_CHARS = 40000
MEMBER_MAX_DYNAMIC_ENTRIES = 120
_MEMBER_LOCK = threading.RLock()


def _default_member_content() -> str:
    """Return the default member memory template."""

    return """# Gary Member Memory

## Focus
- 这里只记录高价值、可复用、能提高成功率的经验。
- 自动写入：关闭。由 Gary 自主决定何时写入或删除经验。
- 主动写入：遇到关键初始化顺序、硬件坑、寄存器判定经验、稳定模板时，调用 `gary_save_member_memory`。
- 主动删除：发现错误、过时、无用经验时，调用 `gary_delete_member_memory`。
- 经验必须短、具体、可执行，不要粘贴大段原始日志。

## Memories

### [Pinned] 启动标记优先
- UART 初始化后立刻打印 `Gary:BOOT`，再初始化 I2C/SPI/TIM/OLED 等外设。
- 这样即使后续外设卡死，也能先确认程序已启动。

### [Pinned] 裸机 HAL_Delay 依赖 SysTick_Handler
- 裸机代码必须定义 `void SysTick_Handler(void) { HAL_IncTick(); }`。
- 否则 `HAL_Delay()` 会永久阻塞。

### [Pinned] I2C 外设先探测再使用
- 初始化后先 `HAL_I2C_IsDeviceReady()` 检查从设备是否应答。
- 无应答优先怀疑接线或地址，不要盲改业务逻辑。

### [Pinned] 增量修改优先精确替换
- 修改已有工程时优先 `str_replace_edit` + `stm32_recompile`。
- 不要无必要地整文件重写。

### [Pinned] 裸机禁止 sprintf/printf/malloc
- 裸机项目优先手写轻量调试输出，避免 `_sbrk/end` 链接错误。
"""


def _ensure_member_file() -> Path:
    """Create `member.md` on first use and return its path."""

    with _MEMBER_LOCK:
        if not MEMBER_MD_PATH.exists():
            MEMBER_MD_PATH.write_text(_default_member_content(), encoding="utf-8")
    return MEMBER_MD_PATH


def _normalize_member_text(value: Any, limit: int = 220) -> str:
    """Normalize one piece of memory text into a compact single line."""

    text = re.sub(r"\s+", " ", str(value or "")).strip(" -\t\r\n")
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def _member_text_to_lines(
    value: Any,
    per_line_limit: int = 220,
    max_lines: int = 8,
) -> list[str]:
    """Split arbitrary text into normalized member entry lines."""

    source = str(value or "").replace("\r", "\n")
    lines: list[str] = []
    for raw in source.splitlines():
        line = _normalize_member_text(raw, limit=per_line_limit)
        if line:
            lines.append(line)
        if len(lines) >= max_lines:
            break
    if not lines:
        single = _normalize_member_text(source, limit=per_line_limit)
        if single:
            lines.append(single)
    return lines


def _split_member_content(text: str) -> tuple[str, list[str]]:
    """Split member markdown into the header section and memory entries."""

    source = (text or "").strip()
    if not source:
        source = _default_member_content().strip()
    if "## Memories" not in source:
        source = _default_member_content().strip() + "\n\n" + source
    before, _, after = source.partition("## Memories")
    header = before.rstrip() + "\n\n## Memories\n"
    entries = [
        chunk.strip() for chunk in re.split(r"(?m)(?=^### )", after.strip()) if chunk.strip()
    ]
    return header, entries


def _prune_member_content(text: str) -> str:
    """Prune member content to the configured file-size limits."""

    header, entries = _split_member_content(text)
    pinned = [entry for entry in entries if entry.startswith("### [Pinned]")]
    dynamic = [entry for entry in entries if not entry.startswith("### [Pinned]")]
    dynamic = dynamic[-MEMBER_MAX_DYNAMIC_ENTRIES:]

    kept: list[str] = []
    total = len(header)
    for entry in pinned:
        needed = len(entry) + 2
        if kept and total + needed > MEMBER_MAX_FILE_CHARS:
            break
        kept.append(entry)
        total += needed

    recent: list[str] = []
    for entry in reversed(dynamic):
        needed = len(entry) + 2
        if recent and total + needed > MEMBER_MAX_FILE_CHARS:
            break
        recent.append(entry)
        total += needed
    recent.reverse()
    kept.extend(recent)

    content = header.rstrip() + "\n\n" + "\n\n".join(kept).strip()
    return content.strip() + "\n"


def _append_member_memory(
    title: str,
    experience: str,
    tags: list[str] | None = None,
    source: str = "manual",
    importance: str = "high",
) -> dict[str, Any]:
    """Append one normalized memory entry into `member.md`."""

    clean_title = _normalize_member_text(title, limit=120)
    lines = _member_text_to_lines(experience, per_line_limit=220, max_lines=10)
    if not clean_title or not lines:
        return {"success": False, "message": "title 或 experience 为空"}

    normalized_tags = [
        _normalize_member_text(tag, limit=24)
        for tag in (tags or [])
        if _normalize_member_text(tag, limit=24)
    ][:10]
    clean_source = _normalize_member_text(source, limit=40) or "manual"
    clean_importance = _normalize_member_text(importance, limit=16) or "high"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry_lines = [
        f"### [{timestamp}] {clean_title}",
        f"- importance: {clean_importance}",
        f"- source: {clean_source}",
    ]
    if normalized_tags:
        entry_lines.append(f"- tags: {', '.join(normalized_tags)}")
    entry_lines.extend(f"- {line}" for line in lines)
    entry = "\n".join(entry_lines)

    with _MEMBER_LOCK:
        path = _ensure_member_file()
        current = path.read_text(encoding="utf-8")
        _, existing_entries = _split_member_content(current)
        normalized_lines = [_normalize_member_text(line, limit=220).lower() for line in lines]
        for existing in existing_entries:
            normalized_entry = re.sub(r"\s+", " ", existing).lower()
            if clean_title.lower() not in normalized_entry:
                continue
            if all(line in normalized_entry for line in normalized_lines):
                return {
                    "success": True,
                    "deduplicated": True,
                    "path": str(path),
                    "message": f"member.md 已存在相似经验: {clean_title}",
                }
        updated = _prune_member_content(current.rstrip() + "\n\n" + entry + "\n")
        path.write_text(updated, encoding="utf-8")

    return {
        "success": True,
        "deduplicated": False,
        "path": str(MEMBER_MD_PATH),
        "message": f"已写入 member.md: {clean_title}",
    }


def gary_save_member_memory(
    title: str,
    experience: str,
    tags: list[str] | None = None,
    importance: str = "high",
) -> dict[str, Any]:
    """Write a high-value reusable experience into Gary's member memory."""

    return _append_member_memory(
        title=title,
        experience=experience,
        tags=tags or [],
        source="model",
        importance=importance,
    )


def gary_delete_member_memory(
    query: str,
    *,
    dry_run: bool = False,
    include_pinned: bool = False,
    max_matches: int = 10,
) -> dict[str, Any]:
    """Delete matching entries from `member.md` by query."""

    needle = _normalize_member_text(query, limit=120)
    if len(needle) < 2:
        return {"success": False, "message": "query 至少需要 2 个字符"}

    with _MEMBER_LOCK:
        path = _ensure_member_file()
        current = path.read_text(encoding="utf-8")
        header, entries = _split_member_content(current)

        matched: list[str] = []
        kept: list[str] = []
        normalized_needle = needle.lower()
        for entry in entries:
            is_pinned = entry.startswith("### [Pinned]")
            haystack = re.sub(r"\s+", " ", entry).lower()
            if normalized_needle in haystack and (include_pinned or not is_pinned):
                matched.append(entry)
            else:
                kept.append(entry)

        if not matched:
            return {
                "success": False,
                "path": str(path),
                "message": f"未找到匹配经验: {needle}",
                "matched_titles": [],
            }

        if max_matches > 0 and len(matched) > max_matches:
            titles = [
                entry.splitlines()[0].removeprefix("### ").strip()
                for entry in matched[:max_matches]
            ]
            return {
                "success": False,
                "path": str(path),
                "message": f"匹配经验过多 ({len(matched)})，请给出更精确的 query",
                "matched_titles": titles,
                "match_count": len(matched),
            }

        titles = [entry.splitlines()[0].removeprefix("### ").strip() for entry in matched]
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "path": str(path),
                "matched_titles": titles,
                "match_count": len(matched),
                "message": f"将删除 {len(matched)} 条经验（dry_run）",
            }

        updated = header.rstrip()
        if kept:
            updated += "\n\n" + "\n\n".join(kept)
        path.write_text(updated.strip() + "\n", encoding="utf-8")

    return {
        "success": True,
        "dry_run": False,
        "path": str(path),
        "deleted_titles": titles,
        "deleted_count": len(titles),
        "message": f"已删除 {len(titles)} 条经验",
    }


def _infer_code_tags(code: str) -> list[str]:
    """Infer compact tags from a generated STM32 source file."""

    text = code or ""
    checks = [
        (
            "rtos",
            any(token in text for token in ("FreeRTOS.h", "xTaskCreate", "vTaskDelay(", "task.h")),
        ),
        ("uart", "HAL_UART_" in text or "USART" in text),
        ("debug_print", "Debug_Print(" in text or "Debug_PrintInt(" in text),
        ("boot_marker", "Gary:BOOT" in text),
        ("systick", "SysTick_Handler" in text),
        ("i2c", "HAL_I2C_" in text or "I2C_HandleTypeDef" in text),
        ("spi", "HAL_SPI_" in text or "SPI_HandleTypeDef" in text),
        ("adc", "HAL_ADC_" in text or "ADC_HandleTypeDef" in text),
        ("pwm", "HAL_TIM_PWM_" in text or "TIM_HandleTypeDef" in text),
        ("oled", "OLED_" in text),
        ("sensor_check", "HAL_I2C_IsDeviceReady" in text),
        ("fault_analysis", "HardFault" in text or "SCB_CFSR" in text),
    ]
    tags = [name for name, matched in checks if matched]
    if "rtos" not in tags:
        tags.insert(0, "baremetal")
    return tags[:10]


def _derive_success_patterns_from_code(code: str) -> list[str]:
    """Derive reusable success heuristics from a known-good code sample."""

    text = code or ""
    patterns: list[str] = []
    if "Gary:BOOT" in text and ("MX_USART" in text or "HAL_UART_Init" in text):
        patterns.append("UART 初始化后会尽早打印 Gary:BOOT，启动链路更容易确认。")
    if "SysTick_Handler" in text and "FreeRTOS.h" not in text:
        patterns.append("裸机代码显式定义 SysTick_Handler，HAL_Delay 不会卡死。")
    if "vApplicationTickHook" in text:
        patterns.append("FreeRTOS 项目通过 vApplicationTickHook 维持 HAL tick。")
    if "HAL_I2C_IsDeviceReady" in text:
        patterns.append("I2C 设备在使用前会先做在线探测。")
    if "Debug_Print(" in text or "Debug_PrintInt(" in text:
        patterns.append("代码保留了轻量串口调试输出，便于运行时定位问题。")
    if "xTaskCreate" in text:
        patterns.append("当前成功模板已经包含可编译的 FreeRTOS 任务结构。")
    if "str_replace_edit" in text:
        patterns.append("此模板来自增量修改链路，适合继续做精准替换。")
    return patterns[:5]


def _record_success_memory(
    event_type: str,
    code: str,
    result: Mapping[str, Any] | None = None,
    request: str = "",
    steps: Sequence[Mapping[str, Any]] | None = None,
    chip: str = "",
    log_error: Callable[[str], None] | None = None,
) -> None:
    """Compatibility no-op: member entries must be written explicitly by Gary."""

    del event_type, code, result, request, steps, chip, log_error
    return None


def _member_preview_markdown(max_dynamic: int = 10, path_label: str = "Path") -> str:
    """Build a markdown preview of the pinned and most recent member entries."""

    with _MEMBER_LOCK:
        path = _ensure_member_file()
        current = path.read_text(encoding="utf-8")
    header, entries = _split_member_content(current)
    pinned = [entry for entry in entries if entry.startswith("### [Pinned]")]
    dynamic = [entry for entry in entries if not entry.startswith("### [Pinned]")]
    selected = pinned + dynamic[-max_dynamic:]
    body = header.rstrip()
    if selected:
        body += "\n\n" + "\n\n".join(selected)
    return f"**{path_label}:** `{path}`\n\n{body.strip()}"


__all__ = [
    "MEMBER_MAX_DYNAMIC_ENTRIES",
    "MEMBER_MAX_FILE_CHARS",
    "MEMBER_MD_PATH",
    "MEMBER_PROMPT_CHAR_LIMIT",
    "MEMBER_PROMPT_MAX_DYNAMIC",
    "_MEMBER_LOCK",
    "_append_member_memory",
    "_derive_success_patterns_from_code",
    "_ensure_member_file",
    "_infer_code_tags",
    "_member_preview_markdown",
    "_prune_member_content",
    "_record_success_memory",
    "_split_member_content",
    "gary_delete_member_memory",
    "gary_save_member_memory",
]
