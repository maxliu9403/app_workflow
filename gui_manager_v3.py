import re
import time
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import customtkinter as ctk
import numpy as np
import yaml
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk


import cv2
from adbutils import adb
from adbutils.errors import AdbError
from extension_manager import ExtensionManager


@dataclass
class RoiPct:
    x1: float
    y1: float
    x2: float
    y2: float

    def normalized(self) -> "RoiPct":
        x1 = float(min(self.x1, self.x2))
        x2 = float(max(self.x1, self.x2))
        y1 = float(min(self.y1, self.y2))
        y2 = float(max(self.y1, self.y2))
        return RoiPct(x1=x1, y1=y1, x2=x2, y2=y2)

    def clipped(self) -> "RoiPct":
        x1 = float(max(0.0, min(1.0, self.x1)))
        x2 = float(max(0.0, min(1.0, self.x2)))
        y1 = float(max(0.0, min(1.0, self.y1)))
        y2 = float(max(0.0, min(1.0, self.y2)))
        return RoiPct(x1=x1, y1=y1, x2=x2, y2=y2)

    def center(self) -> Tuple[float, float]:
        r = self.normalized()
        return (float((r.x1 + r.x2) / 2.0), float((r.y1 + r.y2) / 2.0))


@dataclass
class WorkflowNode:
    """工作流节点数据结构"""
    id: str                                # 唯一标识
    action_type: str                       # 动作类型
    step_name: str = ""                    # 步骤名称
    params: str = ""                       # 参数
    context: str = ""                      # 上下文备注
    coords: Dict[str, float] = field(default_factory=lambda: {"x1": 0, "y1": 0, "x2": 0, "y2": 0})
    canvas_x: int = 100                    # 画布 X 位置
    canvas_y: int = 100                    # 画布 Y 位置
    retry_count: int = 0                   # 重试次数
    is_optional: bool = False              # 是否可选步骤
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于 JSON 导出）"""
        return {
            "step_name": self.step_name,
            "action_type": self.action_type,
            "params": self.params,
            "context": self.context,
            "coords": self.coords,
            "retry_count": self.retry_count,
            "is_optional": self.is_optional,
        }


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
        # V6.0: LOOP 节点
        "LOOP (Count)": {"icon": "🔁", "color": "#7C4DFF", "label": "循环(次数)"},
        "LOOP (Until Text)": {"icon": "🔁", "color": "#651FFF", "label": "循环(直到文字)"},
        "BREAK": {"icon": "⏹️", "color": "#D500F9", "label": "跳出循环"},
        "END LOOP": {"icon": "🔚", "color": "#AA00FF", "label": "循环结束"},
    },
    "⚙️ System": {
        "Wait Time": {"icon": "⏱️", "color": "#607D8B", "label": "等待时间"},
    },
}

# 逻辑节点列表（不执行人类延迟）
LOGIC_ACTIONS = {
    "IF (Check Text)", "IF (Check Image)", "ELSE", "END IF",
    "LOOP (Count)", "LOOP (Until Text)", "BREAK", "END LOOP"
}

# 兼容 V4: 扁平化 NODE_STYLES
NODE_STYLES = {}
for _cat, _actions in ACTION_CATEGORIES.items():
    for _action_type, _style in _actions.items():
        NODE_STYLES[_action_type] = _style

# V7.6: 动作参数快捷键配置 (Value, Label/Comment)
NODE_PARAM_SHORTCUTS = {
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


class VintedAutomationConsole:
    BASE_WIDTH = 1080
    BASE_HEIGHT = 2400

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Vinted 自动化控制台")
        self.root.geometry("1700x980")

        self.selected_serial_var = ctk.StringVar(value="")
        self.device: Any = None
        self.phone_width: int = 0
        self.phone_height: int = 0

        self.screenshot_pil: Optional[Image.Image] = None
        self.screenshot_bgr: Optional[np.ndarray] = None
        self.tk_photo: Optional[ImageTk.PhotoImage] = None

        self.canvas_scale: float = 1.0
        self.canvas_offset_x: int = 0
        self.canvas_offset_y: int = 0
        self.display_width: int = 0
        self.display_height: int = 0

        self.rect_start_canvas: Optional[Tuple[int, int]] = None
        self.rect_id: Optional[int] = None
        self.center_id: Optional[int] = None
        self.template_rect_id: Optional[int] = None

        self.ocr_engine: Any = None

        self.template_path: Optional[Path] = None
        self.template_bgr: Optional[np.ndarray] = None
        self.template_match_roi: Optional[RoiPct] = None

        self.yaml_data: Dict[str, Any] = {}
        self.yaml_path: Path = self._resolve_default_yaml_path()
        self.tree_item_map: Dict[str, Tuple[Any, Union[str, int], str]] = {}

        self.entry_update_job: Optional[str] = None
        self._building_ui: bool = False


        self.template_threshold_var = ctk.StringVar(value="0.80")
        self.template_scope_var = ctk.StringVar(value="全屏")
        self.template_sync_var = ctk.BooleanVar(value=True)
        self.template_scale_min_var = ctk.StringVar(value="0.70")
        self.template_scale_max_var = ctk.StringVar(value="1.30")
        self.template_scale_step_var = ctk.StringVar(value="0.05")
        self.template_preprocess_var = ctk.StringVar(value="灰度")
        self.ocr_target_text_var = ctk.StringVar(value="")

        # 步骤生成器相关变量
        self.gen_step_var = ctk.StringVar(value="Step 1")
        self.gen_category_var = ctk.StringVar(value="👆 Interaction")  # V5.0: 类别选择
        self.gen_action_var = ctk.StringVar(value="Click Region")  # V5.0: 动作选择
        self.gen_operator_var = ctk.StringVar(value="包含 (Contains)") # V7.2: IF判断条件
        self.gen_param_var = ctk.StringVar(value="")
        self.gen_context_var = ctk.StringVar(value="")
        self.gen_x1_var = ctk.StringVar(value="0.000")
        self.gen_y1_var = ctk.StringVar(value="0.000")
        self.gen_x2_var = ctk.StringVar(value="0.000")
        self.gen_y2_var = ctk.StringVar(value="0.000")
        self.gen_canvas: Optional[ctk.CTkCanvas] = None
        self.gen_screenshot_pil: Optional[Image.Image] = None
        self.gen_tk_photo: Optional[ImageTk.PhotoImage] = None
        self.gen_rect_id: Optional[int] = None
        self.gen_rect_start: Optional[Tuple[int, int]] = None
        self.gen_canvas_scale: float = 1.0
        self.gen_canvas_offset_x: int = 0
        self.gen_canvas_offset_y: int = 0
        self.gen_display_width: int = 0
        self.gen_display_height: int = 0
        self.excel_path: Optional[str] = None  # Custom Excel Path
        self.orch_node_images: Dict[str, Any] = {} # Canvas Icon Cache

        # V3.1: 步骤队列系统
        self.gen_step_queue: List[Dict[str, Any]] = []  # 步骤队列
        self.gen_click_marker_id: Optional[int] = None  # 点击可视化标记ID
        self.gen_click_marker_ids: List[int] = []  # 多个标记ID（十字星）

        # V3.2: 编辑模式
        self.gen_edit_mode: bool = False  # 是否处于编辑模式
        self.gen_edit_index: int = -1  # 当前编辑的步骤索引

        # OCR可视化相关
        self.ocr_detections: List[Dict[str, Any]] = []  # OCR识别结果列表
        self.ocr_rect_ids: List[int] = []  # 画布上的OCR矩形ID列表
        self.ocr_text_ids: List[int] = []  # 画布上的OCR文字标签ID列表
        
        # 偏移计算器相关
        self.offset_calculator_mode: bool = False  # 是否处于偏移计算模式
        self.anchor_center: Optional[Tuple[float, float]] = None  # 锚点中心（百分比坐标）
        self.anchor_text_content: str = ""  # 锚点文字内容
        self.target_roi: Optional[RoiPct] = None  # 目标区域（手动框选）
        self.anchor_rect_id: Optional[int] = None  # 锚点标记矩形ID
        self.anchor_text_id: Optional[int] = None  # 锚点标记文字ID
        self.target_rect_id: Optional[int] = None  # 目标区域矩形ID
        self.target_text_id: Optional[int] = None  # 目标区域文字ID
        self.target_line_id: Optional[int] = None  # 连接线ID

        # V4.0: 流程编排器相关变量
        self.orch_nodes: Dict[str, WorkflowNode] = {}  # 节点字典 {id: WorkflowNode}
        self.orch_connections: List[Tuple[str, str]] = []  # 连接列表 [(from_id, to_id)]
        self.orch_selected_node: Optional[str] = None  # 当前选中的节点ID
        self.orch_drag_data: Optional[Dict[str, Any]] = None  # 拖拽数据
        self.orch_drag_node_id: Optional[str] = None  # 正在拖拽的节点ID
        self.orch_drag_offset: Tuple[int, int] = (0, 0)  # 拖拽偏移
        self.orch_connecting_from: Optional[str] = None  # 正在创建连接的源节点
        self.orch_temp_line_id: Optional[int] = None  # 临时连接线ID
        self.orch_node_canvas_items: Dict[str, List[int]] = {}  # 节点的画布元素 {node_id: [item_ids]}
        self.orch_connection_lines: Dict[Tuple[str, str], int] = {}  # 连接线 {(from, to): line_id}
        self.orch_manual_connect_from: Optional[str] = None  # 手动连接模式的源节点
        
        # 编排器属性面板变量
        self.orch_prop_name_var = ctk.StringVar(value="")
        self.orch_prop_action_var = ctk.StringVar(value="Click Region")
        self.orch_prop_params_var = ctk.StringVar(value="")
        self.orch_prop_retry_var = ctk.StringVar(value="0")
        self.orch_prop_optional_var = ctk.BooleanVar(value=False)
        self.orch_prop_x1_var = ctk.StringVar(value="0.0")
        self.orch_prop_y1_var = ctk.StringVar(value="0.0")
        self.orch_prop_x2_var = ctk.StringVar(value="0.0")
        self.orch_prop_y2_var = ctk.StringVar(value="0.0")

        self.gen_y2_var = ctk.StringVar(value="0")

        self.gen_queue_var = ctk.StringVar()
        
        # V7.0: 绑定变量追踪，实现 Inspector -> Node 的实时更新
        self._is_updating_ui = False
        
        self.gen_step_var.trace_add("write", self._on_inspector_change)
        self.gen_action_var.trace_add("write", self._on_inspector_change)
        self.gen_operator_var.trace_add("write", self._on_inspector_change)
        self.gen_param_var.trace_add("write", self._on_inspector_change)
        self.gen_x1_var.trace_add("write", self._on_inspector_change)
        self.gen_y1_var.trace_add("write", self._on_inspector_change)
        self.gen_x2_var.trace_add("write", self._on_inspector_change)
        self.gen_y2_var.trace_add("write", self._on_inspector_change)
        # Category change is handled by command callback which updates action list
        
        # V7.9: Extension Manager
        self.ext_manager = ExtensionManager()
        self._load_custom_nodes()

        self._build_ui()
        self.refresh_device_list()
        self.load_yaml()
        

        
        # V3.3: 启动时自动恢复
        self.root.after(500, self._gen_autoload)

    def _load_custom_nodes(self):
        """V7.9: Load Custom Extensions"""
        nodes = self.ext_manager.load_nodes_metadata()
        for node in nodes:
            cat = node.get("category", "Custom")
            name = node.get("name")
            icon = node.get("icon", "🧩")
            color = node.get("color", "#555")
            shortcuts = node.get("shortcuts")
            
            if cat not in ACTION_CATEGORIES:
                ACTION_CATEGORIES[cat] = {}
            
            ACTION_CATEGORIES[cat][name] = {"icon": icon, "color": color}
            
            # V7.9: Sync NODE_STYLES for Canvas Drawing
            NODE_STYLES[name] = {"icon": icon, "color": color, "label": name}
            
            if shortcuts:
                NODE_PARAM_SHORTCUTS[name] = shortcuts

    def _update_inspector_visibility(self):
        """根据动作类型显示/隐藏参数面板，并更新标签"""
        action_type = self.gen_action_var.get()
        
        # 定义不需要坐标的动作集合 (黑名单模式)
        no_coord_actions = {
            "Input Text", "Input Text (Base64)", "Input Text (Native)", 
            "Key Event", "Click Check Keyboard", "ADB Key",
            "Wait", "Sleep", 
            "Loop (Count)", "BREAK", "END LOOP", "ELSE", "END IF"
        }
        
        # 1. 控制坐标区域显示
        if hasattr(self, 'gen_coord_frame'):
            # 如果动作类型包含 "Input" 或 "Key"，或者在黑名单中 -> 隐藏
            # 但用户特指 Input Text 和 ADB Key 不需要，其他交互都需要
            is_no_coord = False
            for na in no_coord_actions:
                if na in action_type:
                    is_no_coord = True
                    break
            
            if is_no_coord:
                self.gen_coord_frame.grid_remove()
            else:
                self.gen_coord_frame.grid()
                
        # 3. 更新参数标签 (略)
        
        # 4. 更新快捷参数 (V7.6)
        self._update_param_shortcuts(action_type)

    def _update_param_shortcuts(self, action_type: str) -> None:
        """V7.6: 根据动作类型刷新快捷参数按钮"""
        if not hasattr(self, 'gen_shortcut_frame'):
            return
            
        # 清除旧按钮
        for widget in self.gen_shortcut_frame.winfo_children():
            widget.destroy()

        # 查找配置
        shortcuts = NODE_PARAM_SHORTCUTS.get(action_type, [])
        if not shortcuts:
            # 尝试 default fallback
            shortcuts = NODE_PARAM_SHORTCUTS.get("default", [])
        
        # Grid 配置 (2列)
        self.gen_shortcut_frame.grid_columnconfigure((0, 1), weight=1)
        
        # 创建新按钮
        for i, (val, label) in enumerate(shortcuts):
            # 使用闭包绑定值
            def set_val(v=val):
                self.gen_param_var.set(v)
            
            # 显示格式: 中文注释 (真实值)
            display_val = val
            if len(display_val) > 12:
                display_val = display_val[:10] + ".."
            
            full_text = f"{label} ({display_val})"
            
            btn = ctk.CTkButton(
                self.gen_shortcut_frame,
                text=full_text,
                height=28,
                fg_color="#444",
                hover_color="#555",
                font=ctk.CTkFont(size=11),
                command=set_val
            )
            # 2列布局
            btn.grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")

        # 2. 控制判断条件显示 (仅 IF 节点)
        if hasattr(self, 'gen_operator_combo'):
            if action_type.startswith("IF"):
                self.gen_operator_combo.grid()
                if hasattr(self, 'gen_operator_label'):
                    self.gen_operator_label.grid()
            else:
                self.gen_operator_combo.grid_remove()
                if hasattr(self, 'gen_operator_label'):
                    self.gen_operator_label.grid_remove()

        # 3. 动态更新参数标签
        param_label_text = "动作参数："
        if "Wait" in action_type or "Sleep" in action_type:
            param_label_text = "等待时间 (秒)："
        elif "Loop (Count)" in action_type:
            param_label_text = "循环次数："
        elif "Input" in action_type:
            param_label_text = "输入内容："
        elif "Click Text" in action_type or "Check Text" in action_type:
            param_label_text = "目标文本："
        elif "Check Image" in action_type:
            param_label_text = "模板文件名："

        if hasattr(self, 'gen_param_label'):
            self.gen_param_label.configure(text=param_label_text)

        # V7.9: Toggle Image Browse Button
        if hasattr(self, 'gen_param_browse_btn'):
            if "Image" in action_type:
                self.gen_param_browse_btn.grid()
            else:
                self.gen_param_browse_btn.grid_remove()

    def _on_inspector_change(self, *args):
        """Inspector 变量改变时更新选中节点"""
        # 更新可见性 (总是执行)
        self._update_inspector_visibility()

        if self._is_updating_ui:
            return
            
        if not self.orch_selected_node:
            return
            
        node = self.orch_nodes.get(self.orch_selected_node)
        if not node:
            return
            
        # 更新节点数据
        try:
            node.step_name = self.gen_step_var.get()
            node.action_type = self.gen_action_var.get()
            
            # V7.2: IF 节点参数编码 (op:Contains|value)
            raw_param = self.gen_param_var.get()
            if node.action_type.startswith("IF"):
                op_val = self.gen_operator_var.get()
                op_map = {
                    "包含 (Contains)": "Contains",
                    "不包含 (Not Contains)": "NotContains",
                    "等于 (Equals)": "Equals",
                    "不等于 (Not Equals)": "NotEquals"
                }
                simple_op = op_map.get(op_val, "Contains")
                node.params = f"op:{simple_op}|{raw_param}"
            else:
                node.params = raw_param
            
            # 更新坐标
            try:
                node.coords = {
                    "x1": float(self.gen_x1_var.get() or 0),
                    "y1": float(self.gen_y1_var.get() or 0),
                    "x2": float(self.gen_x2_var.get() or 0),
                    "y2": float(self.gen_y2_var.get() or 0)
                }
            except ValueError:
                pass # 忽略无效数字输入
            
            # 获取 AI 上下文 (Textbox 需要特殊处理)
            if hasattr(self, 'gen_context_text'):
                # 暂时存入 params 的 _context 字段用于持久化
                # 这里可能需要更完善的 params 结构，目前先简化
                pass

            # 重绘节点
            self._orch_draw_node(node)
            self._orch_refresh_listbox()
            
        except Exception as e:
            print(f"Error updating node: {e}")

    def _on_inspector_text_change(self, event=None):
        """Inspector 文本框(AI Context)改变时更新选中节点"""
        if self._is_updating_ui:
            return
            
        if not self.orch_selected_node:
            return
            
        node = self.orch_nodes.get(self.orch_selected_node)
        if hasattr(self, 'gen_context_text'):
            new_context = self.gen_context_text.get("1.0", tk.END).strip()
            if node.context != new_context:
                node.context = new_context
                # 不需要重绘，因为 context 不显示在节点上
    
    def _resolve_default_yaml_path(self) -> Path:
        preferred = Path(r"d:\Carousell_Auto\config\coordinates.yaml")
        if preferred.exists():
            return preferred

        here = Path(__file__).resolve()
        candidates = [
            here.parent.parent / "config" / "coordinates.yaml",
            here.parent / "coordinates.yaml",
            here.parent.parent / "coordinates.yaml",
        ]
        for p in candidates:
            if p.exists():
                return p
        return preferred

    def _build_ui(self) -> None:
        self._building_ui = True

        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(self.root)
        top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        top_bar.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(
            top_bar,
            text="设备：",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")

        self.device_combo = ctk.CTkComboBox(
            top_bar,
            width=260,
            variable=self.selected_serial_var,
            values=[],
            command=lambda _v: self.on_device_selected(),
        )
        self.device_combo.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="w")

        self.btn_refresh_devices = ctk.CTkButton(
            top_bar,
            text="刷新设备",
            width=110,
            command=self.refresh_device_list,
        )
        self.btn_refresh_devices.grid(row=0, column=2, padx=6, pady=10, sticky="w")

        self.btn_connect = ctk.CTkButton(
            top_bar,
            text="连接",
            width=90,
            command=self.connect_selected_device,
        )
        self.btn_connect.grid(row=0, column=3, padx=6, pady=10, sticky="w")

        self.btn_disconnect = ctk.CTkButton(
            top_bar,
            text="断开",
            width=90,
            fg_color="#555555",
            command=self.disconnect_device,
        )
        self.btn_disconnect.grid(row=0, column=4, padx=6, pady=10, sticky="w")

        self.status_label = ctk.CTkLabel(
            top_bar,
            text="状态：未连接",
            text_color="#aaaaaa",
        )
        self.status_label.grid(row=0, column=5, padx=10, pady=10, sticky="w")

        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.tab_live = self.tabs.add("实时调试")
        self.tab_designer = self.tabs.add("🛠️ 工作流设计器")  # V6.0: 统一设计器

        self._build_live_tab()
        self._build_designer_tab()  # V6.0: 合并 Generator + Orchestrator

        self._building_ui = False

    def _build_live_tab(self) -> None:
        # 新布局：左-中-右三列布局
        # 左：功能控制面板（滚动区域）
        # 中：画布区域
        # 右：日志控制台
        self.tab_live.grid_rowconfigure(0, weight=1)
        self.tab_live.grid_columnconfigure(0, weight=2)   # 左：功能面板
        self.tab_live.grid_columnconfigure(1, weight=5)   # 中：画布
        self.tab_live.grid_columnconfigure(2, weight=2)   # 右：日志
        
        # 左侧：功能控制面板（滚动区域）
        control_panel = ctk.CTkScrollableFrame(self.tab_live)
        control_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        control_panel.grid_columnconfigure(0, weight=1)
        
        # 中间：画布区域
        canvas_container = ctk.CTkFrame(self.tab_live)
        canvas_container.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        canvas_container.grid_rowconfigure(0, weight=1)
        canvas_container.grid_columnconfigure(0, weight=1)
        
        # 右侧：日志控制台
        log_container = ctk.CTkFrame(self.tab_live)
        log_container.grid(row=0, column=2, sticky="nsew", padx=(5, 10), pady=10)
        log_container.grid_rowconfigure(1, weight=1)
        log_container.grid_columnconfigure(0, weight=1)
        
        # 在控制面板中构建控件（水平排列，紧凑布局）
        coord_frame = ctk.CTkFrame(control_panel)
        coord_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        coord_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            coord_frame,
            text="坐标管理（百分比 0.0 - 1.0）",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 8))

        self.x1_var = ctk.StringVar(value="0.000")
        self.y1_var = ctk.StringVar(value="0.000")
        self.x2_var = ctk.StringVar(value="0.000")
        self.y2_var = ctk.StringVar(value="0.000")

        self._make_labeled_entry(coord_frame, "左上X", self.x1_var, 1, 0)
        self._make_labeled_entry(coord_frame, "左上Y", self.y1_var, 1, 2)
        self._make_labeled_entry(coord_frame, "右下X", self.x2_var, 2, 0)
        self._make_labeled_entry(coord_frame, "右下Y", self.y2_var, 2, 2)

        self.paste_var = ctk.StringVar(value="")
        ctk.CTkLabel(coord_frame, text="快速粘贴：").grid(
            row=3, column=0, sticky="w", padx=10, pady=(10, 6)
        )
        self.paste_entry = ctk.CTkEntry(
            coord_frame,
            textvariable=self.paste_var,
            placeholder_text="例如：(0.1, 0.2) 到 (0.3, 0.4)",
        )
        self.paste_entry.grid(row=3, column=1, columnspan=3, sticky="ew", padx=10, pady=(10, 6))
        self.paste_entry.bind("<Return>", lambda _e: self.parse_quick_paste())

        self.btn_parse = ctk.CTkButton(
            coord_frame,
            text="解析并填充",
            command=self.parse_quick_paste,
        )
        self.btn_parse.grid(row=4, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))

        self.btn_copy_coords = ctk.CTkButton(
            coord_frame,
            text="复制当前坐标",
            fg_color="#555555",
            command=self.copy_current_coords,
        )
        self.btn_copy_coords.grid(row=5, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 5))
        
        # 一键复制功能区域
        quick_copy_frame = ctk.CTkFrame(coord_frame, fg_color="transparent")
        quick_copy_frame.grid(row=6, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))
        quick_copy_frame.grid_columnconfigure((0, 1), weight=1)
        
        self.btn_quick_copy = ctk.CTkButton(
            quick_copy_frame,
            text="📋 一键复制坐标",
            fg_color="#ff6b35",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.quick_copy_coordinates,
        )
        self.btn_quick_copy.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        self.btn_yaml_copy = ctk.CTkButton(
            quick_copy_frame,
            text="📝 复制YAML格式",
            fg_color="#4ecdc4",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.copy_yaml_format,
        )
        self.btn_yaml_copy.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        action_frame = ctk.CTkFrame(control_panel)
        action_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        action_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            action_frame,
            text="动作测试",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))

        self.btn_shot = ctk.CTkButton(
            action_frame,
            text="获取截图",
            command=self.refresh_screenshot,
        )
        self.btn_shot.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.btn_test_click = ctk.CTkButton(
            action_frame,
            text="测试点击（中心点）",
            fg_color="#8b4513",
            command=self.test_click_center,
        )
        self.btn_test_click.grid(row=1, column=1, sticky="ew", padx=10, pady=(0, 10))

        self.btn_test_ocr = ctk.CTkButton(
            action_frame,
            text="测试文字识别（区域）",
            fg_color="#2d7a3e",
            command=self.test_ocr_roi,
        )
        self.btn_test_ocr.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        text_tool_frame = ctk.CTkFrame(control_panel)
        text_tool_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        
        # 添加偏移计算器按钮
        offset_row = ctk.CTkFrame(text_tool_frame, fg_color="transparent")
        offset_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        offset_row.grid_columnconfigure((0, 1), weight=1)
        
        self.btn_offset_calc = ctk.CTkButton(
            offset_row,
            text="🎯 偏移计算器",
            fg_color="#ff00ff",
            command=self.start_offset_calculator,
        )
        self.btn_offset_calc.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        
        self.btn_clear_offset = ctk.CTkButton(
            offset_row,
            text="清除偏移标记",
            fg_color="#555555",
            command=self.clear_offset_calculator,
        )
        self.btn_clear_offset.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        text_tool_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            text_tool_frame,
            text="文字工具",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))

        self.btn_extract_text = ctk.CTkButton(
            text_tool_frame,
            text="提取区域文字（复制）",
            fg_color="#6a5acd",
            command=self.extract_roi_text_copy,
        )
        self.btn_extract_text.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.btn_extract_text_show = ctk.CTkButton(
            text_tool_frame,
            text="提取区域文字（显示）",
            fg_color="#5b728c",
            command=self.extract_roi_text_show,
        )
        self.btn_extract_text_show.grid(row=1, column=1, sticky="ew", padx=10, pady=(0, 10))

        match_row = ctk.CTkFrame(text_tool_frame, fg_color="transparent")
        match_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        match_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_match_text = ctk.CTkButton(
            match_row,
            text="文字匹配",
            fg_color="#ff9500",
            command=self.match_text_in_roi,
        )
        self.btn_match_text.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_clear_ocr = ctk.CTkButton(
            match_row,
            text="清除OCR框",
            fg_color="#555555",
            command=self.clear_ocr_detections,
        )
        self.btn_clear_ocr.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        self.ocr_target_entry = ctk.CTkEntry(
            match_row,
            textvariable=self.ocr_target_text_var,
            placeholder_text="输入要匹配的文字",
        )
        self.ocr_target_entry.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        template_frame = ctk.CTkFrame(control_panel)
        template_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
        template_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            template_frame,
            text="模板匹配",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 8))

        ctk.CTkLabel(template_frame, text="模板：").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        self.template_path_label = ctk.CTkLabel(template_frame, text="未选择", text_color="#aaaaaa")
        self.template_path_label.grid(row=1, column=1, sticky="ew", padx=(0, 6), pady=6)
        self.btn_choose_template = ctk.CTkButton(
            template_frame,
            text="选择",
            width=70,
            command=self.choose_template_image,
        )
        self.btn_choose_template.grid(row=1, column=2, sticky="e", padx=10, pady=6)

        ctk.CTkLabel(template_frame, text="阈值：").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        self.template_threshold_entry = ctk.CTkEntry(template_frame, textvariable=self.template_threshold_var)
        self.template_threshold_entry.grid(row=2, column=1, sticky="ew", padx=(0, 6), pady=6)

        self.template_scope_menu = ctk.CTkOptionMenu(
            template_frame,
            variable=self.template_scope_var,
            values=["全屏", "仅在当前区域"],
        )
        self.template_scope_menu.grid(row=2, column=2, sticky="e", padx=10, pady=6)

        ctk.CTkLabel(template_frame, text="缩放：").grid(row=3, column=0, sticky="w", padx=10, pady=6)
        scale_row = ctk.CTkFrame(template_frame, fg_color="transparent")
        scale_row.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=6)
        scale_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.template_scale_min_entry = ctk.CTkEntry(scale_row, textvariable=self.template_scale_min_var)
        self.template_scale_min_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.template_scale_max_entry = ctk.CTkEntry(scale_row, textvariable=self.template_scale_max_var)
        self.template_scale_max_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.template_scale_step_entry = ctk.CTkEntry(scale_row, textvariable=self.template_scale_step_var)
        self.template_scale_step_entry.grid(row=0, column=2, sticky="ew")

        ctk.CTkLabel(template_frame, text="预处理：").grid(row=4, column=0, sticky="w", padx=10, pady=(0, 6))
        self.template_preprocess_menu = ctk.CTkOptionMenu(
            template_frame,
            variable=self.template_preprocess_var,
            values=["灰度", "边缘", "二值"],
        )
        self.template_preprocess_menu.grid(row=4, column=1, sticky="ew", padx=(0, 6), pady=(0, 6))

        self.template_sync_checkbox = ctk.CTkCheckBox(
            template_frame,
            text="匹配后同步到坐标",
            variable=self.template_sync_var,
        )
        self.template_sync_checkbox.grid(row=5, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))

        self.btn_run_template = ctk.CTkButton(
            template_frame,
            text="开始匹配",
            fg_color="#ff6347",
            command=self.run_template_match,
        )
        self.btn_run_template.grid(row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        self.btn_clear_template = ctk.CTkButton(
            template_frame,
            text="清除匹配框",
            fg_color="#555555",
            command=self.clear_template_match,
        )
        self.btn_clear_template.grid(row=6, column=2, sticky="ew", padx=10, pady=(0, 10))

        yaml_frame = ctk.CTkFrame(control_panel)
        yaml_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 6))
        yaml_frame.grid_columnconfigure(0, weight=1)
        yaml_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            yaml_frame,
            text="坐标配置（配置文件）",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        yaml_path_row = ctk.CTkFrame(yaml_frame, fg_color="transparent")
        yaml_path_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        yaml_path_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(yaml_path_row, text="路径：").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.yaml_path_var = ctk.StringVar(value=str(self.yaml_path))
        self.yaml_path_entry = ctk.CTkEntry(yaml_path_row, textvariable=self.yaml_path_var)
        self.yaml_path_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        self.btn_choose_yaml = ctk.CTkButton(
            yaml_path_row,
            text="选择",
            width=70,
            command=self.choose_yaml_path,
        )
        self.btn_choose_yaml.grid(row=0, column=2, sticky="e")

        tree_container = ctk.CTkFrame(yaml_frame)
        tree_container.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self._init_treeview(tree_container)

        yaml_btns = ctk.CTkFrame(yaml_frame, fg_color="transparent")
        yaml_btns.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        yaml_btns.grid_columnconfigure((0, 1), weight=1)

        self.btn_load_yaml = ctk.CTkButton(
            yaml_btns,
            text="加载配置",
            command=self.load_yaml,
        )
        self.btn_load_yaml.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=0)

        self.btn_save_yaml = ctk.CTkButton(
            yaml_btns,
            text="保存到配置",
            fg_color="#2e8b57",
            command=self.save_yaml_selected,
        )
        self.btn_save_yaml.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=0)

        # 右侧日志控制台
        log_title_frame = ctk.CTkFrame(log_container)
        log_title_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        
        ctk.CTkLabel(
            log_title_frame,
            text="📋 实时日志控制台",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=10)
        
        self.log_text = ctk.CTkTextbox(log_container, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_container.grid_rowconfigure(1, weight=1)
        
        # 中间画布区域
        self.canvas = ctk.CTkCanvas(canvas_container, bg="#1f1f1f", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        canvas_container.grid_rowconfigure(0, weight=1)
        canvas_container.grid_columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Configure>", lambda _e: self.redraw_screenshot())

        self.canvas.create_text(
            50,
            50,
            text="请先选择设备并连接，然后获取截图",
            fill="#9a9a9a",
            anchor="nw",
            font=("Arial", 14),
            tags="placeholder",
        )

        for var in (self.x1_var, self.y1_var, self.x2_var, self.y2_var):
            var.trace_add("write", lambda *_args: self.schedule_draw_from_entries())

    def _build_designer_tab(self) -> None:
        """V6.0: 构建统一工作流设计器 Tab 页面 - 左-中-右布局
        
        左栏 (Inspector): 步骤配置、参数输入、变量按钮
        中栏 (Viewport): 截图画布、坐标显示
        右栏 (Outliner): 步骤队列、编辑控制、导入导出
        """
        self.tab_designer.grid_rowconfigure(0, weight=1)
        self.tab_designer.grid_columnconfigure(0, weight=2)   # 左：节点库+配置 (20%)
        self.tab_designer.grid_columnconfigure(1, weight=4)   # 中：节点画布 (40%)
        self.tab_designer.grid_columnconfigure(2, weight=2)   # 中右：控制面板 (20%)
        self.tab_designer.grid_columnconfigure(3, weight=2)   # 右：截图预览 (20%)

        # V7.10: Canvas Expand State
        self._canvas_expanded = False
        self._hidden_panels = [] # Stores hidden panel references

        # ==================== 左侧：Inspector 参数配置区 ====================
        # V7.8: 紧凑布局, CTkFrame (无滚动), Pad减少
        self.left_panel = ctk.CTkFrame(self.tab_designer)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.left_panel.grid_columnconfigure(0, weight=1)

        # === 节点库 (快速添加) ===
        palette_frame = ctk.CTkFrame(self.left_panel)
        palette_frame.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        palette_frame.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(palette_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        
        ctk.CTkLabel(header_frame, text="🧩 节点", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=5)
        
        ctk.CTkButton(header_frame, text="✨ 扩展", width=60, height=24, fg_color="#6C5CE7", hover_color="#5849BE", font=ctk.CTkFont(size=12, weight="bold"), command=self._show_extension_import).pack(side="right", padx=5)

        # 生成节点按钮
        node_btn_frame = ctk.CTkFrame(palette_frame, fg_color="transparent")
        node_btn_frame.grid(row=1, column=0, sticky="ew", padx=1, pady=1)
        
        col = 0
        # V7.9: 美化节点图标 (正方形, 圆角, 更大图标, 图片支持)
        for category, actions in ACTION_CATEGORIES.items():
            for action_type, style in list(actions.items())[:3]:  # 保持常用显示
                icon_val = style.get('icon', '?')
                image_obj = None
                text_val = icon_val
                
                # App Icon Support (File-based)
                if isinstance(icon_val, str) and icon_val.lower().endswith(('.png', '.jpg')):
                     try:
                         if Path(icon_val).exists():
                             pil_img = Image.open(icon_val)
                             image_obj = ctk.CTkImage(light_image=pil_img, size=(32, 32))
                             text_val = ""
                     except Exception:
                         pass

                btn = ctk.CTkButton(
                    node_btn_frame,
                    text=text_val,
                    image=image_obj,
                    width=52, height=52,
                    corner_radius=8,   # 现代圆角正方形
                    border_width=0,
                    font=ctk.CTkFont(family="Segoe UI Emoji", size=26), # 确保 Emoji 清晰
                    fg_color=style["color"],
                    command=lambda a=action_type: self._add_node_to_canvas(a),
                )
                if image_obj:
                    btn.image = image_obj # GC Shield

                btn.grid(row=col // 5, column=col % 5, padx=3, pady=3)
                col += 1

        # Step 序号
        step_frame = ctk.CTkFrame(self.left_panel)
        step_frame.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        step_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            step_frame,
            text="📌 配置",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        ctk.CTkLabel(step_frame, text="序号:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.gen_step_entry = ctk.CTkEntry(step_frame, textvariable=self.gen_step_var, width=120)
        self.gen_step_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        # V5.0: 类别下拉菜单
        ctk.CTkLabel(step_frame, text="类别:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.gen_category_combo = ctk.CTkComboBox(
            step_frame,
            variable=self.gen_category_var,
            values=list(ACTION_CATEGORIES.keys()),
            width=220,
            command=self._on_gen_category_change,
        )
        self.gen_category_combo.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        # V5.0: 动作下拉菜单
        ctk.CTkLabel(step_frame, text="动作:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        first_category = list(ACTION_CATEGORIES.keys())[0]
        first_actions = list(ACTION_CATEGORIES[first_category].keys())
        self.gen_action_combo = ctk.CTkComboBox(
            step_frame,
            variable=self.gen_action_var,
            values=first_actions,
            width=220,
        )
        self.gen_action_combo.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

        # 动作参数
        self.gen_param_frame = ctk.CTkFrame(self.left_panel)
        self.gen_param_frame.grid(row=2, column=0, sticky="ew", padx=2, pady=2)
        self.gen_param_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.gen_param_frame,
            text="📝 参数",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        # V7.6: 快捷参数 (Top)
        self.gen_shortcut_label = ctk.CTkLabel(self.gen_param_frame, text="推荐:", font=ctk.CTkFont(size=11))
        self.gen_shortcut_label.grid(row=1, column=0, sticky="w", padx=5, pady=0)
        
        self.gen_shortcut_frame = ctk.CTkFrame(self.gen_param_frame, fg_color="transparent")
        self.gen_shortcut_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=2, pady=0)

        # 判断条件
        self.gen_operator_label = ctk.CTkLabel(self.gen_param_frame, text="条件:")
        self.gen_operator_label.grid(row=3, column=0, sticky="w", padx=5, pady=2)
        
        self.gen_operator_combo = ctk.CTkComboBox(
            self.gen_param_frame,
            variable=self.gen_operator_var,
            values=["包含", "不包含", "等于", "不等于"],
            width=220,
        )
        self.gen_operator_combo.grid(row=3, column=1, sticky="ew", padx=5, pady=2)
        self.gen_operator_combo.grid_remove() # 默认隐藏
        self.gen_operator_label.grid_remove()

        self.gen_param_label = ctk.CTkLabel(self.gen_param_frame, text="值:")
        self.gen_param_label.grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.gen_param_entry = ctk.CTkEntry(
            self.gen_param_frame,
            textvariable=self.gen_param_var,
            placeholder_text="Enter value...",
        )
        self.gen_param_entry.grid(row=4, column=1, sticky="ew", padx=(5, 35), pady=2)
        
        self.gen_param_browse_btn = ctk.CTkButton(
            self.gen_param_frame, text="📂", width=30, height=24, fg_color="#444",
            command=self._browse_param_image
        )
        self.gen_param_browse_btn.grid(row=4, column=1, sticky="e", padx=2, pady=2)
        self.gen_param_browse_btn.grid_remove() # Default hidden

        ctk.CTkLabel(self.gen_param_frame, text="备注:").grid(row=5, column=0, sticky="nw", padx=5, pady=2)
        self.gen_context_text = ctk.CTkTextbox(self.gen_param_frame, height=50, font=ctk.CTkFont(size=12))
        self.gen_context_text.grid(row=5, column=1, sticky="ew", padx=5, pady=2)

        # V6.0: 变量快捷插入行
        var_label_frame = ctk.CTkFrame(self.gen_param_frame, fg_color="transparent")
        var_label_frame.grid(row=6, column=0, columnspan=2, sticky="ew", padx=5, pady=2)
        
        ctk.CTkLabel(var_label_frame, text="变量:", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkButton(
            var_label_frame, text="📂", width=24, height=20, fg_color="#444",
            command=self._select_excel_path
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            var_label_frame, text="{x}", width=40, height=20, fg_color="#555",
            command=self._show_variable_menu
        ).pack(side="right")
        
        # 变量按钮容器
        self.gen_var_frame = ctk.CTkFrame(self.gen_param_frame, fg_color="#2a2a2a")
        self.gen_var_frame.grid(row=7, column=0, columnspan=2, sticky="ew", padx=5, pady=2)
        
        # 初始化变量按钮
        self._load_variable_buttons()





        # 提示标签
        self.orch_hint_label = ctk.CTkLabel(
            self.left_panel,
            text="点击节点查看属性",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
        )
        self.orch_hint_label.grid(row=5, column=0, sticky="ew", padx=10, pady=(10, 20))

        # ==================== 中间：节点画布区 (Viewport) ====================
        self.center_panel = ctk.CTkFrame(self.tab_designer)
        self.center_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        self.center_panel.grid_rowconfigure(1, weight=1)  # 节点画布占满
        self.center_panel.grid_columnconfigure(0, weight=1)

        # === 节点画布区域 ===
        node_header = ctk.CTkFrame(self.center_panel, fg_color="transparent")
        node_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        node_header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            node_header,
            text="🎨 工作流画布 (拖拽节点)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        
        # V7.10: Expand/Pop-out Button
        self.expand_btn = ctk.CTkButton(
            node_header, text="⬜ 独立窗口", width=80, height=24, fg_color="#555",
            command=self._toggle_canvas_popout
        )
        self.expand_btn.grid(row=0, column=1, sticky="e")

        # 节点画布 (使用 orch_canvas) - Store reference for pop-out
        self.canvas_container = ctk.CTkFrame(self.center_panel)
        self.canvas_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))
        self.canvas_container.grid_rowconfigure(0, weight=1)
        self.canvas_container.grid_columnconfigure(0, weight=1)
        
        self.orch_canvas = tk.Canvas(self.canvas_container, bg="#1e1e1e", highlightthickness=0)
        self.orch_canvas.grid(row=0, column=0, sticky="nsew")
        
        # 滚动条
        h_scroll = tk.Scrollbar(self.canvas_container, orient="horizontal", command=self.orch_canvas.xview)
        v_scroll = tk.Scrollbar(self.canvas_container, orient="vertical", command=self.orch_canvas.yview)
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        self.orch_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        # 画布事件绑定
        self.orch_canvas.bind("<Button-1>", self._orch_on_canvas_click)
        self.orch_canvas.bind("<B1-Motion>", self._orch_on_canvas_drag)
        self.orch_canvas.bind("<ButtonRelease-1>", self._orch_on_canvas_release)
        self.orch_canvas.bind("<Double-Button-1>", self._orch_on_canvas_double_click)
        self.orch_canvas.bind("<ButtonPress-2>", self._orch_on_canvas_pan_start)
        self.orch_canvas.bind("<B2-Motion>", self._orch_on_canvas_pan_drag)
        self.orch_canvas.bind("<Control-ButtonPress-1>", self._orch_on_canvas_pan_start)
        self.orch_canvas.bind("<Control-B1-Motion>", self._orch_on_canvas_pan_drag)
        
        # V7.12: Right-click context menu and Delete key
        self.orch_canvas.bind("<Button-3>", self._orch_on_canvas_right_click)
        self.orch_canvas.bind("<Delete>", self._orch_delete_selected_node)
        self.orch_canvas.bind("<BackSpace>", self._orch_delete_selected_node)
        
        self._orch_draw_grid()

        # ==================== 最右侧：截图预览区 (独立面板) ====================
        self.screenshot_panel = ctk.CTkFrame(self.tab_designer)
        self.screenshot_panel.grid(row=0, column=3, sticky="nsew", padx=(5, 10), pady=10)
        self.screenshot_panel.grid_rowconfigure(1, weight=1)
        self.screenshot_panel.grid_columnconfigure(0, weight=1)

        # 标题和刷新按钮
        screenshot_header = ctk.CTkFrame(self.screenshot_panel, fg_color="transparent")
        screenshot_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        screenshot_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            screenshot_header,
            text="📱 设备截图 (1080x2400)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.btn_gen_refresh = ctk.CTkButton(
            screenshot_header,
            text="📷 刷新",
            width=70,
            height=28,
            fg_color="#3498db",
            command=self.refresh_gen_screenshot,
        )
        self.btn_gen_refresh.grid(row=0, column=1, sticky="e")

        # 截图画布 (全高度，保持手机比例 9:20)
        self.gen_canvas = ctk.CTkCanvas(self.screenshot_panel, bg="#1f1f1f", highlightthickness=0)
        self.gen_canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.gen_canvas.bind("<Button-1>", self.on_gen_canvas_press)
        self.gen_canvas.bind("<B1-Motion>", self.on_gen_canvas_drag)
        self.gen_canvas.bind("<ButtonRelease-1>", self.on_gen_canvas_release)
        self.gen_canvas.bind("<Configure>", lambda _e: self.redraw_gen_screenshot())

        self.gen_canvas.create_text(
            20, 50,
            text="请先连接设备\n然后点击「刷新」",
            fill="#9a9a9a",
            anchor="nw",
            font=("Arial", 12),
            tags="placeholder",
        )

        # ==================== 右侧 (中右)：工作流控制区 ====================
        self.control_panel = ctk.CTkFrame(self.tab_designer)
        self.control_panel.grid(row=0, column=2, sticky="nsew", padx=5, pady=10)
        self.control_panel.grid_rowconfigure(2, weight=1)  # 节点列表可扩展
        self.control_panel.grid_columnconfigure(0, weight=1)

        # === 工作流操作按钮 (第一行) ===
        action_frame = ctk.CTkFrame(self.control_panel)
        action_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        action_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            action_frame,
            text="🎮 工作流控制",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 8))

        # 第一行按钮
        ctk.CTkButton(
            action_frame, text="▶️ 运行全部", fg_color="#27ae60", height=32,
            command=self._orch_run_all
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=(10, 3), pady=3)

        ctk.CTkButton(
            action_frame, text="🔴 断点调试", fg_color="#e74c3c", height=32,
            command=self._orch_run_with_breakpoints
        ).grid(row=1, column=2, columnspan=2, sticky="ew", padx=(3, 10), pady=3)

        # 第二行按钮
        ctk.CTkButton(
            action_frame, text="🧪 单点测试", fg_color="#3498db", height=32,
            command=self._orch_test_selected_node
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=(10, 3), pady=3)

        ctk.CTkButton(
            action_frame, text="🗑️ 清空画布", fg_color="#7f8c8d", height=32,
            command=self._orch_clear_canvas
        ).grid(row=2, column=2, columnspan=2, sticky="ew", padx=(3, 10), pady=3)

        # === 文件操作 ===
        file_frame = ctk.CTkFrame(self.control_panel)
        file_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        file_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            file_frame,
            text="📁 流程文件",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))

        ctk.CTkButton(
            file_frame, text="📂 加载流程", fg_color="#555", height=30,
            command=self._orch_import_json
        ).grid(row=1, column=0, sticky="ew", padx=(10, 3), pady=(0, 6))

        ctk.CTkButton(
            file_frame, text="💾 保存流程", fg_color="#555", height=30,
            command=self._orch_export_json
        ).grid(row=1, column=1, sticky="ew", padx=(3, 10), pady=(0, 6))

        # V7.5: 节点操作按钮 (断开连接 + 测试点击)
        node_op_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
        node_op_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 6))
        node_op_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            node_op_frame, text="🔌 断开连接", fg_color="#e67e22", height=30,
            command=self._orch_disconnect_selected_node_all
        ).grid(row=0, column=0, sticky="ew", padx=3)

        ctk.CTkButton(
            node_op_frame, text="👆 测试点击", fg_color="#2980b9", height=30,
            command=self._orch_test_click_region
        ).grid(row=0, column=1, sticky="ew", padx=3)

        # === 节点列表区 ===
        node_list_frame = ctk.CTkFrame(self.control_panel)
        node_list_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))
        node_list_frame.grid_rowconfigure(1, weight=1)
        node_list_frame.grid_columnconfigure(0, weight=1)

        list_header = ctk.CTkFrame(node_list_frame, fg_color="transparent")
        list_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        list_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            list_header, text="📋 节点列表", font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            list_header, text="🔗 自动连接", width=70, height=24, fg_color="#555",
            command=self._orch_auto_connect
        ).grid(row=0, column=1, sticky="e", padx=2)

        # 节点列表 Listbox
        list_container = ctk.CTkFrame(node_list_frame)
        list_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        self.gen_queue_listbox = tk.Listbox(
            list_container, bg="#2a2a2a", fg="#ffffff",
            selectbackground="#3498db", font=("Consolas", 10), height=10
        )
        self.gen_queue_listbox.grid(row=0, column=0, sticky="nsew")
        self.gen_queue_listbox.bind("<<ListboxSelect>>", self._on_node_list_select)
        self.gen_queue_listbox.bind("<Double-1>", self._gen_on_queue_double_click)
        
        # 滚动条
        list_scrollbar = tk.Scrollbar(list_container, orient="vertical", command=self.gen_queue_listbox.yview)
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.gen_queue_listbox.configure(yscrollcommand=list_scrollbar.set)

        # V7.3: 坐标显示区 (移动到右侧，位于节点列表下方)
        self.gen_coord_frame = ctk.CTkFrame(self.control_panel)
        self.gen_coord_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
        self.gen_coord_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(
            self.gen_coord_frame,
            text="📍 目标坐标（百分比）",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 8))

        ctk.CTkLabel(self.gen_coord_frame, text="X1：").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        ctk.CTkEntry(self.gen_coord_frame, textvariable=self.gen_x1_var, width=80, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=(0, 10), pady=4
        )
        ctk.CTkLabel(self.gen_coord_frame, text="Y1：").grid(row=1, column=2, sticky="w", padx=10, pady=4)
        ctk.CTkEntry(self.gen_coord_frame, textvariable=self.gen_y1_var, width=80, state="readonly").grid(
            row=1, column=3, sticky="ew", padx=(0, 10), pady=4
        )

        ctk.CTkLabel(self.gen_coord_frame, text="X2：").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        ctk.CTkEntry(self.gen_coord_frame, textvariable=self.gen_x2_var, width=80, state="readonly").grid(
            row=2, column=1, sticky="ew", padx=(0, 10), pady=4
        )
        ctk.CTkLabel(self.gen_coord_frame, text="Y2：").grid(row=2, column=2, sticky="w", padx=10, pady=4)
        ctk.CTkEntry(self.gen_coord_frame, textvariable=self.gen_y2_var, width=80, state="readonly").grid(
            row=2, column=3, sticky="ew", padx=(0, 10), pady=4
        )

        # 同步坐标按钮 (嵌入到 Control Panel)
        sync_frame = ctk.CTkFrame(self.control_panel, fg_color="transparent")
        sync_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        sync_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_sync_from_live = ctk.CTkButton(
            sync_frame,
            text="📥 从实时调试同步",
            fg_color="#4a90d9",
            command=self.sync_coords_from_live,
        )
        self.btn_sync_from_live.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=6)

        self.btn_clear_gen_coords = ctk.CTkButton(
            sync_frame,
            text="🗑️ 清除坐标",
            fg_color="#555555",
            command=self.clear_gen_coords,
        )
        self.btn_clear_gen_coords.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=6)

    # V7.11: Canvas Pop-out to Separate Window
    def _toggle_canvas_popout(self):
        """Pop out the canvas to a separate window, or dock it back"""
        if hasattr(self, '_canvas_window') and self._canvas_window and self._canvas_window.winfo_exists():
            # Already popped out - dock it back
            self._dock_canvas()
        else:
            # Pop out to new window
            self._popout_canvas()
    
    def _popout_canvas(self):
        """Move canvas to a separate floating window"""
        # 1. Create new Toplevel window
        self._canvas_window = ctk.CTkToplevel(self.root)
        self._canvas_window.title("🎨 工作流画布 - 独立窗口")
        self._canvas_window.geometry("1200x800")
        self._canvas_window.configure(fg_color="#1a1a1a")
        
        # Handle window close
        self._canvas_window.protocol("WM_DELETE_WINDOW", self._dock_canvas)
        
        # 2. Create placeholder in original location
        self._canvas_placeholder = ctk.CTkFrame(self.center_panel, fg_color="#2a2a2a")
        self._canvas_placeholder.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))
        
        placeholder_label = ctk.CTkLabel(
            self._canvas_placeholder, 
            text="📺 画布已在独立窗口中打开\n\n点击「收回画布」按钮或关闭独立窗口\n可将画布嵌入回主界面",
            font=("Arial", 14),
            text_color="#888"
        )
        placeholder_label.pack(expand=True)
        
        dock_btn = ctk.CTkButton(
            self._canvas_placeholder, text="⬅ 收回画布", width=120, height=36,
            fg_color="#27ae60", command=self._dock_canvas
        )
        dock_btn.pack(pady=20)
        
        # 3. Hide original container and move canvas to new window
        self.canvas_container.grid_remove()
        
        # 4. Create new container in popup window
        self._popup_container = ctk.CTkFrame(self._canvas_window, fg_color="#1e1e1e")
        self._popup_container.pack(fill="both", expand=True, padx=10, pady=10)
        self._popup_container.grid_rowconfigure(0, weight=1)
        self._popup_container.grid_columnconfigure(0, weight=1)
        
        # 5. Reparent canvas to popup - MUST use grid_forget first to release from old manager
        self.orch_canvas.grid_forget()
        self.orch_canvas.configure(bg="#1e1e1e")
        
        # Recreate canvas in popup (simpler than reparenting due to Tkinter limitations)
        self._original_canvas = self.orch_canvas  # Keep reference
        self._popup_canvas = tk.Canvas(self._popup_container, bg="#1e1e1e", highlightthickness=0)
        self._popup_canvas.pack(fill="both", expand=True)
        
        # Copy canvas bindings
        self._popup_canvas.bind("<Button-1>", self._orch_on_canvas_click)
        self._popup_canvas.bind("<B1-Motion>", self._orch_on_canvas_drag)
        self._popup_canvas.bind("<ButtonRelease-1>", self._orch_on_canvas_release)
        self._popup_canvas.bind("<Double-Button-1>", self._orch_on_canvas_double_click)
        self._popup_canvas.bind("<ButtonPress-2>", self._orch_on_canvas_pan_start)
        self._popup_canvas.bind("<B2-Motion>", self._orch_on_canvas_pan_drag)
        self._popup_canvas.bind("<Control-ButtonPress-1>", self._orch_on_canvas_pan_start)
        self._popup_canvas.bind("<Control-B1-Motion>", self._orch_on_canvas_pan_drag)
        
        # V7.12: Add missing bindings for popup canvas
        self._popup_canvas.bind("<Button-3>", self._orch_on_canvas_right_click)
        self._popup_canvas.bind("<Delete>", self._orch_delete_selected_node)
        self._popup_canvas.bind("<BackSpace>", self._orch_delete_selected_node)
        
        # Swap canvas reference
        self.orch_canvas = self._popup_canvas
        
        # 6. Add toolbar in popup window
        popup_toolbar = ctk.CTkFrame(self._canvas_window, height=50, fg_color="#222")
        popup_toolbar.pack(fill="x", side="bottom", padx=10, pady=(0, 10))
        
        ctk.CTkButton(popup_toolbar, text="▶️ 运行全部", fg_color="#27ae60", width=100,
                      command=self._orch_run_all).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(popup_toolbar, text="💾 保存", fg_color="#3498db", width=80,
                      command=self._orch_export_json).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(popup_toolbar, text="📂 加载", fg_color="#555", width=80,
                      command=self._orch_import_json).pack(side="left", padx=5, pady=5)
        
        ctk.CTkButton(popup_toolbar, text="⬅ 收回画布", fg_color="#e74c3c", width=100,
                      command=self._dock_canvas).pack(side="right", padx=5, pady=5)
        
        # 7. Update button in main window
        self.expand_btn.configure(text="⬅ 收回", fg_color="#e74c3c")
        
        # 8. Redraw canvas grid
        self._orch_draw_grid()
    
    def _dock_canvas(self):
        """Move canvas back to main window"""
        if not hasattr(self, '_canvas_window') or not self._canvas_window:
            return
            
        # 1. Remove placeholder
        if hasattr(self, '_canvas_placeholder') and self._canvas_placeholder:
            self._canvas_placeholder.destroy()
            self._canvas_placeholder = None
        
        # 2. Restore original canvas reference
        if hasattr(self, '_original_canvas') and self._original_canvas:
            self.orch_canvas = self._original_canvas
            self.orch_canvas.grid(row=0, column=0, sticky="nsew")
        
        # 3. Show original container
        self.canvas_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))
        
        # 4. Destroy popup window (this also destroys popup canvas)
        if self._canvas_window and self._canvas_window.winfo_exists():
            self._canvas_window.destroy()
        self._canvas_window = None
        self._popup_canvas = None
        self._original_canvas = None
        
        # 5. Update button
        self.expand_btn.configure(text="⬜ 独立窗口", fg_color="#555")
        
        # 6. Redraw canvas grid
        self._orch_draw_grid()

    def _make_labeled_entry(
        self,
        parent: ctk.CTkFrame,
        label: str,
        var: ctk.StringVar,
        row: int,
        col: int,
    ) -> None:
        ctk.CTkLabel(parent, text=f"{label}：").grid(row=row, column=col, sticky="w", padx=10, pady=6)
        entry = ctk.CTkEntry(parent, textvariable=var, width=140)
        entry.grid(row=row, column=col + 1, sticky="ew", padx=10, pady=6)

    def _init_treeview(self, parent: ctk.CTkFrame) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Treeview",
            background="#1f1f1f",
            fieldbackground="#1f1f1f",
            foreground="#dddddd",
            rowheight=22,
        )
        style.configure(
            "Treeview.Heading",
            background="#2b2b2b",
            foreground="#dddddd",
        )

        columns = ("类型", "左上X", "左上Y", "右下X", "右下Y")
        self.tree = ttk.Treeview(parent, columns=columns, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="路径")
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=90, anchor="center")
        self.tree.column("#0", width=240)

        self.tree.grid(row=0, column=0, sticky="nsew")
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.on_tree_select())

    def log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        try:
            self.log_text.insert("end", line)
            self.log_text.see("end")
        except Exception:
            pass

    def refresh_device_list(self) -> None:
        try:
            devices = adb.device_list()
            serials = [d.serial for d in devices]
        except Exception as e:
            serials = []
            self.log(f"获取设备列表失败：{e}")

        if not serials:
            self.device_combo.configure(values=[""])
            self.selected_serial_var.set("")
            self.status_label.configure(text="状态：未检测到设备", text_color="#aaaaaa")
            return

        self.device_combo.configure(values=serials)
        if self.selected_serial_var.get() not in serials:
            self.selected_serial_var.set(serials[0])
        self.status_label.configure(text="状态：已检测到设备，请选择并连接", text_color="#aaaaaa")

    def on_device_selected(self) -> None:
        if self.device is not None:
            self.status_label.configure(text="状态：已连接（切换设备需先断开）", text_color="#f0ad4e")

    def connect_selected_device(self) -> None:
        serial = (self.selected_serial_var.get() or "").strip()
        if not serial:
            messagebox.showwarning("提示", "请先选择设备序列号")
            return
        try:
            self.device = adb.device(serial=serial)
            self._update_device_resolution()
            self.status_label.configure(
                text=f"状态：已连接 {serial}（{self.phone_width}x{self.phone_height}）",
                text_color="#66cc66",
            )
            self.log(f"已连接设备：{serial}")
        except AdbError as e:
            self.device = None
            self.status_label.configure(text="状态：连接失败", text_color="#ff6666")
            messagebox.showerror("连接失败", f"连接设备失败：\n{e}")
            self.log(f"连接设备失败：{e}")

    def disconnect_device(self) -> None:
        self.device = None
        self.phone_width = 0
        self.phone_height = 0
        self.screenshot_pil = None
        self.screenshot_bgr = None
        self.tk_photo = None
        self.template_match_roi = None
        self.template_bgr = None
        self.template_path = None
        self.template_rect_id = None
        if hasattr(self, "template_path_label"):
            try:
                self.template_path_label.configure(text="未选择")
            except Exception:
                pass
        self.canvas.delete("all")
        self.canvas.create_text(
            50,
            50,
            text="请先选择设备并连接，然后获取截图",
            fill="#9a9a9a",
            anchor="nw",
            font=("Arial", 14),
            tags="placeholder",
        )
        self.status_label.configure(text="状态：未连接", text_color="#aaaaaa")
        self.log("已断开设备")

    def _update_device_resolution(self) -> None:
        if self.device is None:
            return
        try:
            wm_size = self.device.shell("wm size")
            m = re.search(r"(\d+)x(\d+)", wm_size)
            if not m:
                raise ValueError("无法解析分辨率")
            self.phone_width = int(m.group(1))
            self.phone_height = int(m.group(2))
        except Exception as e:
            raise AdbError(f"获取分辨率失败：{e}")

    def require_device(self) -> bool:
        if self.device is None:
            messagebox.showwarning("提示", "请先选择设备并点击连接")
            return False
        return True

    def refresh_screenshot(self) -> None:
        if not self.require_device():
            return
        try:
            self._update_device_resolution()
            img = self.device.screenshot()
            self.screenshot_pil = img
            rgb = np.array(img)
            if rgb.ndim == 3 and rgb.shape[2] == 3:
                self.screenshot_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            else:
                self.screenshot_bgr = rgb
            self.redraw_screenshot()
            self.log("截图获取成功")
        except AdbError as e:
            messagebox.showerror("截图失败", f"截图失败：\n{e}")
            self.log(f"截图失败：{e}")
        except Exception as e:
            messagebox.showerror("截图失败", f"截图失败：\n{e}")
            self.log(f"截图失败：{e}")

    def redraw_screenshot(self) -> None:
        if self.screenshot_pil is None or self.phone_width <= 0 or self.phone_height <= 0:
            return

        canvas_w = max(1, int(self.canvas.winfo_width()))
        canvas_h = max(1, int(self.canvas.winfo_height()))

        img_ratio = self.phone_width / max(1, self.phone_height)
        canvas_ratio = canvas_w / max(1, canvas_h)

        if img_ratio > canvas_ratio:
            disp_w = canvas_w
            disp_h = int(canvas_w / img_ratio)
        else:
            disp_h = canvas_h
            disp_w = int(canvas_h * img_ratio)

        disp_w = max(1, disp_w)
        disp_h = max(1, disp_h)

        self.display_width = disp_w
        self.display_height = disp_h
        self.canvas_scale = disp_w / max(1, self.phone_width)
        self.canvas_offset_x = int((canvas_w - disp_w) / 2)
        self.canvas_offset_y = int((canvas_h - disp_h) / 2)

        resized = self.screenshot_pil.resize((disp_w, disp_h), Image.LANCZOS)
        self.tk_photo = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(
            self.canvas_offset_x,
            self.canvas_offset_y,
            image=self.tk_photo,
            anchor="nw",
            tags="screenshot",
        )

        self.draw_roi_from_entries()
        self._draw_template_match_box()
        self._draw_ocr_detections()
        self._draw_offset_calculator()

    def choose_yaml_path(self) -> None:
        initial_dir = str(Path(self.yaml_path).parent) if self.yaml_path else str(Path.cwd())
        path = filedialog.askopenfilename(
            title="选择坐标配置文件",
            initialdir=initial_dir,
            filetypes=[("配置文件", "*.yaml *.yml"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.yaml_path = Path(path)
        self.yaml_path_var.set(str(self.yaml_path))
        self.load_yaml()

    def copy_current_coords(self) -> None:
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except Exception:
            messagebox.showwarning("提示", "坐标输入无效")
            return
        text = f"{x1:.3f}\n{y1:.3f}\n{x2:.3f}\n{y2:.3f}"
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception as e:
            messagebox.showwarning("提示", f"复制失败：\n{e}")
            self.log(f"复制失败：{e}")
            return
        messagebox.showinfo("复制成功", "已复制到剪贴板")
        self.log("已复制当前坐标到剪贴板")

    def quick_copy_coordinates(self) -> None:
        """
        一键复制坐标百分比值 (增强版)
        格式: (x1, y1) 到 (x2, y2)
        用户偏好的高精度格式，可直接复制到UI控制面板
        """
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except Exception:
            messagebox.showwarning("提示", "坐标输入无效，请先框选区域或输入坐标值")
            return
        
        # 确保 x1 < x2, y1 < y2
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        
        # 用户偏好的高精度格式: (0.425, 0.559) 到 (0.894, 0.743)
        quick_format = f"({x1:.3f}, {y1:.3f}) 到 ({x2:.3f}, {y2:.3f})"
        
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(quick_format)
        except Exception as e:
            messagebox.showwarning("提示", f"复制失败：\n{e}")
            self.log(f"复制失败：{e}")
            return
        
        # 计算中心点和区域大小
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        width_pct = x2 - x1
        height_pct = y2 - y1
        
        self.log(f"一键复制：{quick_format}")
        messagebox.showinfo(
            "一键复制成功",
            f"已复制到剪贴板：\n{quick_format}\n\n中心点：({cx:.3f}, {cy:.3f})\n区域：{width_pct:.1%} x {height_pct:.1%}"
        )

    def copy_yaml_format(self) -> None:
        """
        复制YAML格式坐标
        用于直接粘贴到配置文件
        """
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except Exception:
            messagebox.showwarning("提示", "坐标输入无效，请先框选区域或输入坐标值")
            return
        
        # 确保 x1 < x2, y1 < y2
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        
        # YAML格式
        yaml_format = f"x_min: {x1:.3f}\ny_min: {y1:.3f}\nx_max: {x2:.3f}\ny_max: {y2:.3f}"
        
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(yaml_format)
        except Exception as e:
            messagebox.showwarning("提示", f"复制失败：\n{e}")
            self.log(f"复制失败：{e}")
            return
        
        self.log("YAML格式已复制")
        messagebox.showinfo(
            "YAML格式已复制",
            f"已复制到剪贴板：\n\n{yaml_format}\n\n可直接粘贴到配置文件"
        )

    def parse_quick_paste(self) -> None:
        text = (self.paste_var.get() or "").strip()
        if not text:
            return
        nums = re.findall(r"-?\d+(?:\.\d+)?", text)
        if len(nums) < 4:
            messagebox.showwarning("提示", "解析失败：请提供四个数字，例如 (0.1, 0.2) 到 (0.3, 0.4)")
            return
        try:
            x1, y1, x2, y2 = map(float, nums[:4])
        except Exception:
            messagebox.showwarning("提示", "解析失败：数字格式不正确")
            return

        self.x1_var.set(f"{x1:.3f}")
        self.y1_var.set(f"{y1:.3f}")
        self.x2_var.set(f"{x2:.3f}")
        self.y2_var.set(f"{y2:.3f}")
        self.log("快速粘贴解析成功，已填充坐标")

    def schedule_draw_from_entries(self) -> None:
        if self._building_ui:
            return
        if self.entry_update_job is not None:
            try:
                self.root.after_cancel(self.entry_update_job)
            except Exception:
                pass
        self.entry_update_job = self.root.after(120, self.draw_roi_from_entries)

    def _get_entries_roi(self) -> Optional[RoiPct]:
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except Exception:
            return None
        return RoiPct(x1=x1, y1=y1, x2=x2, y2=y2).normalized().clipped()

    def draw_roi_from_entries(self) -> None:
        if self.screenshot_pil is None:
            return
        roi = self._get_entries_roi()
        if roi is None:
            return
        self._draw_roi(roi)
        self._draw_template_match_box()

    def _get_current_roi_phone_px(self) -> Optional[Tuple[int, int, int, int]]:
        roi = self._get_entries_roi()
        if roi is None:
            return None
        x1_px, y1_px = self._pct_to_phone_px(roi.x1, roi.y1)
        x2_px, y2_px = self._pct_to_phone_px(roi.x2, roi.y2)
        x1, x2 = int(min(x1_px, x2_px)), int(max(x1_px, x2_px))
        y1, y2 = int(min(y1_px, y2_px)), int(max(y1_px, y2_px))
        return x1, y1, x2, y2

    def _preprocess_for_text(self, bgr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        up = cv2.resize(gray, (gray.shape[1] * 2, gray.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
        _, thr = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thr

    def _run_text_recognition(self, bgr: np.ndarray, region_offset: Tuple[int, int] = (0, 0)) -> Tuple[List[str], List[Dict[str, Any]]]:
        """运行OCR识别，返回文本列表和检测结果列表（包含边界框信息）"""
        if self.ocr_engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self.ocr_engine = RapidOCR()
            self.log("文字识别引擎已初始化")

        binary = self._preprocess_for_text(bgr)
        result = self.ocr_engine(binary)
        if isinstance(result, tuple) and len(result) >= 1:
            detections = result[0]
        else:
            detections = result

        if not detections:
            return [], []

        texts: List[str] = []
        detection_data: List[Dict[str, Any]] = []
        x_offset, y_offset = region_offset
        
        for item in detections:
            try:
                if not item or len(item) < 3:
                    continue
                # RapidOCR返回格式: [bbox, text, confidence]
                bbox = item[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text = str(item[1]).strip()
                confidence = float(item[2]) if len(item) > 2 else 0.0
                
                if text:
                    texts.append(text)
                    # 计算边界框（考虑预处理时放大了2倍）
                    if bbox and len(bbox) >= 4:
                        xs = [p[0] for p in bbox]
                        ys = [p[1] for p in bbox]
                        # 还原到原始尺寸（除以2）并加上区域偏移
                        x1 = int(min(xs) / 2) + x_offset
                        y1 = int(min(ys) / 2) + y_offset
                        x2 = int(max(xs) / 2) + x_offset
                        y2 = int(max(ys) / 2) + y_offset
                        detection_data.append({
                            'bbox': (x1, y1, x2, y2),
                            'text': text,
                            'confidence': confidence
                        })
            except Exception:
                continue
        return texts, detection_data

    def _preprocess_for_template(self, bgr: np.ndarray, mode: str) -> np.ndarray:
        if mode == "边缘":
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 80, 200)
            return edges
        if mode == "二值":
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return thr
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        return gray

    def extract_roi_text_show(self) -> None:
        if self.screenshot_bgr is None:
            messagebox.showwarning("提示", "请先获取截图")
            return
        rect = self._get_current_roi_phone_px()
        if rect is None:
            messagebox.showwarning("提示", "坐标输入无效")
            return
        x1, y1, x2, y2 = rect
        if x2 - x1 < 2 or y2 - y1 < 2:
            messagebox.showwarning("提示", "区域太小，无法提取文字")
            return
        crop = self.screenshot_bgr[y1:y2, x1:x2].copy()
        try:
            lines, detections = self._run_text_recognition(crop, region_offset=(x1, y1))
            # 功能2：OCR结果可视化
            self.ocr_detections = detections
            self.redraw_screenshot()
        except Exception as e:
            messagebox.showerror("识别失败", f"文字提取失败：\n{e}")
            self.log(f"文字提取失败：{e}")
            return

        if not lines:
            self.ocr_detections = []
            self.redraw_screenshot()
            messagebox.showinfo("识别结果", "未识别到文字")
            self.log("区域文字提取：未识别到文字")
            return
        text = "\n".join(lines)
        messagebox.showinfo("识别结果", text)
        self.log("区域文字提取：已完成")

    def match_text_in_roi(self) -> None:
        if self.screenshot_bgr is None:
            messagebox.showwarning("提示", "请先获取截图")
            return
        target = (self.ocr_target_text_var.get() or "").strip()
        if not target:
            messagebox.showwarning("提示", "请输入要匹配的文字")
            return
        rect = self._get_current_roi_phone_px()
        if rect is None:
            messagebox.showwarning("提示", "坐标输入无效")
            return
        x1, y1, x2, y2 = rect
        if x2 - x1 < 2 or y2 - y1 < 2:
            messagebox.showwarning("提示", "区域太小，无法匹配")
            return
        crop = self.screenshot_bgr[y1:y2, x1:x2].copy()
        try:
            lines, detections = self._run_text_recognition(crop, region_offset=(x1, y1))
            # 功能2：OCR结果可视化
            self.ocr_detections = detections
            self.redraw_screenshot()
        except Exception as e:
            messagebox.showerror("识别失败", f"文字识别失败：\n{e}")
            self.log(f"文字识别失败：{e}")
            return

        if not lines:
            self.ocr_detections = []
            self.redraw_screenshot()
            messagebox.showinfo("匹配结果", "未识别到文字")
            self.log("文字匹配：未识别到文字")
            return

        found = False
        matched = []
        matched_detection = None
        for idx, line in enumerate(lines):
            if target.lower() in line.lower() or line.lower() in target.lower():
                found = True
                matched.append(line)
                if idx < len(detections):
                    matched_detection = detections[idx]

        if found:
            msg = "匹配成功\n\n识别到的文字：\n" + "\n".join(f"• {t}" for t in matched)
            messagebox.showinfo("匹配结果", msg)
            self.log("文字匹配：匹配成功")
            
            # 功能3：如果匹配成功且启用偏移计算器，设置锚点
            if matched_detection and self.offset_calculator_mode:
                x1_det, y1_det, x2_det, y2_det = matched_detection['bbox']
                center_x = (x1_det + x2_det) / 2
                center_y = (y1_det + y2_det) / 2
                self.anchor_center = (self._phone_px_to_pct(int(center_x), int(center_y)))
                self.anchor_text_content = matched_detection.get('text', '')
                self.redraw_screenshot()
                self.log(f"✅ 已设置锚点A（OCR中心）：({self.anchor_center[0]:.3f}, {self.anchor_center[1]:.3f})，文字：{self.anchor_text_content}，请框选目标区域B")
        else:
            msg = "未匹配\n\n识别到的文字：\n" + "\n".join(f"• {t}" for t in lines)
            messagebox.showinfo("匹配结果", msg)
            self.log("文字匹配：未匹配")

    def extract_roi_text_copy(self) -> None:
        if self.screenshot_bgr is None:
            messagebox.showwarning("提示", "请先获取截图")
            return
        rect = self._get_current_roi_phone_px()
        if rect is None:
            messagebox.showwarning("提示", "坐标输入无效")
            return
        x1, y1, x2, y2 = rect
        if x2 - x1 < 2 or y2 - y1 < 2:
            messagebox.showwarning("提示", "区域太小，无法提取文字")
            return
        crop = self.screenshot_bgr[y1:y2, x1:x2].copy()
        try:
            lines, detections = self._run_text_recognition(crop, region_offset=(x1, y1))
            # 功能2：OCR结果可视化
            self.ocr_detections = detections
            self.redraw_screenshot()
        except Exception as e:
            messagebox.showerror("识别失败", f"文字提取失败：\n{e}")
            self.log(f"文字提取失败：{e}")
            return

        if not lines:
            self.ocr_detections = []
            self.redraw_screenshot()
            messagebox.showinfo("识别结果", "未识别到文字")
            self.log("区域文字提取：未识别到文字")
            return

        text = "\n".join(lines)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception as e:
            messagebox.showwarning("提示", f"复制失败：\n{e}")
            self.log(f"复制失败：{e}")
            return
        messagebox.showinfo("复制成功", "已复制到剪贴板")
        self.log("区域文字提取：已复制到剪贴板")

    def choose_template_image(self) -> None:
        path = filedialog.askopenfilename(
            title="选择模板图片",
            initialdir=str(Path.cwd()),
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        p = Path(path)
        try:
            img: Optional[np.ndarray] = None
            try:
                data = np.fromfile(str(p), dtype=np.uint8)
                img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            except Exception:
                img = None

            if img is None:
                try:
                    pil_img = Image.open(p)
                    rgb = np.array(pil_img)
                    if rgb.ndim == 3 and rgb.shape[2] == 3:
                        img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                    elif rgb.ndim == 2:
                        img = cv2.cvtColor(rgb, cv2.COLOR_GRAY2BGR)
                    else:
                        img = None
                except Exception:
                    img = None

            if img is None:
                raise ValueError(f"无法读取图片（路径：{p}，后缀：{p.suffix}）")
            self.template_path = p
            self.template_bgr = img
            self.template_match_roi = None
            self.clear_template_match()
            if hasattr(self, "template_path_label"):
                self.template_path_label.configure(text=p.name)
            self.log(f"已选择模板图片：{p}")
        except Exception as e:
            messagebox.showerror("读取失败", f"读取模板图片失败：\n{e}")
            self.log(f"读取模板图片失败：{e}")

    def clear_template_match(self) -> None:
        self.template_match_roi = None
        if self.template_rect_id is not None:
            try:
                self.canvas.delete(self.template_rect_id)
            except Exception:
                pass
            self.template_rect_id = None
        self.log("已清除匹配框")

    def run_template_match(self) -> None:
        if self.screenshot_bgr is None:
            messagebox.showwarning("提示", "请先获取截图")
            return
        if self.template_bgr is None:
            messagebox.showwarning("提示", "请先选择模板图片")
            return

        try:
            threshold = float(self.template_threshold_var.get())
        except Exception:
            messagebox.showwarning("提示", "阈值格式不正确，请输入 0.0 到 1.0")
            return
        if threshold <= 0.0 or threshold > 1.0:
            messagebox.showwarning("提示", "阈值范围应为 0.0 到 1.0")
            return

        try:
            scale_min = float(self.template_scale_min_var.get())
            scale_max = float(self.template_scale_max_var.get())
            scale_step = float(self.template_scale_step_var.get())
        except Exception:
            messagebox.showwarning("提示", "缩放参数格式不正确，请输入数字")
            return
        if scale_min <= 0 or scale_max <= 0 or scale_step <= 0:
            messagebox.showwarning("提示", "缩放参数必须大于 0")
            return
        if scale_min > scale_max:
            scale_min, scale_max = scale_max, scale_min
        if scale_max - scale_min > 2.0:
            messagebox.showwarning("提示", "缩放范围过大，建议控制在 2.0 以内")
            return

        mode = (self.template_preprocess_var.get() or "灰度").strip()
        if mode not in ("灰度", "边缘", "二值"):
            mode = "灰度"

        scope = self.template_scope_var.get()
        x_offset = 0
        y_offset = 0
        search_bgr = self.screenshot_bgr
        if scope == "仅在当前区域":
            rect = self._get_current_roi_phone_px()
            if rect is None:
                messagebox.showwarning("提示", "坐标输入无效")
                return
            x1, y1, x2, y2 = rect
            if x2 - x1 < 2 or y2 - y1 < 2:
                messagebox.showwarning("提示", "区域太小，无法匹配")
                return
            search_bgr = self.screenshot_bgr[y1:y2, x1:x2].copy()
            x_offset, y_offset = x1, y1

        tpl = self.template_bgr
        if tpl is None:
            messagebox.showwarning("提示", "模板图片无效")
            return

        search_proc = self._preprocess_for_template(search_bgr, mode)
        best_val = -1.0
        best_loc: Optional[Tuple[int, int]] = None
        best_scale = 1.0
        best_tw = 0
        best_th = 0

        def frange(a: float, b: float, step: float) -> List[float]:
            vals: List[float] = []
            cur = a
            eps = step / 10.0
            while cur <= b + eps:
                vals.append(float(round(cur, 6)))
                cur += step
            return vals

        scales = frange(scale_min, scale_max, scale_step)
        if not scales:
            scales = [1.0]

        for s in scales:
            try:
                tw = max(1, int(round(tpl.shape[1] * s)))
                th = max(1, int(round(tpl.shape[0] * s)))
                if tw < 2 or th < 2:
                    continue
                if tw > search_proc.shape[1] or th > search_proc.shape[0]:
                    continue

                tpl_scaled = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_AREA)
                tpl_proc = self._preprocess_for_template(tpl_scaled, mode)

                res = cv2.matchTemplate(search_proc, tpl_proc, cv2.TM_CCOEFF_NORMED)
                _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(res)
            except Exception:
                continue

            if max_val > best_val:
                best_val = float(max_val)
                best_loc = (int(max_loc[0]), int(max_loc[1]))
                best_scale = float(s)
                best_tw = int(tw)
                best_th = int(th)

        if best_loc is None:
            messagebox.showinfo("匹配结果", "未找到可用的匹配结果")
            self.clear_template_match()
            return

        self.log(f"模板匹配得分：{best_val:.3f}（阈值 {threshold:.2f}），最佳缩放：{best_scale:.2f}，预处理：{mode}")
        if best_val < threshold:
            messagebox.showinfo("匹配结果", f"未达到阈值，最高得分：{best_val:.3f}")
            self.clear_template_match()
            return

        top_left_x = int(x_offset + best_loc[0])
        top_left_y = int(y_offset + best_loc[1])
        bottom_right_x = int(top_left_x + best_tw)
        bottom_right_y = int(top_left_y + best_th)

        x1_pct, y1_pct = self._phone_px_to_pct(top_left_x, top_left_y)
        x2_pct, y2_pct = self._phone_px_to_pct(bottom_right_x, bottom_right_y)
        roi = RoiPct(x1=x1_pct, y1=y1_pct, x2=x2_pct, y2=y2_pct).normalized().clipped()
        self.template_match_roi = roi
        self._draw_template_match_box()

        if bool(self.template_sync_var.get()):
            self.x1_var.set(f"{roi.x1:.3f}")
            self.y1_var.set(f"{roi.y1:.3f}")
            self.x2_var.set(f"{roi.x2:.3f}")
            self.y2_var.set(f"{roi.y2:.3f}")
            self.draw_roi_from_entries()
            self.log("模板匹配：已同步到坐标")

        messagebox.showinfo("匹配结果", f"匹配成功，得分：{best_val:.3f}，缩放：{best_scale:.2f}")

    def _draw_template_match_box(self) -> None:
        if self.screenshot_pil is None:
            return
        if self.template_match_roi is None:
            return
        roi = self.template_match_roi.normalized().clipped()
        x1_px, y1_px = self._pct_to_phone_px(roi.x1, roi.y1)
        x2_px, y2_px = self._pct_to_phone_px(roi.x2, roi.y2)
        c1x, c1y = self._phone_px_to_canvas(x1_px, y1_px)
        c2x, c2y = self._phone_px_to_canvas(x2_px, y2_px)

        if self.template_rect_id is not None:
            try:
                self.canvas.delete(self.template_rect_id)
            except Exception:
                pass
            self.template_rect_id = None

        self.template_rect_id = self.canvas.create_rectangle(
            c1x,
            c1y,
            c2x,
            c2y,
            outline="#ff4dff",
            width=2,
            tags="template_match",
        )

    def _draw_roi(self, roi: RoiPct) -> None:
        if self.screenshot_pil is None:
            return
        x1_px, y1_px = self._pct_to_phone_px(roi.x1, roi.y1)
        x2_px, y2_px = self._pct_to_phone_px(roi.x2, roi.y2)

        c1x, c1y = self._phone_px_to_canvas(x1_px, y1_px)
        c2x, c2y = self._phone_px_to_canvas(x2_px, y2_px)

        if self.rect_id is not None:
            try:
                self.canvas.delete(self.rect_id)
            except Exception:
                pass
        if self.center_id is not None:
            try:
                self.canvas.delete(self.center_id)
            except Exception:
                pass

        self.rect_id = self.canvas.create_rectangle(
            c1x,
            c1y,
            c2x,
            c2y,
            outline="#00e5ff",
            width=2,
            tags="roi",
        )

        cx, cy = roi.center()
        cx_px, cy_px = self._pct_to_phone_px(cx, cy)
        ccx, ccy = self._phone_px_to_canvas(cx_px, cy_px)
        self.center_id = self.canvas.create_oval(
            ccx - 4,
            ccy - 4,
            ccx + 4,
            ccy + 4,
            outline="#ffcc00",
            width=2,
            tags="roi_center",
        )

    def _draw_ocr_detections(self) -> None:
        """绘制OCR识别结果（红色矩形框+文字标签）"""
        if self.screenshot_pil is None:
            return
        
        # 清除之前的OCR标记
        for rect_id in self.ocr_rect_ids:
            try:
                self.canvas.delete(rect_id)
            except Exception:
                pass
        for text_id in self.ocr_text_ids:
            try:
                self.canvas.delete(text_id)
            except Exception:
                pass
        self.ocr_rect_ids.clear()
        self.ocr_text_ids.clear()
        
        # 绘制新的OCR检测结果
        for det in self.ocr_detections:
            try:
                x1, y1, x2, y2 = det['bbox']
                text = det.get('text', '')
                
                # 转换为画布坐标
                c1x, c1y = self._phone_px_to_canvas(x1, y1)
                c2x, c2y = self._phone_px_to_canvas(x2, y2)
                
                # 绘制红色矩形框
                rect_id = self.canvas.create_rectangle(
                    c1x, c1y, c2x, c2y,
                    outline="#ff0000",  # 红色
                    width=2,
                    tags="ocr_detection"
                )
                self.ocr_rect_ids.append(rect_id)
                
                # 在框上方绘制文字标签
                if text:
                    label_y = max(c1y - 15, 5)  # 文字位置（框上方，但不超过画布顶部）
                    text_id = self.canvas.create_text(
                        c1x, label_y,
                        text=text,
                        fill="#ff0000",
                        anchor="nw",
                        font=("Arial", 10, "bold"),
                        tags="ocr_text"
                    )
                    self.ocr_text_ids.append(text_id)
            except Exception:
                continue

    def clear_ocr_detections(self) -> None:
        """清除OCR检测框"""
        for rect_id in self.ocr_rect_ids:
            try:
                self.canvas.delete(rect_id)
            except Exception:
                pass
        for text_id in self.ocr_text_ids:
            try:
                self.canvas.delete(text_id)
            except Exception:
                pass
        self.ocr_rect_ids.clear()
        self.ocr_text_ids.clear()
        self.ocr_detections.clear()
        self.log("已清除OCR检测框")

    def _draw_offset_calculator(self) -> None:
        """绘制偏移计算器的标记（锚点A和目标区域B）"""
        if self.screenshot_pil is None:
            return
        
        # 清除之前的标记
        if self.anchor_rect_id is not None:
            try:
                self.canvas.delete(self.anchor_rect_id)
            except Exception:
                pass
            self.anchor_rect_id = None
        if self.anchor_text_id is not None:
            try:
                self.canvas.delete(self.anchor_text_id)
            except Exception:
                pass
            self.anchor_text_id = None
        if self.target_rect_id is not None:
            try:
                self.canvas.delete(self.target_rect_id)
            except Exception:
                pass
            self.target_rect_id = None
        if self.target_text_id is not None:
            try:
                self.canvas.delete(self.target_text_id)
            except Exception:
                pass
            self.target_text_id = None
        if self.target_line_id is not None:
            try:
                self.canvas.delete(self.target_line_id)
            except Exception:
                pass
            self.target_line_id = None
        
        # 绘制锚点A（OCR中心点）
        if self.anchor_center is not None:
            try:
                ax, ay = self.anchor_center
                ax_px, ay_px = self._pct_to_phone_px(ax, ay)
                acx, acy = self._phone_px_to_canvas(ax_px, ay_px)
                
                # 绘制锚点圆圈（绿色）
                self.anchor_rect_id = self.canvas.create_oval(
                    acx - 8, acy - 8, acx + 8, acy + 8,
                    outline="#00ff00",  # 绿色
                    width=3,
                    tags="anchor_point"
                )
                # 绘制锚点标签
                self.anchor_text_id = self.canvas.create_text(
                    acx, acy - 20,
                    text="锚点A",
                    fill="#00ff00",
                    anchor="center",
                    font=("Arial", 11, "bold"),
                    tags="anchor_label"
                )
            except Exception:
                pass
        
        # 绘制目标区域B（手动框选区域）
        if self.target_roi is not None:
            try:
                roi = self.target_roi.normalized().clipped()
                x1_px, y1_px = self._pct_to_phone_px(roi.x1, roi.y1)
                x2_px, y2_px = self._pct_to_phone_px(roi.x2, roi.y2)
                c1x, c1y = self._phone_px_to_canvas(x1_px, y1_px)
                c2x, c2y = self._phone_px_to_canvas(x2_px, y2_px)
                
                # 绘制目标区域矩形（黄色）
                self.target_rect_id = self.canvas.create_rectangle(
                    c1x, c1y, c2x, c2y,
                    outline="#ffff00",  # 黄色
                    width=2,
                    tags="target_roi"
                )
                
                # 绘制目标区域中心点
                cx, cy = roi.center()
                cx_px, cy_px = self._pct_to_phone_px(cx, cy)
                ccx, ccy = self._phone_px_to_canvas(cx_px, cy_px)
                
                # 绘制目标区域标签
                self.target_text_id = self.canvas.create_text(
                    ccx, ccy - 25,
                    text="目标B",
                    fill="#ffff00",
                    anchor="center",
                    font=("Arial", 11, "bold"),
                    tags="target_label"
                )
                
                # 如果锚点也存在，绘制连接线
                if self.anchor_center is not None:
                    ax, ay = self.anchor_center
                    ax_px, ay_px = self._pct_to_phone_px(ax, ay)
                    acx, acy = self._phone_px_to_canvas(ax_px, ay_px)
                    
                    # 绘制虚线连接A和B的中心
                    self.target_line_id = self.canvas.create_line(
                        acx, acy, ccx, ccy,
                        fill="#888888",
                        width=1,
                        dash=(5, 5),
                        tags="offset_line"
                    )
            except Exception:
                pass

    def start_offset_calculator(self) -> None:
        """启动偏移计算器模式"""
        if self.screenshot_bgr is None:
            messagebox.showwarning("提示", "请先获取截图")
            return
        
        self.offset_calculator_mode = True
        self.anchor_center = None
        self.anchor_text_content = ""
        self.target_roi = None
        self.redraw_screenshot()
        self.log("✅ 偏移计算器已启动，请先进行文字匹配以设置锚点A，然后框选目标区域B")

    def clear_offset_calculator(self) -> None:
        """清除偏移计算器标记"""
        self.offset_calculator_mode = False
        self.anchor_center = None
        self.anchor_text_content = ""
        self.target_roi = None
        self.redraw_screenshot()
        self.log("已清除偏移计算器标记")

    def _calculate_offset(self) -> None:
        """计算锚点A到目标B的偏移量并输出YAML配置"""
        if self.anchor_center is None or self.target_roi is None:
            return
        
        try:
            # 计算锚点A的中心（像素坐标）
            ax_pct, ay_pct = self.anchor_center
            ax_px, ay_px = self._pct_to_phone_px(ax_pct, ay_pct)
            
            # 计算目标B的中心（百分比坐标和像素坐标）
            target_center_pct = self.target_roi.center()
            bx_pct, by_pct = target_center_pct
            bx_px, by_px = self._pct_to_phone_px(bx_pct, by_pct)
            
            # 计算像素偏移量（从A到B）
            offset_x = bx_px - ax_px
            offset_y = by_px - ay_px
            
            # 生成YAML配置
            yaml_config = f"""
