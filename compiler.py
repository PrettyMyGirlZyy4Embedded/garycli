"""
FlashTalk 编译器 - STM32 交叉编译 + 多芯片适配 + HAL 库自动检测
"""

import subprocess
from pathlib import Path
from config import *

# ==================== 芯片参数表 ====================
# 根据芯片型号自动选择 CPU 核心、Flash/RAM 大小、宏定义、HAL 系列等
CHIP_DB = {
    # --- STM32F1 系列 (Cortex-M3) ---
    "STM32F103C8":  {"cpu": "cortex-m3", "flash_k": 64,  "ram_k": 20,  "define": "STM32F103xB", "family": "f1", "fpu": False},
    "STM32F103CB":  {"cpu": "cortex-m3", "flash_k": 128, "ram_k": 20,  "define": "STM32F103xB", "family": "f1", "fpu": False},
    "STM32F103RB":  {"cpu": "cortex-m3", "flash_k": 128, "ram_k": 20,  "define": "STM32F103xB", "family": "f1", "fpu": False},
    "STM32F103RC":  {"cpu": "cortex-m3", "flash_k": 256, "ram_k": 48,  "define": "STM32F103xE", "family": "f1", "fpu": False},
    "STM32F103RE":  {"cpu": "cortex-m3", "flash_k": 512, "ram_k": 64,  "define": "STM32F103xE", "family": "f1", "fpu": False},
    "STM32F103ZE":  {"cpu": "cortex-m3", "flash_k": 512, "ram_k": 64,  "define": "STM32F103xE", "family": "f1", "fpu": False},
    "STM32F103VE":  {"cpu": "cortex-m3", "flash_k": 512, "ram_k": 64,  "define": "STM32F103xE", "family": "f1", "fpu": False},
    "STM32F100RB":  {"cpu": "cortex-m3", "flash_k": 128, "ram_k": 8,   "define": "STM32F100xB", "family": "f1", "fpu": False},
    "STM32F105":    {"cpu": "cortex-m3", "flash_k": 256, "ram_k": 64,  "define": "STM32F105xC", "family": "f1", "fpu": False},
    "STM32F107":    {"cpu": "cortex-m3", "flash_k": 256, "ram_k": 64,  "define": "STM32F107xC", "family": "f1", "fpu": False},
    # --- STM32F4 系列 (Cortex-M4F) ---
    "STM32F401CC":  {"cpu": "cortex-m4", "flash_k": 256, "ram_k": 64,  "define": "STM32F401xC", "family": "f4", "fpu": True},
    "STM32F401CE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 96,  "define": "STM32F401xE", "family": "f4", "fpu": True},
    "STM32F407VE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 128, "define": "STM32F407xx", "family": "f4", "fpu": True},
    "STM32F407VG":  {"cpu": "cortex-m4", "flash_k": 1024,"ram_k": 128, "define": "STM32F407xx", "family": "f4", "fpu": True},
    "STM32F407ZG":  {"cpu": "cortex-m4", "flash_k": 1024,"ram_k": 128, "define": "STM32F407xx", "family": "f4", "fpu": True},
    "STM32F411CE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 128, "define": "STM32F411xE", "family": "f4", "fpu": True},
    "STM32F429ZI":  {"cpu": "cortex-m4", "flash_k": 2048,"ram_k": 256, "define": "STM32F429xx", "family": "f4", "fpu": True},
    "STM32F446RE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 128, "define": "STM32F446xx", "family": "f4", "fpu": True},
    # --- STM32F0 系列 (Cortex-M0) ---
    "STM32F030F4":  {"cpu": "cortex-m0", "flash_k": 16,  "ram_k": 4,   "define": "STM32F030x6", "family": "f0", "fpu": False},
    "STM32F030C8":  {"cpu": "cortex-m0", "flash_k": 64,  "ram_k": 8,   "define": "STM32F030x8", "family": "f0", "fpu": False},
    "STM32F072RB":  {"cpu": "cortex-m0", "flash_k": 128, "ram_k": 16,  "define": "STM32F072xB", "family": "f0", "fpu": False},
    # --- STM32F3 系列 (Cortex-M4F) ---
    "STM32F303CC":  {"cpu": "cortex-m4", "flash_k": 256, "ram_k": 40,  "define": "STM32F303xC", "family": "f3", "fpu": True},
    "STM32F303RE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 64,  "define": "STM32F303xE", "family": "f3", "fpu": True},
}

# 各系列 IRQ 处理函数名称表（按向量位置排列，None = 保留位填 0）
# 使用具名 weak 别名，C 代码里定义同名函数即可覆盖

