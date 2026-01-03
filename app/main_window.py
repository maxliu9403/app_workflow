"""
主窗口
======

应用程序主窗口 - 薄层协调器
"""

import customtkinter as ctk
from typing import Optional, TYPE_CHECKING

from core.device_manager import DeviceManager
from core.vision_service import VisionService
from core.config_manager import ConfigManager


class MainWindow:
    """
    主窗口类
    
    负责:
    - 初始化核心服务
    - 构建顶部设备栏
    - 创建 Tab 视图并加载各 Tab 模块
    - 提供共享的日志功能
    """
    
    def __init__(self):
        # 设置主题
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # 创建主窗口
        self.root = ctk.CTk()
        self.root.title("Vinted 自动化控制台 V4.0")
        self.root.geometry("1600x900")
        
        # 配置网格权重
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # 初始化核心服务
        self.device_manager = DeviceManager()
        self.vision_service = VisionService()
        self.config_manager = ConfigManager()
        
        # 设置设备状态回调
        self.device_manager.set_status_callback(self._on_device_status_change)
        
        # 尝试加载默认配置
        default_yaml = ConfigManager.find_default_yaml()
        if default_yaml:
            self.config_manager.load(default_yaml)
        
        # 变量
        self.device_var = ctk.StringVar(value="")
        
        # 构建 UI
        self._build_device_bar()
        self._build_tabs()
        
        # 刷新设备列表
        self.refresh_device_list()
    
    def _build_device_bar(self) -> None:
        """构建顶部设备栏"""
        top_bar = ctk.CTkFrame(self.root)
        top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        top_bar.grid_columnconfigure(5, weight=1)
        
        ctk.CTkLabel(
            top_bar,
            text="📱 设备:",
            font=ctk.CTkFont(size=14),
        ).grid(row=0, column=0, padx=10, pady=10)
        
        self.device_combo = ctk.CTkComboBox(
            top_bar,
            variable=self.device_var,
            values=[],
            width=200,
        )
        self.device_combo.grid(row=0, column=1, padx=6, pady=10)
        
        ctk.CTkButton(
            top_bar,
            text="刷新设备",
            width=110,
            command=self.refresh_device_list,
        ).grid(row=0, column=2, padx=6, pady=10)
        
        ctk.CTkButton(
            top_bar,
            text="连接",
            width=90,
            command=self.connect_device,
        ).grid(row=0, column=3, padx=6, pady=10)
        
        ctk.CTkButton(
            top_bar,
            text="断开",
            width=90,
            fg_color="#555555",
            command=self.disconnect_device,
        ).grid(row=0, column=4, padx=6, pady=10)
        
        self.status_label = ctk.CTkLabel(
            top_bar,
            text="状态：未连接",
            text_color="#aaaaaa",
        )
        self.status_label.grid(row=0, column=5, padx=10, pady=10, sticky="w")
        
        # 日志控制台入口（右侧）
        self.log_textbox: Optional[ctk.CTkTextbox] = None  # 将在 Tab 中创建
    
    def _build_tabs(self) -> None:
        """构建 Tab 视图"""
        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # 创建 Tab 页面
        tab_live = self.tabs.add("实时调试")
        tab_log = self.tabs.add("日志回放")
        tab_gen = self.tabs.add("步骤生成器")
        tab_orch = self.tabs.add("流程编排")
        
        # 导入并初始化 Tab 模块
        # 注意：这里使用延迟导入避免循环依赖
        from tabs.orchestrator_tab import OrchestratorTab
        
        # 目前只初始化已模块化的 Tab
        self.orch_tab = OrchestratorTab(tab_orch, self)
        
        # 其他 Tab 暂时显示占位符
        self._build_placeholder_tab(tab_live, "实时调试 Tab（待模块化）")
        self._build_placeholder_tab(tab_log, "日志回放 Tab（待模块化）")
        self._build_placeholder_tab(tab_gen, "步骤生成器 Tab（待模块化）")
    
    def _build_placeholder_tab(self, parent: ctk.CTkFrame, message: str) -> None:
        """构建占位符 Tab"""
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            parent,
            text=message,
            font=ctk.CTkFont(size=20),
            text_color="#666666",
        ).grid(row=0, column=0)
    
    # ==================== 设备管理 ====================
    
    def refresh_device_list(self) -> None:
        """刷新设备列表"""
        devices = self.device_manager.list_devices()
        self.device_combo.configure(values=devices)
        if devices:
            self.device_var.set(devices[0])
        else:
            self.device_var.set("")
    
    def connect_device(self) -> None:
        """连接选中的设备"""
        serial = self.device_var.get()
        if not serial:
            self.log("⚠️ 请先选择设备")
            return
        
        self.device_manager.connect(serial)
    
    def disconnect_device(self) -> None:
        """断开设备连接"""
        self.device_manager.disconnect()
    
    def _on_device_status_change(self, connected: bool, message: str) -> None:
        """设备状态变化回调"""
        if connected:
            self.status_label.configure(text=f"状态：{message}", text_color="#4CAF50")
        else:
            self.status_label.configure(text=f"状态：{message}", text_color="#aaaaaa")
        self.log(f"[设备] {message}")
    
    # ==================== 日志 ====================
    
    def log(self, msg: str) -> None:
        """输出日志"""
        print(f"[LOG] {msg}")  # 暂时输出到控制台
        # TODO: 输出到日志控制台 UI
    
    # ==================== 运行 ====================
    
    def run(self) -> None:
        """启动主循环"""
        self.root.mainloop()
