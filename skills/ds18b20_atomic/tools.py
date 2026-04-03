#!/usr/bin/env python3
"""
ds18b20_atomic — 正点原子DS18B20温度传感器驱动
"""
from typing import Dict, Any, List


# ═══ DS18B20 驱动代码模板 ═══

def _get_driver_code(port: str = "GPIOG", pin: int = 11) -> str:
    """生成DS18B20驱动代码"""
    return f'''/* =============== DS18B20驱动 ({port} Pin{pin}) =============== */
#define DS18B20_PIN       GPIO_PIN_{pin}
#define DS18B20_PORT      {port}
#define DS18B20_HIGH()    HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_SET)
#define DS18B20_LOW()     HAL_GPIO_WritePin(DS18B20_PORT, DS18B20_PIN, GPIO_PIN_RESET)
#define DS18B20_READ()    HAL_GPIO_ReadPin(DS18B20_PORT, DS18B20_PIN)

static uint8_t DS18B20_Data[9];

static void DS18B20_DelayUs(uint32_t us) {{
    __IO uint32_t count = us * 8;
    while(count--);
}}

/* 主机发送复位脉冲，检测DS18B20应答 */
static uint8_t DS18B20_Reset(void) {{
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DS18B20_PIN;
    GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_LOW();
    DS18B20_DelayUs(480);  /* 拉低480us */
    DS18B20_HIGH();
    GPIO_Init.Mode = GPIO_MODE_INPUT;
    GPIO_Init.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_DelayUs(70);   /* 等待DS18B20拉低应答 */
    uint8_t presence = (DS18B20_READ() == GPIO_PIN_RESET) ? 0 : 1;
    DS18B20_DelayUs(410);  /* 等待应答结束 */
    return presence;       /* 0=检测到设备, 1=无设备 */
}}

/* 写一位 */
static void DS18B20_WriteBit(uint8_t bit) {{
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DS18B20_PIN;
    GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_LOW();
    if (bit) {{
        DS18B20_DelayUs(15);
        DS18B20_HIGH();
        DS18B20_DelayUs(45);
    }} else {{
        DS18B20_DelayUs(60);
        DS18B20_HIGH();
        DS18B20_DelayUs(5);
    }}
}}

/* 读一位 */
static uint8_t DS18B20_ReadBit(void) {{
    uint8_t bit;
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DS18B20_PIN;
    GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_LOW();
    DS18B20_DelayUs(5);
    DS18B20_HIGH();
    GPIO_Init.Mode = GPIO_MODE_INPUT;
    GPIO_Init.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(DS18B20_PORT, &GPIO_Init);
    DS18B20_DelayUs(10);
    bit = (DS18B20_READ() == GPIO_PIN_SET) ? 1 : 0;
    DS18B20_DelayUs(45);
    return bit;
}}

/* 写一字节 */
static void DS18B20_WriteByte(uint8_t data) {{
    for (uint8_t i = 0; i < 8; i++) {{
        DS18B20_WriteBit(data & 0x01);
        data >>= 1;
    }}
}}

/* 读一字节 */
static uint8_t DS18B20_ReadByte(void) {{
    uint8_t byte = 0;
    for (uint8_t i = 0; i < 8; i++) {{
        byte >>= 1;
        if (DS18B20_ReadBit()) byte |= 0x80;
    }}
    return byte;
}}

/* 启动温度转换 */
static void DS18B20_Start(void) {{
    DS18B20_Reset();
    DS18B20_WriteByte(0xCC);  /* 跳过ROM */
    DS18B20_WriteByte(0x44);  /* 启动转换 */
}}

/* 读取温度值，返回整数温度(放大10倍，如255表示25.5°C) */
int16_t DS18B20_ReadTemp(void) {{
    uint8_t temp_lsb, temp_msb;
    int16_t temp;
    
    DS18B20_Reset();
    DS18B20_WriteByte(0xCC);  /* 跳过ROM */
    DS18B20_WriteByte(0xBE);  /* 读暂存器 */
    
    for (uint8_t i = 0; i < 9; i++) {{
        DS18B20_Data[i] = DS18B20_ReadByte();
    }}
    
    temp_lsb = DS18B20_Data[0];
    temp_msb = DS18B20_Data[1];
    temp = (temp_msb << 8) | temp_lsb;
    /* 温度值是定点数，低4位是小数，转换为10倍整数 */
    temp = (temp * 10) / 16;
    return temp;
}}

/* 检测DS18B20是否存在 */
uint8_t DS18B20_Check(void) {{
    return DS18B20_Reset();  /* 0=存在, 1=不存在 */
}}'''


