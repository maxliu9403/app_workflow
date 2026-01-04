from dataclasses import dataclass, field
from typing import Dict, Any, Tuple

@dataclass
class RoiPct:
    x1: float
    y1: float
    x2: float
    y2: float

    def normalized(self) -> "RoiPct":
        x1 = float(min(self.x1, self.x2))
        x2 = float(max(self.x1, self.x2))
        y1 = float(min(self.y1, self.y2))
        y2 = float(max(self.y1, self.y2))
        return RoiPct(x1=x1, y1=y1, x2=x2, y2=y2)

    def clipped(self) -> "RoiPct":
        x1 = float(max(0.0, min(1.0, self.x1)))
        x2 = float(max(0.0, min(1.0, self.x2)))
        y1 = float(max(0.0, min(1.0, self.y1)))
        y2 = float(max(0.0, min(1.0, self.y2)))
        return RoiPct(x1=x1, y1=y1, x2=x2, y2=y2)

    def center(self) -> Tuple[float, float]:
        r = self.normalized()
        return (float((r.x1 + r.x2) / 2.0), float((r.y1 + r.y2) / 2.0))


@dataclass
class WorkflowNode:
    """工作流节点数据结构"""
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
            "id": self.id,
            "step_name": self.step_name,
            "action_type": self.action_type,
            "params": self.params,
            "context": self.context,
            "coords": self.coords,
            "canvas_x": self.canvas_x,
            "canvas_y": self.canvas_y,
            "retry_count": self.retry_count,
            "is_optional": self.is_optional,
        }
