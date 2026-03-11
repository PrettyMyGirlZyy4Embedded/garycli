<div align="center">

# 🗡️ GARY CLI: The Spear Carrier

**Piercing the Silicon with AI.**
<br>
*专为 STM32 打造的 AI 原生命令行开发与调试智能体*

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)
[![STM32](https://img.shields.io/badge/STM32-F0%20F1%20F3%20F4-blue.svg)](#supported-chips)
[![Website](https://img.shields.io/badge/Website-garycli.com-success)](https://www.garycli.com)

<br>

```
   ██████╗  █████╗ ██████╗ ██╗   ██╗
  ██╔════╝ ██╔══██╗██╔══██╗╚██╗ ██╔╝
  ██║  ███╗███████║██████╔╝ ╚████╔╝
  ██║   ██║██╔══██║██╔══██╗  ╚██╔╝
  ╚██████╔╝██║  ██║██║  ██║   ██║
   ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝
```

**用自然语言对话，让 AI 直接操控你的 STM32 硬件。**

<p align="center">
  <a href="./README.md"><b>English</b></a>
</p>

[快速开始](#-快速开始) · [功能特性](#-核心功能) · [使用指南](#-使用指南) · [命令参考](#-命令参考) · [技能系统](#-技能系统-skills) · [常见问题](#-常见问题)

</div>

---

## ⚡ 什么是 Gary？

在传统嵌入式开发中，查阅数百页 Reference Manual、配置寄存器、处理玄学接线问题消耗了工程师 80% 的精力。

**Gary（持矛者）** 不是另一个代码生成器——它是一个能**直接介入你的物理硬件**的 AI 智能体。你只需用自然语言描述需求，Gary 会自动完成从代码生成、交叉编译、物理烧录到错误自愈的**完整闭环**。

```
你说："帮我做一个 OLED 显示温湿度的程序，传感器用 AHT20"

Gary 自动执行：
  ✓ 生成完整 main.c（HAL 库 + I2C 驱动 + OLED 显示）
  ✓ arm-none-eabi-gcc 交叉编译
  ✓ 通过串口/SWD 烧录到 STM32
  ✓ 监控串口输出，验证启动
  ✓ 读取寄存器确认外设状态
  ✗ 发现 I2C 无应答 → 自动分析原因 → 修复代码 → 重新烧录
  ✓ 第 2 轮成功，程序正常运行
```

---

## 🎯 核心功能

### 🗣️ 自然语言 → 硬件控制

不再需要翻 Reference Manual。用中文说出你想做什么，Gary 生成完整可编译的 STM32 HAL C 代码。

```bash
gary do "PA0 接了 LED，帮我做一个呼吸灯，PWM 频率 1kHz"
gary do "用 I2C1 读取 MPU6050 加速度数据，串口打印"
gary do "配置 TIM2 编码器模式读取电机转速"
```

### 🔄 全自动闭环调试

Gary 的核心能力不是"生成代码"，而是**自动验证并修复**：

```
编译 → 烧录 → 读串口 → 读寄存器 → 分析结果
  ↑                                      ↓
  └──── 自动修复代码 ←── 发现问题 ←──────┘
```

- **编译失败** → 读取 GCC 错误信息，自动修复代码
- **HardFault** → 分析 SCB_CFSR/HFSR 寄存器，定位精确原因
- **程序卡死** → 检查 SysTick、I2C 总线锁死、时钟配置
- **传感器不响应** → 检测 I2C NACK/ARLO，判断是硬件未接还是地址错误
- **最多 8 轮自动修复**，修不好会告诉你具体是什么硬件问题

### ⚡ 烧录
Gary 默认**优先使用SWD烧录**遇到需要读寄存器调试的场景自动切换到 SWD和串口通信。

### 🧰 内置工具集

| 工具 | 用途 |
|---|---|
| **PID 自动调参** | 分析响应曲线（超调/振荡/稳态误差），自动推荐 Kp/Ki/Kd |
| **I2C 总线扫描** | 扫描所有设备地址，自动识别 100+ 常见芯片型号 |
| **引脚冲突检测** | 静态分析代码，发现引脚重复配置、SWD 误占等问题 |
| **PWM 频率扫描** | 自动计算 PSC/ARR，生成频率扫描表测试电机/蜂鸣器 |
| **舵机校准** | 生成角度扫描代码，精确映射脉宽到角度 |
| **信号采集分析** | 分析 ADC/传感器数据的噪声、信噪比、频率特征 |
| **外设冒烟测试** | 一键生成 GPIO/UART/I2C/SPI/ADC 最小测试代码 |
| **Flash/RAM 分析** | 显示固件资源占用率，预警 Flash 溢出 |
| **功耗估算** | 基于使能的外设估算 MCU 电流和功耗 |
| **字模生成** | 任意中英文 → OLED 点阵 C 数组（系统字体渲染，非手写） |

### 🔌 Bring Your Own Key

Gary 不绑定任何 AI 服务商。你的 API Key，你做主：

| 服务商 | 模型 | 说明 |
|---|---|---|
| DeepSeek | deepseek-chat | 性价比首选 |
| Kimi / Moonshot | kimi-k2.5 | 中文能力强 |
| OpenAI | gpt-4o | 综合能力强 |
| Google Gemini | gemini-2.0-flash | 免费额度大 |
| 通义千问 | qwen-plus | 阿里云 |
| 智谱 GLM | glm-4-flash | 免费 |
| Ollama | qwen2.5-coder:14b | 本地离线，完全私有 |

### 🧩 技能系统（Skills）

通过**可插拔的技能包**扩展 Gary 的能力：

```bash
/skill install pid_tuner.py              # 从 .py 文件安装
/skill install ~/Downloads/skill.zip     # 从压缩包安装
/skill install https://github.com/xxx    # 从 Git 仓库安装
/skill list                               # 查看所有技能
/skill create my_tool "我的工具"          # 创建新技能模板
/skill export my_tool                     # 打包分享给别人
```

每个 Skill 包含工具函数 + AI Schema + 提示词，安装后**立即生效**，无需重启。

---

## 🚀 快速开始

### 一键安装

**Linux / macOS / WSL：**
```bash
curl -fsSL https://www.garycli.com/install.sh | bash
```

**Windows（PowerShell 管理员）：**
```powershell
irm https://www.garycli.com/install.ps1 | iex
```

安装脚本会自动完成：
- Python 环境检测
- arm-none-eabi-gcc 交叉编译器安装
- STM32 HAL 库下载
- Python 依赖安装（openai, rich, pyserial, pyocd 等）
- 串口烧录工具安装（stm32loader）

### 手动安装

```bash
# 1. 克隆仓库
git clone https://github.com/PrettyMyGirlZyy4Embedded/garycli.git
cd garycli

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装交叉编译器
# Ubuntu/Debian:
sudo apt install gcc-arm-none-eabi
# macOS:
brew install --cask gcc-arm-embedded
# Windows: 从 ARM 官网下载安装

# 4. 安装串口烧录工具（可选，推荐）
pip install stm32loader

# 5. 安装调试器驱动（可选）
pip install pyocd

# 6. 下载 HAL 库
python3 setup.py --hal

# 7. 运行环境诊断
python3 stm32_agent.py --doctor
```

### 首次配置

```bash
# 配置 AI 后端（交互式向导）
gary config
```

按提示选择服务商、输入 API Key 即可。推荐 DeepSeek（便宜好用）或 Ollama（完全本地）。

### 环境诊断

```bash
gary doctor
```

输出示例：
```
■ AI 接口
  ✓ API Key   sk-abc...xyz
  ✓ Base URL  https://api.deepseek.com/v1
  ✓ Model     deepseek-chat
  ✓ API 连通性  测试通过

■ 编译工具链
  ✓ arm-none-eabi-gcc  arm-none-eabi-gcc (15.1.0) 15.1.0
  ✓ HAL 库      STM32F0xx, STM32F1xx, STM32F3xx, STM32F4xx
  ✓ CMSIS Core

■ Python 依赖
  ✓ openai
  ✓ rich
  ✓ prompt_toolkit
  ✓ pyserial  (可选)
  ✓ pyocd  (可选)
  ✓ stm32loader  (可选)

■ 硬件探针
  ✓ STM32 STLink V2  (066BFF...)
  ✓ 串口 /dev/ttyUSB0

  ✅  所有核心配置正常，Gary 已就绪！
```

---

## 📖 使用指南

### 模式一：单次任务（gary do）

不启动交互界面，一句话执行完退出：

```bash
# 生成 + 编译（无硬件）
gary do "写一个 WS2812 灯带驱动，控制 8 颗 LED 跑彩虹效果"

# 生成 + 编译 + 烧录（连接硬件）
gary do "PA0 LED 闪烁，500ms 间隔" --connect

# 指定芯片型号
gary do "读取 ADC 电压，串口打印" --chip STM32F407VET6 --connect
```

### 模式二：交互式对话（gary）

启动沉浸式 TUI，持续对话迭代开发：

```bash
gary                        # 启动
gary --connect              # 启动并自动连接硬件
gary --chip STM32F407VET6   # 指定芯片型号
```

进入后：

```
Gary > 帮我做一个 OLED 时钟，I2C1 接 SSD1306，显示时分秒

  🔧 stm32_reset_debug_attempts → 计数器已重置
  🔧 stm32_hardware_status → chip: STM32F103C8T6, hw_connected: true
  🔧 stm32_generate_font → 生成 "0123456789:" 字模
  🔧 stm32_auto_flash_cycle → 编译成功 8.2KB，烧录成功...
  串口输出: Gary:BOOT → OLED Init OK → 12:34:56

✓ 编译烧录成功，8.2KB。OLED 已显示时间。

Gary > 加一个按键调时间，PA1 接按键，短按切换时/分/秒，长按加1

  🔧 str_replace_edit → 替换按键相关代码
  🔧 stm32_auto_flash_cycle → 编译成功 9.1KB，烧录成功...

✓ 已添加按键调时功能。短按切换位，长按+1。
```

### 模式三：增量修改

Gary 会记住上次的代码。你可以持续迭代：

```
Gary > LED 闪烁太快了，改成 1 秒
Gary > 改成共阳数码管
Gary > 加一个蜂鸣器，报警时响
Gary > 把 I2C 地址从 0x3C 改成 0x3D
```

Gary 只修改你要求的部分，不会重写整个程序。

---

## 📋 命令参考

### 终端命令

| 命令 | 说明 |
|---|---|
| `gary` | 启动交互式对话界面 |
| `gary do "任务描述"` | 单次任务模式 |
| `gary do "任务" --connect` | 单次任务 + 自动连接硬件 |
| `gary --chip STM32F407VET6` | 指定芯片型号 |
| `gary --connect` | 启动并连接硬件 |
| `gary config` | 配置 AI 后端（API Key / Model） |
| `gary doctor` | 环境诊断（检查所有配置） |

### 交互式命令（在 Gary > 提示符下输入）

| 命令 | 说明 |
|---|---|
| `/connect [芯片]` | 连接 SWD 调试器（如 `/connect STM32F103C8T6`） |
| `/disconnect` | 断开硬件 |
| `/serial [端口] [波特率]` | 连接串口（如 `/serial /dev/ttyUSB0 115200`） |
| `/serial list` | 列出可用串口 |
| `/chip [型号]` | 查看/切换芯片 |
| `/flash [uart\|swd\|auto]` | 切换烧录模式 |
| `/flash status` | 查看烧录工具状态 |
| `/probes` | 列出所有调试探针 |
| `/status` | 查看完整硬件状态 |
| `/config` | 配置 AI 接口 |
| `/projects` | 列出历史项目 |
| `/skill list` | 列出已安装技能 |
| `/skill install <来源>` | 安装技能包 |
| `/skill create <名称>` | 创建技能模板 |
| `/clear` | 清空对话历史 |
| `/exit` | 退出 |

---

## 🔧 硬件接线

### 方案：串口 + SWD

额外加一个调试器（ST-Link V2，¥10），可以读寄存器、分析 HardFault：

```
ST-Link           STM32
  SWDIO ─────────── PA13
  SWCLK ─────────── PA14
  GND ──────────── GND
  3.3V ─────────── 3.3V

USB-TTL           STM32（串口监控）
  TX  ──────────→ PA10
  RX  ←────────── PA9
  GND ──────────── GND
```

---

## 🧩 技能系统 (Skills)

Gary 通过可插拔的**技能包**扩展功能。每个 Skill 是一个标准目录：

```
~/.gary/skills/
├── pid_tuner/
│   ├── skill.json        ← 元信息（名称、版本、作者、依赖）
│   ├── tools.py          ← 工具函数（Python）
│   ├── schemas.json      ← AI 调用格式（OpenAI Function Calling）
│   ├── prompt.md         ← 教 AI 什么场景用这些工具
│   └── requirements.txt  ← Python 依赖
├── uart_flash/
└── _disabled/            ← 已禁用的技能
```

### 安装技能

```bash
# 从 .py 文件（自动包装成 skill）
/skill install stm32_extra_tools.py

# 从压缩包
/skill install ~/Downloads/gary_skill_pid_tuner.zip

# 从 Git 仓库
/skill install https://github.com/someone/gary-skill-motor.git

# 从本地目录
/skill install ~/my_skills/sensor_kit/
```

### 管理技能

```bash
/skill list                  # 列出所有（含已禁用）
/skill info pid_tuner        # 查看详情
/skill disable pid_tuner     # 暂时禁用
/skill enable pid_tuner      # 重新启用
/skill uninstall pid_tuner   # 卸载
/skill reload                # 热重载全部
```

### 开发自己的 Skill

```bash
# 1. 生成模板
/skill create motor_driver "直流电机 PID 控制工具"

# 2. 编辑生成的文件
#    ~/.gary/skills/motor_driver/tools.py     ← 写工具函数
#    ~/.gary/skills/motor_driver/schemas.json ← 写 AI Schema
#    ~/.gary/skills/motor_driver/prompt.md    ← 写使用指南

# 3. 热重载
/skill reload

# 4. 打包分享
/skill export motor_driver
# → gary_skill_motor_driver.zip
```

### Skill 开发规范

**tools.py**（必须导出 `TOOLS_MAP`）：

```python
def motor_set_speed(rpm: int) -> dict:
    """设置电机转速"""
    return {"success": True, "message": f"目标转速: {rpm} RPM"}

TOOLS_MAP = {
    "motor_set_speed": motor_set_speed,
}
```

**schemas.json**（OpenAI Function Calling 格式）：

```json
[
  {
    "type": "function",
    "function": {
      "name": "motor_set_speed",
      "description": "设置直流电机目标转速",
      "parameters": {
        "type": "object",
        "properties": {
          "rpm": {"type": "integer", "description": "目标转速 RPM"}
        },
        "required": ["rpm"]
      }
    }
  }
]
```

**prompt.md**（教 AI 怎么用）：

```markdown
## 电机控制
用户要控制电机时，调用 motor_set_speed 设置目标转速。
```

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────┐
│                    Gary CLI (TUI)                     │
│              rich + prompt_toolkit                    │
├──────────────────────────────────────────────────────┤
│                   AI 对话引擎                         │
│         OpenAI API (流式 + Function Calling)          │
│    DeepSeek │ Kimi │ GPT │ Gemini │ Ollama │ ...    │
├──────────────┬──────────────┬────────────────────────┤
│  代码生成     │   编译器      │    硬件后端            │
│  STM32 HAL   │  GCC Cross   │  ┌─────────────────┐  │
│  C 代码模板   │  Compiler    │  │ UART ISP (首选)  │  │
│              │              │  │  stm32loader     │  │
│              │              │  ├─────────────────┤  │
│              │              │  │ SWD (备选)       │  │
│              │              │  │  pyocd           │  │
│              │              │  ├─────────────────┤  │
│              │              │  │ 串口监控         │  │
│              │              │  │  pyserial        │  │
│              │              │  └─────────────────┘  │
├──────────────┴──────────────┴────────────────────────┤
│                   技能系统 (Skills)                    │
│  PID调参 │ I2C扫描 │ PWM扫描 │ 字模生成 │ 自定义...  │
└──────────────────────────────────────────────────────┘
         ↕ USB                    ↕ USB
┌──────────────┐          ┌──────────────────┐
│  USB-TTL     │          │  ST-Link/J-Link  │
│  (CH340)     │          │  (可选)          │
└──────┬───────┘          └──────┬───────────┘
       │ UART                    │ SWD
┌──────┴─────────────────────────┴───────────┐
│              STM32 目标板                    │
│   PA9/PA10 (UART)    PA13/PA14 (SWD)       │
└────────────────────────────────────────────┘
```

---

## <a name="supported-chips"></a> 📟 支持的芯片

| 系列 | 典型型号 | Flash | RAM |
|---|---|---|---|
| **STM32F0** | F030F4, F030C8, F072CB | 16-128 KB | 4-16 KB |
| **STM32F1** | F103C8T6 (BluePill), F103RCT6, F103ZET6 | 64-512 KB | 20-64 KB |
| **STM32F3** | F303CCT6, F303RCT6 | 256 KB | 40 KB |
| **STM32F4** | F401CCU6, F407VET6, F411CEU6 | 256-1024 KB | 64-128 KB |

> 其他型号：Gary 会自动下载对应的 CMSIS Pack（首次连接时），理论上支持所有 Cortex-M 系列。

---

## 💡 实战示例

### 🔰 入门：LED 闪烁

```
Gary > 帮我做一个 LED 闪烁，PA0 引脚，500ms 间隔
```

### 🔢 数码管显示

```
Gary > 4 位共阳数码管，PA0-PA7 接段选，PB0-PB3 接位选，显示计数器
```

### 📡 传感器读取

```
Gary > I2C1 接 AHT20 温湿度传感器，串口打印温度和湿度
Gary > 再加个 SSD1306 OLED 显示温度
```

### 🎛️ PID 电机控速

```
Gary > 直流电机 PID 速度控制：TIM2 CH1 输出 PWM，TIM3 编码器读反馈，目标 500rpm
```

Gary 会自动：生成 PID 代码 → 烧录 → 采集串口数据 → 分析响应 → 调参 → 重新烧录 → 循环直到稳定。

### 🔍 I2C 设备排查

```
Gary > 我接了几个 I2C 设备但不确定地址，帮我扫描一下
```

### 🎵 蜂鸣器音乐

```
Gary > 无源蜂鸣器接 PA1，帮我播放一段《小星星》
```

### 🖥️ OLED 中文显示

```
Gary > OLED 显示中文"你好世界"，字体 16x16
```

Gary 自动调用字模生成工具，用系统字体渲染真实点阵，不是手写数据。

---

## 📁 项目结构

```
gary/
├── stm32_agent.py          # 主程序（TUI + AI 对话 + 工具框架）
├── compiler.py             # GCC 交叉编译器封装
├── config.py               # 配置文件（API Key、芯片、路径）
├── setup.py                # 安装脚本
├── stm32_uart_flash.py     # 串口 ISP 烧录模块
├── stm32_extra_tools.py    # 扩展工具集（PID/I2C/PWM/信号分析...）
├── gary_skills.py          # 技能系统管理器
├── requirements.txt        # Python 依赖
└── ~/.gary/                # 用户数据目录
    ├── skills/             # 已安装技能
    ├── projects/           # 历史项目存档
    └── skills_registry.json
```

---

## ❓ 常见问题

### 安装相关

<details>
<summary><b>Q: arm-none-eabi-gcc 安装后找不到？</b></summary>

确认已加入 PATH：
```bash
which arm-none-eabi-gcc
# 若无输出，手动添加：
export PATH=$PATH:/usr/lib/arm-none-eabi/bin
```
或运行 `gary doctor` 查看诊断结果。
</details>

<details>
<summary><b>Q: HAL 库下载失败？</b></summary>

```bash
# 手动下载
python3 setup.py --hal

# 或指定系列
python3 setup.py --hal f1 f4
```
</details>

<details>
<summary><b>Q: Windows 上串口权限问题？</b></summary>

确认安装了 CH340/CP2102 驱动。在设备管理器中确认 COM 口已识别。
</details>

<details>
<summary><b>Q: Linux 上串口打不开（Permission denied）？</b></summary>

```bash
sudo usermod -aG dialout $USER
newgrp dialout
```
</details>

### 使用相关

<details>
<summary><b>Q: 串口烧录没有响应？</b></summary>

检查清单：
1. BOOT0 跳线是否拨到 1（VCC 侧）？
2. 是否按了复位键？
3. TX/RX 是否交叉连接？（TTL-TX → STM32-PA10）
4. 串口波特率是否为 115200？
</details>

<details>
<summary><b>Q: 编译报错 undefined reference to _sbrk？</b></summary>

代码中用了 `sprintf`/`printf`/`malloc`。Gary 生成的代码不使用这些函数，如果你手动加了，改用 Gary 的 `Debug_Print`/`Debug_PrintInt` 替代。
</details>

<details>
<summary><b>Q: HardFault 怎么排查？</b></summary>

Gary 连接 SWD 后会自动读取 SCB_CFSR 寄存器分析。常见原因：
- `PRECISERR`：访问了未使能时钟的外设
- `UNDEFINSTR`：栈溢出或函数指针错误
- `IACCVIOL`：Flash 地址非法
</details>

<details>
<summary><b>Q: 可以用 Ollama 本地模型吗？</b></summary>

可以。运行 `gary config`，选择 Ollama，模型建议用 `qwen2.5-coder:14b` 或更大的。小模型（7B）函数调用能力较弱。
</details>

<details>
<summary><b>Q: 支持 Arduino / ESP32 吗？</b></summary>

目前仅支持 STM32。ESP32/Arduino 支持在路线图中。
</details>

---

## 🗺️ 路线图

- [x] STM32F1/F4 全系列支持
- [x] UART 串口烧录（免调试器）
- [x] PID 自动调参
- [x] 技能系统（Skills）
- [ ] 技能市场（在线浏览/安装社区技能）
- [ ] 可视化波形（串口数据实时绘图）
- [ ] ESP32 支持
- [ ] STM32CubeMX 项目导入
- [ ] VS Code 扩展

---

## 🤝 贡献

欢迎提交 Issue 和 PR！特别欢迎以下贡献：

- **新的 Skill 包**：将你的工具封装成标准 Skill 分享给社区
- **芯片支持**：适配更多 STM32 系列的寄存器地址表
- **文档翻译**：帮助翻译为英文/其他语言
- **Bug 修复**：使用中遇到的任何问题

### 开发 Skill 并贡献

```bash
# 1. 创建 skill 模板
/skill create my_awesome_tool "我的工具"

# 2. 开发 & 测试
# 编辑 ~/.gary/skills/my_awesome_tool/ 下的文件

# 3. 导出
/skill export my_awesome_tool

# 4. 提交 PR 到本仓库的 skills/ 目录
```

---

## 📜 协议

本项目采用 [Apache-2.0 License](https://opensource.org/licenses/Apache-2.0) 开源。

---

<div align="center">

**🗡️ Just Gary Do It.**

[官网](https://www.garycli.com) · [GitHub](https://github.com/GaryCLI/gary) · [反馈问题](https://github.com/GaryCLI/gary/issues)

</div>
