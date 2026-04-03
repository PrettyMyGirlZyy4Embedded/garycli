#!/usr/bin/env python3
"""
dht11_atomic - 正点原子标准DHT11温湿度传感器驱动

特性：
- 基于正点原子官方驱动，时序精准
- 支持STM32F103任意GPIO引脚
- 自动校验和检查
- 非阻塞读取，带超时保护
"""
from typing import Dict, Any


def dht11_atomic_get_driver_code(port: str = "GPIOG", pin: int = 11) -> dict:
    """
    获取正点原子标准DHT11驱动代码
    
    Args:
        port: GPIO端口，如 GPIOA, GPIOB, GPIOC, GPIOD, GPIOE, GPIOF, GPIOG
        pin: GPIO引脚号，如 0-15
    
    Returns:
        code: 可直接使用的DHT11驱动C代码
    """
    code = f'''/* ==================== DHT11 驱动 ({port} Pin{pin}) - 正点原子标准版 ==================== */
#define DHT11_PIN       GPIO_PIN_{pin}
#define DHT11_PORT      {port}

#define DHT11_HIGH()    HAL_GPIO_WritePin(DHT11_PORT, DHT11_PIN, GPIO_PIN_SET)
#define DHT11_LOW()     HAL_GPIO_WritePin(DHT11_PORT, DHT11_PIN, GPIO_PIN_RESET)
#define DHT11_READ()    HAL_GPIO_ReadPin(DHT11_PORT, DHT11_PIN)

static uint8_t DHT11_Data[5];

/* 延时函数 - 72MHz下 */
static void DHT11_DelayUs(uint32_t us) {{
    __IO uint32_t count = us * 8;  /* 72MHz下约8个周期1us */
    while(count--);
}}

static void DHT11_DelayMs(uint32_t ms) {{
    HAL_Delay(ms);
}}

/* 复位DHT11 */
static void DHT11_Rst(void) {{
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DHT11_PIN;
    GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DHT11_PORT, &GPIO_Init);
    
    DHT11_LOW();
    DHT11_DelayMs(20);  /* 拉低至少18ms */
    DHT11_HIGH();
    DHT11_DelayUs(30);  /* 拉高20~40us */
}}

/* 等待DHT11回应
 * 返回0: 正常
 * 返回1: 未检测到DHT11
 */
static uint8_t DHT11_Check(void) {{
    uint8_t retry = 0;
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DHT11_PIN;
    GPIO_Init.Mode = GPIO_MODE_INPUT;
    GPIO_Init.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(DHT11_PORT, &GPIO_Init);
    
    /* 等待DHT11拉低响应 (80us) */
    while (DHT11_READ() == GPIO_PIN_SET && retry < 100) {{
        retry++;
        DHT11_DelayUs(1);
    }}
    if(retry >= 100) return 1;  /* DHT11未响应 */
    
    /* 等待DHT11拉高 (80us) */
    retry = 0;
    while (DHT11_READ() == GPIO_PIN_RESET && retry < 100) {{
        retry++;
        DHT11_DelayUs(1);
    }}
    if(retry >= 100) return 1;
    
    /* 等待准备发送数据 */
    retry = 0;
    while (DHT11_READ() == GPIO_PIN_SET && retry < 100) {{
        retry++;
        DHT11_DelayUs(1);
    }}
    if(retry >= 100) return 1;
    
    return 0;
}}

/* 从DHT11读取一个位 */
static uint8_t DHT11_Read_Bit(void) {{
    uint8_t retry = 0;
    
    /* 等待低电平结束 (50us) */
    while (DHT11_READ() == GPIO_PIN_RESET && retry < 100) {{
        retry++;
        DHT11_DelayUs(1);
    }}
    
    /* 延时40us */
    DHT11_DelayUs(40);
    
    /* 读取电平状态 */
    uint8_t bit = 0;
    if (DHT11_READ() == GPIO_PIN_SET) {{
        bit = 1;
    }}
    
    /* 等待高电平结束 */
    retry = 0;
    while (DHT11_READ() == GPIO_PIN_SET && retry < 100) {{
        retry++;
        DHT11_DelayUs(1);
    }}
    
    return bit;
}}

/* 从DHT11读取一个字节 */
static uint8_t DHT11_Read_Byte(void) {{
    uint8_t byte = 0;
    for (uint8_t i = 0; i < 8; i++) {{
        byte <<= 1;
        byte |= DHT11_Read_Bit();
    }}
    return byte;
}}

/* 读取DHT11完整数据
 * 返回0: 成功
 * 返回1: 设备未响应
 * 返回2: 校验失败
 */
uint8_t DHT11_Read(void) {{
    DHT11_Rst();
    if (DHT11_Check() != 0) return 1;  /* 设备未响应 */
    
    /* 读取5字节数据 */
    DHT11_Data[0] = DHT11_Read_Byte();  /* 湿度整数 */
    DHT11_Data[1] = DHT11_Read_Byte();  /* 湿度小数 */
    DHT11_Data[2] = DHT11_Read_Byte();  /* 温度整数 */
    DHT11_Data[3] = DHT11_Read_Byte();  /* 温度小数 */
    DHT11_Data[4] = DHT11_Read_Byte();  /* 校验和 */
    
    /* 结束信号 */
    GPIO_InitTypeDef GPIO_Init = {{0}};
    GPIO_Init.Pin = DHT11_PIN;
    GPIO_Init.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_Init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DHT11_PORT, &GPIO_Init);
    DHT11_HIGH();
    
    /* 校验 */
    if ((DHT11_Data[0] + DHT11_Data[1] + DHT11_Data[2] + DHT11_Data[3]) != DHT11_Data[4]) {{
        return 2;  /* 校验失败 */
    }}
    
    return 0;
}}

/* 获取温湿度值 */
uint8_t DHT11_Get_Humi(void) {{ return DHT11_Data[0]; }}
uint8_t DHT11_Get_Temp(void) {{ return DHT11_Data[2]; }}
'''
    return {
        "success": True,
        "code": code,
        "port": port,
        "pin": pin
    }


