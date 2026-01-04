import customtkinter as ctk
from app.core.constants import ACTION_CATEGORIES

class NodeSearchWindow(ctk.CTkToplevel):
    def __init__(self, master, on_select_callback, x=None, y=None):
        super().__init__(master)
        
        self.on_select_callback = on_select_callback
        self.title("🔍 添加节点")
        self.geometry("300x400")
        self.resizable(False, False)
        
        # Move window to mouse position if provided
        if x is not None and y is not None:
             self.geometry(f"+{int(x)}+{int(y)}")
             
        self.transient(master)
        self.grab_set()
        self.focus_force()
        self.overrideredirect(True) # Frameless for modern popup feel
        
        # Main Frame with Border
        self.main_frame = ctk.CTkFrame(self, border_width=2, border_color="#3498db")
        self.main_frame.pack(fill="both", expand=True)

        # 1. Search Bar
        self.search_var = ctk.StringVar()
        self.search_var.trace("w", self._filter_list)
        
        self.search_entry = ctk.CTkEntry(
            self.main_frame, 
            placeholder_text="输入关键字搜索...", 
            textvariable=self.search_var,
            font=("Arial", 14),
            height=40
        )
        self.search_entry.pack(fill="x", padx=10, pady=10)
        self.search_entry.bind("<Return>", self._on_enter)
        self.search_entry.bind("<Down>", self._focus_list)
        self.search_entry.bind("<Escape>", lambda e: self.destroy())
        self.search_entry.focus_set()

        # 2. Scrollable List of Actions
        self.scroll_frame = ctk.CTkScrollableFrame(self.main_frame)
        self.scroll_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        
        # Flatten actions for searching
        self.all_actions = []
        for cat, actions in ACTION_CATEGORIES.items():
            for action_type, meta in actions.items():
                self.all_actions.append({
                    "label": meta.get("label", action_type),
                    "action_type": action_type,
                    "icon": meta.get("icon", "🔹"),
                    "category": cat
                })
        
        self.action_buttons = []
        self._filter_list() # Initial populate

    def _filter_list(self, *args):
        query = self.search_var.get().lower()
        
        # Clear existing
        for btn in self.action_buttons:
            btn.destroy()
        self.action_buttons = []
        
        # Filter (Top 20 matches)
        matches = [a for a in self.all_actions if query in a["label"].lower() or query in a["action_type"].lower()]
        
        for action in matches:
            btn = ctk.CTkButton(
                self.scroll_frame,
                text=f"{action['icon']} {action['label']}",
                anchor="w",
                fg_color="transparent",
                text_color="#eee",
                hover_color="#34495e",
                height=32,
                command=lambda a=action: self._select_action(a)
            )
            btn.pack(fill="x", padx=2, pady=1)
            self.action_buttons.append(btn)
            
            # Allow keyboard selection binding for first item?
            # Implemented simplified Enter key selection below

    def _select_action(self, action):
        if self.on_select_callback:
            self.on_select_callback(action["action_type"])
        self.destroy()

    def _on_enter(self, event):
        # Select first visible item
        if self.action_buttons:
            self.action_buttons[0].invoke()
            
    def _focus_list(self, event):
        # Todo: Implement proper list keyboard navigation
        pass