# 自动生成的偏移配置
anchor_text: "{self.anchor_text_content}"
target_center: [{bx_pct:.3f}, {by_pct:.3f}]  # 目标区域中心百分比坐标
offset_from_anchor: [{offset_x}, {offset_y}]  # 像素偏移量 (从锚点A到目标B)
"""
            
            self.log("=" * 60)
            self.log("✅ 偏移计算完成")
            self.log("=" * 60)
            self.log(yaml_config)
            self.log("=" * 60)
            
            # 更新画布显示（显示计算结果，用户可以手动清除标记）
            self.redraw_screenshot()
            
            # 注意：不自动清除状态，让用户可以看到计算结果，可以通过"清除偏移标记"按钮手动清除
            
        except Exception as e:
            self.log(f"偏移计算失败：{e}")
            messagebox.showerror("计算失败", f"偏移计算失败：\n{e}")

    def on_canvas_press(self, event) -> None:
        if self.screenshot_pil is None:
            return
        if not self._is_point_on_image(event.x, event.y):
            return
        self.rect_start_canvas = (int(event.x), int(event.y))
        if self.rect_id is not None:
            try:
                self.canvas.delete(self.rect_id)
            except Exception:
                pass
            self.rect_id = None
        if self.center_id is not None:
            try:
                self.canvas.delete(self.center_id)
            except Exception:
                pass
            self.center_id = None

    def on_canvas_drag(self, event) -> None:
        if self.screenshot_pil is None or self.rect_start_canvas is None:
            return
        x0, y0 = self.rect_start_canvas
        x1, y1 = int(event.x), int(event.y)
        if self.rect_id is not None:
            try:
                self.canvas.delete(self.rect_id)
            except Exception:
                pass
        self.rect_id = self.canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            outline="#00e5ff",
            width=2,
            tags="roi",
        )

    def on_canvas_release(self, event) -> None:
        if self.screenshot_pil is None or self.rect_start_canvas is None:
            return
        x0, y0 = self.rect_start_canvas
        x1, y1 = int(event.x), int(event.y)
        self.rect_start_canvas = None

        if not self._is_point_on_image(x0, y0) or not self._is_point_on_image(x1, y1):
            return

        x0_px, y0_px = self._canvas_to_phone_px(x0, y0)
        x1_px, y1_px = self._canvas_to_phone_px(x1, y1)

        x0_pct, y0_pct = self._phone_px_to_pct(x0_px, y0_px)
        x1_pct, y1_pct = self._phone_px_to_pct(x1_px, y1_px)

        roi = RoiPct(x1=x0_pct, y1=y0_pct, x2=x1_pct, y2=y1_pct).normalized().clipped()
        self.x1_var.set(f"{roi.x1:.3f}")
        self.y1_var.set(f"{roi.y1:.3f}")
        self.x2_var.set(f"{roi.x2:.3f}")
        self.y2_var.set(f"{roi.y2:.3f}")
        self._draw_roi(roi)
        
        # 功能4：任意区域坐标拾取 - 立即输出坐标信息
        x1_px_final = int(roi.x1 * self.phone_width)
        y1_px_final = int(roi.y1 * self.phone_height)
        x2_px_final = int(roi.x2 * self.phone_width)
        y2_px_final = int(roi.y2 * self.phone_height)
        
        coord_log = f"""✅ 区域坐标拾取完成

