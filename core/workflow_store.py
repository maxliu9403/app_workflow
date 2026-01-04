from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
import uuid
import json
import logging

logger = logging.getLogger(__name__)

@dataclass
class WorkflowNodeModel:
    """
    Data Model for a single node in the workflow graph.
    Decoupled from UI logic.
    """
    id: str
    action_type: str
    x: float
    y: float
    # Parameters for the action (e.g. text to type, coordinates)
    params: Dict[str, Any] = field(default_factory=dict)
    # Graph Topology
    inputs: List[str] = field(default_factory=list)  # Connection Node IDs (Incoming)
    outputs: List[str] = field(default_factory=list) # Connection Node IDs (Outgoing)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action_type": self.action_type,
            "x": self.x,
            "y": self.y,
            "params": self.params,
            "inputs": self.inputs,
            "outputs": self.outputs
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowNodeModel':
        return cls(
            id=data["id"],
            action_type=data["action_type"],
            x=data["x"],
            y=data["y"],
            params=data.get("params", {}),
            inputs=data.get("inputs", []),
            outputs=data.get("outputs", [])
        )

class WorkflowStore:
    """
    Central State Store for the Workflow Editor.
    Implements Observer pattern to notify UI of changes.
    """
    def __init__(self):
        self.nodes: Dict[str, WorkflowNodeModel] = {}
        self._observers: List[Callable[[str, Any], None]] = []
        
    def add_observer(self, callback: Callable[[str, Any], None]):
        """Register a callback for state changes: func(event_type, data)"""
        self._observers.append(callback)

    def _notify(self, event: str, data: Any = None):
        for callback in self._observers:
            try:
                callback(event, data)
            except Exception as e:
                logger.error(f"Observer callback failed: {e}")

    # ==================== Actions ====================

    def add_node(self, action_type: str, x: float, y: float, params: Dict[str, Any] = None) -> WorkflowNodeModel:
        node_id = str(uuid.uuid4())
        node = WorkflowNodeModel(
            id=node_id, 
            action_type=action_type, 
            x=x, 
            y=y,
            params=params or {}
        )
        self.nodes[node_id] = node
        self._notify("node_added", node)
        return node

    def remove_node(self, node_id: str):
        if node_id in self.nodes:
            # 1. Disconnect all edges first
            node = self.nodes[node_id]
            # Copy lists to avoid concurrent modification issues during iteration
            for input_id in list(node.inputs):
                self.disconnect(input_id, node_id)
            for output_id in list(node.outputs):
                self.disconnect(node_id, output_id)
            
            # 2. Remove node
            del self.nodes[node_id]
            self._notify("node_removed", node_id)

    def connect(self, source_id: str, target_id: str) -> bool:
        if source_id not in self.nodes or target_id not in self.nodes:
            return False
            
        source = self.nodes[source_id]
        target = self.nodes[target_id]
        
        # Avoid duplicates
        if target_id in source.outputs:
            return False
            
        # Avoid self-loops (basic cycle check could be added here)
        if source_id == target_id:
            return False

        source.outputs.append(target_id)
        target.inputs.append(source_id)
        
        self._notify("connection_added", (source_id, target_id))
        return True

    def disconnect(self, source_id: str, target_id: str):
        if source_id in self.nodes:
            source = self.nodes[source_id]
            if target_id in source.outputs:
                source.outputs.remove(target_id)
                
        if target_id in self.nodes:
            target = self.nodes[target_id]
            if source_id in target.inputs:
                target.inputs.remove(source_id)
                
        self._notify("connection_removed", (source_id, target_id))

    def update_node_params(self, node_id: str, params: Dict[str, Any]):
        if node_id in self.nodes:
            self.nodes[node_id].params.update(params)
            self._notify("node_updated", self.nodes[node_id])

    def update_node_position(self, node_id: str, x: float, y: float):
        if node_id in self.nodes:
            self.nodes[node_id].x = x
            self.nodes[node_id].y = y
            # Optimization: Might not want to notify on every pixel drag. 
            # Could have a separate "node_moved" event.
            self._notify("node_moved", self.nodes[node_id])

    # ==================== Persistence ====================
    
    def save_to_json(self, filepath: str):
        data = {
            "version": "2.0", # Graph Format
            "nodes": [n.to_dict() for n in self.nodes.values()]
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_from_json(self, filepath: str):
        self.nodes.clear()
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        for n_data in data.get("nodes", []):
            node = WorkflowNodeModel.from_dict(n_data)
            self.nodes[node.id] = node
            
        self._notify("graph_loaded")
