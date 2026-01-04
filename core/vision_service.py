"""
视觉处理服务
============

封装 OCR 识别和模板匹配功能
"""

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from models.data_types import RoiPct


class VisionService:
    """
    视觉处理服务
    
    提供 OCR 文字识别和模板匹配功能
    """
    
    def __init__(self):
        self._ocr_engine: Any = None
        self._ocr_initialized = False
    
    def _init_ocr(self) -> bool:
        """延迟初始化 OCR 引擎"""
        if self._ocr_initialized:
            return self._ocr_engine is not None
        
        self._ocr_initialized = True
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr_engine = RapidOCR()
            return True
        except ImportError:
            self._ocr_engine = None
            return False
    
    @property
    def ocr_engine(self) -> Any:
        """获取 OCR 引擎（延迟初始化）"""
        if not self._ocr_initialized:
            self._init_ocr()
        return self._ocr_engine
    
    def is_ocr_available(self) -> bool:
        """检查 OCR 是否可用"""
        return self.ocr_engine is not None
    
    # ==================== 图像预处理 ====================
    
    def preprocess_for_ocr(self, bgr: np.ndarray) -> np.ndarray:
        """OCR 预处理：转灰度"""
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    
    def preprocess_for_template(self, bgr: np.ndarray, mode: str = "gray") -> np.ndarray:
        """
        模板匹配预处理
        
        Args:
            bgr: BGR 图像
            mode: 预处理模式 (gray/edge/binary)
        """
        if mode == "edge":
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            return cv2.Canny(gray, 50, 150)
        elif mode == "binary":
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            return binary
        else:
            return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    
    # ==================== OCR 识别 ====================
    
    def run_ocr(
        self,
        image: np.ndarray,
        region: Optional[RoiPct] = None,
        region_offset: Tuple[int, int] = (0, 0),
        preprocess: str = "Default",
        threshold: int = 127,
        engine: str = "PaddleOCR"
    ) -> List[Dict[str, Any]]:
        """
        运行 OCR 识别
        
        Args:
            image: BGR 图像（numpy 数组）
            region: 可选的识别区域（百分比）
            region_offset: 区域偏移（用于坐标转换）
            preprocess: 预处理模式 (Default/Grayscale/Binary/Otsu)
            threshold: 二值化阈值 (仅 Binary 模式有效)
            engine: OCR 引擎 (PaddleOCR/Tesseract)
            
        Returns:
            识别结果列表
        """
        if not self.is_ocr_available():
            return []
        
        # 1. 预处理
        img_to_proc = image
        if preprocess == "Grayscale":
            img_to_proc = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif preprocess == "Binary":
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, img_to_proc = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
        elif preprocess == "Otsu":
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, img_to_proc = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
        try:
            # 2. 引擎选择 (目前主要支持 RapidOCR/PaddleOCR，Tesseract 可扩展)
            if "Tesseract" in engine:
                # Mock Tesseract or implement if pytesseract is available
                # import pytesseract
                # text = pytesseract.image_to_string(img_to_proc, lang='chi_sim')
                # For now, fallback to RapidOCR/Paddle but log warning or implement later
                pass 

            result = self._ocr_engine(img_to_proc)
            if result is None:
                return []
            
            detections = []
            for item in result:
                if item and len(item) >= 2:
                    box = item[0]
                    text = item[1]
                    confidence = item[2] if len(item) > 2 else 1.0
                    
                    # 应用偏移
                    adjusted_box = [
                        [p[0] + region_offset[0], p[1] + region_offset[1]]
                        for p in box
                    ]
                    
                    detections.append({
                        "text": text,
                        "box": adjusted_box,
                        "confidence": confidence,
                    })
            
            return detections
            
        except Exception:
            return []
    
    def find_text(
        self,
        image: np.ndarray,
        target_text: str,
        partial_match: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        在图像中查找指定文字
        
        Args:
            image: BGR 图像
            target_text: 目标文字
            partial_match: 是否允许部分匹配
            
        Returns:
            找到的文字信息，未找到返回 None
        """
        results = self.run_ocr(image)
        
        for item in results:
            text = item.get("text", "")
            if partial_match:
                if target_text in text:
                    return item
            else:
                if target_text == text:
                    return item
        
        return None
    
    def get_all_text(self, image: np.ndarray) -> str:
        """获取图像中的所有文字（拼接）"""
        results = self.run_ocr(image)
        return " ".join(item.get("text", "") for item in results)
    
    # ==================== 模板匹配 ====================
    
    def template_match(
        self,
        image: np.ndarray,
        template: np.ndarray,
        threshold: float = 0.8,
        preprocess: str = "gray",
        scale_range: Tuple[float, float, float] = (1.0, 1.0, 0.1),
    ) -> Optional[Tuple[RoiPct, float]]:
        """
        模板匹配
        
        Args:
            image: 源图像
            template: 模板图像
            threshold: 匹配阈值
            preprocess: 预处理模式
            scale_range: 缩放范围 (min, max, step)
            
        Returns:
            (匹配的 ROI, 匹配度) 或 None
        """
        img_processed = self.preprocess_for_template(image, preprocess)
        
        best_match = None
        best_score = 0
        best_loc = None
        best_size = None
        
        scale_min, scale_max, scale_step = scale_range
        scale = scale_min
        
        while scale <= scale_max:
            # 缩放模板
            h, w = template.shape[:2]
            new_w = int(w * scale)
            new_h = int(h * scale)
            
            if new_w < 10 or new_h < 10:
                scale += scale_step
                continue
            
            scaled_template = cv2.resize(template, (new_w, new_h))
            tmpl_processed = self.preprocess_for_template(scaled_template, preprocess)
            
            # 匹配
            try:
                result = cv2.matchTemplate(img_processed, tmpl_processed, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                
                if max_val > best_score:
                    best_score = max_val
                    best_loc = max_loc
                    best_size = (new_w, new_h)
            except Exception:
                pass
            
            scale += scale_step
        
        if best_score >= threshold and best_loc and best_size:
            h, w = image.shape[:2]
            x1 = best_loc[0] / w
            y1 = best_loc[1] / h
            x2 = (best_loc[0] + best_size[0]) / w
            y2 = (best_loc[1] + best_size[1]) / h
            
            roi = RoiPct(x1=x1, y1=y1, x2=x2, y2=y2)
            return (roi, best_score)
        
        return None
    
    # ==================== 工具方法 ====================
    
    @staticmethod
    def pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
        """PIL Image 转 OpenCV BGR 格式"""
        rgb = np.array(pil_image)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    
    @staticmethod
    def cv2_to_pil(cv2_image: np.ndarray) -> Image.Image:
        """OpenCV BGR 转 PIL Image"""
        rgb = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    
    def format_ocr_result(self, results: List[Dict[str, Any]]) -> str:
        """格式化 OCR 结果为可读字符串"""
        if not results:
            return "（未识别到文字）"
        
        lines = []
        for i, item in enumerate(results, 1):
            text = item.get("text", "")
            conf = item.get("confidence", 0)
            lines.append(f"{i}. {text} ({conf:.2%})")
        
        return "\n".join(lines)