百分比坐标: [{roi.x1:.3f}, {roi.y1:.3f}, {roi.x2:.3f}, {roi.y2:.3f}]
像素坐标: [{x1_px_final}, {y1_px_final}, {x2_px_final}, {y2_px_final}]

YAML search_region 格式:
search_region:
  x1: {roi.x1:.3f}
  y1: {roi.y1:.3f}
  x2: {roi.x2:.3f}
  y2: {roi.y2:.3f}"""
        
        self.log(coord_log)
        
        # 如果处于偏移计算模式，保存为目标区域B
        if self.offset_calculator_mode and self.anchor_center is not None:
            self.target_roi = roi
            self._calculate_offset()
        
        self.log(f"已通过拖动选择区域，并同步到输入框：({roi.x1:.3f}, {roi.y1:.3f}) 到 ({roi.x2:.3f}, {roi.y2:.3f})")

    def _is_point_on_image(self, cx: int, cy: int) -> bool:
        return (
            self.canvas_offset_x <= cx <= self.canvas_offset_x + self.display_width
            and self.canvas_offset_y <= cy <= self.canvas_offset_y + self.display_height
        )

    def _canvas_to_phone_px(self, cx: int, cy: int) -> Tuple[int, int]:
        x = int((cx - self.canvas_offset_x) / max(1e-6, self.canvas_scale))
        y = int((cy - self.canvas_offset_y) / max(1e-6, self.canvas_scale))
        x = int(max(0, min(self.phone_width - 1, x)))
        y = int(max(0, min(self.phone_height - 1, y)))
        return x, y

    def _phone_px_to_canvas(self, x: int, y: int) -> Tuple[int, int]:
        cx = int(self.canvas_offset_x + x * self.canvas_scale)
        cy = int(self.canvas_offset_y + y * self.canvas_scale)
        return cx, cy

    def _phone_px_to_pct(self, x: int, y: int) -> Tuple[float, float]:
        if self.phone_width <= 0 or self.phone_height <= 0:
            return 0.0, 0.0
        return float(x / self.phone_width), float(y / self.phone_height)

    def _pct_to_phone_px(self, x: float, y: float) -> Tuple[int, int]:
        x_px = int(round(x * self.phone_width))
        y_px = int(round(y * self.phone_height))
        x_px = int(max(0, min(self.phone_width - 1, x_px)))
        y_px = int(max(0, min(self.phone_height - 1, y_px)))
        return x_px, y_px

    def test_click_center(self) -> None:
        if not self.require_device():
            return
        roi = self._get_entries_roi()
        if roi is None:
            messagebox.showwarning("提示", "坐标输入无效")
            return
        cx, cy = roi.center()
        x_px, y_px = self._pct_to_phone_px(cx, cy)
        try:
            self.device.click(x_px, y_px)
            self.log(f"已点击中心点：({cx:.3f}, {cy:.3f}) -> ({x_px}, {y_px})")
        except AdbError as e:
            messagebox.showerror("点击失败", f"点击失败：\n{e}")
            self.log(f"点击失败：{e}")

    def test_ocr_roi(self) -> None:
        if not self.require_device():
            return
        if self.screenshot_bgr is None:
            messagebox.showwarning("提示", "请先获取截图")
            return
        roi = self._get_entries_roi()
        if roi is None:
            messagebox.showwarning("提示", "坐标输入无效")
            return

        x1_px, y1_px = self._pct_to_phone_px(roi.x1, roi.y1)
        x2_px, y2_px = self._pct_to_phone_px(roi.x2, roi.y2)
        x1, x2 = int(min(x1_px, x2_px)), int(max(x1_px, x2_px))
        y1, y2 = int(min(y1_px, y2_px)), int(max(y1_px, y2_px))

        if x2 - x1 < 2 or y2 - y1 < 2:
            messagebox.showwarning("提示", "区域太小，无法识别")
            return

        crop = self.screenshot_bgr[y1:y2, x1:x2].copy()
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        up = cv2.resize(gray, (gray.shape[1] * 2, gray.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
        _, thr = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        try:
            if self.ocr_engine is None:
                from rapidocr_onnxruntime import RapidOCR

                self.ocr_engine = RapidOCR()
                self.log("文字识别引擎已初始化")

            # 使用新的OCR方法（返回检测结果）
            binary_full = self._preprocess_for_text(self.screenshot_bgr)
            result = self.ocr_engine(binary_full)
            if isinstance(result, tuple) and len(result) >= 1:
                detections_raw = result[0]
            else:
                detections_raw = result
            
            if not detections_raw:
                self.ocr_detections = []
                self.redraw_screenshot()
                self.log("未识别到文字")
                messagebox.showinfo("识别结果", "未识别到文字")
                return
            
            # 处理检测结果
            self.ocr_detections = []
            texts_list = []
            for item in detections_raw:
                try:
                    if not item or len(item) < 3:
                        continue
                    bbox = item[0]
                    text = str(item[1]).strip()
                    confidence = float(item[2]) if len(item) > 2 else 0.0
                    
                    if text:
                        texts_list.append(text)
                        if bbox and len(bbox) >= 4:
                            xs = [p[0] for p in bbox]
                            ys = [p[1] for p in bbox]
                            # 全屏OCR时，需要除以2（因为预处理放大了2倍）
                            x1 = int(min(xs) / 2)
                            y1 = int(min(ys) / 2)
                            x2 = int(max(xs) / 2)
                            y2 = int(max(ys) / 2)
                            self.ocr_detections.append({
                                'bbox': (x1, y1, x2, y2),
                                'text': text,
                                'confidence': confidence
                            })
                except Exception:
                    continue
            
            # 功能2：OCR结果可视化 - 重绘画布
            self.redraw_screenshot()
            
            msg = "\n".join(texts_list)
            self.log(f"文字识别完成，识别到 {len(self.ocr_detections)} 个文字区域")
            messagebox.showinfo("识别结果", msg)
        except Exception as e:
            messagebox.showerror("识别失败", f"文字识别失败：\n{e}")
            self.log(f"文字识别失败：{e}")

    def _format_rapidocr_result(self, result: Any) -> List[str]:
        if result is None:
            return []
        if isinstance(result, tuple) and len(result) >= 1:
            result_data = result[0]
        else:
            result_data = result

        if not result_data:
            return []

        texts: List[str] = []
        try:
            for item in result_data:
                if not item or len(item) < 3:
                    continue
                text = str(item[1])
                score = float(item[2])
                texts.append(f"{text}（置信度 {score:.2f}）")
        except Exception:
            try:
                texts = [str(result_data)]
            except Exception:
                texts = []
        return texts

    def load_yaml(self) -> None:
        try:
            current_path = (self.yaml_path_var.get() or "").strip() if hasattr(self, "yaml_path_var") else ""
            if current_path:
                self.yaml_path = Path(current_path)
            if self.yaml_path.exists():
                with open(self.yaml_path, "r", encoding="utf-8") as f:
                    self.yaml_data = yaml.safe_load(f) or {}
                self.log(f"已加载配置文件：{self.yaml_path}")
            else:
                self.yaml_data = {}
                self.log(f"未找到配置文件，稍后可保存生成：{self.yaml_path}")
            if hasattr(self, "yaml_path_var"):
                self.yaml_path_var.set(str(self.yaml_path))
            self.populate_tree()
        except Exception as e:
            self.yaml_data = {}
            self.populate_tree()
            messagebox.showerror("加载失败", f"加载配置文件失败：\n{e}")
            self.log(f"加载配置文件失败：{e}")

    def populate_tree(self) -> None:
        for item in self.tree.get_children(""):
            self.tree.delete(item)
        self.tree_item_map.clear()

        def add_node(parent_iid: str, key: str, value: Any, parent_obj: Any, parent_key: Union[str, int]):
            text = str(key)
            roi = self._extract_roi_pct_from_node(value) if isinstance(value, dict) else None
            if isinstance(value, dict) and roi is not None:
                roi = roi.normalized().clipped()
                iid = self.tree.insert(
                    parent_iid,
                    "end",
                    text=text,
                    values=("区域", f"{roi.x1:.3f}", f"{roi.y1:.3f}", f"{roi.x2:.3f}", f"{roi.y2:.3f}"),
                )
                fmt = self._roi_format_of_node(value)
                self.tree_item_map[iid] = (parent_obj, parent_key, fmt)
                return

            if isinstance(value, dict):
                iid = self.tree.insert(parent_iid, "end", text=text, values=("字典", "", "", "", ""))
                for k2, v2 in value.items():
                    add_node(iid, str(k2), v2, value, k2)
                return

            if isinstance(value, list):
                iid = self.tree.insert(parent_iid, "end", text=text, values=("列表", "", "", "", ""))
                for idx, item in enumerate(value):
                    label = f"[{idx}]"
                    if isinstance(item, dict) and "label" in item:
                        label = f"[{idx}] {item.get('label')}"
                    add_node(iid, label, item, value, idx)
                return

            self.tree.insert(parent_iid, "end", text=text, values=("值", "", "", "", ""))

        root_iid = ""
        if isinstance(self.yaml_data, dict):
            for k, v in self.yaml_data.items():
                add_node(root_iid, str(k), v, self.yaml_data, k)

    def _roi_format_of_node(self, node: Dict[str, Any]) -> str:
        if all(k in node for k in ("x_min", "x_max", "y_min", "y_max")):
            return "pct"
        if all(k in node for k in ("x1_px", "x2_px", "y1_px", "y2_px")):
            return "px"
        if "coords" in node and "y_coords" in node:
            return "points"
        return "unknown"

    def _extract_roi_pct_from_node(self, node: Dict[str, Any]) -> Optional[RoiPct]:
        try:
            if all(k in node for k in ("x_min", "x_max", "y_min", "y_max")):
                return RoiPct(
                    x1=float(node["x_min"]),
                    y1=float(node["y_min"]),
                    x2=float(node["x_max"]),
                    y2=float(node["y_max"]),
                )
            if all(k in node for k in ("x1_px", "x2_px", "y1_px", "y2_px")):
                return RoiPct(
                    x1=float(node["x1_px"]) / self.BASE_WIDTH,
                    y1=float(node["y1_px"]) / self.BASE_HEIGHT,
                    x2=float(node["x2_px"]) / self.BASE_WIDTH,
                    y2=float(node["y2_px"]) / self.BASE_HEIGHT,
                )
            if "coords" in node and "y_coords" in node:
                xs = [float(x) for x in list(node.get("coords") or [])]
                ys = [float(y) for y in list(node.get("y_coords") or [])]
                if not xs or not ys:
                    return None
                return RoiPct(x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys))
        except Exception:
            return None
        return None

    def on_tree_select(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid not in self.tree_item_map:
            return

        parent_obj, parent_key, _fmt = self.tree_item_map[iid]
        try:
            node = parent_obj[parent_key]
        except Exception:
            return

        if not isinstance(node, dict):
            return

        roi = self._extract_roi_pct_from_node(node)
        if roi is None:
            return
        roi = roi.normalized().clipped()
        self.x1_var.set(f"{roi.x1:.3f}")
        self.y1_var.set(f"{roi.y1:.3f}")
        self.x2_var.set(f"{roi.x2:.3f}")
        self.y2_var.set(f"{roi.y2:.3f}")
        self.draw_roi_from_entries()
        self.log("已从配置树选择项加载坐标")

    def save_yaml_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在配置树中选择一个坐标节点")
            return
        iid = sel[0]
        if iid not in self.tree_item_map:
            messagebox.showwarning("提示", "所选节点不是可保存的坐标节点")
            return
        roi = self._get_entries_roi()
        if roi is None:
            messagebox.showwarning("提示", "坐标输入无效")
            return

        parent_obj, parent_key, fmt = self.tree_item_map[iid]
        try:
            node = parent_obj[parent_key]
        except Exception:
            messagebox.showerror("保存失败", "无法定位所选节点")
            return

        if not isinstance(node, dict):
            messagebox.showerror("保存失败", "所选节点数据类型不支持保存")
            return

        roi = roi.normalized().clipped()
        if fmt not in ("pct", "px"):
            messagebox.showwarning("提示", "该节点坐标格式不支持写回保存（仅支持矩形框：百分比或像素格式）")
            return
        if fmt == "px":
            node["x1_px"] = int(round(roi.x1 * self.BASE_WIDTH))
            node["y1_px"] = int(round(roi.y1 * self.BASE_HEIGHT))
            node["x2_px"] = int(round(roi.x2 * self.BASE_WIDTH))
            node["y2_px"] = int(round(roi.y2 * self.BASE_HEIGHT))
        else:
            node["x_min"] = float(round(roi.x1, 3))
            node["y_min"] = float(round(roi.y1, 3))
            node["x_max"] = float(round(roi.x2, 3))
            node["y_max"] = float(round(roi.y2, 3))

        try:
            self.yaml_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.yaml_data, f, allow_unicode=True, sort_keys=False)
            self.populate_tree()
            self.log(f"已保存到配置文件：{self.yaml_path}")
            messagebox.showinfo("保存成功", f"已保存到：\n{self.yaml_path}")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存配置文件失败：\n{e}")
            self.log(f"保存配置文件失败：{e}")

    # ==================== 步骤生成器方法 ====================

    def gen_log(self, msg: str) -> None:
        """步骤生成器专用日志"""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        try:
            self.gen_log_text.insert("end", line)
            self.gen_log_text.see("end")
        except Exception:
            pass

    def sync_coords_from_live(self) -> None:
        """从实时调试 Tab 同步坐标到步骤生成器"""
        try:
            x1 = self.x1_var.get()
            y1 = self.y1_var.get()
            x2 = self.x2_var.get()
            y2 = self.y2_var.get()
            self.gen_x1_var.set(x1)
            self.gen_y1_var.set(y1)
            self.gen_x2_var.set(x2)
            self.gen_y2_var.set(y2)
            self.gen_log(f"已同步坐标: ({x1}, {y1}) -> ({x2}, {y2})")
            # 如果有截图，重绘以显示框选区域
            if self.gen_screenshot_pil is not None:
                self.redraw_gen_screenshot()
        except Exception as e:
            self.gen_log(f"同步坐标失败: {e}")

    def clear_gen_coords(self) -> None:
        """清除步骤生成器的坐标"""
        self.gen_x1_var.set("0.000")
        self.gen_y1_var.set("0.000")
        self.gen_x2_var.set("0.000")
        self.gen_y2_var.set("0.000")
        if self.gen_rect_id is not None and self.gen_canvas is not None:
            try:
                self.gen_canvas.delete(self.gen_rect_id)
            except Exception:
                pass
            self.gen_rect_id = None
        self.gen_log("已清除坐标")

    def refresh_gen_screenshot(self) -> None:
        """刷新步骤生成器的截图"""
        if not self.require_device():
            return
        try:
            self._update_device_resolution()
            img = self.device.screenshot()
            self.gen_screenshot_pil = img
            self.redraw_gen_screenshot()
            self.gen_log("截图获取成功")
        except AdbError as e:
            messagebox.showerror("截图失败", f"截图失败：\n{e}")
            self.gen_log(f"截图失败: {e}")
        except Exception as e:
            messagebox.showerror("截图失败", f"截图失败：\n{e}")
            self.gen_log(f"截图失败: {e}")

    def redraw_gen_screenshot(self) -> None:
        """重绘步骤生成器的截图"""
        if self.gen_canvas is None:
            return
        if self.gen_screenshot_pil is None or self.phone_width <= 0 or self.phone_height <= 0:
            return

        canvas_w = max(1, int(self.gen_canvas.winfo_width()))
        canvas_h = max(1, int(self.gen_canvas.winfo_height()))

        img_ratio = self.phone_width / max(1, self.phone_height)
        canvas_ratio = canvas_w / max(1, canvas_h)

        if img_ratio > canvas_ratio:
            disp_w = canvas_w
            disp_h = int(canvas_w / img_ratio)
        else:
            disp_h = canvas_h
            disp_w = int(canvas_h * img_ratio)

        disp_w = max(1, disp_w)
        disp_h = max(1, disp_h)

        self.gen_display_width = disp_w
        self.gen_display_height = disp_h
        self.gen_canvas_scale = disp_w / max(1, self.phone_width)
        self.gen_canvas_offset_x = int((canvas_w - disp_w) / 2)
        self.gen_canvas_offset_y = int((canvas_h - disp_h) / 2)

        resized = self.gen_screenshot_pil.resize((disp_w, disp_h), Image.LANCZOS)
        self.gen_tk_photo = ImageTk.PhotoImage(resized)

        self.gen_canvas.delete("all")
        self.gen_canvas.create_image(
            self.gen_canvas_offset_x,
            self.gen_canvas_offset_y,
            image=self.gen_tk_photo,
            anchor="nw",
            tags="screenshot",
        )

        # 绘制当前选中的区域
        self._draw_gen_roi()

    def _draw_gen_roi(self) -> None:
        """绘制步骤生成器中的选框"""
        if self.gen_canvas is None or self.gen_screenshot_pil is None:
            return

        try:
            x1 = float(self.gen_x1_var.get())
            y1 = float(self.gen_y1_var.get())
            x2 = float(self.gen_x2_var.get())
            y2 = float(self.gen_y2_var.get())
        except Exception:
            return

        if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
            return

        # 转换为画布坐标
        x1_px = int(x1 * self.phone_width)
        y1_px = int(y1 * self.phone_height)
        x2_px = int(x2 * self.phone_width)
        y2_px = int(y2 * self.phone_height)

        c1x = int(self.gen_canvas_offset_x + x1_px * self.gen_canvas_scale)
        c1y = int(self.gen_canvas_offset_y + y1_px * self.gen_canvas_scale)
        c2x = int(self.gen_canvas_offset_x + x2_px * self.gen_canvas_scale)
        c2y = int(self.gen_canvas_offset_y + y2_px * self.gen_canvas_scale)

        if self.gen_rect_id is not None:
            try:
                self.gen_canvas.delete(self.gen_rect_id)
            except Exception:
                pass

        self.gen_rect_id = self.gen_canvas.create_rectangle(
            c1x, c1y, c2x, c2y,
            outline="#ff6b35",
            width=3,
            tags="gen_roi",
        )

    def _gen_is_point_on_image(self, cx: int, cy: int) -> bool:
        """检查点是否在步骤生成器截图上"""
        return (
            self.gen_canvas_offset_x <= cx <= self.gen_canvas_offset_x + self.gen_display_width
            and self.gen_canvas_offset_y <= cy <= self.gen_canvas_offset_y + self.gen_display_height
        )

    def _gen_canvas_to_pct(self, cx: int, cy: int) -> Tuple[float, float]:
        """将步骤生成器画布坐标转换为百分比坐标"""
        x = (cx - self.gen_canvas_offset_x) / max(1e-6, self.gen_canvas_scale)
        y = (cy - self.gen_canvas_offset_y) / max(1e-6, self.gen_canvas_scale)
        x = max(0, min(self.phone_width - 1, x))
        y = max(0, min(self.phone_height - 1, y))
        x_pct = x / max(1, self.phone_width)
        y_pct = y / max(1, self.phone_height)
        return float(x_pct), float(y_pct)

    def on_gen_canvas_press(self, event) -> None:
        """步骤生成器画布按下事件"""
        if self.gen_screenshot_pil is None:
            return
        if not self._gen_is_point_on_image(event.x, event.y):
            return
        self.gen_rect_start = (int(event.x), int(event.y))
        if self.gen_rect_id is not None:
            try:
                self.gen_canvas.delete(self.gen_rect_id)
            except Exception:
                pass
            self.gen_rect_id = None

    def on_gen_canvas_drag(self, event) -> None:
        """步骤生成器画布拖动事件"""
        if self.gen_screenshot_pil is None or self.gen_rect_start is None:
            return
        x0, y0 = self.gen_rect_start
        x1, y1 = int(event.x), int(event.y)
        if self.gen_rect_id is not None:
            try:
                self.gen_canvas.delete(self.gen_rect_id)
            except Exception:
                pass
        self.gen_rect_id = self.gen_canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="#ff6b35",
            width=3,
            tags="gen_roi",
        )

    def on_gen_canvas_release(self, event) -> None:
        """步骤生成器画布释放事件 - 自动填入坐标"""
        if self.gen_screenshot_pil is None or self.gen_rect_start is None:
            return
        x0, y0 = self.gen_rect_start
        x1, y1 = int(event.x), int(event.y)
        self.gen_rect_start = None

        if not self._gen_is_point_on_image(x0, y0) or not self._gen_is_point_on_image(x1, y1):
            return

        # 转换为百分比坐标
        x0_pct, y0_pct = self._gen_canvas_to_pct(x0, y0)
        x1_pct, y1_pct = self._gen_canvas_to_pct(x1, y1)

        # 规范化坐标
        x_min, x_max = min(x0_pct, x1_pct), max(x0_pct, x1_pct)
        y_min, y_max = min(y0_pct, y1_pct), max(y0_pct, y1_pct)

        # 更新坐标变量
        self.gen_x1_var.set(f"{x_min:.3f}")
        self.gen_y1_var.set(f"{y_min:.3f}")
        self.gen_x2_var.set(f"{x_max:.3f}")
        self.gen_y2_var.set(f"{y_max:.3f}")

        self.gen_log(f"已选择区域: ({x_min:.3f}, {y_min:.3f}) -> ({x_max:.3f}, {y_max:.3f})")

        # V3.1: OCR 智能参数填充
        # 清洗动作类型：移除中文注释，只保留英文部分
        raw_action = self.gen_action_var.get()
        action = raw_action.split(' (')[0].strip()
        if action in ("Check Text", "Wait Text", "Click Text", "Wait Until Disappear", "Assert Exists"):
            self._gen_ocr_auto_fill(x_min, y_min, x_max, y_max)

    def _gen_ocr_auto_fill(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """V3.1: OCR 智能参数填充 - 对选中区域执行 OCR 并填入参数框"""
        if self.screenshot_bgr is None and self.gen_screenshot_pil is None:
            self.gen_log("⚠️ 无截图，无法执行 OCR")
            return

        try:
            # 获取截图 BGR 格式
            if self.gen_screenshot_pil is not None:
                rgb = np.array(self.gen_screenshot_pil)
                if rgb.ndim == 3 and rgb.shape[2] == 3:
                    screenshot_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                else:
                    screenshot_bgr = rgb
            else:
                screenshot_bgr = self.screenshot_bgr

            if screenshot_bgr is None:
                return

            # 转换百分比坐标为像素坐标
            h, w = screenshot_bgr.shape[:2]
            x1_px = int(x1 * w)
            y1_px = int(y1 * h)
            x2_px = int(x2 * w)
            y2_px = int(y2 * h)

            # 裁剪区域
            if x2_px - x1_px < 5 or y2_px - y1_px < 5:
                return

            crop = screenshot_bgr[y1_px:y2_px, x1_px:x2_px].copy()

            # 执行 OCR
            if self.ocr_engine is None:
                from rapidocr_onnxruntime import RapidOCR
                self.ocr_engine = RapidOCR()

            # 预处理
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            up = cv2.resize(gray, (gray.shape[1] * 2, gray.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
            _, thr = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            result = self.ocr_engine(thr)
            if isinstance(result, tuple) and len(result) >= 1:
                detections = result[0]
            else:
                detections = result

            if not detections:
                self.gen_log("⚠️ OCR 未识别到文字")
                return

            # 提取第一个识别结果
            texts = []
            for item in detections:
                if item and len(item) >= 2:
                    text = str(item[1]).strip()
                    if text:
                        texts.append(text)

            if texts:
                recognized_text = texts[0]  # 使用第一个识别结果
                self.gen_param_var.set(recognized_text)
                self.gen_log(f"🧠 已自动填充识别文本: '{recognized_text}'")

        except Exception as e:
            self.gen_log(f"⚠️ OCR 自动填充失败: {e}")

    def _on_gen_category_change(self, category: str) -> None:
        """V5.0: 类别下拉框改变时，更新动作下拉框"""
        actions = list(ACTION_CATEGORIES.get(category, {}).keys())
        self.gen_action_combo.configure(values=actions)
        if actions:
            self.gen_action_var.set(actions[0])

    def _find_category_for_action(self, action: str) -> str:
        """V5.0: 根据动作类型反查所属类别"""
        for category, actions in ACTION_CATEGORIES.items():
            if action in actions:
                return category
        return list(ACTION_CATEGORIES.keys())[0]

    # ==================== V6.0: 变量插入功能 ====================

    def _load_excel_headers(self) -> list:
        """V6.0: 尝试从 Excel 读取表头作为变量名"""
        try:
            import pandas as pd
            from pathlib import Path
            
            # 尝试多个可能的数据文件路径
            paths = []
            if self.excel_path and Path(self.excel_path).exists():
                paths.append(Path(self.excel_path))
                
            paths.extend([
                Path(__file__).parent / "data" / "output.xlsx",
                Path(__file__).parent / "output.xlsx",
                Path(__file__).parent / "data.xlsx",
            ])
            
            for p in paths:
                if p.exists():
                    df = pd.read_excel(p, nrows=0)
                    return list(df.columns)
            
            return []
        except Exception:
            return []

    def _select_excel_path(self):
        """Select Custom Excel File"""
        path = filedialog.askopenfilename(
            title="Select Excel Data",
            filetypes=[("Excel Files", "*.xlsx;*.xls")]
        )
        if path:
            self.excel_path = path
            self._load_variable_buttons()
            messagebox.showinfo("Info", f"Selected: {Path(path).name}")

    def _browse_param_image(self):
        """Select Image for Parameter"""
        path = filedialog.askopenfilename(
            title="Select Template Image",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp")]
        )
        if path:
            self.gen_param_var.set(path)

    def _load_variable_buttons(self) -> None:
        """V6.0: 加载变量快捷按钮 (Grid Layout)"""
        # 清除旧按钮
        for widget in self.gen_var_frame.winfo_children():
            widget.destroy()
        
        # 默认变量列表 (回退值)
        default_vars = ["SKU", "Title", "Price", "Brand", "Size", "Color"]
        
        # 尝试从 Excel 读取
        excel_vars = self._load_excel_headers()
        variables = excel_vars if excel_vars else default_vars
        
        # Grid config
        self.gen_var_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # 创建按钮
        for i, var_name in enumerate(variables[:12]):  # 最多显示12个
            btn = ctk.CTkButton(
                self.gen_var_frame,
                text=f"${{{var_name}}}",
                width=60,
                height=24,
                fg_color="#3a3a3a",
                hover_color="#555",
                font=ctk.CTkFont(size=11),
                command=lambda v=var_name: self._insert_variable(v)
            )
            # 3 Columns
            btn.grid(row=i // 3, column=i % 3, padx=1, pady=1, sticky="ew")

    def _show_variable_menu(self) -> None:
        """V6.0: 显示变量选择菜单"""
        menu = tk.Menu(self.root, tearoff=0)
        
        # 默认变量 + Excel 变量
        default_vars = ["SKU", "Title", "Price", "Brand", "Size", "Color", "Description"]
        excel_vars = self._load_excel_headers()
        
        all_vars = list(dict.fromkeys(excel_vars + default_vars))  # 去重保持顺序
        
        for var_name in all_vars:
            menu.add_command(
                label=f"${{{var_name}}}",
                command=lambda v=var_name: self._insert_variable(v)
            )
        
        menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def _insert_variable(self, var_name: str) -> None:
        """V6.0: 将变量插入到参数输入框"""
        current = self.gen_param_var.get()
        self.gen_param_var.set(current + f"${{{var_name}}}")
        self.gen_log(f"📊 已插入变量: ${{{var_name}}}")

    def gen_test_action(self) -> None:
        """测试当前配置的动作"""
        if not self.require_device():
            return

        # 清洗动作类型：移除中文注释，只保留英文部分
        raw_action = self.gen_action_var.get()
        action = raw_action.split(' (')[0].strip()
        param = self.gen_param_var.get().strip()

        try:
            x1 = float(self.gen_x1_var.get())
            y1 = float(self.gen_y1_var.get())
            x2 = float(self.gen_x2_var.get())
            y2 = float(self.gen_y2_var.get())
        except Exception:
            messagebox.showwarning("提示", "坐标无效")
            return

        # 计算中心点
        cx_pct = (x1 + x2) / 2
        cy_pct = (y1 + y2) / 2
        cx_px = int(cx_pct * self.phone_width)
        cy_px = int(cy_pct * self.phone_height)

        self.gen_log(f"测试动作: {action}")

        try:
            if action == "Click Region" or action == "Click Text":
                # 点击区域中心
                self.device.click(cx_px, cy_px)
                self.gen_log(f"✅ 点击成功: ({cx_px}, {cy_px})")
                # V3.1: 可视化点击位置
                self._gen_draw_click_marker(cx_pct, cy_pct)

            elif action == "Input Text":
                if not param:
                    messagebox.showwarning("提示", "请输入要输入的文本")
                    return
                # 先点击区域，然后输入文本
                self.device.click(cx_px, cy_px)
                time.sleep(0.3)
                # 使用 shell input text 输入
                import shlex
                escaped_text = param.replace(" ", "%s")
                self.device.shell(f"input text {shlex.quote(escaped_text)}")
                self.gen_log(f"✅ 输入成功: '{param}'")

            elif action == "Swipe":
                # 从区域顶部滑动到底部
                x1_px = int(x1 * self.phone_width)
                y1_px = int(y1 * self.phone_height)
                x2_px = int(x2 * self.phone_width)
                y2_px = int(y2 * self.phone_height)
                self.device.swipe(cx_px, y1_px, cx_px, y2_px, 0.5)
                self.gen_log(f"✅ 滑动成功: ({cx_px}, {y1_px}) -> ({cx_px}, {y2_px})")

            elif action == "Long Press":
                # 长按区域中心
                self.device.swipe(cx_px, cy_px, cx_px, cy_px, 1.0)
                self.gen_log(f"✅ 长按成功: ({cx_px}, {cy_px})")

            elif action in ("Check Text", "Check Image", "Wait Element"):
                self.gen_log(f"⚠️ {action} 需要 OCR/模板匹配支持，请使用实时调试 Tab 验证")

            else:
                self.gen_log(f"⚠️ 未知动作类型: {action}")

        except AdbError as e:
            self.gen_log(f"❌ 执行失败: {e}")
            messagebox.showerror("执行失败", f"执行失败：\n{e}")
        except Exception as e:
            self.gen_log(f"❌ 执行失败: {e}")
            messagebox.showerror("执行失败", f"执行失败：\n{e}")

    def _get_action_function_name(self, action: str) -> str:
        """根据动作类型返回对应的函数名"""
        mapping = {
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
        return mapping.get(action, "unknown_action")

    def gen_generate_prompt(self) -> None:
        """生成 AI 指令 Prompt"""
        step = self.gen_step_var.get().strip() or "Step X"
        # 清洗动作类型：移除中文注释，只保留英文部分
        raw_action = self.gen_action_var.get()
        action = raw_action.split(' (')[0].strip()
        param = self.gen_param_var.get().strip()
        context = self.gen_context_text.get("1.0", "end").strip()

        try:
            x1 = float(self.gen_x1_var.get())
            y1 = float(self.gen_y1_var.get())
            x2 = float(self.gen_x2_var.get())
            y2 = float(self.gen_y2_var.get())
        except Exception:
            x1 = y1 = x2 = y2 = 0.0

        func_name = self._get_action_function_name(action)

        # 构建 Prompt
        prompt = f"""【请求实现新步骤】
