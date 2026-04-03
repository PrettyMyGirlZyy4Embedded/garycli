#!/usr/bin/env python3
"""
oled_8080_elite — 正点原子STM32精英板 OLED 8080并口驱动

硬件连接 (精英板):
- 数据线 D[7:0] -> PC[7:0]
- CS   -> PD6
- DC   -> PD3 (RS/数据命令选择)
- WR   -> PG14
- RD   -> PG13
- RST  -> PG15
"""
from typing import Dict, Any, List, Optional


# ═══ 工具函数 ═══

def oled_8080_elite_get_driver_code() -> dict:
    """
    获取OLED 8080并口驱动完整代码
    
    返回可直接使用的OLED初始化、显示函数代码
    """
    code = '''/* OLED 8080并口驱动 - 正点原子精英板 */

/* 引脚定义 */
#define OLED_CS_PORT      GPIOD
#define OLED_CS_PIN       GPIO_PIN_6
#define OLED_DC_PORT      GPIOD
#define OLED_DC_PIN       GPIO_PIN_3
#define OLED_WR_PORT      GPIOG
#define OLED_WR_PIN       GPIO_PIN_14
#define OLED_RD_PORT      GPIOG
#define OLED_RD_PIN       GPIO_PIN_13
#define OLED_RST_PORT     GPIOG
#define OLED_RST_PIN      GPIO_PIN_15

/* GPIO操作宏 */
#define OLED_CS_H()   HAL_GPIO_WritePin(OLED_CS_PORT, OLED_CS_PIN, GPIO_PIN_SET)
#define OLED_CS_L()   HAL_GPIO_WritePin(OLED_CS_PORT, OLED_CS_PIN, GPIO_PIN_RESET)
#define OLED_DC_H()   HAL_GPIO_WritePin(OLED_DC_PORT, OLED_DC_PIN, GPIO_PIN_SET)
#define OLED_DC_L()   HAL_GPIO_WritePin(OLED_DC_PORT, OLED_DC_PIN, GPIO_PIN_RESET)
#define OLED_WR_H()   HAL_GPIO_WritePin(OLED_WR_PORT, OLED_WR_PIN, GPIO_PIN_SET)
#define OLED_WR_L()   HAL_GPIO_WritePin(OLED_WR_PORT, OLED_WR_PIN, GPIO_PIN_RESET)
#define OLED_RD_H()   HAL_GPIO_WritePin(OLED_RD_PORT, OLED_RD_PIN, GPIO_PIN_SET)
#define OLED_RD_L()   HAL_GPIO_WritePin(OLED_RD_PORT, OLED_RD_PIN, GPIO_PIN_RESET)
#define OLED_RST_H()  HAL_GPIO_WritePin(OLED_RST_PORT, OLED_RST_PIN, GPIO_PIN_SET)
#define OLED_RST_L()  HAL_GPIO_WritePin(OLED_RST_PORT, OLED_RST_PIN, GPIO_PIN_RESET)

/* 6x8 ASCII字模表 (32-126可打印字符, 95个字符) */
static const uint8_t ASCII_6x8[][6] = {
    {0x00,0x00,0x00,0x00,0x00,0x00},/* SP */
    {0x00,0x00,0x5F,0x00,0x00,0x00},/* ! */
    {0x00,0x00,0x07,0x00,0x07,0x00},/* " */
    {0x00,0x14,0x7F,0x14,0x7F,0x14},/* # */
    {0x00,0x24,0x2A,0x7F,0x2A,0x12},/* $ */
    {0x00,0x23,0x13,0x08,0x64,0x62},/* % */
    {0x00,0x36,0x49,0x55,0x22,0x50},/* & */
    {0x00,0x00,0x05,0x03,0x00,0x00},/* ' */
    {0x00,0x00,0x1C,0x22,0x41,0x00},/* ( */
    {0x00,0x00,0x41,0x22,0x1C,0x00},/* ) */
    {0x00,0x08,0x2A,0x1C,0x2A,0x08},/* * */
    {0x00,0x08,0x08,0x3E,0x08,0x08},/* + */
    {0x00,0x00,0x50,0x30,0x00,0x00},/* , */
    {0x00,0x08,0x08,0x08,0x08,0x08},/* - */
    {0x00,0x00,0x60,0x60,0x00,0x00},/* . */
    {0x00,0x20,0x10,0x08,0x04,0x02},/* / */
    {0x00,0x3E,0x51,0x49,0x45,0x3E},/* 0 */
    {0x00,0x00,0x42,0x7F,0x40,0x00},/* 1 */
    {0x00,0x42,0x61,0x51,0x49,0x46},/* 2 */
    {0x00,0x21,0x41,0x45,0x4B,0x31},/* 3 */
    {0x00,0x18,0x14,0x12,0x7F,0x10},/* 4 */
    {0x00,0x27,0x45,0x45,0x45,0x39},/* 5 */
    {0x00,0x3C,0x4A,0x49,0x49,0x30},/* 6 */
    {0x00,0x01,0x71,0x09,0x05,0x03},/* 7 */
    {0x00,0x36,0x49,0x49,0x49,0x36},/* 8 */
    {0x00,0x06,0x49,0x49,0x29,0x1E},/* 9 */
    {0x00,0x00,0x36,0x36,0x00,0x00},/* : */
    {0x00,0x00,0x56,0x36,0x00,0x00},/* ; */
    {0x00,0x00,0x08,0x14,0x22,0x41},/* < */
    {0x00,0x14,0x14,0x14,0x14,0x14},/* = */
    {0x00,0x41,0x22,0x14,0x08,0x00},/* > */
    {0x00,0x02,0x01,0x51,0x09,0x06},/* ? */
    {0x00,0x32,0x49,0x79,0x41,0x3E},/* @ */
    {0x00,0x7E,0x11,0x11,0x11,0x7E},/* A */
    {0x00,0x7F,0x49,0x49,0x49,0x36},/* B */
    {0x00,0x3E,0x41,0x41,0x41,0x22},/* C */
    {0x00,0x7F,0x41,0x41,0x22,0x1C},/* D */
    {0x00,0x7F,0x49,0x49,0x49,0x41},/* E */
    {0x00,0x7F,0x09,0x09,0x01,0x01},/* F */
    {0x00,0x3E,0x41,0x41,0x51,0x32},/* G */
    {0x00,0x7F,0x08,0x08,0x08,0x7F},/* H */
    {0x00,0x00,0x41,0x7F,0x41,0x00},/* I */
    {0x00,0x20,0x40,0x41,0x3F,0x01},/* J */
    {0x00,0x7F,0x08,0x14,0x22,0x41},/* K */
    {0x00,0x7F,0x40,0x40,0x40,0x40},/* L */
    {0x00,0x7F,0x02,0x04,0x02,0x7F},/* M */
    {0x00,0x7F,0x04,0x08,0x10,0x7F},/* N */
    {0x00,0x3E,0x41,0x41,0x41,0x3E},/* O */
    {0x00,0x7F,0x09,0x09,0x09,0x06},/* P */
    {0x00,0x3E,0x41,0x51,0x21,0x5E},/* Q */
    {0x00,0x7F,0x09,0x19,0x29,0x46},/* R */
    {0x00,0x46,0x49,0x49,0x49,0x31},/* S */
    {0x00,0x01,0x01,0x7F,0x01,0x01},/* T */
    {0x00,0x3F,0x40,0x40,0x40,0x3F},/* U */
    {0x00,0x1F,0x20,0x40,0x20,0x1F},/* V */
    {0x00,0x7F,0x20,0x18,0x20,0x7F},/* W */
    {0x00,0x63,0x14,0x08,0x14,0x63},/* X */
    {0x00,0x03,0x04,0x78,0x04,0x03},/* Y */
    {0x00,0x61,0x51,0x49,0x45,0x43},/* Z */
    {0x00,0x00,0x7F,0x41,0x41,0x00},/* [ */
    {0x00,0x02,0x04,0x08,0x10,0x20},/* \ */
    {0x00,0x00,0x41,0x41,0x7F,0x00},/* ] */
    {0x00,0x04,0x02,0x01,0x02,0x04},/* ^ */
    {0x00,0x40,0x40,0x40,0x40,0x40},/* _ */
    {0x00,0x00,0x01,0x02,0x04,0x00},/* ` */
    {0x00,0x20,0x54,0x54,0x54,0x78},/* a */
    {0x00,0x7F,0x48,0x44,0x44,0x38},/* b */
    {0x00,0x38,0x44,0x44,0x44,0x20},/* c */
    {0x00,0x38,0x44,0x44,0x48,0x7F},/* d */
    {0x00,0x38,0x54,0x54,0x54,0x18},/* e */
    {0x00,0x08,0x7E,0x09,0x01,0x02},/* f */
    {0x00,0x0C,0x52,0x52,0x52,0x3E},/* g */
    {0x00,0x7F,0x08,0x04,0x04,0x78},/* h */
    {0x00,0x00,0x44,0x7D,0x40,0x00},/* i */
    {0x00,0x20,0x40,0x44,0x3D,0x00},/* j */
    {0x00,0x7F,0x10,0x28,0x44,0x00},/* k */
    {0x00,0x00,0x41,0x7F,0x40,0x00},/* l */
    {0x00,0x7C,0x04,0x18,0x04,0x78},/* m */
    {0x00,0x7C,0x08,0x04,0x04,0x78},/* n */
    {0x00,0x38,0x44,0x44,0x44,0x38},/* o */
    {0x00,0x7C,0x14,0x14,0x14,0x08},/* p */
    {0x00,0x08,0x14,0x14,0x18,0x7C},/* q */
    {0x00,0x7C,0x08,0x04,0x04,0x08},/* r */
    {0x00,0x48,0x54,0x54,0x54,0x20},/* s */
    {0x00,0x04,0x3F,0x44,0x40,0x20},/* t */
    {0x00,0x3C,0x40,0x40,0x20,0x7C},/* u */
    {0x00,0x1C,0x20,0x40,0x20,0x1C},/* v */
    {0x00,0x3C,0x40,0x30,0x40,0x3C},/* w */
    {0x00,0x44,0x28,0x10,0x28,0x44},/* x */
    {0x00,0x0C,0x50,0x50,0x50,0x3C},/* y */
    {0x00,0x44,0x64,0x54,0x4C,0x44},/* z */
    {0x00,0x00,0x08,0x36,0x41,0x00},/* { */
    {0x00,0x00,0x00,0x7F,0x00,0x00},/* | */
    {0x00,0x00,0x41,0x36,0x08,0x00},/* } */
    {0x00,0x08,0x08,0x2A,0x1C,0x08} /* ~ */
};

/* 数据输出 */
void OLED_DataOut(uint8_t data) {
    GPIOC->ODR = (GPIOC->ODR & 0xFF00) | data;
}

/* 写字节 */
void OLED_WriteByte(uint8_t data, uint8_t cmd) {
    OLED_DataOut(data);
    if (cmd) OLED_DC_H(); else OLED_DC_L();
    OLED_CS_L();
    OLED_WR_L();
    OLED_WR_H();
    OLED_CS_H();
}

#define OLED_WriteCmd(cmd)  OLED_WriteByte(cmd, 0)
#define OLED_WriteData(dat) OLED_WriteByte(dat, 1)

/* 设置位置 */
void OLED_SetPos(uint8_t x, uint8_t y) {
    if (y > 7) y = 7;
    OLED_WriteCmd(0xB0 + y);
    OLED_WriteCmd(((x & 0xF0) >> 4) | 0x10);
    OLED_WriteCmd(x & 0x0F);
}

/* 清屏 */
void OLED_Clear(void) {
    for (uint8_t i = 0; i < 8; i++) {
        OLED_SetPos(0, i);
        for (uint8_t j = 0; j < 128; j++) OLED_WriteData(0x00);
    }
}

/* 全屏点亮 */
void OLED_FullOn(void) {
    for (uint8_t i = 0; i < 8; i++) {
        OLED_SetPos(0, i);
        for (uint8_t j = 0; j < 128; j++) OLED_WriteData(0xFF);
    }
}

/* 显示字符 6x8 */
void OLED_ShowChar(uint8_t x, uint8_t y, char chr) {
    if (chr < 32 || chr > 126) chr = 32;  /* 越界显示空格 */
    uint8_t c = chr - 32;  /* 字模从空格(32)开始 */
    OLED_SetPos(x, y);
    for (uint8_t i = 0; i < 6; i++) OLED_WriteData(ASCII_6x8[c][i]);
}

/* 显示字符串 */
void OLED_ShowString(uint8_t x, uint8_t y, const char* str) {
    OLED_SetPos(x, y);
    while (*str) {
        char chr = *str++;
        if (chr < 32 || chr > 126) chr = 32;
        uint8_t c = chr - 32;
        for (uint8_t i = 0; i < 6; i++) OLED_WriteData(ASCII_6x8[c][i]);
    }
}

/* 显示数字 (右对齐，len为显示位数) */
void OLED_ShowNum(uint8_t x, uint8_t y, uint16_t num, uint8_t len) {
    char buf[8];
    uint8_t i;
    for (i = 0; i < len; i++) buf[i] = ' ';
    buf[len] = '\0';
    
    if (num == 0 && len > 0) {
        buf[len - 1] = '0';
    } else {
        int idx = len - 1;
        while (num && idx >= 0) {
            buf[idx--] = '0' + (num % 10);
            num /= 10;
        }
    }
    OLED_ShowString(x, y, buf);
}

/* GPIO初始化 */
void OLED_GPIO_Init(void) {
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOG_CLK_ENABLE();
    
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    
    GPIO_InitStruct.Pin = GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3|
                          GPIO_PIN_4|GPIO_PIN_5|GPIO_PIN_6|GPIO_PIN_7;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);
    
    GPIO_InitStruct.Pin = GPIO_PIN_3 | GPIO_PIN_6;
    HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);
    
    GPIO_InitStruct.Pin = GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15;
    HAL_GPIO_Init(GPIOG, &GPIO_InitStruct);
    
    OLED_CS_H(); OLED_DC_H(); OLED_WR_H(); OLED_RD_H(); OLED_RST_H();
    GPIOC->ODR |= 0xFF;
}

/* OLED初始化 */
void OLED_Init(void) {
    OLED_GPIO_Init();
    OLED_RST_H(); HAL_Delay(1);
    OLED_RST_L(); HAL_Delay(100);
    OLED_RST_H(); HAL_Delay(100);
    
    OLED_WriteCmd(0xAE);
    OLED_WriteCmd(0xD5); OLED_WriteCmd(0x80);
    OLED_WriteCmd(0xA8); OLED_WriteCmd(0x3F);
    OLED_WriteCmd(0xD3); OLED_WriteCmd(0x00);
    OLED_WriteCmd(0x40);
    OLED_WriteCmd(0x8D); OLED_WriteCmd(0x14);
    OLED_WriteCmd(0x20); OLED_WriteCmd(0x02);
    OLED_WriteCmd(0xA1);
    OLED_WriteCmd(0xC8);
    OLED_WriteCmd(0xDA); OLED_WriteCmd(0x12);
    OLED_WriteCmd(0x81); OLED_WriteCmd(0xEF);
    OLED_WriteCmd(0xD9); OLED_WriteCmd(0xF1);
    OLED_WriteCmd(0xDB); OLED_WriteCmd(0x30);
    OLED_WriteCmd(0xA4);
    OLED_WriteCmd(0xA6);
    OLED_WriteCmd(0xAF);
    OLED_Clear();
}

/* 绘制点 */
void OLED_DrawPoint(uint8_t x, uint8_t y, uint8_t t) {
    if (x > 127 || y > 63) return;
    OLED_SetPos(x, y / 8);
    uint8_t tmp = 1 << (y % 8);
    OLED_WriteData(t ? tmp : 0x00);
}

/* 画线 */
void OLED_DrawLine(uint8_t x1, uint8_t y1, uint8_t x2, uint8_t y2) {
    int dx = x2 - x1, dy = y2 - y1;
    int steps = (abs(dx) > abs(dy)) ? abs(dx) : abs(dy);
    float xinc = dx / (float)steps;
    float yinc = dy / (float)steps;
    float x = x1, y = y1;
    for (int i = 0; i <= steps; i++) {
        OLED_DrawPoint((uint8_t)x, (uint8_t)y, 1);
        x += xinc; y += yinc;
    }
}

/* 画矩形 */
void OLED_DrawRect(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint8_t fill) {
    if (fill) {
        for (uint8_t i = y; i < y + h && i < 64; i++) {
            for (uint8_t j = x; j < x + w && j < 128; j++) {
                OLED_DrawPoint(j, i, 1);
            }
        }
    } else {
        OLED_DrawLine(x, y, x + w - 1, y);
        OLED_DrawLine(x, y + h - 1, x + w - 1, y + h - 1);
        OLED_DrawLine(x, y, x, y + h - 1);
        OLED_DrawLine(x + w - 1, y, x + w - 1, y + h - 1);
    }
}
'''
    return {"success": True, "code": code}


