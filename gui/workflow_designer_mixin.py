"""
Workflow Designer Mixin
=======================

Contains workflow canvas events, node selection, connection handling,
and node rendering methods for the Workflow Designer tab.
"""

from typing import Any, Dict, List, Optional, Tuple
from tkinter import messagebox
import tkinter as tk

from core.models import WorkflowNode


class WorkflowDesignerMixin:
    """Mixin class for Workflow Designer (工作流设计器) functionality."""
    
    # Type hints for attributes defined in main class
    orch_canvas: Any
    orch_nodes: Dict[str, WorkflowNode]
    orch_connections: List[Tuple[str, str]]
    orch_selected_node: Optional[str]
    orch_drag_node_id: Optional[str]
    orch_drag_offset: Tuple[int, int]
    orch_connecting_from: Optional[str]
    orch_temp_line_id: Optional[int]
    orch_node_canvas_items: Dict[str, List[int]]
    orch_connection_lines: Dict[Tuple[str, str], int]
    orch_manual_connect_from: Optional[str]

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
                    node = self.orch_nodes.get(node_id)
                    if node is None:
                        return
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
                ox, oy = self.orch_drag_offset
                new_x = int(cx - ox)
                new_y = int(cy - oy)
                node.canvas_x = new_x
                node.canvas_y = new_y
                self._orch_redraw_node(node)
                self._orch_update_connections(self.orch_drag_node_id)

    def _orch_on_canvas_release(self, event) -> None:
        """画布释放事件"""
        cx = self.orch_canvas.canvasx(event.x)
        cy = self.orch_canvas.canvasy(event.y)

        # 完成连接
        if self.orch_connecting_from:
            if self.orch_temp_line_id:
                self.orch_canvas.delete(self.orch_temp_line_id)
                self.orch_temp_line_id = None

            items = self.orch_canvas.find_overlapping(cx - 8, cy - 8, cx + 8, cy + 8)
            for item in items:
                tags = self.orch_canvas.gettags(item)
                for tag in tags:
                    if tag.startswith("input_") and tag != "input_port":
                        to_id = tag.replace("input_", "")
                        if to_id in self.orch_nodes and to_id != self.orch_connecting_from:
                            conn = (self.orch_connecting_from, to_id)
                            if conn not in self.orch_connections:
                                self.orch_connections.append(conn)
                                self._orch_draw_connection(self.orch_connecting_from, to_id)
                                from_node = self.orch_nodes.get(self.orch_connecting_from)
                                to_node = self.orch_nodes.get(to_id)
                                self.log(f"[编排] 🔗 已连接: {from_node.step_name} → {to_node.step_name}")
                        self.orch_connecting_from = None
                        return
            self.orch_connecting_from = None

        # 结束节点拖拽
        if self.orch_drag_node_id:
            self._gen_autosave()
            self.orch_drag_node_id = None

    def _orch_select_node(self, node_id: str) -> None:
        """选中节点"""
        if self.orch_selected_node == node_id:
            return
        
        # 取消之前选中的节点
        if self.orch_selected_node:
            self._orch_deselect_node()
        
        self.orch_selected_node = node_id
        node = self.orch_nodes.get(node_id)
        if not node:
            return
        
        # 绘制选中效果
        for item_id in self.orch_node_canvas_items.get(node_id, []):
            try:
                self.orch_canvas.itemconfigure(item_id, width=3)
            except Exception:
                pass
        
        # 更新 Inspector 面板
        self._is_updating_ui = True
        try:
            self.gen_step_var.set(node.step_name)
            self.gen_action_var.set(node.action_type)
            self.gen_param_var.set(node.params)
            self.gen_context_var.set(node.context)
            self.gen_x1_var.set(f"{node.coords.get('x1', 0):.3f}")
            self.gen_y1_var.set(f"{node.coords.get('y1', 0):.3f}")
            self.gen_x2_var.set(f"{node.coords.get('x2', 0):.3f}")
            self.gen_y2_var.set(f"{node.coords.get('y2', 0):.3f}")
            
            # Update category based on action
            cat = self._find_category_for_action(node.action_type)
            if cat:
                self.gen_category_var.set(cat)
            
            self._update_inspector_visibility()
            self._update_param_shortcuts(node.action_type)
        finally:
            self._is_updating_ui = False

    def _orch_deselect_node(self) -> None:
        """取消选中"""
        if self.orch_selected_node:
            self.orch_selected_node = None
            self._orch_draw_all_nodes()
