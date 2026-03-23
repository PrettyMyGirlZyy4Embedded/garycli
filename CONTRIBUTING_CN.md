# 🗡️ 贡献指南 · Contributing Guide

> 感谢你愿意为 **Gary CLI** 做出贡献！  
> 无论是修 Bug、扩展芯片支持、贡献 Skill 包，还是改善文档，你的每一次提交都会让更多嵌入式开发者受益。

---

## 目录

- [行为准则](#行为准则)
- [快速开始：本地开发环境](#快速开始本地开发环境)
- [项目结构说明](#项目结构说明)
- [贡献类型](#贡献类型)
  - [🐛 报告 Bug](#-报告-bug)
  - [💡 功能建议](#-功能建议)
  - [🔧 提交代码修复或功能](#-提交代码修复或功能)
  - [🧩 贡献 Skill 包](#-贡献-skill-包)
  - [📟 扩展芯片支持](#-扩展芯片支持)
  - [📄 改善文档](#-改善文档)
- [Pull Request 规范](#pull-request-规范)
- [代码风格规范](#代码风格规范)
- [Commit Message 规范](#commit-message-规范)
- [常见问题](#常见问题)

---

## 行为准则

本项目遵循开放、友善、包容的社区原则。请做到：

- 对他人的贡献保持尊重，即使观点不同
- 提 Issue 和 PR 时提供清晰的上下文，而不是情绪化的评论
- 不在讨论中附带与项目无关的内容

---

## 快速开始：本地开发环境

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/<你的用户名>/garycli.git
cd garycli

# 2. 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安装依赖（开发模式）
pip install -r requirements.txt
pip install -e .

# 4. 安装交叉编译工具链（用于测试代码生成 + 编译流程）
# Ubuntu / Debian:
sudo apt install gcc-arm-none-eabi
# macOS:
brew install --cask gcc-arm-embedded

# 5. 下载 HAL 资源
python3 setup.py --hal

# 6. 运行环境诊断，确认一切就绪
python3 stm32_agent.py --doctor
```

---

## 项目结构说明

```
garycli/
├── stm32_agent.py        # 主程序：TUI + AI 对话 + 工具调度
├── compiler.py           # GCC 交叉编译封装
├── config.py             # 配置文件与路径管理
├── setup.py              # 安装与初始化脚本
├── stm32_extra_tools.py  # 内置工具集合（I2C 扫描、PWM 计算等）
├── gary_skills.py        # Skill 系统管理器
├── requirements.txt      # Python 依赖
├── install.sh            # Linux / macOS 安装脚本
├── install.ps1           # Windows 安装脚本
└── ~/.gary/              # 用户数据目录（运行时生成）
    ├── skills/           # 已安装的 Skill 包
    ├── projects/         # 历史项目存档
    ├── templates/        # 模板库
    └── member.md         # 知识 / 记忆库
```

如果你要新增功能，请根据其性质放到对应模块中，而不是统一堆在 `stm32_agent.py` 里。

---

## 贡献类型

### 🐛 报告 Bug

在 [Issues](https://github.com/PrettyMyGirlZyy4Embedded/garycli/issues) 中新建 Issue，请包含：

- **Gary 版本** / Python 版本 / 操作系统
- **芯片型号**（如 STM32F103C8T6）
- **使用的 AI 后端**（如 deepseek-chat、gpt-4o）
- **复现步骤**（最小可复现案例最佳）
- **实际行为** vs **预期行为**
- 如涉及编译或烧录问题，请附上 `gary doctor` 的输出

---

### 💡 功能建议

同样通过 Issues 提交，标题加前缀 `[Feature]`，请描述：

- 这个功能解决了什么问题（面向场景，而非技术实现）
- 如果已有初步实现思路，可附上伪代码或架构草图

---

### 🔧 提交代码修复或功能

1. **先开 Issue 讨论**（对于非 trivial 的改动），避免白费功夫
2. 在自己的 fork 上新建分支：

```bash
git checkout -b fix/i2c-scan-crash
# 或
git checkout -b feat/stm32g0-support
```

3. 编写代码，确保：
   - 不破坏现有的三种 AI 后端调用方式（Function Calling 格式）
   - 新增工具需在 `stm32_extra_tools.py` 中注册，并补充 schema
   - 硬件相关代码优先通过 `gary doctor` 的诊断项验证
4. 提交 PR，填写模板

---

### 🧩 贡献 Skill 包

Skill 是 Gary 最重要的扩展机制，欢迎贡献新的 Skill！

#### Skill 标准目录结构

```
my_skill/
├── skill.json         # Skill 元信息
├── tools.py           # Python 工具函数
├── schemas.json       # OpenAI Function Calling Schema
├── prompt.md          # 提示词说明
└── requirements.txt   # 额外 Python 依赖（可选）
```

#### skill.json 示例

```json
{
  "name": "my_skill",
  "version": "1.0.0",
  "description": "一句话描述这个 Skill 做什么",
  "author": "你的 GitHub 用户名",
  "tags": ["motor", "pid", "sensor"],
  "gary_min_version": "0.1.0"
}
```

#### tools.py 示例

```python
def my_tool_function(param: str) -> dict:
    """工具函数：描述其作用"""
    # 你的实现
    return {"success": True, "result": "..."}

# 必须导出此映射
TOOLS_MAP = {
    "my_tool_function": my_tool_function,
}
```

#### schemas.json 示例

```json
[
  {
    "type": "function",
    "function": {
      "name": "my_tool_function",
      "description": "描述 AI 何时应该调用此工具",
      "parameters": {
        "type": "object",
        "properties": {
          "param": {
            "type": "string",
            "description": "参数说明"
          }
        },
        "required": ["param"]
      }
    }
  }
]
```

#### 本地调试 Skill

```bash
# 在 gary 交互模式中安装并热加载
/skill install ./my_skill/
/skill reload
/skill list
```

#### 提交 Skill 包的 PR 要求

- `skill.json` 中 `author` 字段填写你的 GitHub 用户名
- 在 PR 描述中说明：该 Skill 解决什么问题、测试用的芯片 / 外设组合
- 若 Skill 依赖特定硬件，请在 `prompt.md` 中注明前提条件

---

### 📟 扩展芯片支持

目前 Gary 主要支持 STM32F0 / F1 / F3 / F4 系列。如果你想添加新系列（如 STM32G0、STM32H7），需要：

1. 在 `setup.py` 中添加对应 HAL / CMSIS 资源的下载逻辑
2. 在 `compiler.py` 中补充该系列的编译参数（MCU flag、链接脚本等）
3. 在 `stm32_agent.py` 的芯片识别逻辑中注册新系列
4. 至少提供一个可编译通过的基础 `main.c` 模板
5. 在 PR 中说明你实际测试过的具体型号和开发板

---

### 📄 改善文档

文档贡献同样非常欢迎，包括但不限于：

- 修正 `README.md` / `README_CN.md` 中的错误或过时信息
- 补充 FAQ 条目（常见安装问题、特定芯片的坑）
- 添加典型使用场景的 `gary do` 示例
- 翻译文档到其他语言

文档类 PR 无需开 Issue，直接提交即可。

---

## Pull Request 规范

提交 PR 时，请确保：

- [ ] PR 标题简洁说明变更内容（中英文均可）
- [ ] PR 描述中填写：**变更原因**、**实现方式**、**测试方法**
- [ ] 如果修复了某个 Issue，在描述中加 `Closes #<issue号>`
- [ ] 新增功能已在本地通过 `gary doctor` 诊断
- [ ] 代码通过 `flake8` / `black` 格式检查（见下方）
- [ ] 不引入与项目无关的依赖

---

## 代码风格规范

本项目使用 Python，遵循以下规范：

```bash
# 安装格式化工具
pip install black flake8

# 格式化代码
black .

# 风格检查
flake8 . --max-line-length=100 --exclude=.venv
```

主要约定：

- 缩进：4 个空格
- 最大行长：100 字符
- 字符串优先使用双引号
- 函数和类需要有 docstring（尤其是工具函数，AI 会读取这些注释来理解工具用途）
- 避免在主流程中使用 `print()`，统一通过 `rich` 控制台输出

---

## Commit Message 规范

使用如下格式（参考 [Conventional Commits](https://www.conventionalcommits.org/)）：

```
<类型>(<范围>): <简短描述>

[可选正文：详细说明变更原因和内容]

[可选脚注：关联 Issue 或 Breaking Change 说明]
```

**类型：**

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 仅文档变更 |
| `skill` | 新增或更新 Skill 包 |
| `chip` | 新增芯片支持 |
| `refactor` | 重构（不影响功能） |
| `perf` | 性能优化 |
| `ci` | CI/CD 配置变更 |

**示例：**

```
feat(compiler): 添加 STM32G0 系列编译参数支持

支持 STM32G030/G031/G071 等常用型号，
补充对应的 HAL 下载逻辑和链接脚本配置。

Closes #42
```

```
skill: 新增 uart_protocol_analyzer Skill

支持对 UART 抓包数据进行协议分析，
识别常见传感器（DHT11、MPU6050）的通信帧格式。
```

---

## 常见问题

**Q：我没有 STM32 硬件，可以贡献代码吗？**  
可以。代码生成、编译流程、AI 后端对接、Skill 开发、文档改进等都不需要实体硬件。

**Q：Skill 可以调用外部网络请求吗？**  
可以，但请在 `skill.json` 的 `description` 和 `prompt.md` 中明确说明，让用户知道 Skill 会进行网络请求。

**Q：PR 被 Review 需要多久？**  
维护者会尽力在 7 天内响应。若超时未回复，欢迎在 PR 下留言 ping 一下。

**Q：我想重构某个核心模块，需要注意什么？**  
请先开 Issue 描述重构方案，讨论对齐后再动手。核心模块（如 `stm32_agent.py` 的 AI 调度循环）的重构需要保证对三种烧录方式（SWD / UART ISP / 无硬件）的行为一致性。

---

> **🗡️ Just Gary Do It.**  
> 每一行代码、每一个 Skill、每一条文档，都是对 STM32 开发者社区的礼物。

[返回主页](https://github.com/PrettyMyGirlZyy4Embedded/garycli) · [提交 Issue](https://github.com/PrettyMyGirlZyy4Embedded/garycli/issues) · [官网](https://www.garycli.com)
