"""UART ISP flashing helpers."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def flash_via_uart(
    bin_path: str,
    *,
    port: str,
    baud: int = 115200,
    address: str = "0x08000000",
    console: Any = None,
) -> dict[str, Any]:
    """Flash a binary over the STM32 ROM bootloader using stm32loader."""

    image_path = Path(bin_path)
    if not image_path.exists():
        return {"success": False, "message": f"文件不存在: {bin_path}"}
    if not port:
        return {"success": False, "message": "缺少串口端口，无法进行 UART ISP 烧录"}

    commands = [
        [
            sys.executable,
            "-m",
            "stm32loader.main",
            "-p",
            port,
            "-b",
            str(baud),
            "-e",
            "erase",
            "-w",
            str(image_path),
            "-v",
            "-g",
            address,
        ]
    ]
    executable = shutil.which("stm32loader")
    if executable:
        commands.append(
            [
                executable,
                "-p",
                port,
                "-b",
                str(baud),
                "-e",
                "erase",
                "-w",
                str(image_path),
                "-v",
                "-g",
                address,
            ]
        )

    last_error = "stm32loader 未安装: pip install stm32loader"
    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except Exception as exc:
            last_error = str(exc)
            continue
        if result.returncode == 0:
            output = (result.stdout or "").strip()
            return {
                "success": True,
                "message": output or f"UART ISP 烧录成功: {image_path.name}",
            }
        stderr = (result.stderr or result.stdout or "").strip()
        if console is not None:
            try:
                console.print(f"[yellow]  UART ISP 失败: {stderr[:200]}[/]")
            except Exception:
                pass
        last_error = stderr or f"stm32loader 返回码 {result.returncode}"

    return {"success": False, "message": last_error}


__all__ = ["flash_via_uart"]
