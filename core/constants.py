"""
Core Constants
===============
Action categories, node styles, and parameter shortcuts for workflow nodes.
"""

from typing import Dict, List, Set, Tuple, Any

# V5.0: 分类节点配置
ACTION_CATEGORIES: Dict[str, Dict[str, Dict[str, str]]] = {
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
        # V6.0: LOOP 节点
        "LOOP (Count)": {"icon": "🔁", "color": "#7C4DFF", "label": "循环(次数)"},
        "LOOP (Until Text)": {"icon": "🔁", "color": "#651FFF", "label": "循环(直到文字)"},
        "BREAK": {"icon": "⏹️", "color": "#D500F9", "label": "跳出循环"},
        "END LOOP": {"icon": "🔚", "color": "#AA00FF", "label": "循环结束"},
    },
    "⚙️ System": {
        "Wait Time": {"icon": "⏱️", "color": "#607D8B", "label": "等待时间"},
    },
    "🌐 Network": {
        "HTTP Request": {"icon": "🌐", "color": "#3F51B5", "label": "HTTP请求"},
    },
}

# 逻辑节点列表（不执行人类延迟）
LOGIC_ACTIONS: Set[str] = {
    "IF (Check Text)", "IF (Check Image)", "ELSE", "END IF",
    "LOOP (Count)", "LOOP (Until Text)", "BREAK", "END LOOP"
}

# 兼容 V4: 扁平化 NODE_STYLES
NODE_STYLES: Dict[str, Dict[str, str]] = {}
for _cat, _actions in ACTION_CATEGORIES.items():
    for _action_type, _style in _actions.items():
        NODE_STYLES[_action_type] = _style

# V7.6: 动作参数快捷键配置 (Value, Label/Comment)
NODE_PARAM_SHORTCUTS: Dict[str, List[Tuple[str, str]]] = {
    "Wait Time": [
        ("1.0", "等待 1 秒"), ("2.0", "等待 2 秒"), ("3.0", "等待 3 秒"),
        ("5.0", "等待 5 秒"), ("random(2,5)", "随机 2-5 秒")
    ],
    "Input Text (Base64)": [
        ("Hello", "输入 Hello"), ("Test", "输入测试文本"), 
        ("Username", "输入用户名"), ("Password", "输入密码"),
        ("{clipboard}", "粘贴剪贴板")
    ],
    "Input Text (Native)": [
        ("123", "输入数字"), ("abc", "输入字母")
    ],
    "Key Event": [
        ("3", "Home键 (3)"), ("4", "返回键 (4)"), ("66", "回车键 (66)"),
        ("26", "电源键 (26)"), ("61", "Tab键 (61)"), ("67", "退格键 (67)")
    ],
    "Click Text": [
        ("Login", "登录"), ("Confirm", "确认"), ("Cancel", "取消"),
        ("Next", "下一步"), ("Skip", "跳过"), ("Allow", "允许")
    ],
    "Wait Text": [
        ("Home", "首页"), ("Loaded", "加载完毕"), ("Success", "成功")
    ],
    "IF (Check Text)": [
        ("Error", "错误提示"), ("Success", "成功提示"), ("Fail", "失败提示")
    ],
    "Loop (Count)": [
        ("3", "循环3次"), ("5", "循环5次"), ("10", "循环10次")
    ],
    "Swipe": [
        ("0.5", "快滑 (0.5s)"), ("1.0", "标准 (1.0s)"), ("2.0", "慢滑 (2.0s)")
    ],
    "Long Press": [
         ("1.0", "长按1秒"), ("3.0", "长按3秒")
    ],
    "Wait Element": [
        ("timeout=10", "超时10秒"), ("timeout=30", "超时30秒")
    ],
    "Check Image": [
        ("0.8", "相似度0.8"), ("0.9", "相似度0.9"), ("0.95", "相似度0.95")
    ]
}
