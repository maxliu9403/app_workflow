import customtkinter as ctk
import tkinter as tk
from typing import Optional, Dict, Any, Tuple
import math

class GraphEditor(ctk.CTkFrame):
    """
    Visual Node Graph Editor Component.
    Renders the WorkflowStore state on an infinite canvas.
    """
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Internal State
        self.store = None
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.offset_y = 0
        self.selected_node_id = None
        self.running_node_id = None # V-Next: Runtime Highlight
        self._drag_data = {"x": 0, "y": 0, "item": None}
        
        # Canvas
        self.canvas = tk.Canvas(
            self, 
            bg="#1e1e1e", 
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill="both", expand=True)
        
        # Events
        self.canvas.bind("<ButtonPress-3>", self._on_pan_start)
        self.canvas.bind("<B3-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_click) # Context Menu
        
        # Keyboard (Must focus first)
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())
        self.canvas.bind("<Delete>", self._on_key_delete)
        self.canvas.bind("<BackSpace>", self._on_key_delete)  # Windows
        
        # Initial Draw
        self._draw_grid()

    def set_store(self, store):
        """Bind to WorkflowStore"""
        self.store = store
        self.store.add_observer(self._on_store_update)
        self.redraw()

    def _on_store_update(self, event: str, data: Any):
        """Callback from WorkflowStore"""
        # Optimize: redraw only relevant parts ideally
        # For prototype: Full Redraw
        if event in ("node_added", "node_removed", "connection_added", "connection_removed", "graph_loaded"):
            self.redraw()
        elif event == "node_moved":
            # self._update_node_pos(data) # To be implemented for optimization
            self.redraw()

    def set_running_node(self, node_id):
        """Highlight the currently executing node"""
        self.running_node_id = node_id
        self.redraw()

    def redraw(self):
        """Full repaint of the graph"""
        self.canvas.delete("all")
        self._draw_grid()
        
        if not self.store:
            return
            
        # Draw Edges first (behind nodes)
        for node in self.store.nodes.values():
            for target_id in node.outputs:
                if target_id in self.store.nodes:
                    target = self.store.nodes[target_id]
                    self._draw_connection(node, target)

        # Draw Nodes
        for node in self.store.nodes.values():
            self._draw_node(node)

    def _draw_grid(self):
        """Draw infinite grid background"""
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        # Fallback if window not mapped yet
        if w < 10: w = 2000
        if h < 10: h = 2000

        step = 50 * self.scale
        
        # Calculate start/end based on offset
        # (Simplified static grid for now, true infinite grid needs math)
        # Using scan_mark/dragto is easier for panning, but drawing logical grid is better
        # Let's just draw a fixed large grid for the prototype
        
        # Draw Dots
        for x in range(0, w, int(step)):
            for y in range(0, h, int(step)):
                self.canvas.create_oval(
                    x-1, y-1, x+1, y+1, 
                    fill="#333", outline=""
                )

    def _draw_node(self, node):
        """Draw a single node"""
        x = node.x * self.scale + self.offset_x
        y = node.y * self.scale + self.offset_y
        w = 160 * self.scale
        h = 80 * self.scale
        r = 10 * self.scale # Radius
        
        # Shadow
        self.canvas.create_rectangle(
            x+5, y+5, x+w+5, y+h+5,
            fill="#111", outline="",
            tags=("node", node.id)
        )
        
        
        # Body
        color = "#444" # Default
        outline_color = "#666"
        outline_width = 2
        
        # State Prioritization: Running > Selected > Default
        if self.running_node_id == node.id:
            outline_color = "#00FF00" # Running (Green Glow)
            outline_width = 4
            # Add glow effect (simulated with multiple rectangles if needed, simple outline for now)
        elif self.selected_node_id == node.id:
            outline_color = "#F0A500" # Highlight (Orange/Gold)
            outline_width = 3

        self.canvas.create_rectangle(
            x, y, x+w, y+h,
            fill=color, outline=outline_color, width=outline_width,
            tags=("node", node.id)
        )
        
        # Header Color
        self.canvas.create_rectangle(
            x, y, x+w, y+24*self.scale,
            fill="#333", outline="",
            tags=("node", node.id)
        )
        
        # Title
        self.canvas.create_text(
            x+10*self.scale, y+12*self.scale,
            text=node.action_type,
            fill="white",
            anchor="w",
            font=("Arial", int(10*self.scale), "bold"),
            tags=("node", node.id)
        )

        # Ports (Input Left, Output Right)
        port_r = 6 * self.scale
        # In
        self.canvas.create_oval(
            x-port_r, y+h/2-port_r, x+port_r, y+h/2+port_r,
            fill="#777", outline="black",
            tags=("port", "in", node.id)
        )
        # Out
        self.canvas.create_oval(
            x+w-port_r, y+h/2-port_r, x+w+port_r, y+h/2+port_r,
            fill="#777", outline="black",
            tags=("port", "out", node.id)
        )

    def _draw_connection(self, source, target):
        """Draw bezier curve between nodes"""
        sx = (source.x * self.scale + self.offset_x) + 160 * self.scale
        sy = (source.y * self.scale + self.offset_y) + 40 * self.scale
        tx = (target.x * self.scale + self.offset_x)
        ty = (target.y * self.scale + self.offset_y) + 40 * self.scale
        
        # Control points
        dist = abs(tx - sx) * 0.5
        c1x = sx + dist
        c1y = sy
        c2x = tx - dist
        c2y = ty
        
        self.canvas.create_line(
            sx, sy, c1x, c1y, c2x, c2y, tx, ty,
            fill="#888", width=3*self.scale, smooth=True,
            arrow=tk.LAST
        )

    # ==================== Interaction ====================
    def _on_pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _on_pan_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_click(self, event):
        """Select, Drag Node or Start Connection"""
        wx, wy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        items = self.canvas.find_closest(wx, wy)
        tags = self.canvas.gettags(items[0]) if items else ()
        
        # Reset Selection if clicking empty space (unless port)
        if not items or ("node" not in tags and "port" not in tags):
            self._clear_selection()

        if "node" in tags:
            # Drag Node
            node_id = tags[1] 
            self._select_node(node_id) # Select on click
            self._drag_data["item"] = node_id
            self._drag_data["x"] = event.x
            self._drag_data["y"] = event.y
            
        elif "port" in tags:
            # Start Connection
            # tag format: ("port", "in"/"out", node_id)
            port_type = tags[1]
            node_id = tags[2]
            
            if port_type == "out":
                self._drag_data["connecting"] = True
                self._drag_data["start_node"] = node_id
                self._drag_data["start_x"] = wx
                self._drag_data["start_y"] = wy

    def _on_drag(self, event):
        wx, wy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        if self._drag_data.get("connecting"):
            # Draw Temp Line
            self.canvas.delete("temp_line")
            sx, sy = self._drag_data["start_x"], self._drag_data["start_y"]
            self.canvas.create_line(
                sx, sy, wx, wy,
                fill="#fff", dash=(4, 2), tags="temp_line"
            )
            
        elif self._drag_data["item"]:
            # Node Dragging
            node_id = self._drag_data["item"]
            dx = (event.x - self._drag_data["x"]) / self.scale
            dy = (event.y - self._drag_data["y"]) / self.scale
            
            if self.store and node_id in self.store.nodes:
                node = self.store.nodes[node_id]
                self.store.update_node_position(node_id, node.x + dx, node.y + dy)
                
            self._drag_data["x"] = event.x
            self._drag_data["y"] = event.y

    def _on_release(self, event):
        wx, wy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        if self._drag_data.get("connecting"):
            # Finish Connection
            self.canvas.delete("temp_line")
            items = self.canvas.find_closest(wx, wy)
            tags = self.canvas.gettags(items[0]) if items else ()
            
            if "port" in tags and tags[1] == "in":
                target_id = tags[2]
                source_id = self._drag_data["start_node"]
                
                if self.store:
                    self.store.connect(source_id, target_id)
            
            self._drag_data["connecting"] = False

        self._drag_data["item"] = None
        
    def _on_right_click(self, event):
        """Context Menu"""
        wx, wy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        items = self.canvas.find_closest(wx, wy)
        tags = self.canvas.gettags(items[0]) if items else ()
        
        menu = tk.Menu(self, tearoff=0)
        
        if "node" in tags:
            node_id = tags[1]
            self._select_node(node_id)
            menu.add_command(label="❌ Delete Node", command=lambda: self.store.remove_node(node_id))
            menu.add_command(label="✏️ Edit Params", command=lambda: print(f"Edit {node_id}")) # Todo: Dialog
        else:
            menu.add_command(label="➕ Add Note", command=lambda: print("Add Note"))
            
        menu.post(event.x_root, event.y_root)

    # ==================== Selection ====================
    def set_selection_callback(self, callback):
        self.selection_callback = callback

    def _select_node(self, node_id):
        self.selected_node_id = node_id
        self.redraw() # Update outline color
        if hasattr(self, 'selection_callback') and self.selection_callback:
            self.selection_callback(node_id)

    def _clear_selection(self):
        self.selected_node_id = None
        self.redraw()
        if hasattr(self, 'selection_callback') and self.selection_callback:
            self.selection_callback(None)
        
    def _on_key_delete(self, event):
        if self.selected_node_id and self.store:
            self.store.remove_node(self.selected_node_id)
            self.selected_node_id = None

    def _on_zoom(self, event):
        """Mouse Wheel Zoom"""
        factor = 1.1 if event.delta > 0 else 0.9
        self.scale *= factor
        if self.scale < 0.2: self.scale = 0.2
        if self.scale > 3.0: self.scale = 3.0
        self.redraw()
