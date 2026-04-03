# 正点原子DS18B20温度传感器驱动

基于正点原子官方DS18B20驱动封装，单总线协议，精度0.1°C。

## 硬件连接

| DS18B20引脚 | 连接说明 |
|-------------|----------|
| VCC         | 3.3V 或 5V |
| GND         | GND |
| DQ          | 任意GPIO（默认PG11）|

> **注意**: DQ数据线建议接上拉电阻4.7KΩ到VCC，模块通常已集成。

## 工具函数

### ds18b20_atomic_get_driver_code

获取DS18B20驱动代码核心片段。

**参数：**
- `port`: GPIO端口（默认`GPIOG`）
- `pin`: 引脚号（默认`11`）

**示例：**
```python
# 获取PG11的DS18B20驱动
ds18b20_atomic_get_driver_code(port="GPIOG", pin=11)

# 获取PA0的DS18B20驱动
ds18b20_atomic_get_driver_code(port="GPIOA", pin=0)
```

### ds18b20_atomic_get_full_main

获取完整可编译的main.c（含DS18B20 + OLED/UART显示）。

**参数：**
- `port`: GPIO端口
- `pin`: 引脚号
- `display`: 显示方式 (`oled`/`uart`/`none`)

**示例：**
```python
# OLED显示版本（正点原子精英板）
ds18b20_atomic_get_full_main(port="GPIOG", pin=11, display="oled")

# 仅串口输出版本
ds18b20_atomic_get_full_main(port="GPIOG", pin=11, display="uart")
```

## 使用示例

### 基础读取

```c
/* 检测DS18B20是否在线 */
if (DS18B20_Check() == 0) {
    Debug_Print("DS18B20 found\r\n");
}

/* 读取温度 */
DS18B20_Start();           /* 启动转换 */
HAL_Delay(750);            /* 等待转换完成（必须≥750ms）*/
int16_t temp = DS18B20_ReadTemp();  /* 返回温度×10，如255=25.5°C */

/* 解析温度 */
uint8_t integer = temp / 10;   /* 整数部分 */
uint8_t decimal = temp % 10;   /* 小数部分 */
```

### 返回值说明

| 函数 | 返回值 | 含义 |
|------|--------|------|
| `DS18B20_Check()` | 0 | 设备存在 |
| | 1 | 设备未响应 |
| `DS18B20_ReadTemp()` | 850 | 读取错误（默认值）|
| | 其他 | 温度值×10 |

## 时序说明

DS18B20使用严格的单总线时序：
- **复位脉冲**: 主机拉低480μs，等待设备应答
- **写0**: 拉低60μs
- **写1**: 拉低15μs后释放
- **读时隙**: 拉低5μs后释放，15μs内采样

## 注意事项

1. **转换时间**: 12位精度需要750ms，程序中必须`HAL_Delay(750)`
2. **读取间隔**: 建议≥2秒，频繁读取会导致温度不准
3. **寄生供电**: 本驱动使用外部供电模式
4. **多设备**: 当前代码跳过ROM（0xCC），只支持单设备
