"""
STM32 Agent 配置文件（云端优先）

说明：
1. server.py + compiler.py 依赖本文件中的服务器/编译配置。
2. 客户端硬件配置已迁移到 client/client_config.py。
3. 下面保留的少量“单机遗留参数”仅用于兼容旧版 stm32_agent.py 参考运行。
"""
import os
from pathlib import Path


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

# ================= 单机遗留参数（兼容旧版） =================
SWDIO_GPIO = 72   # 物理 Pin 18 → STM32 SWDIO (PA13)
SWCLK_GPIO = 73   # 物理 Pin 22 → STM32 SWCLK (PA14)
SRST_GPIO = 70    # 物理 Pin 16 → STM32 NRST (可选，设为 None 不使用)

# ================= 串口 (UART 监控) =================
# 香橙派 TX → STM32 PA10(RX)，香橙派 RX → STM32 PA9(TX)
SERIAL_PORT = "/dev/ttyS5"  # 香橙派 Zero3 UART5
SERIAL_BAUD = 115200

# ================= OpenOCD =================
OPENOCD_BIN = "openocd"
OPENOCD_TELNET_PORT = 4444

# ================= Web 服务器 =================
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000

# ================= 调试参数 =================
MAX_DEBUG_ATTEMPTS = 5
REGISTER_READ_DELAY = 0.3  # 读寄存器前等待时间（秒）
POST_FLASH_DELAY = 1.5     # 烧录后等待程序启动时间（秒）
UART_READ_TIMEOUT = 3      # 串口读取超时（秒）

# ================= 默认目标芯片 =================
DEFAULT_CHIP = "STM32F103C8T6"
DEFAULT_CLOCK = "HSI_internal"

# ================= 服务器配置 =================
KEYS_DB_PATH = BASE_DIR / "keys.db"
SESSION_TTL = 7200      # 会话过期时间（秒）
BINARY_TTL = 600        # 编译产物缓存时间（秒）
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
