"""
V10.3: Parameter Serializer
============================

Converts between UI-friendly form values and internal params string format.
Enables low-code experience by hiding complex syntax from users.

Usage:
    from core.param_serializer import ParamSerializer
    
    # UI form → internal params
    params = ParamSerializer.to_internal("Check Text", {
        "target": "登录成功",
        "operator": "包含",
        "capture_to": "Result"
    })
    # → "op:Contains|登录成功 -> ${Result}"
    
    # Internal params → UI form
    values = ParamSerializer.to_form("Check Text", "op:Contains|登录成功 -> ${Result}")
    # → {"target": "登录成功", "operator": "包含", "capture_to": "Result"}
"""

import re
from typing import Any, Dict, Optional


class ParamSerializer:
    """
    Bidirectional converter between UI form values and internal params string.
    """
    
    # Operator mapping for Check Text / IF
    OPERATOR_MAP = {
        "包含": "Contains",
        "不包含": "NotContains",
        "等于": "Equals",
        "不等于": "NotEquals",
    }
    OPERATOR_MAP_REVERSE = {v: k for k, v in OPERATOR_MAP.items()}
    
    @classmethod
    def to_internal(cls, action_type: str, form_values: Dict[str, Any]) -> str:
        """
        Convert UI form values to internal params string.
        
        Args:
            action_type: Node action type (e.g. "Check Text")
            form_values: Dict from UI form widgets
            
        Returns:
            Internal params string for workflow JSON
        """
        if action_type == "Check Text":
            return cls._check_text_to_internal(form_values)
        elif action_type in ("IF (Check Text)",):
            return cls._if_check_text_to_internal(form_values)
        elif action_type == "Wait Time":
            return cls._wait_time_to_internal(form_values)
        elif action_type == "Set Variable":
            return cls._set_variable_to_internal(form_values)
        elif action_type == "LOOP LIST":
            return cls._loop_list_to_internal(form_values)
        elif action_type == "Load Excel Data":
            return cls._load_excel_to_internal(form_values)
        elif action_type == "HTTP Request":
            return cls._http_request_to_internal(form_values)
        elif action_type in ("Wait Text", "Wait Until Disappear"):
            return cls._wait_text_to_internal(form_values)
        elif action_type in ("Input Text (Base64)", "Input Text (Native)", "Click Text"):
            return form_values.get("text", "") or form_values.get("target", "")
        elif action_type in ("Swipe", "Long Press"):
            return form_values.get("duration", "1.0")
        elif action_type == "LOOP (Count)":
            return form_values.get("count", "3")
        elif action_type == "LOOP (Until Text)":
            return form_values.get("target", "")
        elif action_type == "Print Variable":
            var = form_values.get("var_name", "")
            if var and not var.startswith("${"):
                var = f"${{{var}}}"
            return var
        else:
            # Default: return first non-empty value or empty string
            for v in form_values.values():
                if v:
                    return str(v)
            return ""
    
    @classmethod
    def to_form(cls, action_type: str, params: str) -> Dict[str, Any]:
        """
        Parse internal params string to UI form values.
        
        Args:
            action_type: Node action type
            params: Internal params string
            
        Returns:
            Dict of form field values
        """
        if action_type == "Check Text":
            return cls._check_text_to_form(params)
        elif action_type in ("IF (Check Text)",):
            return cls._if_check_text_to_form(params)
        elif action_type == "Wait Time":
            return {"seconds": params}
        elif action_type == "Set Variable":
            return cls._set_variable_to_form(params)
        elif action_type == "LOOP LIST":
            return cls._loop_list_to_form(params)
        elif action_type == "Load Excel Data":
            return cls._load_excel_to_form(params)
        elif action_type == "HTTP Request":
            return cls._http_request_to_form(params)
        elif action_type in ("Wait Text", "Wait Until Disappear"):
            return cls._wait_text_to_form(params)
        elif action_type in ("Input Text (Base64)", "Input Text (Native)"):
            return {"text": params}
        elif action_type == "Click Text":
            return {"target": params}
        elif action_type in ("Swipe", "Long Press"):
            return {"duration": params or "1.0"}
        elif action_type == "LOOP (Count)":
            return {"count": params or "3"}
        elif action_type == "LOOP (Until Text)":
            return {"target": params}
        elif action_type == "Print Variable":
            var = params
            if var.startswith("${") and var.endswith("}"):
                var = var[2:-1]
            return {"var_name": var}
        else:
            return {"value": params}
    
    # ==================== Check Text ====================
    
    @classmethod
    def _check_text_to_internal(cls, values: Dict) -> str:
        """Convert Check Text form values to internal format"""
        target = values.get("target", "")
        operator = values.get("operator", "包含")
        capture = values.get("capture_to", "")
        
        # Build params string
        op_code = cls.OPERATOR_MAP.get(operator, "Contains")
        
        # Simple contains doesn't need op: prefix
        if op_code == "Contains" and not capture:
            return target
        
        result = f"op:{op_code}|{target}"
        
        if capture:
            # Ensure variable format
            if not capture.startswith("${"):
                capture = f"${{{capture}}}"
            result += f" -> {capture}"
        
        return result
    
    @classmethod
    def _check_text_to_form(cls, params: str) -> Dict:
        """Parse Check Text params to form values"""
        result = {"target": "", "operator": "包含", "capture_to": ""}
        
        # Check for capture syntax
        if " -> " in params:
            main_part, capture = params.split(" -> ", 1)
            if capture.startswith("${") and capture.endswith("}"):
                capture = capture[2:-1]
            result["capture_to"] = capture
            params = main_part
        
        # Check for operator syntax
        if params.startswith("op:"):
            match = re.match(r"op:(\w+)\|(.+)", params)
            if match:
                op_code, target = match.groups()
                result["operator"] = cls.OPERATOR_MAP_REVERSE.get(op_code, "包含")
                result["target"] = target
        else:
            result["target"] = params
        
        return result
    
    # ==================== IF (Check Text) ====================
    
    @classmethod
    def _if_check_text_to_internal(cls, values: Dict) -> str:
        """Convert IF Check Text form to internal"""
        condition = values.get("condition", "")
        operator = values.get("operator", "包含")
        
        if operator == "不包含":
            return f"op:NotContains|{condition}"
        return condition
    
    @classmethod
    def _if_check_text_to_form(cls, params: str) -> Dict:
        """Parse IF Check Text params"""
        if params.startswith("op:NotContains|"):
            return {"condition": params[15:], "operator": "不包含"}
        return {"condition": params, "operator": "包含"}
    
    # ==================== Wait Time ====================
    
    @classmethod
    def _wait_time_to_internal(cls, values: Dict) -> str:
        """Convert Wait Time form to internal"""
        return values.get("seconds", "1")
    
    # ==================== Set Variable ====================
    
    @classmethod
    def _set_variable_to_internal(cls, values: Dict) -> str:
        """Convert Set Variable form to internal"""
        key = values.get("key", "")
        value_type = values.get("value_type", "文本")
        value = values.get("value", "")
        
        if value_type == "表达式":
            return f"{key} = eval: {value}"
        return f"{key} = {value}"
    
    @classmethod
    def _set_variable_to_form(cls, params: str) -> Dict:
        """Parse Set Variable params"""
        if " = eval: " in params:
            key, value = params.split(" = eval: ", 1)
            return {"key": key.strip(), "value_type": "表达式", "value": value}
        elif " = " in params:
            key, value = params.split(" = ", 1)
            return {"key": key.strip(), "value_type": "文本", "value": value}
        return {"key": "", "value_type": "文本", "value": params}
    
    # ==================== LOOP LIST ====================
    
    @classmethod
    def _loop_list_to_internal(cls, values: Dict) -> str:
        """Convert LOOP LIST form to internal"""
        list_var = values.get("list_var", "")
        item_var = values.get("item_var", "Item")
        
        # Ensure list_var has ${}
        if list_var and not list_var.startswith("${"):
            list_var = f"${{{list_var}}}"
        
        return f"{list_var} as ${{{item_var}}}"
    
    @classmethod
    def _loop_list_to_form(cls, params: str) -> Dict:
        """Parse LOOP LIST params"""
        match = re.match(r"(\$\{[^}]+\})\s+as\s+\$\{([^}]+)\}", params)
        if match:
            return {"list_var": match.group(1), "item_var": match.group(2)}
        return {"list_var": "", "item_var": "Item"}
    
    # ==================== Load Excel Data ====================
    
    @classmethod
    def _load_excel_to_internal(cls, values: Dict) -> str:
        """Convert Load Excel form to internal"""
        file_path = values.get("file_path", "")
        target_var = values.get("target_var", "")
        
        if target_var and not target_var.startswith("${"):
            target_var = f"${{{target_var}}}"
        
        return f"{file_path} -> {target_var}"
    
    @classmethod
    def _load_excel_to_form(cls, params: str) -> Dict:
        """Parse Load Excel params"""
        if " -> " in params:
            path, var = params.split(" -> ", 1)
            if var.startswith("${") and var.endswith("}"):
                var = var[2:-1]
            return {"file_path": path.strip(), "target_var": var}
        return {"file_path": params, "target_var": ""}
    
    # ==================== Wait Text ====================
    
    @classmethod
    def _wait_text_to_internal(cls, values: Dict) -> str:
        """Convert Wait Text form to internal"""
        target = values.get("target", "")
        timeout = values.get("timeout", "30")
        
        if timeout and timeout != "30":
            return f"{target}|timeout={timeout}"
        return target
    
    @classmethod
    def _wait_text_to_form(cls, params: str) -> Dict:
        """Parse Wait Text params"""
        if "|timeout=" in params:
            target, timeout_part = params.split("|timeout=", 1)
            return {"target": target, "timeout": timeout_part}
        return {"target": params, "timeout": "30"}
    
    # ==================== HTTP Request ====================
    
    @classmethod
    def _http_request_to_internal(cls, values: Dict) -> str:
        """Convert HTTP Request form to internal JSON"""
        import json
        
        data = {
            "url": values.get("url", ""),
            "method": values.get("method", "GET"),
        }
        
        body = values.get("body", "")
        if body:
            try:
                data["body"] = json.loads(body)
            except:
                data["body"] = body
        
        capture = values.get("capture_to", "")
        if capture:
            if not capture.startswith("${"):
                capture = f"${{{capture}}}"
            data["capture_to"] = capture
        
        return json.dumps(data, ensure_ascii=False)
    
    @classmethod
    def _http_request_to_form(cls, params: str) -> Dict:
        """Parse HTTP Request JSON params"""
        import json
        
        try:
            data = json.loads(params)
            result = {
                "url": data.get("url", ""),
                "method": data.get("method", "GET"),
            }
            
            body = data.get("body")
            if body:
                result["body"] = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)
            else:
                result["body"] = ""
            
            capture = data.get("capture_to", "")
            if capture and capture.startswith("${") and capture.endswith("}"):
                capture = capture[2:-1]
            result["capture_to"] = capture
            
            return result
        except:
            return {"url": params, "method": "GET", "body": "", "capture_to": ""}
