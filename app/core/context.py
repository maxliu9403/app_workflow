from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Tuple
from PIL import Image, ImageTk
from adbutils import adb
from pathlib import Path
import numpy as np

class SharedContext:
    def __init__(self):
        self.adb_client = adb
        self.device: Any = None
        self.selected_serial: str = ""
        
        # Custom Excel Path
        self.excel_path: Optional[str] = None

        # Screenshot Cache
        self.screenshot_pil: Optional[Image.Image] = None
        self.screenshot_bgr: Any = None # numpy array
        self.screenshot_tk: Optional[ImageTk.PhotoImage] = None
        self.phone_width: int = 0
        self.phone_height: int = 0
        self.display_width: int = 0
        self.display_height: int = 0
        self.canvas_scale: float = 1.0
        self.canvas_offset_x: int = 0
        self.canvas_offset_y: int = 0
        
        # Configuration
        self.config: Dict[str, Any] = {}
        self.yaml_path: Optional[Path] = None
        
        # Global Settings
        self.template_threshold: float = 0.8
        
        # Extension Manager Reference
        self.ext_manager: Any = None
        
        # OCR Engine (Shared if needed)
        self.ocr_engine: Any = None

    def update_screenshot(self, pil_image: Image.Image, bgr_image: Any = None):
        self.screenshot_pil = pil_image
        self.screenshot_bgr = bgr_image
        self.display_width = pil_image.width
        self.display_height = pil_image.height
