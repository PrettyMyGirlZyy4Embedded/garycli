<div align="center">

# 🗡️ GARY CLI: The Spear Carrier

**Piercing the Silicon with AI.**
<br>
*专为 STM32 打造的 AI 原生命令行开发与调试智能体*

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12+-green.svg)](https://www.python.org/)
[![Website](https://img.shields.io/badge/Website-garycli.com-success)](https://www.garycli.com)

</div>

---

## ⚡ 什么是 Gary？

在传统的嵌入式开发中，查阅数百页的 Reference Manual、配置复杂的寄存器、处理玄学的连线问题消耗了工程师 80% 的精力。

**Gary (持矛者)** 是一个完全基于命令行的 AI Agent。它不再是简单的“代码生成器”，而是能够**直接介入你的物理硬件**的智能体。你只需要用自然语言下达指令，Gary 会自动完成从代码生成、交叉编译、物理烧录到错误自愈的完整闭环。

## 🚀 极速安装 (Quick Start)

只需一行命令，立刻唤醒持矛者：

**Linux / macOS / WSL:**
```bash
curl -fsSL [https://www.garycli.com/install.sh](https://www.garycli.com/install.sh) | bash
```

**Windows (PowerShell):**
```bash
irm [https://www.garycli.com/install.ps1](https://www.garycli.com/install.ps1) | iex
```

🛠️ 核心特性 (Features)
🗣️ 自然语言驱动硬件：只需说 gary do "配置 I2C 读取 MPU6050 数据"，逻辑瞬间生成。

⚡ 全自动编译与烧录：无缝对接 GCC 与 ST-Link/DAP-Link，跳过繁琐的 IDE 配置。

🧠 闭环自愈调试 (Self-Correction)：遇到 HardFault 或编译报错？Gary 会自动读取日志、分析寄存器状态并自我修正代码，直到跑通为止。

🔌 BYOK (Bring Your Own Key)：原生支持 DeepSeek 等大模型，由开发者自己掌控 API Key 与数据隐私。

💻 使用范例 (Usage)
初始化环境并配置大模型 API Key 后，你可以随时在终端呼叫它：
```bash
# 执行单次开发任务
gary do "帮我写一个呼吸灯程序，使用 PA8 引脚的 PWM 输出"

# 进入沉浸式调试模式
gary

# 诊断物理探针与环境
gary doctor
```
📜 协议 (License)
本项目采用 Apache-2.0 License 开源。

<div align="center">
<i>"Just Gary Do it."</i>
</div>