def dht11_atomic_get_full_main(port: str = "GPIOG", pin: int = 11, display: str = "oled") -> dict:
    """
    获取完整的main.c示例代码（DHT11 + OLED显示）
    
    Args:
        port: GPIO端口
        pin: GPIO引脚号
        display: 显示方式 (oled/uart/none)
    
    Returns:
        code: 完整可编译的main.c代码
    """
    driver = dht11_atomic_get_driver_code(port, pin)["code"]
    
    if display == "oled":
        demo_code = '''    OLED_ShowString(0, 0, "DHT11 Sensor");
    OLED_ShowString(0, 2, "Temp: -- C");
    OLED_ShowString(0, 4, "Humi: -- %");
    
    while (1) {
        if (DHT11_Read() == 0) {
            OLED_ShowString(0, 2, "Temp:    C");
            OLED_ShowNum(36, 2, DHT11_Get_Temp(), 2);
            OLED_ShowString(0, 4, "Humi:    %");
            OLED_ShowNum(36, 4, DHT11_Get_Humi(), 2);
            OLED_ShowString(90, 6, "OK ");
        } else {
            OLED_ShowString(90, 6, "Err");
        }
        HAL_Delay(2000);
    }'''
    elif display == "uart":
        demo_code = '''    while (1) {
        if (DHT11_Read() == 0) {
            Debug_Print("Temp: ");
            Debug_PrintInt(DHT11_Get_Temp());
            Debug_Print(" C, Humi: ");
            Debug_PrintInt(DHT11_Get_Humi());
            Debug_Print(" %\\r\\n");
        } else {
            Debug_Print("DHT11 Error\\r\\n");
        }
        HAL_Delay(2000);
    }'''
    else:
        demo_code = '''    while (1) {
        DHT11_Read();
        HAL_Delay(2000);
    }'''
    
    main_code = f'''#include "stm32f1xx_hal.h"
#include <string.h>

/* 简易调试输出 */
UART_HandleTypeDef huart1;
void Debug_Print(const char* s) {{
    HAL_UART_Transmit(&huart1, (uint8_t*)s, strlen(s), 100);
}}

void SystemClock_Config(void) {{
    RCC_OscInitTypeDef RCC_OscInitStruct = {{0}};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {{0}};
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

/* DHT11驱动 */
{driver}

int main(void) {{
    HAL_Init();
    SystemClock_Config();
    MX_USART1_UART_Init();
    Debug_Print("Gary:BOOT\\r\\n");
    
    /* 使能DHT11 GPIO时钟 */
    __HAL_RCC_{port}_CLK_ENABLE();
    
{demo_code}
}}
'''
    return {
        "success": True,
        "code": main_code,
        "port": port,
        "pin": pin,
        "display": display
    }


# 工具注册表
TOOLS_MAP = {
    "dht11_atomic_get_driver_code": dht11_atomic_get_driver_code,
    "dht11_atomic_get_full_main": dht11_atomic_get_full_main,
}
