# 正点原子DHT11温湿度传感器驱动

## 简介

基于正点原子官方DHT11驱动封装，时序精准，读取稳定。

## 硬件连接

| DHT11引脚 | 连接说明 |
|-----------|----------|
| VCC       | 3.3V 或 5V |
| GND       | GND |
| DATA      | 任意GPIO（默认PG11） |

## 工具函数

### dht11_atomic_get_driver_code

获取DHT11驱动代码核心片段。

**参数：**
- `port`: GPIO端口（默认GPIOG）
- `pin`: 引脚号（默认11）

**示例：**
```python
# 获取PG11的DHT11驱动
dht11_atomic_get_driver_code(port="GPIOG", pin=11)

# 获取PA0的DHT11驱动
dht11_atomic_get_driver_code(port="GPIOA", pin=0)
```

### dht11_atomic_get_full_main

获取完整可编译的main.c（含DHT11 + OLED显示）。

**参数：**
- `port`: GPIO端口
- `pin`: 引脚号
- `display`: 显示方式 (`oled`/`uart`/`none`)

## 使用示例

### 基础读取

```c
/* 读取温湿度 */
if (DHT11_Read() == 0) {
    uint8_t temp = DHT11_Get_Temp();  // 温度
    uint8_t humi = DHT11_Get_Humi();  // 湿度
}
```

### 返回值说明

| 返回值 | 含义 |
|--------|------|
| 0      | 读取成功 |
| 1      | 设备未响应 |
| 2      | 校验失败 |

## 注意事项

1. 读取间隔至少2秒
2. 首次上电需等待1秒稳定
3. DATA线建议接上拉电阻（模块通常已集成）
