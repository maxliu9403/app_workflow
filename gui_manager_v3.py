import re
import time
import json
import os
import uuid
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

# Import from core module for better code organization
from core.models import RoiPct, WorkflowNode
from core.constants import (
    ACTION_CATEGORIES, NODE_STYLES, NODE_PARAM_SHORTCUTS, LOGIC_ACTIONS,
    ACTION_PARAM_TEMPLATES, ACTION_PLACEHOLDERS  # V10.2
)

# Import Mixins for modular code organization
from gui.device_mixin import DeviceMixin
from gui.live_debugger_mixin import LiveDebuggerMixin
from gui.workflow_designer_mixin import WorkflowDesignerMixin
from gui.inspector_mixin import InspectorMixin
from gui.code_export_mixin import CodeExportMixin  # V10.4: Code Export


class VintedAutomationConsole(DeviceMixin, LiveDebuggerMixin, WorkflowDesignerMixin, InspectorMixin, CodeExportMixin):
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
        
        # V9.0: Global Variable Library
        self.global_vars = {} # {Key: Value}
        self._load_global_vars()

        self.gen_queue_var = ctk.StringVar()
        
        # V8.3: HTTP Request Node Variables
        self.http_url_var = ctk.StringVar()
        # Port removed
        self.http_method_var = ctk.StringVar(value="GET")
        self.http_logic_var = ctk.StringVar(value="res.status_code == 200")
        self.http_timeout_var = ctk.StringVar(value="10")
        self.http_body_content = "" # Mirror of text widget
        
        # V7.0: 绑定变量追踪，实现 Inspector -> Node 的实时更新
        self._is_updating_ui = False
        
        self.http_url_var.trace_add("write", self._on_http_inspector_change)
        # Port removed
        self.http_method_var.trace_add("write", self._on_http_inspector_change)
        self.http_logic_var.trace_add("write", self._on_http_inspector_change)
        self.http_timeout_var.trace_add("write", self._on_http_inspector_change)

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
        
    def _build_http_inspector(self, parent):
        """V8.3: Build specialized HTTP Request Inspector"""
        self.http_prop_frame = ctk.CTkFrame(parent, fg_color="transparent")
        
        # URL & Method
        row1 = ctk.CTkFrame(self.http_prop_frame, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="Method:", width=50).pack(side="left")
        ctk.CTkComboBox(row1, variable=self.http_method_var, values=["GET", "POST", "PUT", "DELETE"], width=80).pack(side="left", padx=5)
        ctk.CTkLabel(row1, text="URL:", width=40).pack(side="left")
        ctk.CTkEntry(row1, textvariable=self.http_url_var, placeholder_text="http://api.com").pack(side="left", fill="x", expand=True)

        # Port & Timeout
        row2 = ctk.CTkFrame(self.http_prop_frame, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        # Port removed
        ctk.CTkLabel(row2, text="Timeout:", width=60).pack(side="left")
        ctk.CTkEntry(row2, textvariable=self.http_timeout_var, width=60).pack(side="left")
        
        # Body (Key-Value Editor)
        ctk.CTkLabel(self.http_prop_frame, text="Request Body (Key-Value):", anchor="w").pack(fill="x", pady=(5,0))
        
        # Header (Key | Value | Del)
        header_frame = ctk.CTkFrame(self.http_prop_frame, fg_color="transparent", height=24)
        header_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(header_frame, text="Key", width=80, anchor="w", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=5)
        # Value expands
        ctk.CTkLabel(header_frame, text="Value (supports ${v})", anchor="w", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=5, fill="x", expand=True)
        # Placeholder for delete btn alignment
        ctk.CTkLabel(header_frame, text="", width=24).pack(side="right", padx=2)

        # Scrollable container for rows
        self.http_kv_frame = ctk.CTkScrollableFrame(self.http_prop_frame, height=120, fg_color="transparent")
        self.http_kv_frame.pack(fill="x", pady=2)
        
        # Add Button
        ctk.CTkButton(self.http_prop_frame, text="+ Add Field", height=24, fg_color="#555", command=self._add_http_kv_row).pack(fill="x", pady=2)
        
        self.http_kv_rows = [] # List of (key_entry, value_entry, row_frame)
        
        # Logic
        ctk.CTkLabel(self.http_prop_frame, text="Success Logic (e.g. res.status = 200):", anchor="w").pack(fill="x", pady=(5,0))
        ctk.CTkEntry(self.http_prop_frame, textvariable=self.http_logic_var).pack(fill="x", pady=2)

    def _add_http_kv_row(self, key="", val=""):
        row = ctk.CTkFrame(self.http_kv_frame, fg_color="transparent")
        row.pack(fill="x", pady=1)
        
        k_ent = ctk.CTkEntry(row, width=80, placeholder_text="key")
        k_ent.pack(side="left", padx=2)
        if key: k_ent.insert(0, key)
        k_ent.bind("<KeyRelease>", self._sync_kv_to_json)
        
        v_ent = ctk.CTkEntry(row, placeholder_text="val")
        v_ent.pack(side="left", fill="x", expand=True, padx=2)
        if val: v_ent.insert(0, val)
        v_ent.bind("<KeyRelease>", self._sync_kv_to_json)


        
        del_btn = ctk.CTkButton(row, text="×", width=24, height=24, fg_color="#C0392B", command=lambda r=row: self._remove_http_kv_row(r))
        del_btn.pack(side="right", padx=2)
        
        self.http_kv_rows.append((k_ent, v_ent, row))
        self._sync_kv_to_json()

    def _show_global_vars_dialog(self):
        """V9.0: Show Global Variable Library Dialog"""
        if hasattr(self, 'global_vars_window') and self.global_vars_window is not None and self.global_vars_window.winfo_exists():
            self.global_vars_window.focus()
            return

        self.global_vars_window = ctk.CTkToplevel(self.root)
        self.global_vars_window.title("Global Variable Library")
        self.global_vars_window.geometry("500x400")
        self.global_vars_window.attributes("-topmost", True)
        
        # Header
        ctk.CTkLabel(self.global_vars_window, text="Global Variables", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        ctk.CTkLabel(self.global_vars_window, text="Accessible in node params via ${Key}", text_color="gray").pack()

        # Canvas for entries
        self.gv_scroll = ctk.CTkScrollableFrame(self.global_vars_window, width=450, height=250)
        self.gv_scroll.pack(padx=10, pady=10, fill="both", expand=True)

        self.gv_entries = [] # List of (key_entry, val_entry, frame)

        # Populate existing
        for k, v in self.global_vars.items():
            self._add_gv_row(k, v)

        # Control Bar
        ctrl_frame = ctk.CTkFrame(self.global_vars_window, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(ctrl_frame, text="+ Add Variable", command=lambda: self._add_gv_row()).pack(side="left", padx=5)
        ctk.CTkButton(ctrl_frame, text="Save & Close", fg_color="green", command=self._save_global_vars).pack(side="right", padx=5)

    def _add_gv_row(self, k="", v=""):
        row = ctk.CTkFrame(self.gv_scroll, fg_color="transparent")
        row.pack(fill="x", pady=2)
        
        k_ent = ctk.CTkEntry(row, width=120, placeholder_text="Key")
        k_ent.pack(side="left", padx=2)
        if k: k_ent.insert(0, k)
        # Lock DeviceID
        if k == "DeviceID": k_ent.configure(state="disabled")

        v_ent = ctk.CTkEntry(row, placeholder_text="Value")
        v_ent.pack(side="left", fill="x", expand=True, padx=2)
        if v: v_ent.insert(0, str(v))
        
        if k != "DeviceID":
            del_btn = ctk.CTkButton(row, text="×", width=24, height=24, fg_color="#C0392B", command=lambda r=row: self._remove_gv_row(r))
            del_btn.pack(side="right", padx=2)
        else:
             ctk.CTkLabel(row, text="🔒", width=24).pack(side="right", padx=2)

        self.gv_entries.append((k_ent, v_ent, row))

    def _remove_gv_row(self, row_obj):
        self.gv_entries = [r for r in self.gv_entries if r[2] != row_obj]
        row_obj.destroy()

    def _save_global_vars(self):
        new_vars = {}
        for k_e, v_e, _ in self.gv_entries:
            key = k_e.get().strip()
            val = v_e.get().strip()
            if key:
                new_vars[key] = val
        
        self.global_vars = new_vars
        self.log(f"[Global] Variables updated: {len(self.global_vars)} keys")
        
        # Persistence
        try:
            with open("global_vars.json", "w", encoding="utf-8") as f:
                json.dump(self.global_vars, f, indent=2)
            self.log("[Global] Variables saved to global_vars.json")
        except Exception as e:
            self.log(f"[Global] Save failed: {e}")

        if self.global_vars_window:
            self.global_vars_window.destroy()

    def _load_global_vars(self):
        try:
            if os.path.exists("global_vars.json"):
                with open("global_vars.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.global_vars.update(data)
                        self.log(f"[Global] Loaded {len(data)} variables")
        except Exception as e:
            self.log(f"[Global] Load failed: {e}")

    def _refresh_variable_watcher(self):
        """V10.0: Refresh Variable Watcher TreeView with current variables"""
        if not hasattr(self, 'var_watcher_tree'):
            return
        
        # Clear existing items
        for item in self.var_watcher_tree.get_children():
            self.var_watcher_tree.delete(item)
        
        # Collect variables from multiple sources
        all_vars = {}
        
        # 1. Global variables
        if hasattr(self, 'global_vars') and self.global_vars:
            all_vars.update(self.global_vars)
        
        # 2. Runtime VariableStore (if workflow runner is active)
        if hasattr(self, 'workflow_runner') and self.workflow_runner:
            if hasattr(self.workflow_runner, 'variable_store'):
                runtime_vars = self.workflow_runner.variable_store.variables
                all_vars.update(runtime_vars)
        
        # 3. Device ID (if connected)
        if self.device:
            all_vars["DeviceID"] = self.device.serial
        
        # Populate TreeView
        for key, value in sorted(all_vars.items()):
            # Determine type
            val_type = type(value).__name__
            if val_type == "str":
                val_type = "str"
            elif val_type in ("int", "float"):
                val_type = val_type
            elif val_type == "list":
                val_type = "list"
            elif val_type == "dict":
                val_type = "dict"
            elif val_type == "bool":
                val_type = "bool"
            else:
                val_type = "?"
            
            # Truncate long values for display
            display_val = str(value)
            if len(display_val) > 40:
                display_val = display_val[:37] + "..."
            
            self.var_watcher_tree.insert(
                "",
                "end",
                values=(key, val_type, display_val)
            )
        
        self.log(f"[VarWatcher] Refreshed: {len(all_vars)} variables")


    def _remove_http_kv_row(self, row_widget):
        # Remove from list
        self.http_kv_rows = [r for r in self.http_kv_rows if r[2] != row_widget]
        row_widget.destroy()
        self._sync_kv_to_json()

    def _sync_kv_to_json(self, event=None):
        """Serialize KV rows to JSON string and update params Params"""
        data = {}
        for k_ent, v_ent, _ in self.http_kv_rows:
            k = k_ent.get().strip()
            v = v_ent.get() # Don't strip value, spaces might be needed? Usually strip param values.
            if k:
                data[k] = v
        
        try:
            import json
            self.http_body_content = json.dumps(data)
            self._on_http_inspector_change()
        except:
             pass

    def _on_http_inspector_change(self, *args):
        """Sync HTTP UI -> Node Params JSON"""
        if self._is_updating_ui or not self.orch_selected_node:
            return
            
        # Only if current action is HTTP Request
        if self.gen_action_var.get() != "HTTP Request":
            return

        import json
        node = self.orch_nodes.get(self.orch_selected_node)
        if not node: return
        
        params = {
            "url": self.http_url_var.get(),
            # Port removed
            "method": self.http_method_var.get(),
            "body": self.http_body_content,
            "logic": self.http_logic_var.get(),
            "timeout": self.http_timeout_var.get()
        }
        
        try:
            node.params = json.dumps(params)
             # Update visual label if needed (optional)
            self._orch_draw_node(node)
        except: pass
        

        
        # V3.3: 启动时自动恢复
        self.root.after(500, self._gen_autoload)

        # V8.0: Global Shortcuts
        self.root.bind("<F8>", self._orch_toggle_pause)

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
            "Loop (Count)", "BREAK", "END LOOP", "ELSE", "END IF",
            "HTTP Request"
        }
        
        # V8.3: HTTP Inspector Toggle
        if hasattr(self, 'http_prop_frame'):
            if action_type == "HTTP Request":
                self.http_prop_frame.grid()
                if hasattr(self, 'gen_param_frame'):
                    # Hide dynamic inspector container for HTTP special case
                    self.gen_param_frame.grid_remove() 
            else:
                self.http_prop_frame.grid_remove()
                if hasattr(self, 'inspector_container'):
                    self.inspector_container.grid()
                elif hasattr(self, 'gen_param_frame'):
                    # Fallback
                    self.gen_param_frame.grid()
        
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
        # V8.0: OCR Settings UI
        ocr_settings_frame = ctk.CTkFrame(control_panel)
        ocr_settings_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
        
        ctk.CTkLabel(ocr_settings_frame, text="⚙️ OCR 参数设置", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(5, 5))
        
        # Threshold
        ctk.CTkLabel(ocr_settings_frame, text="二值化阈值:").grid(row=1, column=0, sticky="w", padx=10)
        self.ocr_threshold_var = ctk.IntVar(value=127)
        self.ocr_threshold_slider = ctk.CTkSlider(ocr_settings_frame, from_=0, to=255, variable=self.ocr_threshold_var, number_of_steps=255)
        self.ocr_threshold_slider.grid(row=1, column=1, sticky="ew", padx=10)
        
        # Preprocessing
        ctk.CTkLabel(ocr_settings_frame, text="预处理:").grid(row=2, column=0, sticky="w", padx=10)
        self.ocr_preproc_var = ctk.StringVar(value="Default")
        self.ocr_preproc_combo = ctk.CTkComboBox(ocr_settings_frame, variable=self.ocr_preproc_var, values=["Default", "Grayscale", "Binary", "Otsu"])
        self.ocr_preproc_combo.grid(row=2, column=1, sticky="ew", padx=10, pady=5)

        # Engine
        ctk.CTkLabel(ocr_settings_frame, text="OCR 引擎:").grid(row=3, column=0, sticky="w", padx=10)
        self.ocr_engine_var = ctk.StringVar(value="PaddleOCR")
        self.ocr_engine_combo = ctk.CTkComboBox(ocr_settings_frame, variable=self.ocr_engine_var, values=["PaddleOCR", "Tesseract"])
        self.ocr_engine_combo.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        
        ocr_settings_frame.grid_columnconfigure(1, weight=1)

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
        
        ctk.CTkButton(header_frame, text="🌐 变量", width=60, height=24, fg_color="#E67E22", hover_color="#D35400", font=ctk.CTkFont(size=12, weight="bold"), command=self._show_global_vars_dialog).pack(side="right", padx=5)
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
        ).grid(row=0, column=0, columnspan=1, sticky="w", padx=5, pady=2)
        
        # V10.4: Code Export Button (Action Bar)
        # Using a small frame for buttons if needed
        action_bar = ctk.CTkFrame(step_frame, fg_color="transparent")
        action_bar.grid(row=0, column=1, sticky="e", padx=2, pady=2)
        self._build_code_export_ui(action_bar)

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

        # 动作参数 (Dynamic Inspector)
        # V10.3: Dynamic Inspector Container (Replaces gen_param_frame for UI display)
        self.inspector_container = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.inspector_container.grid(row=2, column=0, sticky="nsew", padx=2, pady=2)
        self.inspector_container.grid_columnconfigure(0, weight=1)
        
        # Build Dynamic UI inside the container
        self._build_inspector_ui(self.inspector_container)

        # Legacy Param Frame (Kept hidden for backward compat of widget references)
        self.gen_param_frame = ctk.CTkFrame(self.left_panel)
        # self.gen_param_frame.grid() # NEVER GRID THIS - Hides legacy clutter
        
        # Legacy components kept for code compatibility (referenced in other methods)
        self.gen_param_entry = ctk.CTkEntry(self.left_panel) # Dummy
        self.gen_operator_combo = ctk.CTkComboBox(self.left_panel, values=[]) # Dummy

        # V8.3: specialized HTTP Inspector (Hidden by default, integrated later?)
        self._build_http_inspector(self.left_panel)
        self.http_prop_frame.grid(row=3, column=0, sticky="ew", padx=2, pady=2)
        self.http_prop_frame.grid_remove() # Default hidden

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

        # V10.2: 模板下拉框 - 帮助用户快速填写参数
        self.gen_template_label = ctk.CTkLabel(self.gen_param_frame, text="📝 模板:", font=ctk.CTkFont(size=11))
        self.gen_template_label.grid(row=4, column=0, sticky="w", padx=5, pady=2)
        
        self.gen_template_var = ctk.StringVar(value="-- 选择模板 --")
        self.gen_template_combo = ctk.CTkComboBox(
            self.gen_param_frame,
            variable=self.gen_template_var,
            values=["-- 选择模板 --"],
            width=220,
            command=self._on_template_selected,
            state="readonly"
        )
        self.gen_template_combo.grid(row=4, column=1, sticky="ew", padx=5, pady=2)
        
        # 存储当前模板映射 {"label": "template_content"}
        self._current_templates: Dict[str, str] = {}

        self.gen_param_label = ctk.CTkLabel(self.gen_param_frame, text="值:")
        self.gen_param_label.grid(row=5, column=0, sticky="w", padx=5, pady=2)
        self.gen_param_entry = ctk.CTkEntry(
            self.gen_param_frame,
            textvariable=self.gen_param_var,
            placeholder_text="Enter value...",
        )
        self.gen_param_entry.grid(row=5, column=1, sticky="ew", padx=(5, 35), pady=2)
        
        self.gen_param_browse_btn = ctk.CTkButton(
            self.gen_param_frame, text="📂", width=30, height=24, fg_color="#444",
            command=self._browse_param_image
        )
        self.gen_param_browse_btn.grid(row=5, column=1, sticky="e", padx=2, pady=2)
        self.gen_param_browse_btn.grid_remove() # Default hidden

        ctk.CTkLabel(self.gen_param_frame, text="备注:").grid(row=6, column=0, sticky="nw", padx=5, pady=2)
        self.gen_context_text = ctk.CTkTextbox(self.gen_param_frame, height=50, font=ctk.CTkFont(size=12))
        self.gen_context_text.grid(row=6, column=1, sticky="ew", padx=5, pady=2)
        
        # V10.2: Variable buttons removed - now using node-based data approach





        # 提示标签
        self.orch_hint_label = ctk.CTkLabel(
            self.left_panel,
            text="点击节点查看属性",
            text_color="#888888",
            font=ctk.CTkFont(size=11),
        )
        self.orch_hint_label.grid(row=5, column=0, sticky="ew", padx=10, pady=(10, 5))

        # === V10.0: Variable Watcher ===
        var_watcher_frame = ctk.CTkFrame(self.left_panel)
        var_watcher_frame.grid(row=6, column=0, sticky="nsew", padx=2, pady=2)
        var_watcher_frame.grid_rowconfigure(1, weight=1)
        var_watcher_frame.grid_columnconfigure(0, weight=1)
        self.left_panel.grid_rowconfigure(6, weight=1)  # Make watcher expandable

        var_header = ctk.CTkFrame(var_watcher_frame, fg_color="transparent")
        var_header.pack(fill="x", padx=5, pady=2)
        
        ctk.CTkLabel(
            var_header,
            text="👁️ 变量监视器",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")
        
        self.var_watcher_refresh_btn = ctk.CTkButton(
            var_header,
            text="🔄",
            width=28, height=24,
            fg_color="#444",
            command=self._refresh_variable_watcher
        )
        self.var_watcher_refresh_btn.pack(side="right", padx=2)

        # TreeView for variables
        var_tree_container = ctk.CTkFrame(var_watcher_frame, fg_color="#1e1e1e")
        var_tree_container.pack(fill="both", expand=True, padx=5, pady=5)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "VarWatcher.Treeview",
            background="#1e1e1e",
            foreground="#e0e0e0",
            fieldbackground="#1e1e1e",
            rowheight=22,
            font=("Consolas", 10)
        )
        style.configure(
            "VarWatcher.Treeview.Heading",
            background="#333",
            foreground="#fff",
            font=("Segoe UI", 10, "bold")
        )

        self.var_watcher_tree = ttk.Treeview(
            var_tree_container,
            columns=("key", "type", "value"),
            show="headings",
            height=6,
            style="VarWatcher.Treeview"
        )
        self.var_watcher_tree.heading("key", text="Key")
        self.var_watcher_tree.heading("type", text="Type")
        self.var_watcher_tree.heading("value", text="Value")
        self.var_watcher_tree.column("key", width=80, anchor="w")
        self.var_watcher_tree.column("type", width=50, anchor="center")
        self.var_watcher_tree.column("value", width=100, anchor="w")
        
        var_scroll = ttk.Scrollbar(var_tree_container, orient="vertical", command=self.var_watcher_tree.yview)
        self.var_watcher_tree.configure(yscrollcommand=var_scroll.set)
        var_scroll.pack(side="right", fill="y")
        self.var_watcher_tree.pack(side="left", fill="both", expand=True)

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

        # 节点列表 Listbox (Split to share space with Log)
        list_container = ctk.CTkFrame(node_list_frame)
        list_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        list_container.grid_rowconfigure(0, weight=2) # List box gets 66%
        list_container.grid_rowconfigure(1, weight=1) # Log box gets 33%
        list_container.grid_columnconfigure(0, weight=1)

        # 1. 节点列表 (Top 66%)
        listbox_frame = ctk.CTkFrame(list_container, fg_color="transparent")
        listbox_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        listbox_frame.grid_rowconfigure(0, weight=1)
        listbox_frame.grid_columnconfigure(0, weight=1)

        self.gen_queue_listbox = tk.Listbox(
            listbox_frame, bg="#2a2a2a", fg="#ffffff",
            selectbackground="#3498db", font=("Consolas", 10), height=10
        )
        self.gen_queue_listbox.grid(row=0, column=0, sticky="nsew")
        self.gen_queue_listbox.bind("<<ListboxSelect>>", self._on_node_list_select)
        self.gen_queue_listbox.bind("<Double-1>", self._gen_on_queue_double_click)
        
        list_scrollbar = tk.Scrollbar(listbox_frame, orient="vertical", command=self.gen_queue_listbox.yview)
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.gen_queue_listbox.configure(yscrollcommand=list_scrollbar.set)

        # 2. 运行日志 (Bottom 33%)
        log_frame = ctk.CTkFrame(list_container, fg_color="transparent")
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(log_frame, text="📜 运行日志", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, sticky="w")
        
        self.orch_log_text = ctk.CTkTextbox(log_frame, font=("Consolas", 9), activate_scrollbars=True)
        self.orch_log_text.grid(row=1, column=0, sticky="nsew")

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

    # Device methods (refresh_device_list, connect_selected_device, etc.)
    # are inherited from gui.device_mixin.DeviceMixin
    
    # Screenshot/coordinate methods (redraw_screenshot, copy_current_coords, etc.)
    # are inherited from gui.live_debugger_mixin.LiveDebuggerMixin

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

    # copy_current_coords and quick_copy_coordinates inherited from LiveDebuggerMixin

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

    # Canvas event handlers (on_canvas_press, on_canvas_drag, on_canvas_release) 
    # and coordinate conversion methods (_is_point_on_image, _canvas_to_phone_px, 
    # _phone_px_to_canvas, _phone_px_to_pct, _pct_to_phone_px, test_click_center)
    # are inherited from gui.live_debugger_mixin.LiveDebuggerMixin

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
            # V10.2: 同时更新模板下拉框
            if hasattr(self, '_update_templates_for_action'):
                self._update_templates_for_action(actions[0])

    def _find_category_for_action(self, action: str) -> str:
        """V5.0: 根据动作类型反查所属类别"""
        for category, actions in ACTION_CATEGORIES.items():
            if action in actions:
                return category
        return list(ACTION_CATEGORIES.keys())[0]

    # ==================== V6.0: 变量插入功能 ====================

    # V10.2: Removed Excel-related methods (now using node-based data approach):
    # - _get_col_letter (removed)
    # - _load_excel_headers (removed)
    # - _select_excel_path (removed)
    # - _load_variable_buttons (removed)
    # - _create_tooltip (removed)
    # - _show_variable_menu (removed)

    # ==================== V10.2: 参数模板系统 ====================

    def _on_template_selected(self, selected: str) -> None:
        """V10.2: 当用户选择模板时，填充参数输入框"""
        if selected == "-- 选择模板 --" or not selected:
            return
        
        # 从映射中获取模板内容
        template_content = self._current_templates.get(selected, "")
        if template_content:
            self.gen_param_var.set(template_content)
            self.gen_log(f"📝 已应用模板: {selected}")
        
        # 重置下拉框显示
        self.gen_template_var.set("-- 选择模板 --")

    def _update_templates_for_action(self, action: str) -> None:
        """V10.2: 根据动作类型更新模板下拉框和占位提示"""
        # 清理动作名称（移除中文注释）
        clean_action = action.split(' (')[0].strip()
        
        # 更新模板下拉框
        templates = ACTION_PARAM_TEMPLATES.get(clean_action, [])
        self._current_templates.clear()
        
        if templates:
            labels = ["-- 选择模板 --"]
            for desc, content, _ in templates:
                label = f"{desc}"
                labels.append(label)
                self._current_templates[label] = content
            
            self.gen_template_combo.configure(values=labels)
            self.gen_template_var.set("-- 选择模板 --")
            self.gen_template_label.grid()
            self.gen_template_combo.grid()
        else:
            self.gen_template_combo.configure(values=["-- 无可用模板 --"])
            self.gen_template_var.set("-- 无可用模板 --")
            # 对于没有模板的动作，可选择隐藏
            # self.gen_template_label.grid_remove()
            # self.gen_template_combo.grid_remove()
        
        # 更新占位提示文本
        placeholder = ACTION_PLACEHOLDERS.get(clean_action, "输入参数...")
        self.gen_param_entry.configure(placeholder_text=placeholder)
    
    def _browse_param_image(self):
        """Select Image for Parameter"""
        path = filedialog.askopenfilename(
            title="Select Template Image",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp")]
        )
        if path:
            self.gen_param_var.set(path)

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
                # V8.2: Fix Terminal "invalid command" errors
                # Cancel all pending after callbacks if possible
                try:
                    for id in app.root.tk.call('after', 'info'):
                        app.root.after_cancel(id)
                except: pass
                
                app.root.quit()
                app.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    app = VintedAutomationConsole()
    app.run()
