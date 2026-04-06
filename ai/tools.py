"""AI tool schemas and tool dispatch registry."""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Optional

from gary_skills import SKILL_TOOL_SCHEMAS, SKILL_TOOLS_MAP, init_skills
from stm32_extra_tools import EXTRA_TOOL_SCHEMAS, EXTRA_TOOLS_MAP

ToolHandler = Callable[..., Any]

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "stm32_list_probes",
            "description": "列出所有已连接的调试探针（ST-Link、CMSIS-DAP、J-Link）。连接前先调用此函数确认探针存在。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_connect",
            "description": "连接目标硬件。STM32 走 pyocd 探针 + UART；MicroPython 目标走 USB 串口。传 MICROPYTHON / MIRCOPYTHON 时会自动扫描并识别板子。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chip": {
                        "type": "string",
                        "description": "芯片型号，如 STM32F103C8T6、PICO_W、ESP32、CANMV_K230；也可传 MICROPYTHON 自动扫描识别（可选，不填用当前设置）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_disconnect",
            "description": "断开探针和串口连接。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_serial_connect",
            "description": (
                "单独连接/重连 UART 串口监控（不影响 pyocd 探针）。"
                "串口用于接收 Debug_Print 日志和 Gary:BOOT 启动标记，是 AI 判断程序运行状态的关键。"
                "stm32_connect 会自动尝试用默认端口连接，若失败或需要更换端口时调用此函数。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {
                        "type": "string",
                        "description": "串口设备路径，如 /dev/ttyUSB0、/dev/ttyAMA0（不填用 config.py 默认值）",
                    },
                    "baud": {"type": "integer", "description": "波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_serial_disconnect",
            "description": "断开串口（保留探针连接）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_set_chip",
            "description": "切换目标芯片型号，同时更新寄存器地址表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chip": {
                        "type": "string",
                        "description": "芯片完整型号，如 STM32F103C8T6 / STM32F407VET6",
                    },
                },
                "required": ["chip"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_hardware_status",
            "description": "查询当前硬件状态：芯片型号、探针/串口连接状态、GCC 版本、HAL 库是否就绪。开始工作前建议先调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_compile",
            "description": "使用 arm-none-eabi-gcc + HAL 库编译完整的 main.c 代码，返回编译结果和 bin 路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "完整的 main.c 代码（含所有 #include 和函数定义）",
                    },
                    "chip": {"type": "string", "description": "可选：临时指定芯片型号"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_compile_rtos",
            "description": "使用 arm-none-eabi-gcc + HAL + FreeRTOS Kernel 编译带 RTOS 的完整 main.c 代码。"
            "仅在用户需要 FreeRTOS 多任务时使用，裸机项目使用 stm32_compile。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "完整的 main.c 代码（含 FreeRTOS 头文件和任务定义）",
                    },
                    "chip": {"type": "string", "description": "可选：临时指定芯片型号"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_recompile",
            "description": (
                "直接从 latest_workspace/main.c 或 main.py 重新编译，无需传递代码字符串。"
                "str_replace_edit 修改文件后使用此工具代替 read_file + stm32_compile，"
                "节省 token，避免代码传输中的幻觉。"
                "STM32 下 mode='auto' 自动检测裸机或 RTOS；MicroPython 目标下会自动走 main.py 语法检查。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["auto", "bare", "rtos"],
                        "description": "编译模式：auto(自动检测)、bare(裸机)、rtos(FreeRTOS)。默认 auto。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_regen_bsp",
            "description": (
                "强制重新生成 BSP 文件（startup.s、link.ld、FreeRTOSConfig.h）并验证 FPU 使能代码。"
                "在切换芯片型号后、FreeRTOS 编译前、或怀疑 startup.s 不含 CPACR 初始化时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chip": {
                        "type": "string",
                        "description": "可选：指定芯片型号（如 STM32F411CE）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_analyze_fault_rtos",
            "description": (
                "FreeRTOS 专用 HardFault 分析。读取 SCB_CFSR/HFSR/BFAR/PC，"
                "检查 startup.s FPU 使能状态，给出 FPU 未使能、栈溢出、非法地址等具体诊断。"
                "FreeRTOS 程序 HardFault 时优先调用此工具而非 stm32_analyze_fault。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_rtos_check_code",
            "description": (
                "FreeRTOS 代码静态检查 —— 编译前自动检测常见 RTOS 编程错误。"
                "检查项：SysTick_Handler 冲突、HAL_Delay 陷阱、缺少 hook 函数、"
                "任务栈大小不足、ISR 中使用非 FromISR API、缺少头文件等。"
                "编写 RTOS 代码后、调用 stm32_compile_rtos 前使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 main.c 代码"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_rtos_task_stats",
            "description": (
                "读取 FreeRTOS 运行时任务统计：任务数、堆剩余/历史最低、当前任务名。"
                "通过 ELF 符号表定位内存地址，用 pyocd 读取。"
                "需要已编译（有 ELF）且硬件已连接。用于性能分析和堆使用诊断。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_rtos_suggest_config",
            "description": (
                "根据任务需求计算推荐的 FreeRTOS 配置：栈大小、堆大小、优先级数。"
                "评估 RAM 使用率并给出警告。在规划 RTOS 程序前调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_count": {
                        "type": "integer",
                        "description": "计划创建的任务数量（不含 Idle 和 Timer）",
                    },
                    "use_fpu": {
                        "type": "boolean",
                        "description": "任务是否使用浮点运算（默认 false）",
                    },
                    "use_printf": {
                        "type": "boolean",
                        "description": "任务是否使用 snprintf（默认 false）",
                    },
                    "ram_k": {
                        "type": "integer",
                        "description": "可选：指定 RAM 大小(KB)，不填用当前芯片参数",
                    },
                },
                "required": ["task_count"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_rtos_plan_project",
            "description": (
                "FreeRTOS 项目架构规划 —— 复杂 RTOS 项目的必备第一步。"
                "根据需求描述自动生成：任务分解、通信拓扑、中断策略、外设分配、资源估算。"
                "满足以下任一条件时必须调用：①任务数≥3 ②涉及中断+任务通信 ③涉及多个外设协同 ④涉及控制算法。"
                "规划结果需向用户展示并确认后再写代码。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "用户需求的完整描述（中文），包含功能要求、外设需求、性能要求等",
                    },
                    "peripherals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '可选：明确指定的外设列表，如 ["uart", "i2c", "adc", "pwm"]',
                    },
                    "task_hints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '可选：用户指定的任务名称提示，如 ["SensorTask", "MotorTask"]',
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_flash",
            "description": "通过 pyocd 将已编译的固件烧录到 STM32。需要先 connect 和 compile。",
            "parameters": {
                "type": "object",
                "properties": {
                    "bin_path": {
                        "type": "string",
                        "description": "可选：bin 文件路径，不填则用上次编译结果",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_read_registers",
            "description": "读取 STM32 关键寄存器（RCC、GPIO ODR/IDR、TIM、UART、I2C 等）。只在 stm32_auto_flash_cycle 未返回寄存器数据时补充调用一次，禁止循环重复调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "regs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '可选：指定寄存器名称列表，如 ["RCC_APB2ENR", "GPIOA_CRL"]。不填读取所有调试寄存器。',
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_analyze_fault",
            "description": "读取并分析 HardFault 状态寄存器（SCB_CFSR/HFSR/BFAR + PC），定位故障原因。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_serial_read",
            "description": "读取 UART 串口输出（调试日志、错误信息）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeout": {"type": "number", "description": "读取超时（秒），默认 3.0"},
                    "wait_for": {
                        "type": "string",
                        "description": "可选：等待直到出现此字符串（如 Gary:）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_auto_flash_cycle",
            "description": (
                "完整开发闭环（推荐）：编译 → 烧录 → 读串口 → 读寄存器，一步到位。"
                "代码生成后直接调用此函数，获取完整的验证结果。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 main.c 代码"},
                    "request": {"type": "string", "description": "需求描述（用于保存项目，可选）"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_reset_debug_attempts",
            "description": (
                "重置调试轮次计数器。必须调用的场景：(1)全新需求 (2)用户要求修改功能/显示内容/引脚/逻辑。"
                "不调用的场景：仅在修复上一轮的编译错误/烧录失败/运行异常时继续重试。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_generate_font",
            "description": (
                "将任意文字（含中文）渲染为真实字模 C 数组，使用系统字体精确生成，"
                "固定格式：横向取模·高位在前（row-major MSB=left），并附带配套的 OLED_ShowFontN() 显示函数。"
                "返回的 c_code 包含字模数组 + 显示函数，直接粘贴进 main.c 使用，无需修改。"
                "显示中文/特殊字符时必须先调用此工具，禁止手写字模数据。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要生成字模的文字，如 '你好世界'"},
                    "size": {
                        "type": "integer",
                        "description": "字体大小（像素），默认 16，常用 8/12/16/24/32",
                        "default": 16,
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_save_code",
            "description": "将代码保存到项目目录（不编译，仅保存源码；STM32 保存 main.c，MicroPython 目标保存 main.py）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "主源码内容（STM32 为 main.c，MicroPython 目标为 main.py）"},
                    "request": {"type": "string", "description": "项目描述（作为目录名）"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_list_projects",
            "description": "列出最近 15 个历史项目（名称、芯片、需求描述、时间）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_read_project",
            "description": "读取指定历史项目的主源码，用于查看或修改（STM32 为 main.c，MicroPython 目标为 main.py）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "项目目录名（从 stm32_list_projects 获取）",
                    },
                },
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rp2040_connect",
            "description": "通过 USB 串口连接 RP2040 / Pico / Pico W，并切到 MicroPython 工作流。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chip": {
                        "type": "string",
                        "description": "可选：目标板名称，如 RP2040、PICO、PICO_W",
                    },
                    "port": {
                        "type": "string",
                        "description": "可选：串口设备路径，如 /dev/ttyACM0",
                    },
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rp2040_hardware_status",
            "description": "查询 RP2040 + MicroPython 当前状态：目标板、串口连接、候选串口、运行时类型。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rp2040_compile",
            "description": "对完整 main.py 做 MicroPython 语法检查，并缓存到 workspace/projects/latest_workspace/main.py。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 main.py 代码"},
                    "chip": {"type": "string", "description": "可选：目标板名称，如 PICO_W"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rp2040_flash",
            "description": "通过 MicroPython raw REPL 把 main.py 同步到 RP2040，并软复位执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "可选：本地 .py 文件路径；不填则使用 workspace/projects/latest_workspace/main.py",
                    },
                    "port": {"type": "string", "description": "可选：串口设备路径"},
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rp2040_auto_sync_cycle",
            "description": "RP2040 推荐闭环：语法检查 main.py → 同步到设备 → 软复位 → 读取启动日志/Traceback。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 main.py 代码"},
                    "request": {"type": "string", "description": "项目描述（用于保存项目，可选）"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rp2040_list_files",
            "description": "列出当前 MicroPython 设备上的文件，检查 main.py、库文件和资源是否已经同步。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "设备目录路径，默认 ."},
                    "port": {"type": "string", "description": "可选：串口设备路径"},
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esp_connect",
            "description": "通过 USB 串口连接 ESP32 / ESP8266 / ESP32-S3 等开发板，并切到 MicroPython 工作流。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chip": {
                        "type": "string",
                        "description": "可选：目标板名称，如 ESP32、ESP8266、ESP32-S3、ESP32-C3、NodeMCU、D1 Mini、LOLIN32",
                    },
                    "port": {
                        "type": "string",
                        "description": "可选：串口设备路径，如 /dev/ttyUSB0",
                    },
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esp_hardware_status",
            "description": "查询 ESP 系列 + MicroPython 当前状态：目标板、串口连接、候选串口、运行时类型。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esp_compile",
            "description": "对完整 main.py 做 MicroPython 语法检查，并缓存到 workspace/projects/latest_workspace/main.py。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 main.py 代码"},
                    "chip": {"type": "string", "description": "可选：目标板名称，如 ESP32-S3、ESP32-C3、ESP8266、NodeMCU"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esp_flash",
            "description": "通过 MicroPython raw REPL 把 main.py 同步到 ESP 系列开发板，并软复位执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "可选：本地 .py 文件路径；不填则使用 workspace/projects/latest_workspace/main.py",
                    },
                    "port": {"type": "string", "description": "可选：串口设备路径"},
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esp_auto_sync_cycle",
            "description": "ESP 系列推荐闭环：语法检查 main.py → 同步到设备 → 软复位 → 读取启动日志/Traceback。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 main.py 代码"},
                    "request": {"type": "string", "description": "项目描述（用于保存项目，可选）"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esp_list_files",
            "description": "列出当前 ESP MicroPython 设备上的文件，检查 main.py、库文件和资源是否已经同步。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "设备目录路径，默认 ."},
                    "port": {"type": "string", "description": "可选：串口设备路径"},
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canmv_connect",
            "description": "通过 USB 串口连接 CanMV K230 / K230D，并切到 CanMV MicroPython 工作流。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chip": {
                        "type": "string",
                        "description": "可选：目标板名称，如 CANMV_K230、CANMV_K230D、K230、K230D",
                    },
                    "port": {
                        "type": "string",
                        "description": "可选：串口设备路径，如 /dev/ttyACM0",
                    },
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canmv_hardware_status",
            "description": "查询 CanMV K230 + MicroPython 当前状态：目标板、串口连接、候选串口、设备主脚本路径。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canmv_compile",
            "description": "对完整 main.py 做 CanMV MicroPython 语法检查，并缓存到 workspace/projects/latest_workspace/main.py。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 main.py 代码"},
                    "chip": {"type": "string", "description": "可选：目标板名称，如 CANMV_K230 或 CANMV_K230D"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canmv_flash",
            "description": "通过 MicroPython raw REPL 把 main.py 同步到 CanMV 设备上的 /sdcard/main.py，并软复位执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "可选：本地 .py 文件路径；不填则使用 workspace/projects/latest_workspace/main.py",
                    },
                    "port": {"type": "string", "description": "可选：串口设备路径"},
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canmv_auto_sync_cycle",
            "description": "CanMV K230 推荐闭环：语法检查 main.py → 同步到 /sdcard/main.py → 软复位 → 读取启动日志/Traceback。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 main.py 代码"},
                    "request": {"type": "string", "description": "项目描述（用于保存项目，可选）"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canmv_list_files",
            "description": "列出当前 CanMV 设备上的文件；默认优先查看 /sdcard，用于检查 main.py、模型和资源文件是否已经同步。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "设备目录路径，默认 .（CanMV 默认会转到 /sdcard）"},
                    "port": {"type": "string", "description": "可选：串口设备路径"},
                    "baud": {"type": "integer", "description": "串口波特率，默认 115200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gary_save_member_memory",
            "description": (
                "把高价值、可复用的经验写入 member.md。"
                "适用于：成功模板、关键初始化顺序、硬件易错点、寄存器判定经验、RTOS/裸机专项坑。"
                "禁止写冗长日志，必须提炼成短而可执行的结论。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "经验标题，简短具体，如“F103 裸机 UART 先打 Gary:BOOT 再启 I2C”",
                    },
                    "experience": {
                        "type": "string",
                        "description": "经验正文，2-6 行为宜，写成可复用的做法/结论",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '可选标签，如 ["baremetal", "uart", "i2c", "boot_marker"]',
                    },
                    "importance": {
                        "type": "string",
                        "enum": ["medium", "high", "critical"],
                        "description": "经验重要度，默认 high。",
                    },
                },
                "required": ["title", "experience"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gary_delete_member_memory",
            "description": (
                "从 member.md 删除错误、过时或无用的动态经验。"
                "默认只删除非 pinned 经验；建议先用精确 query，避免一次删太多。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用于匹配标题或正文的关键词，如“编译成功模板”或某条错误经验标题",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "是否只预览匹配结果而不真正删除，默认 false",
                    },
                    "include_pinned": {
                        "type": "boolean",
                        "description": "是否允许删除 pinned 经验，默认 false",
                    },
                    "max_matches": {
                        "type": "integer",
                        "description": "允许删除的最大匹配数，默认 10；匹配过多时工具会要求更精确的 query",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # 通用工具
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容（带行号）。",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_or_overwrite_file",
            "description": "创建或完全覆盖一个文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "str_replace_edit",
            "description": "精确替换文件中的字符串（old_str 必须在文件中唯一，包含 3-5 行上下文）。仅适用于已存在的文件；若 latest_workspace/main.py 不存在，应先生成完整文件并调用 compile / auto_sync_cycle。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "old_str": {
                        "type": "string",
                        "description": "要替换的原文（必须唯一，包含足够上下文）",
                    },
                    "new_str": {"type": "string", "description": "替换后的新文"},
                },
                "required": ["file_path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出目录内容。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "执行 Shell 命令（如查看日志、安装包、运行脚本等）。",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "按文件名关键字搜索文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string", "description": "搜索目录（默认当前）"},
                    "file_type": {"type": "string", "description": "扩展名过滤，如 .c / .h"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "基础网络搜索（需要本地 SearXNG 实例）。通常优先使用 browser_search。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_search",
            "description": "首选的网页搜索入口。使用本地 SearXNG 做结构化搜索，返回标题、URL 和摘要。遇到最新信息、官方文档、API、示例、教程、陌生模块或不确定的说法时，优先用它，不要靠记忆猜。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "结果数量，默认 5，最大 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_open",
            "description": "打开网页，返回标题、正文纯文本和页面中的链接列表。适合阅读搜索结果页或文档页；在下结论前应至少打开一个结果核对细节。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要打开的 URL"},
                    "max_chars": {"type": "integer", "description": "正文最大返回字符数，默认 8000"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract_links",
            "description": "提取网页中的链接列表，不返回正文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要提取链接的 URL"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_open_result",
            "description": "推荐的检索第二步。先搜索，再按结果索引直接打开网页。index 从 0 开始。若你不确定某个 API、模块或说法是否正确，搜索后应立即用它打开至少一个结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "index": {"type": "integer", "description": "搜索结果索引，从 0 开始，默认 0"},
                    "max_chars": {"type": "integer", "description": "正文最大返回字符数，默认 8000"},
                },
                "required": ["query"],
            },
        },
    },
    # ── 扩展通用工具 ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "append_file_content",
            "description": "向文件末尾追加内容（代码/文本文件）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "目标文件路径"},
                    "content": {"type": "string", "description": "要追加的内容"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "在文件中递归搜索正则表达式模式，返回匹配位置和内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则表达式模式"},
                    "path": {"type": "string", "description": "搜索目录（默认 .）"},
                    "include_extension": {"type": "string", "description": "按扩展名过滤，如 .py"},
                    "recursive": {"type": "boolean", "description": "是否递归（默认 True）"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_batch_commands",
            "description": "批量顺序执行多条 Shell 命令，默认遇错停止。",
            "parameters": {
                "type": "object",
                "properties": {
                    "commands": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "命令列表",
                    },
                    "stop_on_error": {
                        "type": "boolean",
                        "description": "遇错是否停止（默认 True）",
                    },
                },
                "required": ["commands"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "抓取 URL 页面并返回纯文本内容。仅适合已知 URL 的轻量抓取；需要标题或链接时优先用 browser_open。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要获取的 URL"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前系统时间、星期和时区。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_human",
            "description": "向用户提问，等待用户在终端输入回答。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要问用户的问题"},
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "执行 git status，查看当前仓库的文件修改状态。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "执行 git diff，查看实际代码变更内容。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "执行 git commit -m <message> 提交变更。",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "提交信息"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file_lines",
            "description": (
                "基于行号编辑文件（优先使用 str_replace_edit）。\n"
                "操作类型：replace（替换行范围）、insert（在行前插入）、delete（删除行范围）。\n"
                "仅在无法用 str_replace_edit 时使用（如在空白处插入新代码）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "operation": {
                        "type": "string",
                        "enum": ["replace", "insert", "delete"],
                        "description": "操作类型",
                    },
                    "start_line": {"type": "integer", "description": "起始行（1-indexed）"},
                    "end_line": {
                        "type": "integer",
                        "description": "结束行（可选，默认等于 start_line）",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "新内容（replace/insert 时必填）",
                    },
                },
                "required": ["file_path", "operation", "start_line"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_content_by_regex",
            "description": "在文件中第一个正则匹配位置之后插入内容，适合向类/函数后添加新方法。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件路径"},
                    "regex_pattern": {
                        "type": "string",
                        "description": "用于定位插入点的正则表达式",
                    },
                    "content": {"type": "string", "description": "要插入的内容"},
                },
                "required": ["file_path", "regex_pattern", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_python_code",
            "description": "检查 Python 文件的语法错误和代码风格（flake8/ast）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Python 文件路径（.py）"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python_code",
            "description": "执行 Python 代码片段（临时文件沙箱），用于验证逻辑或测试库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的 Python 代码"},
                },
                "required": ["code"],
            },
        },
    },
    # ── Word 文档工具 ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_docx",
            "description": "读取 Word 文档(.docx)的文本内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": ".docx 文件路径"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_docx_text",
            "description": "替换 Word 文档中的文本（尽量保留格式，支持正则）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": ".docx 文件路径"},
                    "old_text": {"type": "string", "description": "要查找的文本或正则模式"},
                    "new_text": {"type": "string", "description": "替换为的新文本"},
                    "use_regex": {
                        "type": "boolean",
                        "description": "是否启用正则匹配（默认 False）",
                    },
                },
                "required": ["file_path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_docx_content",
            "description": "向 Word 文档追加内容，可追加到末尾或指定段落索引之后。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": ".docx 文件路径"},
                    "content": {"type": "string", "description": "要追加的内容（\\n 分隔多段落）"},
                    "after_paragraph_index": {
                        "type": "integer",
                        "description": "插入位置段落索引（不填则追加到末尾）",
                    },
                    "style": {
                        "type": "string",
                        "description": "Word 样式名，如 'Heading 1'、'Normal'（可选）",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_docx_structure",
            "description": "查看 Word 文档段落结构（索引和内容预览），用于确定插入位置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": ".docx 文件路径"},
                    "max_paragraphs": {
                        "type": "integer",
                        "description": "最多显示段落数（默认 50）",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_docx_content_after_heading",
            "description": "在 Word 文档指定标题段落之后插入内容（大小写不敏感匹配）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": ".docx 文件路径"},
                    "heading_text": {
                        "type": "string",
                        "description": "目标标题文本（大小写不敏感）",
                    },
                    "content": {"type": "string", "description": "要插入的内容"},
                    "style": {"type": "string", "description": "Word 样式（可选）"},
                },
                "required": ["file_path", "heading_text", "content"],
            },
        },
    },
]

