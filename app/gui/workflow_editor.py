import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import customtkinter as ctk
import uuid
import json
import logging 
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from PIL import Image, ImageTk

from app.core.context import SharedContext
from app.core.models import WorkflowNode, RoiPct
from app.core.constants import NODE_STYLES, ACTION_CATEGORIES, NODE_PARAM_SHORTCUTS
from app.core.workflow_runner import WorkflowRunner
from app.gui.node_search_window import NodeSearchWindow
import threading



class WorkflowEditorFrame(ctk.CTkFrame):
    def __init__(self, master, ctx: SharedContext, **kwargs):
        super().__init__(master, **kwargs)
        self.ctx = ctx
        self.logger = logging.getLogger(__name__)

        # State
        self.orch_nodes: Dict[str, WorkflowNode] = {}
        self.orch_connections: List[Tuple[str, str]] = [] 
        self.orch_selected_node: Optional[str] = None
        self.orch_connection_lines: Dict[Tuple[str, str], List[int]] = {}
        self.orch_node_canvas_items: Dict[str, List[int]] = {}
        
        # Interaction State
        self.orch_drag_node_id: Optional[str] = None
        self.orch_drag_offset: Tuple[int, int] = (0, 0)
        self.orch_connecting_from: Optional[str] = None
        self.orch_temp_line_id: Optional[int] = None
        self._is_updating_ui = False
        
        # Pop-out state
        self._canvas_window: Optional[ctk.CTkToplevel] = None
        self._canvas_window: Optional[ctk.CTkToplevel] = None
        self._original_canvas: Optional[tk.Canvas] = None
        self.orch_panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0
        self.orch_wire_mode = False # Click-Click connection status
        
        # Variables
        self.prop_name_var = ctk.StringVar()
        self.prop_action_var = ctk.StringVar()
        self.prop_params_var = ctk.StringVar()
        self.prop_context_var = ctk.StringVar()
        self.prop_x1_var = ctk.StringVar(value="0")
        self.prop_y1_var = ctk.StringVar(value="0")
        self.prop_x2_var = ctk.StringVar(value="0")
        self.prop_y2_var = ctk.StringVar(value="0")
        
        self.prop_name_var.trace_add("write", self._on_inspector_change)
        self.prop_params_var.trace_add("write", self._on_inspector_change)
        self.prop_x1_var.trace_add("write", self._on_inspector_change)
        self.prop_y1_var.trace_add("write", self._on_inspector_change)
        self.prop_x2_var.trace_add("write", self._on_inspector_change)
        self.prop_y2_var.trace_add("write", self._on_inspector_change)

        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=2)   # Left: Inspector
        self.grid_columnconfigure(1, weight=5)   # Center: Canvas
        self.grid_columnconfigure(2, weight=2)   # Right: Outliner & Controls
        self.grid_columnconfigure(3, weight=3)   # Far Right: Screenshot

        # === Column 0: Inspector ===
        self.left_panel = ctk.CTkFrame(self)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._build_inspector_panel()
        
        # === Column 1: Main Canvas ===
        self.center_panel = ctk.CTkFrame(self)
        self.center_panel.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self.center_panel.grid_rowconfigure(0, weight=1)
        self.center_panel.grid_columnconfigure(0, weight=1)
        
        self.canvas_container = ctk.CTkFrame(self.center_panel)
        self.canvas_container.grid(row=0, column=0, sticky="nsew")
        self.canvas_container.grid_rowconfigure(0, weight=1)
        self.canvas_container.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.canvas_container, bg="#1e1e1e", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbars
        h_scroll = tk.Scrollbar(self.canvas_container, orient="horizontal", command=self.canvas.xview)
        v_scroll = tk.Scrollbar(self.canvas_container, orient="vertical", command=self.canvas.yview)
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        # Toolbar (Top of Canvas) - Modernized
        toolbar = ctk.CTkFrame(self.center_panel, height=50, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 10), padx=10)
        
        self.expand_btn = ctk.CTkButton(toolbar, text="⬜ 独立窗口", width=100, height=36,
                                      fg_color="#555", hover_color="#666", 
                                      command=self._toggle_canvas_popout)
        self.expand_btn.pack(side="left", padx=5)

        # Execution Controls
        ctk.CTkButton(toolbar, text="▶ 全部运行", width=100, height=36,
                      fg_color="#2ecc71", hover_color="#27ae60",
                      command=self._orch_run_all).pack(side="left", padx=5)
                      
        ctk.CTkButton(toolbar, text="🧪 单点测试", width=100, height=36,
                      fg_color="#3498db", hover_color="#2980b9",
                      command=self._orch_test_selected_node).pack(side="left", padx=5)
        
        ctk.CTkButton(toolbar, text="🧹 清空", width=80, height=36,
                      fg_color="#e74c3c", hover_color="#c0392b",
                      command=self._clear_canvas).pack(side="right", padx=5)
                      
        ctk.CTkButton(toolbar, text="💾 保存", width=80, height=36,
                      fg_color="#2c3e50", hover_color="#34495e",
                      command=self._export_json).pack(side="right", padx=5)
                      
        ctk.CTkButton(toolbar, text="📂 加载", width=80, height=36,
                      fg_color="#2c3e50", hover_color="#34495e",
                      command=self._import_json).pack(side="right", padx=5)

        self.status_label = ctk.CTkLabel(toolbar, text="就绪", text_color="#aaa")
        self.status_label.pack(side="right", padx=20)

        
        ctk.CTkButton(toolbar, text="🗑️ 清空", width=60, fg_color="red", command=self._clear_canvas).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="🔗 自动连线", width=80, command=self._auto_connect).pack(side="right", padx=5)
        
        # Canvas Bindings
        self._bind_canvas_events()
        self.canvas.bind("<Configure>", lambda e: self._draw_grid())

        # === Column 2: Outliner & Controls ===
        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.grid(row=0, column=2, sticky="nsew", padx=2, pady=2)
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.right_panel, text="📑 节点大纲", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=5)
        
        # Treeview Style - Dark Mode
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", 
                        background="#2b2b2b", 
                        foreground="#ffffff", 
                        fieldbackground="#2b2b2b", 
                        rowheight=25,
                        borderwidth=0)
        style.configure("Treeview.Heading", 
                        background="#3a3a3a", 
                        foreground="#ffffff", 
                        relief="flat")
        style.map("Treeview", background=[("selected", "#3498db")])

        self.tree = ttk.Treeview(self.right_panel, columns=("desc",), show="tree", selectmode="browse")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        ysb = ttk.Scrollbar(self.right_panel, orient="vertical", command=self.tree.yview)
        ysb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=ysb.set)
        
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        
        ctk.CTkButton(self.right_panel, text="💾 导出 JSON", command=self._export_json).grid(row=2, column=0, pady=5, sticky="ew", padx=5)
        ctk.CTkButton(self.right_panel, text="📂 导入 JSON", command=self._import_json).grid(row=3, column=0, pady=(0,5), sticky="ew", padx=5)

        # === Column 3: Screenshot Panel ===
        self.screenshot_panel = ctk.CTkFrame(self)
        self.screenshot_panel.grid(row=0, column=3, sticky="nsew", padx=(2, 5), pady=2)
        self.screenshot_panel.grid_rowconfigure(1, weight=1)
        self.screenshot_panel.grid_columnconfigure(0, weight=1)
        
        top_bar_scr = ctk.CTkFrame(self.screenshot_panel, fg_color="transparent")
        top_bar_scr.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkLabel(top_bar_scr, text="📱 手机界面", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(top_bar_scr, text="📷 刷新", width=60, fg_color="#3498db", command=self.refresh_screenshot).pack(side="right")
        
        self.gen_canvas = tk.Canvas(self.screenshot_panel, bg="#1f1f1f", highlightthickness=0)
        self.gen_canvas.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Placeholder on screenshot canvas
        self.gen_canvas.create_text(
            20, 50, text="请点击刷新\n获取截图", fill="#999", anchor="nw", font=("Arial", 12)
        )
        
    def _build_inspector_panel(self):
        p = self.left_panel
        p.grid_rowconfigure(2, weight=1) 
        p.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(p, text="🔧 属性配置", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=5)
        
        # Action Selector
        act_frame = ctk.CTkFrame(p)
        act_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkLabel(act_frame, text="添加节点:").pack(side="left", padx=5)
        
        self.action_combo = ctk.CTkOptionMenu(
            act_frame, 
            values=self._get_flattened_actions(),
            command=self._on_add_node_from_combo
        )
        self.action_combo.pack(side="left", fill="x", expand=True, padx=5)
        
        # Properties
        self.prop_scroll = ctk.CTkScrollableFrame(p)
        self.prop_scroll.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        self.prop_scroll.grid_columnconfigure(1, weight=1)
        
        self._add_prop_entry(self.prop_scroll, 0, "步骤名称", self.prop_name_var)
        self._add_prop_entry(self.prop_scroll, 1, "动作类型", self.prop_action_var, state="readonly")
        ctk.CTkLabel(self.prop_scroll, text="参数配置:").grid(row=2, column=0, sticky="w", padx=5, pady=10)
        self._add_prop_entry(self.prop_scroll, 3, "参数值", self.prop_params_var)
        
        self.shortcut_frame = ctk.CTkFrame(self.prop_scroll)
        self.shortcut_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=2, pady=5)
        
        coord_grp = ctk.CTkFrame(self.prop_scroll)
        coord_grp.grid(row=5, column=0, columnspan=2, sticky="ew", padx=2, pady=10)
        ctk.CTkLabel(coord_grp, text="坐标区域 (0.0-1.0)").grid(row=0, column=0, columnspan=4)
        self._add_prop_entry(coord_grp, 1, "X1", self.prop_x1_var, col_idx=0)
        self._add_prop_entry(coord_grp, 1, "Y1", self.prop_y1_var, col_idx=2)
        self._add_prop_entry(coord_grp, 2, "X2", self.prop_x2_var, col_idx=0)
        self._add_prop_entry(coord_grp, 2, "Y2", self.prop_y2_var, col_idx=2)
        
    def _add_prop_entry(self, parent, row, label, var, col_idx=0, **kwargs):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=col_idx, sticky="w", padx=5)
        ctk.CTkEntry(parent, textvariable=var, **kwargs).grid(row=row, column=col_idx+1, sticky="ew", padx=5, pady=2)
        
    def _get_flattened_actions(self) -> List[str]:
        actions = []
        for cat, acts in ACTION_CATEGORIES.items():
            for name in acts.keys(): actions.append(name)
        return sorted(actions)

    def _bind_canvas_events(self):
        self.canvas.bind("<Button-1>", self._orch_on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._orch_on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._orch_on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self._orch_on_canvas_double_click)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click) # Windows Right and Mac Right?
        self.canvas.bind("<ButtonPress-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_drag)
        # Mouse Wheel
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Button-4>", self._on_mouse_wheel) # Linux
        self.canvas.bind("<Button-5>", self._on_mouse_wheel) # Linux
        # Motion for Click-Click wire
        self.canvas.bind("<Motion>", self._orch_on_canvas_drag)

        # Robust Port Bindings
        self.canvas.tag_bind("output_port", "<Button-1>", self._on_port_start)
        self.canvas.tag_bind("input_port", "<Button-1>", self._on_port_end)
        self.canvas.tag_bind("output_port", "<Enter>", lambda e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind("output_port", "<Leave>", lambda e: self.canvas.configure(cursor=""))
        self.canvas.tag_bind("input_port", "<Enter>", lambda e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind("input_port", "<Leave>", lambda e: self.canvas.configure(cursor=""))

        # Robust Node Bindings
        self.canvas.tag_bind("node", "<Button-1>", self._on_node_press)
        self.canvas.tag_bind("node", "<B1-Motion>", self._on_node_drag)
        self.canvas.tag_bind("node", "<ButtonRelease-1>", self._on_node_release)
        self.canvas.tag_bind("node", "<Enter>", lambda e: self.canvas.configure(cursor="fleur")) 
        self.canvas.tag_bind("node", "<Leave>", lambda e: self.canvas.configure(cursor=""))

    def _on_node_press(self, event):
        try:
            # Find which node was clicked
            tags = self.canvas.gettags("current")
            nid = None
            for tag in tags:
                if tag.startswith("node_"):
                    nid = tag.split("_")[1]
                    break
            
            if nid:
                self._select_node(nid)
                self.orch_drag_node_id = nid
                # Calculate offset
                click_x = self.canvas.canvasx(event.x)
                click_y = self.canvas.canvasy(event.y)
                node = self.orch_nodes[nid]
                self.orch_drag_offset = (click_x - node.canvas_x, click_y - node.canvas_y)
                
        except Exception as e:
            self.logger.error(f"Node press error: {e}")

    def _on_node_drag(self, event):
        try:
            if not self.orch_drag_node_id: return
            
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            
            node = self.orch_nodes[self.orch_drag_node_id]
            node.canvas_x = int(cx - self.orch_drag_offset[0])
            node.canvas_y = int(cy - self.orch_drag_offset[1])
            self._draw_node(node)
            self._update_connections()
        except: pass

    def _on_node_release(self, event):
        self.orch_drag_node_id = None
        self._update_scrollregion() # Ensure scrollable area expands

    def _on_port_start(self, event):
        self.canvas.tag_bind("output_port", "<Button-1>", self._on_port_start)
        self.canvas.tag_bind("input_port", "<Button-1>", self._on_port_end)
        self.canvas.tag_bind("output_port", "<Enter>", lambda e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind("output_port", "<Leave>", lambda e: self.canvas.configure(cursor=""))
        self.canvas.tag_bind("input_port", "<Enter>", lambda e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind("input_port", "<Leave>", lambda e: self.canvas.configure(cursor=""))

    def _on_port_start(self, event):
        try:
            tags = self.canvas.gettags("current")
            for tag in tags:
                if tag.startswith("output_"):
                    self.orch_connecting_from = tag.split("_")[1]
                    # Don't return, let Drag handle motion
        except: pass

    def _on_port_end(self, event):
        try:
            if not self.orch_connecting_from: return
            tags = self.canvas.gettags("current")
            for tag in tags:
                 if tag.startswith("input_"):
                    target_id = tag.split("_")[1]
                    if target_id != self.orch_connecting_from:
                        self.orch_connections.append((self.orch_connecting_from, target_id))
                        self._draw_connection(self.orch_connecting_from, target_id)
            
            # Reset state
            if self.orch_temp_line_id: self.canvas.delete(self.orch_temp_line_id)
            self.orch_temp_line_id = None
            self.orch_connecting_from = None
            self.orch_wire_mode = False
        except: pass

    # === Interaction ===
    def _on_add_node_from_combo(self, action_type):
        self._add_node_center(action_type)
        
    def _update_scrollregion(self):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except: pass

    def _add_node_center(self, action_type):
        # Use smart placement instead of naive
        x, y = self._find_smart_position(200, 100)
        node = WorkflowNode(id=str(uuid.uuid4())[:8], action_type=action_type, step_name=f"Step {len(self.orch_nodes)+1}", canvas_x=x, canvas_y=y)
        self.orch_nodes[node.id] = node
        self._draw_node(node)
        self._select_node(node.id)
        self._update_tree()
        self._update_scrollregion()

    def _find_smart_position(self, start_x, start_y):
        # Spiraling search for empty spot
        x, y = start_x, start_y
        step = 0
        while True:
            # Check collision with existing nodes
            collision = False
            rect = (x, y, x+160, y+70)
            for n in self.orch_nodes.values():
                # Simple AABB collision
                nx, ny = n.canvas_x, n.canvas_y
                if (x < nx + 170 and x + 170 > nx and
                    y < ny + 80 and y + 80 > ny):
                    collision = True
                    break
            
            if not collision:
                return x, y
            
            # Spiral / Stagger logic
            step += 1
            # Simple staggered columns
            x = start_x + (step % 5) * 40
            y = start_y + (step * 60)
            if step > 100: return x, y # Give up

    def _select_node(self, node_id):
        self._is_updating_ui = True
        self.orch_selected_node = node_id
        node = self.orch_nodes[node_id]
        self.prop_name_var.set(node.step_name)
        self.prop_action_var.set(node.action_type)
        self.prop_params_var.set(node.params)
        self.prop_context_var.set(node.context)
        c = node.coords
        self.prop_x1_var.set(str(c.get("x1", 0)))
        self.prop_y1_var.set(str(c.get("y1", 0)))
        self.prop_x2_var.set(str(c.get("x2", 0)))
        self.prop_y2_var.set(str(c.get("y2", 0)))
        self._update_param_shortcuts(node.action_type)
        for nid, n in self.orch_nodes.items(): self._draw_node(n)
        self._is_updating_ui = False
        if self.tree.exists(node_id):
            self.tree.selection_set(node_id)
            self.tree.see(node_id)

    def _update_param_shortcuts(self, action_type):
        for w in self.shortcut_frame.winfo_children(): w.destroy()
        
        shortcuts = NODE_PARAM_SHORTCUTS.get(action_type, [])
        if not shortcuts: return

        # Header
        ctk.CTkLabel(self.shortcut_frame, text="💡 推荐参数:", font=("Arial", 12, "bold"), text_color="#f1c40f").pack(anchor="w", pady=(5, 2))
        
        # Grid layout for buttons
        grid_frame = ctk.CTkFrame(self.shortcut_frame, fg_color="transparent")
        grid_frame.pack(fill="x")
        
        for i, (val, lbl) in enumerate(shortcuts):
            btn = ctk.CTkButton(
                grid_frame, 
                text=f"{lbl} ({val})", 
                command=lambda v=val: self.prop_params_var.set(v), 
                height=28, 
                fg_color="#444",
                hover_color="#555",
                font=("Arial", 11)
            )
            btn.grid(row=i//2, column=i%2, sticky="ew", padx=2, pady=2)
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)


    def _on_inspector_change(self, *args):
        if self._is_updating_ui or not self.orch_selected_node: return
        node = self.orch_nodes[self.orch_selected_node]
        node.step_name = self.prop_name_var.get()
        node.params = self.prop_params_var.get()
        try:
             node.coords = {"x1": float(self.prop_x1_var.get()), "y1": float(self.prop_y1_var.get()), "x2": float(self.prop_x2_var.get()), "y2": float(self.prop_y2_var.get())}
        except: pass
        self._draw_node(node)
        if self.tree.exists(node.id): self.tree.item(node.id, text=f"{node.step_name} ({node.action_type})")

    # === Drawing ===
    def _draw_node(self, node: WorkflowNode):
        style = NODE_STYLES.get(node.action_type, {"color": "#666", "label": node.action_type})
        x, y = node.canvas_x, node.canvas_y
        w, h = 160, 70
        if node.id in self.orch_node_canvas_items:
            for i in self.orch_node_canvas_items[node.id]: self.canvas.delete(i)
        items = []
        outline = "yellow" if self.orch_selected_node == node.id else "#333"
        bg = style.get("color", "#555")
        
        # Tags are crucial for dragging! Apply to all items
        tags_ = ("node", f"node_{node.id}")
        
        rect = self.canvas.create_rectangle(x, y, x+w, y+h, fill=bg, outline=outline, width=2, tags=tags_)
        items.append(rect)
        
        txt = self.canvas.create_text(x+10, y+15, text=node.step_name, anchor="w", fill="white", font=("Arial", 10, "bold"), tags=tags_)
        items.append(txt)
        
        lbl = self.canvas.create_text(x+10, y+35, text=style.get("label", "?"), anchor="w", fill="#ddd", font=("Arial", 9), tags=tags_)
        items.append(lbl)
        
        in_p = self.canvas.create_oval(x-5, y+30, x+5, y+40, fill="#fff", tags=("input_port", f"input_{node.id}"))
        out_p = self.canvas.create_oval(x+w-5, y+30, x+w+5, y+40, fill="#fff", tags=("output_port", f"output_{node.id}"))
        items.extend([in_p, out_p])
        self.orch_node_canvas_items[node.id] = items

    def _draw_grid(self):
        self.canvas.delete("grid")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        for x in range(0, w, 40): self.canvas.create_line(x, 0, x, h, fill="#2a2a2a", tags="grid")
        for y in range(0, h, 40): self.canvas.create_line(0, y, w, y, fill="#2a2a2a", tags="grid")
        self.canvas.tag_lower("grid")

    # === Drag & Connect ===


    def _orch_on_canvas_click(self, event):
        try:
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            
            # Check if we clicked on something (Node or Port)
            # We use tag bindings for interaction, so if we hit something, 
            # we let the specific binding handle it and just return here.
            # "current" tag is set by Tkinter under the mouse.
            tags = self.canvas.gettags("current")
            for t in tags:
                if t.startswith("node_") or t.startswith("input_") or t.startswith("output_"):
                    return

            # Also check overlapping just in case "current" is stale or tricky with small items
            curr = self.canvas.find_overlapping(cx-1, cy-1, cx+1, cy+1)
            for t in curr:
                tags = self.canvas.gettags(t)
                for tag in tags:
                    if tag.startswith("node_") or tag.startswith("input_") or tag.startswith("output_"):
                        return
            
            # Clicked on Empty Space -> Panning & Deselect
            self._orch_deselect_node()
            self.orch_panning = True
            self.canvas.scan_mark(event.x, event.y)
            
        except Exception as e:
            self.logger.error(f"Canvas Click Error: {e}")

    def _orch_deselect_node(self):
        self._is_updating_ui = True
        self.orch_selected_node = None
        
        # Clear specific vars
        self.prop_name_var.set("")
        self.prop_action_var.set("")
        self.prop_params_var.set("")
        self.prop_context_var.set("")
        self.prop_x1_var.set("0")
        self.prop_y1_var.set("0")
        self.prop_x2_var.set("0")
        self.prop_y2_var.set("0")
        
        # Clear shortcuts
        for w in self.shortcut_frame.winfo_children(): w.destroy()
        
        # Redraw all nodes to remove highlight
        for n in self.orch_nodes.values(): self._draw_node(n)
        
        # Clear tree selection
        if self.tree.selection():
            self.tree.selection_remove(self.tree.selection())
            
        self._is_updating_ui = False

    def _on_canvas_right_click(self, event):
        # Find node under cursor
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        
        clicked_node_id = None
        curr = self.canvas.find_overlapping(cx-5, cy-5, cx+5, cy+5)
        for t in curr:
            tags = self.canvas.gettags(t)
            for tag in tags:
                if tag.startswith("node_"):
                    clicked_node_id = tag.split("_")[1]
                    break
        
        menu = tk.Menu(self, tearoff=0)
        if clicked_node_id:
            self._select_node(clicked_node_id)
            menu.add_command(label="🗑️ 删除节点 (Delete)", command=self._delete_selected_node)
            menu.add_command(label="📋 复制节点 (Copy)", command=self._copy_selected_node)
        else:
             menu.add_command(label="➕ 添加节点 (Add Node)", command=lambda: self._orch_on_canvas_double_click(event))
             
        menu.post(event.x_root, event.y_root)

    def _delete_selected_node(self):
        if not self.orch_selected_node: return
        nid = self.orch_selected_node
        
        # Remove connections
        self.orch_connections = [(u,v) for u,v in self.orch_connections if u!=nid and v!=nid]
        
        # Remove node
        if nid in self.orch_nodes:
            del self.orch_nodes[nid]
            
        if nid in self.orch_node_canvas_items:
            del self.orch_node_canvas_items[nid]
        
        self.orch_selected_node = None
        self._orch_deselect_node()
        
        # Full redraw
        self.canvas.delete("all")
        self.orch_node_canvas_items = {} # Reset and rebuild
        self._draw_grid()
        for n in self.orch_nodes.values(): self._draw_node(n)
        self._update_connections()
        self._update_tree()

    def _copy_selected_node(self):
        if not self.orch_selected_node: return
        # Simple duplicate logic
        old = self.orch_nodes[self.orch_selected_node]
        new_id = str(uuid.uuid4())[:8]
        new_node = WorkflowNode(
            id=new_id, 
            action_type=old.action_type, 
            step_name=f"{old.step_name}_Copy",
            params=old.params,
            context=old.context,
            coords=old.coords.copy(),
            canvas_x=old.canvas_x + 20,
            canvas_y=old.canvas_y + 20
        )
        self.orch_nodes[new_id] = new_node
        self._draw_node(new_node)
        self._select_node(new_id)
        self._update_tree()

    def _orch_on_canvas_double_click(self, event):
        """Double click to add node via Quick Search"""
        # Save click position
        self._last_click_pos = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        
        # Calculate screen coordinates for popup
        # To ensure it appears on top of the correct window (Popout or Main),
        # determine the correct master.
        master = self.canvas.winfo_toplevel()
        NodeSearchWindow(master, self._on_quick_node_selected, x=event.x_root, y=event.y_root)

    def _on_quick_node_selected(self, action_type):
        """Callback from NodeSearchWindow"""
        cx, cy = getattr(self, '_last_click_pos', (100, 100))
        self._add_node_at_pos(action_type, cx, cy)

    def _add_node_at_pos(self, action_type, x, y):
        """Add node and select it immediately"""
        node_id = str(uuid.uuid4())[:8]
        
        # Determine label
        label = action_type
        for cat in ACTION_CATEGORIES.values():
            if action_type in cat:
                label = cat[action_type].get("label", action_type)
                break
                
        node = WorkflowNode(
            id=node_id,
            action_type=action_type,
            step_name=label,
            canvas_x=int(x),
            canvas_y=int(y)
        )
        self.orch_nodes[node_id] = node
        self._draw_node(node)
        
        # Auto-select to show recommended params immediately
        self._select_node(node_id)
        self._update_scrollregion()
        
    def _orch_on_canvas_drag(self, event):
        try:
            Canvas = self.canvas
            cx = Canvas.canvasx(event.x)
            cy = Canvas.canvasy(event.y)
            
            if self.orch_panning:
                self.canvas.scan_dragto(event.x, event.y, gain=1)
                return

            if self.orch_connecting_from:
                if self.orch_temp_line_id: Canvas.delete(self.orch_temp_line_id)
                # Guard against missing node
                if self.orch_connecting_from not in self.orch_nodes: return
                node = self.orch_nodes[self.orch_connecting_from]
                x1, y1 = node.canvas_x + 160, node.canvas_y + 35
                self.orch_temp_line_id = Canvas.create_line(x1, y1, cx, cy, fill="#aaa", dash=(4,2))
                return
                
            if self.orch_drag_node_id:
                if self.orch_drag_node_id not in self.orch_nodes: return
                node = self.orch_nodes[self.orch_drag_node_id]
                # Must cast to int
                node.canvas_x = int(cx - self.orch_drag_offset[0])
                node.canvas_y = int(cy - self.orch_drag_offset[1])
                self._draw_node(node)
            self._update_connections()

        except Exception as e:
            self.logger.error(f"Drag error: {e}")

    def _orch_on_canvas_release(self, event):
        try:
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            
            if self.orch_connecting_from:
                # If we were DRAGGING a connection (mouse held down)
                # Check if we landed on a target
                if self.orch_temp_line_id: self.canvas.delete(self.orch_temp_line_id)
                self.orch_temp_line_id = None
                
                curr = self.canvas.find_overlapping(cx-10, cy-10, cx+10, cy+10)
                found_target = False
                for t in curr:
                    tags = self.canvas.gettags(t)
                    for tag in tags:
                        if tag.startswith("input_"):
                            target_id = tag.split("_")[1]
                            if target_id != self.orch_connecting_from:
                                self.orch_connections.append((self.orch_connecting_from, target_id))
                                self._draw_connection(self.orch_connecting_from, target_id)
                                found_target = True
                
                # If NO target found, enter WIRE MODE (Click-Click)
                if not found_target:
                     # Re-create the temp line for motion tracking
                     node = self.orch_nodes[self.orch_connecting_from]
                     x1, y1 = node.canvas_x + 160, node.canvas_y + 35
                     self.orch_temp_line_id = self.canvas.create_line(x1, y1, cx, cy, fill="#aaa", dash=(4,2))
                     self.orch_wire_mode = True
                     # Do NOT clear orch_connecting_from
                     self.orch_drag_node_id = None
                     return
            
            # If we were panning or dragging node
            self.orch_connecting_from = None
            self.orch_drag_node_id = None
            self.orch_panning = False
        except Exception as e:
            self.logger.error(f"Release error: {e}")

    def _on_mouse_wheel(self, event):
        # Respond to Linux (4/5) or Windows/Mac (delta)
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")

    def _draw_connection(self, from_id, to_id):
        if from_id not in self.orch_nodes or to_id not in self.orch_nodes:
            return 
            
        n1 = self.orch_nodes[from_id]
        n2 = self.orch_nodes[to_id]
        
        # Start and End points
        x1, y1 = n1.canvas_x + 160, n1.canvas_y + 35
        x2, y2 = n2.canvas_x, n2.canvas_y + 35
        
        # Cubic Bezier Control Points
        # We want the line to come out horizontally from x1, and arrive horizontally at x2
        dist = abs(x2 - x1) * 0.5
        if dist < 50: dist = 50 # Minimum curvature
        
        cp1x, cp1y = x1 + dist, y1
        cp2x, cp2y = x2 - dist, y2
        
        line = self.canvas.create_line(x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2, smooth=True, fill="#5dade2", width=3, arrow=tk.LAST)
        self.canvas.tag_lower(line, "grid")
        
        if (from_id, to_id) not in self.orch_connection_lines: self.orch_connection_lines[(from_id, to_id)] = []
        self.orch_connection_lines[(from_id, to_id)].append(line)

    def _update_connections(self):
        for l_list in self.orch_connection_lines.values():
            for l in l_list: self.canvas.delete(l)
        self.orch_connection_lines = {}
        for (u, v) in self.orch_connections: self._draw_connection(u, v)

    def _on_pan_start(self, event): self.canvas.scan_mark(event.x, event.y)
    def _on_pan_drag(self, event): self.canvas.scan_dragto(event.x, event.y, gain=1)

    # === Screenshot Preview ===
    def refresh_screenshot(self):
        if not self.ctx.device: return
        try:
            pil_img = self.ctx.device.screenshot()
            self.ctx.screenshot_pil = pil_img # Shared
            self._redraw_gen_screenshot(pil_img)
        except Exception as e:
            self.logger.error(f"Scr error: {e}")

    def _redraw_gen_screenshot(self, pil_img):
        w = max(1, self.gen_canvas.winfo_width())
        h = max(1, self.gen_canvas.winfo_height())
        iw, ih = pil_img.size
        if iw == 0 or ih == 0: return
        
        ratio = min(w/iw, h/ih)
        nw, nh = int(iw*ratio), int(ih*ratio)
        resized = pil_img.resize((nw, nh), Image.LANCZOS)
        self.gen_photo = ImageTk.PhotoImage(resized) # Keep ref
        
        self.gen_canvas.delete("all")
        x = (w - nw) // 2
        y = (h - nh) // 2
        self.gen_canvas.create_image(x, y, image=self.gen_photo, anchor="nw")

    # === Treeview ===
    def _update_tree(self):
        self.tree.delete(*self.tree.get_children())
        nodes = sorted(self.orch_nodes.values(), key=lambda n: n.canvas_y)
        for n in nodes: self.tree.insert("", "end", iid=n.id, text=f"{n.step_name} ({n.action_type})")
            
    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if sel: self._select_node(sel[0])

    # === Actions ===
    def _orch_test_selected_node(self):
        if not self.orch_selected_node:
            messagebox.showwarning("Warning", "Select a node first")
            return
        
        node = self.orch_nodes[self.orch_selected_node]
        if not self.ctx.device:
            messagebox.showwarning("Warning", "Device not connected")
            return
            
        step_data = {
            "step_id": 999,
            "step_name": node.step_name,
            "action_type": node.action_type,
            "params": node.params,
            "context": node.context,
            "coords": node.coords,
            "retry_count": 0,
            "is_optional": False
        }
        
        threading.Thread(target=self._run_single_node_thread, args=(step_data, node.id), daemon=True).start()

    def _run_single_node_thread(self, step_data, node_id):
        try:
            runner = WorkflowRunner(self.ctx.device)
            self.after(0, lambda: self.status_label.configure(text=f"Testing: {step_data['step_name']}", text_color="#3498db"))
            self.after(0, lambda: self._highlight_node(node_id, "#f1c40f"))
            
            success = runner.execute_step(step_data, {})
            
            if success:
                self.after(0, lambda: self.status_label.configure(text=f"Test Passed: {step_data['step_name']}"))
                self.after(0, lambda: self._highlight_node(node_id, "#2ecc71"))
                self.after(0, lambda: messagebox.showinfo("Success", "Node executed successfully"))
            else:
                self.after(0, lambda: self.status_label.configure(text=f"Test Failed: {step_data['step_name']}"))
                self.after(0, lambda: self._highlight_node(node_id, "#e74c3c"))
                self.after(0, lambda: messagebox.showerror("Failed", "Node execution failed"))
                
        except Exception as e:
            self.logger.error(f"Test failed: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    def _orch_run_all(self):
        if not self.orch_nodes:
            messagebox.showwarning("Warning", "No nodes to run")
            return
        if not self.ctx.device:
            messagebox.showwarning("Warning", "Device not connected")
            return

        # 1. Topological Sort
        ordered_nodes = self._orch_topological_sort()
        total_steps = len(ordered_nodes)
        
        # 2. Export to execution format
        execution_plan = []
        for i, node in enumerate(ordered_nodes, 1):
            execution_plan.append({
                "step_id": i,
                "step_name": node.step_name,
                "action_type": node.action_type,
                "params": node.params,
                "context": node.context,
                "coords": node.coords,
                "retry_count": node.retry_count,
                "is_optional": node.is_optional,
                "_node_id": node.id
            })

        # 3. Run in Thread
        threading.Thread(target=self._run_workflow_thread, args=(execution_plan,), daemon=True).start()

    def _run_workflow_thread(self, execution_plan):
        try:
            runner = WorkflowRunner(self.ctx.device)
            total = len(execution_plan)
            
            self.after(0, lambda: self.status_label.configure(text=f"运行中: 0/{total}", text_color="#3498db"))
            
            success_count = 0
            fail_count = 0
            
            for i, step in enumerate(execution_plan):
                # Robustness Check: Ensure window still exists
                if not self.winfo_exists():
                    break
                    
                node_id = step.pop("_node_id")
                step_name = step.get("step_name")
                
                # Update UI
                self.after(0, lambda idx=i, name=step_name: self.status_label.configure(text=f"运行中: {idx+1}/{total} - {name}"))
                self.after(0, lambda nid=node_id: self._highlight_node(nid, "#f1c40f")) # Running: Yellow
                
                try:
                    # Execute
                    success = runner.execute_step(step, {})
                except Exception as step_e:
                    self.logger.error(f"Step '{step_name}' crashed: {step_e}")
                    success = False

                if success:
                    success_count += 1
                    self.after(0, lambda nid=node_id: self._highlight_node(nid, "#2ecc71")) # Success: Green
                else:
                    fail_count += 1
                    is_optional = step.get("is_optional", False)
                    self.after(0, lambda nid=node_id: self._highlight_node(nid, "#e74c3c")) # Fail: Red
                    
                    if not is_optional:
                        self.after(0, lambda: messagebox.showerror("执行失败", f"步骤失败: {step_name}"))
                        break
                        
            self.after(0, lambda: self.status_label.configure(text=f"完成: {success_count} 成功, {fail_count} 失败"))
            if fail_count == 0:
                self.after(0, lambda: messagebox.showinfo("成功", "所有步骤执行成功"))
                
        except Exception as e:
            self.logger.error(f"Execution failed: {e}")
            self.after(0, lambda: messagebox.showerror("严重错误", f"工作流执行崩溃: {str(e)}"))


    def _orch_topological_sort(self) -> List[WorkflowNode]:
        if not self.orch_connections:
            return sorted(self.orch_nodes.values(), key=lambda n: n.canvas_y)
            
        in_degree = {nid: 0 for nid in self.orch_nodes}
        adj = {nid: [] for nid in self.orch_nodes}
        
        for u, v in self.orch_connections:
            if u in adj and v in in_degree:
                adj[u].append(v)
                in_degree[v] += 1
                
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        # Sort queue by Y position to handle parallel branches Deterministically
        queue.sort(key=lambda nid: self.orch_nodes[nid].canvas_y)
        
        result = []
        while queue:
            nid = queue.pop(0)
            result.append(self.orch_nodes[nid])
            
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            
            # Re-sort queue
            queue.sort(key=lambda nid: self.orch_nodes[nid].canvas_y)
            
        # Add isolated nodes
        for node in self.orch_nodes.values():
            if node not in result: result.append(node)
            
        return result

    def _highlight_node(self, node_id, color):
        if not self.winfo_exists(): return
        if node_id in self.orch_node_canvas_items:
            items = self.orch_node_canvas_items[node_id]
            if items: 
                try:
                    self.canvas.itemconfig(items[0], outline=color, width=3)
                except Exception:
                     # Ignore canvas errors (item deleted, etc.)
                     pass

    def _clear_canvas(self):
        try:
            self.orch_nodes = {}
            self.orch_connections = []
            self.orch_node_canvas_items = {}
            self.orch_connection_lines = {}
            self.canvas.delete("all")
            self._draw_grid()
            self._update_tree()
        except Exception as e:
            self.logger.error(f"Clear canvas error: {e}")
        
    def _auto_connect(self):
        # Sort by Y then X for stable ordering
        nodes = sorted(self.orch_nodes.values(), key=lambda n: (n.canvas_y, n.canvas_x))
        self.orch_connections = []

        for i in range(len(nodes)-1): self.orch_connections.append((nodes[i].id, nodes[i+1].id))
        self.canvas.delete("all")
        self._draw_grid()
        for n in self.orch_nodes.values(): self._draw_node(n)
        self._update_connections()

    def _export_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            data = {
                "nodes": [n.to_dict() for n in self.orch_nodes.values()],
                "connections": self.orch_connections
            }
            with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)
                
    def _import_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f: data = json.load(f)
            
            # Helper to parse node list vs legacy format
            is_legacy_list = isinstance(data, list)
            nodes_data = data.get("nodes", []) if isinstance(data, dict) else data
            connections_data = data.get("connections", []) if isinstance(data, dict) else []

            self._clear_canvas()
            
            loaded_ids = []
            
            # Restore Nodes
            for i, n_data in enumerate(nodes_data):
                # Use ID from JSON or generate new if missing (legacy)
                # For legacy, ensure unique but consistent if possible, or just random
                nid = n_data.get("id") or str(uuid.uuid4())[:8]
                loaded_ids.append(nid)
                
                # Auto-layout for legacy: default spacing
                default_x = 100 + (30 * (i % 5)) # slight stagger
                default_y = 50 + (i * 120)       # vertical spacing
                
                cx = n_data.get("canvas_x")
                cy = n_data.get("canvas_y")
                
                # If coordinates are missing (legacy), use auto-calculated
                final_x = int(cx) if cx is not None else default_x
                final_y = int(cy) if cy is not None else default_y
                
                node = WorkflowNode(
                    id=nid,
                    action_type=n_data.get("action_type", "Click Region"),
                    step_name=n_data.get("step_name", f"Step {i+1}"),
                    params=n_data.get("params", ""),
                    context=n_data.get("context", ""),
                    coords=n_data.get("coords", {}),
                    canvas_x=final_x,
                    canvas_y=final_y
                )
                self.orch_nodes[node.id] = node
                self._draw_node(node)
                
            # Restore Connections
            self.orch_connections = []
            if connections_data:
                self.orch_connections = [tuple(c) for c in connections_data]
            elif is_legacy_list and len(loaded_ids) > 1:
                # Legacy auto-connect: sequential
                for i in range(len(loaded_ids) - 1):
                    self.orch_connections.append((loaded_ids[i], loaded_ids[i+1]))

            self._update_connections()
            self._update_tree()

                
        except Exception as e:
            messagebox.showerror("Error", f"Import failed: {e}")
            self.logger.error(f"Import error: {e}")
            
    def _toggle_canvas_popout(self):
        if self._canvas_window:
            self._dock_canvas()
        else:
            self._popout_canvas()

    def _popout_canvas(self):
        self._canvas_window = ctk.CTkToplevel(self)
        self._canvas_window.title("WorkFlow Canvas - Independent Window")
        self._canvas_window.geometry("1200x800")
        self._canvas_window.protocol("WM_DELETE_WINDOW", self._dock_canvas)
        
        # 1. Create placeholder in main window
        self._canvas_placeholder = ctk.CTkFrame(self.center_panel, fg_color="#2a2a2a")
        self._canvas_placeholder.grid(row=0, column=0, sticky="nsew", padx=10, pady=(0, 5))
        ctk.CTkLabel(self._canvas_placeholder, text="📺 Canvas is in independent window", font=("Arial", 16)).pack(expand=True)
        ctk.CTkButton(self._canvas_placeholder, text="⬅ Dock Canvas", command=self._dock_canvas).pack(pady=20)
        
        # 2. Hide original container
        self.canvas_container.grid_remove()
        
        # 3. Create new container in popup
        self._popup_container = ctk.CTkFrame(self._canvas_window)
        self._popup_container.pack(fill="both", expand=True)
        self._popup_container.grid_rowconfigure(0, weight=1)
        self._popup_container.grid_columnconfigure(0, weight=1)
        
        # 4. Swap Canvas
        # We can't easily repack the SAME widget across windows in Tkinter without issues.
        # Instead, we create a fresh canvas and bind events.
        self._original_canvas = self.canvas
        self.canvas = tk.Canvas(self._popup_container, bg="#1e1e1e", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbars for popup
        h_scroll = tk.Scrollbar(self._popup_container, orient="horizontal", command=self.canvas.xview)
        v_scroll = tk.Scrollbar(self._popup_container, orient="vertical", command=self.canvas.yview)
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        # Re-bind events
        self._bind_canvas_events()
        
        # CLEAR TRACKING to avoid ID collisions
        self.orch_node_canvas_items = {}
        self.orch_connection_lines = {}
        
        # Initial draw
        self._draw_grid()
        for n in self.orch_nodes.values(): self._draw_node(n)
        self._update_connections()
        
        self._update_connections()
        self._update_scrollregion()
        
        self.expand_btn.configure(text="⬅ Dock", fg_color="#e74c3c")
        self._canvas_window.focus_force()
        
    def _dock_canvas(self):
        if not self._canvas_window: return
        
        # 0. Deselect to prevent "ghost" selection trying to update UI
        self._orch_deselect_node()
        
        # 1. Capture reference to window to destroy
        window_to_destroy = self._canvas_window
        self._canvas_window = None
        
        # 2. Restore Canvas Reference FIRST
        # This ensures that if any event fires during destroy(), self.canvas is valid (the docked one)
        self.canvas = self._original_canvas
        self.canvas_container.grid(row=0, column=0, sticky="nsew")
        
        # 3. Destroy popup SAFELY
        try:
            window_to_destroy.destroy()
        except Exception as e:
            self.logger.error(f"Error destroying popup: {e}")
            
        # 4. Restore placeholder
        if hasattr(self, "_canvas_placeholder"):
             self._canvas_placeholder.destroy()
        
        # 5. Force update to prevent layout glitch
        self.canvas.update_idletasks()
        
        # 6. Redraw on original
        self.canvas.delete("all")
        
        # CLEAR TRACKING to avoid ID collisions
        self.orch_node_canvas_items = {}
        self.orch_connection_lines = {}
        
        self._draw_grid()
        for n in self.orch_nodes.values(): self._draw_node(n)
        self._update_connections()

        self.expand_btn.configure(text="⬜ 独立窗口", fg_color="#555")
