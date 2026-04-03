# 正点原子探索版DHT11温湿度传感器驱动

## 简介

基于正点原子探索版STM32F407的DHT11温湿度传感器驱动，支持8080并口OLED显示和UART串口输出。

## 硬件连接

### DHT11引脚

| DHT11引脚 | 连接说明 |
|-----------|----------|
| VCC       | 3.3V 或 5V |
| GND       | GND |
| DATA      | PG9（默认，可配置） |

### OLED引脚（探索版8080并口）

| OLED引脚 | STM32引脚 |
|----------|----------|
| D0-D7    | PC6,PC7,PC8,PC9,PC11,PB6,PE5,PE6 |
| CS       | PB7 |
| DC       | PD6 |
| WR       | PA4 |
| RD       | PD7 |
| RST      | PG15 |

## 工具函数

### dht11_discovery_get_driver_code

获取DHT11驱动代码核心片段，可嵌入到main.c中使用。

**参数：**
- `port`: GPIO端口（默认GPIOG）
- `pin`: 引脚号（默认9）

**示例：**
```python
# 获取默认PG9的DHT11驱动
dht11_discovery_get_driver_code()

# 获取PA0的DHT11驱动
dht11_discovery_get_driver_code(port="GPIOA", pin=0)
```

### dht11_discovery_get_full_main

获取完整可编译的main.c（含DHT11 + OLED/UART显示）。

**参数：**
- `port`: GPIO端口（默认GPIOG）
- `pin`: 引脚号（默认9）
- `display`: 显示方式 (`oled`/`uart`/`none`)

**示例：**
```python
# OLED显示版本（默认）
dht11_discovery_get_full_main()

# 仅串口输出版本
dht11_discovery_get_full_main(display="uart")

# PA1引脚 + OLED显示
dht11_discovery_get_full_main(port="GPIOA", pin=1, display="oled")
```

## 使用示例

### 基础读取

```c
/* 读取温湿度 */
if (DHT11_Read() == 0) {
    uint8_t temp = DHT11_Get_Temp();  // 温度 °C
    uint8_t humi = DHT11_Get_Humi();  // 湿度 %
}
```

### 返回值说明

| 返回值 | 含义 |
|--------|------|
| 0      | 读取成功 |
| 1      | 通信失败/校验错误 |

## 注意事项

1. **读取间隔**：DHT11读取间隔至少2秒
2. **首次上电**：需等待1秒稳定
3. **DATA线**：建议接上拉电阻4.7KΩ到VCC，模块通常已集成
4. **精度**：温度±2°C，湿度±5%RH