"""
Workflow Designer Mixin
=======================

Contains workflow canvas events, node selection, connection handling,
and node rendering methods for the Workflow Designer tab.
"""

from typing import Any, Dict, List, Optional, Tuple
from tkinter import messagebox, simpledialog
import tkinter as tk
import customtkinter as ctk

from pathlib import Path
from PIL import Image, ImageTk

from core.models import WorkflowNode
from core.constants import NODE_STYLES, ACTION_CATEGORIES


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
                self._orch_draw_node(node)
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
            # 1. 更新通用变量
            if hasattr(self, 'gen_step_var'):
                self.gen_step_var.set(node.step_name)
            
            if hasattr(self, 'gen_category_var'):
                category = self._find_category_for_action(node.action_type)
                self.gen_category_var.set(category)
                # Trigger category change logic manually if needed
                if hasattr(self, '_on_gen_category_change'):
                    self._on_gen_category_change(category)

            if hasattr(self, 'gen_action_var'):
                self.gen_action_var.set(node.action_type)

            # 2. 处理参数 (Dynamic Inspector V10.3)
            if hasattr(self, 'load_params_into_form'):
                # 使用新版动态表单加载参数
                self.load_params_into_form(node.action_type, str(node.params))
            elif hasattr(self, 'gen_param_var'):
                # Legacy Fallback
                self.gen_param_var.set(str(node.params))

            # 3. 更新 Context 文本框 (如果存在)
            if hasattr(self, 'gen_context_text'):
                self.gen_context_text.delete("1.0", tk.END)
                self.gen_context_text.insert("1.0", node.context)
                # V7.0: 绑定文本框修改事件
                self.gen_context_text.bind("<KeyRelease>", self._on_inspector_text_change)
            elif hasattr(self, 'gen_context_var'):
                self.gen_context_var.set(node.context)

            # 4. 更新坐标显示
            if hasattr(self, 'gen_x1_var'):
                self.gen_x1_var.set(f"{node.coords.get('x1', 0):.3f}")
                self.gen_y1_var.set(f"{node.coords.get('y1', 0):.3f}")
                self.gen_x2_var.set(f"{node.coords.get('x2', 0):.3f}")
                self.gen_y2_var.set(f"{node.coords.get('y2', 0):.3f}")
            
            # 5. 更新其他 UI 状态
            self._update_inspector_visibility()
            self._update_param_shortcuts(node.action_type)
            
            # 6. 更新提示标签
            if hasattr(self, 'orch_hint_label'):
                self.orch_hint_label.configure(text=f"已选中: {node.step_name}")
                
        finally:
            self._is_updating_ui = False

    def _orch_deselect_node(self) -> None:
        """取消选中"""
        self.orch_selected_node = None
        if hasattr(self, 'orch_hint_label'):
            self.orch_hint_label.configure(text="点击节点查看属性")
        self._orch_draw_all_nodes()

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
        
        # 5. Refresh listbox (Must be implemented in main class or separate mixin)
        if hasattr(self, '_orch_refresh_listbox'):
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
                # Use list copy for safety if iterating? Actually self.orch_connection_lines[key] is a list of IDs.
                # Just deleting them is fine.
                if isinstance(self.orch_connection_lines[key], list):
                    for item_id in self.orch_connection_lines[key]:
                        try:
                            self.orch_canvas.delete(item_id)
                        except Exception:
                            pass
                else: 
                     # Handle single int case if schema differs
                     try:
                        self.orch_canvas.delete(self.orch_connection_lines[key])
                     except Exception:
                        pass
                
                del self.orch_connection_lines[key]
            
            if (from_id, to_id) in self.orch_connections:
                self.orch_connections.remove((from_id, to_id))
        
    # ==================== Layer 2: Rendering Engine ====================

    def _darken_color(self, hex_color: str, factor: float = 0.8) -> str:
        """Helper: Darken a hex color"""
        hex_color = hex_color.lstrip("#")
        try:
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            r, g, b = int(r * factor), int(g * factor), int(b * factor)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

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

    def _orch_scroll_to_node(self, node_id: str) -> None:
        """Scroll canvas to center the specified node"""
        node = self.orch_nodes.get(node_id)
        if not node or not hasattr(self, 'orch_canvas'):
            return
            
        try:
            # 1. Force update scrollregion to ensure it includes all nodes
            self.orch_canvas.update_idletasks()
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
            
            if total_w > view_w and total_w > 0:
                target_left = node_cx - (view_w / 2)
                if target_left < min_x: target_left = min_x
                if target_left > max_x - view_w: target_left = max_x - view_w
                fraction_x = (target_left - min_x) / total_w
                self.orch_canvas.xview_moveto(fraction_x)
                
            if total_h > view_h and total_h > 0:
                target_top = node_cy - (view_h / 2)
                if target_top < min_y: target_top = min_y
                if target_top > max_y - view_h: target_top = max_y - view_h
                fraction_y = (target_top - min_y) / total_h
                self.orch_canvas.yview_moveto(fraction_y)
                
        except Exception as e:
            print(f"Auto-scroll error: {e}")

    def _orch_draw_node(self, node: WorkflowNode) -> None:
        """V7.0: 绘制单个节点 (增强视觉效果)"""
        style = NODE_STYLES.get(node.action_type, {"color": "#666666", "icon": "?", "label": "未知"})

        x, y = node.canvas_x, node.canvas_y
        w, h = 160, 70
        is_selected = self.orch_selected_node == node.id
        is_running = hasattr(self, 'orch_running_node') and self.orch_running_node == node.id

        # 清除旧的绘制
        if node.id in self.orch_node_canvas_items:
            for item_id in self.orch_node_canvas_items[node.id]:
                self.orch_canvas.delete(item_id)

        items = []
        
        # V7.12: Running glow effect
        if is_running:
            glow_id = self.orch_canvas.create_rectangle(
                x - 6, y - 6, x + w + 6, y + h + 6,
                fill="", outline="#ff0000", width=4,
                tags=("node", f"node_{node.id}", "running_glow"),
            )
            items.append(glow_id)
            
            glow2_id = self.orch_canvas.create_rectangle(
                x - 3, y - 3, x + w + 3, y + h + 3,
                fill="", outline="#ff4444", width=2,
                tags=("node", f"node_{node.id}", "running_glow"),
            )
            items.append(glow2_id)
        
        # Shadow
        shadow_id = self.orch_canvas.create_rectangle(
            x + 3, y + 3, x + w + 3, y + h + 3,
            fill="#0a0a0a", outline="",
            tags=("node", f"node_{node.id}"),
        )
        items.append(shadow_id)

        # Background
        bg_color = style["color"]
        if is_running:
            outline_color = "#ff0000"
            outline_width = 4
        elif is_selected:
            outline_color = "#ffff00"
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
        
        # Header
        header_id = self.orch_canvas.create_rectangle(
            x + 1, y + 1, x + w - 1, y + 22,
            fill=self._darken_color(bg_color),
            outline="",
            tags=("node", f"node_{node.id}"),
        )
        items.append(header_id)

        # Title
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

        # Icon/Emoji
        icon_val = style.get("icon", "?")
        icon_x = x + w - 25
        icon_y = y + h // 2 + 5
        
        if isinstance(icon_val, str) and icon_val.lower().endswith(('.png', '.jpg')):
             try:
                 if Path(icon_val).exists():
                     cache_key = f"{icon_val}_32"
                     if hasattr(self, 'orch_node_images'):
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
             emoji_id = self.orch_canvas.create_text(
                  icon_x, icon_y,
                  text=icon_val,
                  font=("Segoe UI Emoji", 24),
                  fill="#555",
                  tags=("node", f"node_{node.id}")
             )
             items.append(emoji_id)

        # Label
        action_id = self.orch_canvas.create_text(
            x + 10, y + 38,
            text=style["label"],
            fill="#dddddd",
            font=("Arial", 9),
            anchor="w",
            tags=("node", f"node_{node.id}"),
        )
        items.append(action_id)
        
        # Params
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

        # Inputs
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

        # Outputs
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
        
        # Breakpoint marker
        if "[BREAKPOINT]" in node.context:
             bp_id = self.orch_canvas.create_oval(
                 x - 10, y - 10, x + 10, y + 10,
                 fill="red", outline="white", width=2,
                 tags=("node", f"node_{node.id}", "breakpoint_marker")
             )
             items.append(bp_id)

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
        # 更新滚动区域
        try:
             self.orch_canvas.configure(scrollregion=self.orch_canvas.bbox("all"))
        except:
             pass

    def _orch_mark_node_success(self, node_id: str) -> None:
        """Helper: Mark a node as successfully executed (Green)"""
        node = self.orch_nodes.get(node_id)
        if node:
            # Re-draw with success color or just override tag
            # For simplicity, we can tag outline or fill
            # Finding the rectangle item:
            items = self.orch_node_canvas_items.get(node_id, [])
            if items:
                 # First item is usually the rect
                 self.orch_canvas.itemconfig(items[0], outline="#2ecc71", width=3)
            self.log(f"[执行成功] {node.step_name}")

    def _orch_mark_node_failed(self, node_id: str) -> None:
        """Helper: Mark a node as failed (Red)"""
        node = self.orch_nodes.get(node_id)
        if node:
             items = self.orch_node_canvas_items.get(node_id, [])
             if items:
                 self.orch_canvas.itemconfig(items[0], outline="#e74c3c", width=3)
             self.log(f"[执行失败] {node.step_name}")

    def _orch_update_connections(self, node_id: str) -> None:
        """更新与指定节点相关的所有连接"""
        related_connections = [
            (from_id, to_id) 
            for from_id, to_id in self.orch_connections 
            if from_id == node_id or to_id == node_id
        ]
        
        for from_id, to_id in related_connections:
            if (from_id, to_id) in self.orch_connection_lines:
                try:
                     items = self.orch_connection_lines[(from_id, to_id)]
                     if isinstance(items, list):
                         for i in items: self.orch_canvas.delete(i)
                     else:
                         self.orch_canvas.delete(items)
                except: pass
            
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

        x1 = from_node.canvas_x + 160
        y1 = from_node.canvas_y + 35
        x2 = to_node.canvas_x
        y2 = to_node.canvas_y + 35

        # Bezier control points
        cx1 = x1 + abs(x2 - x1) / 3
        cy1 = y1
        cx2 = x2 - abs(x2 - x1) / 3
        cy2 = y2

        points = []
        for t in [i / 20 for i in range(21)]:
            px = (1-t)**3 * x1 + 3*(1-t)**2*t * cx1 + 3*(1-t)*t**2 * cx2 + t**3 * x2
            py = (1-t)**3 * y1 + 3*(1-t)**2*t * cy1 + 3*(1-t)*t**2 * cy2 + t**3 * y2
            points.extend([px, py])

        # Remove old line
        key = (from_id, to_id)
        if key in self.orch_connection_lines:
             items = self.orch_connection_lines[key]
             if isinstance(items, list):
                 for i in items: self.orch_canvas.delete(i)
             else:
                 self.orch_canvas.delete(items)

        items = []
        
        # Glow
        glow_id = self.orch_canvas.create_line(
            points,
            fill="#4fc3f7",
            width=6,
            smooth=True,
            tags=("connection", f"conn_{from_id}_{to_id}"),
        )
        items.append(glow_id)
        
        # Main line
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

    def _orch_clear_canvas_items(self) -> None:
        """清除画布上的所有元素记录（用于重绘）"""
        self.orch_canvas.delete("all")
        self.orch_node_canvas_items.clear()
        self.orch_connection_lines.clear()
        self._orch_draw_grid()

    def _orch_highlight_executing_node(self, node_id: str) -> None:
        """高亮正在执行的节点（黄色边框）并自动滚动"""
        self._orch_set_running_node(node_id)
            
    def _orch_set_running_node(self, node_id: str) -> None:
        """设置当前运行节点，重绘并自动滚动"""
        self.orch_running_node = node_id
        self._orch_draw_all_nodes()
        self._orch_scroll_to_node(node_id)
            
    def _orch_mark_node_success(self, node_id: str) -> None:
        """标记节点执行成功（绿色边框）"""
        if node_id not in self.orch_node_canvas_items:
            return
        items = self.orch_node_canvas_items[node_id]
        if items:
            self.orch_canvas.itemconfig(items[0], outline="#00FF00", width=3)
            
    # ==================== Layer 3: UI & Interaction ====================

    def _toggle_canvas_popout(self):
        """Pop out the canvas to a separate window, or dock it back"""
        if hasattr(self, '_canvas_window') and self._canvas_window and self._canvas_window.winfo_exists():
            self._dock_canvas()
        else:
            self._popout_canvas()
    
    def _popout_canvas(self):
        """Move canvas to a separate floating window"""
        self._canvas_window = ctk.CTkToplevel(self.root)
        self._canvas_window.title("🎨 工作流画布 - 独立窗口")
        self._canvas_window.geometry("1200x800")
        self._canvas_window.configure(fg_color="#1a1a1a")
        
        self._canvas_window.protocol("WM_DELETE_WINDOW", self._dock_canvas)
        
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
        
        self.canvas_container.grid_remove()
        
        self._popup_container = ctk.CTkFrame(self._canvas_window, fg_color="#1e1e1e")
        self._popup_container.pack(fill="both", expand=True, padx=10, pady=10)
        self._popup_container.grid_rowconfigure(0, weight=1)
        self._popup_container.grid_columnconfigure(0, weight=1)
        
        self.orch_canvas.grid_forget()
        self.orch_canvas.configure(bg="#1e1e1e")
        
        self._original_canvas = self.orch_canvas
        self._popup_canvas = tk.Canvas(self._popup_container, bg="#1e1e1e", highlightthickness=0)
        self._popup_canvas.pack(fill="both", expand=True)
        
        self._popup_canvas.bind("<Button-1>", self._orch_on_canvas_click)
        self._popup_canvas.bind("<B1-Motion>", self._orch_on_canvas_drag)
        self._popup_canvas.bind("<ButtonRelease-1>", self._orch_on_canvas_release)
        self._popup_canvas.bind("<Double-Button-1>", self._orch_on_canvas_double_click)
        self._popup_canvas.bind("<ButtonPress-2>", self._orch_on_canvas_pan_start)
        self._popup_canvas.bind("<B2-Motion>", self._orch_on_canvas_pan_drag)
        self._popup_canvas.bind("<Control-ButtonPress-1>", self._orch_on_canvas_pan_start)
        self._popup_canvas.bind("<Control-B1-Motion>", self._orch_on_canvas_pan_drag)
        
        self._popup_canvas.bind("<Button-3>", self._orch_on_canvas_right_click)
        self._popup_canvas.bind("<Delete>", self._orch_delete_selected_node)
        self._popup_canvas.bind("<BackSpace>", self._orch_delete_selected_node)
        
        self.orch_canvas = self._popup_canvas
        
        popup_toolbar = ctk.CTkFrame(self._canvas_window, height=50, fg_color="#222")
        popup_toolbar.pack(fill="x", side="bottom", padx=10, pady=(0, 10))
        
        ctk.CTkButton(popup_toolbar, text="▶️ 运行全部", fg_color="#27ae60", width=100,
                      command=self._orch_run_all).pack(side="left", padx=5, pady=5)
        # Note: _orch_export_json and _orch_import_json are in Layer 4, not yet moved.
        # Ensure they are available or move them too. For now we assume they exist in main or will be moved soon.
        # Actually, let's just reference self._orch_export_json as it's still on self (mixed in or inherited).
        ctk.CTkButton(popup_toolbar, text="💾 保存", fg_color="#3498db", width=80,
                      command=self._orch_export_json).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(popup_toolbar, text="📂 加载", fg_color="#555", width=80,
                      command=self._orch_import_json).pack(side="left", padx=5, pady=5)
        
        ctk.CTkButton(popup_toolbar, text="⬅ 收回画布", fg_color="#e74c3c", width=100,
                      command=self._dock_canvas).pack(side="right", padx=5, pady=5)
        
        self.expand_btn.configure(text="⬅ 收回", fg_color="#e74c3c")
        self._orch_draw_grid()
    
    def _dock_canvas(self):
        """Move canvas back to main window"""
        if not hasattr(self, '_canvas_window') or not self._canvas_window:
            return
            
        if hasattr(self, '_canvas_placeholder') and self._canvas_placeholder:
            self._canvas_placeholder.destroy()
            self._canvas_placeholder = None
        
        if hasattr(self, '_original_canvas') and self._original_canvas:
            self.orch_canvas = self._original_canvas
            self.orch_canvas.grid(row=0, column=0, sticky="nsew")
        
        self.canvas_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))
        
        if self._canvas_window and self._canvas_window.winfo_exists():
            self._canvas_window.destroy()
        self._canvas_window = None
        self._popup_canvas = None
        self._original_canvas = None
        
        self.expand_btn.configure(text="⬜ 独立窗口", fg_color="#555")
        self._orch_draw_grid()

    def _orch_on_canvas_double_click(self, event) -> None:
        """画布双击事件 - 编辑节点名称"""
        if self.orch_selected_node:
            node = self.orch_nodes.get(self.orch_selected_node)
            if node and hasattr(self, 'orch_prop_name_entry'):
                self.orch_prop_name_entry.focus_set()
                self.orch_prop_name_entry.select_range(0, tk.END)

    def _orch_on_canvas_right_click(self, event) -> None:
        """Show context menu on right-click"""
        cx = self.orch_canvas.canvasx(event.x)
        cy = self.orch_canvas.canvasy(event.y)
        
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
            
        self._orch_select_node(clicked_node_id)
        self.orch_canvas.focus_set()
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
        
        menu = ctk.CTkToplevel()
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.geometry(f"+{x}+{y}")
        self._context_menu_window = menu
        
        menu.bind("<FocusOut>", lambda e: self._close_context_menu() if str(e.widget) == str(menu) else None)
        menu.after(50, menu.focus_set)
        
        frame = ctk.CTkFrame(menu, fg_color="#2b2b2b", border_width=1, border_color="#444444", corner_radius=8)
        frame.pack(fill="both", expand=True)
        
        lbl = ctk.CTkLabel(frame, text=f"  📌 {node.step_name}", anchor="w", font=("Segoe UI", 12, "bold"), text_color="#888")
        lbl.pack(fill="x", pady=(6, 4), padx=4)
        
        ctk.CTkFrame(frame, height=1, fg_color="#444").pack(fill="x", pady=2, padx=4)
        
        self._create_context_menu_item(frame, "  🧪  单点测试", lambda: self._orch_test_selected_node())
        
        bp_label = "  🔴  移除断点" if "[BREAKPOINT]" in node.context else "  🔵  设置断点"
        self._create_context_menu_item(frame, bp_label, lambda: self._orch_toggle_breakpoint())
        
        ctk.CTkFrame(frame, height=1, fg_color="#444").pack(fill="x", pady=2, padx=4)
        
        self._create_context_menu_item(frame, "  ✏️  修改名称", lambda: self._orch_rename_node_dialog(node_id))
        self._create_context_menu_item(frame, "  🔌  断开连接", lambda: self._orch_disconnect_node(node_id))
        
        ctk.CTkFrame(frame, height=1, fg_color="#444").pack(fill="x", pady=2, padx=4)
        
        self._create_context_menu_item(frame, "  🗑️  删除节点", lambda: self._orch_delete_node(node_id), text_color="#ff5555", hover_color="#4a1a1a")

    def _orch_rename_node_dialog(self, node_id: str) -> None:
        """Show dialog to rename a node"""
        if node_id not in self.orch_nodes:
            return
            
        node = self.orch_nodes[node_id]
        
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

    def _orch_save_node_properties(self) -> None:
        """保存节点属性"""
        if not self.orch_selected_node:
            messagebox.showwarning("提示", "请先选择一个节点")
            return

        node = self.orch_nodes.get(self.orch_selected_node)
        if not node:
            return

        # Ensure vars exist
        if not hasattr(self, 'orch_prop_name_var'): return

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
            self.orch_prop_x1_var.set(self.x1_var.get())
            self.orch_prop_y1_var.set(self.y1_var.get())
            self.orch_prop_x2_var.set(self.x2_var.get())
            self.orch_prop_y2_var.set(self.y2_var.get())

            param = self.gen_param_var.get().strip()
            if not param:
                param = self.ocr_target_text_var.get().strip()
            
            if param:
                self.orch_prop_params_var.set(param)
            
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
                        self._orch_mark_node_success(node.id)
                        self.root.after(1000, lambda: self._orch_draw_node(node))
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

        sorted_nodes = sorted(self.orch_nodes.values(), key=lambda n: (n.canvas_x, n.canvas_y))

        self.orch_connections.clear()
        for line_id in self.orch_connection_lines.values():
            self.orch_canvas.delete(line_id)
        self.orch_connection_lines.clear()

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
    # ==================== Layer 3 Supplement: Debug & Test ====================

    def _orch_test_selected_node(self) -> None:
        """V10.0: 测试选中的单个节点 - 使用第一行 Excel 数据"""
        if not self.orch_selected_node:
            messagebox.showwarning("提示", "请先选择一个节点")
            return
        
        if not self.device:
            messagebox.showwarning("提示", "请先连接设备")
            return
        
        node = self.orch_nodes.get(self.orch_selected_node)
        if not node:
            return
        
        # V10.1: Get first data row (skip header at index 0)
        row_data = {}
        if hasattr(self, 'materials_data') and len(self.materials_data) >= 2:
            row_data = self.materials_data[1].copy()
            self.log(f"[调试] 📊 使用第1行数据 (Excel第2行): {list(row_data.keys())}")
        elif hasattr(self, 'global_vars') and self.global_vars:
            row_data = self.global_vars.copy()
        
        self.log(f"[编排] 🧪 单点测试: {node.step_name}")
        
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
                global_vars=getattr(self, 'global_vars', {})
            )
            
            self._orch_highlight_executing_node(node.id)
            self.root.update()
            
            # V10.0: Pass row_data to execute_step
            success = runner.execute_step(step_data, row_data)
            
            # V10.0: Refresh Variable Watcher after execution
            if hasattr(self, '_refresh_variable_watcher'):
                self.workflow_runner = runner  # Store runner for variable watcher
                self._refresh_variable_watcher()
            
            if success:
                self._orch_mark_node_success(node.id)
                self.log(f"[编排] ✅ 单点测试成功: {node.step_name}")
                messagebox.showinfo("测试成功", f"节点 {node.step_name} 执行成功！")
            else:
                self._orch_mark_node_failed(node.id)
                self.log(f"[编排] ❌ 单点测试失败: {node.step_name}")
                messagebox.showerror("测试失败", f"节点 {node.step_name} 执行失败")
            
            self.root.after(2000, lambda: self._orch_draw_node(node))
            
        except ImportError:
            messagebox.showerror("错误", "未找到 workflow_runner.py")
        except Exception as e:
            self.log(f"[编排] ❌ 单点测试失败: {e}")
            messagebox.showerror("测试失败", str(e))

    def _orch_toggle_breakpoint(self) -> None:
        """切换选中节点的断点状态"""
        if not self.orch_selected_node:
            messagebox.showwarning("提示", "请先选择一个节点")
            return
        
        node = self.orch_nodes.get(self.orch_selected_node)
        if not node:
            return
        
        if "[BREAKPOINT]" in node.context:
            node.context = node.context.replace("[BREAKPOINT]", "").strip()
            self.log(f"[编排] 🔵 移除断点: {node.step_name}")
        else:
            node.context = f"[BREAKPOINT] {node.context}".strip()
            self.log(f"[编排] 🔴 设置断点: {node.step_name}")
        
        self._orch_draw_node(node)
        
        # V7.5 Fix: If this node is currently selected, update the Inspector UI to reflect the change
        # otherwise typing in the inspector will overwrite the [BREAKPOINT] tag
        if self.orch_selected_node == node.id:
             if hasattr(self, 'gen_context_text'):
                self.gen_context_text.delete("1.0", tk.END)
                self.gen_context_text.insert("1.0", node.context)
             elif hasattr(self, 'gen_context_var'):
                self.gen_context_var.set(node.context)
    def _orch_on_canvas_pan_start(self, event):
        """画布拖拽开始（中键或 Ctrl+左键）"""
        self.orch_canvas.scan_mark(event.x, event.y)

    def _orch_on_canvas_pan_drag(self, event):
        """画布拖拽中"""
        self.orch_canvas.scan_dragto(event.x, event.y, gain=1)
        self.orch_connection_lines.clear()
        self._orch_deselect_node()

    def _orch_run_with_breakpoints(self) -> None:
        """带断点调试运行 - 在断点处暂停"""
        if not self.orch_nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        if not self.device:
            messagebox.showwarning("提示", "请先连接设备")
            return
        
        # Note: _orch_topological_sort is in Layer 4 (Core Logic), assuming defined in Mixin or Main. 
        # Actually it is NOT in Mixin yet! It is in main file.
        # This will fail if we remove it from main before moving it.
        # But we are dealing with Layer 3 now. Layer 4 is next.
        # Ideally we should move Layer 4 methods too, or ensure self._orch_topological_sort calls the one in Main (via inheritance).
        # Since specific method resolution order (MRO) applies, calling self.method() will find it in Main if not in Mixin.
        # So it is safe to act as if it's there.
        
        # However, we should be careful about _orch_topological_sort dependency.
        
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
                self.log(f"[DEBUG] Node {i+1}: {node.step_name}, Context: '{node.context}'")
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
                
                # V10.0: Get first row of materials for variable injection
                row_data = {}
                if hasattr(self, 'materials_data') and self.materials_data:
                    row_data = self.materials_data[0].copy()
                
                success = runner.execute_step(step_data, row_data)
                
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

    # ==================== Layer 4: Logic & I/O ====================

    def _orch_refresh_listbox(self) -> None:
        """刷新右侧节点列表"""
        if not hasattr(self, 'gen_queue_listbox'):
            return
            
        self.gen_queue_listbox.delete(0, tk.END)
        
        try:
            nodes = list(self.orch_nodes.values())
            # 尝试提取 Step 后面的数字排序
            import re
            def sort_key(n):
                match = re.search(r'(\d+)', n.step_name)
                return int(match.group(1)) if match else 999999
            nodes.sort(key=sort_key)
        except:
            nodes.sort(key=lambda n: n.step_name)
        
        # Cache the sorted node IDs for listbox selection mapping
        self._orch_listbox_cache = [n.id for n in nodes]
        
        for node in nodes:
            display = f"{node.step_name}: {node.action_type}"
            self.gen_queue_listbox.insert(tk.END, display)

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

    def _orch_add_node_from_palette(self, action_type: str) -> None:
        """从节点库添加节点到画布中心"""
        base_x = 200 + len(self.orch_nodes) * 30
        base_y = 100 + (len(self.orch_nodes) % 5) * 80

        import uuid
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
        self.log(f"[编排] 添加节点: {step_name} ({action_type})")
        self._orch_refresh_listbox()

    def _add_node_to_canvas(self, action_type: str) -> None:
        """V6.0: 从节点库添加节点到画布 (统一接口)"""
        self._orch_add_node_from_palette(action_type)

    def _orch_export_json(self) -> None:
        """导出为 JSON 文件"""
        if not self.orch_nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

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

        from tkinter import filedialog
        filepath = filedialog.asksaveasfilename(
            title="导出流程",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile="workflow.json",
        )

        if not filepath:
            return

        try:
            import json
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            self.log(f"[编排] 已导出: {filepath}")
            messagebox.showinfo("导出成功", f"已导出 {len(export_data)} 个步骤到:\n{filepath}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _orch_import_json(self) -> None:
        """从 JSON 文件导入"""
        from tkinter import filedialog
        filepath = filedialog.askopenfilename(
            title="导入流程",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )

        if not filepath:
            return

        try:
            import json
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValueError("JSON 格式错误：根元素必须是数组")

            self._orch_clear_canvas_silent()

            import uuid
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

    def _orch_topological_sort(self) -> List[WorkflowNode]:
        """拓扑排序获取节点执行顺序"""
        if not self.orch_connections:
            return sorted(self.orch_nodes.values(), key=lambda n: (n.canvas_x, n.canvas_y))

        in_degree = {node_id: 0 for node_id in self.orch_nodes}
        adj = {node_id: [] for node_id in self.orch_nodes}

        for from_id, to_id in self.orch_connections:
            if from_id in adj and to_id in in_degree:
                adj[from_id].append(to_id)
                in_degree[to_id] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            queue.sort(key=lambda nid: (self.orch_nodes[nid].canvas_x, self.orch_nodes[nid].canvas_y))
            node_id = queue.pop(0)
            result.append(self.orch_nodes[node_id])

            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        for node in self.orch_nodes.values():
            if node not in result:
                result.append(node)
        return result

    def _orch_run_all(self) -> None:
        """V6.0: 运行全部节点 (alias) - 使用第一行数据"""
        self._orch_run_workflow()

    def _orch_test_first_row(self) -> None:
        """V10.0: 🧪 测试第一行数据 - 用于快速验证变量替换是否正常"""
        if not self.orch_nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        if not self.device:
            messagebox.showwarning("提示", "请先连接设备")
            return
        
        # Check if materials_data exists and has data rows (not just header)
        if not hasattr(self, 'materials_data') or len(self.materials_data) < 2:
            result = messagebox.askyesno(
                "提示", 
                "Excel 中没有数据行（仅有表头）。\n\n"
                "是否继续使用全局变量测试？\n"
                "(建议先点击📂按钮加载包含数据的 Excel)"
            )
            if not result:
                return
        
        row_data = {}
        if hasattr(self, 'materials_data') and len(self.materials_data) >= 2:
            # V10.1: Use index 1 to skip header row (index 0)
            row_data = self.materials_data[1].copy()
            self.log(f"[测试] 📊 使用第一行数据 (Excel第2行): {row_data}")
        elif hasattr(self, 'global_vars'):
            row_data = self.global_vars.copy()
            self.log(f"[测试] 🌐 使用全局变量: {row_data}")
        
        # Run workflow with this single row
        self.log("[测试] 🧪 开始第一行数据测试...")
        self._orch_run_workflow_with_data(row_data)

    def _orch_run_batch_all(self) -> None:
        """V10.0: 📊 批量执行 - 遍历所有 Excel 行数据"""
        if not self.orch_nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        if not self.device:
            messagebox.showwarning("提示", "请先连接设备")
            return
        
        # Check materials_data has data rows (not just header)
        if not hasattr(self, 'materials_data') or len(self.materials_data) < 2:
            messagebox.showwarning(
                "无数据", 
                "Excel 中没有数据行！\n\n"
                "请确保 Excel 至少有 2 行（表头 + 数据）。\n"
                "点击节点编辑器左侧的📂按钮选择 Excel 文件。"
            )
            return
        
        # V10.1: Skip header row (index 0), use [1:]
        data_rows = self.materials_data[1:]
        total_rows = len(data_rows)
        
        # Confirm before batch execution
        if not messagebox.askyesno(
            "确认批量执行",
            f"将对 {total_rows} 行数据执行工作流。\n\n"
            f"预览第一行: {list(data_rows[0].items())[:3]}...\n\n"
            "确定继续？"
        ):
            return
        
        self.log(f"[批量] 🚀 开始批量执行 {total_rows} 行数据...")
        
        success_rows = 0
        failed_rows = 0
        
        # V10.1: Iterate over data_rows (skipped header)
        for idx, row_data in enumerate(data_rows, start=1):
            self.log(f"[批量] ━━━ 第 {idx}/{total_rows} 行 (Excel第{idx+1}行) ━━━")
            
            if hasattr(self, 'orch_hint_label'):
                self.orch_hint_label.configure(text=f"批量: {idx}/{total_rows}")
            self.root.update()
            
            try:
                success = self._orch_run_workflow_with_data(row_data, silent=True)
                if success:
                    success_rows += 1
                    self.log(f"[批量] ✅ 第 {idx} 行完成")
                else:
                    failed_rows += 1
                    self.log(f"[批量] ❌ 第 {idx} 行失败")
                    
                    # Ask whether to continue on failure
                    if not messagebox.askyesno(
                        "行执行失败",
                        f"第 {idx} 行执行失败。\n\n是否继续执行剩余行？"
                    ):
                        break
            except Exception as e:
                failed_rows += 1
                self.log(f"[批量] ❌ 第 {idx} 行异常: {e}")
                break
        
        self.log(f"[批量] 🏁 批量执行完成: {success_rows} 成功, {failed_rows} 失败")
        messagebox.showinfo(
            "批量执行完成",
            f"执行结果:\n\n"
            f"✅ 成功: {success_rows} 行\n"
            f"❌ 失败: {failed_rows} 行"
        )

    def _orch_run_workflow_with_data(self, row_data: dict, silent: bool = False) -> bool:
        """V10.0: 使用指定行数据执行工作流
        
        Args:
            row_data: Excel 行数据字典 {'A': 'value', 'B': 'value', ...}
            silent: 是否静默模式（不弹窗）
        
        Returns:
            bool: 执行成功返回 True
        """
        ordered_nodes = self._orch_topological_sort()
        total_steps = len(ordered_nodes)
        
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
                "_node_id": node.id,
            })

        try:
            from workflow_runner import WorkflowRunner

            runner = WorkflowRunner(
                self.device,
                phone_width=self.phone_width,
                phone_height=self.phone_height,
                global_vars=getattr(self, 'global_vars', {})
            )
            
            # Store runner reference for variable watcher
            self.workflow_runner = runner

            if not silent:
                self.log(f"[执行] 🚀 开始执行 {total_steps} 个步骤...")
            
            all_success = True
            
            for i, step in enumerate(export_data):
                node_id = step.pop("_node_id")
                step_name = step.get("step_name", f"Step {step['step_id']}")

                self._orch_highlight_executing_node(node_id)
                if hasattr(self, 'orch_hint_label'):
                    self.orch_hint_label.configure(text=f"执行中: {i+1}/{total_steps}")
                self.root.update()

                success = runner.execute_step(step, row_data)

                if success:
                    self._orch_mark_node_success(node_id)
                else:
                    self._orch_mark_node_failed(node_id)
                    is_optional = step.get("is_optional", False)
                    
                    if not is_optional:
                        if not silent:
                            self.log(f"[执行] ❌ 步骤失败: {step_name}")
                        all_success = False
                        break
                
                self.root.update()
            
            # Refresh variable watcher
            if hasattr(self, '_refresh_variable_watcher'):
                self._refresh_variable_watcher()

            self.orch_running_node = None
            self.root.after(1000, self._orch_draw_all_nodes)
            
            return all_success

        except Exception as e:
            self.log(f"[执行] ❌ 执行失败: {e}")
            if not silent:
                messagebox.showerror("执行失败", str(e))
            return False

    def _orch_toggle_pause(self, event=None) -> None:
        """V8.0: Toggle Global Pause State (F8)"""
        current_state = getattr(self, "orch_is_paused", False)
        self.orch_is_paused = not current_state
        
        state_str = "已暂停 ⏸️" if self.orch_is_paused else "继续运行 ▶️"
        color = "#e74c3c" if self.orch_is_paused else "#2ecc71"
        
        self.log(f"[全局] {state_str}")
        if hasattr(self, 'orch_hint_label'):
             self.orch_hint_label.configure(text=state_str, text_color=color)

    def _orch_run_workflow(self) -> None:
        """运行当前编排的全部工作流节点"""
        if not self.orch_nodes:
            messagebox.showwarning("提示", "画布上没有节点")
            return

        if not self.device:
            messagebox.showwarning("提示", "请先连接设备")
            return

        ordered_nodes = self._orch_topological_sort()
        total_steps = len(ordered_nodes)
        
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
                "_node_id": node.id,
            })

        try:
            from workflow_runner import WorkflowRunner

            runner = WorkflowRunner(
                self.device,
                phone_width=self.phone_width,
                phone_height=self.phone_height,
                global_vars=getattr(self, 'global_vars', {}) # V9.0: Global Vars
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

                # V8.0: Check Global Pause
                while getattr(self, "orch_is_paused", False):
                    self.log(f"[编排] ⏸️ 流程已暂停 (按 F8 继续)...")
                    if hasattr(self, 'orch_hint_label'):
                        self.orch_hint_label.configure(text=f"⏸️ 已暂停: {step_name}")
                    self.root.update()
                    import time
                    time.sleep(0.5)
                    # Check if user stopped completely
                    if not getattr(self, "orch_running_node", None):
                        self.log("[编排] ⏹️ 流程已终止")
                        return

                self._orch_highlight_executing_node(node_id)
                if hasattr(self, 'orch_hint_label'):
                    self.orch_hint_label.configure(text=f"执行中: {i+1}/{total_steps} - {step_name}")
                self.root.update()

                self.log(f"[编排] ▶️ [{i+1}/{total_steps}] {step_name} - {action_type}")
                
                 # Check for new Log Console from V8.0
                if hasattr(self, 'orch_log_text'):
                    try:
                         import time
                         ts = time.strftime("%H:%M:%S")
                         # V8.1: Enhanced Log Format
                         param_info = f"Params: {step.get('params', 'None')}"
                         coords_info = f"Coords: {step.get('coords', {})}"
                         
                         self.orch_log_text.insert("end", f"[{ts}] ▶️ {step_name}\n")
                         self.orch_log_text.insert("end", f"      Type: {action_type} | {param_info}\n")
                         self.orch_log_text.insert("end", f"      {coords_info}\n")
                         self.orch_log_text.see("end")
                    except: pass

                # V10.0: Get first row of materials data for variable injection
                row_data = {}
                if hasattr(self, 'materials_data') and self.materials_data:
                    row_data = self.materials_data[0].copy()
                
                success = runner.execute_step(step, row_data)

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
            
            # V10.0: Store runner for variable watcher
            self.workflow_runner = runner
            if hasattr(self, '_refresh_variable_watcher'):
                self._refresh_variable_watcher()

            self.orch_running_node = None
            self.root.after(2000, self._orch_draw_all_nodes)

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

    def _orch_test_node_by_id(self, node_id: str) -> None:
        """通过 ID 测试节点"""
        self.orch_selected_node = node_id
        self._orch_test_selected_node()
    
    def _orch_toggle_breakpoint_by_id(self, node_id: str) -> None:
        """通过 ID 切换断点"""
        self.orch_selected_node = node_id
        self._orch_toggle_breakpoint()
    
    def _orch_delete_node_by_id(self, node_id: str) -> None:
        """通过 ID 删除节点"""
        self.orch_selected_node = node_id
        self._orch_draw_all_nodes()
        self._orch_delete_selected_node()

    def _orch_disconnect_node(self, node_id: str) -> None:
        """断开节点的所有连接"""
        self.orch_selected_node = node_id
        self._orch_disconnect_selected_node_all()

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
            x1 = float(coords.get("x1", 0))
            y1 = float(coords.get("y1", 0))
            x2 = float(coords.get("x2", 0))
            y2 = float(coords.get("y2", 0))
            
            if x1 == 0 and x2 == 0:
                 self.log("[测试] ⚠️ 坐标无效 (0,0)")
                 return

            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            
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
        if not hasattr(self, 'ext_manager'): 
             # Fallback if ext_manager is not init
             from extension_manager import ExtensionManager
             self.ext_manager = ExtensionManager()

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
