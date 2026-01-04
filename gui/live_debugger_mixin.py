"""
Live Debugger Mixin
===================

Contains screenshot display, coordinate handling, canvas events,
and template matching methods for the Live Debug tab.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from tkinter import filedialog, messagebox

import cv2
import numpy as np
from PIL import Image, ImageTk

from core.models import RoiPct


class LiveDebuggerMixin:
    """Mixin class for Live Debugger (实时调试) functionality."""
    
    # Type hints for attributes defined in main class
    screenshot_pil: Optional[Image.Image]
    screenshot_bgr: Optional[np.ndarray]
    phone_width: int
    phone_height: int
    canvas: Any
    canvas_scale: float
    canvas_offset_x: int
    canvas_offset_y: int
    display_width: int
    display_height: int
    
    def redraw_screenshot(self) -> None:
        if self.screenshot_pil is None or self.phone_width <= 0 or self.phone_height <= 0:
            return

        canvas_w = max(1, int(self.canvas.winfo_width()))
        canvas_h = max(1, int(self.canvas.winfo_height()))

        img_ratio = self.phone_width / max(1, self.phone_height)
        canvas_ratio = canvas_w / max(1, canvas_h)

        if img_ratio > canvas_ratio:
            disp_w = canvas_w
            disp_h = int(canvas_w / img_ratio)
        else:
            disp_h = canvas_h
            disp_w = int(canvas_h * img_ratio)

        disp_w = max(1, disp_w)
        disp_h = max(1, disp_h)

        self.display_width = disp_w
        self.display_height = disp_h
        self.canvas_scale = disp_w / max(1, self.phone_width)
        self.canvas_offset_x = int((canvas_w - disp_w) / 2)
        self.canvas_offset_y = int((canvas_h - disp_h) / 2)

        resized = self.screenshot_pil.resize((disp_w, disp_h), Image.LANCZOS)
        self.tk_photo = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(
            self.canvas_offset_x,
            self.canvas_offset_y,
            image=self.tk_photo,
            anchor="nw",
            tags="screenshot",
        )

        self.draw_roi_from_entries()
        self._draw_template_match_box()
        self._draw_ocr_detections()
        self._draw_offset_calculator()

    def copy_current_coords(self) -> None:
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except Exception:
            messagebox.showwarning("提示", "坐标输入无效")
            return
        text = f"{x1:.3f}\n{y1:.3f}\n{x2:.3f}\n{y2:.3f}"
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception as e:
            messagebox.showwarning("提示", f"复制失败：\n{e}")
            self.log(f"复制失败：{e}")
            return
        messagebox.showinfo("复制成功", "已复制到剪贴板")
        self.log("已复制当前坐标到剪贴板")

    def quick_copy_coordinates(self) -> None:
        """一键复制坐标百分比值 (增强版)"""
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except Exception:
            messagebox.showwarning("提示", "坐标输入无效，请先框选区域或输入坐标值")
            return
        
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        
        quick_format = f"({x1:.3f}, {y1:.3f}) 到 ({x2:.3f}, {y2:.3f})"
        
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(quick_format)
        except Exception as e:
            messagebox.showwarning("提示", f"复制失败：\n{e}")
            self.log(f"复制失败：{e}")
            return
        
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        width_pct = x2 - x1
        height_pct = y2 - y1
        
        self.log(f"一键复制：{quick_format}")
        messagebox.showinfo(
            "一键复制成功",
            f"已复制：\n{quick_format}\n\n"
            f"区域中心: ({cx:.3f}, {cy:.3f})\n"
            f"区域尺寸: {width_pct:.3f} x {height_pct:.3f}"
        )

    def _is_point_on_image(self, cx: int, cy: int) -> bool:
        return (
            self.canvas_offset_x <= cx <= self.canvas_offset_x + self.display_width
            and self.canvas_offset_y <= cy <= self.canvas_offset_y + self.display_height
        )

    def _canvas_to_phone_px(self, cx: int, cy: int) -> Tuple[int, int]:
        x = int((cx - self.canvas_offset_x) / max(1e-6, self.canvas_scale))
        y = int((cy - self.canvas_offset_y) / max(1e-6, self.canvas_scale))
        x = int(max(0, min(self.phone_width - 1, x)))
        y = int(max(0, min(self.phone_height - 1, y)))
        return x, y

    def _phone_px_to_canvas(self, x: int, y: int) -> Tuple[int, int]:
        cx = int(self.canvas_offset_x + x * self.canvas_scale)
        cy = int(self.canvas_offset_y + y * self.canvas_scale)
        return cx, cy

    def _phone_px_to_pct(self, x: int, y: int) -> Tuple[float, float]:
        if self.phone_width <= 0 or self.phone_height <= 0:
            return 0.0, 0.0
        return float(x / self.phone_width), float(y / self.phone_height)

    def _pct_to_phone_px(self, x: float, y: float) -> Tuple[int, int]:
        x_px = int(round(x * self.phone_width))
        y_px = int(round(y * self.phone_height))
        x_px = int(max(0, min(self.phone_width - 1, x_px)))
        y_px = int(max(0, min(self.phone_height - 1, y_px)))
        return x_px, y_px

    def on_canvas_press(self, event) -> None:
        if self.screenshot_pil is None:
            return
        cx, cy = int(event.x), int(event.y)
        if not self._is_point_on_image(cx, cy):
            return
        self.rect_start_canvas = (cx, cy)
        if self.rect_id is not None:
            try:
                self.canvas.delete(self.rect_id)
            except Exception:
                pass
            self.rect_id = None
        if self.center_id is not None:
            try:
                self.canvas.delete(self.center_id)
            except Exception:
                pass
            self.center_id = None

    def on_canvas_drag(self, event) -> None:
        if self.screenshot_pil is None or self.rect_start_canvas is None:
            return
        x0, y0 = self.rect_start_canvas
        x1, y1 = int(event.x), int(event.y)
        if self.rect_id is not None:
            try:
                self.canvas.delete(self.rect_id)
            except Exception:
                pass
        self.rect_id = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="#00e5ff",
            width=2,
            tags="roi",
        )

    def on_canvas_release(self, event) -> None:
        if self.screenshot_pil is None or self.rect_start_canvas is None:
            return
        x0, y0 = self.rect_start_canvas
        x1, y1 = int(event.x), int(event.y)
        self.rect_start_canvas = None

        if not self._is_point_on_image(x0, y0) or not self._is_point_on_image(x1, y1):
            return

        x0_px, y0_px = self._canvas_to_phone_px(x0, y0)
        x1_px, y1_px = self._canvas_to_phone_px(x1, y1)

        x0_pct, y0_pct = self._phone_px_to_pct(x0_px, y0_px)
        x1_pct, y1_pct = self._phone_px_to_pct(x1_px, y1_px)

        roi = RoiPct(x1=x0_pct, y1=y0_pct, x2=x1_pct, y2=y1_pct).normalized().clipped()
        self.x1_var.set(f"{roi.x1:.3f}")
        self.y1_var.set(f"{roi.y1:.3f}")
        self.x2_var.set(f"{roi.x2:.3f}")
        self.y2_var.set(f"{roi.y2:.3f}")
        self._draw_roi(roi)
        
        x1_px_final = int(roi.x1 * self.phone_width)
        y1_px_final = int(roi.y1 * self.phone_height)
        x2_px_final = int(roi.x2 * self.phone_width)
        y2_px_final = int(roi.y2 * self.phone_height)
        
        coord_log = f"""✅ 区域坐标拾取完成

