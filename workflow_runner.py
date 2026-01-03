"""
WorkflowRunner - 工作流执行引擎
================================

读取 JSON 流程文件，结合 Excel 数据，驱动手机执行自动化操作。

工业级特性：
1. 📸 失败自动截图 (Screenshot on Fail)
2. 🛡️ 容错与重试机制 (Retry & Optional)
3. 🧠 变量注入增强 (Eval Support)

JSON 格式示例：
[
    {
        "step_id": 1,
        "step_name": "Step 1",
        "action_type": "Click Region",
        "params": "${SKU}",
        "context": "点击搜索按钮",
        "coords": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4},
        "retry_count": 3,
        "is_optional": false
    }
]

Usage:
    from adbutils import adb
    from workflow_runner import WorkflowRunner

    device = adb.device()
    runner = WorkflowRunner(device)
    
    row_data = {"SKU": "A001", "Price": "29.99"}
    success = runner.run_workflow("config/upload_flow.json", row_data)
"""

import json
import logging
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("WorkflowRunner")


class WorkflowRunner:
    """
    工作流执行引擎 - 读取 JSON 流程文件并执行自动化操作
    
    设计思路：
    1. 解耦设计：不依赖 GUI，可独立运行
    2. 数据驱动：支持 Excel 变量注入 (${Variable})
    3. 拟人化操作：所有操作带随机延迟和抖动
    4. 健壮性：完整的异常处理、重试机制和日志记录
    """

    # 默认配置
    DEFAULT_RETRY_COUNT = 0
    DEFAULT_RETRY_INTERVAL = (1.0, 2.0)  # 重试间隔范围（秒）
    DEFAULT_CLICK_JITTER = 0.02  # 点击抖动范围（百分比）
    DEFAULT_ACTION_DELAY = (0.3, 0.8)  # 动作后延迟范围（秒）
    ERROR_SCREENSHOT_DIR = "./logs/error_screenshots"

    def __init__(
        self,
        device,
        human_device=None,
        ocr_engine=None,
        phone_width: int = 1080,
        phone_height: int = 2400,
    ):
        """
        初始化工作流执行器

        Args:
            device: ADB 连接对象 (adbutils.Device)
            human_device: 可选，拟人化操作实例（如果有自定义实现）
            ocr_engine: 可选，OCR 引擎实例（如 RapidOCR）
            phone_width: 手机屏幕宽度（像素）
            phone_height: 手机屏幕高度（像素）
        """
        self.device = device
        self.human_device = human_device
        self.ocr_engine = ocr_engine
        self.phone_width = phone_width
        self.phone_height = phone_height

        # 尝试自动获取屏幕分辨率
        self._update_screen_resolution()

        # 确保截图目录存在
        Path(self.ERROR_SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)

        # 动作分发器映射表
        self._action_handlers: Dict[str, Callable] = {
            "Click Region": self._action_click_region,
            "Click Text": self._action_click_text,
            "Input Text": self._action_input_text,
            "Swipe": self._action_swipe,
            "Long Press": self._action_long_press,
            "Check Text": self._action_check_text,
            "Wait Text": self._action_wait_text,
            "Wait Element": self._action_wait_element,
            "Wait Time": self._action_wait_time,
            "Assert Exists": self._action_assert_exists,
            "Wait Until Disappear": self._action_wait_until_disappear,
        }

        logger.info(
            f"WorkflowRunner 初始化完成 | 屏幕: {self.phone_width}x{self.phone_height}"
        )

    # ==================== 核心公共方法 ====================

    def run_workflow(
        self, json_path: str, row_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        执行整个工作流

        Args:
            json_path: JSON 流程文件路径
            row_data: Excel 数据行（字典格式），用于变量替换

        Returns:
            bool: 执行成功返回 True，失败返回 False
        """
        row_data = row_data or {}

        # 1. 加载 JSON 文件
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                steps: List[Dict[str, Any]] = json.load(f)
        except FileNotFoundError:
            logger.error(f"❌ 工作流文件不存在: {json_path}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析错误: {e}")
            return False

        if not isinstance(steps, list):
            logger.error("❌ JSON 格式错误: 根元素必须是数组")
            return False

        logger.info(f"📂 加载工作流: {json_path} | 共 {len(steps)} 个步骤")
        logger.info(f"📊 数据行: {row_data}")

        # 2. 逐步执行
        total_steps = len(steps)
        failed_steps = []

        for idx, step in enumerate(steps, 1):
            step_id = step.get("step_id", idx)
            step_name = step.get("step_name", f"Step {idx}")
            action_type = step.get("action_type", "Unknown")

            logger.info(f"▶️ [{idx}/{total_steps}] {step_name} | 动作: {action_type}")

            success = self.execute_step(step, row_data)

            if not success:
                is_optional = step.get("is_optional", False)
                if is_optional:
                    logger.warning(
                        f"⚠️ 步骤 {step_id} 失败但设置为可选，继续执行..."
                    )
                    failed_steps.append((step_id, step_name, "optional_failed"))
                else:
                    logger.error(f"❌ 步骤 {step_id} 失败，工作流中断")
                    return False

            # 动作间随机延迟（拟人化）
            delay = random.uniform(*self.DEFAULT_ACTION_DELAY)
            time.sleep(delay)

        # 3. 执行完成汇总
        if failed_steps:
            logger.warning(
                f"⚠️ 工作流完成，但有 {len(failed_steps)} 个可选步骤失败: {failed_steps}"
            )
        else:
            logger.info("✅ 工作流全部执行成功！")

        return True

    def execute_step(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """
        执行单个步骤（带重试和容错机制）

        Args:
            step: 步骤配置字典
            row_data: Excel 数据行

        Returns:
            bool: 执行成功返回 True，失败返回 False
        """
        step_id = step.get("step_id", 0)
        step_name = step.get("step_name", "Unknown")
        action_type = step.get("action_type", "Unknown")
        retry_count = step.get("retry_count", self.DEFAULT_RETRY_COUNT)

        # 获取动作处理器
        handler = self._action_handlers.get(action_type)
        if handler is None:
            logger.error(f"❌ 未知动作类型: {action_type}")
            self._take_error_screenshot(step_id)
            return False

        # 重试循环
        last_error = None
        for attempt in range(retry_count + 1):
            try:
                if attempt > 0:
                    retry_delay = random.uniform(*self.DEFAULT_RETRY_INTERVAL)
                    logger.info(
                        f"🔄 重试第 {attempt}/{retry_count} 次 | 步骤: {step_name} | 等待 {retry_delay:.1f}s"
                    )
                    time.sleep(retry_delay)

                # 执行动作
                success = handler(step, row_data)

                if success:
                    logger.info(f"✅ 步骤完成: {step_name}")
                    return True
                else:
                    last_error = "动作返回 False"
                    logger.warning(f"⚠️ 步骤执行失败: {step_name}")

            except Exception as e:
                last_error = str(e)
                logger.exception(f"💥 步骤异常: {step_name} | 错误: {e}")

        # 所有重试都失败
        logger.error(
            f"❌ 步骤最终失败: {step_name} | 尝试 {retry_count + 1} 次 | 错误: {last_error}"
        )
        self._take_error_screenshot(step_id)
        return False

    # ==================== 变量注入系统 ====================

    def _inject_variables(self, text: str, row_data: Dict[str, Any]) -> str:
        """
        变量注入：将 ${Key} 格式的占位符替换为 row_data 中的值

        示例：
            text = "Hello ${Name}, your price is ${Price}"
            row_data = {"Name": "John", "Price": "100"}
            返回：  "Hello John, your price is 100"

        Args:
            text: 包含变量占位符的文本
            row_data: 变量值字典

        Returns:
            str: 替换后的文本
        """
        if not text or not row_data:
            return text

        # 正则匹配 ${...} 模式
        pattern = r"\$\{(\w+)\}"

        def replacer(match):
            key = match.group(1)
            value = row_data.get(key, match.group(0))  # 未找到则保留原样
            return str(value)

        return re.sub(pattern, replacer, text)

    def _evaluate_expression(self, expr: str, row_data: Dict[str, Any]) -> str:
        """
        表达式求值：支持 eval: 前缀的 Python 表达式

        示例：
            expr = "eval: float(${Price}) + 10"
            row_data = {"Price": "100"}
            返回：  "110.0"

        Args:
            expr: 表达式字符串（可能以 "eval:" 开头）
            row_data: 变量值字典

        Returns:
            str: 求值结果或原始字符串
        """
        if not expr:
            return expr

        # 检查是否是 eval 表达式
        if expr.strip().lower().startswith("eval:"):
            raw_expr = expr.strip()[5:].strip()  # 移除 "eval:" 前缀

            # 先替换变量
            injected_expr = self._inject_variables(raw_expr, row_data)

            try:
                # 安全求值：只允许基本运算和内置函数
                allowed_names = {
                    "float": float,
                    "int": int,
                    "str": str,
                    "round": round,
                    "abs": abs,
                    "min": min,
                    "max": max,
                    "len": len,
                }
                result = eval(injected_expr, {"__builtins__": {}}, allowed_names)
                logger.debug(f"📐 表达式求值: {raw_expr} → {result}")
                return str(result)
            except Exception as e:
                logger.warning(f"⚠️ 表达式求值失败: {raw_expr} | 错误: {e}")
                return expr  # 失败时返回原始字符串

        # 普通变量替换
        return self._inject_variables(expr, row_data)

    # ==================== 坐标计算 ====================

    def _calculate_click_point(
        self, coords: Dict[str, float], jitter: bool = True
    ) -> Tuple[int, int]:
        """
        计算点击坐标：中心点 + 随机抖动

        Args:
            coords: 坐标字典 {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4}
            jitter: 是否添加随机抖动

        Returns:
            Tuple[int, int]: (x, y) 像素坐标
        """
        x1 = coords.get("x1", 0)
        y1 = coords.get("y1", 0)
        x2 = coords.get("x2", 0)
        y2 = coords.get("y2", 0)

        # 计算中心点（百分比）
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # 添加随机抖动
        if jitter:
            jitter_x = random.uniform(
                -self.DEFAULT_CLICK_JITTER, self.DEFAULT_CLICK_JITTER
            )
            jitter_y = random.uniform(
                -self.DEFAULT_CLICK_JITTER, self.DEFAULT_CLICK_JITTER
            )
            cx = max(0, min(1, cx + jitter_x))
            cy = max(0, min(1, cy + jitter_y))

        # 转换为像素坐标
        px = int(cx * self.phone_width)
        py = int(cy * self.phone_height)

        return (px, py)

    def _pct_to_px(self, x: float, y: float) -> Tuple[int, int]:
        """百分比坐标转像素坐标"""
        return (int(x * self.phone_width), int(y * self.phone_height))

    # ==================== 截图与工具方法 ====================

    def _take_error_screenshot(self, step_id: Union[int, str]) -> Optional[str]:
        """
        失败截图：捕获当前屏幕并保存

        Args:
            step_id: 步骤 ID

        Returns:
            str: 截图文件路径，失败返回 None
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Error_Step{step_id}_{timestamp}.png"
            filepath = os.path.join(self.ERROR_SCREENSHOT_DIR, filename)

            # ADB 截图
            png_data = self.device.screenshot()
            
            # 保存文件
            if hasattr(png_data, 'save'):
                # PIL Image 对象
                png_data.save(filepath)
            else:
                # bytes 数据
                with open(filepath, "wb") as f:
                    f.write(png_data)

            logger.info(f"📸 错误截图已保存: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"❌ 截图失败: {e}")
            return None

    def _update_screen_resolution(self) -> None:
        """尝试自动获取屏幕分辨率"""
        try:
            output = self.device.shell("wm size")
            # 输出格式: "Physical size: 1080x2400"
            match = re.search(r"(\d+)x(\d+)", output)
            if match:
                self.phone_width = int(match.group(1))
                self.phone_height = int(match.group(2))
                logger.info(
                    f"📱 自动检测屏幕分辨率: {self.phone_width}x{self.phone_height}"
                )
        except Exception as e:
            logger.warning(f"⚠️ 无法自动获取屏幕分辨率: {e}")

    def _get_screenshot_for_ocr(self):
        """获取截图用于 OCR"""
        try:
            return self.device.screenshot()
        except Exception as e:
            logger.error(f"❌ 截图失败: {e}")
            return None

    # ==================== 动作处理器实现 ====================

    def _action_click_region(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Click Region: 点击区域中心（带随机抖动）"""
        coords = step.get("coords", {})
        px, py = self._calculate_click_point(coords)

        logger.debug(f"🖱️ 点击坐标: ({px}, {py})")

        if self.human_device:
            self.human_device.click(px, py)
        else:
            self.device.click(px, py)

        return True

    def _action_click_text(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Click Text: 基于 OCR 点击文字锚点"""
        params = step.get("params", "")
        target_text = self._evaluate_expression(params, row_data)
        coords = step.get("coords", {})

        if not target_text:
            logger.warning("⚠️ Click Text 需要指定目标文字")
            return False

        if not self.ocr_engine:
            # 如果没有 OCR 引擎，退化为普通点击
            logger.warning("⚠️ 未配置 OCR 引擎，退化为区域点击")
            return self._action_click_region(step, row_data)

        # 执行 OCR 查找文字
        screenshot = self._get_screenshot_for_ocr()
        if screenshot is None:
            return False

        try:
            result = self.ocr_engine(screenshot)
            if result is None:
                return False

            # 查找目标文字
            for item in result:
                if item and len(item) >= 2:
                    text = item[1] if isinstance(item[1], str) else str(item[1])
                    if target_text in text:
                        # 找到目标，计算中心点
                        box = item[0]
                        cx = sum(p[0] for p in box) / 4
                        cy = sum(p[1] for p in box) / 4
                        self.device.click(int(cx), int(cy))
                        logger.info(f"🔤 点击文字 '{target_text}' @ ({int(cx)}, {int(cy)})")
                        return True

            logger.warning(f"⚠️ 未找到文字: {target_text}")
            return False

        except Exception as e:
            logger.error(f"❌ OCR 点击失败: {e}")
            return False

    def _action_input_text(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Input Text: 输入文本（支持变量注入和表达式）"""
        coords = step.get("coords", {})
        params = step.get("params", "")

        # 变量注入/表达式求值
        text_to_input = self._evaluate_expression(params, row_data)

        if not text_to_input:
            logger.warning("⚠️ Input Text 参数为空")
            return True  # 空输入不算失败

        # 先点击目标区域（激活输入框）
        px, py = self._calculate_click_point(coords)
        self.device.click(px, py)
        time.sleep(0.3)

        # 输入文本
        if self.human_device and hasattr(self.human_device, "input_text_stealth"):
            self.human_device.input_text_stealth(text_to_input)
        else:
            # 使用 ADB input text（需要转义特殊字符）
            escaped = text_to_input.replace(" ", "%s").replace("&", "\\&")
            self.device.shell(f"input text '{escaped}'")

        logger.info(f"⌨️ 输入文本: '{text_to_input}'")
        return True

    def _action_swipe(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Swipe: 从区域顶部滑动到底部"""
        coords = step.get("coords", {})

        x1 = coords.get("x1", 0.5)
        y1 = coords.get("y1", 0.3)
        x2 = coords.get("x2", 0.5)
        y2 = coords.get("y2", 0.7)

        # 中心 X，从 y1 滑到 y2
        cx = (x1 + x2) / 2
        start_x, start_y = self._pct_to_px(cx, y1)
        end_x, end_y = self._pct_to_px(cx, y2)

        duration = random.uniform(0.3, 0.6)

        if self.human_device and hasattr(self.human_device, "swipe"):
            self.human_device.swipe(start_x, start_y, end_x, end_y, duration)
        else:
            self.device.swipe(start_x, start_y, end_x, end_y, duration)

        logger.info(f"👆 滑动: ({start_x}, {start_y}) → ({end_x}, {end_y})")
        return True

    def _action_long_press(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Long Press: 长按区域中心"""
        coords = step.get("coords", {})
        px, py = self._calculate_click_point(coords)

        duration = 1.0  # 长按 1 秒

        # 使用 swipe 模拟长按（起点终点相同）
        self.device.swipe(px, py, px, py, duration)

        logger.info(f"👇 长按: ({px}, {py}) | 持续 {duration}s")
        return True

    def _action_check_text(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Check Text: OCR 检查屏幕文字是否存在（不阻塞）"""
        params = step.get("params", "")
        target_text = self._evaluate_expression(params, row_data)

        if not target_text:
            logger.warning("⚠️ Check Text 需要指定目标文字")
            return False

        if not self.ocr_engine:
            logger.warning("⚠️ 未配置 OCR 引擎，无法执行 Check Text")
            return False

        screenshot = self._get_screenshot_for_ocr()
        if screenshot is None:
            return False

        try:
            result = self.ocr_engine(screenshot)
            if result:
                all_text = " ".join(
                    item[1] for item in result if item and len(item) >= 2
                )
                if target_text in all_text:
                    logger.info(f"✅ 找到文字: '{target_text}'")
                    return True

            logger.info(f"❌ 未找到文字: '{target_text}'")
            return False

        except Exception as e:
            logger.error(f"❌ OCR 检查失败: {e}")
            return False

    def _action_wait_text(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Wait Text: 等待文字出现（轮询 OCR）"""
        params = step.get("params", "")
        target_text = self._evaluate_expression(params, row_data)

        # 解析超时时间（默认 10 秒）
        timeout = 10
        timeout_match = re.search(r"timeout[=:]?\s*(\d+)", params, re.IGNORECASE)
        if timeout_match:
            timeout = int(timeout_match.group(1))

        if not target_text:
            logger.warning("⚠️ Wait Text 需要指定目标文字")
            return False

        if not self.ocr_engine:
            logger.warning("⚠️ 未配置 OCR 引擎，无法执行 Wait Text")
            return False

        logger.info(f"⏳ 等待文字出现: '{target_text}' | 超时: {timeout}s")

        start_time = time.time()
        while time.time() - start_time < timeout:
            screenshot = self._get_screenshot_for_ocr()
            if screenshot:
                try:
                    result = self.ocr_engine(screenshot)
                    if result:
                        all_text = " ".join(
                            item[1] for item in result if item and len(item) >= 2
                        )
                        if target_text in all_text:
                            elapsed = time.time() - start_time
                            logger.info(f"✅ 文字已出现: '{target_text}' | 耗时: {elapsed:.1f}s")
                            return True
                except Exception:
                    pass

            time.sleep(1)  # 每秒检查一次

        logger.warning(f"⏰ 等待超时: '{target_text}' 未出现")
        return False

    def _action_wait_element(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Wait Element: 等待元素出现（基于模板匹配或 OCR）"""
        # 简化实现：委托给 Wait Text
        return self._action_wait_text(step, row_data)

    def _action_wait_time(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Wait Time: 固定等待"""
        params = step.get("params", "")

        # 尝试从 params 提取数字
        wait_seconds = 1.0  # 默认 1 秒
        match = re.search(r"(\d+(?:\.\d+)?)", params)
        if match:
            wait_seconds = float(match.group(1))

        logger.info(f"⏱️ 等待 {wait_seconds} 秒...")
        time.sleep(wait_seconds)
        return True

    def _action_assert_exists(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Assert Exists: 断言元素存在，失败抛出异常"""
        # 先执行 Check Text
        exists = self._action_check_text(step, row_data)

        if not exists:
            params = step.get("params", "")
            target = self._evaluate_expression(params, row_data)
            error_msg = f"断言失败: 元素 '{target}' 不存在"
            logger.error(f"💥 {error_msg}")
            raise AssertionError(error_msg)

        return True

    def _action_wait_until_disappear(
        self, step: Dict[str, Any], row_data: Dict[str, Any]
    ) -> bool:
        """Wait Until Disappear: 等待元素消失"""
        params = step.get("params", "")
        target_text = self._evaluate_expression(params, row_data)

        # 解析超时时间（默认 30 秒）
        timeout = 30
        timeout_match = re.search(r"timeout[=:]?\s*(\d+)", params, re.IGNORECASE)
        if timeout_match:
            timeout = int(timeout_match.group(1))

        if not target_text:
            logger.warning("⚠️ Wait Until Disappear 需要指定目标文字")
            return False

        if not self.ocr_engine:
            logger.warning("⚠️ 未配置 OCR 引擎，直接返回成功")
            return True

        logger.info(f"⏳ 等待元素消失: '{target_text}' | 超时: {timeout}s")

        start_time = time.time()
        while time.time() - start_time < timeout:
            screenshot = self._get_screenshot_for_ocr()
            if screenshot:
                try:
                    result = self.ocr_engine(screenshot)
                    if result:
                        all_text = " ".join(
                            item[1] for item in result if item and len(item) >= 2
                        )
                        if target_text not in all_text:
                            elapsed = time.time() - start_time
                            logger.info(f"✅ 元素已消失: '{target_text}' | 耗时: {elapsed:.1f}s")
                            return True
                    else:
                        # OCR 无结果，认为元素已消失
                        return True
                except Exception:
                    pass

            time.sleep(1)

        logger.warning(f"⏰ 等待超时: '{target_text}' 仍然存在")
        return False


# ==================== 便捷工厂函数 ====================


def create_runner_from_serial(serial: str = None, **kwargs) -> WorkflowRunner:
    """
    便捷函数：从设备序列号创建 WorkflowRunner

    Args:
        serial: 设备序列号，None 则自动选择第一个设备

    Returns:
        WorkflowRunner 实例
    """
    try:
        from adbutils import adb

        if serial:
            device = adb.device(serial=serial)
        else:
            devices = adb.device_list()
            if not devices:
                raise RuntimeError("未找到已连接的 ADB 设备")
            device = devices[0]
            logger.info(f"📱 自动选择设备: {device.serial}")

        return WorkflowRunner(device, **kwargs)

    except ImportError:
        raise ImportError("请安装 adbutils: pip install adbutils")


# ==================== 测试入口 ====================


def _test_variable_injection():
    """独立测试变量注入功能（无需设备连接）"""
    import re as test_re

    def inject_variables(text: str, row_data: dict) -> str:
        """测试用变量注入"""
        if not text or not row_data:
            return text
        pattern = r"\$\{(\w+)\}"
        def replacer(match):
            key = match.group(1)
            return str(row_data.get(key, match.group(0)))
        return test_re.sub(pattern, replacer, text)

    def evaluate_expression(expr: str, row_data: dict) -> str:
        """测试用表达式求值"""
        if not expr:
            return expr
        if expr.strip().lower().startswith("eval:"):
            raw_expr = expr.strip()[5:].strip()
            injected_expr = inject_variables(raw_expr, row_data)
            try:
                allowed_names = {"float": float, "int": int, "str": str, "round": round, "abs": abs, "min": min, "max": max, "len": len}
                result = eval(injected_expr, {"__builtins__": {}}, allowed_names)
                return str(result)
            except Exception:
                return expr
        return inject_variables(expr, row_data)

    test_cases = [
        ("Hello ${Name}!", {"Name": "World"}, "Hello World!"),
        ("Price: ${Price}", {"Price": "99.99"}, "Price: 99.99"),
        ("eval: float(${Price}) * 1.1", {"Price": "100"}, "110.00000000000001"),
        ("eval: round(float(${Amount}) / 3, 2)", {"Amount": "100"}, "33.33"),
    ]

    print("\n📐 变量注入测试:")
    all_passed = True
    for expr, data, expected in test_cases:
        result = evaluate_expression(expr, data)
        passed = result == expected
        if not passed:
            all_passed = False
        status = "✅" if passed else "❌"
        print(f"  {status} '{expr}' → '{result}' (期望: '{expected}')")

    return all_passed


if __name__ == "__main__":
    # 示例：创建执行器并运行测试
    print("=" * 60)
    print("WorkflowRunner - 工作流执行引擎测试")
    print("=" * 60)

    # 运行变量注入测试
    _test_variable_injection()

    print("\n💡 使用示例:")
    print("""
    from adbutils import adb
    from workflow_runner import WorkflowRunner

    device = adb.device()
    runner = WorkflowRunner(device)

    row_data = {"SKU": "A001", "Price": "29.99", "Title": "Sneakers"}
    success = runner.run_workflow("config/upload_flow.json", row_data)
    """)
