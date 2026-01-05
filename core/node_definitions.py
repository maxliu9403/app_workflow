"""
V10.3: Unified Node Definition System
=====================================

Single source of truth for all workflow nodes.
Replaces fragmented definitions across constants.py and action_library.py.

Usage:
    from core.node_definitions import NODE_REGISTRY, get_node, get_categories
    
    node = get_node("Check Text")
    print(node.params)  # List of ParamField
    
    # Get all categories for UI
    categories = get_categories()
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ParamField:
    """
    参数字段定义 - 决定UI如何渲染
    
    Attributes:
        name: 内部字段名 (用于序列化)
        type: 字段类型 - "text" | "select" | "file" | "variable" | "number" | "json" | "coords"
        label: 中文UI标签
        placeholder: 输入框占位文本
        required: 是否必填
        options: type="select" 时的选项列表
        default: 默认值
        help_text: 帮助提示
    """
    name: str
    type: str  # text, select, file, variable, number, json, coords
    label: str
    placeholder: str = ""
    required: bool = True
    options: List[str] = field(default_factory=list)
    default: str = ""
    help_text: str = ""


@dataclass
class NodeDefinition:
    """
    节点完整定义 - 一处定义，处处可用
    
    Attributes:
        action_type: 动作类型标识 (如 "Click Text")
        category: 所属分类 (如 "👆 Interaction")
        icon: Emoji 图标
        color: 十六进制颜色
        label: 中文名称
        description: 完整说明
        params: 参数字段列表
        handler: 执行器函数引用 (可选，运行时绑定)
        is_logic: 是否逻辑节点 (不触发人类延迟)
        use_coords: 是否使用坐标选择
    """
    action_type: str
    category: str
    icon: str = "🔘"
    color: str = "#4CAF50"
    label: str = ""
    description: str = ""
    params: List[ParamField] = field(default_factory=list)
    handler: Optional[Callable] = None
    is_logic: bool = False
    use_coords: bool = False


# ==================== NODE REGISTRY ====================
# All node definitions in one place

NODE_REGISTRY: Dict[str, NodeDefinition] = {}


def _register_nodes():
    """Register all built-in nodes"""
    global NODE_REGISTRY
    
    # ==================== 👆 Interaction ====================
    
    NODE_REGISTRY["Click Region"] = NodeDefinition(
        action_type="Click Region",
        category="👆 Interaction",
        icon="👆", color="#4CAF50",
        label="点击区域",
        description="点击指定区域的中心位置(带随机抖动)",
        params=[],  # Uses coords only
        use_coords=True,
    )
    
    NODE_REGISTRY["Click Text"] = NodeDefinition(
        action_type="Click Text",
        category="👆 Interaction",
        icon="🔤", color="#8BC34A",
        label="点击文字",
        description="通过OCR识别并点击指定文字",
        params=[
            ParamField("target", "text", "目标文字", placeholder="要点击的文字内容"),
        ],
    )
    
    NODE_REGISTRY["Swipe"] = NodeDefinition(
        action_type="Swipe",
        category="👆 Interaction",
        icon="👆", color="#CDDC39",
        label="滑动",
        description="在指定区域内从上向下滑动",
        params=[
            ParamField("duration", "number", "持续时间(秒)", placeholder="1.0", default="1.0"),
        ],
        use_coords=True,
    )
    
    NODE_REGISTRY["Long Press"] = NodeDefinition(
        action_type="Long Press",
        category="👆 Interaction",
        icon="👇", color="#FFC107",
        label="长按",
        description="在指定位置长按",
        params=[
            ParamField("duration", "number", "长按时间(秒)", placeholder="1.0", default="1.0"),
        ],
        use_coords=True,
    )
    
    # ==================== ⌨️ Input ====================
    
    NODE_REGISTRY["Input Text (Base64)"] = NodeDefinition(
        action_type="Input Text (Base64)",
        category="⌨️ Input",
        icon="⌨️", color="#FF9800",
        label="输入文本(中文)",
        description="通过剪贴板输入文本，支持中文",
        params=[
            ParamField("text", "text", "输入内容", placeholder="要输入的文本或${变量}"),
        ],
        use_coords=True,
    )
    
    NODE_REGISTRY["Input Text (Native)"] = NodeDefinition(
        action_type="Input Text (Native)",
        category="⌨️ Input",
        icon="⌨️", color="#FF5722",
        label="输入文本(原生)",
        description="使用ADB原生输入，仅支持ASCII字符",
        params=[
            ParamField("text", "text", "输入内容", placeholder="英文/数字 或 ${变量}"),
        ],
        use_coords=True,
    )
    
    NODE_REGISTRY["Click & Check Keyboard"] = NodeDefinition(
        action_type="Click & Check Keyboard",
        category="⌨️ Input",
        icon="⌨️", color="#795548",
        label="点击并检查键盘",
        description="点击输入框并验证键盘是否弹出",
        params=[],
        use_coords=True,
    )
    
    # ==================== 👁️ Vision ====================
    
    NODE_REGISTRY["Check Text"] = NodeDefinition(
        action_type="Check Text",
        category="👁️ Vision",
        icon="🔍", color="#2196F3",
        label="检查文字",
        description="OCR检测屏幕是否包含指定文字",
        params=[
            ParamField("target", "text", "目标文字", placeholder="要检测的文字"),
            ParamField("operator", "select", "匹配方式", 
                      options=["包含", "不包含", "等于", "不等于"],
                      default="包含"),
            ParamField("capture_to", "variable", "捕获到变量", 
                      required=False, placeholder="${VarName}",
                      help_text="可选: 将匹配结果存入变量"),
        ],
    )
    
    NODE_REGISTRY["Wait Text"] = NodeDefinition(
        action_type="Wait Text",
        category="👁️ Vision",
        icon="⏳", color="#03A9F4",
        label="等待文字",
        description="等待屏幕出现指定文字",
        params=[
            ParamField("target", "text", "目标文字", placeholder="要等待的文字"),
            ParamField("timeout", "number", "超时(秒)", placeholder="30", default="30"),
        ],
    )
    
    NODE_REGISTRY["Check Image"] = NodeDefinition(
        action_type="Check Image",
        category="👁️ Vision",
        icon="🖼️", color="#00BCD4",
        label="检查图片",
        description="检测屏幕是否包含指定模板图片",
        params=[
            ParamField("template", "file", "模板图片", placeholder="选择图片文件"),
            ParamField("threshold", "number", "相似度阈值", placeholder="0.8", default="0.8"),
        ],
    )
    
    NODE_REGISTRY["Wait Element"] = NodeDefinition(
        action_type="Wait Element",
        category="👁️ Vision",
        icon="⏳", color="#009688",
        label="等待元素",
        description="等待屏幕出现指定元素(文字或图像区域)",
        params=[
            ParamField("target", "text", "目标文字/元素", placeholder="要等待的文字", required=True),
            ParamField("timeout", "number", "超时(秒)", placeholder="10", default="10"),
        ],
        use_coords=True,
    )
    
    NODE_REGISTRY["Wait Until Disappear"] = NodeDefinition(
        action_type="Wait Until Disappear",
        category="👁️ Vision",
        icon="👻", color="#E91E63",
        label="等待消失",
        description="等待屏幕上的文字消失",
        params=[
            ParamField("target", "text", "目标文字", placeholder="要等待消失的文字"),
            ParamField("timeout", "number", "超时(秒)", placeholder="30", default="30"),
        ],
    )
    
    NODE_REGISTRY["Assert Exists"] = NodeDefinition(
        action_type="Assert Exists",
        category="👁️ Vision",
        icon="✅", color="#9C27B0",
        label="断言存在",
        description="断言屏幕存在指定文字，失败则中止",
        params=[
            ParamField("target", "text", "目标文字", placeholder="必须存在的文字"),
        ],
    )
    
    # ==================== 🔀 Logic ====================
    
    NODE_REGISTRY["IF (Check Text)"] = NodeDefinition(
        action_type="IF (Check Text)",
        category="🔀 Logic",
        icon="❓", color="#9C27B0",
        label="条件(文字)",
        description="如果屏幕包含指定文字则执行分支",
        params=[
            ParamField("condition", "text", "条件文字", placeholder="要检测的文字"),
            ParamField("operator", "select", "匹配方式",
                      options=["包含", "不包含"],
                      default="包含"),
        ],
        is_logic=True,
    )
    
    NODE_REGISTRY["IF (Check Image)"] = NodeDefinition(
        action_type="IF (Check Image)",
        category="🔀 Logic",
        icon="❓", color="#7B1FA2",
        label="条件(图片)",
        description="如果屏幕包含指定图片则执行分支",
        params=[
            ParamField("template", "file", "模板图片", placeholder="选择图片文件"),
            ParamField("threshold", "number", "相似度阈值", placeholder="0.8", default="0.8"),
        ],
        is_logic=True,
    )
    
    NODE_REGISTRY["ELSE"] = NodeDefinition(
        action_type="ELSE",
        category="🔀 Logic",
        icon="↩️", color="#6A1B9A",
        label="否则",
        description="IF条件不满足时执行",
        params=[],
        is_logic=True,
    )
    
    NODE_REGISTRY["END IF"] = NodeDefinition(
        action_type="END IF",
        category="🔀 Logic",
        icon="⏹️", color="#4A148C",
        label="结束条件",
        description="结束IF条件分支",
        params=[],
        is_logic=True,
    )
    
    NODE_REGISTRY["LOOP (Count)"] = NodeDefinition(
        action_type="LOOP (Count)",
        category="🔀 Logic",
        icon="🔁", color="#7C4DFF",
        label="循环(次数)",
        description="按指定次数循环执行",
        params=[
            ParamField("count", "number", "循环次数", placeholder="3", default="3"),
        ],
        is_logic=True,
    )
    
    NODE_REGISTRY["LOOP (Until Text)"] = NodeDefinition(
        action_type="LOOP (Until Text)",
        category="🔀 Logic",
        icon="🔁", color="#651FFF",
        label="循环(直到文字)",
        description="循环直到屏幕出现指定文字",
        params=[
            ParamField("target", "text", "目标文字", placeholder="循环停止条件文字"),
        ],
        is_logic=True,
    )
    
    NODE_REGISTRY["LOOP LIST"] = NodeDefinition(
        action_type="LOOP LIST",
        category="🔀 Logic",
        icon="📜", color="#536DFE",
        label="遍历列表",
        description="遍历列表变量中的每一项",
        params=[
            ParamField("list_var", "variable", "列表变量", placeholder="${MyList}"),
            ParamField("item_var", "text", "迭代变量名", placeholder="Item", default="Item"),
        ],
        is_logic=True,
    )
    
    NODE_REGISTRY["BREAK"] = NodeDefinition(
        action_type="BREAK",
        category="🔀 Logic",
        icon="⏹️", color="#D500F9",
        label="跳出循环",
        description="立即跳出当前循环",
        params=[],
        is_logic=True,
    )
    
    NODE_REGISTRY["END LOOP"] = NodeDefinition(
        action_type="END LOOP",
        category="🔀 Logic",
        icon="🔚", color="#AA00FF",
        label="循环结束",
        description="标记循环块结束",
        params=[],
        is_logic=True,
    )
    
    NODE_REGISTRY["Set Variable"] = NodeDefinition(
        action_type="Set Variable",
        category="🔀 Logic",
        icon="📝", color="#00C853",
        label="设置变量",
        description="设置或计算变量值",
        params=[
            ParamField("key", "text", "变量名", placeholder="MyVar"),
            ParamField("value_type", "select", "值类型",
                      options=["文本", "表达式"],
                      default="文本"),
            ParamField("value", "text", "值", placeholder="固定值 或 eval: 表达式"),
        ],
        is_logic=True,
    )
    
    NODE_REGISTRY["Print Variable"] = NodeDefinition(
        action_type="Print Variable",
        category="🔀 Logic",
        icon="💬", color="#64DD17",
        label="打印变量",
        description="打印变量值到日志",
        params=[
            ParamField("var_name", "variable", "变量名", 
                      placeholder="${MyVar}", required=False,
                      help_text="留空打印所有变量"),
        ],
        is_logic=True,
    )
    
    # ==================== ⚙️ System ====================
    
    NODE_REGISTRY["Wait Time"] = NodeDefinition(
        action_type="Wait Time",
        category="⚙️ System",
        icon="⏱️", color="#607D8B",
        label="等待时间",
        description="等待指定秒数",
        params=[
            ParamField("seconds", "text", "等待时间", 
                      placeholder="秒数 或 random:1-3", default="1"),
        ],
        is_logic=True,
    )
    
    # ==================== 🌐 Network ====================
    
    NODE_REGISTRY["HTTP Request"] = NodeDefinition(
        action_type="HTTP Request",
        category="🌐 Network",
        icon="🌐", color="#3F51B5",
        label="HTTP请求",
        description="发送HTTP请求并获取响应",
        params=[
            ParamField("url", "text", "请求URL", placeholder="https://api.example.com"),
            ParamField("method", "select", "请求方法",
                      options=["GET", "POST", "PUT", "DELETE"],
                      default="GET"),
            ParamField("body", "json", "请求体(JSON)", 
                      placeholder='{"key": "value"}', required=False),
            ParamField("capture_to", "variable", "响应存入变量",
                      placeholder="${Response}", required=False),
        ],
        is_logic=True,
    )
    
    # ==================== 📊 Data Processing ====================
    
    NODE_REGISTRY["Load Excel Data"] = NodeDefinition(
        action_type="Load Excel Data",
        category="📊 Data Processing",
        icon="📊", color="#217346",
        label="读取Excel",
        description="读取Excel文件并存储为列表变量",
        params=[
            ParamField("file_path", "file", "Excel文件", placeholder="选择或输入路径"),
            ParamField("target_var", "variable", "存储到变量", placeholder="${DataRows}"),
        ],
        is_logic=True,
    )


# Initialize registry
_register_nodes()


# ==================== Helper Functions ====================

def get_node(action_type: str) -> Optional[NodeDefinition]:
    """Get node definition by action type"""
    return NODE_REGISTRY.get(action_type)


def get_nodes_by_category(category: str) -> List[NodeDefinition]:
    """Get all nodes in a category"""
    return [n for n in NODE_REGISTRY.values() if n.category == category]


def get_categories() -> List[str]:
    """Get all unique categories in order"""
    seen = set()
    result = []
    for node in NODE_REGISTRY.values():
        if node.category not in seen:
            seen.add(node.category)
            result.append(node.category)
    return result


def get_action_categories() -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Generate ACTION_CATEGORIES format for backward compatibility.
    Returns dict like: {"👆 Interaction": {"Click Text": {"icon": "🔤", "color": "#8BC34A", "label": "点击文字"}}}
    """
    result: Dict[str, Dict[str, Dict[str, str]]] = {}
    for node in NODE_REGISTRY.values():
        if node.category not in result:
            result[node.category] = {}
        result[node.category][node.action_type] = {
            "icon": node.icon,
            "color": node.color,
            "label": node.label,
        }
    return result


def get_logic_actions() -> set:
    """Get set of logic action types (no human delay)"""
    return {n.action_type for n in NODE_REGISTRY.values() if n.is_logic}
