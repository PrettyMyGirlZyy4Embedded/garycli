#!/usr/bin/env python3
"""
dht11_discovery — 正点原子探索版DHT11温湿度传感器驱动
硬件: STM32F407ZG 探索版
默认引脚: PG9
"""
from typing import Dict, Any, List


def dht11_discovery_get_driver_code(port: str = "GPIOG", pin: int = 9) -> dict:
    """
    获取DHT11驱动代码核心片段
    
    参数:
        port: GPIO端口，默认GPIOG
        pin: 引脚号，默认9
    
    返回:
        code: 可直接嵌入main.c的驱动代码
        port: 使用的GPIO端口
        pin: 使用的引脚号
    """
    code = f'''/* =============== DHT11驱动 ({port} Pin{pin}) =============== */
#define DHT11_PIN       GPIO_PIN_{pin}
#define DHT11_PORT      {port}
#define DHT11_HIGH()    HAL_GPIO_WritePin(DHT11_PORT, DHT11_PIN, GPIO_PIN_SET)
#define DHT11_LOW()     HAL_GPIO_WritePin(DHT11_PORT, DHT11_PIN, GPIO_PIN_RESET)
#define DHT11_READ()    HAL_GPIO_ReadPin(DHT11_PORT, DHT11_PIN)

static uint8_t DHT11_Data[5];

static void DHT11_DelayUs(uint32_t us) {{
    __IO uint32_t count = us * 21;
    while(count--);
}}

/* DHT11启动信号，返回0=成功，1=失败 */
static uint8_t DHT11_Start(void) {{
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DHT11_PIN;
    GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DHT11_PORT, &GPIO_Init);
    DHT11_LOW();
    HAL_Delay(20);  /* 拉低至少18ms */
    DHT11_HIGH();
    DHT11_DelayUs(40);  /* 等待20-40us */
    GPIO_Init.Mode = GPIO_MODE_INPUT;
    GPIO_Init.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(DHT11_PORT, &GPIO_Init);
    DHT11_DelayUs(10);
    if (DHT11_READ() != GPIO_PIN_RESET) return 1;  /* 未拉低 */
    DHT11_DelayUs(80);
    if (DHT11_READ() != GPIO_PIN_SET) return 1;    /* 未拉高 */
    DHT11_DelayUs(80);
    return 0;
}}

/* 读取一位 */
static uint8_t DHT11_ReadBit(void) {{
    while (DHT11_READ() == GPIO_PIN_RESET);  /* 等待低电平结束 */
    DHT11_DelayUs(40);
    uint8_t bit = (DHT11_READ() == GPIO_PIN_SET) ? 1 : 0;
    while (DHT11_READ() == GPIO_PIN_SET);    /* 等待高电平结束 */
    return bit;
}}

/* 读取一字节 */
static uint8_t DHT11_ReadByte(void) {{
    uint8_t byte = 0;
    for (uint8_t i = 0; i < 8; i++) {{
        byte <<= 1;
        byte |= DHT11_ReadBit();
    }}
    return byte;
}}

/* 读取温湿度，返回0=成功，1=失败 */
static uint8_t DHT11_Read(void) {{
    __HAL_RCC_GPIOG_CLK_ENABLE();
    if (DHT11_Start() != 0) return 1;
    for (uint8_t i = 0; i < 5; i++) {{
        DHT11_Data[i] = DHT11_ReadByte();
    }}
    uint8_t sum = DHT11_Data[0] + DHT11_Data[1] + DHT11_Data[2] + DHT11_Data[3];
    if (sum != DHT11_Data[4]) return 1;  /* 校验失败 */
    return 0;
}}

static uint8_t DHT11_Get_Humi(void) {{ return DHT11_Data[0]; }}
static uint8_t DHT11_Get_Temp(void) {{ return DHT11_Data[2]; }}'''
    
    return {
        "success": True,
        "code": code,
        "port": port,
        "pin": pin
    }


