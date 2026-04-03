#!/usr/bin/env python3
"""
oled_8080_discovery - 正点原子STM32探索版OLED 8080并口驱动

特性：
- 支持STM32F407ZG探索版OLED 8080并口显示
- 支持DS18B20温度传感器读取和显示
- 支持字符串、数字、温度格式化显示
- 自动清除残留字符

硬件连接（STM32F407ZG探索版）：
- OLED_CS  -> PB7
- OLED_WR  -> PA4
- OLED_RST -> PG15
- OLED_DC  -> PD6
- OLED_RD  -> PD7
- OLED_D0-D3 -> PC6-PC9
- OLED_D4  -> PC11
- OLED_D5  -> PB6
- OLED_D6  -> PE5
- OLED_D7  -> PE6

- DS18B20  -> PG9 (U19接口，与摄像头OV_PWDN复用)
"""
from typing import Dict, Any


def oled_8080_discovery_get_driver_code() -> dict:
    """
    获取正点原子探索版OLED 8080驱动代码核心片段
    
    Returns:
        code: OLED驱动C代码（初始化、显示函数等）
    """
    code = '''/* ==================== OLED 8080 驱动 - 探索版 ==================== */
/* OLED 8080并口引脚定义 - STM32F407ZG探索版 */
#define OLED_CS_PORT        GPIOB
#define OLED_CS_PIN         GPIO_PIN_7
#define OLED_WR_PORT        GPIOA
#define OLED_WR_PIN         GPIO_PIN_4
#define OLED_RST_PORT       GPIOG
#define OLED_RST_PIN        GPIO_PIN_15
#define OLED_DC_PORT        GPIOD
#define OLED_DC_PIN         GPIO_PIN_6
#define OLED_RD_PORT        GPIOD
#define OLED_RD_PIN         GPIO_PIN_7
#define OLED_D0_PORT        GPIOC
#define OLED_D0_PIN         GPIO_PIN_6
#define OLED_D1_PORT        GPIOC
#define OLED_D1_PIN         GPIO_PIN_7
#define OLED_D2_PORT        GPIOC
#define OLED_D2_PIN         GPIO_PIN_8
#define OLED_D3_PORT        GPIOC
#define OLED_D3_PIN         GPIO_PIN_9
#define OLED_D4_PORT        GPIOC
#define OLED_D4_PIN         GPIO_PIN_11
#define OLED_D5_PORT        GPIOB
#define OLED_D5_PIN         GPIO_PIN_6
#define OLED_D6_PORT        GPIOE
#define OLED_D6_PIN         GPIO_PIN_5
#define OLED_D7_PORT        GPIOE
#define OLED_D7_PIN         GPIO_PIN_6

#define OLED_CS_H()     HAL_GPIO_WritePin(OLED_CS_PORT, OLED_CS_PIN, GPIO_PIN_SET)
#define OLED_CS_L()     HAL_GPIO_WritePin(OLED_CS_PORT, OLED_CS_PIN, GPIO_PIN_RESET)
#define OLED_WR_H()     HAL_GPIO_WritePin(OLED_WR_PORT, OLED_WR_PIN, GPIO_PIN_SET)
#define OLED_WR_L()     HAL_GPIO_WritePin(OLED_WR_PORT, OLED_WR_PIN, GPIO_PIN_RESET)
#define OLED_DC_H()     HAL_GPIO_WritePin(OLED_DC_PORT, OLED_DC_PIN, GPIO_PIN_SET)
#define OLED_DC_L()     HAL_GPIO_WritePin(OLED_DC_PORT, OLED_DC_PIN, GPIO_PIN_RESET)
#define OLED_RD_H()     HAL_GPIO_WritePin(OLED_RD_PORT, OLED_RD_PIN, GPIO_PIN_SET)
#define OLED_RD_L()     HAL_GPIO_WritePin(OLED_RD_PORT, OLED_RD_PIN, GPIO_PIN_RESET)
#define OLED_RST_H()    HAL_GPIO_WritePin(OLED_RST_PORT, OLED_RST_PIN, GPIO_PIN_SET)
#define OLED_RST_L()    HAL_GPIO_WritePin(OLED_RST_PORT, OLED_RST_PIN, GPIO_PIN_RESET)

#define OLED_CMD    0
#define OLED_DATA   1

/* OLED 6x8字模 */
static const uint8_t OLED_F6x8[][6] = {
    {0x00,0x00,0x00,0x00,0x00,0x00},{0x00,0x00,0x5F,0x00,0x00,0x00},{0x00,0x07,0x00,0x07,0x00,0x00},
    {0x14,0x7F,0x14,0x7F,0x14,0x00},{0x24,0x2A,0x7F,0x2A,0x12,0x00},{0x23,0x13,0x08,0x64,0x62,0x00},
    {0x36,0x49,0x55,0x22,0x50,0x00},{0x00,0x05,0x03,0x00,0x00,0x00},{0x00,0x1C,0x22,0x41,0x00,0x00},
    {0x00,0x41,0x22,0x1C,0x00,0x00},{0x08,0x2A,0x1C,0x2A,0x08,0x00},{0x08,0x08,0x3E,0x08,0x08,0x00},
    {0x00,0x50,0x30,0x00,0x00,0x00},{0x08,0x08,0x08,0x08,0x08,0x00},{0x00,0x60,0x60,0x00,0x00,0x00},
    {0x20,0x10,0x08,0x04,0x02,0x00},{0x3E,0x51,0x49,0x45,0x3E,0x00},{0x00,0x42,0x7F,0x40,0x00,0x00},
    {0x42,0x61,0x51,0x49,0x46,0x00},{0x21,0x41,0x45,0x4B,0x31,0x00},{0x18,0x14,0x12,0x7F,0x10,0x00},
    {0x27,0x45,0x45,0x45,0x39,0x00},{0x3C,0x4A,0x49,0x49,0x30,0x00},{0x01,0x71,0x09,0x05,0x03,0x00},
    {0x36,0x49,0x49,0x49,0x36,0x00},{0x06,0x49,0x49,0x29,0x1E,0x00},{0x00,0x36,0x36,0x00,0x00,0x00},
    {0x00,0x56,0x36,0x00,0x00,0x00},{0x00,0x08,0x14,0x22,0x41,0x00},{0x14,0x14,0x14,0x14,0x14,0x00},
    {0x41,0x22,0x14,0x08,0x00,0x00},{0x02,0x01,0x51,0x09,0x06,0x00},{0x32,0x49,0x79,0x41,0x3E,0x00},
    {0x7E,0x11,0x11,0x11,0x7E,0x00},{0x7F,0x49,0x49,0x49,0x36,0x00},{0x3E,0x41,0x41,0x41,0x22,0x00},
    {0x7F,0x41,0x41,0x22,0x1C,0x00},{0x7F,0x49,0x49,0x49,0x41,0x00},{0x7F,0x09,0x09,0x01,0x01,0x00},
    {0x3E,0x41,0x41,0x51,0x32,0x00},{0x7F,0x08,0x08,0x08,0x7F,0x00},{0x00,0x41,0x7F,0x41,0x00,0x00},
    {0x20,0x40,0x41,0x3F,0x01,0x00},{0x7F,0x08,0x14,0x22,0x41,0x00},{0x7F,0x40,0x40,0x40,0x40,0x00},
    {0x7F,0x02,0x04,0x02,0x7F,0x00},{0x7F,0x04,0x08,0x10,0x7F,0x00},{0x3E,0x41,0x41,0x41,0x3E,0x00},
    {0x7F,0x09,0x09,0x09,0x06,0x00},{0x3E,0x41,0x51,0x21,0x5E,0x00},{0x7F,0x09,0x19,0x29,0x46,0x00},
    {0x46,0x49,0x49,0x49,0x31,0x00},{0x01,0x01,0x7F,0x01,0x01,0x00},{0x3F,0x40,0x40,0x40,0x3F,0x00},
    {0x1F,0x20,0x40,0x20,0x1F,0x00},{0x7F,0x20,0x18,0x20,0x7F,0x00},{0x63,0x14,0x08,0x14,0x63,0x00},
    {0x03,0x04,0x78,0x04,0x03,0x00},{0x61,0x51,0x49,0x45,0x43,0x00},{0x00,0x00,0x7F,0x41,0x41,0x00},
    {0x02,0x04,0x08,0x10,0x20,0x00},{0x41,0x41,0x7F,0x00,0x00,0x00},{0x04,0x02,0x01,0x02,0x04,0x00},
    {0x40,0x40,0x40,0x40,0x40,0x00},{0x00,0x01,0x02,0x04,0x00,0x00},{0x20,0x54,0x54,0x54,0x78,0x00},
    {0x7F,0x48,0x44,0x44,0x38,0x00},{0x38,0x44,0x44,0x44,0x20,0x00},{0x38,0x44,0x44,0x48,0x7F,0x00},
    {0x38,0x54,0x54,0x54,0x18,0x00},{0x08,0x7E,0x09,0x01,0x02,0x00},{0x08,0x14,0x54,0x54,0x3C,0x00},
    {0x7F,0x08,0x04,0x04,0x78,0x00},{0x00,0x44,0x7D,0x40,0x00,0x00},{0x20,0x40,0x44,0x3D,0x00,0x00},
    {0x00,0x7F,0x10,0x28,0x44,0x00},{0x00,0x41,0x7F,0x40,0x00,0x00},{0x7C,0x04,0x18,0x04,0x78,0x00},
    {0x7C,0x08,0x04,0x04,0x78,0x00},{0x38,0x44,0x44,0x44,0x38,0x00},{0x7C,0x14,0x14,0x14,0x08,0x00},
    {0x08,0x14,0x14,0x18,0x7C,0x00},{0x7C,0x08,0x04,0x04,0x08,0x00},{0x48,0x54,0x54,0x54,0x20,0x00},
    {0x04,0x3F,0x44,0x40,0x20,0x00},{0x3C,0x40,0x40,0x20,0x7C,0x00},{0x1C,0x20,0x40,0x20,0x1C,0x00},
    {0x3C,0x40,0x30,0x40,0x3C,0x00},{0x44,0x28,0x10,0x28,0x44,0x00},{0x0C,0x50,0x50,0x50,0x3C,0x00},
    {0x44,0x64,0x54,0x4C,0x44,0x00},{0x00,0x08,0x36,0x41,0x00,0x00},{0x00,0x00,0x7F,0x00,0x00,0x00},
    {0x00,0x41,0x36,0x08,0x00,0x00},{0x08,0x08,0x2A,0x1C,0x08,0x00}
};

/* 写命令 */
static void OLED_WriteCommand(uint8_t cmd) {
    OLED_DC_L(); OLED_CS_L();
    HAL_GPIO_WritePin(OLED_D0_PORT, OLED_D0_PIN, (cmd & 0x01) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D1_PORT, OLED_D1_PIN, (cmd & 0x02) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D2_PORT, OLED_D2_PIN, (cmd & 0x04) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D3_PORT, OLED_D3_PIN, (cmd & 0x08) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D4_PORT, OLED_D4_PIN, (cmd & 0x10) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D5_PORT, OLED_D5_PIN, (cmd & 0x20) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D6_PORT, OLED_D6_PIN, (cmd & 0x40) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D7_PORT, OLED_D7_PIN, (cmd & 0x80) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    OLED_WR_L(); OLED_WR_H(); OLED_CS_H();
}

/* 写数据 */
static void OLED_WriteData(uint8_t data) {
    OLED_DC_H(); OLED_CS_L();
    HAL_GPIO_WritePin(OLED_D0_PORT, OLED_D0_PIN, (data & 0x01) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D1_PORT, OLED_D1_PIN, (data & 0x02) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D2_PORT, OLED_D2_PIN, (data & 0x04) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D3_PORT, OLED_D3_PIN, (data & 0x08) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D4_PORT, OLED_D4_PIN, (data & 0x10) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D5_PORT, OLED_D5_PIN, (data & 0x20) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D6_PORT, OLED_D6_PIN, (data & 0x40) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D7_PORT, OLED_D7_PIN, (data & 0x80) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    OLED_WR_L(); OLED_WR_H(); OLED_CS_H();
}

/* 设置显示位置 */
static void OLED_SetPos(uint8_t x, uint8_t y) {
    OLED_WriteCommand(0xB0 + y);
    OLED_WriteCommand(((x & 0xF0) >> 4) | 0x10);
    OLED_WriteCommand((x & 0x0F) | 0x01);
}

/* 清屏 */
static void OLED_Clear(void) {
    for (uint8_t y = 0; y < 8; y++) {
        OLED_SetPos(0, y);
        for (uint8_t x = 0; x < 128; x++) OLED_WriteData(0x00);
    }
}

/* OLED初始化 */
static void OLED_Init(void) {
    __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE(); __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE(); __HAL_RCC_GPIOG_CLK_ENABLE();
    
    GPIO_InitTypeDef GPIO_Init = {0};
    GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP; GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_Init.Pin = OLED_CS_PIN; HAL_GPIO_Init(OLED_CS_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_WR_PIN; HAL_GPIO_Init(OLED_WR_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_DC_PIN; HAL_GPIO_Init(OLED_DC_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_RD_PIN; HAL_GPIO_Init(OLED_RD_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_RST_PIN; HAL_GPIO_Init(OLED_RST_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_D0_PIN; HAL_GPIO_Init(OLED_D0_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_D1_PIN; HAL_GPIO_Init(OLED_D1_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_D2_PIN; HAL_GPIO_Init(OLED_D2_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_D3_PIN; HAL_GPIO_Init(OLED_D3_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_D4_PIN; HAL_GPIO_Init(OLED_D4_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_D5_PIN; HAL_GPIO_Init(OLED_D5_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_D6_PIN; HAL_GPIO_Init(OLED_D6_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_D7_PIN; HAL_GPIO_Init(OLED_D7_PORT, &GPIO_Init);
    
    OLED_RD_H(); OLED_CS_H(); OLED_WR_H(); OLED_RST_L(); HAL_Delay(100); OLED_RST_H(); HAL_Delay(100);
    OLED_WriteCommand(0xAE); OLED_WriteCommand(0xD5); OLED_WriteCommand(0x80);
    OLED_WriteCommand(0xA8); OLED_WriteCommand(0x3F); OLED_WriteCommand(0xD3);
    OLED_WriteCommand(0x00); OLED_WriteCommand(0x40); OLED_WriteCommand(0x8D);
    OLED_WriteCommand(0x14); OLED_WriteCommand(0x20); OLED_WriteCommand(0x00);
    OLED_WriteCommand(0xA1); OLED_WriteCommand(0xC8); OLED_WriteCommand(0xDA);
    OLED_WriteCommand(0x12); OLED_WriteCommand(0x81); OLED_WriteCommand(0xCF);
    OLED_WriteCommand(0xD9); OLED_WriteCommand(0xF1); OLED_WriteCommand(0xDB);
    OLED_WriteCommand(0x40); OLED_WriteCommand(0xA4); OLED_WriteCommand(0xA6);
    OLED_WriteCommand(0xAF);
    OLED_Clear();
}

/* 显示6x8字符 */
static void OLED_ShowChar(uint8_t x, uint8_t y, uint8_t chr) {
    if (x > 122 || y > 7 || chr < 32 || chr > 126) return;
    uint8_t c = chr - 32;
    OLED_SetPos(x, y);
    for (uint8_t i = 0; i < 6; i++) OLED_WriteData(OLED_F6x8[c][i]);
}

/* 显示字符串 */
static void OLED_ShowString(uint8_t x, uint8_t y, const char* str) {
    while (*str) { OLED_ShowChar(x, y, *str++); x += 6; if (x > 122) { x = 0; y++; } }
}

/* 清除一行 */
static void OLED_ClearLine(uint8_t y) {
    OLED_SetPos(0, y);
    for (uint8_t x = 0; x < 128; x++) OLED_WriteData(0x00);
}

/* 显示数字（固定宽度，清除残留） */
static void OLED_ShowNum(uint8_t x, uint8_t y, int16_t num, uint8_t width) {
    char buf[8]; 
    int i = 0;
    uint8_t start_x = x;
    
    /* 先清除显示区域 */
    for (uint8_t j = 0; j < width; j++) {
        OLED_SetPos(start_x + j * 6, y);
        for (uint8_t k = 0; k < 6; k++) OLED_WriteData(0x00);
    }
    
    if (num < 0) { OLED_ShowChar(x, y, '-'); x += 6; num = -num; }
    if (num == 0) { OLED_ShowChar(x, y, '0'); return; }
    while (num) { buf[i++] = '0' + num % 10; num /= 10; }
    while (i--) { OLED_ShowChar(x, y, buf[i]); x += 6; }
}

/* 显示温度（格式：XX.XC，固定宽度清除残留） */
static void OLED_ShowTemp(uint8_t x, uint8_t y, int16_t temp) {
    uint8_t abs_temp = (temp < 0) ? -temp : temp;
    uint8_t integer = abs_temp / 10;
    uint8_t decimal = abs_temp % 10;
    uint8_t pos = x;
    
    /* 清除温度显示区域（最多8个字符宽度） */
    for (uint8_t j = 0; j < 8; j++) {
        OLED_SetPos(x + j * 6, y);
        for (uint8_t k = 0; k < 6; k++) OLED_WriteData(0x00);
    }
    
    if (temp < 0) { OLED_ShowChar(pos, y, '-'); pos += 6; }
    OLED_ShowNum(pos, y, integer, 3); 
    /* 计算数字实际宽度 */
    uint8_t int_width = (integer >= 100) ? 3 : (integer >= 10) ? 2 : 1;
    pos += int_width * 6;
    OLED_ShowChar(pos, y, '.'); pos += 6;
    OLED_ShowChar(pos, y, '0' + decimal); pos += 6;
    OLED_ShowChar(pos, y, 'C');
}'''
    return {"success": True, "code": code}


