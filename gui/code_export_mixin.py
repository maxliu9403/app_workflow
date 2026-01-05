"""
V10.4: Code Export Mixin (Gemini Optimized)
===========================================

Provides the UI for exporting workflows to Python code.
Features:
- "Export Python" button in Action Bar
- Preview Dialog with Syntax Highlighting (Simulated)
- Copy / Save As functionality
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading

from core.script_generator import ScriptGenerator


class CodeExportMixin:
    """
    Mixin to add Python Code Export capabilities to the GUI Manager.
    """

    def _build_code_export_ui(self, parent: ctk.CTkFrame):
        """Add Export button to the provided frame (Action Bar)"""
        btn = ctk.CTkButton(
            parent,
            text="📤 导出 Python",
            width=30,  # Compact if mainly icon
            fg_color="#4CAF50",
            hover_color="#388E3C",
            command=self._on_export_python_click
        )
        btn.pack(side="left", padx=2)
        # Store reference if needed
        self.btn_export_python = btn

    def _on_export_python_click(self):
        """Handle Export Button Click"""
        if not hasattr(self, 'orch_nodes') or not self.orch_nodes:
            self.gen_log("⚠️ No nodes to export.")
            return

        # 1. Generate Code
        try:
            # Sorted nodes list (assuming step_index reflects order, or using internal logic)
            # In Vinted Console, nodes are in orch_nodes dict, connections define order...
            # For simplicity in V1 (Linear), we sort by Y position or step name??
            # Actually workflow runner executes in order. Let's just grab sorted list.
            
            # Prepare Steps List for Generator
            # 1. Sort nodes (Use topological sort if available for correct execution order)
            sorted_nodes = []
            if hasattr(self, '_orch_topological_sort'):
                try:
                    sorted_nodes = self._orch_topological_sort()
                except Exception as e:
                    self.gen_log(f"⚠️ Topological sort failed, using simple sort: {e}")
                    sorted_nodes = []

            # Fallback if topo sort missing or failed
            if not sorted_nodes and hasattr(self, 'orch_nodes'):
                sorted_nodes = list(self.orch_nodes.values())
                # Try sorting by Step Name (Step 1, Step 2...)
                try:
                    import re
                    sorted_nodes.sort(key=lambda n: int(re.search(r'(\d+)', getattr(n, 'step_name', '0')).group(1)))
                except:
                    pass # Keep insertion/dict order if parse fails

            # 2. Convert to dicts matching ScriptGenerator schema
            step_list = []
            for node in sorted_nodes:
                step_data = {
                    "action_type": node.action_type,
                    "step_name": getattr(node, "step_name", ""),
                    "params": node.params, # Internal param string
                    "coords": node.coords,
                    "context": getattr(node, "context", "")
                }
                step_list.append(step_data)

            generator = ScriptGenerator()
            code = generator.generate(step_list)
            
            # 2. Show Preview Dialog
            self._show_code_preview_dialog(code)
            
        except Exception as e:
            self.gen_log(f"❌ Export failed: {e}")
            import traceback
            traceback.print_exc()

    def _show_code_preview_dialog(self, code: str):
        """Open a TopLevel dialog to preview/copy/save code"""
        top = ctk.CTkToplevel(self.root if hasattr(self, 'root') else None)
        top.title("🐍 Python Script Preview")
        top.geometry("800x600")
        
        # Make modal-ish
        top.transient(self.root)
        top.lift()
        
        # 1. Text Area (ReadOnly by default?)
        text_frame = ctk.CTkFrame(top)
        text_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        textbox = ctk.CTkTextbox(
            text_frame, 
            font=("Consolas", 12), 
            wrap="none" # No wrapping for code
        )
        textbox.pack(fill="both", expand=True)
        textbox.insert("1.0", code)
        
        # Simple Syntax Highlighting (Keywords)
        # Note: CTkTextbox tags support is limited compared to tk.Text
        # But we can try using the underlying tk widget
        self._apply_syntax_highlighting(textbox, code)
        
        # 2. Button Bar
        btn_frame = ctk.CTkFrame(top, height=50)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        ctk.CTkButton(
            btn_frame, text="📋 复制到剪贴板", 
            command=lambda: self._copy_to_clipboard(top, code)
        ).pack(side="left", padx=5, pady=5)
        
        ctk.CTkButton(
            btn_frame, text="💾 另存为...", 
            command=lambda: self._save_code_to_file(top, code)
        ).pack(side="left", padx=5, pady=5)
        
        ctk.CTkButton(
            btn_frame, text="关闭", 
            fg_color="#555",
            command=top.destroy
        ).pack(side="right", padx=5, pady=5)

    def _copy_to_clipboard(self, parent, text):
        parent.clipboard_clear()
        parent.clipboard_append(text)
        messagebox.showinfo("Success", "Code copied to clipboard!", parent=parent)

    def _save_code_to_file(self, parent, text):
        path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python Script", "*.py"), ("All Files", "*.*")],
            parent=parent
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                messagebox.showinfo("Success", f"Saved to {path}", parent=parent)
            except Exception as e:
                messagebox.showerror("Error", f"Save failed: {e}", parent=parent)

    def _apply_syntax_highlighting(self, ctk_textbox, code):
        """Apply basic colors to keywords using underlying TK widget"""
        # CTkTextbox._textbox is the tkinter.Text widget
        tk_text = ctk_textbox._textbox 
        
        # Define Tags
        tk_text.tag_config("keyword", foreground="#CC7832") # Orange
        tk_text.tag_config("string", foreground="#6A8759") # Green
        tk_text.tag_config("comment", foreground="#808080") # Grey
        tk_text.tag_config("def", foreground="#FFC66D") # Yellow
        
        # Regex Patterns
        import re
        
        # 1. Keywords
        keywords = r"\b(def|class|import|from|return|if|else|elif|try|except|for|in|while|pass|break|continue|and|or|not)\b"
        self._highlight_pattern(tk_text, keywords, "keyword", code)
        
        # 2. Strings (Double and Single quotes)
        strings = r"(\".*?\"|'.*?')"
        self._highlight_pattern(tk_text, strings, "string", code)

        # 3. Comments
        comments = r"(#.*)"
        self._highlight_pattern(tk_text, comments, "comment", code)
        
        # 4. Function definitions (def name)
        funcs = r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        self._highlight_pattern(tk_text, funcs, "def", code, group=1)

    def _highlight_pattern(self, tk_text, pattern, tag, code, group=0):
        """Helper to apply tag to all regex matches"""
        import re
        for match in re.finditer(pattern, code):
            start = match.start(group)
            end = match.end(group)
            
            # Convert char index to line.col
            # Note: This simple conversion assumes code matches text widget content exactly
            # Tkinter uses 1.0 for first char
            
            # Efficient way: rely on tk_text.search?
            # Or map indices. Let's map indices since we have the code string.
            
            start_idx = self._get_tk_index(code, start)
            end_idx = self._get_tk_index(code, end)
            
            tk_text.tag_add(tag, start_idx, end_idx)

    def _get_tk_index(self, code, char_index):
        """Convert 0-based char index to Tkinter line.col index"""
        # Count newlines up to char_index
        sub = code[:char_index]
        line = sub.count('\n') + 1
        col = len(sub) - sub.rfind('\n') - 1
        if col < 0: col = len(sub) # Case where no newline found
        return f"{line}.{col}"
