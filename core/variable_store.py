"""
VariableStore - 全功能变量库系统
================================

支持变量的动态定义、强类型存储、运行时读写。

核心特性：
1. 🔢 类型保留：int/float/bool/list/dict/str 原生存储
2. 📍 嵌套访问：支持 Dot Notation (User.Address.City)
3. 🔄 动态注入：${Key} 替换，支持对象直接返回
4. 📝 结果回写：支持 -> ${VarName} 语法捕获结果

Usage:
    from core.variable_store import VariableStore
    
    store = VariableStore()
    store.set_variable("Count", 0)
    store.set_variable("User", {"Name": "John", "Age": 25})
    
    print(store.get_variable("User.Name"))  # "John"
    print(store.get_variable("Count"))      # 0 (int, not str)
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("VariableStore")


class VariableStore:
    """
    全功能变量库 - 支持类型保留、嵌套访问、动态注入
    
    升级自 ContextManager，保持向后兼容。
    """
    
    # 支持的类型
    SUPPORTED_TYPES = {"auto", "int", "float", "bool", "str", "list", "dict"}
    
    def __init__(
        self,
        row_data: Dict[str, Any] = None,
        global_context: Dict[str, Any] = None
    ):
        """
        初始化变量库
        
        Args:
            row_data: Excel 行数据 (优先级高)
            global_context: 全局变量 (优先级低)
        """
        self._global_context = global_context or {}
        self._row_data = row_data or {}
        
        # 内部统一存储 (保留类型)
        self._variables: Dict[str, Any] = {}
        
        # 合并初始上下文
        self._merge_initial_context()
    
    def _merge_initial_context(self):
        """合并全局和行数据到内部存储"""
        # 全局变量先入
        for k, v in self._global_context.items():
            self._variables[k] = v
        
        # 行数据覆盖
        for k, v in self._row_data.items():
            self._variables[k] = v
    
    # ==================== 核心存取方法 ====================
    
    def set_variable(
        self,
        key: str,
        value: Any,
        var_type: str = "auto"
    ) -> bool:
        """
        设置变量（带类型转换）
        
        Args:
            key: 变量名 (支持嵌套如 "User.Name")
            value: 变量值
            var_type: 类型指定 ("auto", "int", "float", "bool", "str", "list", "dict")
        
        Returns:
            bool: 设置成功返回 True
        
        Examples:
            store.set_variable("Count", "10", "int")       # -> 10 (int)
            store.set_variable("Price", "99.5", "auto")    # -> 99.5 (float)
            store.set_variable("Items", "[]", "list")      # -> [] (list)
            store.set_variable("User.Age", 25)             # 嵌套设置
        """
        if var_type not in self.SUPPORTED_TYPES:
            logger.warning(f"⚠️ Unsupported type '{var_type}', falling back to 'auto'")
            var_type = "auto"
        
        # 类型转换
        converted_value = self._convert_type(value, var_type)
        
        # 嵌套设置
        if "." in key:
            return self._set_nested(key, converted_value)
        
        self._variables[key] = converted_value
        logger.debug(f"📝 Set Variable: {key} = {converted_value} ({type(converted_value).__name__})")
        return True
    
    def get_variable(self, key: str, default: Any = None) -> Any:
        """
        获取变量（支持嵌套访问）
        
        Args:
            key: 变量名 (支持 Dot Notation 如 "User.Address.City")
            default: 未找到时的默认值
        
        Returns:
            变量值 (保留原始类型)
        
        Examples:
            store.get_variable("Count")           # -> 10 (int)
            store.get_variable("User.Name")       # -> "John"
            store.get_variable("User.Address.City")  # 深层嵌套
        """
        if "." in key:
            return self._get_nested(key, default)
        
        return self._variables.get(key, default)
    
    def has_variable(self, key: str) -> bool:
        """检查变量是否存在"""
        return self.get_variable(key) is not None
    
    def delete_variable(self, key: str) -> bool:
        """删除变量"""
        if key in self._variables:
            del self._variables[key]
            return True
        return False
    
    def clear(self):
        """清空所有变量"""
        self._variables.clear()
    
    @property
    def variables(self) -> Dict[str, Any]:
        """获取所有变量的只读副本"""
        return self._variables.copy()
    
    @property
    def context(self) -> Dict[str, Any]:
        """兼容 ContextManager 接口"""
        return self._variables
    
    # ==================== 类型转换 ====================
    
    def _convert_type(self, value: Any, var_type: str) -> Any:
        """
        类型转换
        
        Args:
            value: 原始值
            var_type: 目标类型
        
        Returns:
            转换后的值
        """
        if var_type == "auto":
            return self._auto_detect_type(value)
        
        try:
            if var_type == "int":
                return int(float(str(value)))  # 支持 "10.0" -> 10
            
            elif var_type == "float":
                return float(value)
            
            elif var_type == "bool":
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on")
                return bool(value)
            
            elif var_type == "str":
                return str(value)
            
            elif var_type == "list":
                if isinstance(value, list):
                    return value
                if isinstance(value, str):
                    value = value.strip()
                    if value.startswith("["):
                        return json.loads(value)
                    # 逗号分隔
                    return [v.strip() for v in value.split(",") if v.strip()]
                return list(value)
            
            elif var_type == "dict":
                if isinstance(value, dict):
                    return value
                if isinstance(value, str):
                    return json.loads(value)
                return dict(value)
        
        except Exception as e:
            logger.warning(f"⚠️ Type conversion failed: {value} -> {var_type} | Error: {e}")
            return value
        
        return value
    
    def _auto_detect_type(self, value: Any) -> Any:
        """
        自动类型推断
        
        优先级：保持原类型 > int > float > bool > dict/list > str
        """
        # 已经是目标类型
        if isinstance(value, (int, float, bool, list, dict)) and not isinstance(value, str):
            return value
        
        if not isinstance(value, str):
            return value
        
        value_str = value.strip()
        
        # 空字符串
        if not value_str:
            return ""
        
        # Bool
        if value_str.lower() in ("true", "false"):
            return value_str.lower() == "true"
        
        # Int
        try:
            if value_str.isdigit() or (value_str.startswith("-") and value_str[1:].isdigit()):
                return int(value_str)
        except:
            pass
        
        # Float
        try:
            if "." in value_str or "e" in value_str.lower():
                float_val = float(value_str)
                return float_val
        except:
            pass
        
        # JSON (List/Dict)
        if value_str.startswith(("[", "{")):
            try:
                return json.loads(value_str)
            except:
                pass
        
        # Default: String
        return value_str
    
    # ==================== 嵌套访问 ====================
    
    def _get_nested(self, key: str, default: Any = None) -> Any:
        """
        嵌套访问 (Dot Notation)
        
        例如: "User.Address.City" -> self._variables["User"]["Address"]["City"]
        """
        parts = key.split(".")
        current = self._variables
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                try:
                    index = int(part)
                    current = current[index]
                except (ValueError, IndexError):
                    return default
            else:
                return default
        
        return current
    
    def _set_nested(self, key: str, value: Any) -> bool:
        """
        嵌套设置 (Dot Notation)
        
        例如: "User.Address.City" = "NYC"
        """
        parts = key.split(".")
        
        # 确保根键存在
        root_key = parts[0]
        if root_key not in self._variables:
            self._variables[root_key] = {}
        
        current = self._variables
        
        # 遍历到倒数第二层
        for i, part in enumerate(parts[:-1]):
            if isinstance(current, dict):
                if part not in current:
                    current[part] = {}
                current = current[part]
            elif isinstance(current, list):
                try:
                    index = int(part)
                    current = current[index]
                except (ValueError, IndexError):
                    return False
            else:
                return False
        
        # 设置最终值
        final_key = parts[-1]
        if isinstance(current, dict):
            current[final_key] = value
            return True
        elif isinstance(current, list):
            try:
                index = int(final_key)
                current[index] = value
                return True
            except (ValueError, IndexError):
                return False
        
        return False
    
    # ==================== 变量注入 ====================
    
    def inject_variables(self, text: str, preserve_type: bool = False) -> Union[str, Any]:
        """
        变量注入：将 ${Key} 格式的占位符替换为变量值
        
        Args:
            text: 包含变量占位符的文本
            preserve_type: 如果模板只有一个 ${Key}，是否保留原始类型
        
        Returns:
            替换后的文本，或原始类型对象 (当 preserve_type=True)
        
        Examples:
            inject_variables("Hello ${Name}")         # -> "Hello John"
            inject_variables("${Count}", True)        # -> 10 (int)
            inject_variables("${User}", True)         # -> {"Name": "John"} (dict)
            inject_variables("Value: ${Count}")       # -> "Value: 10" (str)
        """
        if not text:
            return text
        
        text_str = str(text)
        
        # 特殊情况：只有一个变量占位符，且需要保留类型
        if preserve_type:
            single_var_match = re.fullmatch(r"\$\{(\w+(?:\.\w+)*)\}", text_str.strip())
            if single_var_match:
                key = single_var_match.group(1)
                value = self.get_variable(key)
                if value is not None:
                    return value
        
        # 正则匹配 ${...} 模式 (支持 Dot Notation)
        pattern = r"\$\{(\w+(?:\.\w+)*)\}"
        
        def replacer(match):
            key = match.group(1)
            value = self.get_variable(key)
            
            if value is not None:
                return str(value)
            
            # 大小写不敏感回退
            key_lower = key.lower()
            for k in self._variables:
                if k.lower() == key_lower:
                    logger.warning(f"⚠️ Variable Case Mismatch: '${{{key}}}' -> Found '{k}'")
                    return str(self._variables[k])
            
            logger.warning(f"⚠️ Variable Not Found: '${{{key}}}'")
            return match.group(0)
        
        return re.sub(pattern, replacer, text_str)
    
    def evaluate_expression(self, expr: str) -> Any:
        """
        表达式求值：支持 eval: 前缀的 Python 表达式
        
        Args:
            expr: 表达式字符串（可能以 "eval:" 开头）
        
        Returns:
            求值结果 (保留类型)
        
        Examples:
            evaluate_expression("eval: ${Count} + 1")    # -> 11 (int)
            evaluate_expression("eval: float(${Price}) * 0.8")  # -> float
            evaluate_expression("${Name}")               # -> "John"
        """
        if not expr:
            return expr
        
        expr_str = str(expr).strip()
        
        # 检查是否是 eval 表达式
        if expr_str.lower().startswith("eval:"):
            raw_expr = expr_str[5:].strip()
            
            # 先替换变量 (保留类型)
            injected_expr = self._inject_for_eval(raw_expr)
            
            try:
                allowed_names = {
                    "float": float, "int": int, "str": str,
                    "round": round, "abs": abs, "min": min,
                    "max": max, "len": len, "sum": sum,
                    "list": list, "dict": dict, "bool": bool,
                    "True": True, "False": False, "None": None,
                }
                result = eval(injected_expr, {"__builtins__": {}}, allowed_names)
                logger.debug(f"📐 Expression: {raw_expr} → {result}")
                return result
            except Exception as e:
                logger.warning(f"⚠️ Expression eval failed: {raw_expr} | Error: {e}")
                return expr
        
        # 普通变量替换 (保留类型)
        return self.inject_variables(expr_str, preserve_type=True)
    
    def _inject_for_eval(self, expr: str) -> str:
        """
        为 eval 表达式注入变量 (保留数值类型的字面量)
        """
        pattern = r"\$\{(\w+(?:\.\w+)*)\}"
        
        def replacer(match):
            key = match.group(1)
            value = self.get_variable(key)
            
            if value is None:
                return "None"
            
            # 数值直接返回
            if isinstance(value, (int, float)):
                return str(value)
            
            # 布尔
            if isinstance(value, bool):
                return "True" if value else "False"
            
            # 字符串包裹引号
            if isinstance(value, str):
                # 转义引号
                escaped = value.replace("\\", "\\\\").replace("'", "\\'")
                return f"'{escaped}'"
            
            # 其他复杂类型用 repr
            return repr(value)
        
        return re.sub(pattern, replacer, expr)
    
    # ==================== 结果捕获语法解析 ====================
    
    @staticmethod
    def parse_capture_syntax(params: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        解析结果捕获语法
        
        格式: "pattern -> ${VarName}" 或 "pattern -> ${VarName}:regex"
        
        Args:
            params: 参数字符串
        
        Returns:
            Tuple[str, Optional[str], Optional[str]]:
                (清理后的参数, 捕获变量名, 可选的正则表达式)
        
        Examples:
            "Hello World"                    -> ("Hello World", None, None)
            "Price: \\d+ -> ${CurrentPrice}" -> ("Price: \\d+", "CurrentPrice", None)
            "ID: (\\d+) -> ${ItemID}:1"      -> ("ID: (\\d+)", "ItemID", "1")
        """
        if " -> ${" not in params:
            return params.strip(), None, None
        
        # 分割主参数和捕获部分
        parts = params.rsplit(" -> ${", 1)
        main_param = parts[0].strip()
        
        # 解析捕获部分 "VarName}" 或 "VarName}:regex"
        capture_part = parts[1]
        
        if "}:" in capture_part:
            var_and_regex = capture_part.split("}:", 1)
            var_name = var_and_regex[0].strip()
            regex_pattern = var_and_regex[1].strip()
        elif capture_part.endswith("}"):
            var_name = capture_part[:-1].strip()
            regex_pattern = None
        else:
            var_name = capture_part.strip()
            regex_pattern = None
        
        return main_param, var_name, regex_pattern
    
    def capture_result(
        self,
        full_text: str,
        var_name: str,
        regex_pattern: Optional[str] = None
    ) -> bool:
        """
        捕获结果到变量
        
        Args:
            full_text: 完整的 OCR/响应文本
            var_name: 目标变量名
            regex_pattern: 可选的正则表达式 (捕获组1)
        
        Returns:
            bool: 捕获成功返回 True
        """
        if not var_name:
            return False
        
        captured_value = full_text
        
        # 如果有正则，提取匹配
        if regex_pattern:
            try:
                match = re.search(regex_pattern, full_text)
                if match:
                    # 优先使用捕获组
                    if match.groups():
                        captured_value = match.group(1)
                    else:
                        captured_value = match.group(0)
                else:
                    logger.warning(f"⚠️ Regex '{regex_pattern}' no match in text")
                    return False
            except re.error as e:
                logger.error(f"❌ Invalid regex: {regex_pattern} | Error: {e}")
                return False
        
        # 自动类型推断并存储
        self.set_variable(var_name, captured_value, "auto")
        logger.info(f"📥 Captured: ${{{var_name}}} = {captured_value}")
        return True


# ==================== 向后兼容别名 ====================

# 保持与 ContextManager 的兼容性
ContextManager = VariableStore
