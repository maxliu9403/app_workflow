"""
Tab 基类
========

所有 Tab 页面的抽象基类
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

import customtkinter as ctk

if TYPE_CHECKING:
    from app.main_window import MainWindow


class BaseTab(ABC):
    """
    Tab 基类
    
    提供共享的设备管理器、视觉服务和日志功能
    """
    
    def __init__(self, parent: ctk.CTkFrame, app: "MainWindow"):
        """
        初始化 Tab
        
        Args:
            parent: 父容器（Tab 页面）
            app: 主窗口实例
        """
        self.parent = parent
        self.app = app
        
        # 从 app 获取共享服务
        self.device_manager = app.device_manager
        self.vision_service = app.vision_service
        self.config_manager = app.config_manager
        
        # 构建 UI
        self._build_ui()
    
    @abstractmethod
    def _build_ui(self) -> None:
        """
        构建 Tab UI（子类必须实现）
        """
        pass
    
    # ==================== 日志方法 ====================
    
    def log(self, msg: str) -> None:
        """输出到日志控制台"""
        self.app.log(msg)
    
    def log_local(self, msg: str) -> None:
        """输出到本地日志（如果有）"""
        pass  # 子类可覆盖
    
    # ==================== 设备便捷方法 ====================
    
    @property
    def device(self) -> Any:
        """获取当前设备"""
        return self.device_manager.device
    
    @property
    def phone_width(self) -> int:
        """获取手机宽度"""
        return self.device_manager.phone_width
    
    @property
    def phone_height(self) -> int:
        """获取手机高度"""
        return self.device_manager.phone_height
    
    def require_device(self) -> bool:
        """检查设备是否已连接"""
        if not self.device_manager.is_connected():
            self.log("⚠️ 请先连接设备")
            return False
        return True
    
    # ==================== 视觉便捷方法 ====================
    
    def run_ocr(self, image, **kwargs):
        """运行 OCR"""
        return self.vision_service.run_ocr(image, **kwargs)
    
    def template_match(self, image, template, **kwargs):
        """模板匹配"""
        return self.vision_service.template_match(image, template, **kwargs)
