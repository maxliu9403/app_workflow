
import time
import random
import logging
import shlex
import math
from adbutils import AdbDevice

logger = logging.getLogger("HumanDevice")

class HumanDevice:
    """
    Bio-Mimicry Device Wrapper V2.0
    ===============================
    Simulates advanced human biological traits:
    - Micro-Tremor Click: Finger never stays perfectly still during a press.
    - Fitts's Law Swipe: Movement speed correlates with distance.
    - Secure Input: Shell-safe character injection with cognitive delays.
    
    Prevents behavioral analysis flagging by mimicking physical constraints.
    """
    def __init__(self, device: AdbDevice):
        self.device = device
        
    def click(self, x: int, y: int, jitter: int = 5):
        """
        Bio-Click V2: Simulates current flow/touch area changes during press.
        Uses 'input swipe' with micro-movement to mimic finger tremor.
        """
        # 1. Target Jitter (Intention Error)
        offset_x = random.randint(-jitter, jitter)
        offset_y = random.randint(-jitter, jitter)
        tx = x + offset_x
        ty = y + offset_y
        
        # 2. Micro-Movement (Tremor during press)
        # Real fingers slide slightly (1-2px) during a "static" press
        end_x = tx + random.randint(-2, 2)
        end_y = ty + random.randint(-2, 2)
        
        # 3. Random Press Duration (60-140ms)
        duration = random.randint(60, 140) 
        
        # 4. Micro-Delay (Reaction Time)
        time.sleep(random.uniform(0.05, 0.15))
        
        logger.info(f"👆 Bio-Click: ({tx}, {ty}) -> ({end_x}, {end_y}) | {duration}ms")
        
        try:
            # input swipe <x1> <y1> <x2> <y2> <duration_ms>
            cmd = f"input swipe {tx} {ty} {end_x} {end_y} {duration}"
            self.device.shell(cmd)
        except Exception as e:
            logger.error(f"❌ Bio-Click failed: {e}")
        
        # 5. Post-Action Decay
        time.sleep(random.uniform(0.1, 0.3))

    def swipe(self, x1, y1, x2, y2, duration=None):
        """
        Physics-Swipe V2 (Fitts's Law): 
        Calculates duration based on distance to simulate physical arm/finger velocity.
        """
        jitter = 15
        
        # 1. Jitter Endpoints
        sx = x1 + random.randint(-jitter, jitter)
        sy = y1 + random.randint(-jitter, jitter)
        ex = x2 + random.randint(-jitter, jitter)
        ey = y2 + random.randint(-jitter, jitter)
        
        # 2. Dynamic Duration Calculation (Fitts's Law approximation)
        if duration is None:
            distance = math.hypot(ex - sx, ey - sy)
            velocity = 0.5  # pixels per millisecond (average thumb speed)
            
            # Base duration on distance + entropy
            calc_duration = int(distance / velocity) + random.randint(-50, 150)
            
            # Clamp limits (Human physiological constraints)
            # Short swipes ~200ms, Long swipes ~1500ms
            duration = max(200, min(calc_duration, 1500))
            
        logger.info(f"👋 Physics-Swipe: ({sx}, {sy}) -> ({ex}, {ey}) | Dist: {int(math.hypot(ex-sx, ey-sy))}px | Time: {duration}ms")
        
        try:
            # ADB usually takes seconds for swipe, convert ms to seconds
            # adbutils.device.swipe expects seconds
            self.device.swipe(sx, sy, ex, ey, duration / 1000.0)
        except Exception as e:
            logger.error(f"❌ Swipe failed: {e}")
            
        # Post-swipe stability delay
        time.sleep(random.uniform(0.3, 0.6))

    def input_text(self, text: str):
        """
        Secure Cognitive Input: 
        Uses shlex for safe quoting and simulates focus delay.
        """
        # 1. Cognitive Delay (Eye tracking simulation)
        focus_delay = random.uniform(0.5, 1.5)
        logger.info(f"👀 Focusing input field... ({focus_delay:.2f}s)")
        time.sleep(focus_delay)
        
        logger.info(f"⌨️ Human Input: {text}")
        
        try:
            # 2. Shell Injection Protection
            safe_text = shlex.quote(text)
            self.device.shell(f"input text {safe_text}")
        except Exception as e:
            logger.error(f"❌ Input failed: {e}")
            
        # Post-typing verification delay
        time.sleep(random.uniform(0.5, 1.0))

    def shell(self, cmd):
        """Robust shell execution with error logging"""
        try:
            return self.device.shell(cmd)
        except Exception as e:
            logger.error(f"❌ Shell command failed: {cmd} | Error: {e}")
            return ""
        
    def __getattr__(self, name):
        """Delegate all other methods to the underlying AdbDevice"""
        return getattr(self.device, name)