def _get_oled_driver_code() -> str:
    """获取OLED驱动代码"""
    return '''/* =============== OLED 8080并口驱动 =============== */
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

#define OLED_CS_H()   HAL_GPIO_WritePin(OLED_CS_PORT, OLED_CS_PIN, GPIO_PIN_SET)
#define OLED_CS_L()   HAL_GPIO_WritePin(OLED_CS_PORT, OLED_CS_PIN, GPIO_PIN_RESET)
#define OLED_DC_H()   HAL_GPIO_WritePin(OLED_DC_PORT, OLED_DC_PIN, GPIO_PIN_SET)
#define OLED_DC_L()   HAL_GPIO_WritePin(OLED_DC_PORT, OLED_DC_PIN, GPIO_PIN_RESET)
#define OLED_WR_H()   HAL_GPIO_WritePin(OLED_WR_PORT, OLED_WR_PIN, GPIO_PIN_SET)
#define OLED_WR_L()   HAL_GPIO_WritePin(OLED_WR_PORT, OLED_WR_PIN, GPIO_PIN_RESET)
#define OLED_RD_H()   HAL_GPIO_WritePin(OLED_RD_PORT, OLED_RD_PIN, GPIO_PIN_SET)
#define OLED_RST_H()  HAL_GPIO_WritePin(OLED_RST_PORT, OLED_RST_PIN, GPIO_PIN_SET)
#define OLED_RST_L()  HAL_GPIO_WritePin(OLED_RST_PORT, OLED_RST_PIN, GPIO_PIN_RESET)

#define OLED_DATA_PORT    GPIOC
#define OLED_DATA_MASK    0x00FF

static const uint8_t OLED_F6x8[][6] = {
    {0x00,0x00,0x00,0x00,0x00,0x00},{0x00,0x00,0x5F,0x00,0x00,0x00},{0x00,0x07,0x00,0x07,0x00,0x00},
    {0x14,0x7F,0x14,0x7F,0x14,0x00},{0x24,0x2A,0x7F,0x2A,0x12,0x00},{0x23,0x13,0x08,0x64,0x62,0x00},
    {0x36,0x49,0x56,0x20,0x50,0x00},{0x00,0x08,0x07,0x03,0x00,0x00},{0x00,0x1C,0x22,0x41,0x00,0x00},
    {0x00,0x41,0x22,0x1C,0x00,0x00},{0x2A,0x1C,0x7F,0x1C,0x2A,0x00},{0x08,0x08,0x3E,0x08,0x08,0x00},
    {0x00,0x80,0x70,0x30,0x00,0x00},{0x08,0x08,0x08,0x08,0x08,0x00},{0x00,0x00,0x60,0x60,0x00,0x00},
    {0x20,0x10,0x08,0x04,0x02,0x00},{0x3E,0x51,0x49,0x45,0x3E,0x00},{0x00,0x42,0x7F,0x40,0x00,0x00},
    {0x72,0x49,0x49,0x49,0x46,0x00},{0x21,0x41,0x49,0x4D,0x33,0x00},{0x18,0x14,0x12,0x7F,0x10,0x00},
    {0x27,0x45,0x45,0x45,0x39,0x00},{0x3C,0x4A,0x49,0x49,0x31,0x00},{0x41,0x21,0x11,0x09,0x07,0x00},
    {0x36,0x49,0x49,0x49,0x36,0x00},{0x46,0x49,0x49,0x29,0x1E,0x00},{0x00,0x00,0x14,0x00,0x00,0x00},
    {0x00,0x40,0x34,0x00,0x00,0x00},{0x00,0x08,0x14,0x22,0x41,0x00},{0x14,0x14,0x14,0x14,0x14,0x00},
    {0x00,0x41,0x22,0x14,0x08,0x00},{0x02,0x01,0x59,0x09,0x06,0x00},{0x3E,0x41,0x5D,0x59,0x4E,0x00},
    {0x7C,0x12,0x11,0x12,0x7C,0x00},{0x7F,0x49,0x49,0x49,0x36,0x00},{0x3E,0x41,0x41,0x41,0x22,0x00},
    {0x7F,0x41,0x41,0x41,0x3E,0x00},{0x7F,0x49,0x49,0x49,0x41,0x00},{0x7F,0x09,0x09,0x09,0x01,0x00},
    {0x3E,0x41,0x41,0x51,0x73,0x00},{0x7F,0x08,0x08,0x08,0x7F,0x00},{0x00,0x41,0x7F,0x41,0x00,0x00},
    {0x20,0x40,0x41,0x3F,0x01,0x00},{0x7F,0x08,0x14,0x22,0x41,0x00},{0x7F,0x40,0x40,0x40,0x40,0x00},
    {0x7F,0x02,0x1C,0x02,0x7F,0x00},{0x7F,0x04,0x08,0x10,0x7F,0x00},{0x3E,0x41,0x41,0x41,0x3E,0x00},
    {0x7F,0x09,0x09,0x09,0x06,0x00},{0x3E,0x41,0x51,0x21,0x5E,0x00},{0x7F,0x09,0x19,0x29,0x46,0x00},
    {0x26,0x49,0x49,0x49,0x32,0x00},{0x03,0x01,0x7F,0x01,0x03,0x00},{0x3F,0x40,0x40,0x40,0x3F,0x00},
    {0x1F,0x20,0x40,0x20,0x1F,0x00},{0x3F,0x40,0x38,0x40,0x3F,0x00},{0x63,0x14,0x08,0x14,0x63,0x00},
    {0x03,0x04,0x78,0x04,0x03,0x00},{0x61,0x59,0x49,0x4D,0x43,0x00},{0x00,0x7F,0x41,0x41,0x41,0x00},
    {0x02,0x04,0x08,0x10,0x20,0x00},{0x00,0x41,0x41,0x41,0x7F,0x00},{0x04,0x02,0x01,0x02,0x04,0x00},
    {0x40,0x40,0x40,0x40,0x40,0x00},{0x00,0x03,0x07,0x08,0x00,0x00},{0x20,0x54,0x54,0x78,0x40,0x00},
    {0x7F,0x28,0x44,0x44,0x38,0x00},{0x38,0x44,0x44,0x44,0x28,0x00},{0x38,0x44,0x44,0x28,0x7F,0x00},
    {0x38,0x54,0x54,0x54,0x18,0x00},{0x00,0x08,0x7E,0x09,0x02,0x00},{0x18,0xA4,0xA4,0x9C,0x78,0x00},
    {0x7F,0x08,0x04,0x04,0x78,0x00},{0x00,0x44,0x7D,0x40,0x00,0x00},{0x20,0x40,0x40,0x3D,0x00,0x00},
    {0x7F,0x10,0x28,0x44,0x00,0x00},{0x00,0x41,0x7F,0x40,0x00,0x00},{0x7C,0x04,0x78,0x04,0x78,0x00},
    {0x7C,0x08,0x04,0x04,0x78,0x00},{0x38,0x44,0x44,0x44,0x38,0x00},{0xFC,0x18,0x24,0x24,0x18,0x00},
    {0x18,0x24,0x24,0x18,0xFC,0x00},{0x7C,0x08,0x04,0x04,0x08,0x00},{0x48,0x54,0x54,0x54,0x24,0x00},
    {0x04,0x04,0x3F,0x44,0x24,0x00},{0x3C,0x40,0x40,0x20,0x7C,0x00},{0x1C,0x20,0x40,0x20,0x1C,0x00},
    {0x3C,0x40,0x30,0x40,0x3C,0x00},{0x44,0x28,0x10,0x28,0x44,0x00},{0x4C,0x90,0x90,0x90,0x7C,0x00},
    {0x44,0x64,0x54,0x4C,0x44,0x00},{0x00,0x08,0x36,0x41,0x00,0x00},{0x00,0x00,0x77,0x00,0x00,0x00},
    {0x00,0x41,0x36,0x08,0x00,0x00},{0x02,0x01,0x02,0x04,0x02,0x00}
};

static void OLED_WriteCmd(uint8_t cmd) {{
    OLED_DC_L(); OLED_CS_L();
    HAL_GPIO_WritePin(OLED_DATA_PORT, OLED_DATA_MASK, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_DATA_PORT, cmd, GPIO_PIN_SET);
    OLED_WR_L(); OLED_WR_H(); OLED_CS_H();
}}

static void OLED_WriteData(uint8_t data) {{
    OLED_DC_H(); OLED_CS_L();
    HAL_GPIO_WritePin(OLED_DATA_PORT, OLED_DATA_MASK, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_DATA_PORT, data, GPIO_PIN_SET);
    OLED_WR_L(); OLED_WR_H(); OLED_CS_H();
}}

void OLED_SetPos(uint8_t x, uint8_t y) {{
    OLED_WriteCmd(0xB0 + y);
    OLED_WriteCmd(((x & 0xF0) >> 4) | 0x10);
    OLED_WriteCmd((x & 0x0F));
}}

void OLED_Clear(void) {{
    for (uint8_t i = 0; i < 8; i++) {{
        OLED_SetPos(0, i);
        for (uint8_t j = 0; j < 128; j++) OLED_WriteData(0x00);
    }}
}}

void OLED_ShowChar(uint8_t x, uint8_t y, uint8_t chr) {{
    OLED_SetPos(x, y);
    for (uint8_t i = 0; i < 6; i++)
        OLED_WriteData(OLED_F6x8[chr - 32][i]);
}}

void OLED_ShowString(uint8_t x, uint8_t y, char *str) {{
    while (*str) {{ OLED_ShowChar(x, y, *str++); x += 6; }}
}}

void OLED_ShowNum(uint8_t x, uint8_t y, uint16_t num, uint8_t len) {{
    char buf[6]; int i = 0;
    if (num == 0 && len == 1) {{ OLED_ShowChar(x, y, '0'); return; }}
    while (num > 0) {{ buf[i++] = '0' + (num % 10); num /= 10; }}
    for (int j = 0; j < len - i; j++) OLED_ShowChar(x + j*6, y, '0');
    for (int j = 0; j < i; j++) OLED_ShowChar(x + (len-1-j)*6, y, buf[j]);
}}

void OLED_Init(void) {{
    __HAL_RCC_GPIOC_CLK_ENABLE(); __HAL_RCC_GPIOD_CLK_ENABLE(); __HAL_RCC_GPIOG_CLK_ENABLE();
    GPIO_InitTypeDef GPIO_Init = {{0}}; GPIO_Init.Pin = OLED_DATA_MASK; GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP; GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH; HAL_GPIO_Init(OLED_DATA_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_CS_PIN; HAL_GPIO_Init(OLED_CS_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_DC_PIN; HAL_GPIO_Init(OLED_DC_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_WR_PIN; HAL_GPIO_Init(OLED_WR_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_RD_PIN; HAL_GPIO_Init(OLED_RD_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_RST_PIN; HAL_GPIO_Init(OLED_RST_PORT, &GPIO_Init);
    OLED_RD_H(); OLED_RST_L(); HAL_Delay(100); OLED_RST_H();
    OLED_WriteCmd(0xAE); OLED_WriteCmd(0x20); OLED_WriteCmd(0x10);
    OLED_WriteCmd(0xB0); OLED_WriteCmd(0xC8); OLED_WriteCmd(0x00);
    OLED_WriteCmd(0x10); OLED_WriteCmd(0x40); OLED_WriteCmd(0x81);
    OLED_WriteCmd(0xFF); OLED_WriteCmd(0xA1); OLED_WriteCmd(0xA6);
    OLED_WriteCmd(0xA8); OLED_WriteCmd(0x3F); OLED_WriteCmd(0xA4);
    OLED_WriteCmd(0xD3); OLED_WriteCmd(0x00); OLED_WriteCmd(0xD5);
    OLED_WriteCmd(0xF0); OLED_WriteCmd(0xD9); OLED_WriteCmd(0x22);
    OLED_WriteCmd(0xDA); OLED_WriteCmd(0x12); OLED_WriteCmd(0xDB);
    OLED_WriteCmd(0x20); OLED_WriteCmd(0x8D); OLED_WriteCmd(0x14);
    OLED_WriteCmd(0xAF); OLED_Clear();
}}'''


