# Custom Actions for V7 Editor
import time
import random
import logging



# Action: Double Click
import time
import random

def action_double_click(runner, step, row_data):
    """
    Performs a double click at the center of the selected region.
    """
    # 1. Get device resolution
    w, h = runner.device.window_size()

    # 2. Parse coordinates (Default to full screen center if not set)
    coords = step.get('coords', {})
    x1 = coords.get('x1', 0.0)
    y1 = coords.get('y1', 0.0)
    x2 = coords.get('x2', 1.0)
    y2 = coords.get('y2', 1.0)

    # 3. Calculate center point in pixels
    cx = int((x1 + x2) / 2 * w)
    cy = int((y1 + y2) / 2 * h)

    # 4. Perform Double Click logic
    # First click
    runner.device.click(cx, cy)
    
    # Random interval between 50ms and 150ms for human-like behavior
    interval = random.uniform(0.05, 0.15)
    time.sleep(interval)
    
    # Second click
    runner.device.click(cx, cy)

    return True


# Action: Double Click
import time
import random

def action_double_click(runner, step, row_data):
    """
    Performs a double click at the center of the selected region.
    """
    # 1. Get device resolution
    w, h = runner.device.window_size()

    # 2. Parse coordinates (Default to full screen center if not set)
    coords = step.get('coords', {})
    x1 = coords.get('x1', 0.0)
    y1 = coords.get('y1', 0.0)
    x2 = coords.get('x2', 1.0)
    y2 = coords.get('y2', 1.0)

    # 3. Calculate center point in pixels
    cx = int((x1 + x2) / 2 * w)
    cy = int((y1 + y2) / 2 * h)

    # 4. Perform Double Click logic
    # First click
    runner.device.click(cx, cy)
    
    # Random interval between 50ms and 150ms for human-like behavior
    interval = random.uniform(0.05, 0.15)
    time.sleep(interval)
    
    # Second click
    runner.device.click(cx, cy)

    return True


# Action: Double Click
import time
import random

def action_double_click(runner, step, row_data):
    """
    Performs a double click at the center of the selected region.
    """
    # 1. Get device resolution
    w, h = runner.device.window_size()

    # 2. Parse coordinates (Default to full screen center if not set)
    coords = step.get('coords', {})
    x1 = coords.get('x1', 0.0)
    y1 = coords.get('y1', 0.0)
    x2 = coords.get('x2', 1.0)
    y2 = coords.get('y2', 1.0)

    # 3. Calculate center point in pixels
    cx = int((x1 + x2) / 2 * w)
    cy = int((y1 + y2) / 2 * h)

    # 4. Perform Double Click logic
    # First click
    runner.device.click(cx, cy)
    
    # Random interval between 50ms and 150ms for human-like behavior
    interval = random.uniform(0.05, 0.15)
    time.sleep(interval)
    
    # Second click
    runner.device.click(cx, cy)

    return True


# Action: 双击屏幕
import time
import random

def action_double_click(runner, step, row_data):
    """
    双击选中区域中心
    """
    # 1. 获取屏幕分辨率
    w, h = runner.device.window_size()

    # 2. 解析坐标 (默认全屏)
    coords = step.get('coords', {})
    x1 = coords.get('x1', 0.0)
    y1 = coords.get('y1', 0.0)
    x2 = coords.get('x2', 1.0)
    y2 = coords.get('y2', 1.0)

    # 3. 计算像素坐标
    cx = int((x1 + x2) / 2 * w)
    cy = int((y1 + y2) / 2 * h)

    # 4. 获取间隔参数 (默认 0.1s)
    try:
        interval = float(step.get('params', 0.1))
    except:
        interval = 0.1

    # 5. 执行双击
    runner.device.click(cx, cy)
    time.sleep(interval)
    runner.device.click(cx, cy)

    return True
