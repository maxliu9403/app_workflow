
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk
from pathlib import Path
from typing import List, Optional
import os

class LogReplayFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.log_folder: Optional[Path] = None
        self.log_images: List[Path] = []
        self.log_index: int = -1
        self.log_tk_photo: Optional[ImageTk.PhotoImage] = None
        self.log_image_pil: Optional[Image.Image] = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top Bar
        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        top.grid_columnconfigure(2, weight=1)

        self.btn_load_folder = ctk.CTkButton(
            top,
            text="加载日志文件夹",
            command=self.load_log_folder,
        )
        self.btn_load_folder.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.log_folder_label = ctk.CTkLabel(top, text="未选择文件夹", text_color="#aaaaaa")
        self.log_folder_label.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        # Main Body
        body = ctk.CTkFrame(self)
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        # Left List
        left = ctk.CTkFrame(body, width=420)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="图片列表",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        list_container = ctk.CTkFrame(left)
        list_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        self.log_listbox = tk.Listbox(
            list_container,
            bg="#1f1f1f",
            fg="#dddddd",
            selectbackground="#2b6cb0",
            activestyle="none",
            highlightthickness=0,
            bd=0,
        )
        self.log_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(list_container, orient="vertical", command=self.log_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_listbox.configure(yscrollcommand=scrollbar.set)
        self.log_listbox.bind("<<ListboxSelect>>", lambda _e: self.on_log_list_select())

        # Right Image
        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=10)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.log_canvas = ctk.CTkCanvas(right, bg="#1f1f1f", highlightthickness=0)
        self.log_canvas.grid(row=0, column=0, sticky="nsew")
        self.log_canvas.bind("<Configure>", lambda _e: self.redraw_log_image())

        # Bottom Controls
        bottom = ctk.CTkFrame(self)
        bottom.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_prev = ctk.CTkButton(bottom, text="上一张", command=lambda: self.step_log(-1))
        self.btn_prev.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.log_index_label = ctk.CTkLabel(bottom, text="0 / 0")
        self.log_index_label.grid(row=0, column=1, sticky="ew", padx=10, pady=10)

        self.btn_next = ctk.CTkButton(bottom, text="下一张", command=lambda: self.step_log(1))
        self.btn_next.grid(row=0, column=2, sticky="ew", padx=10, pady=10)

    def load_log_folder(self) -> None:
        path = filedialog.askdirectory(title="选择日志文件夹", initialdir=str(Path.cwd()))
        if not path:
            return
        p = Path(path)
        self.log_folder = p
        self.log_folder_label.configure(text=str(p))

        self.log_images = sorted(list(p.glob("*.png")) + list(p.glob("*.jpg")))
        self.log_listbox.delete(0, tk.END)
        for img_path in self.log_images:
            self.log_listbox.insert(tk.END, img_path.name)

        if self.log_images:
            self.log_index = 0
            self.log_listbox.select_set(0)
            self.load_log_image(self.log_images[0])
            self.update_log_status()
        else:
            self.log_index = -1
            self.log_image_pil = None
            self.log_tk_photo = None
            self.log_canvas.delete("all")
            self.update_log_status()

    def on_log_list_select(self) -> None:
        sel = self.log_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.log_index = idx
        self.load_log_image(self.log_images[idx])
        self.update_log_status()

    def load_log_image(self, path: Path) -> None:
        try:
            self.log_image_pil = Image.open(path)
            self.redraw_log_image()
        except Exception as e:
            print(f"Error loading log image: {e}")

    def redraw_log_image(self) -> None:
        if self.log_image_pil is None:
            return
        
        canvas_w = self.log_canvas.winfo_width()
        canvas_h = self.log_canvas.winfo_height()
        if canvas_w < 5 or canvas_h < 5:
            return

        img_w, img_h = self.log_image_pil.size
        ratio = min(canvas_w / img_w, canvas_h / img_h)
        new_w = int(img_w * ratio)
        new_h = int(img_h * ratio)

        resized = self.log_image_pil.resize((new_w, new_h), Image.LANCZOS)
        self.log_tk_photo = ImageTk.PhotoImage(resized)

        self.log_canvas.delete("all")
        self.log_canvas.create_image(
            canvas_w // 2, canvas_h // 2,
            image=self.log_tk_photo,
            anchor="center"
        )

    def step_log(self, delta: int) -> None:
        if not self.log_images:
            return
        new_idx = self.log_index + delta
        if 0 <= new_idx < len(self.log_images):
            self.log_index = new_idx
            self.log_listbox.selection_clear(0, tk.END)
            self.log_listbox.select_set(new_idx)
            self.log_listbox.see(new_idx)
            self.load_log_image(self.log_images[new_idx])
            self.update_log_status()

    def update_log_status(self) -> None:
        total = len(self.log_images)
        current = self.log_index + 1 if total > 0 else 0
        self.log_index_label.configure(text=f"{current} / {total}")
