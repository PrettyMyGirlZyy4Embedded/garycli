## Skill: 正点原子探索版DHT11温湿度传感器驱动

当用户需要在正点原子探索版STM32F407上使用DHT11温湿度传感器时，使用此Skill。

### 使用场景

- 需要读取DHT11温湿度数据
- 需要在OLED上显示温湿度
- 需要通过串口输出温湿度数据

### 工具选择

1. **仅需驱动代码** → `dht11_discovery_get_driver_code`
   - 返回DHT11驱动代码片段，需嵌入到用户main.c中
   - 可配置GPIO端口和引脚

2. **完整可运行程序** → `dht11_discovery_get_full_main`
   - 返回完整可编译的main.c
   - 支持display参数：oled/uart/none

### 默认配置

- 芯片：STM32F407ZG
- DHT11引脚：PG9
- UART：USART1 (PA9/PA10)
- OLED：探索版8080并口

### 示例对话

用户："读取DHT11温湿度并在OLED显示"
→ 调用 `dht11_discovery_get_full_main(display="oled")`

用户："DHT11接到PA1，串口输出"
→ 调用 `dht11_discovery_get_full_main(port="GPIOA", pin=1, display="uart")`

用户："把DHT11驱动加到现有代码里"
→ 调用 `dht11_discovery_get_driver_code()`，然后将code返回给用户