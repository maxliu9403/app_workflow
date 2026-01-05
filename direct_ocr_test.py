
from adbutils import adb
from workflow_runner import WorkflowRunner
import logging
import time

# Setup logging to console
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DirectTest")

def main():
    logger.info("🚀 Starting Direct OCR Test...")
    
    try:
        device = adb.device()
        logger.info(f"📱 Connected: {device.serial}")
    except Exception as e:
        logger.error(f"❌ No device: {e}")
        return

    runner = WorkflowRunner(device)
    
    # 1. Test Screenshot Type Log
    logger.info("📸 Testing _get_screenshot_for_ocr type...")
    img = runner._get_screenshot_for_ocr()
    logger.info(f"👉 Returned Image Type: {type(img)}")
    
    # 2. Test Check Text
    logger.info("🔍 Testing _action_check_text...")
    step = {
        "action_type": "Check Text",
        "params": "op:Contains|Settings" # Common text
    }
    result = runner._action_check_text(step, {})
    logger.info(f"✅ Result: {result}")

if __name__ == "__main__":
    main()
