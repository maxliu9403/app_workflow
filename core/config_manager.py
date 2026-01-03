"""
配置管理器
==========

封装 YAML 配置文件的读写操作
"""

from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml


class ConfigManager:
    """
    配置管理器
    
    管理 YAML 格式的配置文件（坐标配置等）
    """
    
    def __init__(self, default_path: Optional[Path] = None):
        self.config_path: Optional[Path] = default_path
        self.config_data: Dict[str, Any] = {}
        self._modified = False
    
    def set_path(self, path: Union[str, Path]) -> None:
        """设置配置文件路径"""
        self.config_path = Path(path)
    
    def load(self, path: Optional[Union[str, Path]] = None) -> bool:
        """
        加载配置文件
        
        Args:
            path: 可选的配置文件路径
            
        Returns:
            bool: 加载成功返回 True
        """
        if path:
            self.config_path = Path(path)
        
        if not self.config_path or not self.config_path.exists():
            self.config_data = {}
            return False
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config_data = yaml.safe_load(f) or {}
            self._modified = False
            return True
        except Exception:
            self.config_data = {}
            return False
    
    def save(self, path: Optional[Union[str, Path]] = None) -> bool:
        """
        保存配置文件
        
        Args:
            path: 可选的保存路径
            
        Returns:
            bool: 保存成功返回 True
        """
        save_path = Path(path) if path else self.config_path
        
        if not save_path:
            return False
        
        try:
            # 确保目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(save_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self.config_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            self._modified = False
            return True
        except Exception:
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config_data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        self.config_data[key] = value
        self._modified = True
    
    def get_nested(self, *keys, default: Any = None) -> Any:
        """获取嵌套配置值"""
        current = self.config_data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return default
            if current is None:
                return default
        return current
    
    def set_nested(self, *keys, value: Any) -> None:
        """设置嵌套配置值"""
        if len(keys) < 1:
            return
        
        current = self.config_data
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
        self._modified = True
    
    def is_modified(self) -> bool:
        """检查是否有未保存的修改"""
        return self._modified
    
    def get_path(self) -> Optional[Path]:
        """获取当前配置文件路径"""
        return self.config_path
    
    def to_dict(self) -> Dict[str, Any]:
        """返回配置数据的字典副本"""
        return dict(self.config_data)
    
    @staticmethod
    def find_default_yaml() -> Optional[Path]:
        """查找默认的 YAML 配置文件"""
        candidates = [
            Path(r"d:\Carousell_Auto\config\coordinates.yaml"),
            Path(__file__).parent.parent / "config" / "coordinates.yaml",
            Path.cwd() / "config" / "coordinates.yaml",
        ]
        
        for path in candidates:
            if path.exists():
                return path
        
        return None
