import json
import os
import re
import sys
import importlib.util

class ExtensionManager:
    NODE_FILE = "custom_nodes.json"
    ACTION_FILE = "custom_actions.py"
    
    def __init__(self):
        self.ensure_files()
        
    def ensure_files(self):
        if not os.path.exists(self.NODE_FILE):
                with open(self.NODE_FILE, "w", encoding="utf-8") as f:
                    json.dump([], f)
        
        if not os.path.exists(self.ACTION_FILE):
            with open(self.ACTION_FILE, "w", encoding="utf-8") as f:
                f.write("# Custom Actions for V7 Editor\n")
                f.write("import time\nimport random\nimport logging\n\n")

    def load_nodes_metadata(self):
        """Load metadata for GUI (Name, Icon, Category, Shortcuts)"""
        try:
            with open(self.NODE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading custom nodes: {e}")
            return []

    def load_actions_map(self):
        """Return dict mapping {ActionName: FunctionName} for the runner"""
        try:
            nodes = self.load_nodes_metadata()
            mapping = {}
            for n in nodes:
                # Only include valid entries that have both name and function_name
                if "name" in n and "function_name" in n:
                    mapping[n["name"]] = n["function_name"]
            return mapping
        except Exception:
            return {}

    def load_custom_functions(self):
        """Import custom_actions.py and return {func_name: function}"""
        if not os.path.exists(self.ACTION_FILE):
            return {}
            
        try:
            # Dynamic import
            spec = importlib.util.spec_from_file_location("custom_actions", self.ACTION_FILE)
            module = importlib.util.module_from_spec(spec)
            sys.modules["custom_actions"] = module
            spec.loader.exec_module(module)
            
            funcs = {}
            for name, obj in module.__dict__.items():
                if callable(obj) and not name.startswith("__"):
                    funcs[name] = obj
            return funcs
        except Exception as e:
            print(f"Error importing custom actions: {e}")
            return {}

    def import_extension(self, json_str: str) -> tuple[bool, str]:
        """
        Parse JSON payload, append code to custom_actions.py, 
        and save metadata to custom_nodes.json.
        """
        try:
            data = json.loads(json_str)
            name = data.get("name")
            code = data.get("python_code")
            
            if not name or not code:
                return False, "Missing 'name' or 'python_code'"

            # Extract function name
            match = re.search(r"def\s+(\w+)\s*\(", code)
            if not match:
                return False, "Could not find 'def function_name(...' in code"
            func_name = match.group(1)
            
            data["function_name"] = func_name
            
            # Clean data for JSON storage (runtime params)
            store_data = data.copy()
            if "python_code" in store_data:
                del store_data["python_code"]
                
            # 1. Append Code
            with open(self.ACTION_FILE, "a", encoding="utf-8") as f:
                f.write("\n\n# Action: " + name + "\n")
                f.write(code + "\n")
                
            # 2. Update JSON
            nodes = self.load_nodes_metadata()
            # Remove existing if same name (overwrite)
            nodes = [n for n in nodes if n["name"] != name]
            nodes.append(store_data)
            
            with open(self.NODE_FILE, "w", encoding="utf-8") as f:
                json.dump(nodes, f, indent=2, ensure_ascii=False)
                
            return True, f"Successfully imported '{name}'"
        except json.JSONDecodeError:
            return False, "Invalid JSON format"
        except Exception as e:
            return False, str(e)

    def delete_node(self, name: str) -> bool:
        """Remove node from metadata (Function code remains but is orphaned)"""
        try:
            nodes = self.load_nodes_metadata()
            new_nodes = [n for n in nodes if n["name"] != name]
            if len(new_nodes) == len(nodes):
                return False # Not found
            
            with open(self.NODE_FILE, "w", encoding="utf-8") as f:
                json.dump(new_nodes, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Delete failed: {e}")
            return False