百分比坐标: [{roi.x1:.3f}, {roi.y1:.3f}, {roi.x2:.3f}, {roi.y2:.3f}]
像素坐标: [{x1_px_final}, {y1_px_final}, {x2_px_final}, {y2_px_final}]

YAML search_region 格式:
search_region:
  x1: {roi.x1:.3f}
  y1: {roi.y1:.3f}
  x2: {roi.x2:.3f}
  y2: {roi.y2:.3f}"""
        
        self.log(coord_log)
        
        if self.offset_calculator_mode and self.anchor_center is not None:
            self.target_roi = roi
            self._calculate_offset()
        
        self.log(f"已通过拖动选择区域，并同步到输入框：({roi.x1:.3f}, {roi.y1:.3f}) 到 ({roi.x2:.3f}, {roi.y2:.3f})")

    def test_click_center(self) -> None:
        if not self.require_device():
            return
        roi = self._get_entries_roi()
        if roi is None:
            messagebox.showwarning("提示", "坐标输入无效")
            return
        cx, cy = roi.center()
        x_px, y_px = self._pct_to_phone_px(cx, cy)
        try:
            self.device.click(x_px, y_px)
            self.log(f"测试点击：({x_px}, {y_px})，中心：({cx:.3f}, {cy:.3f})")
        except Exception as e:
            messagebox.showerror("点击失败", f"点击失败：\n{e}")
            self.log(f"点击失败：{e}")
