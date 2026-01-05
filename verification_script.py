
import logging
import time
import json
import traceback
from adbutils import adb
from workflow_runner import WorkflowRunner

# Configure logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("verification.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Verifier")
# Force debug on core
logging.getLogger("core.action_library").setLevel(logging.DEBUG)
logging.getLogger("workflow_runner").setLevel(logging.DEBUG)

def verify_all_nodes():
    logger.info("🚀 Starting Full Node Verification Script...")
    
    report = []
    
    try:
        # 1. Connect
        device = adb.device()
        runner = WorkflowRunner(device)
        logger.info(f"📱 Connected to {device.serial}")
        
        # 2. Define Test Cases
        # We test independent actions directly to avoid 'run_workflow' file I/O complexity if that was the issue
        # But run_workflow is the integration test.
        
        # Let's verify _get_screenshot_for_ocr first
        img = runner._get_screenshot_for_ocr()
        img_type = str(type(img))
        logger.info(f"📸 Screenshot Type: {img_type}")
        if "numpy" in img_type:
            report.append("✅ OCR Screenshot Fix: Success (numpy)")
        else:
            report.append(f"❌ OCR Screenshot Fix: Failed ({img_type})")
            
        test_steps = [
            {
                "id": "VAR_01",
                "step": {"action_type": "Set Variable", "params": "TestVar = Passed"},
                "desc": "Set Variable"
            },
            {
                "id": "VAR_02",
                "step": {"action_type": "Print Variable", "params": "${TestVar}"},
                "desc": "Print Variable"
            },
            {
                "id": "SYS_01",
                "step": {"action_type": "Wait Time", "params": "0.5"},
                "desc": "Wait Time"
            },
            {
                "id": "VIS_01",
                "step": {"action_type": "Check Text", "params": "op:Contains|Settings"},
                "desc": "Check Text (OCR)"
            },
            {
                "id": "INP_B64",
                "step": {"action_type": "Input Text (Base64)", "params": "Test B64 Input"},
                "desc": "Input Text (Base64) - Raw Process Check"
            },
            # We assume Input Text (Base64) requires root, user has it.
            # We skip it in auto-test to avoid side-effects on screen, 
            # unless we click a known safe area.
            {
                "id": "VIS_02", # Click Text
                "step": {"action_type": "Click Text", "params": "Settings", "is_optional": True},
                "desc": "Click Text (OCR)"
            }
        ]
        
        row_data = {"Initial": "Data"}
        
        for case in test_steps:
            step_data = case["step"]
            step_desc = case["desc"]
            step_id = case["id"]
            
            logger.info(f"▶️ Testing {step_id}: {step_desc}")
            try:
                # Manually invoke handler if mapped, or execute_step
                success = runner.execute_step(step_data, row_data)
                
                if success:
                    report.append(f"✅ {step_id}: {step_desc} - Passed")
                else:
                    report.append(f"⚠️ {step_id}: {step_desc} - Returned False (Logic/Vision Mismatch?)")
            except Exception as e:
                report.append(f"❌ {step_id}: {step_desc} - Exception: {e}")
                traceback.print_exc()

    except Exception as e:
        logger.error(f"❌ Global Crash: {e}")
        report.append(f"❌ Global Crash: {e}")
        
    # Write Report
    with open("verification_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
        
    logger.info("📝 Report written to verification_report.txt")
    print("\nXXX_REPORT_START_XXX")
    print("\n".join(report))
    print("XXX_REPORT_END_XXX")

if __name__ == "__main__":
    verify_all_nodes()
