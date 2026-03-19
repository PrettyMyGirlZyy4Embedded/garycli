<div align="center">

# 🗡️ GARY CLI: The Spear Carrier

**Piercing the Silicon with AI.**
*An AI-native command-line development and debugging agent built for STM32*

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/)
[![STM32](https://img.shields.io/badge/STM32-F0%20F1%20F3%20F4-blue.svg)](#supported-chips)
[![Website](https://img.shields.io/badge/Website-garycli.com-success)](https://www.garycli.com)

<br>

```text
   ██████╗  █████╗ ██████╗ ██╗   ██╗
  ██╔════╝ ██╔══██╗██╔══██╗╚██╗ ██╔╝
  ██║  ███╗███████║██████╔╝ ╚████╔╝
  ██║   ██║██╔══██║██╔══██╗  ╚██╔╝
  ╚██████╔╝██║  ██║██║  ██║   ██║
   ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝
```

**Talk to it in natural language, and let AI directly participate in STM32 development, compilation, flashing, and debugging.**

<p align="center">
  <a href="./README.md"><b>中文</b></a>
</p>

[Quick Start](#-quick-start) · [Core Features](#-core-features) · [Usage Guide](#-usage-guide) · [Command Reference](#-command-reference) · [Skill System](#-skill-system-skills) · [FAQ](#-faq)

</div>

---

## ⚡ What is Gary?

In traditional embedded development, the real time sink is usually not just “writing a few lines of C code,” but this full chain:

**Requirement understanding → Peripheral configuration → Code generation → Cross-compilation → Firmware flashing → Serial verification → Register inspection → Fault fixing → Reflashing**

**Gary (The Spear Carrier)** is not just another chat tool that can only “generate code.”
It is an **AI execution agent for STM32 development**: you describe the goal, and it generates code, invokes toolchains, connects to hardware, collects runtime feedback, and keeps fixing issues when the results are verifiable.

```text
You say:
  “Help me build an OLED temperature and humidity display using an AHT20 sensor.”

Gary automatically executes:
  ✓ Generates a complete main.c (HAL + I2C + AHT20 + SSD1306)
  ✓ Cross-compiles with arm-none-eabi-gcc
  ✓ Flashes the STM32 via SWD or UART ISP
  ✓ Monitors serial output to verify that the program really started
  ✓ Reads registers to inspect peripheral state
  ✗ Detects no I2C response → analyzes cause → patches code → reflashes
  ✓ Second run succeeds
```

In one sentence:

> **Gary is not just trying to “write STM32 code for you” — it is trying to complete an STM32 development loop for you.**

---

## 🎯 Core Features

### 🗣️ Natural language → compilable STM32 HAL project code

Describe the target behavior directly, and Gary generates complete STM32 HAL C code that can be cross-compiled.

```bash
gary do "PA0 has an LED connected. Make a breathing light with 1kHz PWM"
gary do "Read MPU6050 acceleration data over I2C1 and print it over UART"
gary do "Configure TIM2 in encoder mode to read motor speed"
```

Typical use cases:

* GPIO / PWM / ADC / EXTI
* UART / I2C / SPI / timers
* OLED / sensors / seven-segment displays / buzzers
* PID control / encoder feedback / motor control
* Rapid bare-metal prototyping

### 🔄 Automatic closed-loop debugging

Gary’s priority is not “getting it right on the first try,” but this:

```text
Generate code → Compile → Flash → Verify over serial → Read registers → Analyze issue → Patch code → Recompile and reflash
```

It tries to continue based on real feedback instead of stopping at “you may want to change this.”

Typical diagnostics include:

* **Compilation failures**: reads GCC errors and fixes syntax, symbol, or initialization problems
* **No program output**: checks startup path, SysTick, clock configuration, and UART init sequence
* **HardFault**: inspects SCB-related registers to help locate the fault type
* **I2C failures**: checks device address, bus lockup, init order, NACK/ARLO, and similar conditions
* **Multiple automatic repair rounds**: if it still cannot fix the issue, it tries to narrow it down clearly to either a **code problem** or a **hardware problem**

### ⚡ Consistent flashing and debugging strategy

Gary uses a clear and consistent hardware strategy:

* **SWD by default**: best for stable flashing, register access, fault analysis, and debug loops
* **UART ISP optional**: can be used when no debugger is available
* **Serial monitoring stays separate**: whether you flash over SWD or UART ISP, UART is still used to observe real runtime behavior

That means:

* **SWD** handles “flashing + debugging”
* **UART** handles “logs + runtime verification”

This is more stable than mixing flashing and runtime feedback together, and better matches real embedded workflows.

### 🧰 Built-in tools

| Tool                         | Purpose                                                                           |
| ---------------------------- | --------------------------------------------------------------------------------- |
| **PID Auto Tuning**          | Analyzes overshoot, oscillation, and steady-state error, then recommends Kp/Ki/Kd |
| **I2C Bus Scan**             | Scans device addresses and helps identify common chips                            |
| **Pin Conflict Detection**   | Detects GPIO mux conflicts, SWD pin misuse, and similar issues                    |
| **PWM Parameter Calculator** | Computes PSC/ARR automatically and quickly validates target frequencies           |
| **Servo Calibration**        | Generates angle sweep logic and maps pulse width to angle                         |
| **Signal Capture Analysis**  | Analyzes ADC/sensor waveform fluctuation, noise, and frequency characteristics    |
| **Peripheral Smoke Tests**   | One-click minimal test code for GPIO/UART/I2C/SPI/ADC                             |
| **Flash/RAM Analysis**       | Shows memory usage and warns about capacity issues                                |
| **Power Estimation**         | Estimates power consumption from enabled peripherals                              |
| **Font Generator**           | Converts Chinese/English text into OLED bitmap arrays                             |

### 🔌 Bring Your Own Key

Gary is not tied to a single AI provider. You can switch backends freely:

| Provider        | Model             | Notes                        |
| --------------- | ----------------- | ---------------------------- |
| DeepSeek        | deepseek-chat     | Cost-effective               |
| Kimi / Moonshot | kimi-k2.5         | Strong Chinese capability    |
| OpenAI          | gpt-4o            | Strong overall performance   |
| Google Gemini   | gemini-2.0-flash  | Fast response                |
| Tongyi Qianwen  | qwen-plus         | Alibaba Cloud                |
| Zhipu GLM       | glm-4-flash       | Easy to integrate            |
| Ollama          | qwen2.5-coder:14b | Local offline, fully private |

### 🧩 Skill System (Skills)

Gary supports pluggable skill packs to extend its capabilities.

```bash
/skill install pid_tuner.py
/skill install ~/Downloads/skill.zip
/skill install https://github.com/xxx/skill.git
/skill list
/skill create my_tool "My tool"
/skill export my_tool
```

Each Skill can include:

* Python tool functions
* OpenAI Function Calling schemas
* Prompt instructions
* Dependency files

Once installed, skills can be hot-loaded without restarting.

---

## 🚀 Quick Start

### One-line install

**Linux / macOS / WSL:**

```bash
curl -fsSL https://www.garycli.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://www.garycli.com/install.ps1 | iex
```

The install script will attempt to complete:

* Python environment check
* arm-none-eabi-gcc installation or detection
* HAL / CMSIS resource setup
* Python dependency installation
* Serial and debug tool installation
* CLI launcher command setup

### Manual installation

```bash
# 1. Clone the repository
git clone https://github.com/PrettyMyGirlZyy4Embedded/garycli.git
cd garycli

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install the cross compiler
# Ubuntu / Debian:
sudo apt install gcc-arm-none-eabi

# macOS:
brew install --cask gcc-arm-embedded

# Windows:
# Install gcc-arm-none-eabi from ARM official sources or a suitable distribution

# 4. Optional: install UART ISP flashing tool
pip install stm32loader

# 5. Optional: install SWD debugging tool
pip install pyocd

# 6. Download HAL resources
python3 setup.py --hal

# 7. Run environment diagnostics
python3 stm32_agent.py --doctor
```

### First-time configuration

```bash
gary config
```

Follow the prompts to configure:

* API Key
* Base URL
* Model
* Default chip model
* Default serial parameters (optional)

### Environment diagnostics

```bash
gary doctor
```

Example output:

```text
■ AI Interface
  ✓ API Key   sk-abc...xyz
  ✓ Base URL  https://api.deepseek.com/v1
  ✓ Model     deepseek-chat
  ✓ API connectivity  OK

■ Compilation Toolchain
  ✓ arm-none-eabi-gcc  arm-none-eabi-gcc (15.1.0)
  ✓ HAL resources      STM32F0xx, STM32F1xx, STM32F3xx, STM32F4xx
  ✓ CMSIS Core

■ Python Dependencies
  ✓ openai
  ✓ rich
  ✓ prompt_toolkit
  ✓ pyserial      (optional)
  ✓ pyocd         (optional)
  ✓ stm32loader   (optional)

■ Hardware Probes
  ✓ ST-Link V2
  ✓ Serial port /dev/ttyUSB0

✅ All core components are ready. Gary is good to go.
```

---

## 📖 Usage Guide

### Mode 1: One-shot task (`gary do`)

Best for quickly validating a single requirement:

```bash
# Generate + compile only (no hardware connection)
gary do "Write a WS2812 driver for 8 LEDs with a rainbow animation"

# Generate + compile + connect to hardware
gary do "Blink an LED on PA0 with a 500ms interval" --connect

# Specify chip model
gary do "Read ADC voltage and print it over UART" --chip STM32F407VET6 --connect
```

### Mode 2: Interactive conversation (`gary`)

Best for iterative, multi-turn development:

```bash
gary
gary --connect
gary --chip STM32F407VET6
gary --connect --chip STM32F103C8T6
```

Example:

```text
Gary > Help me build an OLED clock on I2C1 with SSD1306, showing HH:MM:SS

  🔧 stm32_reset_debug_attempts → counter reset
  🔧 stm32_hardware_status → chip: STM32F103C8T6, hw_connected: true
  🔧 stm32_generate_font → generated bitmap for "0123456789:"
  🔧 stm32_auto_flash_cycle → compile success 8.2KB, flash success
  Serial output: Gary:BOOT → OLED Init OK → 12:34:56

✓ OLED is now displaying the time correctly
```

### Mode 3: Incremental modifications

Gary tries to continue from the current project instead of rewriting everything from scratch each time:

```text
Gary > The LED is blinking too fast, change it to 1 second
Gary > Change it to common-anode seven-segment
Gary > Add a buzzer that sounds on alarm
Gary > Change the I2C address from 0x3C to 0x3D
```

This works well for continuous iteration on the same project.

---

## 📋 Command Reference

### Terminal commands

| Command                      | Description                           |
| ---------------------------- | ------------------------------------- |
| `gary`                       | Launch interactive conversation mode  |
| `gary do "task description"` | One-shot task mode                    |
| `gary do "task" --connect`   | One-shot task + auto-connect hardware |
| `gary --chip STM32F407VET6`  | Specify chip model                    |
| `gary --connect`             | Launch and connect hardware           |
| `gary config`                | Configure AI backend                  |
| `gary doctor`                | Run environment diagnostics           |

### Interactive commands (inside `Gary >`)

| Command                     | Description                                     |
| --------------------------- | ----------------------------------------------- |
| `/connect [chip]`           | Connect debugger or initialize hardware context |
| `/disconnect`               | Disconnect hardware                             |
| `/serial [port] [baudrate]` | Connect serial port                             |
| `/serial list`              | List available serial ports                     |
| `/chip [model]`             | Show or switch chip model                       |
| `/flash [swd\|uart\|auto]`  | Set flashing method                             |
| `/flash status`             | Show flashing tool status                       |
| `/probes`                   | List debug probes                               |
| `/status`                   | Show full hardware status                       |
| `/config`                   | Reconfigure AI backend                          |
| `/projects`                 | Show project history                            |
| `/skill list`               | List installed skills                           |
| `/skill install <source>`   | Install a skill pack                            |
| `/skill create <name>`      | Create a skill template                         |
| `/clear`                    | Clear conversation history                      |
| `/exit`                     | Exit                                            |

---

## 🔌 Hardware Connection Recommendations

### Recommended setup: SWD + serial logging

This is the most stable combination:

* **SWD**: flashing, register inspection, fault debugging
* **UART**: serial monitoring and startup verification

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

### Pure serial setup (no debugger)

If you do not have an ST-Link, you can also use only a USB-TTL adapter and flash over UART ISP, but capability will be limited:

* Flashing is possible
* Serial output is visible
* **Register reads and fault analysis are not as convenient as with SWD**

So SWD is still strongly recommended when available.

---

## 🧩 Skill System (Skills)

Gary supports capability extensions through skill packs. A standard Skill directory looks like this:

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

### Install a skill

```bash
/skill install stm32_extra_tools.py
/skill install ~/Downloads/gary_skill_pid_tuner.zip
/skill install https://github.com/someone/gary-skill-motor.git
/skill install ~/my_skills/sensor_kit/
```

### Manage skills

```bash
/skill list
/skill info pid_tuner
/skill disable pid_tuner
/skill enable pid_tuner
/skill uninstall pid_tuner
/skill reload
```

### Build your own Skill

```bash
# 1. Create a template
/skill create motor_driver "DC motor PID control tool"

# 2. Edit the generated files
# ~/.gary/skills/motor_driver/tools.py
# ~/.gary/skills/motor_driver/schemas.json
# ~/.gary/skills/motor_driver/prompt.md

# 3. Hot reload
/skill reload

# 4. Export for sharing
/skill export motor_driver
```

### Skill development spec

**tools.py**:

```python
def motor_set_speed(rpm: int) -> dict:
    """Set motor speed"""
    return {"success": True, "message": f"Target speed: {rpm} RPM"}

TOOLS_MAP = {
    "motor_set_speed": motor_set_speed,
}
```

**schemas.json**:

```json
[
  {
    "type": "function",
    "function": {
      "name": "motor_set_speed",
      "description": "Set the target speed of a DC motor",
      "parameters": {
        "type": "object",
        "properties": {
          "rpm": {
            "type": "integer",
            "description": "Target speed in RPM"
          }
        },
        "required": ["rpm"]
      }
    }
  }
]
```

**prompt.md**:

```markdown
## Motor Control
When the user wants to control a motor, call motor_set_speed to set the target RPM.
```

---

## 🏗️ Architecture

```text
┌──────────────────────────────────────────────────────┐
│                    Gary CLI (TUI)                    │
│              rich + prompt_toolkit                   │
├──────────────────────────────────────────────────────┤
│                   AI Conversation Engine             │
│         Streaming dialogue + Function Calling        │
│   DeepSeek │ Kimi │ GPT │ Gemini │ Ollama │ ...     │
├──────────────┬──────────────┬────────────────────────┤
│  Code Gen     │   Compiler    │   Hardware Backend    │
│  HAL templates │  GCC Cross   │  ┌─────────────────┐  │
│  Project reuse │  Compiler    │  │ SWD (default)   │  │
│  Template base │              │  │ pyocd           │  │
│                │              │  ├─────────────────┤  │
│                │              │  │ UART ISP opt.   │  │
│                │              │  │ stm32loader     │  │
│                │              │  ├─────────────────┤  │
│                │              │  │ Serial monitor  │  │
│                │              │  │ pyserial        │  │
│                │              │  └─────────────────┘  │
├──────────────┴──────────────┴────────────────────────┤
│                   Skill System (Skills)              │
│   PID tuning │ I2C scan │ PWM tools │ Font gen │ ... │
└──────────────────────────────────────────────────────┘
```

---

## <a name="supported-chips"></a> 📟 Supported Chips

Gary currently focuses on the following STM32 series:

| Series      | Typical models               | Flash       | RAM       |
| ----------- | ---------------------------- | ----------- | --------- |
| **STM32F0** | F030F4, F030C8, F072CB       | 16–128 KB   | 4–16 KB   |
| **STM32F1** | F103C8T6, F103RCT6, F103ZET6 | 64–512 KB   | 20–64 KB  |
| **STM32F3** | F303CCT6, F303RCT6           | 256 KB      | 40 KB     |
| **STM32F4** | F401CCU6, F407VET6, F411CEU6 | 256–1024 KB | 64–128 KB |

> Other models may also work by adding HAL / CMSIS resources and templates, but this README only makes explicit commitments for the series listed above.

---

## 💡 Practical Examples

### 🔰 LED blink

```text
Gary > Help me make an LED blink on PA0 with a 500ms interval
```

### 🔢 Seven-segment display

```text
Gary > A 4-digit common-anode seven-segment display, PA0-PA7 for segment select, PB0-PB3 for digit select, show a counter
```

### 📡 Sensor reading

```text
Gary > Connect an AHT20 temperature and humidity sensor to I2C1 and print temperature and humidity over UART
Gary > Now add an SSD1306 OLED to display the temperature too
```

### 🎛️ PID motor speed control

```text
Gary > DC motor PID speed control: TIM2 CH1 outputs PWM, TIM3 encoder reads feedback, target 500rpm
```

### 🔍 I2C troubleshooting

```text
Gary > I connected several I2C devices but I’m not sure about the addresses, help me scan them
```

### 🎵 Buzzer music

```text
Gary > A passive buzzer is connected to PA1. Help me play Twinkle Twinkle Little Star
```

### 🖥️ Chinese text on OLED

```text
Gary > Display the Chinese text “你好世界” on the OLED with a 16x16 font
```

---

## 📁 Project Structure

This layout is closer to the repository’s current structure:

```text
garycli/
├── stm32_agent.py          # Main program: TUI + AI dialogue + tool orchestration
├── compiler.py             # GCC cross-compilation wrapper
├── config.py               # Config files and path management
├── setup.py                # Installation and initialization script
├── stm32_extra_tools.py    # Extra tool collection
├── gary_skills.py          # Skill system manager
├── requirements.txt        # Python dependencies
├── install.sh              # Linux / macOS / WSL install script
├── install.ps1             # Windows install script
└── ~/.gary/                # User data directory
    ├── skills/             # Installed skills
    ├── projects/           # Historical project archives
    ├── templates/          # Template library
    └── member.md           # Knowledge / memory base
```

---

## ❓ FAQ

### Installation

<details>
<summary><b>Q: I installed arm-none-eabi-gcc, but it still cannot be found.</b></summary>

Confirm it is in your PATH:

```bash
which arm-none-eabi-gcc
```

If nothing is returned, add it to PATH manually or run `gary doctor` for diagnosis.

</details>

<details>
<summary><b>Q: HAL resource download failed.</b></summary>

```bash
python3 setup.py --hal
# Or specify families
python3 setup.py --hal f1 f4
```

</details>

<details>
<summary><b>Q: Serial port permissions or drivers are broken on Windows.</b></summary>

Make sure the CH340 / CP2102 driver is installed and that the corresponding COM port appears in Device Manager.

</details>

<details>
<summary><b>Q: On Linux, opening the serial port returns Permission denied.</b></summary>

```bash
sudo usermod -aG dialout $USER
newgrp dialout
```

</details>

### Usage

<details>
<summary><b>Q: UART flashing does not respond.</b></summary>

Check the following:

1. Whether BOOT0 is pulled high for download mode
2. Whether the board has been reset
3. Whether TX / RX are cross-connected
4. Whether the port and baudrate are correct

</details>

<details>
<summary><b>Q: Compilation fails with undefined reference to _sbrk.</b></summary>

This usually means the code pulls in symbols that depend on heap support, such as `printf`, `sprintf`, or `malloc`. For minimal bare-metal projects, it is better to avoid these directly.

</details>

<details>
<summary><b>Q: How do I debug a HardFault?</b></summary>

SWD is recommended. Gary can use register information to help classify the issue:

* `PRECISERR`: often caused by accessing a peripheral before it is ready
* `UNDEFINSTR`: may indicate stack corruption, bad branching, or invalid instructions
* `IACCVIOL`: may indicate access to an illegal code region

</details>

<details>
<summary><b>Q: Can I use a local model through Ollama?</b></summary>

Yes. Run `gary config` and select Ollama. Models with more stable function-calling behavior are recommended.

</details>

<details>
<summary><b>Q: Does it support Arduino or ESP32?</b></summary>

STM32 is the current primary target. Other platforms are planned for future expansion.

</details>

---

## 🗺️ Roadmap

* [x] Basic support for STM32F0 / F1 / F3 / F4
* [x] UART ISP flashing support
* [x] SWD debugging and register inspection
* [x] Skill system (Skills)
* [x] Early template library and experience base
* [ ] Skill marketplace (browse / install community skills online)
* [ ] Real-time serial data visualization
* [ ] STM32CubeMX project import
* [ ] VS Code extension
* [ ] ESP32 support

---

## 🤝 Contributing

Issues and PRs are welcome. Contributions are especially appreciated in these areas:

* New Skill packs
* More STM32 family support
* Documentation improvements and translations
* Fault reproduction and fixes
* Example projects and demo videos

### Contributing a Skill

```bash
# 1. Create a template
/skill create my_awesome_tool "My tool"

# 2. Develop and test
# Edit ~/.gary/skills/my_awesome_tool/

# 3. Export
/skill export my_awesome_tool

# 4. Submit a PR
```

---

## 📜 License

This project is released under the [Apache-2.0 License](https://opensource.org/licenses/Apache-2.0).

---

<div align="center">

**🗡️ Just Gary Do It.**

[Website](https://www.garycli.com) · [GitHub](https://github.com/PrettyMyGirlZyy4Embedded/garycli) · [Submit an Issue](https://github.com/PrettyMyGirlZyy4Embedded/garycli/issues)

</div>
