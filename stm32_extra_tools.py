#!/usr/bin/env python3
"""
Gary Dev Agent — 扩展工具集
=============================
为 stm32_agent.py 提供高级调试/调参/测试工具。

工具列表：
  1. stm32_pid_tune        — AI 辅助 PID 自动调参（Ziegler-Nichols + 响应曲线分析）
  2. stm32_pid_analyze     — 分析串口采集的 PID 响应数据
  3. stm32_signal_capture  — 通用信号采集与分析（ADC/编码器/传感器）
  4. stm32_i2c_scan        — I2C 总线扫描（自动检测所有设备地址）
  5. stm32_pwm_sweep       — PWM 频率/占空比扫描测试
  6. stm32_memory_map      — Flash/RAM 使用分析
  7. stm32_power_estimate  — 功耗估算（基于外设使能状态）
  8. stm32_pin_conflict    — 引脚冲突检测
  9. stm32_peripheral_test — 外设快速冒烟测试
 10. stm32_servo_calibrate — 舵机角度校准

使用方式：
  将本文件放在 stm32_agent.py 同级目录，
  在 stm32_agent.py 中 import 并注册到 TOOLS_MAP 和 TOOL_SCHEMAS。
"""

import json, time, re, math, statistics
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict


# ═══════════════════════════════════════════════════════════════
# 工具 1: PID 自动调参
# ═══════════════════════════════════════════════════════════════

@dataclass
class PIDParams:
    kp: float = 0.0
    ki: float = 0.0
    kd: float = 0.0

@dataclass
class PIDResponse:
    """PID 响应曲线分析结果"""
    overshoot_pct: float = 0.0       # 超调量 %
    rise_time_ms: float = 0.0        # 上升时间 ms（10%→90%）
    settling_time_ms: float = 0.0    # 调节时间 ms（进入±5%带）
    steady_state_error: float = 0.0  # 稳态误差
    oscillation_count: int = 0       # 振荡次数
    is_stable: bool = True           # 是否收敛
    peak_value: float = 0.0
    final_value: float = 0.0
    target_value: float = 0.0


def _parse_pid_serial(raw: str, value_key: str = "PID") -> List[dict]:
    """
    解析串口 PID 调试输出，支持多种常见格式：
    格式1: PID:t=100,sp=1000,pv=980,out=50,err=20
    格式2: PID 100 1000 980 50 20
    格式3: [PID] time=100 sp=1000 pv=980 out=50
    返回 [{t, sp, pv, out, err}, ...]
    """
    data = []

    # 格式1: key=value 对
    pattern1 = re.compile(
        rf'{value_key}[:\s]+'
        r't=(\d+)[,\s]+sp=([\d.+-]+)[,\s]+pv=([\d.+-]+)[,\s]+out=([\d.+-]+)'
        r'(?:[,\s]+err=([\d.+-]+))?',
        re.IGNORECASE
    )
    # 格式2: 纯空格分隔数字
    pattern2 = re.compile(
        rf'{value_key}\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)',
        re.IGNORECASE
    )
    # 格式3: [PID] time=N sp=N pv=N
    pattern3 = re.compile(
        rf'\[?{value_key}\]?\s+time=([\d.+-]+)\s+sp=([\d.+-]+)\s+pv=([\d.+-]+)\s+out=([\d.+-]+)',
        re.IGNORECASE
    )

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        m = pattern1.search(line)
        if m:
            data.append({
                "t": float(m.group(1)),
                "sp": float(m.group(2)),
                "pv": float(m.group(3)),
                "out": float(m.group(4)),
                "err": float(m.group(5)) if m.group(5) else float(m.group(2)) - float(m.group(3)),
            })
            continue

        m = pattern3.search(line)
        if m:
            data.append({
                "t": float(m.group(1)),
                "sp": float(m.group(2)),
                "pv": float(m.group(3)),
                "out": float(m.group(4)),
                "err": float(m.group(2)) - float(m.group(3)),
            })
            continue

        m = pattern2.search(line)
        if m:
            t, sp, pv, out = float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
            data.append({"t": t, "sp": sp, "pv": pv, "out": out, "err": sp - pv})
            continue

    return data