def oled_8080_discovery_get_ds18b20_code(port: str = "GPIOG", pin: int = 9) -> dict:
    """
    获取DS18B20驱动代码
    
    Args:
        port: GPIO端口（默认GPIOG）
        pin: 引脚号（默认9，对应探索版U19接口）
    
    Returns:
        code: DS18B20驱动C代码
    """
    code = f'''/* ==================== DS18B20 驱动 ({port} Pin{pin}) ==================== */
#define DS18B20_PIN       GPIO_PIN_{pin}
#define DS18B20_PORT      {port}
#define DS18B20_HIGH()    HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_SET)
#define DS18B20_LOW()     HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_RESET)
#define DS18B20_READ()    HAL_GPIO_ReadPin(DS18B20_PORT, DS18B20_PIN)

static uint8_t DS18B20_Data[9];

static void DS18B20_DelayUs(uint32_t us) {{
    __IO uint32_t count = us * 21;
    while(count--);
}}

static uint8_t DS18B20_Reset(void) {{
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DS18B20_PIN; GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP; GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_LOW(); DS18B20_DelayUs(480); DS18B20_HIGH();
    GPIO_Init.Mode = GPIO_MODE_INPUT; GPIO_Init.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_DelayUs(70);
    uint8_t presence = (DS18B20_READ() == GPIO_PIN_RESET) ? 0 : 1;
    DS18B20_DelayUs(410); return presence;
}}

static void DS18B20_WriteBit(uint8_t bit) {{
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DS18B20_PIN; GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP; GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_LOW();
    if (bit) {{ DS18B20_DelayUs(15); DS18B20_HIGH(); DS18B20_DelayUs(45); }}
    else {{ DS18B20_DelayUs(60); DS18B20_HIGH(); DS18B20_DelayUs(5); }}
}}

static uint8_t DS18B20_ReadBit(void) {{
    uint8_t bit;
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DS18B20_PIN; GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP; GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_LOW(); DS18B20_DelayUs(5); DS18B20_HIGH();
    GPIO_Init.Mode = GPIO_MODE_INPUT; GPIO_Init.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_DelayUs(10);
    bit = (DS18B20_READ() == GPIO_PIN_SET) ? 1 : 0;
    DS18B20_DelayUs(45); return bit;
}}

static void DS18B20_WriteByte(uint8_t data) {{
    for (uint8_t i = 0; i < 8; i++) {{ DS18B20_WriteBit(data & 0x01); data >>= 1; }}
}}

static uint8_t DS18B20_ReadByte(void) {{
    uint8_t byte = 0;
    for (uint8_t i = 0; i < 8; i++) {{ byte >>= 1; if (DS18B20_ReadBit()) byte |= 0x80; }}
    return byte;
}}

static void DS18B20_Start(void) {{ DS18B20_Reset(); DS18B20_WriteByte(0xCC); DS18B20_WriteByte(0x44); }}

static int16_t DS18B20_ReadTemp(void) {{
    uint8_t temp_lsb, temp_msb; int16_t temp;
    DS18B20_Reset(); DS18B20_WriteByte(0xCC); DS18B20_WriteByte(0xBE);
    for (uint8_t i = 0; i < 9; i++) DS18B20_Data[i] = DS18B20_ReadByte();
    temp_lsb = DS18B20_Data[0]; temp_msb = DS18B20_Data[1];
    temp = (temp_msb << 8) | temp_lsb;
    temp = (temp * 10) / 16; return temp;
}}

static uint8_t DS18B20_Check(void) {{ return DS18B20_Reset(); }}'''
    return {"success": True, "code": code, "port": port, "pin": pin}


