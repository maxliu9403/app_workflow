"""
设备管理器
==========

封装所有 ADB 设备操作
"""

import re
from typing import Any, List, Optional, Tuple

from PIL import Image

try:
    from adbutils import adb
    from adbutils.errors import AdbError
except ImportError:
    adb = None
    AdbError = Exception

from models.constants import DEFAULT_PHONE_WIDTH, DEFAULT_PHONE_HEIGHT


class DeviceManager:
    """
    ADB 设备管理器
    
    封装设备连接、截图、点击等操作
    """
    
    def __init__(self):
        self.device: Any = None
        self.phone_width: int = DEFAULT_PHONE_WIDTH
        self.phone_height: int = DEFAULT_PHONE_HEIGHT
        self._on_status_change = None  # 状态变化回调
    
    def set_status_callback(self, callback):
        """设置状态变化回调"""
        self._on_status_change = callback
    
    def _notify_status(self, connected: bool, message: str):
        """通知状态变化"""
        if self._on_status_change:
            self._on_status_change(connected, message)
    
    def list_devices(self) -> List[str]:
        """获取已连接的设备列表"""
        if adb is None:
            return []
        try:
            devices = adb.device_list()
            return [d.serial for d in devices]
        except Exception:
            return []
    
    def connect(self, serial: str) -> bool:
        """
        连接到指定设备
        
        Args:
            serial: 设备序列号
            
        Returns:
            bool: 连接成功返回 True
        """
        if adb is None:
            self._notify_status(False, "adbutils 未安装")
            return False
        
        try:
            self.device = adb.device(serial=serial)
            self._update_resolution()
            self._notify_status(True, f"已连接: {serial}")
            return True
        except AdbError as e:
            self._notify_status(False, f"连接失败: {e}")
            return False
        except Exception as e:
            self._notify_status(False, f"连接失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开设备连接"""
        self.device = None
        self.phone_width = DEFAULT_PHONE_WIDTH
        self.phone_height = DEFAULT_PHONE_HEIGHT
        self._notify_status(False, "已断开")
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.device is not None
    
    def _update_resolution(self) -> None:
        """自动获取屏幕分辨率"""
        if not self.device:
            return
        try:
            output = self.device.shell("wm size")
            match = re.search(r"(\d+)x(\d+)", output)
            if match:
                self.phone_width = int(match.group(1))
                self.phone_height = int(match.group(2))
        except Exception:
            pass
    
    def screenshot(self) -> Optional[Image.Image]:
        """
        获取设备截图
        
        Returns:
            PIL Image 对象，失败返回 None
        """
        if not self.device:
            return None
        try:
            return self.device.screenshot()
        except Exception:
            return None
    
    def click(self, x: int, y: int) -> bool:
        """
        点击指定坐标
        
        Args:
            x, y: 像素坐标
            
        Returns:
            bool: 成功返回 True
        """
        if not self.device:
            return False
        try:
            self.device.click(x, y)
            return True
        except Exception:
            return False
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> bool:
        """
        滑动操作
        
        Args:
            x1, y1: 起点坐标
            x2, y2: 终点坐标
            duration: 持续时间（秒）
            
        Returns:
            bool: 成功返回 True
        """
        if not self.device:
            return False
        try:
            self.device.swipe(x1, y1, x2, y2, duration)
            return True
        except Exception:
            return False
    
    def long_press(self, x: int, y: int, duration: float = 1.0) -> bool:
        """长按操作"""
        return self.swipe(x, y, x, y, duration)
    
    def input_text(self, text: str) -> bool:
        """
        输入文本
        
        Args:
            text: 要输入的文本
            
        Returns:
            bool: 成功返回 True
        """
        if not self.device:
            return False
        try:
            escaped = text.replace(" ", "%s").replace("&", "\\&")
            self.device.shell(f"input text '{escaped}'")
            return True
        except Exception:
            return False
    
    def shell(self, command: str) -> str:
        """执行 shell 命令"""
        if not self.device:
            return ""
        try:
            return self.device.shell(command)
        except Exception:
            return ""
    
    # ==================== 坐标转换工具 ====================
    
    def pct_to_px(self, x: float, y: float) -> Tuple[int, int]:
        """百分比坐标转像素坐标"""
        return (int(x * self.phone_width), int(y * self.phone_height))
    
    def px_to_pct(self, x: int, y: int) -> Tuple[float, float]:
        """像素坐标转百分比坐标"""
        if self.phone_width == 0 or self.phone_height == 0:
            return (0.0, 0.0)
        return (x / self.phone_width, y / self.phone_height)
    
    def get_resolution(self) -> Tuple[int, int]:
        """获取当前分辨率"""
        return (self.phone_width, self.phone_height)
