
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.context import SharedContext
from app.core.constants import ACTION_CATEGORIES, NODE_STYLES, NODE_PARAM_SHORTCUTS
from app.gui.live_debugger import LiveDebuggerFrame
from app.gui.workflow_editor import WorkflowEditorFrame
from app.extension_manager import ExtensionManager
from adbutils import adb, AdbError

# Configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class VintedAutomationApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Vinted Automation V4.0 (Refactored)")
        self.geometry("1400x900")
        
        # Initialize Shared Context
        self.ctx = SharedContext()
        self._setup_logging()
        
        # Initialize Extensions
        self._init_extensions()
        
        # Build UI
        self._build_top_bar()
        self._build_tabs()
        
        # Initial device refresh
        self.after(1000, self.refresh_device_list)

    def _setup_logging(self):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
        self.logger = logging.getLogger("VintedApp")

    def _init_extensions(self):
        """Initialize ExtensionManager and load custom nodes"""
        try:
            self.ext_manager = ExtensionManager()
            self.ctx.ext_manager = self.ext_manager
            
            # Load metadata
            nodes = self.ext_manager.load_nodes_metadata()
            count = 0
            for node in nodes:
                cat = node.get("category", "Custom")
                name = node.get("name")
                icon = node.get("icon", "🧩")
                color = node.get("color", "#555")
                shortcuts = node.get("shortcuts")
                
                if cat not in ACTION_CATEGORIES:
                    ACTION_CATEGORIES[cat] = {}
                
                ACTION_CATEGORIES[cat][name] = {"icon": icon, "color": color, "label": name}
                NODE_STYLES[name] = {"icon": icon, "color": color, "label": name}
                
                if shortcuts:
                    NODE_PARAM_SHORTCUTS[name] = shortcuts
                count += 1
                
            self.logger.info(f"Loaded {count} custom extensions.")
        except Exception as e:
            self.logger.error(f"Failed to load extensions: {e}")

    def _build_top_bar(self):
        self.top_bar = ctk.CTkFrame(self, height=50)
        self.top_bar.pack(side="top", fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(self.top_bar, text="📱 设备:").pack(side="left", padx=5)
        
        self.device_combo = ctk.CTkComboBox(self.top_bar, width=200)
        self.device_combo.pack(side="left", padx=5)
        
        ctk.CTkButton(self.top_bar, text="🔄 刷新", width=60, command=self.refresh_device_list).pack(side="left", padx=5)
        ctk.CTkButton(self.top_bar, text="🔌 连接", width=80, fg_color="green", command=self.connect_device).pack(side="left", padx=5)
        
        self.status_label = ctk.CTkLabel(self.top_bar, text="未连接", text_color="gray")
        self.status_label.pack(side="left", padx=20)

    def _build_tabs(self):
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(fill="both", expand=True, padx=5, pady=5)
        
        # T1: Live Debugger
        t1 = self.tab_view.add("🔍 实时调试")
        self.live_debugger = LiveDebuggerFrame(t1, self.ctx)
        self.live_debugger.pack(fill="both", expand=True)
        
        # T2: Workflow Designer
        t2 = self.tab_view.add("🎨 工作流编排")
        self.workflow_editor = WorkflowEditorFrame(t2, self.ctx)
        self.workflow_editor.pack(fill="both", expand=True)

    def refresh_device_list(self):
        try:
            devices = adb.device_list()
            serials = [d.serial for d in devices]
            self.device_combo.configure(values=serials if serials else ["No devices"])
            if serials:
                self.device_combo.set(serials[0])
        except Exception as e:
            self.logger.error(f"Failed to list devices: {e}")

    def connect_device(self):
        serial = self.device_combo.get()
        if not serial or serial == "No devices":
            return
            
        try:
            self.ctx.device = adb.device(serial=serial)
            self.ctx.selected_serial = serial
            self.status_label.configure(text=f"已连接: {serial}", text_color="lightgreen")
            
            # Update Live Debugger
            self.live_debugger.refresh_screenshot()
            
            messagebox.showinfo("Success", f"Connected to {serial}")
        except AdbError as e:
            self.status_label.configure(text="连接失败", text_color="red")
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    app = VintedAutomationApp()
    app.mainloop()
