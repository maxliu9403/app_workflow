"""
Device Management Mixin
=======================

Contains device connection, screenshot capture, and resolution management.
"""

import re
from typing import Any, Optional, Tuple
from tkinter import messagebox

import cv2
import numpy as np
from PIL import Image
from adbutils import adb
from adbutils.errors import AdbError


class DeviceMixin:
    """Mixin class for device management functionality."""
    
    # These attributes are defined in the main class __init__
    device: Any
    phone_width: int
    phone_height: int
    screenshot_pil: Optional[Image.Image]
    screenshot_bgr: Optional[np.ndarray]
    
    def refresh_device_list(self) -> None:
        try:
            devices = adb.device_list()
            serials = [d.serial for d in devices]
        except Exception as e:
            serials = []
            self.log(f"获取设备列表失败：{e}")

        if not serials:
            self.device_combo.configure(values=[""])
            self.selected_serial_var.set("")
            self.status_label.configure(text="状态：未检测到设备", text_color="#aaaaaa")
            return

        self.device_combo.configure(values=serials)
        if self.selected_serial_var.get() not in serials:
            self.selected_serial_var.set(serials[0])
        self.status_label.configure(text="状态：已检测到设备，请选择并连接", text_color="#aaaaaa")

    def on_device_selected(self) -> None:
        if self.device is not None:
            self.status_label.configure(text="状态：已连接（切换设备需先断开）", text_color="#f0ad4e")

    def connect_selected_device(self) -> None:
        serial = (self.selected_serial_var.get() or "").strip()
        if not serial:
            messagebox.showwarning("提示", "请先选择设备序列号")
            return
        try:
            self.device = adb.device(serial=serial)
            self._update_device_resolution()
            self.status_label.configure(
                text=f"状态：已连接 {serial}（{self.phone_width}x{self.phone_height}）",
                text_color="#66cc66",
            )
            self.log(f"已连接设备：{serial}")
        except AdbError as e:
            self.device = None
            self.status_label.configure(text="状态：连接失败", text_color="#ff6666")
            messagebox.showerror("连接失败", f"连接设备失败：\n{e}")
            self.log(f"连接设备失败：{e}")

    def disconnect_device(self) -> None:
        self.device = None
        self.phone_width = 0
        self.phone_height = 0
        self.screenshot_pil = None
        self.screenshot_bgr = None
        self.tk_photo = None
        self.template_match_roi = None
        self.template_bgr = None
        self.template_path = None
        self.template_rect_id = None
        if hasattr(self, "template_path_label"):
            try:
                self.template_path_label.configure(text="未选择")
            except Exception:
                pass
        self.canvas.delete("all")
        self.canvas.create_text(
            50,
            50,
            text="请先选择设备并连接，然后获取截图",
            fill="#9a9a9a",
            anchor="nw",
            font=("Arial", 14),
            tags="placeholder",
        )
        self.status_label.configure(text="状态：未连接", text_color="#aaaaaa")
        self.log("已断开设备")

    def _update_device_resolution(self) -> None:
        if self.device is None:
            return
        try:
            wm_size = self.device.shell("wm size")
            m = re.search(r"(\d+)x(\d+)", wm_size)
            if not m:
                raise ValueError("无法解析分辨率")
            self.phone_width = int(m.group(1))
            self.phone_height = int(m.group(2))
        except Exception as e:
            raise AdbError(f"获取分辨率失败：{e}")

    def require_device(self) -> bool:
        if self.device is None:
            messagebox.showwarning("提示", "请先选择设备并点击连接")
            return False
        return True

    def refresh_screenshot(self) -> None:
        if not self.require_device():
            return
        try:
            self._update_device_resolution()
            img = self.device.screenshot()
            self.screenshot_pil = img
            rgb = np.array(img)
            if rgb.ndim == 3 and rgb.shape[2] == 3:
                self.screenshot_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            else:
                self.screenshot_bgr = rgb
            self.redraw_screenshot()
            self.log("截图获取成功")
        except AdbError as e:
            messagebox.showerror("截图失败", f"截图失败：\n{e}")
            self.log(f"截图失败：{e}")
        except Exception as e:
            messagebox.showerror("截图失败", f"截图失败：\n{e}")
            self.log(f"截图失败：{e}")
