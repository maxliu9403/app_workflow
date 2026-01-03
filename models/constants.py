"""
常量定义
========

包含所有应用级别的常量配置
"""

# 节点样式配置
NODE_STYLES = {
    "Click Region": {"color": "#4CAF50", "icon": "🖱️", "label": "点击区域"},
    "Click Text": {"color": "#8BC34A", "icon": "🔤", "label": "点击文字"},
    "Input Text": {"color": "#2196F3", "icon": "⌨️", "label": "输入文本"},
    "Swipe": {"color": "#FF9800", "icon": "👆", "label": "滑动"},
    "Long Press": {"color": "#FF5722", "icon": "👇", "label": "长按"},
    "Wait Time": {"color": "#9C27B0", "icon": "⏱️", "label": "等待时间"},
    "Wait Text": {"color": "#673AB7", "icon": "⏳", "label": "等待文字"},
    "Wait Element": {"color": "#3F51B5", "icon": "🔍", "label": "等待元素"},
    "Check Text": {"color": "#00BCD4", "icon": "✓", "label": "检查文字"},
    "Check Image": {"color": "#009688", "icon": "🖼️", "label": "检查图片"},
    "Assert Exists": {"color": "#F44336", "icon": "⚠️", "label": "断言存在"},
    "Wait Until Disappear": {"color": "#E91E63", "icon": "👻", "label": "等待消失"},
}

# 支持的动作类型列表
ACTION_TYPES = list(NODE_STYLES.keys())

# 动作类型到函数名的映射
ACTION_FUNCTION_MAP = {
    "Click Region": "click_random_in_rect",
    "Input Text": "input_text_stealth",
    "Swipe": "swipe_down",
    "Check Text": "check_region_text",
    "Check Image": "find_image",
    "Wait Element": "wait_for_element",
    "Long Press": "long_press",
    "Assert Exists": "assert_element_exists",
    "Wait Until Disappear": "wait_until_disappear",
    "Click Text": "click_text",
    "Wait Text": "wait_for_text",
}

# 默认设备分辨率
DEFAULT_PHONE_WIDTH = 1080
DEFAULT_PHONE_HEIGHT = 2400

# UI 配置
CANVAS_GRID_SIZE = 30
CANVAS_BG_COLOR = "#1e1e1e"
CANVAS_GRID_COLOR = "#2a2a2a"

# 节点尺寸
NODE_WIDTH = 140
NODE_HEIGHT = 60

# 快捷变量列表
QUICK_VARIABLES = ["SKU", "Title", "Price", "Brand", "Size", "Color"]

# 自动保存文件名
AUTOSAVE_FILENAME = "autosave_flow.json"
