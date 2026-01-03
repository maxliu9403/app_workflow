"""
流程编排器 Tab
==============

提供可视化的节点编排功能
"""

import json
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import customtkinter as ctk

from models.data_types import WorkflowNode
from models.constants import NODE_STYLES, QUICK_VARIABLES
from tabs.base_tab import BaseTab

if TYPE_CHECKING:
    from app.main_window import MainWindow


class OrchestratorTab(BaseTab):
    """
    流程编排器 Tab
    
    提供可视化节点编排功能，支持:
    - 从节点库拖拽添加节点
    - 节点间拖拽连接
    - 节点属性编辑
    - 导入/导出 JSON
    - 直接运行工作流
    """
    
    def __init__(self, parent: ctk.CTkFrame, app: "MainWindow"):
        # 初始化编排器状态
        self.nodes: Dict[str, WorkflowNode] = {}
        self.connections: List[Tuple[str, str]] = []
        self.selected_node: Optional[str] = None
        self.drag_node_id: Optional[str] = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.connecting_from: Optional[str] = None
        self.temp_line_id: Optional[int] = None
        self.node_canvas_items: Dict[str, List[int]] = {}
        self.connection_lines: Dict[Tuple[str, str], int] = {}
        
        # 属性面板变量
        self.prop_name_var = ctk.StringVar(value="")
        self.prop_action_var = ctk.StringVar(value="Click Region")
        self.prop_params_var = ctk.StringVar(value="")
        self.prop_retry_var = ctk.StringVar(value="0")
        self.prop_optional_var = ctk.BooleanVar(value=False)
        self.prop_x1_var = ctk.StringVar(value="0.0")
        self.prop_y1_var = ctk.StringVar(value="0.0")
        self.prop_x2_var = ctk.StringVar(value="0.0")
        self.prop_y2_var = ctk.StringVar(value="0.0")
        
        super().__init__(parent, app)
    
    def _build_ui(self) -> None:
        """构建流程编排器 UI"""
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)   # 左：节点库
        self.parent.grid_columnconfigure(1, weight=4)   # 中：画布
        self.parent.grid_columnconfigure(2, weight=2)   # 右：属性面板

        self._build_palette()
        self._build_canvas()
        self._build_property_panel()
    
    def _build_palette(self) -> None:
        """构建左侧节点库"""
        palette_frame = ctk.CTkFrame(self.parent, width=180)
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
            text="点击添加节点到画布",
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
                command=lambda at=action_type: self._add_node_from_palette(at),
            )
            btn.grid(row=idx, column=0, sticky="ew", padx=5, pady=3)
    
    def _build_canvas(self) -> None:
        """构建中间编排画布"""
        canvas_frame = ctk.CTkFrame(self.parent)
        canvas_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg="#1e1e1e",
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # 画布事件绑定
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.canvas.bind("<Delete>", self._delete_selected_node)
        self.canvas.bind("<BackSpace>", self._delete_selected_node)
        self.canvas.bind("<Configure>", lambda e: self._draw_grid())

        # 底部工具栏
        toolbar = ctk.CTkFrame(canvas_frame, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        toolbar.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkButton(
            toolbar,
            text="📥 导入 JSON",
            fg_color="#555555",
            command=self._import_json,
        ).grid(row=0, column=0, sticky="ew", padx=3)

        ctk.CTkButton(
            toolbar,
            text="📤 导出 JSON",
            fg_color="#2196F3",
            command=self._export_json,
        ).grid(row=0, column=1, sticky="ew", padx=3)

        ctk.CTkButton(
            toolbar,
            text="▶️ 运行流程",
            fg_color="#4CAF50",
            command=self._run_workflow,
        ).grid(row=0, column=2, sticky="ew", padx=3)

        ctk.CTkButton(
            toolbar,
            text="🔗 自动连接",
            fg_color="#FF9800",
            command=self._auto_connect,
        ).grid(row=0, column=3, sticky="ew", padx=3)

        ctk.CTkButton(
            toolbar,
            text="🗑️ 清空画布",
            fg_color="#F44336",
            command=self._clear_canvas,
        ).grid(row=0, column=4, sticky="ew", padx=3)
    
    def _build_property_panel(self) -> None:
        """构建右侧属性面板"""
        prop_frame = ctk.CTkFrame(self.parent, width=280)
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
        self.prop_name_entry = ctk.CTkEntry(prop_frame, textvariable=self.prop_name_var)
        self.prop_name_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)

        # 动作类型
        ctk.CTkLabel(prop_frame, text="动作类型:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.prop_action_combo = ctk.CTkComboBox(
            prop_frame,
            variable=self.prop_action_var,
            values=list(NODE_STYLES.keys()),
            state="readonly",
        )
        self.prop_action_combo.grid(row=2, column=1, sticky="ew", padx=10, pady=5)

        # 参数
        ctk.CTkLabel(prop_frame, text="参数:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.prop_params_entry = ctk.CTkEntry(
            prop_frame,
            textvariable=self.prop_params_var,
            placeholder_text="${Variable} 或 eval:..."
        )
        self.prop_params_entry.grid(row=3, column=1, sticky="ew", padx=10, pady=5)

        # 变量快捷插入
        var_frame = ctk.CTkFrame(prop_frame, fg_color="transparent")
        var_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(var_frame, text="快捷变量:", font=ctk.CTkFont(size=11)).pack(side="left")
        for var_name in QUICK_VARIABLES[:4]:
            ctk.CTkButton(
                var_frame,
                text=f"${{{var_name}}}",
                width=60,
                height=24,
                fg_color="#333333",
                command=lambda v=var_name: self._insert_variable(v),
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
        ctk.CTkEntry(coord_grid, textvariable=self.prop_x1_var, width=60).grid(row=0, column=1, sticky="ew", padx=2)
        ctk.CTkLabel(coord_grid, text="Y1:").grid(row=0, column=2, sticky="w", padx=2)
        ctk.CTkEntry(coord_grid, textvariable=self.prop_y1_var, width=60).grid(row=0, column=3, sticky="ew", padx=2)

        ctk.CTkLabel(coord_grid, text="X2:").grid(row=1, column=0, sticky="w", padx=2, pady=3)
        ctk.CTkEntry(coord_grid, textvariable=self.prop_x2_var, width=60).grid(row=1, column=1, sticky="ew", padx=2)
        ctk.CTkLabel(coord_grid, text="Y2:").grid(row=1, column=2, sticky="w", padx=2)
        ctk.CTkEntry(coord_grid, textvariable=self.prop_y2_var, width=60).grid(row=1, column=3, sticky="ew", padx=2)

        # 从实时调试同步坐标
        ctk.CTkButton(
            prop_frame,
            text="📥 从实时调试同步坐标",
            fg_color="#4a90d9",
            command=self._sync_coords_from_live,
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
        ctk.CTkEntry(retry_frame, textvariable=self.prop_retry_var, width=50).pack(side="left", padx=5)

        ctk.CTkCheckBox(
            prop_frame,
            text="可选步骤 (失败不中断)",
            variable=self.prop_optional_var,
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        # 保存按钮
        ctk.CTkButton(
            prop_frame,
            text="💾 保存修改",
            fg_color="#2e8b57",
            height=40,
            command=self._save_node_properties,
        ).grid(row=11, column=0, columnspan=2, sticky="ew", padx=10, pady=20)

        # 提示标签
        self.hint_label = ctk.CTkLabel(
            prop_frame,
            text="点击节点查看属性",
            text_color="#666666",
            font=ctk.CTkFont(size=11),
        )
        self.hint_label.grid(row=12, column=0, columnspan=2, sticky="w", padx=10)
    
    # ==================== 工具方法 ====================
    
    @staticmethod
    def _darken_color(hex_color: str, factor: float = 0.8) -> str:
        """将颜色变暗"""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r, g, b = int(r * factor), int(g * factor), int(b * factor)
        return f"#{r:02x}{g:02x}{b:02x}"
    
    # ==================== 画布操作 ====================
    
    def _draw_grid(self) -> None:
        """绘制画布网格背景"""
        self.canvas.delete("grid")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        grid_size = 30
        grid_color = "#2a2a2a"

        for x in range(0, w, grid_size):
            self.canvas.create_line(x, 0, x, h, fill=grid_color, tags="grid")
        for y in range(0, h, grid_size):
            self.canvas.create_line(0, y, w, y, fill=grid_color, tags="grid")

        self.canvas.tag_lower("grid")

    def _add_node_from_palette(self, action_type: str) -> None:
        """从节点库添加节点到画布"""
        base_x = 200 + len(self.nodes) * 30
        base_y = 100 + (len(self.nodes) % 5) * 80

        node_id = str(uuid.uuid4())[:8]
        step_name = f"Step {len(self.nodes) + 1}"

        node = WorkflowNode(
            id=node_id,
            action_type=action_type,
            step_name=step_name,
            canvas_x=base_x,
            canvas_y=base_y,
        )

        self.nodes[node_id] = node
        self._draw_node(node)
        self._select_node(node_id)
        self.log(f"[编排] 添加节点: {step_name} ({action_type})")

    def _draw_node(self, node: WorkflowNode) -> None:
        """绘制单个节点"""
        style = NODE_STYLES.get(node.action_type, {"color": "#666666", "icon": "?", "label": "未知"})

        x, y = node.canvas_x, node.canvas_y
        w, h = 140, 60

        # 清除旧的绘制
        if node.id in self.node_canvas_items:
            for item_id in self.node_canvas_items[node.id]:
                self.canvas.delete(item_id)

        items = []

        # 节点背景
        rect_id = self.canvas.create_rectangle(
            x, y, x + w, y + h,
            fill=style["color"],
            outline="#ffffff" if self.selected_node == node.id else "#444444",
            width=3 if self.selected_node == node.id else 1,
            tags=("node", f"node_{node.id}"),
        )
        items.append(rect_id)

        # 节点标题
        title_text = f"{style['icon']} {node.step_name}"
        if len(title_text) > 16:
            title_text = title_text[:14] + "..."

        title_id = self.canvas.create_text(
            x + w // 2, y + 20,
            text=title_text,
            fill="white",
            font=("Arial", 11, "bold"),
            tags=("node", f"node_{node.id}"),
        )
        items.append(title_id)

        # 动作类型标签
        action_id = self.canvas.create_text(
            x + w // 2, y + 42,
            text=style["label"],
            fill="#cccccc",
            font=("Arial", 9),
            tags=("node", f"node_{node.id}"),
        )
        items.append(action_id)

        # 输出端口
        out_dot_id = self.canvas.create_oval(
            x + w - 5, y + h // 2 - 5,
            x + w + 5, y + h // 2 + 5,
            fill="#ffffff",
            outline=style["color"],
            tags=("output_port", f"output_{node.id}"),
        )
        items.append(out_dot_id)

        # 输入端口
        in_dot_id = self.canvas.create_oval(
            x - 5, y + h // 2 - 5,
            x + 5, y + h // 2 + 5,
            fill="#ffffff",
            outline=style["color"],
            tags=("input_port", f"input_{node.id}"),
        )
        items.append(in_dot_id)

        self.node_canvas_items[node.id] = items

    def _draw_all_nodes(self) -> None:
        """重绘所有节点"""
        for node in self.nodes.values():
            self._draw_node(node)
        self._draw_all_connections()

    def _draw_connection(self, from_id: str, to_id: str) -> None:
        """绘制两个节点之间的连接线（贝塞尔曲线）"""
        if from_id not in self.nodes or to_id not in self.nodes:
            return

        from_node = self.nodes[from_id]
        to_node = self.nodes[to_id]

        x1 = from_node.canvas_x + 140
        y1 = from_node.canvas_y + 30
        x2 = to_node.canvas_x
        y2 = to_node.canvas_y + 30

        cx1 = x1 + abs(x2 - x1) / 3
        cy1 = y1
        cx2 = x2 - abs(x2 - x1) / 3
        cy2 = y2

        points = []
        for t in [i / 20 for i in range(21)]:
            px = (1-t)**3 * x1 + 3*(1-t)**2*t * cx1 + 3*(1-t)*t**2 * cx2 + t**3 * x2
            py = (1-t)**3 * y1 + 3*(1-t)**2*t * cy1 + 3*(1-t)*t**2 * cy2 + t**3 * y2
            points.extend([px, py])

        key = (from_id, to_id)
        if key in self.connection_lines:
            self.canvas.delete(self.connection_lines[key])

        line_id = self.canvas.create_line(
            points,
            fill="#888888",
            width=2,
            smooth=True,
            arrow=tk.LAST,
            arrowshape=(10, 12, 5),
            tags=("connection", f"conn_{from_id}_{to_id}"),
        )
        self.connection_lines[key] = line_id
        self.canvas.tag_lower("connection")

    def _draw_all_connections(self) -> None:
        """重绘所有连接线"""
        for from_id, to_id in self.connections:
            self._draw_connection(from_id, to_id)

    # ==================== 画布事件 ====================

    def _on_canvas_click(self, event) -> None:
        """画布点击事件"""
        self.canvas.focus_set()

        items = self.canvas.find_overlapping(event.x - 5, event.y - 5, event.x + 5, event.y + 5)
        for item in items:
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("output_"):
                    node_id = tag.replace("output_", "")
                    self.connecting_from = node_id
                    return

        for item in items:
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("node_"):
                    node_id = tag.replace("node_", "")
                    self._select_node(node_id)
                    node = self.nodes[node_id]
                    self.drag_node_id = node_id
                    self.drag_offset = (event.x - node.canvas_x, event.y - node.canvas_y)
                    return

        self._deselect_node()

    def _on_canvas_drag(self, event) -> None:
        """画布拖拽事件"""
        if self.connecting_from:
            if self.temp_line_id:
                self.canvas.delete(self.temp_line_id)

            from_node = self.nodes.get(self.connecting_from)
            if from_node:
                x1 = from_node.canvas_x + 140
                y1 = from_node.canvas_y + 30
                self.temp_line_id = self.canvas.create_line(
                    x1, y1, event.x, event.y,
                    fill="#aaaaaa",
                    width=2,
                    dash=(5, 3),
                )
            return

        if self.drag_node_id:
            node = self.nodes.get(self.drag_node_id)
            if node:
                node.canvas_x = event.x - self.drag_offset[0]
                node.canvas_y = event.y - self.drag_offset[1]
                self._draw_node(node)
                self._draw_all_connections()

    def _on_canvas_release(self, event) -> None:
        """画布释放事件"""
        if self.connecting_from:
            if self.temp_line_id:
                self.canvas.delete(self.temp_line_id)
                self.temp_line_id = None

            items = self.canvas.find_overlapping(event.x - 10, event.y - 10, event.x + 10, event.y + 10)
            for item in items:
                tags = self.canvas.gettags(item)
                for tag in tags:
                    if tag.startswith("input_"):
                        to_node_id = tag.replace("input_", "")
                        if to_node_id != self.connecting_from:
                            conn = (self.connecting_from, to_node_id)
                            if conn not in self.connections:
                                self.connections.append(conn)
                                self._draw_connection(*conn)
                                self.log(f"[编排] 连接: {self.connecting_from} → {to_node_id}")
                        break

            self.connecting_from = None

        self.drag_node_id = None

    def _on_canvas_double_click(self, event) -> None:
        """画布双击事件"""
        if self.selected_node:
            self.prop_name_entry.focus_set()
            self.prop_name_entry.select_range(0, tk.END)

    # ==================== 节点操作 ====================

    def _select_node(self, node_id: str) -> None:
        """选中节点"""
        self.selected_node = node_id
        node = self.nodes.get(node_id)
        if node:
            self.prop_name_var.set(node.step_name)
            self.prop_action_var.set(node.action_type)
            self.prop_params_var.set(node.params)
            self.prop_retry_var.set(str(node.retry_count))
            self.prop_optional_var.set(node.is_optional)
            self.prop_x1_var.set(str(node.coords.get("x1", 0)))
            self.prop_y1_var.set(str(node.coords.get("y1", 0)))
            self.prop_x2_var.set(str(node.coords.get("x2", 0)))
            self.prop_y2_var.set(str(node.coords.get("y2", 0)))
            self.hint_label.configure(text=f"已选中: {node.step_name}")

        self._draw_all_nodes()

    def _deselect_node(self) -> None:
        """取消选中"""
        self.selected_node = None
        self.hint_label.configure(text="点击节点查看属性")
        self._draw_all_nodes()

    def _delete_selected_node(self, event=None) -> None:
        """删除选中的节点"""
        if not self.selected_node:
            return

        node_id = self.selected_node
        node = self.nodes.get(node_id)

        if node_id in self.node_canvas_items:
            for item_id in self.node_canvas_items[node_id]:
                self.canvas.delete(item_id)
            del self.node_canvas_items[node_id]

        self.connections = [
            (f, t) for f, t in self.connections
            if f != node_id and t != node_id
        ]

        keys_to_delete = [k for k in self.connection_lines if node_id in k]
        for key in keys_to_delete:
            self.canvas.delete(self.connection_lines[key])
            del self.connection_lines[key]

        if node_id in self.nodes:
            del self.nodes[node_id]

        self._deselect_node()
        self.log(f"[编排] 删除节点: {node.step_name if node else node_id}")

    def _save_node_properties(self) -> None:
        """保存节点属性"""
        if not self.selected_node:
            messagebox.showwarning("提示", "请先选择一个节点")
            return

        node = self.nodes.get(self.selected_node)
        if not node:
            return

        node.step_name = self.prop_name_var.get()
        node.action_type = self.prop_action_var.get()
        node.params = self.prop_params_var.get()

        try:
            node.retry_count = int(self.prop_retry_var.get())
        except ValueError:
            node.retry_count = 0

        node.is_optional = self.prop_optional_var.get()

        try:
            node.coords = {
                "x1": float(self.prop_x1_var.get()),
                "y1": float(self.prop_y1_var.get()),
                "x2": float(self.prop_x2_var.get()),
                "y2": float(self.prop_y2_var.get()),
            }
        except ValueError:
            pass

        self._draw_node(node)
        self.log(f"[编排] 保存节点: {node.step_name}")
        self.hint_label.configure(text=f"已保存: {node.step_name}")

    def _insert_variable(self, var_name: str) -> None:
        """插入变量到参数框"""
        current = self.prop_params_var.get()
        self.prop_params_var.set(current + f"${{{var_name}}}")

    def _sync_coords_from_live(self) -> None:
        """从实时调试同步坐标"""
        try:
            # 尝试从主窗口获取实时调试坐标
            live_tab = getattr(self.app, 'live_tab', None)
            if live_tab and hasattr(live_tab, 'x1_var'):
                self.prop_x1_var.set(live_tab.x1_var.get())
                self.prop_y1_var.set(live_tab.y1_var.get())
                self.prop_x2_var.set(live_tab.x2_var.get())
                self.prop_y2_var.set(live_tab.y2_var.get())
                self.log("[编排] 已从实时调试同步坐标")
            else:
                self.log("[编排] 无法同步坐标：实时调试 Tab 不可用")
        except Exception as e:
            self.log(f"[编排] 同步坐标失败: {e}")

    # ==================== 工具栏操作 ====================

    def _auto_connect(self) -> None:
        """自动按顺序连接所有节点"""
        if len(self.nodes) < 2:
            messagebox.showinfo("提示", "需要至少 2 个节点才能自动连接")
            return

        sorted_nodes = sorted(self.nodes.values(), key=lambda n: (n.canvas_x, n.canvas_y))

        self.connections.clear()
        for line_id in self.connection_lines.values():
            self.canvas.delete(line_id)
        self.connection_lines.clear()

        for i in range(len(sorted_nodes) - 1):
            conn = (sorted_nodes[i].id, sorted_nodes[i + 1].id)
            self.connections.append(conn)

        self._draw_all_connections()
        self.log(f"[编排] 自动连接 {len(self.connections)} 条线")

    def _clear_canvas(self) -> None:
        """清空画布"""
        if not self.nodes:
            return

        if not messagebox.askyesno("确认", "确定要清空画布吗？"):
            return

        self.canvas.delete("node")
        self.canvas.delete("connection")
        self.nodes.clear()
        self.connections.clear()
        self.node_canvas_items.clear()
        self.connection_lines.clear()
        self._deselect_node()
        self._draw_grid()
        self.log("[编排] 画布已清空")

    def _clear_canvas_silent(self) -> None:
        """静默清空画布"""
        self.canvas.delete("node")
        self.canvas.delete("connection")
        self.nodes.clear()
        self.connections.clear()
        self.node_canvas_items.clear()
        self.connection_lines.clear()
        self._deselect_node()

    # ==================== 导入/导出 ====================

    def _topological_sort(self) -> List[WorkflowNode]:
        """拓扑排序获取节点执行顺序"""
        if not self.connections:
            return sorted(self.nodes.values(), key=lambda n: (n.canvas_x, n.canvas_y))

        in_degree = {node_id: 0 for node_id in self.nodes}
        adj = {node_id: [] for node_id in self.nodes}

        for from_id, to_id in self.connections:
            if from_id in adj and to_id in in_degree:
                adj[from_id].append(to_id)
                in_degree[to_id] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            queue.sort(key=lambda nid: (self.nodes[nid].canvas_x, self.nodes[nid].canvas_y))
            node_id = queue.pop(0)
            result.append(self.nodes[node_id])

            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        for node in self.nodes.values():
            if node not in result:
                result.append(node)

        return result

    def _export_json(self) -> None:
        """导出为 JSON 文件"""
        if not self.nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        ordered_nodes = self._topological_sort()

        export_data = []
        for i, node in enumerate(ordered_nodes, 1):
            export_data.append(node.to_export_dict(i))

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
            messagebox.showinfo("导出成功", f"已导出 {len(export_data)} 个步骤")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _import_json(self) -> None:
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

            self._clear_canvas_silent()

            for i, item in enumerate(data):
                node_id = str(uuid.uuid4())[:8]
                node = WorkflowNode.from_dict(node_id, item)
                node.canvas_x = 150 + i * 180
                node.canvas_y = 100 + (i % 3) * 100
                self.nodes[node_id] = node

            self._draw_all_nodes()
            self._auto_connect()
            self.log(f"[编排] 已导入 {len(self.nodes)} 个节点")
            messagebox.showinfo("导入成功", f"已导入 {len(self.nodes)} 个节点")

        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _run_workflow(self) -> None:
        """运行当前编排的工作流"""
        if not self.nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        if not self.require_device():
            return

        ordered_nodes = self._topological_sort()
        export_data = [node.to_export_dict(i) for i, node in enumerate(ordered_nodes, 1)]

        try:
            from workflow_runner import WorkflowRunner

            runner = WorkflowRunner(
                self.device,
                phone_width=self.phone_width,
                phone_height=self.phone_height,
            )

            self.log("[编排] 开始执行工作流...")
            
            for step in export_data:
                self.log(f"[编排] 执行: {step['step_name']} - {step['action_type']}")
                success = runner.execute_step(step, {})
                if not success:
                    if step.get("is_optional", False):
                        self.log("[编排] 步骤失败但可选，继续执行")
                    else:
                        self.log("[编排] 步骤失败，工作流中断")
                        messagebox.showerror("执行失败", f"步骤 {step['step_name']} 执行失败")
                        return

            self.log("[编排] 工作流执行完成！")
            messagebox.showinfo("执行完成", "工作流执行完成！")

        except ImportError:
            messagebox.showerror("错误", "未找到 workflow_runner.py")
        except Exception as e:
            self.log(f"[编排] 执行失败: {e}")
            messagebox.showerror("执行失败", str(e))