def oled_8080_discovery_get_full_main(display: str = "oled") -> dict:
    """
    获取完整可编译的main.c（DS18B20 + OLED显示）
    
    Args:
        display: 显示方式 (oled/uart/none)
    
    Returns:
        code: 完整main.c代码
    """
    oled_code = oled_8080_discovery_get_driver_code()["code"]
    ds18b20_code = oled_8080_discovery_get_ds18b20_code()["code"]
    
    demo_code = '''    OLED_ShowString(0, 0, "DS18B20 Sensor");
    OLED_ShowString(0, 2, "Status:");
    
    if (DS18B20_Check() != 0) {
        OLED_ShowString(48, 2, "Not Found");
    } else {
        OLED_ShowString(48, 2, "OK       ");
    }
    OLED_ShowString(0, 4, "Temperature:");
    
    while (1) {
        DS18B20_Start(); HAL_Delay(750);
        int16_t temp = DS18B20_ReadTemp();
        if (temp != 850) {
            OLED_ShowTemp(0, 6, temp);
        } else {
            OLED_ShowString(0, 6, "Read Error");
        }
        HAL_Delay(2000);
    }'''
    
    main_code = f'''#include "stm32f4xx_hal.h"
#include <string.h>

UART_HandleTypeDef huart1;
void Debug_Print(const char* s) {{
    HAL_UART_Transmit(&huart1, (uint8_t*)s, strlen(s), 100);
}}

void SystemClock_Config(void) {{
    RCC_OscInitTypeDef osc = {{0}};
    RCC_ClkInitTypeDef clk = {{0}};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    osc.HSIState = RCC_HSI_ON;
    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSI;
    osc.PLL.PLLM = 16;
    osc.PLL.PLLN = 336;
    osc.PLL.PLLP = RCC_PLLP_DIV2;
    osc.PLL.PLLQ = 7;
    HAL_RCC_OscConfig(&osc);
    clk.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV4;
    clk.APB2CLKDivider = RCC_HCLK_DIV2;
    HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_5);
}}

void MX_USART1_UART_Init(void) {{
    huart1.Instance = USART1;
    huart1.Init.BaudRate = 115200;
    huart1.Init.WordLength = UART_WORDLENGTH_8B;
    huart1.Init.StopBits = UART_STOPBITS_1;
    huart1.Init.Parity = UART_PARITY_NONE;
    huart1.Init.Mode = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart1.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart1);
}}

void HAL_UART_MspInit(UART_HandleTypeDef* huart) {{
    GPIO_InitTypeDef GPIO_InitStruct = {{0}};
    if(huart->Instance == USART1) {{
        __HAL_RCC_USART1_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();
        GPIO_InitStruct.Pin = GPIO_PIN_9;
        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
        GPIO_InitStruct.Pull = GPIO_NOPULL;
        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
        GPIO_InitStruct.Alternate = GPIO_AF7_USART1;
        HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
        GPIO_InitStruct.Pin = GPIO_PIN_10;
        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
        HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
    }}
}}

void SysTick_Handler(void) {{ HAL_IncTick(); }}

/* OLED驱动 */
{oled_code}

/* DS18B20驱动 */
{ds18b20_code}

int main(void) {{
    HAL_Init();
    SystemClock_Config();
    MX_USART1_UART_Init();
    Debug_Print("Gary:BOOT\\r\\n");
    
    OLED_Init();
    Debug_Print("OLED OK\\r\\n");
    __HAL_RCC_GPIOG_CLK_ENABLE();
    
{demo_code}
}}
'''
    return {"success": True, "code": main_code, "display": display}


# 工具注册表
TOOLS_MAP = {
    "oled_8080_discovery_get_driver_code": oled_8080_discovery_get_driver_code,
    "oled_8080_discovery_get_ds18b20_code": oled_8080_discovery_get_ds18b20_code,
    "oled_8080_discovery_get_full_main": oled_8080_discovery_get_full_main,
}