def oled_8080_elite_draw_bitmap(bitmap_name: str, width: int = 128, height: int = 64) -> dict:
    """
    生成位图绘制代码
    
    Args:
        bitmap_name: 位图名称或描述
        width: 位图宽度(像素)
        height: 位图高度(像素)
    """
    # 预定义一些常用图案
    bitmaps = {
        "heart": [
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x18,0x3C,0x7E,0x7E,0x3C,0x18,0x00,
            0x00,0x3C,0x7E,0xFF,0xFF,0x7E,0x3C,0x00,
            0x00,0x7E,0xFF,0xFF,0xFF,0xFF,0x7E,0x00,
            0x00,0x3C,0x7E,0xFF,0xFF,0x7E,0x3C,0x00,
            0x00,0x18,0x3C,0x7E,0x7E,0x3C,0x18,0x00
        ],
        "smile": [
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x66,0x00,0x00,0x66,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
            0x00,0x00,0x3C,0x42,0x42,0x3C,0x00,0x00,
            0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00
        ]
    }
    
    code = f'''/* 绘制位图: {bitmap_name} ({width}x{height}) */
'''
    
    if bitmap_name.lower() in bitmaps:
        data = bitmaps[bitmap_name.lower()]
        code += f'''static const uint8_t BMP_{bitmap_name.upper()}[] = {{
    {', '.join([f'0x{b:02X}' for b in data])}
}};

void OLED_Show{bitmap_name.capitalize()}(uint8_t x, uint8_t y) {{
    for (uint8_t page = 0; page < {height // 8}; page++) {{
        OLED_SetPos(x, y + page);
        for (uint8_t col = 0; col < {width}; col++) {{
            OLED_WriteData(BMP_{bitmap_name.upper()}[page * {width} + col]);
        }}
    }}
}}
'''
    else:
        code += f'''/* 自定义位图绘制函数模板 */
void OLED_DrawBitmap_{bitmap_name}(uint8_t x, uint8_t y, const uint8_t* data, uint8_t w, uint8_t h) {{
    uint8_t pages = (h + 7) / 8;
    for (uint8_t page = 0; page < pages; page++) {{
        OLED_SetPos(x, y + page);
        for (uint8_t col = 0; col < w; col++) {{
            OLED_WriteData(data[page * w + col]);
        }}
    }}
}}
'''
    
    return {"success": True, "code": code, "bitmap": bitmap_name}