Step 序号: {step}
操作意图: {context if context else "执行" + action + "操作"}
调用函数: {func_name}
目标坐标: {{ 'x_min': {x1:.3f}, 'x_max': {x2:.3f}, 'y_min': {y1:.3f}, 'y_max': {y2:.3f} }}
额外参数: {param if param else "无"}

请生成对应的 Python 代码块，包含必要的 sleep 和日志打印。
"""

        # 更新预览框
        self.gen_prompt_preview.delete("1.0", "end")
        self.gen_prompt_preview.insert("1.0", prompt)

        # 自动复制到剪贴板
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt)
            self.gen_log("✅ Prompt 已生成并复制到剪贴板")
            messagebox.showinfo("生成成功", "AI 指令已生成并复制到剪贴板！")
        except Exception as e:
            self.gen_log(f"复制到剪贴板失败: {e}")

    def copy_gen_prompt(self) -> None:
        """复制 Prompt 预览框内容到剪贴板"""
        try:
            content = self.gen_prompt_preview.get("1.0", "end").strip()
            if not content:
                messagebox.showwarning("提示", "预览框为空，请先生成 Prompt")
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.gen_log("✅ 已复制到剪贴板")
        except Exception as e:
            self.gen_log(f"复制失败: {e}")
            messagebox.showwarning("复制失败", f"复制失败：\n{e}")

    # ==================== V3.1: 点击可视化 ====================

    def _gen_draw_click_marker(self, cx_pct: float, cy_pct: float) -> None:
        """V3.1: 在画布上绘制点击标记（红色十字星），2秒后自动消失"""
        if self.gen_canvas is None or self.gen_screenshot_pil is None:
            return

        try:
            # 清除之前的标记
            for marker_id in self.gen_click_marker_ids:
                try:
                    self.gen_canvas.delete(marker_id)
                except Exception:
                    pass
            self.gen_click_marker_ids.clear()

            # 计算画布坐标
            cx_px = int(cx_pct * self.phone_width)
            cy_px = int(cy_pct * self.phone_height)
            canvas_x = int(self.gen_canvas_offset_x + cx_px * self.gen_canvas_scale)
            canvas_y = int(self.gen_canvas_offset_y + cy_px * self.gen_canvas_scale)

            # 绘制十字星标记
            marker_size = 15
            line_width = 3

            # 水平线
            h_line = self.gen_canvas.create_line(
                canvas_x - marker_size, canvas_y,
                canvas_x + marker_size, canvas_y,
                fill="#ff0000", width=line_width, tags="click_marker"
            )
            self.gen_click_marker_ids.append(h_line)

            # 垂直线
            v_line = self.gen_canvas.create_line(
                canvas_x, canvas_y - marker_size,
                canvas_x, canvas_y + marker_size,
                fill="#ff0000", width=line_width, tags="click_marker"
            )
            self.gen_click_marker_ids.append(v_line)

            # 中心圆点
            circle = self.gen_canvas.create_oval(
                canvas_x - 5, canvas_y - 5,
                canvas_x + 5, canvas_y + 5,
                fill="#ff0000", outline="#ffffff", width=2, tags="click_marker"
            )
            self.gen_click_marker_ids.append(circle)

            # 2秒后自动消失
            self.root.after(2000, self._gen_clear_click_marker)

        except Exception as e:
            self.gen_log(f"绘制点击标记失败: {e}")

    def _gen_clear_click_marker(self) -> None:
        """清除点击标记"""
        for marker_id in self.gen_click_marker_ids:
            try:
                self.gen_canvas.delete(marker_id)
            except Exception:
                pass
        self.gen_click_marker_ids.clear()

    # ==================== V3.1: 步骤队列系统 ====================

    def gen_add_to_queue(self) -> None:
        """将当前配置加入步骤队列（或保存修改）"""
        step = self.gen_step_var.get().strip() or "Step X"
        # 清洗动作类型：移除中文注释，只保留英文部分
        raw_action = self.gen_action_var.get()
        action = raw_action.split(' (')[0].strip()
        param = self.gen_param_var.get().strip()
        context = self.gen_context_text.get("1.0", "end").strip()

        try:
            x1 = float(self.gen_x1_var.get())
            y1 = float(self.gen_y1_var.get())
            x2 = float(self.gen_x2_var.get())
            y2 = float(self.gen_y2_var.get())
        except Exception:
            x1 = y1 = x2 = y2 = 0.0

        # 创建步骤数据（使用清洗后的纯英文 action）
        step_data = {
            "step": step,
            "action": action,
            "param": param,
            "context": context,
            "coords": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        }

        # V3.2: 编辑模式 - 更新现有步骤
        if self.gen_edit_mode and 0 <= self.gen_edit_index < len(self.gen_step_queue):
            self.gen_step_queue[self.gen_edit_index] = step_data
            # 更新列表显示
            display_text = f"{step}: {action}"
            if param:
                display_text += f" ({param[:15]}...)" if len(param) > 15 else f" ({param})"
            self.gen_queue_listbox.delete(self.gen_edit_index)
            self.gen_queue_listbox.insert(self.gen_edit_index, display_text)
            self.gen_log(f"✅ 已保存修改: {step} - {action}")
            # 退出编辑模式
            self._gen_exit_edit_mode()
            self._gen_autosave()  # V3.3: 自动保存
        else:
            # 加入队列
            self.gen_step_queue.append(step_data)

            # 更新列表显示
            display_text = f"{step}: {action}"
            if param:
                display_text += f" ({param[:15]}...)" if len(param) > 15 else f" ({param})"
            self.gen_queue_listbox.insert(tk.END, display_text)

            self.gen_log(f"✅ 已加入队列: {step} - {action}")

            # 清空输入框并自动递增 Step 序号
            self._gen_auto_increment_step()
            self.gen_param_var.set("")
            self.gen_context_text.delete("1.0", "end")
            self.clear_gen_coords()
            self._gen_autosave()  # V3.3: 自动保存

    def _gen_auto_increment_step(self) -> None:
        """自动递增 Step 序号"""
        current = self.gen_step_var.get().strip()
        # 尝试提取数字并递增
        import re
        match = re.search(r'(\d+)', current)
        if match:
            num = int(match.group(1))
            new_step = current.replace(match.group(1), str(num + 1))
            self.gen_step_var.set(new_step)
        else:
            # 如果没有数字，添加数字
            self.gen_step_var.set(f"{current} 2")

    def gen_clear_queue(self) -> None:
        """清空步骤队列（V3.3: 安全确认）"""
        if not self.gen_step_queue:
            self.gen_log("队列已为空")
            return

        # V3.3: 安全确认
        confirm = messagebox.askyesno(
            "确认清空",
            "确定要清空所有步骤吗？此操作无法撤销。"
        )
        if not confirm:
            return

        self.gen_step_queue.clear()
        self.gen_queue_listbox.delete(0, tk.END)
        self._gen_exit_edit_mode()  # V3.2: 退出编辑模式
        self._gen_autosave()  # V3.3: 自动保存
        self.gen_log("已清空步骤队列")

    def gen_remove_selected_step(self) -> None:
        """删除选中的步骤"""
        selection = self.gen_queue_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要删除的步骤")
            return

        idx = selection[0]
        if 0 <= idx < len(self.gen_step_queue):
            removed = self.gen_step_queue.pop(idx)
            self.gen_queue_listbox.delete(idx)
            self._gen_autosave()  # V3.3: 自动保存
            self.gen_log(f"已删除步骤: {removed.get('step', 'Unknown')}")

    def gen_export_all_prompts(self) -> None:
        """导出全部步骤的 AI 指令（V3.2: 自动重新编号）"""
        if not self.gen_step_queue:
            messagebox.showwarning("提示", "步骤队列为空，请先添加步骤")
            return

        # 构建批量 Prompt
        lines = ["【请求批量实现以下步骤】\n"]

        # V3.2: 自动重新编号 Step 1, 2, 3...
        for i, step_data in enumerate(self.gen_step_queue, 1):
            action = step_data.get("action", "Unknown")
            param = step_data.get("param", "")
            context = step_data.get("context", "")
            coords = step_data.get("coords", {})

            func_name = self._get_action_function_name(action)

            x1 = coords.get("x1", 0)
            y1 = coords.get("y1", 0)
            x2 = coords.get("x2", 0)
            y2 = coords.get("y2", 0)

            # V3.2: 使用自动编号而非原始 step 名称
            step_prompt = f"""
