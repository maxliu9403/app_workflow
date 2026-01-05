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
        "LOOP LIST": {"icon": "📜", "color": "#536DFE", "label": "遍历列表"},  # V10.0
        "BREAK": {"icon": "⏹️", "color": "#D500F9", "label": "跳出循环"},
        "END LOOP": {"icon": "🔚", "color": "#AA00FF", "label": "循环结束"},
        # V10.0: Variable Actions
        "Set Variable": {"icon": "📝", "color": "#00C853", "label": "设置变量"},
        "Print Variable": {"icon": "💬", "color": "#64DD17", "label": "打印变量"},
    },
    "⚙️ System": {
        "Wait Time": {"icon": "⏱️", "color": "#607D8B", "label": "等待时间"},
    },
    "🌐 Network": {
        "HTTP Request": {"icon": "🌐", "color": "#3F51B5", "label": "HTTP请求"},
    },
    # V10.2: Data Processing Category
    "📊 Data Processing": {
        "Load Excel Data": {"icon": "📊", "color": "#217346", "label": "读取Excel数据"},
    },
}

# 逻辑节点列表（不执行人类延迟）
LOGIC_ACTIONS: Set[str] = {
    "IF (Check Text)", "IF (Check Image)", "ELSE", "END IF",
    "LOOP (Count)", "LOOP (Until Text)", "LOOP LIST", "BREAK", "END LOOP",
    "Set Variable", "Print Variable"  # V10.0: Variable Actions
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

# V10.2: 动作参数模板库 - 帮助用户快速填写正确格式
# 结构: { "动作名称": [ ("模板描述", "模板内容", "占位提示"), ... ] }
ACTION_PARAM_TEMPLATES: Dict[str, List[Tuple[str, str, str]]] = {
    # === Wait Time ===
    "Wait Time": [
        ("1秒延迟", "1", "秒数 或 random:1-3"),
        ("2秒延迟", "2", ""),
        ("随机延迟", "random:1-3", "格式: random:最小-最大"),
        ("自定义随机", "random:2-5", ""),
    ],
    # === Check Text ===
    "Check Text": [
        ("包含文字", "Success", "要检测的文字"),
        ("完全匹配", "op:Equals|登录成功", "op:Equals|要匹配的文字"),
        ("不包含", "op:NotContains|错误", "op:NotContains|不含的文字"),
        ("捕获到变量", "价格: (\\d+) -> ${Price}", "正则 -> ${变量名}"),
    ],
    # === Input Text ===
    "Input Text (Base64)": [
        ("固定文本", "Hello World", "要输入的文本"),
        ("变量输入", "${Password}", "${变量名}"),
        ("中文输入", "你好世界", "支持中文"),
    ],
    "Input Text (Native)": [
        ("英文/数字", "user123", "ASCII字符"),
        ("变量输入", "${Username}", "${变量名}"),
    ],
    # === Set Variable ===
    "Set Variable": [
        ("简单赋值", "Name = John", "Key = Value"),
        ("数学计算", "Price = eval: float(${A}) * 0.8", "Key = eval: 表达式"),
        ("定义列表", "MyList = eval: [1, 2, 3]", "Key = eval: [...]"),
        ("字符串拼接", "Full = eval: ${First} + ' ' + ${Last}", ""),
    ],
    # === Print Variable ===
    "Print Variable": [
        ("打印单个", "${MyVar}", "${变量名}"),
        ("打印全部", "", "留空打印所有变量"),
    ],
    # === LOOP LIST ===
    "LOOP LIST": [
        ("遍历列表", "${ImageList} as ${Item}", "${列表} as ${项}"),
    ],
    # === LOOP (Count) ===
    "LOOP (Count)": [
        ("循环3次", "3", "次数"),
        ("循环5次", "5", ""),
        ("变量次数", "${Count}", "${变量名}"),
    ],
    # === LOOP (Until Text) ===
    "LOOP (Until Text)": [
        ("直到出现", "加载完成", "目标文字"),
        ("变量目标", "${TargetText}", "${变量名}"),
    ],
    # === Wait Text ===
    "Wait Text": [
        ("等待文字", "加载中", "要等待的文字"),
        ("超时设置", "Home|timeout=30", "文字|timeout=秒数"),
    ],
    # === Click Text ===
    "Click Text": [
        ("点击按钮", "确定", "要点击的文字"),
        ("变量文字", "${ButtonText}", "${变量名}"),
    ],
    # === HTTP Request ===
    "HTTP Request": [
        ("GET请求", '{"url": "https://api.example.com", "method": "GET"}', "JSON参数"),
        ("POST请求", '{"url": "https://api.example.com", "method": "POST", "body": {"key": "${Value}"}}', ""),
    ],
    # === IF (Check Text) ===
    "IF (Check Text)": [
        ("如果包含", "登录成功", "条件文字"),
        ("如果不含", "op:NotContains|错误", "op:NotContains|文字"),
    ],
    # === Swipe ===
    "Swipe": [
        ("正常滑动", "1.0", "持续时间(秒)"),
        ("快速滑动", "0.3", ""),
        ("慢速滑动", "2.0", ""),
    ],
    # === V10.2: Load Excel Data ===
    "Load Excel Data": [
        ("读取本地文件", "D:\\data.xlsx -> ${ExcelRows}", "路径 -> ${变量名}"),
        ("读取相对路径", "data/products.xlsx -> ${Products}", "相对路径 -> ${变量名}"),
        ("使用变量路径", "${ProjectDir}/config.xlsx -> ${Config}", "${路径变量} -> ${变量名}"),
    ],
}

# V10.2: 动作占位提示文本
ACTION_PLACEHOLDERS: Dict[str, str] = {
    "Wait Time": "秒数 (如: 2) 或 random:最小-最大",
    "Check Text": "文字 或 op:操作符|文字 或 正则 -> ${变量}",
    "Input Text (Base64)": "要输入的文本 (支持中文)",
    "Input Text (Native)": "英文/数字文本 或 ${变量}",
    "Set Variable": "Key = Value 或 Key = eval: 表达式",
    "Print Variable": "${变量名} 或留空打印全部",
    "LOOP LIST": "${列表变量} as ${迭代项}",
    "LOOP (Count)": "循环次数",
    "LOOP (Until Text)": "目标文字 (出现后停止)",
    "Wait Text": "要等待出现的文字",
    "Click Text": "要点击的文字内容",
    "Click Region": "无需参数 (使用坐标)",
    "Swipe": "滑动持续时间(秒)",
    "Long Press": "长按持续时间(秒)",
    "HTTP Request": "JSON格式: {url, method, body...}",
    "IF (Check Text)": "条件文字 或 op:操作符|文字",
    "ELSE": "无需参数",
    "END IF": "无需参数",
    "BREAK": "无需参数",
    "END LOOP": "无需参数",
    # V10.2: Data Processing
    "Load Excel Data": "Excel路径 -> ${变量名}",
}