def _get_full_main(port: str = "GPIOG", pin: int = 11, display: str = "oled") -> str:
    """生成完整main.c代码"""
    
    # 基础头文件和调试输出
    header = '''#include "stm32f1xx_hal.h"
#include <string.h>
#include <stdlib.h>

/* =============== 简易调试输出 =============== */
UART_HandleTypeDef huart1;
void Debug_Print(const char* s) {
    HAL_UART_Transmit(&huart1, (uint8_t*)s, strlen(s), 100);
}
void Debug_PrintInt(int val) {
    char buf[16]; int i = 0, neg = 0;
    if (val < 0) { neg = 1; val = -val; }
    if (val == 0) { buf[i++] = '0'; }
    else { while (val) { buf[i++] = '0' + val % 10; val /= 10; } }
    if (neg) buf[i++] = '-';
    for (int j = i-1; j >= 0; j--) HAL_UART_Transmit(&huart1, (uint8_t*)&buf[j], 1, 100);
}

/* =============== 系统时钟配置 =============== */
void SystemClock_Config(void) {
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
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
}

/* =============== UART1初始化 =============== */
void MX_USART1_UART_Init(void) {
    huart1.Instance = USART1;
    huart1.Init.BaudRate = 115200;
    huart1.Init.WordLength = UART_WORDLENGTH_8B;
    huart1.Init.StopBits = UART_STOPBITS_1;
    huart1.Init.Parity = UART_PARITY_NONE;
    huart1.Init.Mode = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart1.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart1);
}
void HAL_UART_MspInit(UART_HandleTypeDef* uartHandle) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    if (uartHandle->Instance == USART1) {
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
    }
}
void SysTick_Handler(void) { HAL_IncTick(); }
'''
    
    # DS18B20驱动代码
    ds18b20_code = _get_driver_code(port, pin)
    
    # 主函数 - OLED显示版本
    if display == "oled":
        oled_code = _get_oled_driver_code()
        main_code = '''
/* =============== 主函数 =============== */
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_USART1_UART_Init();
    Debug_Print("Gary:BOOT\\r\\n");
    
    /* 使能DS18B20 GPIO时钟 */
    __HAL_RCC_''' + port + '''_CLK_ENABLE();
    
    /* OLED初始化 */
    OLED_Init();
    OLED_ShowString(0, 0, "DS18B20 Temp");
    OLED_ShowString(0, 2, "Temp: --.- C");
    
    /* 检测DS18B20 */
    if (DS18B20_Check() != 0) {
        OLED_ShowString(0, 4, "Sensor Error!");
        Debug_Print("DS18B20 not found\\r\\n");
    } else {
        OLED_ShowString(0, 4, "Sensor OK    ");
        Debug_Print("DS18B20 init OK\\r\\n");
    }
    
    while (1) {
        DS18B20_Start();           /* 启动转换 */
        HAL_Delay(750);            /* 转换需要约750ms */
        
        int16_t temp = DS18B20_ReadTemp();  /* 读取温度 */
        
        if (temp != 850) {         /* 850是默认错误值 */
            /* 显示温度，保留1位小数 */
            uint8_t abs_temp = (temp < 0) ? -temp : temp;
            uint8_t integer = abs_temp / 10;
            uint8_t decimal = abs_temp % 10;
            
            OLED_ShowString(0, 2, "Temp:      C");
            OLED_ShowNum(36, 2, integer, 2);
            OLED_ShowChar(52, 2, \'.\');
            OLED_ShowNum(58, 2, decimal, 1);
            OLED_ShowString(90, 6, "OK ");
            
            Debug_Print("Temp:"); 
            if (temp < 0) Debug_Print("-");
            Debug_PrintInt(integer); Debug_Print("."); Debug_PrintInt(decimal); Debug_Print("C\\r\\n");
        } else {
            OLED_ShowString(90, 6, "Err");
            Debug_Print("DS18B20 Read Error\\r\\n");
        }
        HAL_Delay(1000);
    }
}'''
        return header + oled_code + '\n' + ds18b20_code + '\n' + main_code
    
    # UART显示版本
    else:
        main_code = '''
/* =============== 主函数 =============== */
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_USART1_UART_Init();
    Debug_Print("Gary:BOOT\\r\\n");
    
    /* 使能DS18B20 GPIO时钟 */
    __HAL_RCC_''' + port + '''_CLK_ENABLE();
    
    /* 检测DS18B20 */
    if (DS18B20_Check() != 0) {
        Debug_Print("DS18B20 not found\\r\\n");
    } else {
        Debug_Print("DS18B20 init OK\\r\\n");
    }
    
    while (1) {
        DS18B20_Start();           /* 启动转换 */
        HAL_Delay(750);            /* 转换需要约750ms */
        
        int16_t temp = DS18B20_ReadTemp();  /* 读取温度 */
        
        if (temp != 850) {         /* 850是默认错误值 */
            uint8_t abs_temp = (temp < 0) ? -temp : temp;
            uint8_t integer = abs_temp / 10;
            uint8_t decimal = abs_temp % 10;
            
            Debug_Print("Temp:"); 
            if (temp < 0) Debug_Print("-");
            Debug_PrintInt(integer); Debug_Print("."); Debug_PrintInt(decimal); Debug_Print("C\\r\\n");
        } else {
            Debug_Print("DS18B20 Read Error\\r\\n");
        }
        HAL_Delay(1000);
    }
}'''
        return header + ds18b20_code + '\n' + main_code