Step {i}: {action}
  - 操作意图: {context if context else "执行" + action + "操作"}
  - 调用函数: {func_name}
  - 目标坐标: {{ 'x_min': {x1:.3f}, 'x_max': {x2:.3f}, 'y_min': {y1:.3f}, 'y_max': {y2:.3f} }}
  - 额外参数: {param if param else "无"}
"""
            lines.append(step_prompt)

        lines.append("\n请将上述步骤合并为一个完整的 Python 函数，包含必要的 sleep 和日志打印。")

        full_prompt = "".join(lines)

        # 更新预览框
        self.gen_prompt_preview.delete("1.0", "end")
        self.gen_prompt_preview.insert("1.0", full_prompt)

        # 复制到剪贴板
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(full_prompt)
            self.gen_log(f"✅ 已导出 {len(self.gen_step_queue)} 个步骤到剪贴板")
            messagebox.showinfo("导出成功", f"已导出 {len(self.gen_step_queue)} 个步骤的 AI 指令到剪贴板！")
        except Exception as e:
            self.gen_log(f"导出失败: {e}")
            messagebox.showerror("导出失败", f"导出失败：\n{e}")

    # ==================== V3.2: 编辑模式与排序 ====================

    def _gen_on_queue_double_click(self, event) -> None:
        """V3.2: 双击步骤进入编辑模式"""
        selection = self.gen_queue_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if 0 <= idx < len(self.gen_step_queue):
            self._gen_enter_edit_mode(idx)

    def _gen_enter_edit_mode(self, idx: int) -> None:
        """V3.2: 进入编辑模式，回填数据"""
        if idx < 0 or idx >= len(self.gen_step_queue):
            return

        step_data = self.gen_step_queue[idx]

        # 回填数据
        self.gen_step_var.set(step_data.get("step", "Step X"))
        self.gen_action_var.set(step_data.get("action", "Click Region"))
        self.gen_param_var.set(step_data.get("param", ""))

        # 回填 AI 备注
        self.gen_context_text.delete("1.0", "end")
        self.gen_context_text.insert("1.0", step_data.get("context", ""))

        # 回填坐标
        coords = step_data.get("coords", {})
        self.gen_x1_var.set(f"{coords.get('x1', 0):.3f}")
        self.gen_y1_var.set(f"{coords.get('y1', 0):.3f}")
        self.gen_x2_var.set(f"{coords.get('x2', 0):.3f}")
        self.gen_y2_var.set(f"{coords.get('y2', 0):.3f}")

        # 重绘画布以显示选框
        if self.gen_screenshot_pil is not None:
            self.redraw_gen_screenshot()

        # 设置编辑状态
        self.gen_edit_mode = True
        self.gen_edit_index = idx

        # 更新按钮外观
        self.btn_add_to_queue.configure(text="💾 保存修改", fg_color="#27ae60")
        # 显示取消按钮
        self.btn_cancel_edit.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))
        # 隐藏导出按钮
        self.btn_export_all.grid_forget()

        self.gen_log(f"✏️ 编辑模式: 正在编辑 {step_data.get('step', 'Unknown')}")

    def _gen_exit_edit_mode(self) -> None:
        """V3.2: 退出编辑模式"""
        self.gen_edit_mode = False
        self.gen_edit_index = -1

        # 恢复按钮外观
        self.btn_add_to_queue.configure(text="➕ 加入队列", fg_color="#3498db")
        # 隐藏取消按钮
        self.btn_cancel_edit.grid_forget()
        # 恢复导出按钮
        self.btn_export_all.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        # 清空输入框
        self.gen_param_var.set("")
        self.gen_context_text.delete("1.0", "end")
        self.clear_gen_coords()
        self.gen_step_var.set(f"Step {len(self.gen_step_queue) + 1}")

    def gen_cancel_edit(self) -> None:
        """V3.2: 取消编辑，放弃修改"""
        self._gen_exit_edit_mode()
        self.gen_log("已取消编辑")

    def gen_move_step_up(self) -> None:
        """V3.2: 上移选中的步骤"""
        selection = self.gen_queue_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要移动的步骤")
            return

        idx = selection[0]
        if idx <= 0:
            return  # 已经是第一个

        # 交换数据
        self.gen_step_queue[idx], self.gen_step_queue[idx - 1] = \
            self.gen_step_queue[idx - 1], self.gen_step_queue[idx]

        # 刷新列表显示
        self._gen_refresh_queue_listbox()

        # 保持选中状态
        self.gen_queue_listbox.selection_clear(0, tk.END)
        self.gen_queue_listbox.selection_set(idx - 1)
        self.gen_log(f"⬆️ 已上移步骤")

    def gen_move_step_down(self) -> None:
        """V3.2: 下移选中的步骤"""
        selection = self.gen_queue_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要移动的步骤")
            return

        idx = selection[0]
        if idx >= len(self.gen_step_queue) - 1:
            return  # 已经是最后一个

        # 交换数据
        self.gen_step_queue[idx], self.gen_step_queue[idx + 1] = \
            self.gen_step_queue[idx + 1], self.gen_step_queue[idx]

        # 刷新列表显示
        self._gen_refresh_queue_listbox()

        # 保持选中状态
        self.gen_queue_listbox.selection_clear(0, tk.END)
        self.gen_queue_listbox.selection_set(idx + 1)
        self.gen_log(f"⬇️ 已下移步骤")

    def _gen_refresh_queue_listbox(self) -> None:
        """V6.0: 刷新列表显示 - 带缩进和图标"""
        self.gen_queue_listbox.delete(0, tk.END)
        
        indent_level = 0
        for i, step_data in enumerate(self.gen_step_queue):
            step = step_data.get("step", f"Step {i+1}")
            action = step_data.get("action", "Unknown")
            param = step_data.get("param", "")
            context = step_data.get("context", "")
            
            # 缩进处理: END 节点先减少缩进
            if action in ("END IF", "END LOOP"):
                indent_level = max(0, indent_level - 1)
            
            # 构建缩进前缀
            if indent_level > 0:
                prefix = "    " * (indent_level - 1) + "|__ "
            else:
                prefix = ""
            
            # 获取图标
            icon = NODE_STYLES.get(action, {}).get("icon", "?")
            
            # 构建显示文本
            step_num = step.replace("Step ", "") if "Step " in step else str(i + 1)
            display_text = f"{prefix}[{step_num}] {icon} {action}"
            
            # 添加参数预览
            if param:
                param_preview = param[:12] + "..." if len(param) > 12 else param
                display_text += f" | {param_preview}"
            elif context:
                ctx_preview = context[:12] + "..." if len(context) > 12 else context
                display_text += f" | {ctx_preview}"
            
            self.gen_queue_listbox.insert(tk.END, display_text)
            
            # 增加缩进: IF/LOOP 开始节点
            if action in ("IF (Check Text)", "IF (Check Image)", "LOOP (Count)", "LOOP (Until Text)"):
                indent_level += 1

    # ==================== V3.3: 数据持久化 ====================

    def _get_autosave_path(self) -> Path:
        """返回自动保存文件路径"""
        return Path(__file__).parent / "autosave_flow.json"

    def gen_save_flow(self) -> None:
        """V3.3: 保存步骤流程到 JSON 文件"""
        if not self.gen_step_queue:
            messagebox.showwarning("提示", "步骤队列为空，无需保存")
            return

        from tkinter import filedialog
        filepath = filedialog.asksaveasfilename(
            title="保存流程",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile="my_flow.json",
        )

        if not filepath:
            return

        try:
            import json
            # 转换数据为可序列化格式
            export_data = []
            for i, step_data in enumerate(self.gen_step_queue, 1):
                export_data.append({
                    "step_id": i,
                    "step_name": step_data.get("step", f"Step {i}"),
                    "action_type": step_data.get("action", "Click Region"),
                    "params": step_data.get("param", ""),
                    "context": step_data.get("context", ""),
                    "coords": step_data.get("coords", {"x1": 0, "y1": 0, "x2": 0, "y2": 0}),
                })

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            self.gen_log(f"✅ 流程已保存: {filepath}")
            messagebox.showinfo("保存成功", f"流程已保存到:\n{filepath}")

        except Exception as e:
            self.gen_log(f"❌ 保存失败: {e}")
            messagebox.showerror("保存失败", f"保存失败:\n{e}")

    def gen_load_flow(self) -> None:
        """V3.3: 从 JSON 文件加载步骤流程"""
        from tkinter import filedialog
        filepath = filedialog.askopenfilename(
            title="加载流程",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )

        if not filepath:
            return

        # 加载前确认覆盖
        if self.gen_step_queue:
            confirm = messagebox.askyesno(
                "确认覆盖",
                "当前队列不为空，加载将覆盖现有步骤。\n是否继续？"
            )
            if not confirm:
                return

        try:
            import json
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValueError("JSON 格式错误：根元素必须是数组")

            # 清空当前队列
            self.gen_step_queue.clear()

            # 解析并填充队列
            for item in data:
                step_data = {
                    "step": item.get("step_name", item.get("step", f"Step {len(self.gen_step_queue) + 1}")),
                    "action": item.get("action_type", item.get("action", "Click Region")),
                    "param": item.get("params", item.get("param", "")),
                    "context": item.get("context", ""),
                    "coords": item.get("coords", {"x1": 0, "y1": 0, "x2": 0, "y2": 0}),
                }
                self.gen_step_queue.append(step_data)

            # 刷新 UI
            self._gen_refresh_queue_listbox()
            self._gen_exit_edit_mode()

            self.gen_log(f"✅ 已加载 {len(self.gen_step_queue)} 个步骤: {filepath}")
            messagebox.showinfo("加载成功", f"已加载 {len(self.gen_step_queue)} 个步骤")

        except Exception as e:
            self.gen_log(f"❌ 加载失败: {e}")
            messagebox.showerror("加载失败", f"加载失败:\n{e}")

    def gen_run_all_workflow(self) -> None:
        """V4.0: 运行队列中的全部步骤"""
        if not self.require_device():
            return

        if not self.gen_step_queue:
            messagebox.showwarning("提示", "步骤队列为空")
            return

        # 转换步骤队列为 WorkflowRunner 兼容格式
        workflow_steps = []
        for i, step_data in enumerate(self.gen_step_queue, 1):
            workflow_steps.append({
                "step_id": i,
                "step_name": step_data.get("step", f"Step {i}"),
                "action_type": step_data.get("action", "Click Region"),
                "params": step_data.get("param", ""),
                "context": step_data.get("context", ""),
                "coords": step_data.get("coords", {"x1": 0, "y1": 0, "x2": 0, "y2": 0}),
                "retry_count": step_data.get("retry_count", 0),
                "is_optional": step_data.get("is_optional", False),
            })

        self.gen_log(f"🚀 开始运行 {len(workflow_steps)} 个步骤...")

        try:
            from workflow_runner import WorkflowRunner

            # 创建 WorkflowRunner 实例
            runner = WorkflowRunner(
                self.device,
                phone_width=self.phone_width,
                phone_height=self.phone_height,
            )

            # 逐步执行并更新 UI
            success_count = 0
            fail_count = 0

            for step in workflow_steps:
                step_name = step.get("step_name", f"Step {step['step_id']}")
                action_type = step.get("action_type", "Unknown")

                # 高亮当前步骤
                self._gen_highlight_step(step["step_id"] - 1)
                self.gen_log(f"▶️ [{step['step_id']}/{len(workflow_steps)}] {step_name} - {action_type}")

                # 更新 UI
                self.root.update()

                # 执行步骤
                success = runner.execute_step(step, {})

                if success:
                    success_count += 1
                    self.gen_log(f"✅ 完成: {step_name}")
                else:
                    fail_count += 1
                    is_optional = step.get("is_optional", False)
                    if is_optional:
                        self.gen_log(f"⚠️ 步骤失败 (可选): {step_name}")
                    else:
                        self.gen_log(f"❌ 步骤失败: {step_name}")
                        messagebox.showerror("执行失败", f"步骤 [{step['step_id']}] {step_name} 执行失败")
                        break

            # 清除高亮
            self._gen_clear_highlight()

            # 汇总结果
            self.gen_log(f"🏁 执行完成: {success_count} 成功, {fail_count} 失败")
            if fail_count == 0:
                messagebox.showinfo("执行完成", f"全部 {len(workflow_steps)} 个步骤执行成功！")

        except ImportError:
            self.gen_log("❌ 未找到 workflow_runner.py")
            messagebox.showerror("错误", "未找到 workflow_runner.py\n请确保该文件在同一目录下")
        except Exception as e:
            self.gen_log(f"❌ 执行失败: {e}")
            messagebox.showerror("执行失败", f"执行失败:\n{e}")

    def _gen_highlight_step(self, index: int) -> None:
        """高亮步骤队列中的指定步骤"""
        try:
            self.gen_queue_listbox.selection_clear(0, tk.END)
            self.gen_queue_listbox.selection_set(index)
            self.gen_queue_listbox.see(index)
        except Exception:
            pass

    def _gen_clear_highlight(self) -> None:
        """清除步骤高亮"""
        try:
            self.gen_queue_listbox.selection_clear(0, tk.END)
        except Exception:
            pass

    def _gen_autosave(self) -> None:
        """V3.3: 自动保存到 autosave_flow.json"""
        try:
            import json
            autosave_path = self._get_autosave_path()

            if not self.gen_step_queue:
                # 队列为空时删除自动保存文件
                if autosave_path.exists():
                    autosave_path.unlink()
                return

            export_data = []
            for i, step_data in enumerate(self.gen_step_queue, 1):
                export_data.append({
                    "step_id": i,
                    "step_name": step_data.get("step", f"Step {i}"),
                    "action_type": step_data.get("action", "Click Region"),
                    "params": step_data.get("param", ""),
                    "context": step_data.get("context", ""),
                    "coords": step_data.get("coords", {"x1": 0, "y1": 0, "x2": 0, "y2": 0}),
                })

            with open(autosave_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

        except Exception:
            pass  # 静默失败，不影响用户操作

    def _gen_autoload(self) -> None:
        """V3.3: 启动时自动恢复上次未保存的工作"""
        try:
            import json
            autosave_path = self._get_autosave_path()

            if not autosave_path.exists():
                return

            with open(autosave_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list) or not data:
                return

            # 询问是否恢复
            confirm = messagebox.askyesno(
                "恢复工作",
                f"检测到上次有 {len(data)} 个未保存的步骤。\n是否恢复？"
            )
            if not confirm:
                # 用户选择不恢复，删除自动保存文件
                autosave_path.unlink()
                return

            # 解析并填充队列
            for item in data:
                step_data = {
                    "step": item.get("step_name", item.get("step", f"Step {len(self.gen_step_queue) + 1}")),
                    "action": item.get("action_type", item.get("action", "Click Region")),
                    "param": item.get("params", item.get("param", "")),
                    "context": item.get("context", ""),
                    "coords": item.get("coords", {"x1": 0, "y1": 0, "x2": 0, "y2": 0}),
                }
                self.gen_step_queue.append(step_data)

            # 刷新 UI
            self._gen_refresh_queue_listbox()
            self.gen_log(f"✅ 已恢复 {len(self.gen_step_queue)} 个步骤")

        except Exception:
            pass  # 静默失败

    # ==================== V4.0: 流程编排器 ====================

    def _build_orchestrator_tab(self) -> None:
        """构建流程编排器 Tab - 左中右三栏布局"""
        self.tab_orchestrator.grid_rowconfigure(0, weight=1)
        self.tab_orchestrator.grid_columnconfigure(0, weight=1)   # 左：节点库
        self.tab_orchestrator.grid_columnconfigure(1, weight=4)   # 中：画布
        self.tab_orchestrator.grid_columnconfigure(2, weight=2)   # 右：属性面板

        # ==================== 左侧：节点库 ====================
        palette_frame = ctk.CTkFrame(self.tab_orchestrator, width=180)
        palette_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        palette_frame.grid_propagate(False)
        palette_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            palette_frame,
            text="📦 节点库",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            palette_frame,
            text="拖拽节点到画布",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))

        # 节点按钮列表
        palette_scroll = ctk.CTkScrollableFrame(palette_frame)
        palette_scroll.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        palette_frame.grid_rowconfigure(2, weight=1)

        for idx, (action_type, style) in enumerate(NODE_STYLES.items()):
            btn = ctk.CTkButton(
                palette_scroll,
                text=f"{style['icon']} {style['label']}",
                fg_color=style["color"],
                hover_color=self._darken_color(style["color"]),
                anchor="w",
                height=36,
                command=lambda at=action_type: self._orch_add_node_from_palette(at),
            )
            btn.grid(row=idx, column=0, sticky="ew", padx=5, pady=3)

        # ==================== 中间：编排画布 ====================
        canvas_frame = ctk.CTkFrame(self.tab_orchestrator)
        canvas_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.orch_canvas = tk.Canvas(
            canvas_frame,
            bg="#1e1e1e",
            highlightthickness=0,
        )
        self.orch_canvas.grid(row=0, column=0, sticky="nsew")

        # 滚动条配置
        h_scroll = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.orch_canvas.xview)
        v_scroll = tk.Scrollbar(canvas_frame, orient="vertical", command=self.orch_canvas.yview)
        
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        
        self.orch_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        # 配置 infinite canvas 扩展时的滚动区域更新
        self.orch_canvas.bind("<Configure>", lambda e: self.orch_canvas.configure(scrollregion=self.orch_canvas.bbox("all")))

        # 画布事件绑定
        self.orch_canvas.bind("<Button-1>", self._orch_on_canvas_click)
        self.orch_canvas.bind("<B1-Motion>", self._orch_on_canvas_drag)
        self.orch_canvas.bind("<ButtonRelease-1>", self._orch_on_canvas_release)
        self.orch_canvas.bind("<Double-Button-1>", self._orch_on_canvas_double_click)
        self.orch_canvas.bind("<Delete>", self._orch_delete_selected_node)
        self.orch_canvas.bind("<BackSpace>", self._orch_delete_selected_node)
        
        # 拖拽画布 (中键 或 右键 或 Ctrl+左键)
        self.orch_canvas.bind("<ButtonPress-2>", self._orch_on_canvas_pan_start)
        self.orch_canvas.bind("<B2-Motion>", self._orch_on_canvas_pan_drag)
        self.orch_canvas.bind("<ButtonPress-3>", self._orch_on_canvas_pan_start) # 临时改右键拖拽测试
        self.orch_canvas.bind("<B3-Motion>", self._orch_on_canvas_pan_drag)
        self.orch_canvas.bind("<Control-ButtonPress-1>", self._orch_on_canvas_pan_start)
        self.orch_canvas.bind("<Control-B1-Motion>", self._orch_on_canvas_pan_drag)

        # 底部工具栏
        toolbar = ctk.CTkFrame(canvas_frame, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        toolbar.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkButton(
            toolbar,
            text="📥 导入 JSON",
            fg_color="#555555",
            command=self._orch_import_json,
        ).grid(row=0, column=0, sticky="ew", padx=3)

        ctk.CTkButton(
            toolbar,
            text="📤 导出 JSON",
            fg_color="#2196F3",
            command=self._orch_export_json,
        ).grid(row=0, column=1, sticky="ew", padx=3)

        ctk.CTkButton(
            toolbar,
            text="▶️ 运行全部",
            fg_color="#4CAF50",
            command=self._orch_run_workflow,
        ).grid(row=0, column=2, sticky="ew", padx=3)

        ctk.CTkButton(
            toolbar,
            text="🔗 自动连接",
            fg_color="#FF9800",
            command=self._orch_auto_connect,
        ).grid(row=0, column=3, sticky="ew", padx=3)

        ctk.CTkButton(
            toolbar,
            text="🗑️ 清空画布",
            fg_color="#F44336",
            command=self._orch_clear_canvas,
        ).grid(row=0, column=4, sticky="ew", padx=3)

        # 第二行工具栏
        ctk.CTkButton(
            toolbar,
            text="🧪 单点测试",
            fg_color="#9C27B0",
            command=self._orch_test_selected_node,
        ).grid(row=1, column=0, sticky="ew", padx=3, pady=(6, 0))

        ctk.CTkButton(
            toolbar,
            text="⏸️ 断点调试",
            fg_color="#607D8B",
            command=self._orch_run_with_breakpoints,
        ).grid(row=1, column=1, sticky="ew", padx=3, pady=(6, 0))

        ctk.CTkButton(
            toolbar,
            text="🔴 设置断点",
            fg_color="#795548",
            command=self._orch_toggle_breakpoint,
        ).grid(row=1, column=2, sticky="ew", padx=3, pady=(6, 0))

        ctk.CTkButton(
            toolbar,
            text="✂️ 断开连接",
            fg_color="#455A64",
            command=self._orch_delete_selected_connection,
        ).grid(row=1, column=3, sticky="ew", padx=3, pady=(6, 0))

        ctk.CTkButton(
            toolbar,
            text="🔗 手动连接",
            fg_color="#00796B",
            command=self._orch_start_manual_connect,
        ).grid(row=1, column=4, sticky="ew", padx=3, pady=(6, 0))

        # 右键菜单绑定
        self.orch_canvas.bind("<Button-3>", self._orch_on_right_click)

        # ==================== 右侧：属性面板 ====================
        prop_frame = ctk.CTkFrame(self.tab_orchestrator, width=280)
        prop_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 10), pady=10)
        prop_frame.grid_propagate(False)
        prop_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            prop_frame,
            text="⚙️ 节点属性",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 15))

        # 步骤名称
        ctk.CTkLabel(prop_frame, text="步骤名称:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.orch_prop_name_entry = ctk.CTkEntry(prop_frame, textvariable=self.orch_prop_name_var)
        self.orch_prop_name_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # 动作类型
        ctk.CTkLabel(prop_frame, text="动作类型:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.orch_prop_action_combo = ctk.CTkComboBox(
            prop_frame,
            variable=self.orch_prop_action_var,
            values=list(NODE_STYLES.keys()),
            state="readonly",
        )
        self.orch_prop_action_combo.grid(row=2, column=1, sticky="ew", padx=10, pady=5)

        # 参数
        ctk.CTkLabel(prop_frame, text="参数:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.orch_prop_params_entry = ctk.CTkEntry(
            prop_frame,
            textvariable=self.orch_prop_params_var,
            placeholder_text="${Variable} 或 eval:..."
        )
        self.orch_prop_params_entry.grid(row=3, column=1, sticky="ew", padx=10, pady=5)

        # 变量快捷插入
        var_frame = ctk.CTkFrame(prop_frame, fg_color="transparent")
        var_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(var_frame, text="快捷变量:", font=ctk.CTkFont(size=11)).pack(side="left")
        for var_name in ["SKU", "Title", "Price", "Brand"]:
            ctk.CTkButton(
                var_frame,
                text=f"${{{var_name}}}",
                width=60,
                height=24,
                fg_color="#333333",
                command=lambda v=var_name: self._orch_insert_variable(v),
            ).pack(side="left", padx=2)

        # 坐标区域
        ctk.CTkLabel(
            prop_frame,
            text="📍 坐标 (百分比)",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(15, 5))

        coord_grid = ctk.CTkFrame(prop_frame, fg_color="transparent")
        coord_grid.grid(row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        coord_grid.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(coord_grid, text="X1:").grid(row=0, column=0, sticky="w", padx=2)
        ctk.CTkEntry(coord_grid, textvariable=self.orch_prop_x1_var, width=60).grid(row=0, column=1, sticky="ew", padx=2)
        ctk.CTkLabel(coord_grid, text="Y1:").grid(row=0, column=2, sticky="w", padx=2)
        ctk.CTkEntry(coord_grid, textvariable=self.orch_prop_y1_var, width=60).grid(row=0, column=3, sticky="ew", padx=2)

        ctk.CTkLabel(coord_grid, text="X2:").grid(row=1, column=0, sticky="w", padx=2, pady=3)
        ctk.CTkEntry(coord_grid, textvariable=self.orch_prop_x2_var, width=60).grid(row=1, column=1, sticky="ew", padx=2)
        ctk.CTkLabel(coord_grid, text="Y2:").grid(row=1, column=2, sticky="w", padx=2)
        ctk.CTkEntry(coord_grid, textvariable=self.orch_prop_y2_var, width=60).grid(row=1, column=3, sticky="ew", padx=2)

        # 从实时调试同步坐标
        ctk.CTkButton(
            prop_frame,
            text="📥 从实时调试同步坐标",
            fg_color="#4a90d9",
            command=self._orch_sync_coords_from_live,
        ).grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=10)

        # 容错设置
        ctk.CTkLabel(
            prop_frame,
            text="🛡️ 容错设置",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(15, 5))

        retry_frame = ctk.CTkFrame(prop_frame, fg_color="transparent")
        retry_frame.grid(row=9, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

        ctk.CTkLabel(retry_frame, text="重试次数:").pack(side="left")
        ctk.CTkEntry(retry_frame, textvariable=self.orch_prop_retry_var, width=50).pack(side="left", padx=5)

        ctk.CTkCheckBox(
            prop_frame,
            text="可选步骤 (失败不中断)",
            variable=self.orch_prop_optional_var,
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        # 保存按钮
        ctk.CTkButton(
            prop_frame,
            text="💾 保存修改",
            fg_color="#2e8b57",
            height=36,
            command=self._orch_save_node_properties,
        ).grid(row=11, column=0, columnspan=2, sticky="ew", padx=10, pady=(15, 5))

        # V7.0: 测试当前节点按钮
        ctk.CTkButton(
            prop_frame,
            text="⚡ 测试当前节点",
            fg_color="#e74c3c",
            height=36,
            command=self._orch_test_selected_node,
        ).grid(row=12, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

        # 提示标签
        self.orch_hint_label = ctk.CTkLabel(
            prop_frame,
            text="点击节点查看属性",
            text_color="#666666",
            font=ctk.CTkFont(size=11),
        )
        if hasattr(self, 'orch_hint_label'):
            self.orch_hint_label.grid(row=13, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        # 绘制初始网格
        self.orch_canvas.bind("<Configure>", lambda e: self._orch_draw_grid())

    def _darken_color(self, hex_color: str, factor: float = 0.8) -> str:
        """将颜色变暗"""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r, g, b = int(r * factor), int(g * factor), int(b * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _orch_draw_grid(self) -> None:
        """绘制画布网格背景"""
        self.orch_canvas.delete("grid")
        w = self.orch_canvas.winfo_width()
        h = self.orch_canvas.winfo_height()
        grid_size = 30
        grid_color = "#2a2a2a"

        for x in range(0, w, grid_size):
            self.orch_canvas.create_line(x, 0, x, h, fill=grid_color, tags="grid")
        for y in range(0, h, grid_size):
            self.orch_canvas.create_line(0, y, w, y, fill=grid_color, tags="grid")

        self.orch_canvas.tag_lower("grid")

    def _orch_refresh_listbox(self) -> None:
        """刷新右侧节点列表"""
        if not hasattr(self, 'gen_queue_listbox'):
            return
            
        self.gen_queue_listbox.delete(0, tk.END)
        
        # 按 Step Name 这里的数字排序 (如果格式为 "Step N")
        try:
            nodes = list(self.orch_nodes.values())
            # 尝试提取 Step 后面的数字排序
            import re
            def sort_key(n):
                match = re.search(r'(\d+)', n.step_name)
                return int(match.group(1)) if match else 999999
            nodes.sort(key=sort_key)
        except:
            # 失败则按创建顺序 (这里用ID/StepName fallback)
            nodes.sort(key=lambda n: n.step_name)
        
        # Cache the sorted node IDs for listbox selection mapping
        self._orch_listbox_cache = [n.id for n in nodes]
        
        for node in nodes:
            display = f"{node.step_name}: {node.action_type}"
            self.gen_queue_listbox.insert(tk.END, display)

    def _orch_scroll_to_node(self, node_id: str) -> None:
        """Scroll canvas to center the specified node"""
        node = self.orch_nodes.get(node_id)
        if not node or not hasattr(self, 'orch_canvas'):
            return
            
        try:
            # 1. Force update scrollregion to ensure it includes all nodes
            self.orch_canvas.update_idletasks() # Ensure layout is up to date
            bbox = self.orch_canvas.bbox("all")
            if not bbox:
                return
            
            # Update scrollregion
            self.orch_canvas.configure(scrollregion=bbox)
            
            # 2. Get region dimensions
            min_x, min_y, max_x, max_y = bbox
            total_w = max_x - min_x
            total_h = max_y - min_y
            
            # Canvas viewport dimensions
            view_w = self.orch_canvas.winfo_width()
            view_h = self.orch_canvas.winfo_height()
            
            # Node center coordinates (assuming ~160x70 size)
            node_cx = node.canvas_x + 80
            node_cy = node.canvas_y + 35
            
            # 3. Calculate scroll fraction (xview_moveto/yview_moveto accept 0.0-1.0)
            # 0.0 means viewport left/top is at min_x/min_y
            # 1.0 means viewport right/bottom is at max_x/max_y (approximately)
            # Formula: fraction = (target_edge - min_edge) / total_dimension
            
            if total_w > view_w and total_w > 0:
                # We want node_cx to be at center of viewport
                # viewport_left = node_cx - view_w / 2
                target_left = node_cx - (view_w / 2)
                
                # Clamp target_left within bounds [min_x, max_x - view_w]
                if target_left < min_x: target_left = min_x
                if target_left > max_x - view_w: target_left = max_x - view_w
                
                fraction_x = (target_left - min_x) / total_w
                self.orch_canvas.xview_moveto(fraction_x)
                
            if total_h > view_h and total_h > 0:
                target_top = node_cy - (view_h / 2)
                
                # Clamp
                if target_top < min_y: target_top = min_y
                if target_top > max_y - view_h: target_top = max_y - view_h
                
                fraction_y = (target_top - min_y) / total_h
                self.orch_canvas.yview_moveto(fraction_y)
                
        except Exception as e:
            print(f"Auto-scroll error: {e}")

    def _on_node_list_select(self, event) -> None:
        """Handle selection from the node listbox"""
        selection = self.gen_queue_listbox.curselection()
        if not selection:
            return
            
        idx = selection[0]
        if hasattr(self, '_orch_listbox_cache') and 0 <= idx < len(self._orch_listbox_cache):
            node_id = self._orch_listbox_cache[idx]
            self._orch_select_node(node_id)
            self._orch_scroll_to_node(node_id)
            # Focus properly on canvas is sometimes desired, but listbox focus is also fine.
            # self.orch_canvas.focus_set()

    def _orch_add_node_from_palette(self, action_type: str) -> None:
        """从节点库添加节点到画布中心"""
        # 计算新节点位置（错开已有节点）
        base_x = 200 + len(self.orch_nodes) * 30
        base_y = 100 + (len(self.orch_nodes) % 5) * 80

        node_id = str(uuid.uuid4())[:8]
        step_name = f"Step {len(self.orch_nodes) + 1}"

        node = WorkflowNode(
            id=node_id,
            action_type=action_type,
            step_name=step_name,
            canvas_x=base_x,
            canvas_y=base_y,
        )

        self.orch_nodes[node_id] = node
        self._orch_draw_node(node)
        self._orch_select_node(node_id)
        self._orch_select_node(node_id)
        self.log(f"[编排] 添加节点: {step_name} ({action_type})")
        self._orch_refresh_listbox()

    def _add_node_to_canvas(self, action_type: str) -> None:
        """V6.0: 从节点库添加节点到画布 (统一接口)"""
        self._orch_add_node_from_palette(action_type)

    def _orch_draw_node(self, node: WorkflowNode) -> None:
        """V7.0: 绘制单个节点 (增强视觉效果)"""
        style = NODE_STYLES.get(node.action_type, {"color": "#666666", "icon": "?", "label": "未知"})

        x, y = node.canvas_x, node.canvas_y
        w, h = 160, 70
        r = 8  # 圆角半径
        is_selected = self.orch_selected_node == node.id
        is_running = hasattr(self, 'orch_running_node') and self.orch_running_node == node.id

        # 清除旧的绘制
        if node.id in self.orch_node_canvas_items:
            for item_id in self.orch_node_canvas_items[node.id]:
                self.orch_canvas.delete(item_id)

        items = []
        
        # V7.12: Running glow effect (pulsing border)
        if is_running:
            # Outer glow
            glow_id = self.orch_canvas.create_rectangle(
                x - 6, y - 6, x + w + 6, y + h + 6,
                fill="", outline="#ff0000", width=4,
                tags=("node", f"node_{node.id}", "running_glow"),
            )
            items.append(glow_id)
            
            # Second glow layer
            glow2_id = self.orch_canvas.create_rectangle(
                x - 3, y - 3, x + w + 3, y + h + 3,
                fill="", outline="#ff4444", width=2,
                tags=("node", f"node_{node.id}", "running_glow"),
            )
            items.append(glow2_id)
        
        # 阴影效果
        shadow_id = self.orch_canvas.create_rectangle(
            x + 3, y + 3, x + w + 3, y + h + 3,
            fill="#0a0a0a", outline="",
            tags=("node", f"node_{node.id}"),
        )
        items.append(shadow_id)

        # 节点背景
        bg_color = style["color"]
        if is_running:
            outline_color = "#ff0000"
            outline_width = 4
        elif is_selected:
            outline_color = "#ffff00"  # Yellow for selection
            outline_width = 3
        else:
            outline_color = "#333333"
            outline_width = 1
        
        rect_id = self.orch_canvas.create_rectangle(
            x, y, x + w, y + h,
            fill=bg_color,
            outline=outline_color,
            width=outline_width,
            tags=("node", f"node_{node.id}"),
        )
        items.append(rect_id)
        
        # 标题栏背景 (深色)
        header_id = self.orch_canvas.create_rectangle(
            x + 1, y + 1, x + w - 1, y + 22,
            fill=self._darken_color(bg_color),
            outline="",
            tags=("node", f"node_{node.id}"),
        )
        items.append(header_id)

        # 节点图标和标题
        title_text = f"{style['icon']} {node.step_name}"
        if len(title_text) > 18:
            title_text = title_text[:16] + "..."

        title_id = self.orch_canvas.create_text(
            x + 10, y + 12,
            text=title_text,
            fill="white",
            font=("Arial", 10, "bold"),
            anchor="w",
            tags=("node", f"node_{node.id}"),
        )
        items.append(title_id)

        # V7.9: Right Icon (Emoji or Image)
        icon_val = style.get("icon", "?")
        icon_x = x + w - 25
        icon_y = y + h // 2 + 5
        
        # Check if Image
        if isinstance(icon_val, str) and icon_val.lower().endswith(('.png', '.jpg')):
             try:
                 if Path(icon_val).exists():
                     # Cache Key
                     cache_key = f"{icon_val}_32"
                     if cache_key not in self.orch_node_images:
                         pil_img = Image.open(icon_val).resize((32, 32))
                         self.orch_node_images[cache_key] = ImageTk.PhotoImage(pil_img)
                     
                     img_obj = self.orch_node_images[cache_key]
                     img_id = self.orch_canvas.create_image(
                         icon_x, icon_y, image=img_obj, tags=("node", f"node_{node.id}")
                     )
                     items.append(img_id)
             except Exception:
                 pass
        else:
             # Emoji/Text
             emoji_id = self.orch_canvas.create_text(
                  icon_x, icon_y,
                  text=icon_val,
                  font=("Segoe UI Emoji", 24),
                  fill="#555",
                  tags=("node", f"node_{node.id}")
             )
             items.append(emoji_id)

        # 动作类型标签
        action_id = self.orch_canvas.create_text(
            x + 10, y + 38,
            text=style["label"],
            fill="#dddddd",
            font=("Arial", 9),
            anchor="w",
            tags=("node", f"node_{node.id}"),
        )
        items.append(action_id)
        
        # 参数预览
        param_text = str(node.params)[:20] if node.params else ""
        if param_text:
            param_id = self.orch_canvas.create_text(
                x + 10, y + 55,
                text=param_text,
                fill="#aaaaaa",
                font=("Arial", 8),
                anchor="w",
                tags=("node", f"node_{node.id}"),
            )
            items.append(param_id)

        # 输入连接点（左侧圆点）
        in_x, in_y = x, y + h // 2
        in_ring_id = self.orch_canvas.create_oval(
            in_x - 8, in_y - 8, in_x + 8, in_y + 8,
            fill="#2a2a2a", outline=bg_color, width=2,
            tags=("input_port", f"input_{node.id}"),
        )
        items.append(in_ring_id)
        in_dot_id = self.orch_canvas.create_oval(
            in_x - 4, in_y - 4, in_x + 4, in_y + 4,
            fill="#ffffff", outline="",
            tags=("input_port", f"input_{node.id}"),
        )
        items.append(in_dot_id)

        # 输出连接点（右侧圆点）
        out_x, out_y = x + w, y + h // 2
        out_ring_id = self.orch_canvas.create_oval(
            out_x - 8, out_y - 8, out_x + 8, out_y + 8,
            fill="#2a2a2a", outline=bg_color, width=2,
            tags=("output_port", f"output_{node.id}"),
        )
        items.append(out_ring_id)
        out_dot_id = self.orch_canvas.create_oval(
            out_x - 4, out_y - 4, out_x + 4, out_y + 4,
            fill="#ffffff", outline="",
            tags=("output_port", f"output_{node.id}"),
        )
        items.append(out_dot_id)

        self.orch_node_canvas_items[node.id] = items

    def _orch_draw_all_nodes(self) -> None:
        """绘制所有节点和连接"""
        self._orch_clear_canvas_items()
        
        # 绘制所有连接
        for from_id, to_id in self.orch_connections:
            self._orch_draw_connection(from_id, to_id)
            
        # 绘制所有节点
        for node in self.orch_nodes.values():
            self._orch_draw_node(node)
            
        # 更新滚动区域
        self.orch_canvas.configure(scrollregion=self.orch_canvas.bbox("all"))

    def _orch_update_connections(self, node_id: str) -> None:
        """更新与指定节点相关的所有连接"""
        # 找出相关的连接
        related_connections = [
            (from_id, to_id) 
            for from_id, to_id in self.orch_connections 
            if from_id == node_id or to_id == node_id
        ]
        
        # 重绘这些连接
        for from_id, to_id in related_connections:
            # 删除旧线
            if (from_id, to_id) in self.orch_connection_lines:
                self.orch_canvas.delete(self.orch_connection_lines[(from_id, to_id)])
            
            # 绘制新线
            self._orch_draw_connection(from_id, to_id)

    def _orch_draw_all_connections(self) -> None:
        """绘制所有连接线"""
        for from_id, to_id in self.orch_connections:
            if (from_id, to_id) not in self.orch_connection_lines:
                self._orch_draw_connection(from_id, to_id)

    def _orch_draw_connection(self, from_id: str, to_id: str) -> None:
        """绘制两个节点之间的连接线（贝塞尔曲线）"""
        if from_id not in self.orch_nodes or to_id not in self.orch_nodes:
            return

        from_node = self.orch_nodes[from_id]
        to_node = self.orch_nodes[to_id]

        # 起点：源节点右侧中心 (新尺寸: 160x70)
        x1 = from_node.canvas_x + 160
        y1 = from_node.canvas_y + 35

        # 终点：目标节点左侧中心
        x2 = to_node.canvas_x
        y2 = to_node.canvas_y + 35

        # 贝塞尔曲线控制点
        cx1 = x1 + abs(x2 - x1) / 3
        cy1 = y1
        cx2 = x2 - abs(x2 - x1) / 3
        cy2 = y2

        # 生成曲线点
        points = []
        for t in [i / 20 for i in range(21)]:
            px = (1-t)**3 * x1 + 3*(1-t)**2*t * cx1 + 3*(1-t)*t**2 * cx2 + t**3 * x2
            py = (1-t)**3 * y1 + 3*(1-t)**2*t * cy1 + 3*(1-t)*t**2 * cy2 + t**3 * y2
            points.extend([px, py])

        # 删除旧线
        key = (from_id, to_id)
        if key in self.orch_connection_lines:
            for item in self.orch_connection_lines[key]:
                self.orch_canvas.delete(item)

        items = []
        
        # 绘制光晕 (更粗的半透明线)
        glow_id = self.orch_canvas.create_line(
            points,
            fill="#4fc3f7",
            width=6,
            smooth=True,
            tags=("connection", f"conn_{from_id}_{to_id}"),
        )
        items.append(glow_id)
        
        # 绘制主线
        line_id = self.orch_canvas.create_line(
            points,
            fill="#81d4fa",
            width=3,
            smooth=True,
            arrow=tk.LAST,
            arrowshape=(12, 15, 6),
            tags=("connection", f"conn_{from_id}_{to_id}"),
        )
        items.append(line_id)
        
        self.orch_connection_lines[key] = items
        self.orch_canvas.tag_lower("connection")

    def _orch_draw_all_connections(self) -> None:
        """重绘所有连接线"""
        for from_id, to_id in self.orch_connections:
            self._orch_draw_connection(from_id, to_id)

    def _on_node_list_select(self, event) -> None:
        """V6.0: 节点列表选择事件"""
        selection = self.gen_queue_listbox.curselection()
        if selection:
            # 获取选中的节点并高亮
            idx = selection[0]
            node_ids = list(self.orch_nodes.keys())
            if idx < len(node_ids):
                node_id = node_ids[idx]
                self._orch_select_node(node_id)

    def _orch_on_canvas_click(self, event) -> None:
        """画布点击事件"""
        self.orch_canvas.focus_set()
        
        # 转换为画布坐标
        cx = self.orch_canvas.canvasx(event.x)
        cy = self.orch_canvas.canvasy(event.y)

        # 检查是否点击了输出端口（开始连接）
        items = self.orch_canvas.find_overlapping(cx - 8, cy - 8, cx + 8, cy + 8)
        for item in items:
            tags = self.orch_canvas.gettags(item)
            for tag in tags:
                if tag.startswith("output_") and tag != "output_port":
                    node_id = tag.replace("output_", "")
                    if node_id in self.orch_nodes:
                        self.orch_connecting_from = node_id
                        return

        # 检查是否点击了节点
        for item in items:
            tags = self.orch_canvas.gettags(item)
            for tag in tags:
                if tag.startswith("node_"):
                    node_id = tag.replace("node_", "")
                    
                    # 手动连接模式：点击目标节点完成连接
                    if self.orch_manual_connect_from and self.orch_manual_connect_from != node_id:
                        from_id = self.orch_manual_connect_from
                        to_id = node_id
                        conn = (from_id, to_id)
                        if conn not in self.orch_connections:
                            self.orch_connections.append(conn)
                            self._orch_draw_connection(from_id, to_id)
                            from_node = self.orch_nodes.get(from_id)
                            to_node = self.orch_nodes.get(to_id)
                            self.log(f"[编排] 🔗 已连接: {from_node.step_name} → {to_node.step_name}")
                        self.orch_manual_connect_from = None
                        if hasattr(self, 'orch_hint_label'):
                            self.orch_hint_label.configure(text="连接完成")
                        return
                    
                    self._orch_select_node(node_id)
                    # 记录拖拽偏移
                    node = self.orch_nodes[node_id]
                    self.orch_drag_node_id = node_id
                    self.orch_drag_offset = (cx - node.canvas_x, cy - node.canvas_y)
                    return

        # 点击空白区域，取消选择和手动连接模式
        self._orch_deselect_node()
        if self.orch_manual_connect_from:
            self.orch_manual_connect_from = None
            if hasattr(self, 'orch_hint_label'):
                self.orch_hint_label.configure(text="手动连接已取消")

    def _orch_on_canvas_drag(self, event) -> None:
        """画布拖拽事件"""
        cx = self.orch_canvas.canvasx(event.x)
        cy = self.orch_canvas.canvasy(event.y)

        # 正在创建连接
        if self.orch_connecting_from:
            if self.orch_temp_line_id:
                self.orch_canvas.delete(self.orch_temp_line_id)

            from_node = self.orch_nodes.get(self.orch_connecting_from)
            if from_node:
                # 修正连接线起点 (160x70)
                x1 = from_node.canvas_x + 160
                y1 = from_node.canvas_y + 35
                self.orch_temp_line_id = self.orch_canvas.create_line(
                    x1, y1, cx, cy,
                    fill="#aaaaaa",
                    width=2,
                    dash=(5, 3),
                )
            return

        # 正在拖拽节点
        if self.orch_drag_node_id:
            node = self.orch_nodes.get(self.orch_drag_node_id)
            if node:
                new_x = cx - self.orch_drag_offset[0]
                new_y = cy - self.orch_drag_offset[1]
                
                # 允许拖拽到负坐标，但限制最小值为 0
                new_x = max(0, new_x)
                new_y = max(0, new_y)
                
                node.canvas_x = new_x
                node.canvas_y = new_y
                
                self._orch_draw_node(node)
                self._orch_update_connections(node.id)
                
                # 动态更新滚动区域
                self.orch_canvas.configure(scrollregion=self.orch_canvas.bbox("all"))

    def _orch_on_canvas_release(self, event) -> None:
        """画布释放事件"""
        cx = self.orch_canvas.canvasx(event.x)
        cy = self.orch_canvas.canvasy(event.y)

        # 完成连接
        if self.orch_connecting_from:
            if self.orch_temp_line_id:
                self.orch_canvas.delete(self.orch_temp_line_id)
                self.orch_temp_line_id = None

            # 检查是否释放在输入端口上
            items = self.orch_canvas.find_overlapping(cx - 10, cy - 10, cx + 10, cy + 10)
            for item in items:
                tags = self.orch_canvas.gettags(item)
                for tag in tags:
                    if tag.startswith("input_") and tag != "input_port":
                        to_node_id = tag.replace("input_", "")
                        if to_node_id != self.orch_connecting_from and to_node_id in self.orch_nodes:
                            conn = (self.orch_connecting_from, to_node_id)
                            if conn not in self.orch_connections:
                                self.orch_connections.append(conn)
                                self._orch_draw_connection(self.orch_connecting_from, to_node_id)
                                self.log("[编排] 🔗 连接创建成功")
                        break
            
            self.orch_connecting_from = None

        # 结束拖拽
        self.orch_drag_node_id = None


    def _orch_on_canvas_double_click(self, event) -> None:
        """画布双击事件 - 编辑节点名称"""
        if self.orch_selected_node:
            node = self.orch_nodes.get(self.orch_selected_node)
            if node and hasattr(self, 'orch_prop_name_entry'):
                # 聚焦到名称输入框
                self.orch_prop_name_entry.focus_set()
                self.orch_prop_name_entry.select_range(0, tk.END)

    # V7.12: Right-click context menu for nodes
    def _orch_on_canvas_right_click(self, event) -> None:
        """Show context menu on right-click"""
        cx = self.orch_canvas.canvasx(event.x)
        cy = self.orch_canvas.canvasy(event.y)
        
        # Find clicked node
        items = self.orch_canvas.find_overlapping(cx - 5, cy - 5, cx + 5, cy + 5)
        clicked_node_id = None
        for item in items:
            tags = self.orch_canvas.gettags(item)
            for tag in tags:
                if tag.startswith("node_"):
                    clicked_node_id = tag.replace("node_", "")
                    break
            if clicked_node_id:
                break
        
        if not clicked_node_id or clicked_node_id not in self.orch_nodes:
            self._orch_deselect_node()
            return
            
        # Select the node and set focus (Critical for keyboard events)
        self._orch_select_node(clicked_node_id)
        self.orch_canvas.focus_set()
        
        # Create custom context menu (Gemini UI Style)
        self._show_custom_context_menu(event.x_root, event.y_root, clicked_node_id)

    def _create_context_menu_item(self, parent, text, command, text_color="#dddddd", hover_color="#3a3a3a"):
        """Helper to create stylized menu items"""
        btn = ctk.CTkButton(
            parent, text=text, command=lambda: [self._close_context_menu(), command()],
            fg_color="transparent", hover_color=hover_color, text_color=text_color,
            anchor="w", height=32, corner_radius=4, font=("Segoe UI", 12)
        )
        btn.pack(fill="x", padx=4, pady=2)
        return btn

    def _close_context_menu(self, event=None):
        """Close the custom context menu"""
        if hasattr(self, '_context_menu_window') and self._context_menu_window:
            self._context_menu_window.destroy()
            self._context_menu_window = None

    def _show_custom_context_menu(self, x, y, node_id):
        """Show a modern, dark-themed context menu using CTkToplevel"""
        self._close_context_menu()
        
        node = self.orch_nodes[node_id]
        
        # Create Toplevel for menu
        menu = ctk.CTkToplevel()
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.geometry(f"+{x}+{y}")
        self._context_menu_window = menu
        
        # Close when losing focus (simulated click-outside behavior)
        menu.bind("<FocusOut>", lambda e: self._close_context_menu() if str(e.widget) == str(menu) else None)
        # Force focus to capture FocusOut
        menu.after(50, menu.focus_set)
        
        # Main container with border
        frame = ctk.CTkFrame(menu, fg_color="#2b2b2b", border_width=1, border_color="#444444", corner_radius=8)
        frame.pack(fill="both", expand=True)
        
        # Header
        lbl = ctk.CTkLabel(frame, text=f"  📌 {node.step_name}", anchor="w", font=("Segoe UI", 12, "bold"), text_color="#888")
        lbl.pack(fill="x", pady=(6, 4), padx=4)
        
        ctk.CTkFrame(frame, height=1, fg_color="#444").pack(fill="x", pady=2, padx=4)
        
        # Items
        self._create_context_menu_item(frame, "  🧪  单点测试", lambda: self._orch_test_node_by_id(node_id))
        
        bp_label = "  🔴  移除断点" if "[BREAKPOINT]" in node.context else "  🔵  设置断点"
        self._create_context_menu_item(frame, bp_label, lambda: self._orch_toggle_breakpoint_by_id(node_id))
        
        ctk.CTkFrame(frame, height=1, fg_color="#444").pack(fill="x", pady=2, padx=4)
        
        self._create_context_menu_item(frame, "  ✏️  修改名称", lambda: self._orch_rename_node_dialog(node_id))
        self._create_context_menu_item(frame, "  🔌  断开连接", lambda: self._orch_disconnect_node(node_id))
        
        ctk.CTkFrame(frame, height=1, fg_color="#444").pack(fill="x", pady=2, padx=4)
        
        self._create_context_menu_item(frame, "  🗑️  删除节点", lambda: self._orch_delete_node(node_id), text_color="#ff5555", hover_color="#4a1a1a")
        
        # Add a transparent overlay or bind click events to close? 
        # FocusOut is mostly sufficient, but sometimes unreliable on Windows if clicks land on non-focusable windows.
        # Adding an explicit 'Leave' or 'FocusOut' is improved by grab_set, but grab_set stops outside interaction.
        # We'll stick to focus logic. A click outside usually triggers focus change.

    def _orch_delete_selected_node(self, event=None) -> None:
        """Delete currently selected node via keyboard"""
        if self.orch_selected_node:
            self._orch_delete_node(self.orch_selected_node)

    def _orch_delete_node(self, node_id: str) -> None:
        """Delete a node and its connections"""
        if node_id not in self.orch_nodes:
            return
            
        node = self.orch_nodes[node_id]
        node_name = node.step_name
        
        # 1. Remove all connections involving this node
        self._orch_disconnect_node(node_id)
        
        # 2. Remove canvas items
        if node_id in self.orch_node_canvas_items:
            for item_id in self.orch_node_canvas_items[node_id]:
                self.orch_canvas.delete(item_id)
            del self.orch_node_canvas_items[node_id]
        
        # 3. Remove from nodes dict
        del self.orch_nodes[node_id]
        
        # 4. Clear selection
        if self.orch_selected_node == node_id:
            self._orch_deselect_node()
        
        # 5. Refresh listbox
        self._orch_refresh_listbox()
        
        self.log(f"[编排] 🗑️ 已删除节点: {node_name}")

    def _orch_disconnect_node(self, node_id: str) -> None:
        """Disconnect all connections from/to a node"""
        if node_id not in self.orch_nodes:
            return
            
        # Find connections to remove
        conns_to_remove = [
            (from_id, to_id) for from_id, to_id in self.orch_connections 
            if from_id == node_id or to_id == node_id
        ]
        
        # Remove connection lines and entries
        for from_id, to_id in conns_to_remove:
            key = (from_id, to_id)
            if key in self.orch_connection_lines:
                for item_id in self.orch_connection_lines[key]:
                    self.orch_canvas.delete(item_id)
                del self.orch_connection_lines[key]
            self.orch_connections.remove((from_id, to_id))
        
        if conns_to_remove:
            self.log(f"[编排] 🔌 已断开 {len(conns_to_remove)} 个连接")

    def _orch_rename_node_dialog(self, node_id: str) -> None:
        """Show dialog to rename a node"""
        if node_id not in self.orch_nodes:
            return
            
        node = self.orch_nodes[node_id]
        
        # Simple input dialog
        from tkinter import simpledialog
        new_name = simpledialog.askstring(
            "修改节点名称", 
            f"当前名称: {node.step_name}\n请输入新名称:",
            initialvalue=node.step_name,
            parent=self.root
        )
        
        if new_name and new_name.strip():
            node.step_name = new_name.strip()
            self._orch_draw_node(node)
            self._orch_refresh_listbox()
            self.log(f"[编排] ✏️ 节点已重命名为: {new_name}")

    def _orch_select_node(self, node_id: str) -> None:
        """选中节点"""
        self.orch_selected_node = node_id
        node = self.orch_nodes.get(node_id)
        if node:
            self._is_updating_ui = True
            try:
                # 更新属性面板变量 (deprecated)
                self.orch_prop_name_var.set(node.step_name)
                self.orch_prop_action_var.set(node.action_type)
                self.orch_prop_params_var.set(node.params)
                self.orch_prop_retry_var.set(str(node.retry_count))
                self.orch_prop_optional_var.set(node.is_optional)
                self.orch_prop_x1_var.set(str(node.coords.get("x1", 0)))
                self.orch_prop_y1_var.set(str(node.coords.get("y1", 0)))
                self.orch_prop_x2_var.set(str(node.coords.get("x2", 0)))
                self.orch_prop_y2_var.set(str(node.coords.get("y2", 0)))
                
                # 同步到左侧面板 (Active)
                if hasattr(self, 'gen_step_var'):
                    self.gen_step_var.set(node.step_name)
                if hasattr(self, 'gen_category_var'):
                    category = self._find_category_for_action(node.action_type)
                    self.gen_category_var.set(category)
                    # Trigger category change logic manually if needed, or rely on command
                    self._on_gen_category_change(category)
                if hasattr(self, 'gen_action_var'):
                    self.gen_action_var.set(node.action_type)
                if hasattr(self, 'gen_param_var'):
                    params_val = str(node.params)
                    if node.action_type.startswith("IF") and params_val.startswith("op:"):
                        try:
                            parts = params_val.split("|", 1)
                            op_code = parts[0].split(":")[1]
                            value = parts[1] if len(parts) > 1 else ""
                            
                            rev_map = {
                                "Contains": "包含 (Contains)",
                                "NotContains": "不包含 (Not Contains)",
                                "Equals": "等于 (Equals)",
                                "NotEquals": "不等于 (Not Equals)"
                            }
                            if hasattr(self, 'gen_operator_var'):
                                self.gen_operator_var.set(rev_map.get(op_code, "包含 (Contains)"))
                            self.gen_param_var.set(value)
                        except:
                            self.gen_param_var.set(params_val)
                    else:
                        self.gen_param_var.set(params_val)
                
                # Update AI Context
                if hasattr(self, 'gen_context_text'):
                    self.gen_context_text.delete("1.0", tk.END)
                    self.gen_context_text.insert("1.0", node.context)
                    # V7.0: 绑定文本框修改事件
                    self.gen_context_text.bind("<KeyRelease>", self._on_inspector_text_change)
                    
                # Update coordinates
                if hasattr(self, 'gen_x1_var'):
                    self.gen_x1_var.set(str(node.coords.get("x1", 0)))
                    self.gen_y1_var.set(str(node.coords.get("y1", 0)))
                    self.gen_x2_var.set(str(node.coords.get("x2", 0)))
                    self.gen_y2_var.set(str(node.coords.get("y2", 0)))

                # 更新提示标签（如果存在）
                if hasattr(self, 'orch_hint_label'):
                    self.orch_hint_label.configure(text=f"已选中: {node.step_name}")
            finally:
                self._is_updating_ui = False

        self._orch_draw_all_nodes()

    def _orch_deselect_node(self) -> None:
        """取消选中"""
        self.orch_selected_node = None
        if hasattr(self, 'orch_hint_label'):
            self.orch_hint_label.configure(text="点击节点查看属性")
        self._orch_draw_all_nodes()

    def _orch_delete_selected_node(self, event=None) -> None:
        """删除选中的节点"""
        if not self.orch_selected_node:
            return

        node_id = self.orch_selected_node
        node = self.orch_nodes.get(node_id)

        # 删除节点的画布元素
        if node_id in self.orch_node_canvas_items:
            for item_id in self.orch_node_canvas_items[node_id]:
                self.orch_canvas.delete(item_id)
            del self.orch_node_canvas_items[node_id]

        # 删除相关连接
        self.orch_connections = [
            (f, t) for f, t in self.orch_connections
            if f != node_id and t != node_id
        ]

        # 删除连接线
        keys_to_delete = [k for k in self.orch_connection_lines if node_id in k]
        for key in keys_to_delete:
            self.orch_canvas.delete(self.orch_connection_lines[key])
            del self.orch_connection_lines[key]

        # 删除节点数据
        if node_id in self.orch_nodes:
            del self.orch_nodes[node_id]

        self._orch_deselect_node()
        self._orch_deselect_node()
        self.log(f"[编排] 删除节点: {node.step_name if node else node_id}")
        self._orch_refresh_listbox()

    def _orch_save_node_properties(self) -> None:
        """保存节点属性"""
        if not self.orch_selected_node:
            messagebox.showwarning("提示", "请先选择一个节点")
            return

        node = self.orch_nodes.get(self.orch_selected_node)
        if not node:
            return

        node.step_name = self.orch_prop_name_var.get()
        node.action_type = self.orch_prop_action_var.get()
        node.params = self.orch_prop_params_var.get()

        try:
            node.retry_count = int(self.orch_prop_retry_var.get())
        except ValueError:
            node.retry_count = 0

        node.is_optional = self.orch_prop_optional_var.get()

        try:
            node.coords = {
                "x1": float(self.orch_prop_x1_var.get()),
                "y1": float(self.orch_prop_y1_var.get()),
                "x2": float(self.orch_prop_x2_var.get()),
                "y2": float(self.orch_prop_y2_var.get()),
            }
        except ValueError:
            pass

        self._orch_draw_node(node)
        self.log(f"[编排] 保存节点: {node.step_name}")
        if hasattr(self, 'orch_hint_label'):
            self.orch_hint_label.configure(text=f"已保存: {node.step_name}")

    def _orch_insert_variable(self, var_name: str) -> None:
        """插入变量到参数框"""
        current = self.orch_prop_params_var.get()
        self.orch_prop_params_var.set(current + f"${{{var_name}}}")

    def _orch_sync_coords_from_live(self) -> None:
        """从实时调试同步坐标和参数，并自动保存"""
        try:
            # 1. 同步坐标
            self.orch_prop_x1_var.set(self.x1_var.get())
            self.orch_prop_y1_var.set(self.y1_var.get())
            self.orch_prop_x2_var.set(self.x2_var.get())
            self.orch_prop_y2_var.set(self.y2_var.get())

            # 2. 同步参数 (优先尝试 gen_param_var，其次 ocr_target_text_var)
            param = self.gen_param_var.get().strip()
            if not param:
                param = self.ocr_target_text_var.get().strip()
            
            if param:
                self.orch_prop_params_var.set(param)
            
            # 3. 自动保存到选中节点
            if self.orch_selected_node:
                node = self.orch_nodes.get(self.orch_selected_node)
                if node:
                    try:
                        node.coords = {
                            "x1": float(self.x1_var.get()),
                            "y1": float(self.y1_var.get()),
                            "x2": float(self.x2_var.get()),
                            "y2": float(self.y2_var.get()),
                        }
                        node.params = self.orch_prop_params_var.get()
                        self.log(f"[编排] ✅ 已同步并保存节点数据: {node.step_name}")
                        self._orch_mark_node_success(node.id) # 给予视觉反馈
                        self.root.after(1000, lambda: self._orch_draw_node(node)) # 1秒后恢复
                    except ValueError:
                        self.log("[编排] ⚠️ 坐标无效，未自动保存")
            
            self.log("[编排] 已从实时调试同步")
        except Exception as e:
            self.log(f"[编排] 同步失败: {e}")

    def _orch_auto_connect(self) -> None:
        """自动按顺序连接所有节点"""
        if len(self.orch_nodes) < 2:
            messagebox.showinfo("提示", "需要至少 2 个节点才能自动连接")
            return

        # 按 canvas_x 位置排序节点
        sorted_nodes = sorted(self.orch_nodes.values(), key=lambda n: (n.canvas_x, n.canvas_y))

        # 清除现有连接
        self.orch_connections.clear()
        for line_id in self.orch_connection_lines.values():
            self.orch_canvas.delete(line_id)
        self.orch_connection_lines.clear()

        # 顺序连接
        for i in range(len(sorted_nodes) - 1):
            conn = (sorted_nodes[i].id, sorted_nodes[i + 1].id)
            self.orch_connections.append(conn)

        self._orch_draw_all_connections()
        self.log(f"[编排] 自动连接 {len(self.orch_connections)} 条线")

    def _orch_clear_canvas(self) -> None:
        """清空画布"""
        if not self.orch_nodes:
            return

        if not messagebox.askyesno("确认", "确定要清空画布吗？所有节点和连接都将被删除。"):
            return

        self.orch_canvas.delete("node")
        self.orch_canvas.delete("connection")
        self.orch_nodes.clear()
        self.orch_connections.clear()
        self.orch_node_canvas_items.clear()
        self.orch_connection_lines.clear()
        self._orch_deselect_node()
        self._orch_draw_grid()
        self._orch_refresh_listbox()
        self.log("[编排] 画布已清空")

    def _orch_export_json(self) -> None:
        """导出为 JSON 文件"""
        if not self.orch_nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        # 拓扑排序获取执行顺序
        ordered_nodes = self._orch_topological_sort()

        export_data = []
        for i, node in enumerate(ordered_nodes, 1):
            export_data.append({
                "step_id": i,
                "step_name": node.step_name,
                "action_type": node.action_type,
                "params": node.params,
                "context": node.context,
                "coords": node.coords,
                "retry_count": node.retry_count,
                "is_optional": node.is_optional,
            })

        filepath = filedialog.asksaveasfilename(
            title="导出流程",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile="workflow.json",
        )

        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            self.log(f"[编排] 已导出: {filepath}")
            messagebox.showinfo("导出成功", f"已导出 {len(export_data)} 个步骤到:\n{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _orch_import_json(self) -> None:
        """从 JSON 文件导入"""
        filepath = filedialog.askopenfilename(
            title="导入流程",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )

        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValueError("JSON 格式错误：根元素必须是数组")

            # 清空现有画布
            self._orch_clear_canvas_silent()

            # 导入节点
            for i, item in enumerate(data):
                node_id = str(uuid.uuid4())[:8]
                node = WorkflowNode(
                    id=node_id,
                    action_type=item.get("action_type", "Click Region"),
                    step_name=item.get("step_name", f"Step {i + 1}"),
                    params=item.get("params", ""),
                    context=item.get("context", ""),
                    coords=item.get("coords", {"x1": 0, "y1": 0, "x2": 0, "y2": 0}),
                    canvas_x=150 + i * 180,
                    canvas_y=100 + (i % 3) * 100,
                    retry_count=item.get("retry_count", 0),
                    is_optional=item.get("is_optional", False),
                )
                self.orch_nodes[node_id] = node

            self._orch_draw_all_nodes()
            self._orch_auto_connect()
            self.log(f"[编排] 已导入 {len(self.orch_nodes)} 个节点")
            self._orch_refresh_listbox()
            messagebox.showinfo("导入成功", f"已导入 {len(self.orch_nodes)} 个节点")

        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _orch_clear_canvas_silent(self) -> None:
        """静默清空画布（不弹窗确认）"""
        self.orch_canvas.delete("node")
        self.orch_canvas.delete("connection")
        self.orch_nodes.clear()
        self.orch_connections.clear()
        self.orch_node_canvas_items.clear()
        self.orch_connection_lines.clear()
        self._orch_deselect_node()
        self._orch_draw_grid()
        self._orch_refresh_listbox()

    def _orch_clear_canvas_items(self) -> None:
        """清除画布上的所有元素记录（用于重绘）"""
        self.orch_canvas.delete("all")
        self.orch_node_canvas_items.clear()
        self.orch_connection_lines.clear()
        self._orch_draw_grid()

    def _orch_on_canvas_pan_start(self, event):
        """画布拖拽开始（中键或 Ctrl+左键）"""
        self.orch_canvas.scan_mark(event.x, event.y)

    def _orch_on_canvas_pan_drag(self, event):
        """画布拖拽中"""
        self.orch_canvas.scan_dragto(event.x, event.y, gain=1)
        self.orch_connection_lines.clear()
        self._orch_deselect_node()

    def _orch_topological_sort(self) -> List[WorkflowNode]:
        """拓扑排序获取节点执行顺序"""
        if not self.orch_connections:
            # 没有连接，按位置排序
            return sorted(self.orch_nodes.values(), key=lambda n: (n.canvas_x, n.canvas_y))

        # 构建邻接表和入度
        in_degree = {node_id: 0 for node_id in self.orch_nodes}
        adj = {node_id: [] for node_id in self.orch_nodes}

        for from_id, to_id in self.orch_connections:
            if from_id in adj and to_id in in_degree:
                adj[from_id].append(to_id)
                in_degree[to_id] += 1

        # Kahn 算法
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            # 按位置排序选择下一个节点（当多个入度为0时）
            queue.sort(key=lambda nid: (self.orch_nodes[nid].canvas_x, self.orch_nodes[nid].canvas_y))
            node_id = queue.pop(0)
            result.append(self.orch_nodes[node_id])

            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 如果有孤立节点，追加到末尾
        for node in self.orch_nodes.values():
            if node not in result:
                result.append(node)

        return result

    def _orch_run_all(self) -> None:
        """V6.0: 运行全部节点 (alias)"""
        self._orch_run_workflow()

    def _orch_run_workflow(self) -> None:
        """运行当前编排的全部工作流节点"""
        if not self.orch_nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        if not self.device:
            messagebox.showwarning("提示", "请先连接设备")
            return

        # 获取排序后的节点
        ordered_nodes = self._orch_topological_sort()
        total_steps = len(ordered_nodes)
        
        # 导出为执行格式
        export_data = []
        for i, node in enumerate(ordered_nodes, 1):
            export_data.append({
                "step_id": i,
                "step_name": node.step_name,
                "action_type": node.action_type,
                "params": node.params,
                "context": node.context,
                "coords": node.coords,
                "retry_count": node.retry_count,
                "is_optional": node.is_optional,
                "_node_id": node.id,  # 用于高亮
            })

        # 尝试使用 WorkflowRunner
        try:
            from workflow_runner import WorkflowRunner

            runner = WorkflowRunner(
                self.device,
                phone_width=self.phone_width,
                phone_height=self.phone_height,
            )

            self.log(f"[编排] 🚀 开始执行 {total_steps} 个步骤...")
            if hasattr(self, 'orch_hint_label'):
                self.orch_hint_label.configure(text=f"执行中: 0/{total_steps}")
            
            success_count = 0
            fail_count = 0

            for i, step in enumerate(export_data):
                node_id = step.pop("_node_id")
                step_name = step.get("step_name", f"Step {step['step_id']}")
                action_type = step.get("action_type", "Unknown")

                # 高亮当前执行的节点
                self._orch_highlight_executing_node(node_id)
                if hasattr(self, 'orch_hint_label'):
                    self.orch_hint_label.configure(text=f"执行中: {i+1}/{total_steps} - {step_name}")
                self.root.update()

                self.log(f"[编排] ▶️ [{i+1}/{total_steps}] {step_name} - {action_type}")

                # 执行步骤
                success = runner.execute_step(step, {})

                if success:
                    success_count += 1
                    self._orch_mark_node_success(node_id)
                    self.log(f"[编排] ✅ 完成: {step_name}")
                else:
                    fail_count += 1
                    is_optional = step.get("is_optional", False)
                    self._orch_mark_node_failed(node_id)
                    
                    if is_optional:
                        self.log(f"[编排] ⚠️ 步骤失败 (可选): {step_name}")
                    else:
                        self.log(f"[编排] ❌ 步骤失败: {step_name}")
                        messagebox.showerror("执行失败", f"步骤 [{step['step_id']}] {step_name} 执行失败")
                        break

                self.root.update()

            # 恢复节点样式
            self.orch_running_node = None
            self.root.after(2000, self._orch_draw_all_nodes)

            # 汇总结果
            self.log(f"[编排] 🏁 执行完成: {success_count} 成功, {fail_count} 失败")
            if hasattr(self, 'orch_hint_label'):
                self.orch_hint_label.configure(text=f"完成: {success_count}✓ {fail_count}✗")
            
            if fail_count == 0:
                messagebox.showinfo("执行完成", f"全部 {total_steps} 个步骤执行成功！")

        except ImportError:
            self.log("[编排] ❌ 未找到 workflow_runner.py")
            messagebox.showerror("错误", "未找到 workflow_runner.py\n请确保该文件在同一目录下")
        except Exception as e:
            self.log(f"[编排] ❌ 执行失败: {e}")
            messagebox.showerror("执行失败", str(e))
            
    def _orch_highlight_executing_node(self, node_id: str) -> None:
        """高亮正在执行的节点（黄色边框）并自动滚动"""
        self._orch_set_running_node(node_id)
            
    def _orch_set_running_node(self, node_id: str) -> None:
        """设置当前运行节点，重绘并自动滚动"""
        self.orch_running_node = node_id
        
        # Redraw ALL nodes to ensure previous running node is cleared
        self._orch_draw_all_nodes()
        
        # Auto-scroll using shared helper
        self._orch_scroll_to_node(node_id)
            
    def _orch_mark_node_success(self, node_id: str) -> None:
        """标记节点执行成功（绿色边框）"""
        if node_id not in self.orch_node_canvas_items:
            return
        items = self.orch_node_canvas_items[node_id]
        if items:
            self.orch_canvas.itemconfig(items[0], outline="#00FF00", width=3)
            
    def _orch_mark_node_failed(self, node_id: str) -> None:
        """标记节点执行失败（红色边框）"""
        if node_id not in self.orch_node_canvas_items:
            return
        items = self.orch_node_canvas_items[node_id]
        if items:
            self.orch_canvas.itemconfig(items[0], outline="#FF0000", width=3)

    # ==================== 新功能: 单点测试 ====================
    
    def _orch_test_selected_node(self) -> None:
        """测试选中的单个节点"""
        if not self.orch_selected_node:
            messagebox.showwarning("提示", "请先选择一个节点")
            return
        
        if not self.device:
            messagebox.showwarning("提示", "请先连接设备")
            return
        
        node = self.orch_nodes.get(self.orch_selected_node)
        if not node:
            return
        
        self.log(f"[编排] 🧪 单点测试: {node.step_name}")
        
        # 构造步骤数据
        step_data = {
            "step_id": 1,
            "step_name": node.step_name,
            "action_type": node.action_type,
            "params": node.params,
            "coords": node.coords,
        }
        
        try:
            from workflow_runner import WorkflowRunner
            
            runner = WorkflowRunner(
                self.device,
                phone_width=self.phone_width,
                phone_height=self.phone_height,
            )
            
            self._orch_highlight_executing_node(node.id)
            self.root.update()
            
            success = runner.execute_step(step_data, {})
            
            if success:
                self._orch_mark_node_success(node.id)
                self.log(f"[编排] ✅ 单点测试成功: {node.step_name}")
                messagebox.showinfo("测试成功", f"节点 {node.step_name} 执行成功！")
            else:
                self._orch_mark_node_failed(node.id)
                self.log(f"[编排] ❌ 单点测试失败: {node.step_name}")
                messagebox.showerror("测试失败", f"节点 {node.step_name} 执行失败")
            
            # 2秒后恢复样式
            self.root.after(2000, lambda: self._orch_draw_node(node))
            
        except ImportError:
            messagebox.showerror("错误", "未找到 workflow_runner.py")
        except Exception as e:
            self.log(f"[编排] ❌ 单点测试失败: {e}")
            messagebox.showerror("测试失败", str(e))

    # ==================== 新功能: 断点调试 ====================
    
    def _orch_toggle_breakpoint(self) -> None:
        """切换选中节点的断点状态"""
        if not self.orch_selected_node:
            messagebox.showwarning("提示", "请先选择一个节点")
            return
        
        node = self.orch_nodes.get(self.orch_selected_node)
        if not node:
            return
        
        # 使用 context 字段存储断点标记
        if "[BREAKPOINT]" in node.context:
            node.context = node.context.replace("[BREAKPOINT]", "").strip()
            self.log(f"[编排] 🔵 移除断点: {node.step_name}")
        else:
            node.context = f"[BREAKPOINT] {node.context}".strip()
            self.log(f"[编排] 🔴 设置断点: {node.step_name}")
        
        # 重绘节点以显示断点标记
        self._orch_draw_node(node)
        if hasattr(self, 'orch_hint_label'):
            self.orch_hint_label.configure(text=f"断点: {'已设置' if '[BREAKPOINT]' in node.context else '已移除'}")
    
    def _orch_run_with_breakpoints(self) -> None:
        """带断点调试运行 - 在断点处暂停"""
        if not self.orch_nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        if not self.device:
            messagebox.showwarning("提示", "请先连接设备")
            return

        ordered_nodes = self._orch_topological_sort()
        total_steps = len(ordered_nodes)
        
        self.log(f"[编排] ⏸️ 断点调试模式启动 ({total_steps} 个步骤)...")
        
        try:
            from workflow_runner import WorkflowRunner
            
            runner = WorkflowRunner(
                self.device,
                phone_width=self.phone_width,
                phone_height=self.phone_height,
            )
            
            for i, node in enumerate(ordered_nodes):
                # 检查断点
                if "[BREAKPOINT]" in node.context:
                    self._orch_highlight_executing_node(node.id)
                    if hasattr(self, 'orch_hint_label'):
                        self.orch_hint_label.configure(text=f"⏸️ 断点暂停: {node.step_name}")
                    self.root.update()
                    
                    result = messagebox.askquestion(
                        "断点暂停",
                        f"在节点 [{i+1}] {node.step_name} 处暂停\n\n"
                        f"动作: {node.action_type}\n"
                        f"参数: {node.params}\n\n"
                        "是否继续执行？",
                        icon="question"
                    )
                    
                    if result != "yes":
                        self.log("[编排] ⏹️ 用户中止调试")
                        self._orch_draw_all_nodes()
                        return
                
                # 执行步骤
                step_data = {
                    "step_id": i + 1,
                    "step_name": node.step_name,
                    "action_type": node.action_type,
                    "params": node.params,
                    "coords": node.coords,
                    "retry_count": node.retry_count,
                    "is_optional": node.is_optional,
                }
                
                self._orch_highlight_executing_node(node.id)
                if hasattr(self, 'orch_hint_label'):
                    self.orch_hint_label.configure(text=f"执行: {i+1}/{total_steps} - {node.step_name}")
                self.root.update()
                
                success = runner.execute_step(step_data, {})
                
                if success:
                    self._orch_mark_node_success(node.id)
                    self.log(f"[编排] ✅ [{i+1}/{total_steps}] {node.step_name}")
                else:
                    self._orch_mark_node_failed(node.id)
                    if not node.is_optional:
                        self.log(f"[编排] ❌ 步骤失败: {node.step_name}")
                        messagebox.showerror("执行失败", f"步骤 {node.step_name} 失败")
                        break
                
                self.root.update()
            
            self.log("[编排] 🏁 断点调试完成")
            self.root.after(2000, self._orch_draw_all_nodes)
            
        except Exception as e:
            self.log(f"[编排] ❌ 调试失败: {e}")
            messagebox.showerror("调试失败", str(e))

    # ==================== 新功能: 连接管理 ====================
    
    def _orch_delete_selected_connection(self) -> None:
        """删除选中的连接（需要先点击连接线）"""
        if not self.orch_connections:
            messagebox.showinfo("提示", "没有连接可删除")
            return
        
        # 如果有选中的节点，删除与该节点相关的所有连接
        if self.orch_selected_node:
            node_id = self.orch_selected_node
            connections_to_remove = [
                conn for conn in self.orch_connections
                if conn[0] == node_id or conn[1] == node_id
            ]
            
            if not connections_to_remove:
                messagebox.showinfo("提示", "选中节点没有连接")
                return
            
            for conn in connections_to_remove:
                self.orch_connections.remove(conn)
                if conn in self.orch_connection_lines:
                    self.orch_canvas.delete(self.orch_connection_lines[conn])
                    del self.orch_connection_lines[conn]
            
            self.log(f"[编排] ✂️ 删除 {len(connections_to_remove)} 条连接")
            messagebox.showinfo("已删除", f"删除了 {len(connections_to_remove)} 条连接")
        else:
            # 删除最后一条连接
            if self.orch_connections:
                conn = self.orch_connections.pop()
                if conn in self.orch_connection_lines:
                    self.orch_canvas.delete(self.orch_connection_lines[conn])
                    del self.orch_connection_lines[conn]
                self.log(f"[编排] ✂️ 删除连接: {conn[0]} → {conn[1]}")
    
    def _orch_start_manual_connect(self) -> None:
        """开始手动连接模式"""
        if not self.orch_selected_node:
            messagebox.showinfo("提示", "请先选择起始节点，然后点击此按钮，再点击目标节点")
            return
        
        self.orch_manual_connect_from = self.orch_selected_node
        node = self.orch_nodes.get(self.orch_selected_node)
        if hasattr(self, 'orch_hint_label'):
            self.orch_hint_label.configure(text=f"🔗 从 {node.step_name} 连接到... (点击目标节点)")
        self.log(f"[编排] 🔗 手动连接模式: 从 {node.step_name} 开始，点击目标节点完成连接")
    
    def _orch_on_right_click(self, event) -> None:
        """右键菜单"""
        # 创建右键菜单
        menu = tk.Menu(self.orch_canvas, tearoff=0)
        
        # 检查是否点击了节点
        items = self.orch_canvas.find_overlapping(event.x - 5, event.y - 5, event.x + 5, event.y + 5)
        clicked_node_id = None
        
        for item in items:
            tags = self.orch_canvas.gettags(item)
            for tag in tags:
                if tag.startswith("node_"):
                    clicked_node_id = tag.replace("node_", "")
                    break
        
        if clicked_node_id:
            node = self.orch_nodes.get(clicked_node_id)
            if node:
                menu.add_command(label=f"🧪 测试: {node.step_name}", 
                               command=lambda: self._orch_test_node_by_id(clicked_node_id))
                menu.add_command(label="🔴 切换断点", 
                               command=lambda: self._orch_toggle_breakpoint_by_id(clicked_node_id))
                menu.add_separator()
                menu.add_command(label="✂️ 断开所有连接", 
                               command=lambda: self._orch_disconnect_node(clicked_node_id))
                menu.add_command(label="🗑️ 删除节点", 
                               command=lambda: self._orch_delete_node_by_id(clicked_node_id))
        else:
            menu.add_command(label="🔗 自动连接所有", command=self._orch_auto_connect)
            menu.add_command(label="🗑️ 清空画布", command=self._orch_clear_canvas)
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _orch_test_node_by_id(self, node_id: str) -> None:
        """通过 ID 测试节点"""
        self.orch_selected_node = node_id
        self._orch_test_selected_node()
    
    def _orch_toggle_breakpoint_by_id(self, node_id: str) -> None:
        """通过 ID 切换断点"""
        self.orch_selected_node = node_id
        self._orch_toggle_breakpoint()
    
    def _orch_disconnect_node(self, node_id: str) -> None:
        """断开节点的所有连接"""
        self.orch_selected_node = node_id
        self._orch_delete_selected_connection()
    
    def _orch_delete_node_by_id(self, node_id: str) -> None:
        """通过 ID 删除节点"""
        self.orch_selected_node = node_id
        self._orch_draw_all_nodes()
        self._orch_delete_selected_node()

    def _orch_disconnect_selected_node_all(self) -> None:
        """V7.5: 断开选中节点的所有连接"""
        if not self.orch_selected_node:
            messagebox.showinfo("提示", "请先选择要断开的节点")
            return
            
        node_id = self.orch_selected_node
        
        # 筛选出要保留的连接
        new_conns = []
        removed_count = 0
        
        keys_to_delete = []
        
        for conn in self.orch_connections:
            if conn[0] == node_id or conn[1] == node_id:
                # 删除对应的线段
                key = f"{conn[0]}_{conn[1]}"
                if key in self.orch_connection_lines:
                    keys_to_delete.append(key)
                removed_count += 1
            else:
                new_conns.append(conn)
        
        # 执行删除
        for key in keys_to_delete:
            self.orch_canvas.delete(self.orch_connection_lines[key])
            del self.orch_connection_lines[key]
            
        self.orch_connections = new_conns
        self.log(f"[编排] 🔌 已断开节点所有连接 ({removed_count} 条)")

    def _orch_test_click_region(self) -> None:
        """V7.5: 测试点击当前节点区域 (静态测试)"""
        if not self.orch_selected_node:
            messagebox.showinfo("提示", "请先选择要测试的节点")
            return
            
        if not self.device:
            messagebox.showwarning("警告", "请先连接设备")
            return
            
        node = self.orch_nodes.get(self.orch_selected_node)
        if not node:
            return

        coords = node.coords
        try:
            # 计算中心点
            x1 = float(coords.get("x1", 0))
            y1 = float(coords.get("y1", 0))
            x2 = float(coords.get("x2", 0))
            y2 = float(coords.get("y2", 0))
            
            if x1 == 0 and x2 == 0:
                 # 防止误点 (0,0)
                 self.log("[测试] ⚠️ 坐标无效 (0,0)")
                 return

            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            
            # 获取设备分辨率
            w, h = self.device.window_size()
            
            px = int(cx * w)
            py = int(cy * h)
            
            self.device.click(px, py)
            self.log(f"[测试] 👆 点击坐标: ({px}, {py}) [{w}x{h}]")
            
        except Exception as e:
            self.log(f"[测试] ❌ 点击失败: {e}")
            messagebox.showerror("错误", f"点击测试失败: {e}")

    def _show_extension_import(self):
        """V7.9: Show Extension Import & Manage Dialog"""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Extension Node Manager")
        width = 900
        height = 600
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.attributes("-topmost", True)
        
        # 2 Columns
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_columnconfigure(1, weight=1)
        dialog.grid_rowconfigure(0, weight=1)
        
        # === Left: Import ===
        left_frame = ctk.CTkFrame(dialog)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(left_frame, text="📥 导入 (粘贴 AI JSON)", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=5)
        text_box = ctk.CTkTextbox(left_frame)
        text_box.pack(fill="both", expand=True, padx=5, pady=5)
        
        def do_import():
            json_str = text_box.get("1.0", "end")
            success, msg = self.ext_manager.import_extension(json_str)
            if success:
                messagebox.showinfo("Success", f"{msg}\n\n请重启应用生效。", parent=dialog)
                # Clear and refresh
                text_box.delete("1.0", "end")
                refresh_list()
            else:
                messagebox.showerror("Error", f"导入失败:\n{msg}", parent=dialog)
                
        ctk.CTkButton(left_frame, text="✅ 确认导入", command=do_import, fg_color="green").pack(pady=10)
        
        # === Right: Manage ===
        right_frame = ctk.CTkFrame(dialog)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(right_frame, text="🗑️ 管理已安装扩展", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=5)
        
        list_frame = ctk.CTkScrollableFrame(right_frame)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        def refresh_list():
            for widget in list_frame.winfo_children():
                widget.destroy()
            
            nodes = self.ext_manager.load_nodes_metadata()
            if not nodes:
                ctk.CTkLabel(list_frame, text="(无扩展)", text_color="gray").pack(pady=20)
                return

            for node in nodes:
                row = ctk.CTkFrame(list_frame)
                row.pack(fill="x", pady=2)
                
                name = node.get("name", "Unknown")
                icon = node.get("icon", "")
                
                # Try render icon if image
                icon_txt = f"{icon} "
                if ".png" in str(icon).lower():
                    icon_txt = "🖼️ "

                ctk.CTkLabel(row, text=f"{icon_txt}{name}", anchor="w", font=ctk.CTkFont(size=12)).pack(side="left", padx=10)
                
                def do_delete(n=name):
                    if messagebox.askyesno("确认", f"确定删除扩展 '{n}' 吗?\n(代码将保留但失效)", parent=dialog):
                        if self.ext_manager.delete_node(n):
                            refresh_list()
                            messagebox.showinfo("提示", "已删除，请重启应用。", parent=dialog)
                        else:
                            messagebox.showerror("错误", "删除失败。", parent=dialog)
                            
                ctk.CTkButton(row, text="🗑️", width=30, height=24, fg_color="#C0392B", command=do_delete).pack(side="right", padx=5, pady=2)

        refresh_list()

    def run(self) -> None:
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.root.destroy()
            sys.exit(0)


if __name__ == "__main__":
    import signal
    import sys

    def signal_handler(sig, frame):
        print("\n[系统] 🛑 捕获 Ctrl+C，程序正在退出...")
        try:
            if 'app' in globals() and app.root.winfo_exists():
                app.root.quit()
                app.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    app = VintedAutomationConsole()
    app.run()