_BASE_TOOL_SCHEMAS = copy.deepcopy(TOOL_SCHEMAS)
_BASE_SCHEMAS_BY_NAME = {
    schema["function"]["name"]: copy.deepcopy(schema)
    for schema in _BASE_TOOL_SCHEMAS
    if schema.get("type") == "function" and schema.get("function", {}).get("name")
}
_TOOLS_WITH_CONTEXT: dict[str, bool] = {}
TOOLS_MAP: dict[str, ToolHandler] = {}


def _find_schema_index(name: str) -> Optional[int]:
    """Return the index of a registered schema by tool name."""

    for index, schema in enumerate(TOOL_SCHEMAS):
        function = schema.get("function", {})
        if function.get("name") == name:
            return index
    return None


def _ensure_schema(schema: dict[str, Any]) -> None:
    """Append a tool schema only when the tool is not registered yet."""

    function = schema.get("function", {})
    name = function.get("name")
    if not name:
        return
    if _find_schema_index(str(name)) is None:
        TOOL_SCHEMAS.append(copy.deepcopy(schema))


def register_tool(
    name: str,
    handler: ToolHandler,
    schema: Optional[dict[str, Any]] = None,
    *,
    replace: bool = True,
    pass_get_context: bool = False,
) -> ToolHandler:
    """Register or replace a tool handler and optionally attach its schema."""

    if not replace and name in TOOLS_MAP:
        return TOOLS_MAP[name]
    TOOLS_MAP[name] = handler
    _TOOLS_WITH_CONTEXT[name] = pass_get_context
    if schema is None:
        schema = _BASE_SCHEMAS_BY_NAME.get(name)
    if schema is not None:
        _ensure_schema(schema)
    return handler


