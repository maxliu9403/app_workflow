"""
数据类型定义
============

包含所有核心数据结构：RoiPct, WorkflowNode 等
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass
class RoiPct:
    """
    百分比坐标区域
    
    使用 0.0-1.0 范围的百分比表示屏幕上的矩形区域
    """
    x1: float
    y1: float
    x2: float
    y2: float

    def normalized(self) -> "RoiPct":
        """返回标准化的 ROI（确保 x1 < x2, y1 < y2）"""
        x1 = float(min(self.x1, self.x2))
        x2 = float(max(self.x1, self.x2))
        y1 = float(min(self.y1, self.y2))
        y2 = float(max(self.y1, self.y2))
        return RoiPct(x1=x1, y1=y1, x2=x2, y2=y2)

    def clipped(self) -> "RoiPct":
        """返回裁剪到 [0, 1] 范围内的 ROI"""
        x1 = float(max(0.0, min(1.0, self.x1)))
        x2 = float(max(0.0, min(1.0, self.x2)))
        y1 = float(max(0.0, min(1.0, self.y1)))
        y2 = float(max(0.0, min(1.0, self.y2)))
        return RoiPct(x1=x1, y1=y1, x2=x2, y2=y2)

    def center(self) -> Tuple[float, float]:
        """返回中心点坐标"""
        r = self.normalized()
        return (float((r.x1 + r.x2) / 2.0), float((r.y1 + r.y2) / 2.0))
    
    def to_dict(self) -> Dict[str, float]:
        """转换为字典"""
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}
    
    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "RoiPct":
        """从字典创建"""
        return cls(
            x1=data.get("x1", 0),
            y1=data.get("y1", 0),
            x2=data.get("x2", 0),
            y2=data.get("y2", 0),
        )


@dataclass
class WorkflowNode:
    """
    工作流节点数据结构
    
    用于流程编排器中的可视化节点
    """
    id: str                                # 唯一标识
    action_type: str                       # 动作类型
    step_name: str = ""                    # 步骤名称
    params: str = ""                       # 参数
    context: str = ""                      # 上下文备注
    coords: Dict[str, float] = field(default_factory=lambda: {"x1": 0, "y1": 0, "x2": 0, "y2": 0})
    canvas_x: int = 100                    # 画布 X 位置
    canvas_y: int = 100                    # 画布 Y 位置
    retry_count: int = 0                   # 重试次数
    is_optional: bool = False              # 是否可选步骤
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于 JSON 导出）"""
        return {
            "step_name": self.step_name,
            "action_type": self.action_type,
            "params": self.params,
            "context": self.context,
            "coords": self.coords,
            "retry_count": self.retry_count,
            "is_optional": self.is_optional,
        }
    
    def to_export_dict(self, step_id: int) -> Dict[str, Any]:
        """转换为 WorkflowRunner 兼容的导出格式"""
        return {
            "step_id": step_id,
            "step_name": self.step_name,
            "action_type": self.action_type,
            "params": self.params,
            "context": self.context,
            "coords": self.coords,
            "retry_count": self.retry_count,
            "is_optional": self.is_optional,
        }
    
    @classmethod
    def from_dict(cls, node_id: str, data: Dict[str, Any]) -> "WorkflowNode":
        """从字典创建"""
        return cls(
            id=node_id,
            action_type=data.get("action_type", "Click Region"),
            step_name=data.get("step_name", ""),
            params=data.get("params", ""),
            context=data.get("context", ""),
            coords=data.get("coords", {"x1": 0, "y1": 0, "x2": 0, "y2": 0}),
            retry_count=data.get("retry_count", 0),
            is_optional=data.get("is_optional", False),
        )


@dataclass
class StepData:
    """
    步骤数据（用于步骤生成器）
    """
    step: str
    action: str
    param: str
    context: str
    coords: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "param": self.param,
            "context": self.context,
            "coords": self.coords,
        }