_F1_IRQ_NAMES = [
    "WWDG_IRQHandler",            "PVD_IRQHandler",             # 0-1
    "TAMPER_IRQHandler",          "RTC_IRQHandler",             # 2-3
    "FLASH_IRQHandler",           "RCC_IRQHandler",             # 4-5
    "EXTI0_IRQHandler",           "EXTI1_IRQHandler",           # 6-7
    "EXTI2_IRQHandler",           "EXTI3_IRQHandler",           # 8-9
    "EXTI4_IRQHandler",                                         # 10
    "DMA1_Channel1_IRQHandler",   "DMA1_Channel2_IRQHandler",  # 11-12
    "DMA1_Channel3_IRQHandler",   "DMA1_Channel4_IRQHandler",  # 13-14
    "DMA1_Channel5_IRQHandler",   "DMA1_Channel6_IRQHandler",  # 15-16
    "DMA1_Channel7_IRQHandler",   "ADC1_2_IRQHandler",         # 17-18
    "USB_HP_CAN1_TX_IRQHandler",  "USB_LP_CAN1_RX0_IRQHandler",# 19-20
    "CAN1_RX1_IRQHandler",        "CAN1_SCE_IRQHandler",        # 21-22
    "EXTI9_5_IRQHandler",                                       # 23
    "TIM1_BRK_IRQHandler",        "TIM1_UP_IRQHandler",         # 24-25
    "TIM1_TRG_COM_IRQHandler",    "TIM1_CC_IRQHandler",         # 26-27
    "TIM2_IRQHandler",            "TIM3_IRQHandler",            # 28-29
    "TIM4_IRQHandler",                                          # 30
    "I2C1_EV_IRQHandler",         "I2C1_ER_IRQHandler",         # 31-32
    "I2C2_EV_IRQHandler",         "I2C2_ER_IRQHandler",         # 33-34
    "SPI1_IRQHandler",            "SPI2_IRQHandler",            # 35-36
    "USART1_IRQHandler",          "USART2_IRQHandler",          # 37-38
    "USART3_IRQHandler",          "EXTI15_10_IRQHandler",       # 39-40
    "RTC_Alarm_IRQHandler",       "USBWakeUp_IRQHandler",       # 41-42
    "TIM8_BRK_IRQHandler",        "TIM8_UP_IRQHandler",         # 43-44
    "TIM8_TRG_COM_IRQHandler",    "TIM8_CC_IRQHandler",         # 45-46
    "ADC3_IRQHandler",            "FSMC_IRQHandler",            # 47-48
    "SDIO_IRQHandler",            "TIM5_IRQHandler",            # 49-50
    "SPI3_IRQHandler",            "UART4_IRQHandler",           # 51-52
    "UART5_IRQHandler",           "TIM6_IRQHandler",            # 53-54
    "TIM7_IRQHandler",                                          # 55
    "DMA2_Channel1_IRQHandler",   "DMA2_Channel2_IRQHandler",  # 56-57
    "DMA2_Channel3_IRQHandler",   "DMA2_Channel4_5_IRQHandler",# 58-59
    None, None, None, None, None, None, None, None,             # 60-67 保留
]

