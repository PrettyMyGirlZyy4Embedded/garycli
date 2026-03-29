"""
STM32 Agent 配置文件（云端优先）

说明：
1. server.py + compiler.py 依赖本文件中的服务器/编译配置。
2. 客户端硬件配置已迁移到 client/client_config.py。
3. 下面保留的少量“单机遗留参数”仅用于兼容旧版 stm32_agent.py 参考运行。
"""

import os
from pathlib import Path

# ================= 网络代理 =================
# 国内服务商（智谱/DeepSeek/通义千问）不需要代理，注释掉即可
# os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
# os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
# os.environ["GRPC_PROXY_EXP"] = "http://127.0.0.1:7890"

AI_TEMPERATURE = 1  # 低温度保证代码稳定性

# ================= 编译工具链 =================
ARM_GCC = "arm-none-eabi-gcc"
ARM_OBJCOPY = "arm-none-eabi-objcopy"
ARM_AR = "arm-none-eabi-ar"
ARM_SIZE = "arm-none-eabi-size"

# ================= 目录结构 =================
BASE_DIR = Path(__file__).parent
WORKSPACE = BASE_DIR / "workspace"
BUILD_DIR = WORKSPACE / "build"
PROJECTS_DIR = WORKSPACE / "projects"
HAL_DIR = WORKSPACE / "hal"
RTOS_DIR = WORKSPACE / "rtos"

# ================= 调试参数 =================
MAX_DEBUG_ATTEMPTS = 5
REGISTER_READ_DELAY = 0.3  # 读寄存器前等待时间（秒）
POST_FLASH_DELAY = 1.5  # 烧录后等待程序启动时间（秒）
UART_READ_TIMEOUT = 3  # 串口读取超时（秒）

# ================= 默认目标芯片 =================
DEFAULT_CHIP = "STM32F103C8T6"
DEFAULT_CLOCK = "HSI_internal"

AI_API_KEY = "sk-Vcadu6rEVtWMzf2H2BXiqasaNkCFQQpbaKOAV3PybqYTXOPm"
AI_BASE_URL = "https://api.moonshot.cn/v1"
AI_MODEL = "kimi-k2.5"
