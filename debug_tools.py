
import logging
import base64
import time
from adbutils import adb
from rapidocr_onnxruntime import RapidOCR
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("DebugTool")

def test_clipboard_commands():
    logger.info("--- 📋 Clipboard Command Test ---")
    text = "测试测试 中文、@"
    text_b64 = base64.b64encode(text.encode('utf-8')).decode('utf-8')
    logger.info(f"Target Text: {text}")
    logger.info(f"Target Base64: {text_b64}")
    
    device = adb.device()
    
    cmds = [
        # 1. Simple
        f"su -c '/system/bin/set_clip -b \"{text_b64}\"'",
        # 2. With SH
        f"su -c 'sh /system/bin/set_clip -b \"{text_b64}\"'",
        # 3. With LANG (The one we think works)
        f"su -c 'export LANG=en_US.UTF-8; /system/bin/set_clip -b \"{text_b64}\"'",
        # 4. Raw App Process
        (
            f"su -c '"
            f"export CLASSPATH=/system/framework/clip.dex; "
            f"export LANG=en_US.UTF-8; "
            f"TEXT=$(echo \"{text_b64}\" | base64 -d); "
            f"app_process /system/bin SetClip \"$TEXT\""
            f"'"
        )
    ]
    
    for i, cmd in enumerate(cmds, 1):
        logger.info(f"\n[Command {i}]")
        logger.info(f"Cmd: {cmd}")
        try:
            output = device.shell(cmd + " 2>&1")
            logger.info(f"Output: {output}")
        except Exception as e:
            logger.error(f"Error: {e}")

def test_ocr_structure():
    logger.info("\n--- 👁️ OCR Structure Test ---")
    device = adb.device()
    
    # Get screenshot
    pil_img = device.screenshot()
    img_np = np.array(pil_img)
    
    ocr = RapidOCR()
    result, _ = ocr(img_np)
    
    if result:
        logger.info(f"Result Type: {type(result)}")
        logger.info(f"Result Len: {len(result)}")
        first_item = result[0]
        logger.info(f"First Item Type: {type(first_item)}")
        logger.info(f"First Item Raw: {first_item}")
        
        if isinstance(first_item, (list, tuple)):
            for idx, sub in enumerate(first_item):
                logger.info(f"  Index {idx}: {type(sub)} -> {sub}")
    else:
        logger.info("No text detected on screen.")

if __name__ == "__main__":
    try:
        test_clipboard_commands()
        test_ocr_structure()
    except Exception as e:
        logger.error(f"Global Crash: {e}")
