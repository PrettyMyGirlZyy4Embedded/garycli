<div align="center">

# 🗡️ GARY CLI: The Spear Carrier

**Piercing the Silicon with AI.**
*专为 STM32 打造的 AI 原生命令行开发与调试智能体*

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![STM32](https://img.shields.io/badge/STM32-F0%20F1%20F3%20F4-blue.svg)](#supported-chips)
[![Website](https://img.shields.io/badge/Website-garycli.com-success)](https://www.garycli.com)
[![Tests](https://github.com/PrettyMyGirlZyy4Embedded/garycli/actions/workflows/test.yml/badge.svg)](https://github.com/PrettyMyGirlZyy4Embedded/garycli/actions)
[![Lint](https://github.com/PrettyMyGirlZyy4Embedded/garycli/actions/workflows/lint.yml/badge.svg)](https://github.com/PrettyMyGirlZyy4Embedded/garycli/actions)

<br>

```text
   ██████╗  █████╗ ██████╗ ██╗   ██╗
  ██╔════╝ ██╔══██╗██╔══██╗╚██╗ ██╔╝
  ██║  ███╗███████║██████╔╝ ╚████╔╝
  ██║   ██║██╔══██║██╔══██╗  ╚██╔╝
  ╚██████╔╝██║  ██║██║  ██║   ██║
   ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝
```

**用自然语言对话，让 AI 直接参与 STM32 开发、编译、烧录与调试。**

<p align="center">
  <a href="./README.md"><b>English</b></a>
</p>

[快速开始](#-快速开始) · [核心功能](#-核心功能) · [使用指南](#-使用指南) · [命令参考](#-命令参考) · [技能系统](#-技能系统-skills) · [常见问题](#-常见问题)

</div>

---

## ⚡ 什么是 Gary？

传统嵌入式开发里，真正耗时的往往不是“写几段 C 代码”，而是下面这条链路：

**需求理解 → 外设配置 → 代码生成 → 交叉编译 → 固件烧录 → 串口验证 → 寄存器排查 → 故障修复 → 再次烧录**

**Gary（持矛者）** 不是另一个只会“生成代码”的聊天工具。
它是一个面向 STM32 的 **AI 开发执行器**：你描述目标，它负责生成代码、调用工具链、连接硬件、收集运行反馈，并在可验证的范围内继续修复问题。

```text
你说：
  “帮我做一个 OLED 显示温湿度的程序，传感器用 AHT20”

Gary 自动执行：
  ✓ 生成完整 main.c（HAL + I2C + AHT20 + SSD1306）
  ✓ arm-none-eabi-gcc 交叉编译
  ✓ 通过 SWD 或 UART ISP 烧录到 STM32
  ✓ 监控串口输出，确认程序是否真正启动
  ✓ 读取寄存器，判断外设状态
  ✗ 发现 I2C 无应答 → 分析原因 → 修改代码 → 重新烧录
  ✓ 第二轮运行成功
```

一句话概括：

> **Gary 不是帮你“写一份 STM32 代码”，而是试图帮你完成一次 STM32 开发闭环。**

---

## 🎯 核心功能

### 🗣️ 自然语言 → 可编译 STM32 HAL 工程代码

你直接描述功能目标，Gary 生成完整、可交叉编译的 STM32 HAL C 代码。

```bash
gary do "PA0 接了 LED，帮我做一个呼吸灯，PWM 频率 1kHz"
gary do "用 I2C1 读取 MPU6050 加速度数据，串口打印"
gary do "配置 TIM2 编码器模式读取电机转速"
```

适合的典型场景：

* GPIO / PWM / ADC / EXTI
* UART / I2C / SPI / 定时器
* OLED / 传感器 / 数码管 / 蜂鸣器
* PID 控制 / 编码器反馈 / 电机控制
* 裸机项目快速原型验证

### 🔄 自动闭环调试

Gary 的重点不是“第一次就写对”，而是：

```text
生成代码 → 编译 → 烧录 → 串口验证 → 读寄存器 → 分析问题 → 修改代码 → 再编译再烧录
```

它会尽量基于真实反馈继续推进，而不是只停留在“建议你这样改”。

支持的典型诊断包括：

* **编译失败**：读取 GCC 错误信息并修复语法/符号/初始化问题
* **程序无输出**：检查启动路径、SysTick、时钟配置、串口初始化顺序
* **HardFault**：分析 SCB 相关寄存器，辅助定位故障类型
* **I2C 异常**：检查设备地址、总线占用、初始化顺序、NACK/ARLO 等情况
* **最多多轮自动修复**：修不好时，会尽量把问题明确收敛到“代码问题”还是“硬件问题”

### ⚡ 一致的烧录与调试策略

Gary 对硬件操作采用清晰的一致策略：

* **默认优先 SWD**：适合稳定烧录、寄存器读取、Fault 分析、调试闭环
* **UART ISP 可选**：在没有调试器时可切换到串口烧录
* **串口监控独立存在**：无论你用 SWD 还是 UART ISP，串口都用于观察程序真实运行状态

也就是说：

* **SWD** 负责“烧录 + 调试”
* **UART** 负责“日志 + 运行验证”

这比把“烧录”和“运行反馈”混在一起更稳定，也更符合真实开发流程。

### 🧰 内置工具集

| 工具               | 用途                                |
| ---------------- | --------------------------------- |
| **PID 自动调参**     | 分析超调、振荡、稳态误差，推荐 Kp/Ki/Kd          |
| **I2C 总线扫描**     | 扫描设备地址，辅助识别常见芯片                   |
| **引脚冲突检测**       | 发现 GPIO 复用冲突、SWD 误占等问题            |
| **PWM 参数计算**     | 自动计算 PSC/ARR，快速验证目标频率             |
| **舵机校准**         | 生成角度扫描逻辑，映射脉宽与角度                  |
| **信号采集分析**       | 分析 ADC/传感器数据的波动、噪声和频率特征           |
| **外设冒烟测试**       | 一键生成 GPIO/UART/I2C/SPI/ADC 最小测试代码 |
| **Flash/RAM 分析** | 展示资源占用并预警容量问题                     |
| **功耗估算**         | 基于外设启用状态估算功耗                      |
| **字模生成**         | 中英文字符 → OLED 点阵数组                 |

### 🔌 Bring Your Own Key

Gary 不绑定单一 AI 服务。你可以自由切换后端：

| 服务商             | 模型                | 说明        |
| --------------- | ----------------- | --------- |
| DeepSeek        | deepseek-chat     | 性价比高      |
| Kimi / Moonshot | kimi-k2.5         | 中文能力强     |
| OpenAI          | gpt-4o            | 综合表现强     |
| Google Gemini   | gemini-2.0-flash  | 响应快       |
| 通义千问            | qwen-plus         | 阿里云       |
| 智谱 GLM          | glm-4-flash       | 易接入       |
| Ollama          | qwen2.5-coder:14b | 本地离线，完全私有 |

### 🧩 技能系统（Skills）

Gary 支持可插拔技能包，用于扩展能力边界。

```bash
/skill install pid_tuner.py
/skill install ~/Downloads/skill.zip
/skill install https://github.com/xxx/skill.git
/skill list
/skill create my_tool "我的工具"
/skill export my_tool
```

每个 Skill 可以包含：

* Python 工具函数
* OpenAI Function Calling Schema
* 提示词说明
* 依赖文件

安装后即可热加载，无需重启。

---

## 🚀 快速开始

### 一键安装

**Linux / macOS / WSL：**

```bash
curl -fsSL https://www.garycli.com/install.sh | bash
```

**Windows（PowerShell）：**

```powershell
irm https://www.garycli.com/install.ps1 | iex
```

安装脚本会尝试完成：

* Python 环境检查
* arm-none-eabi-gcc 安装或检测
* HAL / CMSIS 相关资源准备
* Python 依赖安装
* 串口与调试工具安装
* CLI 启动命令写入

### 手动安装

```bash
# 1. 克隆仓库
git clone https://github.com/PrettyMyGirlZyy4Embedded/garycli.git
cd garycli

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装交叉编译器
# Ubuntu / Debian:
sudo apt install gcc-arm-none-eabi

# macOS:
brew install --cask gcc-arm-embedded

# Windows:
# 从 ARM 官方或对应发行源安装 gcc-arm-none-eabi

# 4. 可选：安装 UART ISP 烧录工具
pip install stm32loader

# 5. 可选：安装 SWD 调试工具
pip install pyocd

# 6. 下载 HAL 资源
python3 setup.py --hal

# 7. 运行环境诊断
python3 stm32_agent.py --doctor
```

### 首次配置

```bash
gary config
```

按提示配置：

* API Key
* Base URL
* Model
* 默认芯片型号
* 默认串口参数（可选）

### 环境诊断

```bash
gary doctor
```

输出示例：

```text
■ AI 接口
  ✓ API Key   sk-abc...xyz
  ✓ Base URL  https://api.deepseek.com/v1
  ✓ Model     deepseek-chat
  ✓ API 连通性  测试通过

■ 编译工具链
  ✓ arm-none-eabi-gcc  arm-none-eabi-gcc (15.1.0)
  ✓ HAL 资源           STM32F0xx, STM32F1xx, STM32F3xx, STM32F4xx
  ✓ CMSIS Core

■ Python 依赖
  ✓ openai
  ✓ rich
  ✓ prompt_toolkit
  ✓ pyserial      (可选)
  ✓ pyocd         (可选)
  ✓ stm32loader   (可选)

■ 硬件探针
  ✓ ST-Link V2
  ✓ 串口 /dev/ttyUSB0

✅ 所有核心配置正常，Gary 已就绪
```

---

## 📖 使用指南

### 模式一：单次任务（`gary do`）

适合快速验证单一需求：

```bash
# 仅生成 + 编译（不连接硬件）
gary do "写一个 WS2812 灯带驱动，控制 8 颗 LED 跑彩虹效果"

# 生成 + 编译 + 连接硬件
gary do "PA0 LED 闪烁，500ms 间隔" --connect

# 指定芯片型号
gary do "读取 ADC 电压，串口打印" --chip STM32F407VET6 --connect
```

### 模式二：交互式对话（`gary`）

适合多轮迭代开发：

```bash
gary
gary --connect
gary --chip STM32F407VET6
gary --connect --chip STM32F103C8T6
```

示例：

```text
Gary > 帮我做一个 OLED 时钟，I2C1 接 SSD1306，显示时分秒

  🔧 stm32_reset_debug_attempts → 计数器已重置
  🔧 stm32_hardware_status → chip: STM32F103C8T6, hw_connected: true
  🔧 stm32_generate_font → 生成 "0123456789:" 字模
  🔧 stm32_auto_flash_cycle → 编译成功 8.2KB，烧录成功
  串口输出: Gary:BOOT → OLED Init OK → 12:34:56

✓ OLED 已正常显示时间
```

### 模式三：增量修改

Gary 会尽量基于当前项目继续修改，而不是每次都重写整个程序：

```text
Gary > LED 闪烁太快了，改成 1 秒
Gary > 改成共阳数码管
Gary > 加一个蜂鸣器，报警时响
Gary > 把 I2C 地址从 0x3C 改成 0x3D
```

适合在同一个项目上连续迭代。

---

## 📋 命令参考

### 终端命令

| 命令                          | 说明            |
| --------------------------- | ------------- |
| `gary`                      | 启动交互式对话界面     |
| `gary do "任务描述"`            | 单次任务模式        |
| `gary do "任务" --connect`    | 单次任务 + 自动连接硬件 |
| `gary --chip STM32F407VET6` | 指定芯片型号        |
| `gary --connect`            | 启动并连接硬件       |
| `gary config`               | 配置 AI 后端      |
| `gary doctor`               | 环境诊断          |

### 交互式命令（在 `Gary >` 下输入）

| 命令                         | 说明             |
| -------------------------- | -------------- |
| `/connect [芯片]`            | 连接调试器或初始化硬件上下文 |
| `/disconnect`              | 断开硬件           |
| `/serial [端口] [波特率]`       | 连接串口           |
| `/serial list`             | 列出可用串口         |
| `/chip [型号]`               | 查看或切换芯片        |
| `/flash [swd\|uart\|auto]` | 设置烧录方式         |
| `/flash status`            | 查看烧录工具状态       |
| `/probes`                  | 列出调试探针         |
| `/status`                  | 查看完整硬件状态       |
| `/config`                  | 重新配置 AI 后端     |
| `/projects`                | 查看历史项目         |
| `/skill list`              | 查看已安装技能        |
| `/skill install <来源>`      | 安装技能包          |
| `/skill create <名称>`       | 创建技能模板         |
| `/clear`                   | 清空对话历史         |
| `/exit`                    | 退出             |

---

## 🔌 硬件连接建议

### 推荐方案：SWD + 串口日志

这是最稳定的组合：

* **SWD**：负责烧录、寄存器读取、故障调试
* **UART**：负责串口监控与启动确认

```text
ST-Link / J-Link      STM32
  SWDIO   ─────────── PA13
  SWCLK   ─────────── PA14
  GND     ─────────── GND
  3.3V    ─────────── 3.3V

USB-TTL               STM32
  TX      ──────────→ PA10
  RX      ←────────── PA9
  GND     ─────────── GND
```

### 纯串口方案（无调试器）

如果手头没有 ST-Link，也可以只接 USB-TTL，使用 UART ISP 烧录，但能力会受限：

* 可以烧录
* 可以看串口输出
* **不能像 SWD 那样方便地读寄存器和分析 Fault**

所以推荐优先使用 SWD。

---

## 🧩 技能系统 (Skills)

Gary 支持通过技能包扩展能力。一个标准 Skill 目录如下：

```text
~/.gary/skills/
├── pid_tuner/
│   ├── skill.json
│   ├── tools.py
│   ├── schemas.json
│   ├── prompt.md
│   └── requirements.txt
├── uart_flash/
└── _disabled/
```

### 安装技能

```bash
/skill install stm32_extra_tools.py
/skill install ~/Downloads/gary_skill_pid_tuner.zip
/skill install https://github.com/someone/gary-skill-motor.git
/skill install ~/my_skills/sensor_kit/
```

### 管理技能

```bash
/skill list
/skill info pid_tuner
/skill disable pid_tuner
/skill enable pid_tuner
/skill uninstall pid_tuner
/skill reload
```

### 开发自己的 Skill

```bash
# 1. 创建模板
/skill create motor_driver "直流电机 PID 控制工具"

# 2. 编辑生成的文件
# ~/.gary/skills/motor_driver/tools.py
# ~/.gary/skills/motor_driver/schemas.json
# ~/.gary/skills/motor_driver/prompt.md

# 3. 热重载
/skill reload

# 4. 导出分享
/skill export motor_driver
```

### Skill 开发规范

**tools.py**：

```python
def motor_set_speed(rpm: int) -> dict:
    """设置电机转速"""
    return {"success": True, "message": f"目标转速: {rpm} RPM"}

TOOLS_MAP = {
    "motor_set_speed": motor_set_speed,
}
```

**schemas.json**：

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
          "rpm": {
            "type": "integer",
            "description": "目标转速 RPM"
          }
        },
        "required": ["rpm"]
      }
    }
  }
]
```

**prompt.md**：

```markdown
## 电机控制
用户要控制电机时，调用 motor_set_speed 设置目标转速。
```

---

## 🏗️ 架构

```text
┌──────────────────────────────────────────────────────┐
│                    Gary CLI (TUI)                    │
│              rich + prompt_toolkit                   │
├──────────────────────────────────────────────────────┤
│                   AI 对话引擎                        │
│         流式对话 + Function Calling                  │
│   DeepSeek │ Kimi │ GPT │ Gemini │ Ollama │ ...     │
├──────────────┬──────────────┬────────────────────────┤
│  代码生成     │   编译器      │    硬件后端            │
│  HAL 模板     │  GCC Cross   │  ┌─────────────────┐  │
│  历史项目复用 │  Compiler    │  │ SWD（默认）      │  │
│  经验与模板库 │              │  │ pyocd            │  │
│              │              │  ├─────────────────┤  │
│              │              │  │ UART ISP（可选） │  │
│              │              │  │ stm32loader      │  │
│              │              │  ├─────────────────┤  │
│              │              │  │ 串口监控         │  │
│              │              │  │ pyserial         │  │
│              │              │  └─────────────────┘  │
├──────────────┴──────────────┴────────────────────────┤
│                   技能系统 (Skills)                  │
│   PID 调参 │ I2C 扫描 │ PWM 工具 │ 字模生成 │ ...    │
└──────────────────────────────────────────────────────┘
```

---

## <a name="supported-chips"></a> 📟 支持的芯片

当前重点支持以下 STM32 系列：

| 系列          | 典型型号                         | Flash       | RAM       |
| ----------- | ---------------------------- | ----------- | --------- |
| **STM32F0** | F030F4, F030C8, F072CB       | 16-128 KB   | 4-16 KB   |
| **STM32F1** | F103C8T6, F103RCT6, F103ZET6 | 64-512 KB   | 20-64 KB  |
| **STM32F3** | F303CCT6, F303RCT6           | 256 KB      | 40 KB     |
| **STM32F4** | F401CCU6, F407VET6, F411CEU6 | 256-1024 KB | 64-128 KB |

> 其他型号可能可以通过补充 HAL / CMSIS 资源和模板继续适配，但当前 README 只对上述系列做明确承诺。

---

## 💡 实战示例

### 🔰 LED 闪烁

```text
Gary > 帮我做一个 LED 闪烁，PA0 引脚，500ms 间隔
```

### 🔢 数码管显示

```text
Gary > 4 位共阳数码管，PA0-PA7 接段选，PB0-PB3 接位选，显示计数器
```

### 📡 传感器读取

```text
Gary > I2C1 接 AHT20 温湿度传感器，串口打印温度和湿度
Gary > 再加个 SSD1306 OLED 显示温度
```

### 🎛️ PID 电机控速

```text
Gary > 直流电机 PID 速度控制：TIM2 CH1 输出 PWM，TIM3 编码器读反馈，目标 500rpm
```

### 🔍 I2C 排查

```text
Gary > 我接了几个 I2C 设备但不确定地址，帮我扫描一下
```

### 🎵 蜂鸣器音乐

```text
Gary > 无源蜂鸣器接 PA1，帮我播放一段《小星星》
```

### 🖥️ OLED 中文显示

```text
Gary > OLED 显示中文“你好世界”，字体 16x16
```

---

## 📁 项目结构

以下结构更贴近当前仓库的实际组织方式：

```text
garycli/
├── stm32_agent.py          # 主程序：TUI + AI 对话 + 工具调度
├── compiler.py             # GCC 交叉编译封装
├── config.py               # 配置文件与路径管理
├── setup.py                # 安装与初始化脚本
├── stm32_extra_tools.py    # 扩展工具集
├── gary_skills.py          # 技能系统管理器
├── requirements.txt        # Python 依赖
├── install.sh              # Linux / macOS / WSL 安装脚本
├── install.ps1             # Windows 安装脚本
└── ~/.gary/                # 用户数据目录
    ├── skills/             # 已安装技能
    ├── projects/           # 历史项目存档
    ├── templates/          # 模板库
    └── member.md           # 经验库 / 记忆
```

---

## ❓ 常见问题

### 安装相关

<details>
<summary><b>Q: arm-none-eabi-gcc 安装后找不到？</b></summary>

确认已加入 PATH：

```bash
which arm-none-eabi-gcc
```

若没有输出，请手动加入 PATH，或执行 `gary doctor` 查看诊断结果。

</details>

<details>
<summary><b>Q: HAL 资源下载失败？</b></summary>

```bash
python3 setup.py --hal
# 或指定系列
python3 setup.py --hal f1 f4
```

</details>

<details>
<summary><b>Q: Windows 上串口权限或驱动异常？</b></summary>

确认已安装 CH340 / CP2102 驱动，并在设备管理器中看到对应 COM 口。

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

检查：

1. BOOT0 是否拉高到下载模式
2. 板子是否复位
3. TX / RX 是否交叉连接
4. 端口与波特率是否正确

</details>

<details>
<summary><b>Q: 编译报错 undefined reference to _sbrk？</b></summary>

通常说明代码里引入了 `printf` / `sprintf` / `malloc` 等依赖堆实现的符号。裸机最小工程建议避免直接使用这些函数。

</details>

<details>
<summary><b>Q: HardFault 怎么排查？</b></summary>

推荐使用 SWD 连接。Gary 会结合寄存器信息辅助判断：

* `PRECISERR`：常见于访问未就绪外设
* `UNDEFINSTR`：可能是栈损坏、跳转错误或指令异常
* `IACCVIOL`：可能访问了非法代码区

</details>

<details>
<summary><b>Q: 可以用 Ollama 本地模型吗？</b></summary>

可以。运行 `gary config` 后选择 Ollama，建议优先使用函数调用能力相对更稳定的代码模型。

</details>

<details>
<summary><b>Q: 支持 Arduino / ESP32 吗？</b></summary>

当前主目标是 STM32。其他平台计划后续扩展。

</details>

---

## 🗺️ 路线图

* [x] STM32F0 / F1 / F3 / F4 基础支持
* [x] UART ISP 烧录支持
* [x] SWD 调试与寄存器读取
* [x] 技能系统（Skills）
* [x] 模板库与经验库雏形
* [ ] 技能市场（在线浏览 / 安装社区技能）
* [ ] 串口数据实时可视化
* [ ] STM32CubeMX 项目导入
* [ ] VS Code 扩展
* [ ] ESP32 支持

---

## 🤝 贡献

欢迎 Issue 和 PR。尤其欢迎以下方向：

* 新的 Skill 包
* 更多 STM32 系列支持
* 文档改进与翻译
* 故障复现与修复
* 示例工程与演示视频

### 贡献 Skill

```bash
# 1. 创建模板
/skill create my_awesome_tool "我的工具"

# 2. 开发与测试
# 编辑 ~/.gary/skills/my_awesome_tool/

# 3. 导出
/skill export my_awesome_tool

# 4. 提交 PR
```

---

## 📜 协议

本项目采用 [Apache-2.0 License](https://opensource.org/licenses/Apache-2.0) 开源。

---

<div align="center">

**🗡️ Just Gary Do It.**

[官网](https://www.garycli.com) · [GitHub](https://github.com/PrettyMyGirlZyy4Embedded/garycli) · [提交 Issue](https://github.com/PrettyMyGirlZyy4Embedded/garycli/issues)

</div>
