"""
常量定义
========

包含所有应用级别的常量配置
"""

# V5.0: 分类节点配置
ACTION_CATEGORIES = {
    "👆 Interaction": {
        "Click Region": {"icon": "🖱️", "color": "#4CAF50", "label": "点击区域"},
        "Click Text": {"icon": "🔤", "color": "#8BC34A", "label": "点击文字"},
        "Swipe": {"icon": "👆", "color": "#FF9800", "label": "滑动"},
        "Long Press": {"icon": "👇", "color": "#FF5722", "label": "长按"},
    },
    "⌨️ Input": {
        "Input Text (Base64)": {"icon": "⌨️", "color": "#2196F3", "label": "输入文本(中文)"},
        "Input Text (Native)": {"icon": "📝", "color": "#03A9F4", "label": "输入文本(英文)"},
        "Click & Check Keyboard": {"icon": "⌨️", "color": "#00BCD4", "label": "点击并验证键盘"},
    },
    "👁️ Vision": {
        "Check Text": {"icon": "✓", "color": "#009688", "label": "检查文字"},
        "Check Image": {"icon": "🖼️", "color": "#795548", "label": "检查图片"},
        "Wait Text": {"icon": "⏳", "color": "#673AB7", "label": "等待文字"},
        "Wait Element": {"icon": "🔍", "color": "#3F51B5", "label": "等待元素"},
        "Assert Exists": {"icon": "⚠️", "color": "#F44336", "label": "断言存在"},
        "Wait Until Disappear": {"icon": "👻", "color": "#E91E63", "label": "等待消失"},
    },
    "🔀 Logic": {
        "IF (Check Text)": {"icon": "❓", "color": "#9C27B0", "label": "条件(文字)"},
        "IF (Check Image)": {"icon": "❓", "color": "#7B1FA2", "label": "条件(图片)"},
        "ELSE": {"icon": "↩️", "color": "#6A1B9A", "label": "否则"},
        "END IF": {"icon": "⏹️", "color": "#4A148C", "label": "结束条件"},
    },
    "⚙️ System": {
        "Wait Time": {"icon": "⏱️", "color": "#607D8B", "label": "等待时间"},
    },
}

# 逻辑节点列表（不执行人类延迟）
LOGIC_ACTIONS = {"IF (Check Text)", "IF (Check Image)", "ELSE", "END IF"}

# 兼容 V4: 扁平化 NODE_STYLES
NODE_STYLES = {}
for category, actions in ACTION_CATEGORIES.items():
    for action_type, style in actions.items():
        NODE_STYLES[action_type] = style

# 支持的动作类型列表
ACTION_TYPES = list(NODE_STYLES.keys())

# 动作类型到函数名的映射 (V5.0 更新)
ACTION_FUNCTION_MAP = {
    "Click Region": "click_random_in_rect",
    "Click Text": "click_text",
    "Swipe": "swipe_down",
    "Long Press": "long_press",
    "Input Text (Base64)": "input_text_base64",
    "Input Text (Native)": "input_text_native",
    "Click & Check Keyboard": "click_check_keyboard",
    "Check Text": "check_text",
    "Check Image": "find_image",
    "Wait Text": "wait_for_text",
    "Wait Element": "wait_for_element",
    "Assert Exists": "assert_element_exists",
    "Wait Until Disappear": "wait_until_disappear",
    "Wait Time": "wait_time",
    "IF (Check Text)": "if_check_text",
    "IF (Check Image)": "if_check_image",
    "ELSE": "else_branch",
    "END IF": "end_if",
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

