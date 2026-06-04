from __future__ import annotations

"""
ImageButtonBuilder — dialog for configuring a canvas image button.

Opens when the user clicks ⚡ on the Image component's 'canvas_button' handler.
Lets the user pick which Canvas widget to target, choose normal/hover/pressed
image keys, set (x, y) position, and name the tag. A live preview canvas in
the dialog shows the actual images and responds to clicks.
"""

import os
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from utils.ui_font import UI_FONT

_BG      = "#1e1e1e"
_PANEL   = "#252526"
_FLD_BG  = "#3c3c3c"
_FLD_FG  = "#cccccc"
_DIM     = "#888888"
_ACCENT  = "#007acc"
_BTN_BG  = "#094771"
_SEP     = "#3a3a3a"

_NONE_KEY = "(none)"   # sentinel shown in hover/pressed dropdowns when not configured


class ImageButtonBuilder(tk.Toplevel):
    """
    Modal dialog for building a canvas image button.

    On OK, calls on_confirm(config_dict) where config_dict has:
        canvas_id, tag, x, y, normal_key, hover_key, pressed_key
    If the user chose 'Create New Canvas', canvas_id == "__new__".
    """

    def __init__(
        self,
        parent: tk.Misc,
        comp_id: str,
        paths: list[str],
        canvas_ids: list[str],
        project_dir: str,
        on_confirm: Callable[[dict], None],
        on_create_canvas: Optional[Callable[[], str]] = None,
        preset_canvas_id: str = "",
        edit_config: Optional[dict] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Image Button Builder")
        self.resizable(False, False)
        self.configure(bg=_BG)
        self.transient(parent)
        self.grab_set()

        self._comp_id         = comp_id
        self._paths           = paths
        self._project_dir     = project_dir
        self._on_confirm      = on_confirm
        self._on_create_canvas = on_create_canvas
        self._canvas_ids      = canvas_ids
        self._preview_thumbs: list = []   # keep PhotoImages alive
        self._preview_normal  = None
        self._preview_hover   = None
        self._preview_pressed = None

        # Compute image stems for dropdowns
        self._stems = [os.path.splitext(os.path.basename(p))[0] for p in paths]
        self._is_multi = len(paths) > 1

        # Variables
        canvas_choices = list(canvas_ids) + ["＋ Create New Canvas"]
        init_canvas = preset_canvas_id if preset_canvas_id in canvas_ids else (canvas_ids[0] if canvas_ids else "")
        self._canvas_var  = tk.StringVar(value=init_canvas or (canvas_choices[0] if canvas_choices else ""))
        self._tag_var     = tk.StringVar(value="")
        self._x_var       = tk.StringVar(value="0")
        self._y_var       = tk.StringVar(value="0")

        if self._is_multi:
            key_choices = self._stems
            self._normal_var  = tk.StringVar(value=self._stems[0] if self._stems else "")
            self._hover_var   = tk.StringVar(value=_NONE_KEY)
            self._pressed_var = tk.StringVar(value=self._stems[1] if len(self._stems) > 1 else self._stems[0] if self._stems else "")
        else:
            key_choices = self._stems[:1]
            self._normal_var  = tk.StringVar(value=self._stems[0] if self._stems else "")
            self._hover_var   = tk.StringVar(value=_NONE_KEY)
            self._pressed_var = tk.StringVar(value=_NONE_KEY)

        # If editing an existing config, pre-fill
        if edit_config:
            if edit_config.get("canvas_id") in canvas_ids:
                self._canvas_var.set(edit_config["canvas_id"])
            self._tag_var.set(edit_config.get("tag", ""))
            self._x_var.set(str(edit_config.get("x", 0)))
            self._y_var.set(str(edit_config.get("y", 0)))
            self._normal_var.set(edit_config.get("normal_key", self._normal_var.get()))
            self._hover_var.set(edit_config.get("hover_key") or _NONE_KEY)
            self._pressed_var.set(edit_config.get("pressed_key") or _NONE_KEY)

        # Auto-generate a default tag name
        if not self._tag_var.get():
            cv = self._canvas_var.get()
            self._tag_var.set(f"btn_{comp_id}_{cv}" if cv and cv != "＋ Create New Canvas" else f"btn_{comp_id}")

        self._build_ui(canvas_choices, key_choices)
        self._canvas_var.trace_add("write", lambda *_: self._on_canvas_changed())
        self._normal_var.trace_add("write", lambda *_: self._refresh_preview())
        self._hover_var.trace_add("write", lambda *_: self._refresh_preview())
        self._pressed_var.trace_add("write", lambda *_: self._refresh_preview())
        self._refresh_preview()
        self.wait_window()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self, canvas_choices: list[str], key_choices: list[str]) -> None:
        hover_key_choices = [_NONE_KEY] + (key_choices if self._is_multi else self._stems[:1])
        pressed_key_choices = [_NONE_KEY] + (key_choices if self._is_multi else self._stems[:1])

        outer = tk.Frame(self, bg=_BG, padx=14, pady=10)
        outer.pack(fill="both", expand=True)

        # ── Left column: fields ───────────────────────────────────────────────
        left = tk.Frame(outer, bg=_BG)
        left.pack(side="left", fill="y", padx=(0, 14))

        def _label(text):
            tk.Label(left, text=text, bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w"
                     ).pack(fill="x", pady=(6, 1))

        # Canvas picker
        _label("Canvas")
        self._canvas_cb = ttk.Combobox(
            left, textvariable=self._canvas_var, values=canvas_choices,
            state="readonly", width=22, font=(UI_FONT, 9),
        )
        self._canvas_cb.pack(fill="x")

        # Normal image
        _label("Normal image" + (" key" if self._is_multi else ""))
        if self._is_multi:
            self._normal_cb = ttk.Combobox(
                left, textvariable=self._normal_var, values=key_choices,
                state="readonly", width=22, font=(UI_FONT, 9),
            )
            self._normal_cb.pack(fill="x")
        else:
            tk.Label(left, text=self._stems[0] if self._stems else "(none)",
                     bg=_FLD_BG, fg=_FLD_FG, font=(UI_FONT, 9), anchor="w", padx=4,
                     ).pack(fill="x")

        # Hover image
        _label("Hover image" + (" key" if self._is_multi else ""))
        self._hover_cb = ttk.Combobox(
            left, textvariable=self._hover_var, values=hover_key_choices,
            state="readonly", width=22, font=(UI_FONT, 9),
        )
        self._hover_cb.pack(fill="x")

        # Pressed image
        _label("Pressed image" + (" key" if self._is_multi else ""))
        self._pressed_cb = ttk.Combobox(
            left, textvariable=self._pressed_var, values=pressed_key_choices,
            state="readonly", width=22, font=(UI_FONT, 9),
        )
        self._pressed_cb.pack(fill="x")

        # Position row
        _label("Position  (x, y)")
        pos_row = tk.Frame(left, bg=_BG)
        pos_row.pack(fill="x")
        tk.Entry(pos_row, textvariable=self._x_var, bg=_FLD_BG, fg=_FLD_FG,
                 insertbackground=_FLD_FG, font=(UI_FONT, 9), width=7, relief="flat", bd=4,
                 ).pack(side="left", padx=(0, 4))
        tk.Entry(pos_row, textvariable=self._y_var, bg=_FLD_BG, fg=_FLD_FG,
                 insertbackground=_FLD_FG, font=(UI_FONT, 9), width=7, relief="flat", bd=4,
                 ).pack(side="left")

        # Tag name
        _label("Tag name")
        tk.Entry(left, textvariable=self._tag_var, bg=_FLD_BG, fg=_FLD_FG,
                 insertbackground=_FLD_FG, font=(UI_FONT, 9), width=22, relief="flat", bd=4,
                 ).pack(fill="x")

        # Auto-size checkbox
        tk.Frame(left, bg=_BG, height=6).pack()
        self._autosize_cv = tk.Canvas(left, bg=_BG, width=120, height=16,
                                       highlightthickness=0, cursor="hand2")
        self._autosize_cv.pack(anchor="w")
        self._autosize_var = tk.BooleanVar(value=True)
        self._draw_autosize_checkbox()
        self._autosize_cv.bind("<ButtonRelease-1>", lambda e: self._toggle_autosize())

        tk.Frame(left, bg=_BG, height=6).pack()

        # Buttons row
        btn_row = tk.Frame(left, bg=_BG)
        btn_row.pack(fill="x")
        for text, cmd in [("OK", self._commit), ("Cancel", self.destroy)]:
            lbl = tk.Label(btn_row, text=text, bg=_BTN_BG, fg="#ffffff",
                           font=(UI_FONT, 9), padx=10, pady=3, cursor="hand2")
            lbl.pack(side="left", padx=(0, 6))
            lbl.bind("<ButtonRelease-1>", lambda e, c=cmd: c())

        # ── Right column: preview ─────────────────────────────────────────────
        right = tk.Frame(outer, bg=_PANEL, padx=6, pady=6,
                         highlightbackground=_SEP, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(right, text="Preview  (click to test)", bg=_PANEL, fg=_DIM,
                 font=(UI_FONT, 7)).pack(anchor="w")

        self._preview_cv = tk.Canvas(
            right, bg="#2d2d2d", width=140, height=140,
            highlightthickness=0, cursor="hand2",
        )
        self._preview_cv.pack(pady=(4, 0))
        self._preview_cv.bind("<Button-1>",        self._on_preview_down)
        self._preview_cv.bind("<ButtonRelease-1>", self._on_preview_up)
        self._preview_cv.bind("<Enter>",           self._on_preview_enter)
        self._preview_cv.bind("<Leave>",           self._on_preview_leave)

        self._state_lbl = tk.Label(right, text="normal", bg=_PANEL, fg=_DIM,
                                   font=(UI_FONT, 7))
        self._state_lbl.pack(pady=(2, 0))

    # ── Canvas picker ─────────────────────────────────────────────────────────

    def _on_canvas_changed(self) -> None:
        val = self._canvas_var.get()
        # When a real canvas is selected, update the default tag to match
        if val and val != "＋ Create New Canvas":
            current = self._tag_var.get()
            if not current or current.startswith(f"btn_{self._comp_id}_"):
                self._tag_var.set(f"btn_{self._comp_id}_{val}")

    # ── Preview ───────────────────────────────────────────────────────────────

    def _load_preview_photo(self, key: str):
        if not key or key == _NONE_KEY:
            return None
        if self._is_multi:
            idx = next((i for i, s in enumerate(self._stems) if s == key), None)
            if idx is None:
                return None
            path = self._paths[idx]
        else:
            path = self._paths[0] if self._paths else ""
        if not path:
            return None
        try:
            from PIL import Image, ImageTk
            resolved = os.path.join(self._project_dir, path) if not os.path.isabs(path) else path
            img = Image.open(resolved).convert("RGBA")
            img.thumbnail((130, 130), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _refresh_preview(self) -> None:
        self._preview_thumbs.clear()
        self._preview_normal  = self._load_preview_photo(self._normal_var.get())
        hk = self._hover_var.get()
        pk = self._pressed_var.get()
        self._preview_hover   = self._load_preview_photo(hk)  if hk  != _NONE_KEY else None
        self._preview_pressed = self._load_preview_photo(pk)  if pk  != _NONE_KEY else None
        for p in (self._preview_normal, self._preview_hover, self._preview_pressed):
            if p:
                self._preview_thumbs.append(p)
        self._show_preview_state(self._preview_normal, "normal")

    def _show_preview_state(self, photo, label: str) -> None:
        cv = self._preview_cv
        cv.delete("all")
        if photo:
            cv.create_image(70, 70, anchor="center", image=photo)
        else:
            cv.create_text(70, 70, text="[no image]", fill=_DIM, font=(UI_FONT, 8))
        self._state_lbl.config(text=label)

    def _on_preview_down(self, _event) -> None:
        self._show_preview_state(self._preview_pressed or self._preview_normal, "pressed")

    def _on_preview_up(self, _event) -> None:
        hover = self._preview_hover
        self._show_preview_state(hover or self._preview_normal, "hover" if hover else "normal")

    def _on_preview_enter(self, _event) -> None:
        if self._preview_hover:
            self._show_preview_state(self._preview_hover, "hover")

    def _on_preview_leave(self, _event) -> None:
        self._show_preview_state(self._preview_normal, "normal")

    # ── Commit ────────────────────────────────────────────────────────────────

    def _draw_autosize_checkbox(self) -> None:
        cv = self._autosize_cv
        cv.delete("all")
        checked = self._autosize_var.get()
        box_fill    = "#007acc" if checked else ""
        box_outline = "#007acc" if checked else "#666666"
        cv.create_rectangle(0, 2, 12, 14, fill=box_fill, outline=box_outline)
        if checked:
            cv.create_text(6, 8, text="✓", fill="#ffffff", font=(UI_FONT, 7, "bold"))
        cv.create_text(17, 8, text="Auto-size canvas", fill="#cccccc",
                       font=(UI_FONT, 8), anchor="w")

    def _toggle_autosize(self) -> None:
        self._autosize_var.set(not self._autosize_var.get())
        self._draw_autosize_checkbox()

    def _get_max_image_size(self) -> tuple[int, int]:
        max_w, max_h = 0, 0
        for path in self._paths:
            try:
                from PIL import Image
                resolved = os.path.join(self._project_dir, path) if not os.path.isabs(path) else path
                with Image.open(resolved) as img:
                    w, h = img.size
                max_w = max(max_w, w)
                max_h = max(max_h, h)
            except Exception:
                pass
        return max_w, max_h

    def _commit(self) -> None:
        canvas_id = self._canvas_var.get().strip()
        tag       = self._tag_var.get().strip()
        if not tag:
            return
        # If "Create New Canvas" is still selected, create one now
        if not canvas_id or canvas_id == "＋ Create New Canvas":
            if not self._on_create_canvas:
                return
            new_id = self._on_create_canvas()
            if not new_id:
                return
            canvas_id = new_id
        try:
            x = int(self._x_var.get())
            y = int(self._y_var.get())
        except ValueError:
            return
        hover_val   = self._hover_var.get()
        pressed_val = self._pressed_var.get()
        auto_w, auto_h = self._get_max_image_size() if self._autosize_var.get() else (0, 0)
        config = {
            "canvas_id":   canvas_id,
            "tag":         tag,
            "x":           x,
            "y":           y,
            "normal_key":  self._normal_var.get() if self._is_multi else "",
            "hover_key":   hover_val   if hover_val   != _NONE_KEY else "",
            "pressed_key": pressed_val if pressed_val != _NONE_KEY else "",
            "auto_size_w": auto_w,
            "auto_size_h": auto_h,
        }
        self._on_confirm(config)
        self.destroy()
