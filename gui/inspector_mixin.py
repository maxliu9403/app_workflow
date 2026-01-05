"""
V10.3: Inspector Mixin (Gemini Optimized)
=========================================

Handles the dynamic generation of the parameter inspector UI.
Decouples UI logic from the main GUI manager.

Features:
- Dynamic form generation based on NodeDefinition
- Two-way binding with ParamSerializer
- Support for multiple field types (text, select, file, variable)
"""

import customtkinter as ctk
import tkinter as tk
from typing import Dict, Any, Optional, List
from tkinter import filedialog
import json

from core.node_definitions import NODE_REGISTRY, NodeDefinition, ParamField, get_node
from core.param_serializer import ParamSerializer


class InspectorMixin:
    """
    Mixin for GUI Manager to handle dynamic node parameter inspection.
    Requires: self.gen_param_frame (ctk.CTkFrame)
    """

    def _init_inspector_vars(self):
        """Initialize inspector variables"""
        # Store current form variables: name -> ctk.Variable
        self.dynamic_form_vars: Dict[str, ctk.Variable] = {}
        # Store widget references for cleanup
        self.dynamic_widgets: List[ctk.CTkBaseClass] = []
        
    def _build_inspector_ui(self, parent: ctk.CTkFrame):
        """Build the dynamic inspector container"""
        self._init_inspector_vars()
        
        # Header
        ctk.CTkLabel(
            parent,
            text="📝 参数配置 (Dynamic)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        # Dynamic Content Container
        # Dynamic Content Container (Scrollable)
        self.inspector_content = ctk.CTkScrollableFrame(parent, fg_color="transparent", height=400)
        self.inspector_content.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        self.inspector_content.grid_columnconfigure(1, weight=1)

        # Hook into action change
        if hasattr(self, 'gen_action_var'):
            self.gen_action_var.trace_add("write", lambda *args: self._render_node_params(self.gen_action_var.get()))

    def _render_node_params(self, action_type: str):
        """
        Rebuild the inspector UI for the selected action.
        """
        # Clear existing widgets
        for widget in self.inspector_content.winfo_children():
            widget.destroy()
        self.dynamic_form_vars.clear()
        
        node = get_node(action_type)
        if not node:
            return

        # Render each field
        for i, field in enumerate(node.params):
            self._create_field_row(self.inspector_content, i, field)
            
        # Hook for value changes to update the internal param string
        # (This simulates the old binding to self.gen_param_var)
        self._bind_form_to_internal(action_type)

    def _create_field_row(self, parent, row: int, field: ParamField):
        """Create a single row for a parameter field"""
        # Label
        label_text = f"{field.label}:"
        if field.required:
            label_text += "*"
            
        ctk.CTkLabel(
            parent, 
            text=label_text,
            font=ctk.CTkFont(size=12)
        ).grid(row=row, column=0, sticky="nw", padx=5, pady=5)
        
        # Widget based on type
        if field.type == "select":
            var = ctk.StringVar(value=field.default)
            widget = ctk.CTkComboBox(
                parent,
                variable=var,
                values=field.options,
                width=200
            )
        elif field.type == "file":
            var = ctk.StringVar(value=field.default)
            widget = self._create_file_picker(parent, var, field.placeholder)
        elif field.type == "variable":
            var = ctk.StringVar(value=field.default)
            widget = ctk.CTkEntry(
                parent,
                textvariable=var,
                placeholder_text=field.placeholder or "${MyVar}"
            )
            # Todo: Add variable picker button
        elif field.type == "coords":
            # Coords are handled separately by the canvas, 
            # but we could show a "Reselect Region" button here
            var = ctk.StringVar(value="使用鼠标框选")
            widget = ctk.CTkLabel(parent, text="(请在右侧屏幕框选区域)", text_color="gray")
        else: # text, number, json
            var = ctk.StringVar(value=field.default)
            widget = ctk.CTkEntry(
                parent,
                textvariable=var,
                placeholder_text=field.placeholder
            )
        
        if field.type != "file" and field.type != "coords":
            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        
        # Help text
        if field.help_text:
            # Simple tooltip simulation via status bar or just a small label below?
            # For now, let's keep it clean.
            pass

        # Store variable
        if field.type != "coords":
            self.dynamic_form_vars[field.name] = var
            
            # Trace changes
            var.trace_add("write", lambda *args: self._on_form_change())

    def _create_file_picker(self, parent, var, placeholder):
        """Helper to create file picker widget group"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=parent.grid_size()[1]-1, column=1, sticky="ew", padx=0, pady=2)
        frame.grid_columnconfigure(0, weight=1)
        
        entry = ctk.CTkEntry(frame, textvariable=var, placeholder_text=placeholder)
        entry.grid(row=0, column=0, sticky="ew", padx=(5, 2))
        
        btn = ctk.CTkButton(
            frame, text="📂", width=30, 
            fg_color="#444", 
            command=lambda: self._pick_file(var)
        )
        btn.grid(row=0, column=1, sticky="e", padx=2)
        return frame

    def _pick_file(self, var: ctk.StringVar):
        path = filedialog.askopenfilename()
        if path:
            var.set(path)

    def _bind_form_to_internal(self, action_type: str):
        """
        When form changes, serialize to internal param string 
        and update the legacy self.gen_param_var for backward compatibility
        """
        pass # Implemented in _on_form_change

    def _on_form_change(self):
        """Callback when any form field changes"""
        # Get current action
        action_type = self.gen_action_var.get()
        if not action_type:
            return
            
        # Collect values
        values = {
            name: var.get() 
            for name, var in self.dynamic_form_vars.items()
        }
        
        # Serialize
        internal_param = ParamSerializer.to_internal(action_type, values)
        
        # Update legacy variable (this triggers the workflow step preview update)
        # We assume self.gen_param_var exists in the main class
        if hasattr(self, 'gen_param_var'):
            # Only update if changed to avoid circular loops if we implement bidirectional sync later
            if self.gen_param_var.get() != internal_param:
                self.gen_param_var.set(internal_param)
                
    def load_params_into_form(self, action_type: str, internal_param: str):
        """
        Reverse direction: load string params into the dynamic form
        (Used when clicking a step in the list to edit it)
        """
        # 1. Render the form first
        self._render_node_params(action_type)
        
        # 2. Parse values
        values = ParamSerializer.to_form(action_type, internal_param)
        
        # 3. Set variables (suppress callbacks to avoid loop?)
        for name, value in values.items():
            if name in self.dynamic_form_vars:
                # Direct set triggers trace -> _on_form_change -> to_internal
                # This ensures consistency
                self.dynamic_form_vars[name].set(str(value))
