# 🧩 V7 编辑器扩展开发标准 (Extension Model)

请将本文档发送给 AI，并要求它按照此格式生成扩展代码。

## 1. 输出格式 (One-Click Import)
AI 必须输出 **单个 JSON 代码块**，包含元数据和 Python 实现。

**命名规范 (重要)**：
- `name`: 必须使用 **中文名称** (例如 "双击屏幕")，这将直接显示在 UI 上。
- `shortcuts`: 快捷指令的说明必须使用 **中文**。

```json
{
  "name": "点击中心",
  "category": "自定义动作",
  "icon": "🎯",
  "color": "#FF9900",
  "description": "点击屏幕正中心位置",
  "shortcuts": [
      ["0.5", "延迟 0.5秒"],
      ["1.0", "延迟 1.0秒"]
  ],
  "python_code": "def action_click_center(runner, step, row_data):\n    # Access runner.device, runner.ocr_engine\n    width, height = runner.device.window_size()\n    runner.device.click(width // 2, height // 2)\n    return True"
}
```

## 2. Python 代码规范
`python_code` 字符串必须包含一个 **独立的函数**。

### 函数签名 (Signature)
```python
def your_function_name(runner, step, row_data):
    """
    Args:
        runner: WorkflowRunner 实例。使用 runner.device 进行 ADB 操作。
        step: 步骤配置字典 (包含 'params' 参数, 'coords' 坐标等)。
        row_data: Excel 变量字典。
    Returns:
        bool: 执行成功返回 True，失败返回 False。
    """
```

### 可用对象
- `runner.device`: ADB 设备对象 (adbutils)。常用方法: `click(x, y)`, `swipe(...)`, `send_keys(...)`。
- `runner.ocr_engine`: OCR 引擎 (如果已初始化)。
- `step['params']`: UI 输入的参数文本。
- `step['coords']`: 选区的坐标 `{'x1':..., 'y1':...}`。

## 3. 图标设置 (App Icon)
- **标准**: 使用 Emoji (如 "📱", "🚀") 填入 `"icon"` 字段。
- **高级**: 支持本地图片。填入图片绝对路径或相对路径 (如 `icons/myapp.png`)，系统会自动渲染为图标。

## 4. 提示词示例 (Prompt Example)
"请帮我生成一个 V7 编辑器扩展节点，名称叫 '清除缓存'。功能是运行 adb 命令 `pm clear <包名>`。参数输入包名。快捷指令包括: 'com.example.app' (标签: 示例应用)。"