# F0 中断名与 F1 差异很大：EXTI 合并、TIM 组合等
_F0_IRQ_NAMES = [
    "WWDG_IRQHandler",                "PVD_VDDIO2_IRQHandler",          # 0-1"""
FlashTalk 编译器 - STM32 交叉编译 + 多芯片适配 + HAL 库自动检测
"""

import subprocess
from pathlib import Path
from config import *

# ==================== 芯片参数表 ====================
# 根据芯片型号自动选择 CPU 核心、Flash/RAM 大小、宏定义、HAL 系列等
CHIP_DB = {
    # --- STM32F1 系列 (Cortex-M3) ---
    "STM32F103C8":  {"cpu": "cortex-m3", "flash_k": 64,  "ram_k": 20,  "define": "STM32F103xB", "family": "f1", "fpu": False},
    "STM32F103CB":  {"cpu": "cortex-m3", "flash_k": 128, "ram_k": 20,  "define": "STM32F103xB", "family": "f1", "fpu": False},
    "STM32F103RB":  {"cpu": "cortex-m3", "flash_k": 128, "ram_k": 20,  "define": "STM32F103xB", "family": "f1", "fpu": False},
    "STM32F103RC":  {"cpu": "cortex-m3", "flash_k": 256, "ram_k": 48,  "define": "STM32F103xE", "family": "f1", "fpu": False},
    "STM32F103RE":  {"cpu": "cortex-m3", "flash_k": 512, "ram_k": 64,  "define": "STM32F103xE", "family": "f1", "fpu": False},
    "STM32F103ZE":  {"cpu": "cortex-m3", "flash_k": 512, "ram_k": 64,  "define": "STM32F103xE", "family": "f1", "fpu": False},
    "STM32F103VE":  {"cpu": "cortex-m3", "flash_k": 512, "ram_k": 64,  "define": "STM32F103xE", "family": "f1", "fpu": False},
    "STM32F100RB":  {"cpu": "cortex-m3", "flash_k": 128, "ram_k": 8,   "define": "STM32F100xB", "family": "f1", "fpu": False},
    "STM32F105":    {"cpu": "cortex-m3", "flash_k": 256, "ram_k": 64,  "define": "STM32F105xC", "family": "f1", "fpu": False},
    "STM32F107":    {"cpu": "cortex-m3", "flash_k": 256, "ram_k": 64,  "define": "STM32F107xC", "family": "f1", "fpu": False},
    # --- STM32F4 系列 (Cortex-M4F) ---
    "STM32F401CC":  {"cpu": "cortex-m4", "flash_k": 256, "ram_k": 64,  "define": "STM32F401xC", "family": "f4", "fpu": True},
    "STM32F401CE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 96,  "define": "STM32F401xE", "family": "f4", "fpu": True},
    "STM32F407VE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 128, "define": "STM32F407xx", "family": "f4", "fpu": True},
    "STM32F407VG":  {"cpu": "cortex-m4", "flash_k": 1024,"ram_k": 128, "define": "STM32F407xx", "family": "f4", "fpu": True},
    "STM32F407ZG":  {"cpu": "cortex-m4", "flash_k": 1024,"ram_k": 128, "define": "STM32F407xx", "family": "f4", "fpu": True},
    "STM32F411CE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 128, "define": "STM32F411xE", "family": "f4", "fpu": True},
    "STM32F429ZI":  {"cpu": "cortex-m4", "flash_k": 2048,"ram_k": 256, "define": "STM32F429xx", "family": "f4", "fpu": True},
    "STM32F446RE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 128, "define": "STM32F446xx", "family": "f4", "fpu": True},
    # --- STM32F0 系列 (Cortex-M0) ---
    "STM32F030F4":  {"cpu": "cortex-m0", "flash_k": 16,  "ram_k": 4,   "define": "STM32F030x6", "family": "f0", "fpu": False},
    "STM32F030C8":  {"cpu": "cortex-m0", "flash_k": 64,  "ram_k": 8,   "define": "STM32F030x8", "family": "f0", "fpu": False},
    "STM32F072RB":  {"cpu": "cortex-m0", "flash_k": 128, "ram_k": 16,  "define": "STM32F072xB", "family": "f0", "fpu": False},
    # --- STM32F3 系列 (Cortex-M4F) ---
    "STM32F303CC":  {"cpu": "cortex-m4", "flash_k": 256, "ram_k": 40,  "define": "STM32F303xC", "family": "f3", "fpu": True},
    "STM32F303RE":  {"cpu": "cortex-m4", "flash_k": 512, "ram_k": 64,  "define": "STM32F303xE", "family": "f3", "fpu": True},
}

# 各系列 IRQ 处理函数名称表（按向量位置排列，None = 保留位填 0）
# 使用具名 weak 别名，C 代码里定义同名函数即可覆盖

_F1_IRQ_NAMES = [
    "WWDG_IRQHandler",            "PVD_IRQHandler",             # 0-1
    "TAMPER_IRQHandler",          "RTC_IRQHandler",             # 2-3
    "FLASH_IRQHandler",           "RCC_IRQHandler",             # 4-5
    "EXTI0_IRQHandler",           "EXTI1_IRQHandler",           # 6-7
    "EXTI2_IRQHandler",           "EXTI3_IRQHandler",           # 8-9
    "EXTI4_IRQHandler",                                         # 10
    "DMA1_Channel1_IRQHandler",   "DMA1_Channel2_IRQHandler",  # 11-12
    "DMA1_Channel3_IRQHandler",   "DMA1_Channel4_IRQHandler",  # 13-14
    "DMA1_Channel5_IRQHandler",   "DMA1_Channel6_IRQHandler",  # 15-16
    "DMA1_Channel7_IRQHandler",   "ADC1_2_IRQHandler",         # 17-18
    "USB_HP_CAN1_TX_IRQHandler",  "USB_LP_CAN1_RX0_IRQHandler",# 19-20
    "CAN1_RX1_IRQHandler",        "CAN1_SCE_IRQHandler",        # 21-22
    "EXTI9_5_IRQHandler",                                       # 23
    "TIM1_BRK_IRQHandler",        "TIM1_UP_IRQHandler",         # 24-25
    "TIM1_TRG_COM_IRQHandler",    "TIM1_CC_IRQHandler",         # 26-27
    "TIM2_IRQHandler",            "TIM3_IRQHandler",            # 28-29
    "TIM4_IRQHandler",                                          # 30
    "I2C1_EV_IRQHandler",         "I2C1_ER_IRQHandler",         # 31-32
    "I2C2_EV_IRQHandler",         "I2C2_ER_IRQHandler",         # 33-34
    "SPI1_IRQHandler",            "SPI2_IRQHandler",            # 35-36
    "USART1_IRQHandler",          "USART2_IRQHandler",          # 37-38
    "USART3_IRQHandler",          "EXTI15_10_IRQHandler",       # 39-40
    "RTC_Alarm_IRQHandler",       "USBWakeUp_IRQHandler",       # 41-42
    "TIM8_BRK_IRQHandler",        "TIM8_UP_IRQHandler",         # 43-44
    "TIM8_TRG_COM_IRQHandler",    "TIM8_CC_IRQHandler",         # 45-46
    "ADC3_IRQHandler",            "FSMC_IRQHandler",            # 47-48
    "SDIO_IRQHandler",            "TIM5_IRQHandler",            # 49-50
    "SPI3_IRQHandler",            "UART4_IRQHandler",           # 51-52
    "UART5_IRQHandler",           "TIM6_IRQHandler",            # 53-54
    "TIM7_IRQHandler",                                          # 55
    "DMA2_Channel1_IRQHandler",   "DMA2_Channel2_IRQHandler",  # 56-57
    "DMA2_Channel3_IRQHandler",   "DMA2_Channel4_5_IRQHandler",# 58-59
    None, None, None, None, None, None, None, None,             # 60-67 保留
]

# F0 中断名与 F1 差异很大：EXTI 合并、TIM 组合等
_F0_IRQ_NAMES = [
    "WWDG_IRQHandler",                "PVD_VDDIO2_IRQHandler",          # 0-1
    "RTC_IRQHandler",                 "FLASH_IRQHandler",               # 2-3
    "RCC_CRS_IRQHandler",             "EXTI0_1_IRQHandler",             # 4-5
    "EXTI2_3_IRQHandler",             "EXTI4_15_IRQHandler",            # 6-7
    "TSC_IRQHandler",                 "DMA1_Channel1_IRQHandler",       # 8-9
    "DMA1_Channel2_3_IRQHandler",     "DMA1_Channel4_5_6_7_IRQHandler", # 10-11
    "ADC1_COMP_IRQHandler",           "TIM1_BRK_UP_TRG_COM_IRQHandler", # 12-13
    "TIM1_CC_IRQHandler",             "TIM2_IRQHandler",                # 14-15
    "TIM3_IRQHandler",                "TIM6_DAC_IRQHandler",            # 16-17
    "TIM7_IRQHandler",                "TIM14_IRQHandler",               # 18-19
    "TIM15_IRQHandler",               "TIM16_IRQHandler",               # 20-21
    "TIM17_IRQHandler",               "I2C1_IRQHandler",                # 22-23
    "I2C2_IRQHandler",                "SPI1_IRQHandler",                # 24-25
    "SPI2_IRQHandler",                "USART1_IRQHandler",              # 26-27
    "USART2_IRQHandler",              "USART3_4_IRQHandler",            # 28-29
    "CEC_CAN_IRQHandler",             "USB_IRQHandler",                 # 30-31
]

_F3_IRQ_NAMES = [
    "WWDG_IRQHandler",            "PVD_IRQHandler",             # 0-1
    "TAMP_STAMP_IRQHandler",      "RTC_WKUP_IRQHandler",        # 2-3
    "FLASH_IRQHandler",           "RCC_IRQHandler",             # 4-5
    "EXTI0_IRQHandler",           "EXTI1_IRQHandler",           # 6-7
    "EXTI2_TSC_IRQHandler",       "EXTI3_IRQHandler",           # 8-9
    "EXTI4_IRQHandler",                                         # 10
    "DMA1_Channel1_IRQHandler",   "DMA1_Channel2_IRQHandler",  # 11-12
    "DMA1_Channel3_IRQHandler",   "DMA1_Channel4_IRQHandler",  # 13-14
    "DMA1_Channel5_IRQHandler",   "DMA1_Channel6_IRQHandler",  # 15-16
    "DMA1_Channel7_IRQHandler",   "ADC1_2_IRQHandler",         # 17-18
    "USB_HP_CAN1_TX_IRQHandler",  "USB_LP_CAN1_RX0_IRQHandler",# 19-20
    "CAN1_RX1_IRQHandler",        "CAN1_SCE_IRQHandler",        # 21-22
    "EXTI9_5_IRQHandler",                                       # 23
    "TIM1_BRK_TIM15_IRQHandler",  "TIM1_UP_TIM16_IRQHandler",  # 24-25
    "TIM1_TRG_COM_TIM17_IRQHandler", "TIM1_CC_IRQHandler",     # 26-27
    "TIM2_IRQHandler",            "TIM3_IRQHandler",            # 28-29
    "TIM4_IRQHandler",                                          # 30
    "I2C1_EV_IRQHandler",         "I2C1_ER_IRQHandler",         # 31-32
    "I2C2_EV_IRQHandler",         "I2C2_ER_IRQHandler",         # 33-34
    "SPI1_IRQHandler",            "SPI2_IRQHandler",            # 35-36
    "USART1_IRQHandler",          "USART2_IRQHandler",          # 37-38
    "USART3_IRQHandler",          "EXTI15_10_IRQHandler",       # 39-40
    "RTC_Alarm_IRQHandler",       "USBWakeUp_IRQHandler",       # 41-42
    "TIM8_BRK_IRQHandler",        "TIM8_UP_IRQHandler",         # 43-44
    "TIM8_TRG_COM_IRQHandler",    "TIM8_CC_IRQHandler",         # 45-46
    "ADC3_IRQHandler",            None, None,                   # 47-49
    "SPI3_IRQHandler",            "UART4_IRQHandler",           # 50-51
    "UART5_IRQHandler",           "TIM6_DAC_IRQHandler",        # 52-53
    "TIM7_IRQHandler",                                          # 54
    "DMA2_Channel1_IRQHandler",   "DMA2_Channel2_IRQHandler",  # 55-56
    "DMA2_Channel3_IRQHandler",   "DMA2_Channel4_IRQHandler",  # 57-58
    "DMA2_Channel5_IRQHandler",   "ADC4_IRQHandler",            # 59-60
    None, None,                                                 # 61-62
    "COMP1_2_3_IRQHandler",       "COMP4_5_6_IRQHandler",       # 63-64
    "COMP7_IRQHandler",           None, None, None, None, None, # 65-70
    "I2C3_EV_IRQHandler",         "I2C3_ER_IRQHandler",         # 71-72 (实际69-70)
    "USB_HP_IRQHandler",          "USB_LP_IRQHandler",          # 73-74
    "USBWakeUp_RMP_IRQHandler",                                 # 75
    "TIM20_BRK_IRQHandler",       "TIM20_UP_IRQHandler",        # 76-77
    "TIM20_TRG_COM_IRQHandler",   "TIM20_CC_IRQHandler",        # 78-79
    "FPU_IRQHandler",             "SPI4_IRQHandler",            # 80-81
]

_F4_IRQ_NAMES = [
    "WWDG_IRQHandler",            "PVD_IRQHandler",             # 0-1
    "TAMP_STAMP_IRQHandler",      "RTC_WKUP_IRQHandler",        # 2-3
    "FLASH_IRQHandler",           "RCC_IRQHandler",             # 4-5
    "EXTI0_IRQHandler",           "EXTI1_IRQHandler",           # 6-7
    "EXTI2_IRQHandler",           "EXTI3_IRQHandler",           # 8-9
    "EXTI4_IRQHandler",                                         # 10
    "DMA1_Stream0_IRQHandler",    "DMA1_Stream1_IRQHandler",   # 11-12
    "DMA1_Stream2_IRQHandler",    "DMA1_Stream3_IRQHandler",   # 13-14
    "DMA1_Stream4_IRQHandler",    "DMA1_Stream5_IRQHandler",   # 15-16
    "DMA1_Stream6_IRQHandler",    "ADC_IRQHandler",             # 17-18
    "CAN1_TX_IRQHandler",         "CAN1_RX0_IRQHandler",        # 19-20
    "CAN1_RX1_IRQHandler",        "CAN1_SCE_IRQHandler",        # 21-22
    "EXTI9_5_IRQHandler",                                       # 23
    "TIM1_BRK_TIM9_IRQHandler",   "TIM1_UP_TIM10_IRQHandler",  # 24-25
    "TIM1_TRG_COM_TIM11_IRQHandler", "TIM1_CC_IRQHandler",     # 26-27
    "TIM2_IRQHandler",            "TIM3_IRQHandler",            # 28-29
    "TIM4_IRQHandler",                                          # 30
    "I2C1_EV_IRQHandler",         "I2C1_ER_IRQHandler",         # 31-32
    "I2C2_EV_IRQHandler",         "I2C2_ER_IRQHandler",         # 33-34
    "SPI1_IRQHandler",            "SPI2_IRQHandler",            # 35-36
    "USART1_IRQHandler",          "USART2_IRQHandler",          # 37-38
    "USART3_IRQHandler",          "EXTI15_10_IRQHandler",       # 39-40
    "RTC_Alarm_IRQHandler",       "OTG_FS_WKUP_IRQHandler",     # 41-42
    "TIM8_BRK_TIM12_IRQHandler",  "TIM8_UP_TIM13_IRQHandler",  # 43-44
    "TIM8_TRG_COM_TIM14_IRQHandler", "TIM8_CC_IRQHandler",     # 45-46
    "DMA1_Stream7_IRQHandler",    "FSMC_IRQHandler",            # 47-48
    "SDIO_IRQHandler",            "TIM5_IRQHandler",            # 49-50
    "SPI3_IRQHandler",            "UART4_IRQHandler",           # 51-52
    "UART5_IRQHandler",           "TIM6_DAC_IRQHandler",        # 53-54
    "TIM7_IRQHandler",                                          # 55
    "DMA2_Stream0_IRQHandler",    "DMA2_Stream1_IRQHandler",   # 56-57
    "DMA2_Stream2_IRQHandler",    "DMA2_Stream3_IRQHandler",   # 58-59
    "DMA2_Stream4_IRQHandler",    "ETH_IRQHandler",             # 60-61
    "ETH_WKUP_IRQHandler",        "CAN2_TX_IRQHandler",         # 62-63
    "CAN2_RX0_IRQHandler",        "CAN2_RX1_IRQHandler",        # 64-65
    "CAN2_SCE_IRQHandler",        "OTG_FS_IRQHandler",          # 66-67
    "DMA2_Stream5_IRQHandler",    "DMA2_Stream6_IRQHandler",   # 68-69
    "DMA2_Stream7_IRQHandler",    "USART6_IRQHandler",          # 70-71
    "I2C3_EV_IRQHandler",         "I2C3_ER_IRQHandler",         # 72-73
    "OTG_HS_EP1_OUT_IRQHandler",  "OTG_HS_EP1_IN_IRQHandler",  # 74-75
    "OTG_HS_WKUP_IRQHandler",     "OTG_HS_IRQHandler",          # 76-77
    "DCMI_IRQHandler",            None,                         # 78-79
    "HASH_RNG_IRQHandler",        "FPU_IRQHandler",             # 80-81
]

_FAMILY_IRQ_NAMES = {
    "f0": _F0_IRQ_NAMES,
    "f1": _F1_IRQ_NAMES,
    "f3": _F3_IRQ_NAMES,
    "f4": _F4_IRQ_NAMES,
}

# 每个 family 对应的 HAL 源文件
_FAMILY_HAL_FILES = {
    "f1": [
        "stm32f1xx_hal.c", "stm32f1xx_hal_cortex.c",
        "stm32f1xx_hal_rcc.c", "stm32f1xx_hal_rcc_ex.c",
        "stm32f1xx_hal_gpio.c", "stm32f1xx_hal_gpio_ex.c",
        "stm32f1xx_hal_uart.c", "stm32f1xx_hal_usart.c",
        "stm32f1xx_hal_tim.c", "stm32f1xx_hal_tim_ex.c",
        "stm32f1xx_hal_adc.c", "stm32f1xx_hal_adc_ex.c",
        "stm32f1xx_hal_i2c.c",
        "stm32f1xx_hal_dma.c",
        "stm32f1xx_hal_pwr.c",
        "stm32f1xx_hal_flash.c", "stm32f1xx_hal_flash_ex.c",
        "stm32f1xx_hal_exti.c",
        "stm32f1xx_hal_spi.c",
        "system_stm32f1xx.c",
    ],
    "f4": [
        "stm32f4xx_hal.c", "stm32f4xx_hal_cortex.c",
        "stm32f4xx_hal_rcc.c", "stm32f4xx_hal_rcc_ex.c",
        "stm32f4xx_hal_gpio.c",
        "stm32f4xx_hal_uart.c", "stm32f4xx_hal_usart.c",
        "stm32f4xx_hal_tim.c", "stm32f4xx_hal_tim_ex.c",
        "stm32f4xx_hal_adc.c", "stm32f4xx_hal_adc_ex.c",
        "stm32f4xx_hal_i2c.c", "stm32f4xx_hal_i2c_ex.c",
        "stm32f4xx_hal_dma.c", "stm32f4xx_hal_dma_ex.c",
        "stm32f4xx_hal_pwr.c", "stm32f4xx_hal_pwr_ex.c",
        "stm32f4xx_hal_flash.c", "stm32f4xx_hal_flash_ex.c",
        "stm32f4xx_hal_exti.c",
        "stm32f4xx_hal_spi.c",
        "system_stm32f4xx.c",
    ],
    "f0": [
        "stm32f0xx_hal.c", "stm32f0xx_hal_cortex.c",
        "stm32f0xx_hal_rcc.c", "stm32f0xx_hal_rcc_ex.c",
        "stm32f0xx_hal_gpio.c",
        "stm32f0xx_hal_uart.c", "stm32f0xx_hal_usart.c",
        "stm32f0xx_hal_tim.c", "stm32f0xx_hal_tim_ex.c",
        "stm32f0xx_hal_adc.c", "stm32f0xx_hal_adc_ex.c",
        "stm32f0xx_hal_i2c.c", "stm32f0xx_hal_i2c_ex.c",
        "stm32f0xx_hal_dma.c",
        "stm32f0xx_hal_pwr.c", "stm32f0xx_hal_pwr_ex.c",
        "stm32f0xx_hal_flash.c", "stm32f0xx_hal_flash_ex.c",
        "stm32f0xx_hal_spi.c",
        "system_stm32f0xx.c",
    ],
    "f3": [
        "stm32f3xx_hal.c", "stm32f3xx_hal_cortex.c",
        "stm32f3xx_hal_rcc.c", "stm32f3xx_hal_rcc_ex.c",
        "stm32f3xx_hal_gpio.c",
        "stm32f3xx_hal_uart.c", "stm32f3xx_hal_usart.c",
        "stm32f3xx_hal_tim.c", "stm32f3xx_hal_tim_ex.c",
        "stm32f3xx_hal_adc.c", "stm32f3xx_hal_adc_ex.c",
        "stm32f3xx_hal_i2c.c", "stm32f3xx_hal_i2c_ex.c",
        "stm32f3xx_hal_dma.c",
        "stm32f3xx_hal_pwr.c", "stm32f3xx_hal_pwr_ex.c",
        "stm32f3xx_hal_flash.c", "stm32f3xx_hal_flash_ex.c",
        "stm32f3xx_hal_spi.c",
        "system_stm32f3xx.c",
    ],
}


def _lookup_chip(chip_name: str) -> dict:
    """根据芯片名称查找参数，支持模糊匹配"""
    import re
    name = chip_name.upper().replace("-", "").replace(" ", "")
    # 精确匹配
    if name in CHIP_DB:
        return CHIP_DB[name]
    # 去掉尾部封装后缀（T6, T7, Tx, U6 等）尝试
    for suffix_len in range(2, 0, -1):
        key = name[:-suffix_len] if len(name) > suffix_len else name
        if key in CHIP_DB:
            return CHIP_DB[key]
    # 前缀匹配（如 "STM32F103C8T6" 匹配 "STM32F103C8"）
    for key in CHIP_DB:
        if name.startswith(key):
            return CHIP_DB[key]
    # 从描述性名称中提取型号（如 "STM32F103 Medium-density" → 匹配 STM32F103 开头的条目）
    m = re.match(r'(STM32[A-Z]\d{3})', name)
    if m:
        prefix = m.group(1)
        # 找第一个匹配的型号（优先选常见封装）
        for key in CHIP_DB:
            if key.startswith(prefix):
                return CHIP_DB[key]
    return None


def _gen_linker_script(flash_k: int, ram_k: int) -> str:
    """根据芯片 Flash/RAM 大小生成链接脚本"""
    return f"""MEMORY {{
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = {flash_k}K
  RAM   (xrw) : ORIGIN = 0x20000000, LENGTH = {ram_k}K
}}
_estack = ORIGIN(RAM) + LENGTH(RAM);
_Min_Heap_Size = 0x200;
_Min_Stack_Size = 0x400;
SECTIONS {{
  .isr_vector : {{ KEEP(*(.isr_vector)) }} >FLASH
  .text : {{ *(.text*) *(.rodata*) . = ALIGN(4); _etext = .; }} >FLASH
  .init : {{ KEEP(*(.init)) }} >FLASH
  .fini : {{ KEEP(*(.fini)) }} >FLASH
  .init_array : {{ KEEP(*(.init_array*)) }} >FLASH
  .fini_array : {{ KEEP(*(.fini_array*)) }} >FLASH
  .data : AT(_etext) {{ _sdata = .; *(.data*) . = ALIGN(4); _edata = .; }} >RAM
  .bss : {{ _sbss = .; *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; }} >RAM
  ._user_heap_stack : {{ . = ALIGN(8); . = . + _Min_Heap_Size; . = . + _Min_Stack_Size; . = ALIGN(8); }} >RAM
  /DISCARD/ : {{ *(.ARM.*) }}
}}
"""


def _gen_startup(cpu: str, irq_names: list) -> str:
    """生成启动汇编：每个 IRQ 都有具名 weak 别名，C 代码定义同名函数即可覆盖"""
    # 向量表条目（None = 保留位填 0）
    vec_lines = []
    for name in irq_names:
        vec_lines.append(f"  .word {name}" if name else "  .word 0  /* reserved */")
    vec_section = "\n".join(vec_lines)

    # weak 别名定义（跳过保留位）
    weak_lines = []
    for name in irq_names:
        if name:
            weak_lines.append(f".weak {name}\n.thumb_set {name}, Default_Handler")
    weak_section = "\n".join(weak_lines)

    return f""".syntax unified
.cpu {cpu}
.thumb

.global g_pfnVectors
.global Default_Handler

.section .isr_vector,"a",%progbits
.type g_pfnVectors, %object
g_pfnVectors:
  .word _estack
  .word Reset_Handler
  .word NMI_Handler
  .word HardFault_Handler
  .word MemManage_Handler
  .word BusFault_Handler
  .word UsageFault_Handler
  .word 0,0,0,0
  .word SVC_Handler
  .word DebugMon_Handler
  .word 0
  .word PendSV_Handler
  .word SysTick_Handler
{vec_section}

.section .text.Reset_Handler
.weak Reset_Handler
.type Reset_Handler, %function
Reset_Handler:
  ldr r0, =_estack
  mov sp, r0
  ldr r0, =_sdata
  ldr r1, =_edata
  ldr r2, =_etext
  b 2f
1: ldr r3, [r2], #4
  str r3, [r0], #4
2: cmp r0, r1
  blt 1b
  ldr r0, =_sbss
  ldr r1, =_ebss
  movs r2, #0
  b 4f
3: str r2, [r0], #4
4: cmp r0, r1
  blt 3b
  bl SystemInit
  bl main
  b .

.section .text.Default_Handler,"ax",%progbits
Default_Handler: b .

.weak NMI_Handler
.thumb_set NMI_Handler, Default_Handler
.weak HardFault_Handler
.thumb_set HardFault_Handler, Default_Handler
.weak MemManage_Handler
.thumb_set MemManage_Handler, Default_Handler
.weak BusFault_Handler
.thumb_set BusFault_Handler, Default_Handler
.weak UsageFault_Handler
.thumb_set UsageFault_Handler, Default_Handler
.weak SVC_Handler
.thumb_set SVC_Handler, Default_Handler
.weak DebugMon_Handler
.thumb_set DebugMon_Handler, Default_Handler
.weak PendSV_Handler
.thumb_set PendSV_Handler, Default_Handler
.weak SysTick_Handler
.thumb_set SysTick_Handler, Default_Handler
.weak SystemInit
.thumb_set SystemInit, Default_Handler
{weak_section}
"""


class Compiler:
    """STM32 交叉编译器 - 支持多芯片系列"""

    def __init__(self):
        self.has_gcc = False
        self.has_specs = False
        self.has_hal = False
        self.has_hal_lib = False  # HAL 是否已预编译为静态库
        self.hal_inc_dirs = []
        self.hal_src_files = []
        self._chip_info = None  # 当前芯片参数
        self._current_family = None

        BUILD_DIR.mkdir(parents=True, exist_ok=True)

    def set_chip(self, chip_name: str) -> dict:
        """设置目标芯片，返回芯片参数或 None"""
        info = _lookup_chip(chip_name)
        if info is None:
            # 未知芯片，默认 F103C8
            print(f"  ⚠️ 未知芯片 {chip_name}，使用默认 STM32F103C8 参数")
            info = CHIP_DB["STM32F103C8"]
        self._chip_info = info

        # 生成链接脚本和启动文件
        ld = _gen_linker_script(info["flash_k"], info["ram_k"])
        (BUILD_DIR / "link.ld").write_text(ld)

        irq_names = _FAMILY_IRQ_NAMES.get(info["family"], _F1_IRQ_NAMES)
        startup = _gen_startup(info["cpu"], irq_names)
        (BUILD_DIR / "startup.s").write_text(startup)

        # 如果 family 变了，重新查找 HAL
        if info["family"] != self._current_family:
            self._current_family = info["family"]
            self._find_hal(info["family"])

        return info

    def check(self, chip_name: str = None) -> dict:
        """检测编译环境"""
        info = {"gcc": False, "gcc_version": "", "specs": False, "hal": False, "chip_info": None}

        # 设置芯片（如果没设过，用默认）
        if chip_name:
            info["chip_info"] = self.set_chip(chip_name)
        elif self._chip_info is None:
            info["chip_info"] = self.set_chip(DEFAULT_CHIP)

        # GCC
        try:
            r = subprocess.run([ARM_GCC, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                self.has_gcc = True
                info["gcc"] = True
                info["gcc_version"] = r.stdout.split('\n')[0]
        except Exception:
            pass

        # specs
        cpu = self._chip_info["cpu"] if self._chip_info else "cortex-m3"
        if self.has_gcc:
            try:
                r = subprocess.run(
                    [ARM_GCC, f"-mcpu={cpu}", "-mthumb",
                     "--specs=nosys.specs", "--specs=nano.specs",
                     "-x", "c", "-E", "-", "-o", "/dev/null"],
                    input="", capture_output=True, text=True, timeout=5)
                self.has_specs = r.returncode == 0
                info["specs"] = self.has_specs
            except Exception:
                pass

        info["hal"] = self.has_hal
        # 有 HAL + 有 GCC → 自动触发预编译（首次约 60s，后续秒级）
        if self.has_hal and self.has_gcc:
            self.precompile_hal()
        info["hal_lib"] = self.has_hal_lib
        return info

    def _find_hal(self, family: str = "f1"):
        """查找 HAL 库，构建 include 目录和源文件列表"""
        hal = HAL_DIR
        hal_header = f"stm32{family}xx_hal.h"
        self.has_hal_lib = False  # family 变化时重置，需重新预编译

        if not (hal / "Inc" / hal_header).exists():
            self.has_hal = False
            self.hal_inc_dirs = []
            self.hal_src_files = []
            return

        self.has_hal = True
        self.hal_inc_dirs = [str(hal / "Inc")]

        # CMSIS 头文件目录
        cmsis_paths = [
            hal / "CMSIS" / "Include",
            hal / "CMSIS" / "Core" / "Include",
        ]
        for p in cmsis_paths:
            if p.exists():
                self.hal_inc_dirs.append(str(p))

        # HAL 源文件
        hal_src = hal / "Src"
        needed = _FAMILY_HAL_FILES.get(family, [])
        self.hal_src_files = [str(hal_src / f) for f in needed if (hal_src / f).exists()]

    def precompile_hal(self) -> bool:
        """将 HAL 源文件预编译为静态库，后续编译只需链接 main.c，速度从 30s→3s。
        支持增量编译：只重新编译有改动的 .c 文件。"""
        if not self.has_hal or not self.has_gcc or not self._chip_info:
            return False

        family = self._current_family or "f1"
        lib_path = BUILD_DIR / f"libstm32hal_{family}.a"
        obj_dir  = BUILD_DIR / f"hal_obj_{family}"
        obj_dir.mkdir(exist_ok=True)

        ci = self._chip_info
        cpu_flags = [f"-mcpu={ci['cpu']}", "-mthumb"]
        if ci["fpu"]:
            cpu_flags += ["-mfloat-abi=hard", "-mfpu=fpv4-sp-d16"]
        inc_flags = [f"-I{d}" for d in self.hal_inc_dirs]

        # 找出哪些 .o 比源文件旧（增量判断）
        to_compile = []
        obj_files  = []
        for src in self.hal_src_files:
            src_path = Path(src)
            obj = obj_dir / (src_path.stem + ".o")
            obj_files.append(obj)
            if not obj.exists() or obj.stat().st_mtime < src_path.stat().st_mtime:
                to_compile.append((src_path, obj))

        if not to_compile and lib_path.exists():
            self.has_hal_lib = True
            return True  # 已是最新，直接用

        total = len(self.hal_src_files)
        fresh = total - len(to_compile)
        print(f"  🔨 预编译 HAL ({len(to_compile)} 个/共 {total}，{fresh} 个复用缓存)...")

        for src_path, obj in to_compile:
            cmd = [
                ARM_GCC, *cpu_flags,
                f"-D{ci['define']}", "-DUSE_HAL_DRIVER",
                *inc_flags,
                "-Os", "-ffunction-sections", "-fdata-sections",
                "-c", str(src_path), "-o", str(obj),
            ]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    first_err = r.stderr.split('\n')[0][:120]
                    print(f"  ❌ {src_path.name}: {first_err}")
                    return False
            except Exception as e:
                print(f"  ❌ 预编译异常: {e}")
                return False

        # 归档所有 .o → .a
        existing = [str(o) for o in obj_files if o.exists()]
        if not existing:
            return False
        try:
            r = subprocess.run([ARM_AR, "rcs", str(lib_path)] + existing,
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                print(f"  ❌ ar 归档失败: {r.stderr[:100]}")
                return False
        except Exception as e:
            print(f"  ❌ ar 异常: {e}")
            return False

        size_kb = lib_path.stat().st_size // 1024
        print(f"  ✅ HAL 静态库已就绪: {lib_path.name} ({size_kb} KB)")
        self.has_hal_lib = True
        return True

    def compile(self, code: str) -> dict:
        """编译 C 代码，返回 {ok, msg, bin_path, bin_size}"""
        if self._chip_info is None:
            self.set_chip(DEFAULT_CHIP)

        ci = self._chip_info
        main_c = BUILD_DIR / "main.c"
        main_c.write_text(code)
        elf = BUILD_DIR / "firmware.elf"
        binf = BUILD_DIR / "firmware.bin"

        for f in [elf, binf]:
            f.unlink(missing_ok=True)

        if not self.has_gcc:
            return {"ok": False, "msg": "arm-none-eabi-gcc 未安装", "bin_path": None, "bin_size": 0}

        # CPU 和 FPU 参数
        cpu_flags = [f"-mcpu={ci['cpu']}", "-mthumb"]
        if ci["fpu"]:
            cpu_flags += ["-mfloat-abi=hard", "-mfpu=fpv4-sp-d16"]

        if self.has_hal:
            inc_flags = [f"-I{d}" for d in self.hal_inc_dirs]
            family = self._current_family or "f1"

            if self.has_hal_lib:
                # 快速路径：只编译 main.c，链接预编译静态库（~3s）
                extra_srcs = []
                extra_libs = [f"-L{BUILD_DIR}", f"-lstm32hal_{family}"]
            else:
                # 兜底路径：重新编译所有 HAL 源文件（~30-60s）
                extra_srcs = self.hal_src_files
                extra_libs = []

            cmd = [
                ARM_GCC,
                *cpu_flags,
                f"-D{ci['define']}", "-DUSE_HAL_DRIVER",
                *inc_flags,
                "-Os", "-Wall", "-Wno-unused-variable", "-Wno-unused-function",
                "-ffunction-sections", "-fdata-sections",
                f"-T{BUILD_DIR / 'link.ld'}",
                "-Wl,--gc-sections",
                str(main_c),
                str(BUILD_DIR / "startup.s"),
                *extra_srcs,
                "-o", str(elf),
                "-nostartfiles",
                *extra_libs,
                "-lc", "-lm", "-lnosys",
            ]
            if self.has_specs:
                cmd += ["--specs=nosys.specs", "--specs=nano.specs"]
        else:
            cmd = [
                ARM_GCC, *cpu_flags, f"-D{ci['define']}",
                "-fsyntax-only", "-Wall", str(main_c),
            ]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                if self.has_hal and elf.exists():
                    subprocess.run([ARM_OBJCOPY, "-O", "binary", str(elf), str(binf)], timeout=10)
                    sz = binf.stat().st_size if binf.exists() else 0
                    return {"ok": True, "msg": f"编译成功 ({sz}B)", "bin_path": str(binf), "bin_size": sz}
                return {"ok": True, "msg": "语法检查通过(无HAL)", "bin_path": None, "bin_size": 0}
            else:
                err = r.stderr
                lines = [l for l in err.split('\n')
                         if any(k in l for k in ['error:', 'undefined reference', 'multiple definition',
                                                   'cannot find', 'No such file', 'fatal:'])]
                lines = [l for l in lines if 'collect2:' not in l] or lines
                short = '\n'.join(lines[:15]) if lines else err[:1000]
                return {"ok": False, "msg": short, "bin_path": None, "bin_size": 0}
        except subprocess.TimeoutExpired:
            return {"ok": False, "msg": "编译超时", "bin_path": None, "bin_size": 0}
        except Exception as e:
            return {"ok": False, "msg": str(e), "bin_path": None, "bin_size": 0}