def dht11_discovery_get_full_main(port: str = "GPIOG", pin: int = 9, display: str = "oled") -> dict:
    """
    获取完整可编译的main.c（含DHT11 + OLED/UART显示）
    
    参数:
        port: GPIO端口，默认GPIOG
        pin: 引脚号，默认9
        display: 显示方式 (oled/uart/none)
    
    返回:
        code: 完整的main.c代码
        display: 显示方式
    """
    
    driver = dht11_discovery_get_driver_code(port, pin)
    driver_code = driver["code"]
    
    # OLED显示相关代码
    oled_code = '''/* OLED驱动 - 探索版8080并口 */
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

static const uint8_t F6x8[][6] = {
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
    {0x38,0x54,0x54,0x54,0x18,0x00},{0x00,0x08,0x7E,0x09,0x02,0x00},{0x18,0x24,0x24,0x1C,0x78,0x00},
    {0x7F,0x08,0x04,0x04,0x78,0x00},{0x00,0x44,0x7D,0x40,0x00,0x00},{0x20,0x40,0x40,0x3D,0x00,0x00},
    {0x7F,0x10,0x28,0x44,0x00,0x00},{0x00,0x41,0x7F,0x40,0x00,0x00},{0x7C,0x04,0x18,0x04,0x78,0x00},
    {0x7C,0x08,0x04,0x04,0x78,0x00},{0x38,0x44,0x44,0x44,0x38,0x00},{0x7C,0x18,0x24,0x24,0x18,0x00},
    {0x18,0x24,0x24,0x18,0x7C,0x00},{0x7C,0x08,0x04,0x04,0x08,0x00},{0x48,0x54,0x54,0x54,0x24,0x00},
    {0x04,0x04,0x3F,0x44,0x24,0x00},{0x3C,0x40,0x40,0x20,0x7C,0x00},{0x1C,0x20,0x40,0x20,0x1C,0x00},
    {0x3C,0x40,0x30,0x40,0x3C,0x00},{0x44,0x28,0x10,0x28,0x44,0x00},{0x4C,0x90,0x90,0x90,0x7C,0x00},
    {0x44,0x64,0x54,0x4C,0x44,0x00},{0x00,0x08,0x36,0x41,0x00,0x00},{0x00,0x00,0x77,0x00,0x00,0x00},
    {0x00,0x41,0x36,0x08,0x00,0x00},{0x02,0x01,0x02,0x04,0x02,0x00}
};

static void OLED_Write_Byte(uint8_t dat, uint8_t cmd) {{
    if(cmd) OLED_DC_H(); else OLED_DC_L();
    OLED_CS_L();
    HAL_GPIO_WritePin(OLED_D0_PORT, OLED_D0_PIN, (dat & 0x01) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D1_PORT, OLED_D1_PIN, (dat & 0x02) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D2_PORT, OLED_D2_PIN, (dat & 0x04) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D3_PORT, OLED_D3_PIN, (dat & 0x08) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D4_PORT, OLED_D4_PIN, (dat & 0x10) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D5_PORT, OLED_D5_PIN, (dat & 0x20) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D6_PORT, OLED_D6_PIN, (dat & 0x40) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(OLED_D7_PORT, OLED_D7_PIN, (dat & 0x80) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    OLED_WR_L(); OLED_WR_H();
    OLED_CS_H();
}}

static void OLED_Set_Pos(uint8_t x, uint8_t y) {{
    OLED_Write_Byte(0xB0 + y, OLED_CMD);
    OLED_Write_Byte(((x & 0xF0) >> 4) | 0x10, OLED_CMD);
    OLED_Write_Byte((x & 0x0F), OLED_CMD);
}}

void OLED_Clear(void) {{
    for(uint8_t i = 0; i < 8; i++) {{
        OLED_Set_Pos(0, i);
        for(uint8_t n = 0; n < 128; n++) OLED_Write_Byte(0, OLED_DATA);
    }}
}}

void OLED_ShowChar(uint8_t x, uint8_t y, char chr) {{
    uint8_t c = chr - ' ';
    if(x > 122 || y > 7) return;
    OLED_Set_Pos(x, y);
    for(uint8_t i = 0; i < 6; i++) OLED_Write_Byte(F6x8[c][i], OLED_DATA);
}}

void OLED_ShowString(uint8_t x, uint8_t y, const char* str) {{
    while(*str) {{ OLED_ShowChar(x, y, *str++); x += 6; if(x > 122) break; }}
}}

void OLED_ShowNum(uint8_t x, uint8_t y, uint8_t num) {{
    if (num >= 100) {{ OLED_ShowChar(x, y, '0' + num / 100); x += 6; }}
    if (num >= 10) {{ OLED_ShowChar(x, y, '0' + (num / 10) % 10); x += 6; }}
    OLED_ShowChar(x, y, '0' + num % 10);
}}

void OLED_Init(void) {{
    __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE(); __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE(); __HAL_RCC_GPIOG_CLK_ENABLE();
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP; GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_Init.Pin = OLED_WR_PIN; HAL_GPIO_Init(OLED_WR_PORT, &GPIO_Init);
    GPIO_Init.Pin = OLED_CS_PIN; HAL_GPIO_Init(OLED_CS_PORT, &GPIO_Init);
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
    OLED_RD_H(); OLED_CS_H(); OLED_RST_L(); HAL_Delay(100); OLED_RST_H();
    uint8_t cmds[] = {{0xAE,0xD5,0x80,0xA8,0x3F,0xD3,0x00,0x40,0x8D,0x14,0x20,0x02,0xA1,0xC8,0xDA,0x12,0x81,0xCF,0xD9,0xF1,0xDB,0x40,0xA4,0xA6,0x8D,0x14,0xAF}};
    for(uint8_t i = 0; i < sizeof(cmds); i++) OLED_Write_Byte(cmds[i], OLED_CMD);
    OLED_Clear();
}}'''

    # UART初始化代码
    uart_code = '''UART_HandleTypeDef huart1;
void Debug_Print(const char* s) {
    HAL_UART_Transmit(&huart1, (uint8_t*)s, strlen(s), 100);
}

void SystemClock_Config(void) {
    RCC_OscInitTypeDef osc = {0};
    RCC_ClkInitTypeDef clk = {0};
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
}

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

void HAL_UART_MspInit(UART_HandleTypeDef* huart) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    if(huart->Instance == USART1) {
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
    }
}

void SysTick_Handler(void) { HAL_IncTick(); }

void Debug_PrintInt(const char* prefix, int val) {
    HAL_UART_Transmit(&huart1, (uint8_t*)prefix, strlen(prefix), 100);
    char buf[8]; int i = 0;
    if (val == 0) { buf[i++] = '0'; }
    else { while (val) { buf[i++] = '0' + val % 10; val /= 10; } }
    for (int j = i-1; j >= 0; j--) HAL_UART_Transmit(&huart1, (uint8_t*)&buf[j], 1, 100);
    HAL_UART_Transmit(&huart1, (uint8_t*)"\r\n", 2, 100);
}'''

    # 主函数 - OLED显示版本
    if display == "oled":
        main_code = f'''
{oled_code}

{driver_code}

int main(void) {{
    HAL_Init();
    SystemClock_Config();
    MX_USART1_UART_Init();
    Debug_Print("Gary:BOOT\r\n");
    OLED_Init();
    Debug_Print("OLED OK\r\n");
    __HAL_RCC_GPIOG_CLK_ENABLE();
    
    OLED_ShowString(0, 0, "DHT11 Sensor");
    OLED_ShowString(0, 2, "Temp:");
    OLED_ShowString(0, 4, "Humi:");
    
    HAL_Delay(1000);
    uint8_t dht_ok = (DHT11_Read() == 0);
    Debug_Print(dht_ok ? "DHT11 OK\r\n" : "DHT11 ERR\r\n");
    
    while(1) {{
        if (DHT11_Read() == 0) {{
            uint8_t temp = DHT11_Get_Temp();
            uint8_t humi = DHT11_Get_Humi();
            OLED_ShowNum(40, 2, temp);
            OLED_ShowString(58, 2, "C");
            OLED_ShowNum(40, 4, humi);
            OLED_ShowString(58, 4, "%");
            Debug_PrintInt("Temp:", temp);
            Debug_PrintInt("Humi:", humi);
        }} else {{
            OLED_ShowString(40, 2, "Err");
            OLED_ShowString(40, 4, "Err");
            Debug_Print("DHT11 Read Err\r\n");
        }}
        HAL_Delay(2000);
    }}
}}'''
    # 主函数 - 仅串口版本
    elif display == "uart":
        main_code = f'''
{driver_code}

int main(void) {{
    HAL_Init();
    SystemClock_Config();
    MX_USART1_UART_Init();
    Debug_Print("Gary:BOOT\r\n");
    __HAL_RCC_GPIOG_CLK_ENABLE();
    
    HAL_Delay(1000);
    uint8_t dht_ok = (DHT11_Read() == 0);
    Debug_Print(dht_ok ? "DHT11 OK\r\n" : "DHT11 ERR\r\n");
    
    while(1) {{
        if (DHT11_Read() == 0) {{
            uint8_t temp = DHT11_Get_Temp();
            uint8_t humi = DHT11_Get_Humi();
            Debug_PrintInt("Temp:", temp);
            Debug_PrintInt("Humi:", humi);
        }} else {{
            Debug_Print("DHT11 Read Err\r\n");
        }}
        HAL_Delay(2000);
    }}
}}'''
    else:
        main_code = f'''
{driver_code}

int main(void) {{
    HAL_Init();
    SystemClock_Config();
    MX_USART1_UART_Init();
    Debug_Print("Gary:BOOT\r\n");
    __HAL_RCC_GPIOG_CLK_ENABLE();
    
    while(1) {{
        if (DHT11_Read() == 0) {{
            uint8_t temp = DHT11_Get_Temp();
            uint8_t humi = DHT11_Get_Humi();
            // 用户自定义处理
        }}
        HAL_Delay(2000);
    }}
}}'''

    full_code = f'''#include "stm32f4xx_hal.h"
#include <string.h>

{uart_code}

{main_code}'''

    return {
        "success": True,
        "code": full_code,
        "display": display,
        "port": port,
        "pin": pin
    }


# ═══ 工具注册表 ═══

TOOLS_MAP: Dict[str, Any] = {
    "dht11_discovery_get_driver_code": dht11_discovery_get_driver_code,
    "dht11_discovery_get_full_main": dht11_discovery_get_full_main,
}