def oled_8080_elite_get_full_main(demo: str = "string") -> dict:
    """
    获取完整可编译的 main.c 代码
    
    Args:
        demo: 演示类型 (string/geometry/bitmap/clear)
    """
    driver = oled_8080_elite_get_driver_code()["code"]
    
    demos = {
        "string": '''    OLED_ShowString(0, 0, "Hello World!");
    OLED_ShowString(0, 2, "STM32 OLED");
    OLED_ShowString(0, 4, "8080 Parallel");
    OLED_ShowString(0, 6, "Test OK!");''',
        
        "geometry": '''    OLED_DrawLine(0, 0, 127, 63);
    OLED_DrawLine(0, 63, 127, 0);
    OLED_DrawRect(10, 10, 50, 30, 0);
    OLED_DrawRect(70, 20, 40, 25, 1);
    OLED_ShowString(0, 7, "Geometry Demo");''',
        
        "bitmap": '''    /* 显示预定义图案 */
    OLED_ShowString(40, 0, "Heart:");
    /* 这里可以调用图案显示函数 */''',
        
        "clear": '''    OLED_Clear();
    OLED_ShowString(30, 3, "CLEARED!");'''
    }
    
    main_code = f'''#include "stm32f1xx_hal.h"
#include <string.h>

{driver}

UART_HandleTypeDef huart1;

void Debug_Print(const char* s) {{
    HAL_UART_Transmit(&huart1, (uint8_t*)s, strlen(s), 100);
}}

void SystemClock_Config(void) {{
    RCC_OscInitTypeDef RCC_OscInitStruct = {{0}};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {{0}};
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI_DIV2;
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL16;
    HAL_RCC_OscConfig(&RCC_OscInitStruct);
    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2);
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

void HAL_UART_MspInit(UART_HandleTypeDef* uartHandle) {{
    GPIO_InitTypeDef GPIO_InitStruct = {{0}};
    if (uartHandle->Instance == USART1) {{
        __HAL_RCC_USART1_CLK_ENABLE();
        __HAL_RCC_GPIOA_CLK_ENABLE();
        GPIO_InitStruct.Pin = GPIO_PIN_9;
        GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
        HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
        GPIO_InitStruct.Pin = GPIO_PIN_10;
        GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
        GPIO_InitStruct.Pull = GPIO_NOPULL;
        HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
    }}
}}

void SysTick_Handler(void) {{ HAL_IncTick(); }}

int main(void) {{
    HAL_Init();
    SystemClock_Config();
    MX_USART1_UART_Init();
    Debug_Print("Gary:BOOT\\r\\n");
    
    OLED_Init();
    Debug_Print("OLED Init OK\\r\\n");
    
{demos.get(demo, demos["string"])}
    Debug_Print("Display Done\\r\\n");
    
    while (1) {{
        HAL_Delay(500);
    }}
}}
'''
    return {"success": True, "code": main_code, "demo": demo}


# ═══ 工具注册表 ═══

TOOLS_MAP: Dict[str, Any] = {
    "oled_8080_elite_get_driver_code": oled_8080_elite_get_driver_code,
    "oled_8080_elite_draw_bitmap": oled_8080_elite_draw_bitmap,
    "oled_8080_elite_get_full_main": oled_8080_elite_get_full_main,
}
