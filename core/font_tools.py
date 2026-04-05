"""STM32 font generation helpers."""

from __future__ import annotations

import os
import subprocess
from typing import Optional


def stm32_generate_font(text: str, size: int = 16) -> dict:
    """
    将任意文字（含中文）渲染为 STM32 OLED 用的 C 点阵数组。
    固定使用「横向取模·高位在前（row-major, MSB=left）」格式。
    """

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {"success": False, "message": "需要安装 Pillow: pip install Pillow"}

    def _find_cjk_font() -> Optional[str]:
        """动态查找系统 CJK 字体路径。"""

        try:
            result = subprocess.run(
                ["fc-match", "--format=%{file}", ":lang=zh"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip()
                if os.path.exists(path):
                    return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/arphic/uming.ttc",
            "/usr/share/fonts/truetype/arphic/ukai.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    font_path = _find_cjk_font()
    if font_path is None:
        return {"success": False, "message": "未找到中文字体，请安装 fonts-noto-cjk"}
    try:
        font = ImageFont.truetype(font_path, size)
    except Exception as exc:
        return {"success": False, "message": f"字体加载失败 ({font_path}): {exc}"}

    def _render_char(char: str) -> list[int]:
        """渲染单个字符到 size×size 位图，返回 0/1 列表（行优先）。"""

        img = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(img)
        try:
            bbox = font.getbbox(char)
            char_w = bbox[2] - bbox[0]
            ox = (size - char_w) // 2 - bbox[0]
            oy = -bbox[1]
        except Exception:
            ox, oy = 0, 0
        draw.text((ox, oy), char, fill=255, font=font)
        return [1 if pixel > 127 else 0 for pixel in img.getdata()]

    def _to_row_msb(pixels: list[int]) -> list[int]:
        """横向取模·高位在前：每行从左到右，bit7=最左列。"""

        data: list[int] = []
        bytes_per_row = (size + 7) // 8
        for row in range(size):
            for byte_index in range(bytes_per_row):
                byte = 0
                for bit in range(8):
                    col = byte_index * 8 + bit
                    if col < size and pixels[row * size + col]:
                        byte |= 1 << (7 - bit)
                data.append(byte)
        return data

    def _ascii_preview(pixels: list[int]) -> str:
        lines = []
        for row in range(size):
            lines.append("".join("█" if pixels[row * size + col] else "." for col in range(size)))
        return "\n".join(lines)

    chars_data = []
    previews = []
    char_list = []
    for char in text:
        pixels = _render_char(char)
        chars_data.append(_to_row_msb(pixels))
        previews.append(_ascii_preview(pixels))
        char_list.append(char)

    bytes_per_char = size * ((size + 7) // 8)
    font_name = f"FONT_{size}x{size}"

    char_entries = []
    for index, (char, data) in enumerate(zip(char_list, chars_data)):
        hex_str = ", ".join(f"0x{byte:02X}" for byte in data)
        char_repr = char if ord(char) < 128 else f"{char}(U+{ord(char):04X})"
        char_entries.append(f"    /* [{index}] '{char_repr}' */\n    {{{hex_str}}}")

    array_code = (
        f"/* ═══ 字模数据：横向取模·高位在前 {size}x{size}px ═══\n"
        f"   格式：每行 {(size + 7) // 8} 字节，bit7=最左列，共 {bytes_per_char} 字节/字符\n"
        f"   字符表: {' '.join(repr(char) for char in char_list)} */\n"
        f"static const uint8_t {font_name}[][{bytes_per_char}] = {{\n"
        + ",\n".join(char_entries)
        + "\n};\n"
    )

    display_func = f"""
/* ═══ 配套显示函数（必须与上面字模数据一起使用）═══ */
/* idx: 字符在 {font_name} 中的下标（按字符表顺序） */
/* x,y: OLED 列(0-127)和页起始行(0-63)         */
void OLED_ShowFont{size}(uint8_t x, uint8_t y, uint8_t idx) {{
    const uint8_t *p = {font_name}[idx];
    uint8_t bytes_per_row = {(size + 7) // 8};
    for (uint8_t row = 0; row < {size}; row++) {{
        OLED_SetCursor(x, y + row);
        for (uint8_t b = 0; b < bytes_per_row; b++) {{
            uint8_t byte = p[row * bytes_per_row + b];
            for (int8_t bit = 7; bit >= 0; bit--) {{
                uint8_t col = b * 8 + (7 - bit);
                if (col < {size}) {{
                    OLED_DrawPixel(x + col, y + row, (byte >> bit) & 1);
                }}
            }}
        }}
    }}
}}
/* 用法示例：显示字符表第0个字符在 (0,0) 位置
   OLED_ShowFont{size}(0, 0, 0);  // 显示 '{char_list[0] if char_list else "?"}' */
"""

    preview_block = "\n\n".join(f"/* '{char}':\n{preview} */" for char, preview in zip(char_list, previews))

    return {
        "success": True,
        "c_code": array_code + display_func,
        "preview": preview_block,
        "char_count": len(text),
        "bytes_per_char": bytes_per_char,
        "font_size": size,
        "mode": "row_msb",
        "char_order": char_list,
    }


__all__ = ["stm32_generate_font"]
