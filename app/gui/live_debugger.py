import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
import numpy as np
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from app.core.context import SharedContext
from app.core.models import RoiPct
from adbutils.errors import AdbError

class LiveDebuggerFrame(ctk.CTkFrame):
    def __init__(self, master, ctx: SharedContext, **kwargs):
        super().__init__(master, **kwargs)
        self.ctx = ctx
        
        # Local state for UI interactions
        self.rect_start_canvas: Optional[Tuple[int, int]] = None
        self.rect_id: Optional[int] = None
        self.center_id: Optional[int] = None
        self.template_rect_id: Optional[int] = None
        
        self.canvas_scale: float = 1.0
        self.canvas_offset_x: int = 0
        self.canvas_offset_y: int = 0
        
        # OCR / Template state
        self.ocr_detections: List[Dict[str, Any]] = []
        self.ocr_rect_ids: List[int] = []
        self.ocr_text_ids: List[int] = []
        
        self.template_path: Optional[Path] = None
        self.template_bgr: Optional[np.ndarray] = None
        self.template_match_roi: Optional[RoiPct] = None
        
        # Offset Calculator State
        self.offset_calculator_mode: bool = False
        self.anchor_center: Optional[Tuple[float, float]] = None
        self.anchor_text_content: str = ""
        self.target_roi: Optional[RoiPct] = None
        self.anchor_rect_id: Optional[int] = None
        self.anchor_text_id: Optional[int] = None
        self.target_rect_id: Optional[int] = None
        self.target_text_id: Optional[int] = None
        self.target_line_id: Optional[int] = None

        # UI Variables
        self.x1_var = ctk.StringVar(value="0.000")
        self.y1_var = ctk.StringVar(value="0.000")
        self.x2_var = ctk.StringVar(value="0.000")
        self.y2_var = ctk.StringVar(value="0.000")
        self.paste_var = ctk.StringVar(value="")
        
        self.template_threshold_var = ctk.StringVar(value="0.80")
        self.template_scope_var = ctk.StringVar(value="全屏")
        self.template_sync_var = ctk.BooleanVar(value=True)
        self.template_scale_min_var = ctk.StringVar(value="0.70")
        self.template_scale_max_var = ctk.StringVar(value="1.30")
        self.template_scale_step_var = ctk.StringVar(value="0.05")
        self.template_preprocess_var = ctk.StringVar(value="灰度")
        self.ocr_target_text_var = ctk.StringVar(value="")

        self._build_ui()
        
        # Bind var changes
        for var in (self.x1_var, self.y1_var, self.x2_var, self.y2_var):
            var.trace_add("write", lambda *_args: self.schedule_draw_from_entries())
            
        self.entry_update_job = None

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=2)   # Left: Controls
        self.grid_columnconfigure(1, weight=5)   # Center: Canvas
        
        # === Left: Control Panel ===
        self.control_panel = ctk.CTkScrollableFrame(self)
        self.control_panel.grid(row=0, column=0, sticky="nsew", padx=(5, 5), pady=5)
        self.control_panel.grid_columnconfigure(0, weight=1)
        
        # 1. Coordinates
        coord_frame = ctk.CTkFrame(self.control_panel)
        coord_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        coord_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(coord_frame, text="坐标管理 (0.0-1.0)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=5)
        
        self._make_labeled_entry(coord_frame, "左上X", self.x1_var, 1, 0)
        self._make_labeled_entry(coord_frame, "左上Y", self.y1_var, 1, 2)
        self._make_labeled_entry(coord_frame, "右下X", self.x2_var, 2, 0)
        self._make_labeled_entry(coord_frame, "右下Y", self.y2_var, 2, 2)
        
        # Paste logic
        ctk.CTkLabel(coord_frame, text="快速粘贴:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.paste_entry = ctk.CTkEntry(coord_frame, textvariable=self.paste_var, placeholder_text="(0.1, 0.2) 到 (0.3, 0.4)")
        self.paste_entry.grid(row=3, column=1, columnspan=3, sticky="ew", padx=5, pady=5)
        self.paste_entry.bind("<Return>", lambda _e: self.parse_quick_paste())
        
        ctk.CTkButton(coord_frame, text="解析并填充", command=self.parse_quick_paste).grid(row=4, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        
        # Quick Copy Buttons
        copy_frame = ctk.CTkFrame(coord_frame, fg_color="transparent")
        copy_frame.grid(row=5, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        copy_frame.grid_columnconfigure((0,1), weight=1)
        
        ctk.CTkButton(copy_frame, text="📋 一键复制", fg_color="#ff6b35", width=80, command=self.quick_copy_coordinates).grid(row=0, column=0, padx=2, sticky="ew")
        ctk.CTkButton(copy_frame, text="📝 YAML", fg_color="#4ecdc4", width=80, command=self.copy_yaml_format).grid(row=0, column=1, padx=2, sticky="ew")

        # 2. Actions
        action_frame = ctk.CTkFrame(self.control_panel)
        action_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        action_frame.grid_columnconfigure((0,1), weight=1)
        
        ctk.CTkLabel(action_frame, text="动作测试", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        ctk.CTkButton(action_frame, text="获取截图", command=self.refresh_screenshot).grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(action_frame, text="测试点击(中心)", fg_color="#8b4513", command=self.test_click_center).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(action_frame, text="测试OCR(区域)", fg_color="#2d7a3e", command=self.test_ocr_roi).grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        # 3. Text Tools & Offset Calculator
        text_frame = ctk.CTkFrame(self.control_panel)
        text_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        text_frame.grid_columnconfigure((0,1), weight=1)
        
        ctk.CTkLabel(text_frame, text="文字工具 & 偏移", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ctk.CTkButton(text_frame, text="提取区域文字(复制)", fg_color="#6a5acd", command=self.extract_roi_text_copy).grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(text_frame, text="提取区域文字(显示)", fg_color="#5b728c", command=self.extract_roi_text_show).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        ctk.CTkButton(text_frame, text="🎯 偏移计算器", fg_color="#ff00ff", command=self.start_offset_calculator).grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(text_frame, text="清除标记", fg_color="#555", command=self.clear_offset_calculator).grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        # 4. Template Match
        tpl_frame = ctk.CTkFrame(self.control_panel)
        tpl_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        tpl_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(tpl_frame, text="模板匹配", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        
        self.tpl_path_label = ctk.CTkLabel(tpl_frame, text="未选择", text_color="gray")
        self.tpl_path_label.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        ctk.CTkButton(tpl_frame, text="选择图片", command=self.choose_template_image).grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        ctk.CTkButton(tpl_frame, text="清除匹配", fg_color="#555", command=self.clear_template_match).grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        ctk.CTkButton(tpl_frame, text="开始匹配", fg_color="#d63031", command=self.run_template_match).grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        # === Center: Canvas ===
        canvas_container = ctk.CTkFrame(self)
        canvas_container.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        canvas_container.grid_rowconfigure(0, weight=1)
        canvas_container.grid_columnconfigure(0, weight=1)
        
        self.canvas = tk.Canvas(canvas_container, bg="#1f1f1f", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # Bindings
        self.canvas.bind("<Button-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Configure>", lambda _e: self.redraw_screenshot())
        
        self.canvas.create_text(
            50, 50, text="请连接设备并获取截图", fill="#999", font=("Arial", 14), anchor="nw", tags="placeholder"
        )

    def _make_labeled_entry(self, parent, label, var, row, col):
        ctk.CTkLabel(parent, text=f"{label}:").grid(row=row, column=col, sticky="w", padx=5, pady=2)
        ctk.CTkEntry(parent, textvariable=var, width=80).grid(row=row, column=col+1, sticky="ew", padx=5, pady=2)

    def refresh_screenshot(self):
        if not self.ctx.device:
            messagebox.showwarning("提示", "未连接设备")
            return
        
        try:
            # Update resolution
            wm_size = self.ctx.device.shell("wm size")
            m = re.search(r"(\d+)x(\d+)", wm_size)
            if m:
                self.ctx.phone_width = int(m.group(1))
                self.ctx.phone_height = int(m.group(2))
            
            # Capture
            pil_img = self.ctx.device.screenshot()
            rgb = np.array(pil_img)
            bgr = None
            if rgb.ndim == 3 and rgb.shape[2] == 3:
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            else:
                bgr = rgb
                
            self.ctx.update_screenshot(pil_img, bgr)
            self.redraw_screenshot()
            
        except Exception as e:
            messagebox.showerror("截图失败", str(e))

    def redraw_screenshot(self):
        if not self.ctx.screenshot_pil:
            return
            
        # Calc layout
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10: return
        
        img_w, img_h = self.ctx.screenshot_pil.size
        ratio_img = img_w / img_h
        ratio_canvas = canvas_w / canvas_h
        
        if ratio_img > ratio_canvas:
            disp_w = canvas_w
            disp_h = int(canvas_w / ratio_img)
        else:
            disp_h = canvas_h
            disp_w = int(canvas_h * ratio_img)
            
        self.ctx.display_width = disp_w
        self.ctx.display_height = disp_h
        self.canvas_scale = disp_w / max(1, img_w)
        
        self.canvas_offset_x = (canvas_w - disp_w) // 2
        self.canvas_offset_y = (canvas_h - disp_h) // 2
        
        # Resize
        resized = self.ctx.screenshot_pil.resize((disp_w, disp_h), Image.LANCZOS)
        self.ctx.screenshot_tk = ImageTk.PhotoImage(resized)
        
        self.canvas.delete("all")
        self.canvas.create_image(
            self.canvas_offset_x, self.canvas_offset_y,
            image=self.ctx.screenshot_tk, anchor="nw"
        )
        
        self.draw_roi_from_entries()
        self._draw_template_match_box()
        self._draw_ocr_detections()
        self._draw_offset_calculator()

    def on_canvas_press(self, event):
        if not self.ctx.screenshot_pil: return
        if not self._is_point_on_image(event.x, event.y): return
        
        self.rect_start_canvas = (event.x, event.y)
        self.canvas.delete("roi")

    def on_canvas_drag(self, event):
        if not self.rect_start_canvas: return
        self.canvas.delete("roi")
        self.canvas.create_rectangle(
            self.rect_start_canvas[0], self.rect_start_canvas[1],
            event.x, event.y,
            outline="cyan", width=2, tags="roi"
        )
    
    def on_canvas_release(self, event):
        if not self.rect_start_canvas: return
        x0, y0 = self.rect_start_canvas
        x1, y1 = event.x, event.y
        self.rect_start_canvas = None
        
        # Convert to PCT
        px0, py0 = self._canvas_to_phone(x0, y0)
        px1, py1 = self._canvas_to_phone(x1, y1)
        
        pct0 = self._phone_to_pct(px0, py0)
        pct1 = self._phone_to_pct(px1, py1)
        
        roi = RoiPct(x1=pct0[0], y1=pct0[1], x2=pct1[0], y2=pct1[1]).normalized().clipped()
        
        # Feature: Offset Calculator interaction
        if self.offset_calculator_mode:
            if self.anchor_center is None:
                messagebox.showinfo("Offset Calculator", "请先设置锚点A（通过OCR匹配）")
                return
            else:
                self.target_roi = roi
                self.x1_var.set(f"{roi.x1:.3f}")
                self.y1_var.set(f"{roi.y1:.3f}")
                self.x2_var.set(f"{roi.x2:.3f}")
                self.y2_var.set(f"{roi.y2:.3f}")
                self._calculate_offset()
            return
            
        self.x1_var.set(f"{roi.x1:.3f}")
        self.y1_var.set(f"{roi.y1:.3f}")
        self.x2_var.set(f"{roi.x2:.3f}")
        self.y2_var.set(f"{roi.y2:.3f}")
        self.draw_roi_from_entries()

    def _is_point_on_image(self, cx, cy):
        ox, oy = self.canvas_offset_x, self.canvas_offset_y
        dw, dh = self.ctx.display_width, self.ctx.display_height
        return ox <= cx <= ox + dw and oy <= cy <= oy + dh

    def _canvas_to_phone(self, cx, cy):
        ox, oy = self.canvas_offset_x, self.canvas_offset_y
        rel_x = cx - ox
        rel_y = cy - oy
        px = int(rel_x / self.canvas_scale)
        py = int(rel_y / self.canvas_scale)
        return px, py

    def _phone_to_pct(self, px, py):
        w, h = self.ctx.phone_width, self.ctx.phone_height
        if w == 0 or h == 0: return 0.0, 0.0
        return px/w, py/h

    def _pct_to_phone(self, pct_x, pct_y):
        w, h = self.ctx.phone_width, self.ctx.phone_height
        return int(pct_x * w), int(pct_y * h)
        
    def _phone_to_canvas(self, px, py):
        cx = int(px * self.canvas_scale) + self.canvas_offset_x
        cy = int(py * self.canvas_scale) + self.canvas_offset_y
        return cx, cy

    def schedule_draw_from_entries(self):
        if self.entry_update_job:
            self.after_cancel(self.entry_update_job)
        self.entry_update_job = self.after(100, self.draw_roi_from_entries)

    def draw_roi_from_entries(self):
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except:
            return
            
        self.canvas.delete("roi", "roi_center")
        
        roi = RoiPct(x1, y1, x2, y2).normalized().clipped()
        px1, py1 = self._pct_to_phone(roi.x1, roi.y1)
        px2, py2 = self._pct_to_phone(roi.x2, roi.y2)
        cx1, cy1 = self._phone_to_canvas(px1, py1)
        cx2, cy2 = self._phone_to_canvas(px2, py2)
        
        self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="cyan", width=2, tags="roi")
        
        # Center
        ccx = (cx1 + cx2) // 2
        ccy = (cy1 + cy2) // 2
        self.canvas.create_oval(ccx-3, ccy-3, ccx+3, ccy+3, outline="yellow", width=2, tags="roi_center")

    def parse_quick_paste(self):
        txt = self.paste_var.get()
        nums = re.findall(r"[\d\.]+", txt)
        if len(nums) >= 4:
            self.x1_var.set(nums[0])
            self.y1_var.set(nums[1])
            self.x2_var.set(nums[2])
            self.y2_var.set(nums[3])
            
    def quick_copy_coordinates(self):
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except:
             return
        
        # Ensure x1 < x2 etc
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        
        txt = f"({x1:.3f}, {y1:.3f}) 到 ({x2:.3f}, {y2:.3f})"
        self.clipboard_clear()
        self.clipboard_append(txt)
        messagebox.showinfo("Copied", txt)
        
    def copy_yaml_format(self):
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except:
             return
             
        txt = f"x_min: {x1:.3f}\ny_min: {y1:.3f}\nx_max: {x2:.3f}\ny_max: {y2:.3f}"
        self.clipboard_clear()
        self.clipboard_append(txt)
        messagebox.showinfo("YAML Copied", "YAML format copied to clipboard")

    def test_click_center(self):
        if not self.ctx.device: return
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            px, py = self._pct_to_phone(cx, cy)
            self.ctx.device.click(px, py)
        except Exception as e:
            messagebox.showerror("Err", str(e))
            
    # === OCR & Text Tools ===
    
    def _ensure_ocr(self):
        if self.ctx.ocr_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self.ctx.ocr_engine = RapidOCR()
            except ImportError:
                messagebox.showerror("Error", "rapidocr_onnxruntime module missing")
                return False
        return True

    def _run_ocr(self, bgr, offset=(0,0)):
        if not self._ensure_ocr(): return [], []
        
        # Preprocess
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        # Resize x2 for better accuracy on small text
        up = cv2.resize(gray, (gray.shape[1] * 2, gray.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
        _, thr = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        result = self.ctx.ocr_engine(thr)
        if not result: return [], []
        
        # Handle format
        detections = result[0] if isinstance(result, tuple) else result
        if not detections: return [], []
        
        texts = []
        data = []
        xo, yo = offset
        for item in detections:
            if len(item) < 2: continue
            bbox = item[0]
            text = item[1]
            if not text: continue
            
            texts.append(text)
            
            # Map back to original image coords
            if bbox:
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                # Divide by 2 (resize) + offset
                x1 = int(min(xs)/2) + xo
                y1 = int(min(ys)/2) + yo
                x2 = int(max(xs)/2) + xo
                y2 = int(max(ys)/2) + yo
                data.append({"bbox": (x1,y1,x2,y2), "text": text})
                
        return texts, data

    def extract_roi_text_copy(self):
        self._extract_text(start_offset_calc=False, copy_mode=True, show_mode=False)

    def extract_roi_text_show(self):
        self._extract_text(start_offset_calc=False, copy_mode=False, show_mode=True)
        
    def test_ocr_roi(self):
        # Same as extract show but maybe just logging
        self._extract_text(start_offset_calc=False, copy_mode=False, show_mode=True)

    def _extract_text(self, start_offset_calc=False, copy_mode=False, show_mode=True):
        if self.ctx.screenshot_bgr is None: return
        
        try:
            x1 = float(self.x1_var.get())
            y1 = float(self.y1_var.get())
            x2 = float(self.x2_var.get())
            y2 = float(self.y2_var.get())
        except:
            return
            
        px1, py1 = self._pct_to_phone(x1, y1)
        px2, py2 = self._pct_to_phone(x2, y2)
        
        # Clip
        h, w = self.ctx.screenshot_bgr.shape[:2]
        px1, py1 = max(0, px1), max(0, py1)
        px2, py2 = min(w, px2), min(h, py2)
        
        if px2<=px1 or py2<=py1: return
        
        crop = self.ctx.screenshot_bgr[py1:py2, px1:px2]
        lines, data = self._run_ocr(crop, offset=(px1, py1))
        
        self.ocr_detections = data
        self.redraw_screenshot()
        
        full_text = "\n".join(lines)
        if copy_mode:
            self.clipboard_clear()
            self.clipboard_append(full_text)
            messagebox.showinfo("Result", "Text copied to clipboard")
        elif show_mode:
            messagebox.showinfo("OCR Result", full_text if full_text else "No text found")

        if start_offset_calc and data:
            # Auto set first detection as anchor if requested (simplified logic)
            pass

    def _draw_ocr_detections(self):
        if not self.ctx.screenshot_pil: return
        
        self.canvas.delete("ocr_rect", "ocr_text")
        
        for item in self.ocr_detections:
            x1, y1, x2, y2 = item['bbox']
            text = item['text']
            
            c1x, c1y = self._phone_to_canvas(x1, y1)
            c2x, c2y = self._phone_to_canvas(x2, y2)
            
            self.canvas.create_rectangle(c1x, c1y, c2x, c2y, outline="red", width=1, tags="ocr_rect")
            self.canvas.create_text(c1x, c1y-10, text=text, fill="red", anchor="w", font=("Arial", 8), tags="ocr_text")

    # === Template Matching ===

    def choose_template_image(self):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if p:
            self.template_path = Path(p)
            self.tpl_path_label.configure(text=self.template_path.name)
            
            # Load BGR
            pil = Image.open(p)
            rgb = np.array(pil)
            if rgb.ndim == 3:
                self.template_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            else:
                self.template_bgr = cv2.cvtColor(rgb, cv2.COLOR_GRAY2BGR)
                
            self.clear_template_match()

    def clear_template_match(self):
        self.template_match_roi = None
        self.redraw_screenshot()
        
    def run_template_match(self):
        if self.ctx.screenshot_bgr is None or self.template_bgr is None:
            return
            
        try:
            threshold = float(self.template_threshold_var.get())
            s_min = float(self.template_scale_min_var.get())
            s_max = float(self.template_scale_max_var.get())
            s_step = float(self.template_scale_step_var.get())
        except:
            return
            
        # Simplified Multi-Scale Template Matching
        gray_screen = cv2.cvtColor(self.ctx.screenshot_bgr, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(self.template_bgr, cv2.COLOR_BGR2GRAY)
        
        best_val = -1
        best_roi = None
        
        for scale in np.arange(s_min, s_max+0.01, s_step):
            w = int(tpl_gray.shape[1] * scale)
            h = int(tpl_gray.shape[0] * scale)
            if w==0 or h==0: continue
            if w > gray_screen.shape[1] or h > gray_screen.shape[0]: continue
            
            resized = cv2.resize(tpl_gray, (w, h))
            res = cv2.matchTemplate(gray_screen, resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            if max_val > best_val:
                best_val = max_val
                best_roi = (max_loc[0], max_loc[1], w, h)
                
        if best_val >= threshold and best_roi:
            x, y, w, h = best_roi
            px1, py1 = x, y
            px2, py2 = x+w, y+h
            
            roi = RoiPct(
                *self._phone_to_pct(px1, py1),
                *self._phone_to_pct(px2, py2)
            ).normalized().clipped()
            
            self.template_match_roi = roi
            
            if self.template_sync_var.get():
                self.x1_var.set(f"{roi.x1:.3f}")
                self.y1_var.set(f"{roi.y1:.3f}")
                self.x2_var.set(f"{roi.x2:.3f}")
                self.y2_var.set(f"{roi.y2:.3f}")
                self.draw_roi_from_entries()
                
            self.redraw_screenshot()
            messagebox.showinfo("Match", f"Found! Score: {best_val:.2f}")
        else:
            messagebox.showinfo("Match", f"Not found. Best: {best_val:.2f}")

    def _draw_template_match_box(self):
        if self.template_match_roi is None: return
        roi = self.template_match_roi
        px1, py1 = self._pct_to_phone(roi.x1, roi.y1)
        px2, py2 = self._pct_to_phone(roi.x2, roi.y2)
        cx1, cy1 = self._phone_to_canvas(px1, py1)
        cx2, cy2 = self._phone_to_canvas(px2, py2)
        
        self.canvas.delete("tpl_match")
        self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="#ff4dff", width=2, tags="tpl_match")

    # === Offset Calculator ===
    
    def start_offset_calculator(self):
        if self.ctx.screenshot_bgr is None: return
        self.offset_calculator_mode = True
        self.anchor_center = None
        self.target_roi = None
        messagebox.showinfo("Offset Calc", "Mode Started.\n1. Run OCR/Match to set Anchor A.\n2. Drag selection for Target B.")
        
    def clear_offset_calculator(self):
        self.offset_calculator_mode = False
        self.anchor_center = None
        self.target_roi = None
        self.redraw_screenshot()
        
    def _calculate_offset(self):
        if not self.anchor_center or not self.target_roi: return
        
        ax_pct, ay_pct = self.anchor_center
        ax_px, ay_px = self._pct_to_phone(ax_pct, ay_pct)
        
        bx_pct, by_pct = self.target_roi.center()
        bx_px, by_px = self._pct_to_phone(bx_pct, by_pct)
        
        off_x = bx_px - ax_px
        off_y = by_px - ay_px
        
        yaml_out = f"""
# Offset Config
anchor_text: "{self.anchor_text_content}"
target_center: [{bx_pct:.3f}, {by_pct:.3f}]
offset_from_anchor: [{off_x}, {off_y}]
"""
        messagebox.showinfo("Offset Result", yaml_out)
        self.redraw_screenshot()

    def _draw_offset_calculator(self):
        self.canvas.delete("offset_line")
        
        if self.anchor_center:
            ax, ay = self.anchor_center
            apx, apy = self._pct_to_phone(ax, ay)
            acx, acy = self._phone_to_canvas(apx, apy)
            
            self.canvas.create_oval(acx-5, acy-5, acx+5, acy+5, fill="red", tags="offset_line")
            self.canvas.create_text(acx, acy-15, text="A", fill="red", tags="offset_line")
            
            if self.target_roi:
                 bx, by = self.target_roi.center()
                 bpx, bpy = self._pct_to_phone(bx, by)
                 bcx, bcy = self._phone_to_canvas(bpx, bpy)
                 
                 self.canvas.create_line(acx, acy, bcx, bcy, fill="yellow", dash=(4,2), tags="offset_line")