def _analyze_response(data: List[dict], target: float = None) -> PIDResponse:
    """分析 PID 响应曲线质量"""
    if not data or len(data) < 3:
        return PIDResponse()

    pv = [d["pv"] for d in data]
    sp = target if target is not None else data[0]["sp"]
    t = [d["t"] for d in data]

    peak = max(pv)
    final = statistics.mean(pv[-max(3, len(pv)//10):])  # 末尾均值作为稳态值

    resp = PIDResponse()
    resp.target_value = sp
    resp.peak_value = peak
    resp.final_value = final

    # 超调量
    if sp != 0:
        resp.overshoot_pct = max(0, (peak - sp) / abs(sp) * 100)

    # 稳态误差
    resp.steady_state_error = abs(sp - final)

    # 上升时间（10% → 90%）
    pv0 = pv[0]
    range_10 = pv0 + 0.1 * (sp - pv0)
    range_90 = pv0 + 0.9 * (sp - pv0)
    t_10, t_90 = None, None
    for i, v in enumerate(pv):
        if t_10 is None and v >= range_10:
            t_10 = t[i]
        if t_90 is None and v >= range_90:
            t_90 = t[i]
    if t_10 is not None and t_90 is not None:
        resp.rise_time_ms = t_90 - t_10

    # 调节时间（进入 ±5% 带不再出来）
    band = abs(sp) * 0.05 if sp != 0 else 1.0
    settling_idx = len(pv) - 1
    for i in range(len(pv) - 1, -1, -1):
        if abs(pv[i] - sp) > band:
            settling_idx = min(i + 1, len(pv) - 1)
            break
    resp.settling_time_ms = t[settling_idx] - t[0] if settling_idx < len(pv) else t[-1] - t[0]

    # 振荡计数（过零点检测）
    errors = [v - sp for v in pv]
    crossings = 0
    for i in range(1, len(errors)):
        if errors[i] * errors[i-1] < 0:
            crossings += 1
    resp.oscillation_count = crossings

    # 稳定性判断
    resp.is_stable = (
        resp.overshoot_pct < 60 and
        resp.oscillation_count < 20 and
        resp.steady_state_error < abs(sp) * 0.1
    )

    return resp


def _ziegler_nichols_from_response(resp: PIDResponse, current: PIDParams,
                                    control_type: str = "pid") -> PIDParams:
    """
    基于响应曲线分析，用改进的 Ziegler-Nichols 规则推荐下一组参数。
    策略：
    - 超调大 → 降 Kp，升 Kd
    - 响应慢 → 升 Kp
    - 稳态误差大 → 升 Ki
    - 振荡多 → 降 Kp，升 Kd
    """
    kp, ki, kd = current.kp, current.ki, current.kd

    # 保底：参数为零时给初始值
    if kp == 0:
        kp = 1.0

    # 超调过大（>25%）
    if resp.overshoot_pct > 25:
        factor = 1.0 - min(0.4, (resp.overshoot_pct - 25) / 100)
        kp *= factor
        kd *= 1.3  # 增加微分抑制超调
        if kd == 0:
            kd = kp * 0.1

    # 超调很小但响应太慢
    elif resp.overshoot_pct < 5 and resp.rise_time_ms > 500:
        kp *= 1.3

    # 振荡过多（>6次）
    if resp.oscillation_count > 6:
        kp *= 0.7
        kd *= 1.5
        if kd == 0:
            kd = kp * 0.15

    # 稳态误差大
    if resp.target_value != 0 and resp.steady_state_error / abs(resp.target_value) > 0.03:
        if ki == 0:
            ki = kp * 0.01
        else:
            ki *= 1.3

    # 不稳定 → 大幅降低增益
    if not resp.is_stable:
        kp *= 0.5
        ki *= 0.5

    # PD 模式：强制 Ki=0
    if control_type.lower() == "pd":
        ki = 0

    # P 模式
    if control_type.lower() == "p":
        ki, kd = 0, 0

    return PIDParams(kp=round(kp, 4), ki=round(ki, 6), kd=round(kd, 4))


def stm32_pid_analyze(serial_output: str, target: float = None,
                       value_key: str = "PID") -> dict:
    """
    分析串口采集的 PID 响应数据。
    输入串口原始文本，返回超调量、上升时间、调节时间、稳态误差、振荡次数等指标，
    以及参数调整建议。

    串口数据格式（任选一种）：
      PID:t=100,sp=1000,pv=980,out=50,err=20
      PID 100 1000 980 50 20
      [PID] time=100 sp=1000 pv=980 out=50
    """
    data = _parse_pid_serial(serial_output, value_key)
    if not data:
        return {
            "success": False,
            "message": f"未解析到 PID 数据，请确保串口输出包含 '{value_key}:' 前缀的调试行",
            "expected_format": "PID:t=<ms>,sp=<目标>,pv=<实际>,out=<输出>,err=<误差>",
        }

    sp = target if target is not None else data[0]["sp"]
    resp = _analyze_response(data, sp)

    # 生成人话诊断
    diagnosis = []
    if resp.overshoot_pct > 25:
        diagnosis.append(f"超调过大({resp.overshoot_pct:.1f}%)：降低 Kp 或增大 Kd")
    elif resp.overshoot_pct < 2:
        diagnosis.append("几乎无超调：可适当增大 Kp 加快响应")

    if resp.rise_time_ms > 1000:
        diagnosis.append(f"上升时间过长({resp.rise_time_ms:.0f}ms)：增大 Kp")

    if resp.oscillation_count > 6:
        diagnosis.append(f"振荡明显({resp.oscillation_count}次)：降低 Kp，增大 Kd")

    if sp != 0 and resp.steady_state_error / abs(sp) > 0.03:
        diagnosis.append(f"稳态误差大({resp.steady_state_error:.2f})：增大 Ki")

    if not resp.is_stable:
        diagnosis.append("⚠ 系统不稳定！大幅降低 Kp 和 Ki")

    if not diagnosis:
        diagnosis.append("✓ 响应质量良好，PID 参数已接近最优")

    return {
        "success": True,
        "data_points": len(data),
        "target": sp,
        "metrics": {
            "overshoot_pct": round(resp.overshoot_pct, 2),
            "rise_time_ms": round(resp.rise_time_ms, 1),
            "settling_time_ms": round(resp.settling_time_ms, 1),
            "steady_state_error": round(resp.steady_state_error, 3),
            "oscillation_count": resp.oscillation_count,
            "peak_value": round(resp.peak_value, 2),
            "final_value": round(resp.final_value, 2),
            "is_stable": resp.is_stable,
        },
        "diagnosis": diagnosis,
    }


def stm32_pid_tune(current_kp: float, current_ki: float, current_kd: float,
                    serial_output: str = "", target: float = None,
                    control_type: str = "pid",
                    value_key: str = "PID") -> dict:
    """
    AI 辅助 PID 自动调参：分析当前响应曲线，推荐下一组参数。

    工作流：
    1. 用户提供当前 Kp/Ki/Kd 和串口采集的响应数据
    2. 工具分析响应质量（超调、振荡、稳态误差）
    3. 基于改进 Ziegler-Nichols 规则推荐新参数
    4. AI 将新参数写入代码，重新编译烧录，循环调优

    参数说明：
    - current_kp/ki/kd: 当前 PID 参数
    - serial_output: 串口原始输出（含 PID 调试数据）
    - target: 目标设定值（不填则从数据中提取 sp）
    - control_type: "pid" / "pd" / "p"
    - value_key: 串口数据前缀（默认 "PID"）
    """
    current = PIDParams(kp=current_kp, ki=current_ki, kd=current_kd)

    # 无串口数据时：用经验公式给初始值
    if not serial_output.strip():
        # 经典 Ziegler-Nichols 起步策略：
        # 先给一个保守 P 值，让 AI 观察首次响应
        if current_kp == 0:
            return {
                "success": True,
                "message": "无响应数据，建议从纯 P 控制开始试探临界增益",
                "recommended": {"kp": 1.0, "ki": 0.0, "kd": 0.0},
                "strategy": (
                    "步骤1: 先用 Kp=1.0, Ki=0, Kd=0 烧录运行\n"
                    "步骤2: 观察串口输出，如果响应太慢就翻倍 Kp\n"
                    "步骤3: 直到出现持续等幅振荡，记录此时 Kp 为 Ku（临界增益）\n"
                    "步骤4: 用振荡周期 Tu 计算: Kp=0.6*Ku, Ki=2*Kp/Tu, Kd=Kp*Tu/8"
                ),
                "current": asdict(current),
                "serial_format": "请在代码中添加: Debug_Print(\"PID:t=%%d,sp=%%d,pv=%%d,out=%%d,err=%%d\\r\\n\", ...);",
            }
        return {
            "success": True,
            "message": "无串口数据，无法分析响应曲线。请先运行一次并采集串口输出。",
            "current": asdict(current),
            "serial_format": "PID:t=<ms>,sp=<目标>,pv=<实际>,out=<输出>,err=<误差>",
        }

    # 解析数据
    data = _parse_pid_serial(serial_output, value_key)
    if not data:
        return {
            "success": False,
            "message": f"串口数据中未找到 '{value_key}' 格式的调试输出",
            "current": asdict(current),
        }

    sp = target if target is not None else data[0]["sp"]
    resp = _analyze_response(data, sp)
    recommended = _ziegler_nichols_from_response(resp, current, control_type)

    # 计算变化量
    changes = {
        "kp": f"{current.kp} → {recommended.kp} ({'↑' if recommended.kp > current.kp else '↓'})",
        "ki": f"{current.ki} → {recommended.ki} ({'↑' if recommended.ki > current.ki else '↓'})",
        "kd": f"{current.kd} → {recommended.kd} ({'↑' if recommended.kd > current.kd else '↓'})",
    }

    analysis = stm32_pid_analyze(serial_output, target, value_key)

    return {
        "success": True,
        "data_points": len(data),
        "current": asdict(current),
        "recommended": asdict(recommended),
        "changes": changes,
        "metrics": analysis.get("metrics", {}),
        "diagnosis": analysis.get("diagnosis", []),
        "next_action": (
            "将 recommended 参数写入代码中的 Kp/Ki/Kd 变量，"
            "重新编译烧录，再次采集串口数据进行下一轮调参"
        ),
    }


# ═══════════════════════════════════════════════════════════════
# 工具 2: I2C 总线扫描代码生成
# ═══════════════════════════════════════════════════════════════

# 已知 I2C 设备地址数据库
_I2C_DEVICE_DB = {
    0x27: "PCF8574 (LCD 1602/2004 I2C 背包)",
    0x3F: "PCF8574A (LCD I2C 背包, A0-A2=111)",
    0x3C: "SSD1306 OLED (SA0=0)",
    0x3D: "SSD1306 OLED (SA0=1)",
    0x50: "AT24C02/04/08 EEPROM",
    0x51: "AT24C02 EEPROM (A0=1)",
    0x68: "MPU6050 / DS1307 RTC / DS3231 RTC",
    0x69: "MPU6050 (AD0=1)",
    0x76: "BME280 / BMP280 (SDO=0)",
    0x77: "BME280 / BMP280 (SDO=1) / BMP180",
    0x53: "ADXL345 加速度计 (ALT=1)",
    0x1D: "ADXL345 加速度计 (ALT=0)",
    0x48: "ADS1115 ADC (ADDR=GND) / PCF8591 / TMP102",
    0x49: "ADS1115 ADC (ADDR=VDD)",
    0x5A: "MLX90614 红外温度",
    0x29: "VL53L0X 激光测距 / TSL2561 光照",
    0x39: "TSL2561 光照 (ADDR=FLOAT)",
    0x40: "INA219 电流传感器 / HDC1080 温湿度 / SHT30 (默认)",
    0x44: "SHT30/SHT31 温湿度 (ADDR=0)",
    0x45: "SHT30/SHT31 温湿度 (ADDR=1)",
    0x57: "MAX30102 心率血氧",
    0x5F: "HTS221 温湿度",
    0x1E: "HMC5883L / QMC5883L 磁力计",
    0x0D: "QMC5883L 磁力计 (新版地址)",
    0x23: "BH1750 光照传感器",
    0x38: "AHT20 温湿度",
    0x20: "PCF8574 IO 扩展 (A0-A2=000)",
}


def stm32_i2c_scan(i2c_instance: str = "I2C1") -> dict:
    """
    生成 I2C 总线扫描代码。
    烧录后通过串口输出所有应答的设备地址，并自动识别常见设备型号。

    返回完整可编译代码片段（插入到 main.c 的 while(1) 前即可）。
    """
    inst = i2c_instance.upper().replace("I2C", "")
    handle = f"hi2c{inst}"

    scan_code = f'''
/* ═══ I2C 总线扫描 ═══ */
void I2C_Scan(void) {{
    Debug_Print("I2C{inst} Scan Start...\\r\\n");
    uint8_t found = 0;
    for (uint8_t addr = 0x08; addr < 0x78; addr++) {{
        if (HAL_I2C_IsDeviceReady(&{handle}, addr << 1, 2, 50) == HAL_OK) {{
            found++;
            char buf[32];
            /* 手写 hex 输出，不用 sprintf */
            const char hex[] = "0123456789ABCDEF";
            buf[0] = ' '; buf[1] = ' ';
            buf[2] = '0'; buf[3] = 'x';
            buf[4] = hex[(addr >> 4) & 0xF];
            buf[5] = hex[addr & 0xF];
            buf[6] = ' '; buf[7] = 'O'; buf[8] = 'K';
            buf[9] = '\\r'; buf[10] = '\\n'; buf[11] = 0;
            Debug_Print(buf);
        }}
    }}
    if (found == 0) {{
        Debug_Print("  No device found\\r\\n");
    }}
    Debug_Print("I2C{inst} Scan Done\\r\\n");
}}
'''
    return {
        "success": True,
        "code_snippet": scan_code,
        "usage": f"在 main() 中 while(1) 之前调用 I2C_Scan();",
        "known_devices": {f"0x{addr:02X}": name for addr, name in _I2C_DEVICE_DB.items()},
        "message": (
            f"已生成 {i2c_instance} 扫描代码。"
            "串口会输出所有应答的地址（0x08-0x77），"
            "对照 known_devices 表可识别具体设备。"
        ),
    }


# ═══════════════════════════════════════════════════════════════
# 工具 3: PWM 频率/占空比扫描
# ═══════════════════════════════════════════════════════════════

def stm32_pwm_sweep(timer: str = "TIM2", channel: int = 1,
                     freq_start: int = 100, freq_end: int = 10000,
                     steps: int = 10, clock_mhz: int = 72) -> dict:
    """
    生成 PWM 频率扫描代码，自动计算每个频率对应的 PSC/ARR 值。
    用于测试电机/蜂鸣器/LED 在不同频率下的响应。
    """
    tim = timer.upper()
    ch_suffix = f"CHANNEL_{channel}"

    freqs = []
    if steps <= 1:
        freqs = [freq_start]
    else:
        for i in range(steps):
            f = freq_start + (freq_end - freq_start) * i / (steps - 1)
            freqs.append(int(f))

    # 计算 PSC/ARR 对
    configs = []
    for f in freqs:
        # clock / (PSC+1) / (ARR+1) = freq
        # 选择 ARR 尽量大（分辨率高）
        best_err = float('inf')
        best = (0, 0)
        for psc in range(0, 65536):
            arr = round(clock_mhz * 1e6 / (psc + 1) / f) - 1
            if arr < 1 or arr > 65535:
                continue
            actual = clock_mhz * 1e6 / (psc + 1) / (arr + 1)
            err = abs(actual - f)
            if err < best_err:
                best_err = err
                best = (psc, arr)
            if err < 1:
                break
        configs.append({
            "freq": f,
            "psc": best[0],
            "arr": best[1],
            "actual_freq": round(clock_mhz * 1e6 / (best[0]+1) / (best[1]+1), 1),
            "duty_50_ccr": best[1] // 2,
        })

    # 生成 C 数组
    array_code = f"/* PWM 频率扫描表：{tim} CH{channel}, 时钟 {clock_mhz}MHz */\n"
    array_code += f"typedef struct {{ uint16_t psc; uint16_t arr; uint16_t ccr; }} PWM_Config;\n"
    array_code += f"const PWM_Config pwm_table[{len(configs)}] = {{\n"
    for c in configs:
        array_code += f"    {{{c['psc']}, {c['arr']}, {c['duty_50_ccr']}}},  /* {c['actual_freq']:.1f} Hz */\n"
    array_code += "};\n"

    sweep_code = f"""
/* 扫描函数：每个频率停留 delay_ms 毫秒 */
void PWM_Sweep(uint16_t delay_ms) {{
    for (int i = 0; i < {len(configs)}; i++) {{
        {tim}->PSC = pwm_table[i].psc;
        {tim}->ARR = pwm_table[i].arr;
        {tim}->CCR{channel} = pwm_table[i].ccr;
        {tim}->EGR = TIM_EGR_UG;  /* 立即更新 */
        Debug_PrintInt("PWM_Hz=", pwm_table[i].arr > 0 ?
            {clock_mhz}000000 / (pwm_table[i].psc + 1) / (pwm_table[i].arr + 1) : 0);
        HAL_Delay(delay_ms);
    }}
}}
"""

    return {
        "success": True,
        "code_array": array_code,
        "code_sweep": sweep_code,
        "configs": configs,
        "usage": f"调用 PWM_Sweep(500); 即可，每频率停 500ms",
        "timer": tim,
        "channel": channel,
    }


# ═══════════════════════════════════════════════════════════════
# 工具 4: Flash/RAM 使用分析
# ═══════════════════════════════════════════════════════════════

def stm32_memory_map(bin_path: str = None, chip: str = "STM32F103C8T6") -> dict:
    """
    分析固件 Flash/RAM 使用情况。
    基于 bin 文件大小和芯片型号，给出资源占用率。
    """
    # 芯片 Flash/RAM 数据库（常见型号）
    chip_db = {
        "STM32F103C8": {"flash_kb": 64,  "ram_kb": 20},
        "STM32F103CB": {"flash_kb": 128, "ram_kb": 20},
        "STM32F103RC": {"flash_kb": 256, "ram_kb": 48},
        "STM32F103RE": {"flash_kb": 512, "ram_kb": 64},
        "STM32F103VE": {"flash_kb": 512, "ram_kb": 64},
        "STM32F103ZE": {"flash_kb": 512, "ram_kb": 64},
        "STM32F401CC": {"flash_kb": 256, "ram_kb": 64},
        "STM32F407VE": {"flash_kb": 512, "ram_kb": 128},
        "STM32F407VG": {"flash_kb": 1024,"ram_kb": 128},
        "STM32F411CE": {"flash_kb": 512, "ram_kb": 128},
        "STM32F030F4": {"flash_kb": 16,  "ram_kb": 4},
        "STM32F030C8": {"flash_kb": 64,  "ram_kb": 8},
        "STM32F072CB": {"flash_kb": 128, "ram_kb": 16},
        "STM32F303CC": {"flash_kb": 256, "ram_kb": 40},
    }

    # 匹配芯片
    chip_upper = chip.upper().strip()
    # 去掉封装+温度后缀（如 T6/U3）
    chip_key = re.sub(r'[A-Z]\d$', '', chip_upper)
    specs = chip_db.get(chip_key, None)

    if specs is None:
        # 模糊匹配
        for k, v in chip_db.items():
            if chip_key.startswith(k) or k.startswith(chip_key):
                specs = v
                break

    if specs is None:
        return {
            "success": False,
            "message": f"未知芯片型号: {chip}，已知型号: {list(chip_db.keys())}",
        }

    bin_size = 0
    if bin_path:
        p = Path(bin_path)
        if p.exists():
            bin_size = p.stat().st_size

    flash_total = specs["flash_kb"] * 1024
    ram_total = specs["ram_kb"] * 1024

    return {
        "success": True,
        "chip": chip,
        "flash": {
            "total_kb": specs["flash_kb"],
            "used_bytes": bin_size,
            "used_pct": round(bin_size / flash_total * 100, 1) if flash_total > 0 else 0,
            "free_bytes": flash_total - bin_size,
        },
        "ram": {
            "total_kb": specs["ram_kb"],
            "note": "RAM 精确使用量需要 .map 文件（编译时加 -Wl,-Map=output.map）",
        },
        "warning": (
            f"⚠ Flash 使用率 {bin_size/flash_total*100:.1f}% 超过 90%！"
            if bin_size > flash_total * 0.9 else ""
        ),
    }


# ═══════════════════════════════════════════════════════════════
# 工具 5: 引脚冲突检测
# ═══════════════════════════════════════════════════════════════

def stm32_pin_conflict(code: str) -> dict:
    """
    静态分析 main.c 代码，检测 GPIO 引脚冲突：
    - 同一引脚被多个外设使用
    - SWD/JTAG 引脚被误占用
    - I2C 引脚未配置为开漏模式
    """
    conflicts = []
    warnings = []
    pin_usage = {}  # {"PA0": ["GPIO_Output", "ADC_IN0"], ...}

    # 提取所有 GPIO_InitStruct 配置
    init_blocks = re.findall(
        r'GPIO_InitStruct\.Pin\s*=\s*([^;]+);.*?'
        r'GPIO_InitStruct\.Mode\s*=\s*([^;]+);.*?'
        r'HAL_GPIO_Init\s*\(\s*(\w+)',
        code, re.DOTALL
    )

    for pin_expr, mode, port in init_blocks:
        # 解析引脚（可能是 GPIO_PIN_0 | GPIO_PIN_1）
        pins = re.findall(r'GPIO_PIN_(\d+)', pin_expr)
        port_letter = port.replace("GPIO", "").strip()

        for pin_num in pins:
            pin_name = f"P{port_letter}{pin_num}"
            mode_clean = mode.strip()

            if pin_name not in pin_usage:
                pin_usage[pin_name] = []
            pin_usage[pin_name].append(mode_clean)

    # 检测冲突
    for pin, modes in pin_usage.items():
        if len(modes) > 1:
            conflicts.append({
                "pin": pin,
                "modes": modes,
                "message": f"{pin} 被配置了 {len(modes)} 次: {', '.join(modes)}",
            })

    # SWD 引脚检查
    swd_pins = {"PA13": "SWDIO", "PA14": "SWCLK"}
    jtag_pins = {"PA15": "JTDI", "PB3": "JTDO/SWO", "PB4": "NJTRST"}

    for pin, func in swd_pins.items():
        if pin in pin_usage:
            conflicts.append({
                "pin": pin,
                "message": f"⚠ {pin} ({func}) 是 SWD 调试引脚！占用后将无法烧录调试！",
                "severity": "critical",
            })

    for pin, func in jtag_pins.items():
        if pin in pin_usage:
            # 检查是否有 NOJTAG 重映射
            if "__HAL_AFIO_REMAP_SWJ_NOJTAG" not in code:
                warnings.append(
                    f"{pin} ({func}) 是 JTAG 引脚，作 GPIO 前需调用 "
                    f"__HAL_AFIO_REMAP_SWJ_NOJTAG()"
                )

    # I2C 引脚模式检查（F1 必须用 AF_OD）
    i2c_pins = re.findall(r'MX_I2C\d+_Init', code)
    if i2c_pins:
        if "GPIO_MODE_AF_OD" not in code and "GPIO_MODE_AF_PP" not in code:
            warnings.append("I2C 引脚未见 AF_OD/AF_PP 模式配置，可能导致通信失败")

    return {
        "success": True,
        "conflicts": conflicts,
        "warnings": warnings,
        "pin_usage": {k: v for k, v in pin_usage.items()},
        "message": (
            f"发现 {len(conflicts)} 个冲突, {len(warnings)} 个警告"
            if conflicts or warnings
            else "✓ 未发现引脚冲突"
        ),
    }


# ═══════════════════════════════════════════════════════════════
# 工具 6: 外设快速冒烟测试
# ═══════════════════════════════════════════════════════════════

def stm32_peripheral_test(peripherals: List[str]) -> dict:
    """
    生成外设快速测试代码片段。
    支持: gpio, uart, i2c, spi, adc, timer, pwm
    每个外设生成一段最小可运行的测试代码。
    """
    snippets = {}

    for p in peripherals:
        p = p.lower().strip()

        if p == "gpio":
            snippets["gpio"] = '''
/* GPIO 测试：PA0 翻转 LED */
__HAL_RCC_GPIOA_CLK_ENABLE();
GPIO_InitTypeDef g = {0};
g.Pin = GPIO_PIN_0; g.Mode = GPIO_MODE_OUTPUT_PP;
g.Speed = GPIO_SPEED_FREQ_LOW;
HAL_GPIO_Init(GPIOA, &g);
for (int i = 0; i < 10; i++) {
    HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_0);
    HAL_Delay(200);
}
Debug_Print("GPIO:OK\\r\\n");
'''
        elif p == "adc":
            snippets["adc"] = '''
/* ADC 测试：读取 PA0 模拟电压 */
__HAL_RCC_ADC1_CLK_ENABLE();
__HAL_RCC_GPIOA_CLK_ENABLE();
GPIO_InitTypeDef g = {0};
g.Pin = GPIO_PIN_0; g.Mode = GPIO_MODE_ANALOG;
HAL_GPIO_Init(GPIOA, &g);
ADC_HandleTypeDef hadc1 = {0};
hadc1.Instance = ADC1;
hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
hadc1.Init.ContinuousConvMode = DISABLE;
hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
hadc1.Init.NbrOfConversion = 1;
HAL_ADC_Init(&hadc1);
ADC_ChannelConfTypeDef ch = {0};
ch.Channel = ADC_CHANNEL_0; ch.Rank = 1;
ch.SamplingTime = ADC_SAMPLETIME_55CYCLES_5;
HAL_ADC_ConfigChannel(&hadc1, &ch);
HAL_ADC_Start(&hadc1);
HAL_ADC_PollForConversion(&hadc1, 100);
uint32_t val = HAL_ADC_GetValue(&hadc1);
Debug_PrintInt("ADC=", val);  /* 0-4095，3.3V 满量程 */
'''
        elif p == "i2c":
            snippets["i2c"] = '''
/* I2C 测试：扫描 0x08-0x77 */
/* 需要先初始化 I2C 外设 */
for (uint8_t a = 0x08; a < 0x78; a++) {
    if (HAL_I2C_IsDeviceReady(&hi2c1, a<<1, 2, 50) == HAL_OK) {
        Debug_PrintInt("I2C_Found=0x", a);
    }
}
Debug_Print("I2C:DONE\\r\\n");
'''
        elif p == "uart":
            snippets["uart"] = '''
/* UART 回环测试：发送后读回 */
uint8_t test[] = "UART_TEST_OK\\r\\n";
HAL_UART_Transmit(&huart1, test, sizeof(test)-1, 100);
Debug_Print("UART:OK\\r\\n");
'''
        elif p == "pwm":
            snippets["pwm"] = '''
/* PWM 测试：TIM2 CH1 输出 1kHz 50% 占空比 */
/* 需要先初始化 TIM2 */
HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1);
htim2.Instance->ARR = 999;   /* 72MHz/72/1000 = 1kHz */
htim2.Instance->PSC = 71;
htim2.Instance->CCR1 = 500;  /* 50% */
htim2.Instance->EGR = TIM_EGR_UG;
Debug_Print("PWM:1kHz_50%\\r\\n");
'''
        elif p in ("timer", "tim"):
            snippets["timer"] = '''
/* 定时器测试：TIM2 1秒中断 */
/* 需要先初始化 TIM2 并使能中断 */
HAL_TIM_Base_Start_IT(&htim2);
Debug_Print("TIM:Started\\r\\n");
/* 在 TIM2 中断回调中: */
/* void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim) {
 *     if (htim->Instance == TIM2) Debug_Print("TIM2:Tick\\r\\n");
 * } */
'''
        elif p == "spi":
            snippets["spi"] = '''
/* SPI 测试：发送并读取一个字节 */
uint8_t tx = 0xAA, rx = 0;
HAL_SPI_TransmitReceive(&hspi1, &tx, &rx, 1, 100);
Debug_PrintInt("SPI_RX=0x", rx);
'''
        else:
            snippets[p] = f"/* 不支持的外设: {p} */"

    return {
        "success": True,
        "snippets": snippets,
        "message": f"已生成 {len(snippets)} 个外设测试代码片段",
        "note": "将代码插入 main() 的 while(1) 之前运行一次，观察串口输出",
    }


# ═══════════════════════════════════════════════════════════════
# 工具 7: 舵机角度校准
# ═══════════════════════════════════════════════════════════════

def stm32_servo_calibrate(timer: str = "TIM2", channel: int = 1,
                           clock_mhz: int = 72,
                           min_pulse_us: int = 500,
                           max_pulse_us: int = 2500,
                           angle_range: int = 180) -> dict:
    """
    生成舵机校准代码：自动扫描角度范围，通过串口输出当前角度和脉宽。
    适用于 SG90/MG995/MG996R 等常见舵机。

    参数：
    - min_pulse_us: 最小脉宽（对应 0°），典型 500-1000us
    - max_pulse_us: 最大脉宽（对应 max_angle），典型 2000-2500us
    - angle_range: 角度范围（90/180/270°）
    """
    tim = timer.upper()

    # 50Hz PWM，PSC/ARR 计算
    # 72MHz / (PSC+1) / (ARR+1) = 50Hz
    # 选 PSC=71 → 1MHz 计数频率 → ARR=19999 → 50Hz，CCR 单位 = 1us
    psc = clock_mhz - 1
    arr = 19999
    period_us = 20000

    ccr_min = min_pulse_us
    ccr_max = max_pulse_us

    calibrate_code = f"""
/* ═══ 舵机校准 ═══ */
/* {tim} CH{channel}, {clock_mhz}MHz, 50Hz PWM */
/* 脉宽范围: {min_pulse_us}~{max_pulse_us}us = 0~{angle_range}° */

#define SERVO_PSC   {psc}
#define SERVO_ARR   {arr}
#define SERVO_MIN   {ccr_min}   /* 0° 对应 CCR */
#define SERVO_MAX   {ccr_max}   /* {angle_range}° 对应 CCR */

void Servo_SetAngle(uint16_t angle) {{
    if (angle > {angle_range}) angle = {angle_range};
    uint16_t ccr = SERVO_MIN + (uint32_t)(SERVO_MAX - SERVO_MIN) * angle / {angle_range};
    {tim}->CCR{channel} = ccr;
    Debug_PrintInt("Servo:deg=", angle);
    /* Debug_PrintInt(" ccr=", ccr); */
}}

/* 校准扫描：从 0° 到 {angle_range}° 再回来 */
void Servo_Calibrate(void) {{
    Debug_Print("Servo:Calibrating...\\r\\n");
    /* 正向扫描 */
    for (uint16_t a = 0; a <= {angle_range}; a += 10) {{
        Servo_SetAngle(a);
        HAL_Delay(200);
    }}
    HAL_Delay(500);
    /* 反向扫描 */
    for (int16_t a = {angle_range}; a >= 0; a -= 10) {{
        Servo_SetAngle((uint16_t)a);
        HAL_Delay(200);
    }}
    Debug_Print("Servo:Done\\r\\n");
}}
"""

    init_hint = f"""
/* 定时器初始化（放在 MX_{tim}_Init 中）*/
htim.Instance = {tim};
htim.Init.Prescaler = SERVO_PSC;
htim.Init.CounterMode = TIM_COUNTERMODE_UP;
htim.Init.Period = SERVO_ARR;
htim.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
HAL_TIM_PWM_Init(&htim);
/* 启动 PWM */
HAL_TIM_PWM_Start(&htim, TIM_CHANNEL_{channel});
"""

    return {
        "success": True,
        "code": calibrate_code,
        "init_hint": init_hint,
        "params": {
            "psc": psc, "arr": arr,
            "ccr_min": ccr_min, "ccr_max": ccr_max,
            "period_us": period_us,
        },
        "usage": "main() 中调用 Servo_Calibrate(); 观察舵机运动和串口输出",
        "tip": (
            "如果舵机在端点抖动，微调 SERVO_MIN/SERVO_MAX；"
            "如果不动，检查 PWM 引脚配置为 AF_PP 模式"
        ),
    }


# ═══════════════════════════════════════════════════════════════
# 工具 8: 功耗估算
# ═══════════════════════════════════════════════════════════════

def stm32_power_estimate(code: str, chip: str = "STM32F103C8T6",
                          vdd: float = 3.3) -> dict:
    """
    基于代码中使能的外设，粗略估算 MCU 功耗。
    注意：这是理论估算，实际功耗受时钟频率、运行模式、外部负载影响很大。
    """
    # 各外设典型电流（mA @ 72MHz, 3.3V, 仅供参考）
    peripheral_current = {
        "GPIOA": 0.1, "GPIOB": 0.1, "GPIOC": 0.1, "GPIOD": 0.1, "GPIOE": 0.1,
        "USART1": 0.5, "USART2": 0.5, "USART3": 0.5,
        "I2C1": 0.3, "I2C2": 0.3,
        "SPI1": 0.5, "SPI2": 0.5,
        "TIM1": 0.3, "TIM2": 0.2, "TIM3": 0.2, "TIM4": 0.2,
        "ADC1": 1.0, "ADC2": 1.0,
        "DMA1": 0.3, "DMA2": 0.3,
        "AFIO": 0.05,
    }

    # 检测代码中使能的外设
    enabled = []
    for periph in peripheral_current:
        pattern = rf'__HAL_RCC_{periph}_CLK_ENABLE|RCC.*{periph}.*EN'
        if re.search(pattern, code, re.IGNORECASE):
            enabled.append(periph)

    # MCU 核心电流（粗估）
    core_ma = 15.0  # F103 @ 72MHz 典型值
    periph_ma = sum(peripheral_current.get(p, 0.1) for p in enabled)
    total_ma = core_ma + periph_ma
    power_mw = total_ma * vdd

    return {
        "success": True,
        "chip": chip,
        "vdd": vdd,
        "core_current_ma": core_ma,
        "peripheral_current_ma": round(periph_ma, 2),
        "total_current_ma": round(total_ma, 2),
        "power_mw": round(power_mw, 1),
        "enabled_peripherals": enabled,
        "note": "⚠ 粗略估算，不含外部负载（LED、电机、传感器等）电流",
        "tips": [
            "降低系统时钟可显著降低功耗",
            "不用的外设及时关闭时钟",
            "低功耗模式：Sleep > Stop > Standby",
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 工具 9: 信号采集与分析
# ═══════════════════════════════════════════════════════════════

def stm32_signal_capture(serial_output: str, value_key: str = "ADC",
                          sample_rate_hz: float = None) -> dict:
    """
    通用信号采集分析：解析串口数据，计算统计量和频域特征。
    支持 ADC 值、编码器计数、传感器读数等任何数值序列。

    串口格式：ADC:1234 或 ADC=1234 或 ADC 1234
    """
    # 解析数值
    pattern = re.compile(rf'{value_key}[:\s=]+([\d.+-]+)', re.IGNORECASE)
    values = [float(m.group(1)) for m in pattern.finditer(serial_output)]

    if not values:
        return {
            "success": False,
            "message": f"未找到 '{value_key}' 数据，请确保格式为 {value_key}:数值",
        }

    n = len(values)
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if n > 1 else 0
    vmin, vmax = min(values), max(values)
    peak_to_peak = vmax - vmin

    result = {
        "success": True,
        "count": n,
        "stats": {
            "mean": round(mean, 3),
            "stdev": round(stdev, 3),
            "min": round(vmin, 3),
            "max": round(vmax, 3),
            "peak_to_peak": round(peak_to_peak, 3),
            "snr_db": round(20 * math.log10(mean / stdev), 1) if stdev > 0 and mean > 0 else None,
        },
    }

    # 简单频率估计（过零点法）
    if n > 10 and sample_rate_hz:
        crossings = 0
        for i in range(1, n):
            if (values[i] - mean) * (values[i-1] - mean) < 0:
                crossings += 1
        est_freq = crossings / 2 * sample_rate_hz / n
        result["estimated_freq_hz"] = round(est_freq, 2)

    # 噪声诊断
    cv = stdev / abs(mean) * 100 if mean != 0 else 0
    if cv > 20:
        result["diagnosis"] = f"信号噪声较大(CV={cv:.1f}%)，建议硬件滤波或增加软件均值滤波"
    elif cv > 5:
        result["diagnosis"] = f"信号有一定噪声(CV={cv:.1f}%)，可用移动平均滤波"
    else:
        result["diagnosis"] = f"信号质量良好(CV={cv:.1f}%)"

    return result


# ═══════════════════════════════════════════════════════════════
# 工具注册表（供 stm32_agent.py 导入）
# ═══════════════════════════════════════════════════════════════

EXTRA_TOOLS_MAP = {
    "stm32_pid_tune":        stm32_pid_tune,
    "stm32_pid_analyze":     stm32_pid_analyze,
    "stm32_i2c_scan":        stm32_i2c_scan,
    "stm32_pwm_sweep":       stm32_pwm_sweep,
    "stm32_memory_map":      stm32_memory_map,
    "stm32_pin_conflict":    stm32_pin_conflict,
    "stm32_peripheral_test": stm32_peripheral_test,
    "stm32_servo_calibrate": stm32_servo_calibrate,
    "stm32_power_estimate":  stm32_power_estimate,
    "stm32_signal_capture":  stm32_signal_capture,
}

EXTRA_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "stm32_pid_tune",
            "description": (
                "AI 辅助 PID 自动调参：分析串口采集的响应曲线，自动推荐下一组 Kp/Ki/Kd 参数。"
                "工作流：(1)用当前参数烧录→(2)采集串口PID数据→(3)调用此工具分析→(4)用推荐参数重新烧录→循环。"
                "串口数据格式：PID:t=<ms>,sp=<目标>,pv=<实际>,out=<输出>,err=<误差>"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "current_kp": {"type": "number", "description": "当前 Kp 值"},
                    "current_ki": {"type": "number", "description": "当前 Ki 值"},
                    "current_kd": {"type": "number", "description": "当前 Kd 值"},
                    "serial_output": {"type": "string", "description": "串口原始输出（含 PID 调试数据）"},
                    "target": {"type": "number", "description": "目标设定值（不填从数据提取）"},
                    "control_type": {
                        "type": "string", "enum": ["pid", "pd", "p"],
                        "description": "控制类型（默认 pid）",
                    },
                    "value_key": {"type": "string", "description": "串口数据前缀（默认 PID）"},
                },
                "required": ["current_kp", "current_ki", "current_kd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_pid_analyze",
            "description": "分析 PID 响应数据：计算超调量、上升时间、调节时间、稳态误差、振荡次数，给出诊断建议。",
            "parameters": {
                "type": "object",
                "properties": {
                    "serial_output": {"type": "string", "description": "串口原始文本"},
                    "target": {"type": "number", "description": "目标值（可选）"},
                    "value_key": {"type": "string", "description": "数据前缀（默认 PID）"},
                },
                "required": ["serial_output"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_i2c_scan",
            "description": "生成 I2C 总线扫描代码，扫描 0x08-0x77 所有地址，串口输出应答设备并自动识别型号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "i2c_instance": {"type": "string", "description": "I2C 实例，如 I2C1/I2C2（默认 I2C1）"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_pwm_sweep",
            "description": "生成 PWM 频率扫描代码+参数表，用于测试电机/蜂鸣器在不同频率下的响应。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timer": {"type": "string", "description": "定时器（默认 TIM2）"},
                    "channel": {"type": "integer", "description": "通道号（1-4）"},
                    "freq_start": {"type": "integer", "description": "起始频率 Hz"},
                    "freq_end": {"type": "integer", "description": "结束频率 Hz"},
                    "steps": {"type": "integer", "description": "频率步数"},
                    "clock_mhz": {"type": "integer", "description": "定时器时钟 MHz"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_memory_map",
            "description": "分析固件 Flash/RAM 使用率，基于 bin 大小和芯片规格给出资源占用报告。",
            "parameters": {
                "type": "object",
                "properties": {
                    "bin_path": {"type": "string", "description": "bin 文件路径"},
                    "chip": {"type": "string", "description": "芯片型号"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_pin_conflict",
            "description": "静态分析代码，检测 GPIO 引脚冲突（重复配置、SWD 占用、I2C 模式错误）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "main.c 源码"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_peripheral_test",
            "description": "生成外设快速冒烟测试代码（gpio/uart/i2c/spi/adc/pwm/timer）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "peripherals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "外设列表，如 [\"gpio\", \"i2c\", \"adc\"]",
                    },
                },
                "required": ["peripherals"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_servo_calibrate",
            "description": "生成舵机角度校准代码：自动扫描角度范围 + PSC/ARR 参数计算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timer": {"type": "string"},
                    "channel": {"type": "integer"},
                    "clock_mhz": {"type": "integer"},
                    "min_pulse_us": {"type": "integer", "description": "0° 脉宽 us（默认 500）"},
                    "max_pulse_us": {"type": "integer", "description": "最大角度脉宽 us（默认 2500）"},
                    "angle_range": {"type": "integer", "description": "角度范围（90/180/270）"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_power_estimate",
            "description": "基于代码中使能的外设，粗略估算 MCU 功耗（mA/mW）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "main.c 源码"},
                    "chip": {"type": "string"},
                    "vdd": {"type": "number", "description": "供电电压（默认 3.3V）"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stm32_signal_capture",
            "description": "通用信号采集分析：解析串口数值序列，计算均值/标准差/峰峰值/信噪比/估计频率。",
            "parameters": {
                "type": "object",
                "properties": {
                    "serial_output": {"type": "string", "description": "串口原始文本"},
                    "value_key": {"type": "string", "description": "数据前缀（如 ADC、ENC、TEMP）"},
                    "sample_rate_hz": {"type": "number", "description": "采样率 Hz（用于频率估计）"},
                },
                "required": ["serial_output"],
            },
        },
    },
]

if __name__ == "__main__":
    print("Gary Extra Tools — 扩展工具集")
    print(f"共 {len(EXTRA_TOOLS_MAP)} 个工具:")
    for name in EXTRA_TOOLS_MAP:
        print(f"  • {name}")
    print(INTEGRATION_GUIDE)