def bind_tool_implementations(implementations: dict[str, ToolHandler]) -> dict[str, ToolHandler]:
    """Bind concrete tool implementations defined in stm32_agent.py."""

    for name, handler in implementations.items():
        register_tool(name, handler)
    return TOOLS_MAP


def dispatch_tool_call(
    name: str,
    arguments: Optional[dict[str, Any] | str] = None,
    *,
    get_context_fn: Optional[Callable[[], Any]] = None,
) -> Any:
    """Dispatch a tool call through the shared registry.

    `get_context_fn` is injected by callers instead of importing `core.state`
    here, which avoids circular imports between the tool registry and runtime.
    """

    if isinstance(arguments, str):
        payload = json.loads(arguments) if arguments.strip() else {}
    else:
        payload = dict(arguments or {})

    handler = TOOLS_MAP.get(name)
    if handler is None:
        return {"error": f"工具不存在: {name}"}

    if _TOOLS_WITH_CONTEXT.get(name) and get_context_fn is not None:
        payload.setdefault("get_context", get_context_fn)

    try:
        return handler(**payload)
    except Exception as exc:
        return {"error": str(exc)}


for _name, _handler in EXTRA_TOOLS_MAP.items():
    register_tool(_name, _handler)
for _schema in EXTRA_TOOL_SCHEMAS:
    _ensure_schema(_schema)
for _name, _handler in SKILL_TOOLS_MAP.items():
    register_tool(_name, _handler)
for _schema in SKILL_TOOL_SCHEMAS:
    _ensure_schema(_schema)
init_skills(TOOLS_MAP, TOOL_SCHEMAS, announce=False)


__all__ = [
    "TOOL_SCHEMAS",
    "TOOLS_MAP",
    "bind_tool_implementations",
    "dispatch_tool_call",
    "register_tool",
]