# ═══ 工具函数 ═══

def ds18b20_atomic_get_driver_code(port: str = "GPIOG", pin: int = 11) -> dict:
    """获取DS18B20驱动代码核心片段
    
    参数：
        port: GPIO端口（默认GPIOG）
        pin: 引脚号（默认11）
    
    返回：
        包含驱动代码的字典
    """
    code = _get_driver_code(port, pin)
    return {
        "success": True,
        "code": code,
        "port": port,
        "pin": pin
    }


def ds18b20_atomic_get_full_main(port: str = "GPIOG", pin: int = 11, display: str = "oled") -> dict:
    """获取完整可编译的main.c（含DS18B20 + 显示）
    
    参数：
        port: GPIO端口
        pin: 引脚号
        display: 显示方式 (oled/uart/none)
    
    返回：
        包含完整main.c的字典
    """
    code = _get_full_main(port, pin, display)
    return {
        "success": True,
        "code": code,
        "port": port,
        "pin": pin,
        "display": display
    }


# ═══ 工具注册表（必须导出）═══

TOOLS_MAP: Dict[str, Any] = {
    "ds18b20_atomic_get_driver_code": ds18b20_atomic_get_driver_code,
    "ds18b20_atomic_get_full_main": ds18b20_atomic_get_full_main,
}
