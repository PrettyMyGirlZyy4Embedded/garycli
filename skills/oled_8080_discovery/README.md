# 正点原子探索版OLED 8080驱动

## 简介

正点原子STM32F407ZG探索版OLED 8080并口驱动，支持DS18B20温度传感器读取和显示。

**特性：**
- 8080并口通信，刷新速度快
- 支持DS18B20单总线温度传感器
- OLED_ShowTemp自动清除残留字符（解决温度跳动问题）
- 支持字符串、数字显示

## 硬件连接（STM32F407ZG探索版）

### OLED 8080并口
| OLED引脚 | STM32引脚 | 说明 |
|---------|----------|------|
| CS      | PB7      | 片选 |
| WR      | PA4      | 写使能 |
| RST     | PG15     | 复位 |
| DC      | PD6      | 数据/命令 |
| RD      | PD7      | 读使能 |
| D0-D3   | PC6-PC9  | 数据线 |
| D4      | PC11     | 数据线 |
| D5      | PB6      | 数据线 |
| D6      | PE5      | 数据线 |
| D7      | PE6      | 数据线 |

### DS18B20传感器（U19接口）
| DS18B20引脚 | 连接 |
|-------------|------|
| VCC         | 3.3V |
| GND         | GND  |
| DQ          | PG9  |

**注意：** PG9同时连接摄像头OV_PWDN信号，两者不能同时使用

## 工具函数

### oled_8080_discovery_get_driver_code

获取OLED驱动代码核心片段（初始化、显示函数）。

**示例：**
```python
oled_8080_discovery_get_driver_code()
```

### oled_8080_discovery_get_ds18b20_code

获取DS18B20驱动代码。

**参数：**
- `port`: GPIO端口（默认GPIOG）
- `pin`: 引脚号（默认9）

**示例：**
```python
oled_8080_discovery_get_ds18b20_code(port="GPIOG", pin=9)
```

### oled_8080_discovery_get_full_main

获取完整可编译的main.c（DS18B20 + OLED显示）。

**参数：**
- `display`: 显示方式 (`oled`/`uart`/`none`，默认`oled`)

**示例：**
```python
oled_8080_discovery_get_full_main(display="oled")
```

## 使用示例

```c
/* 初始化 */
OLED_Init();
__HAL_RCC_GPIOG_CLK_ENABLE();

/* 显示文本 */
OLED_ShowString(0, 0, "DS18B20 Sensor");

/* 显示温度（自动清除残留） */
OLED_ShowTemp(0, 6, 261);  /* 显示 26.1C */

/* 读取温度 */
DS18B20_Start();
HAL_Delay(750);
int16_t temp = DS18B20_ReadTemp();  /* 返回温度×10 */
```

## 显示函数说明

| 函数 | 说明 |
|------|------|
| OLED_Init() | 初始化OLED |
| OLED_Clear() | 清屏 |
| OLED_ShowChar(x,y,ch) | 显示单个字符 |
| OLED_ShowString(x,y,str) | 显示字符串 |
| OLED_ShowNum(x,y,num,width) | 显示数字（自动清除残留） |
| OLED_ShowTemp(x,y,temp) | 显示温度（格式XX.XC，自动清除残留） |
| OLED_ClearLine(y) | 清除整行 |

## 版本历史

- v1.0.0: 初始版本，支持OLED显示和DS18B20温度读取
