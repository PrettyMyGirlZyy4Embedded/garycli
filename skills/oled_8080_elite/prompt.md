# 正点原子STM32精英板 OLED 8080并口驱动

## 硬件连接 (正点原子STM32F103精英板)

| OLED引脚 | STM32引脚 | 说明 |
|---------|----------|------|
| D0-D7   | PC0-PC7  | 8位数据线 |
| CS      | PD6      | 片选 |
| DC(RS)  | PD3      | 数据/命令选择 |
| WR      | PG14     | 写使能 |
| RD      | PG13     | 读使能 |
| RST     | PG15     | 复位 |

## 使用场景

当用户需要在正点原子STM32精英板的OLED上显示内容时，使用此技能生成驱动代码。

支持功能：
- 字符串显示（6x8 ASCII）
- 几何图形（点、线、矩形）
- 自定义位图/图案
- 清屏/全屏操作

## 工具说明

### oled_8080_elite_get_driver_code
获取OLED驱动核心代码（初始化、显示函数等），需要嵌入到main.c中使用。

### oled_8080_elite_draw_bitmap
生成位图绘制代码，支持：
- `heart` - 爱心图案
- `smile` - 笑脸图案
- 自定义名称生成模板

### oled_8080_elite_get_full_main
获取完整可编译的main.c，demo参数：
- `string` - 字符串显示演示
- `geometry` - 几何图形演示
- `bitmap` - 位图显示演示
- `clear` - 清屏演示

## 代码示例

显示字符串：
```c
OLED_Init();
OLED_ShowString(0, 0, "Hello World!");
OLED_ShowString(0, 2, "Second Line");
```

绘制图形：
```c
OLED_DrawLine(0, 0, 127, 63);       // 对角线
OLED_DrawRect(10, 10, 50, 30, 0);   // 空心矩形
OLED_DrawRect(70, 20, 40, 25, 1);   // 实心矩形
```

坐标说明：
- X: 0-127 (128像素)
- Y: 0-7 (8页，每页8像素高度)
