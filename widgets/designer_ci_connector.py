from __future__ import annotations

"""Canvas-item connector — wires a catalog handler to a canvas item's tag event.

Unlike ``ComponentConnector`` (Widget → Event), canvas-item bindings are
*tag-scoped*: codegen emits one ``tag_bind`` per (tag, event) that fires for
every item carrying the tag. So this dialog is Object → Tag → Event:

  * **Object** — the canvas item you clicked (canvasimage1, rect1, …). Picking
    one populates the Tag list with that item's tags.
  * **Tag**    — the binding target. Pick the item's own id-tag to affect only
    this object, or a shared tag to affect every object carrying it. A new tag
    can be typed in the entry below.
  * **Event**  — the logical canvas event (click, dblclick, mousedown, …).

Wire calls ``on_wire(item_id, tag, event_key, combined_option)``.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable

from utils.ui_font import UI_FONT

_BG   = "#252526"
_LIST = "#1e1e1e"
_SEL  = "#094771"
_FG   = "#cccccc"
_DIM  = "#858585"
_ACC  = "#007acc"

# Logical canvas events, in display order.
_CI_EVENTS = (
    "click", "dblclick", "rightclick",
    "mousedown", "mouseup", "mousemove",
    "mouseenter", "mouseleave",
)


class CanvasItemConnector(tk.Toplevel):
    """Modal dialog for wiring a catalog handler to a canvas item's tag event."""

    def __init__(
        self,
        parent: tk.Misc,
        objects: "list[dict]",
        tag_pool: "tuple[str, ...]",
        method_display: str,
        on_wire: Callable[[str, str, str, str], None],
        options: "tuple[str, ...]" = (),
        option_label: str = "Dialog",
        secondary_options: "tuple[str, ...]" = (),
        secondary_label: str = "Mode",
        preselect_item_id: "str | None" = None,
        preselect_tag: "str | None" = None,
        preselect_event_key: "str | None" = None,
        preselect_option: "str | None" = None,
        preselect_secondary: "str | None" = None,
        wire_label: str = "Wire",
        wire_body_resolver: "Callable[[str], str] | None" = None,
    ) -> None:
        super().__init__(parent)
        # objects: [{"id": str, "label": str, "tags": list[str]}]
        self._objects            = objects
        self._tag_pool           = list(tag_pool)
        self._method_display     = method_display
        self._on_wire            = on_wire
        self._opt_list           = options
        self._option_label       = option_label
        self._secondary_opts     = secondary_options
        self._secondary_label    = secondary_label
        self._preselect_item_id  = preselect_item_id
        self._preselect_tag      = preselect_tag
        self._preselect_event    = preselect_event_key
        self._preselect_option   = preselect_option
        self._preselect_secondary = preselect_secondary
        self._wire_label         = wire_label
        self._wire_body_resolver = wire_body_resolver

        self._cur_tags: list[str] = []   # tags shown in the Tag list for the selected object

        self.title(f"Connect {method_display} → Canvas Item Event")
        self.resizable(False, False)
        self.configure(bg=_BG)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._center(parent)
        self.wait_window()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        tk.Label(self, text=f"Wire  {self._method_display}  to a canvas item event",
                 bg=_BG, fg=_FG, font=(UI_FONT, 9), anchor="w", padx=10,
                 pady=6).pack(fill="x")

        cols = tk.Frame(self, bg=_BG)
        cols.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        # Object column
        of = tk.LabelFrame(cols, text="Object", bg=_BG, fg=_DIM, font=(UI_FONT, 8),
                           bd=1, relief="groove", labelanchor="n")
        of.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self._obj_lb = tk.Listbox(
            of, bg=_LIST, fg=_FG, selectbackground=_SEL, activestyle="none",
            font=("Consolas", 8), relief="flat", bd=0, height=12, width=20,
            exportselection=False,
        )
        self._obj_lb.pack(fill="both", expand=True, padx=2, pady=2)

        # Tag column
        tf = tk.LabelFrame(cols, text="Tag", bg=_BG, fg=_DIM, font=(UI_FONT, 8),
                           bd=1, relief="groove", labelanchor="n")
        tf.pack(side="left", fill="both", expand=True, padx=4)
        self._tag_lb = tk.Listbox(
            tf, bg=_LIST, fg=_FG, selectbackground=_SEL, activestyle="none",
            font=("Consolas", 8), relief="flat", bd=0, height=12, width=16,
            exportselection=False,
        )
        self._tag_lb.pack(fill="both", expand=True, padx=2, pady=2)

        # Event column
        ef = tk.LabelFrame(cols, text="Event", bg=_BG, fg=_DIM, font=(UI_FONT, 8),
                           bd=1, relief="groove", labelanchor="n")
        ef.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self._ev_lb = tk.Listbox(
            ef, bg=_LIST, fg=_FG, selectbackground=_SEL, activestyle="none",
            font=("Consolas", 8), relief="flat", bd=0, height=12, width=14,
            exportselection=False,
        )
        self._ev_lb.pack(fill="both", expand=True, padx=2, pady=2)
        for ev in _CI_EVENTS:
            self._ev_lb.insert("end", ev)
        if self._preselect_event in _CI_EVENTS:
            ev_idx = _CI_EVENTS.index(self._preselect_event)
            self._ev_lb.selection_set(ev_idx)
            self._ev_lb.see(ev_idx)

        # New-tag entry row
        new_row = tk.Frame(self, bg=_BG)
        new_row.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(new_row, text="New tag:", bg=_BG, fg=_DIM, font=(UI_FONT, 8),
                 anchor="w", width=8).pack(side="left", padx=(0, 4))
        self._new_tag_var = tk.StringVar()
        new_entry = tk.Entry(
            new_row, textvariable=self._new_tag_var, bg="#3c3c3c", fg="#cccccc",
            insertbackground="#cccccc", relief="flat", highlightthickness=1,
            highlightbackground="#555555", font=(UI_FONT, 9),
        )
        new_entry.pack(side="left", fill="x", expand=True)
        new_entry.bind("<Return>", lambda _e: self._add_new_tag())

        # Option row(s)
        self._option_var:    tk.StringVar | None = None
        self._secondary_var: tk.StringVar | None = None
        if self._opt_list or self._secondary_opts:
            opt_row = tk.Frame(self, bg=_BG)
            opt_row.pack(fill="x", padx=10, pady=(0, 4))
            if self._opt_list:
                tk.Label(opt_row, text=f"{self._option_label}:", bg=_BG, fg=_DIM,
                         font=(UI_FONT, 8), anchor="w").pack(side="left", padx=(0, 4))
                opt_init = (self._preselect_option
                            if self._preselect_option in self._opt_list
                            else self._opt_list[0])
                self._option_var = tk.StringVar(value=opt_init)
                opt_cb = ttk.Combobox(opt_row, textvariable=self._option_var,
                                      values=list(self._opt_list), state="readonly",
                                      width=14, font=(UI_FONT, 9))
                opt_cb.pack(side="left", padx=(0, 12))
                opt_cb.bind("<<ComboboxSelected>>", lambda _e: self._update_preview())
            if self._secondary_opts:
                tk.Label(opt_row, text=f"{self._secondary_label}:", bg=_BG, fg=_DIM,
                         font=(UI_FONT, 8), anchor="w").pack(side="left", padx=(0, 4))
                sec_init = (self._preselect_secondary
                            if self._preselect_secondary in self._secondary_opts
                            else self._secondary_opts[0])
                self._secondary_var = tk.StringVar(value=sec_init)
                sec_cb = ttk.Combobox(opt_row, textvariable=self._secondary_var,
                                      values=list(self._secondary_opts), state="readonly",
                                      width=14, font=(UI_FONT, 9))
                sec_cb.pack(side="left")
                sec_cb.bind("<<ComboboxSelected>>", lambda _e: self._update_preview())

        # Preview + warning
        self._preview = tk.Label(self, text="Select an object, tag and event above",
                                 bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w", padx=10)
        self._preview.pack(fill="x", pady=(0, 2))
        self._warn_lbl = tk.Label(self, text="", bg=_BG, fg="#e8a844",
                                  font=(UI_FONT, 8), anchor="w", padx=10)
        self._warn_lbl.pack(fill="x", pady=(0, 4))

        # Buttons
        btn_row = tk.Frame(self, bg=_BG)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))
        self._wire_btn = tk.Label(btn_row, text=self._wire_label, bg=_ACC, fg="#ffffff",
                                  font=(UI_FONT, 9), padx=12, pady=4, cursor="hand2")
        self._wire_btn.pack(side="right", padx=(6, 0))
        self._wire_btn.bind("<ButtonRelease-1>", lambda e: self._do_wire())
        cancel_btn = tk.Label(btn_row, text="Cancel", bg="#3c3c3c", fg=_FG,
                              font=(UI_FONT, 9), padx=12, pady=4, cursor="hand2")
        cancel_btn.pack(side="right")
        cancel_btn.bind("<ButtonRelease-1>", lambda e: self.destroy())

        # Populate objects; track preselect
        preselect_idx = 0
        for i, obj in enumerate(self._objects):
            self._obj_lb.insert("end", obj["label"])
            if obj["id"] == self._preselect_item_id:
                preselect_idx = i
        self._obj_lb.bind("<<ListboxSelect>>", self._on_object_select)
        self._tag_lb.bind("<<ListboxSelect>>", self._update_preview)
        self._ev_lb.bind("<<ListboxSelect>>", self._update_preview)

        if self._objects:
            self._obj_lb.selection_set(preselect_idx)
            self._obj_lb.see(preselect_idx)
            self._on_object_select(None)

    # ── List behaviour ──────────────────────────────────────────────────────────

    def _selected_object(self) -> "dict | None":
        sel = self._obj_lb.curselection()
        return self._objects[sel[0]] if sel else None

    def _on_object_select(self, _event) -> None:
        obj = self._selected_object()
        if obj is None:
            return
        # Tag list = the object's own tags + its id-tag + remaining pool tags.
        tags: list[str] = list(obj["tags"])
        if obj["id"] not in tags:
            tags.append(obj["id"])   # always offer a unique per-object tag
        for t in self._tag_pool:
            if t not in tags:
                tags.append(t)
        self._cur_tags = tags
        self._tag_lb.delete(0, "end")
        for t in tags:
            shared = self._tag_object_count(t)
            label = f"{t}  ×{shared}" if shared > 1 else t
            self._tag_lb.insert("end", label)
        if tags:
            self._tag_lb.selection_clear(0, "end")
            tag_idx = 0
            if self._preselect_tag in tags:
                tag_idx = tags.index(self._preselect_tag)
            self._preselect_tag = None   # apply only on the initial population
            self._tag_lb.selection_set(tag_idx)
            self._tag_lb.see(tag_idx)
        self._update_preview()

    def _tag_object_count(self, tag: str) -> int:
        """How many objects carry this tag (id-tags count as 1)."""
        n = sum(1 for o in self._objects if tag in o["tags"])
        if any(o["id"] == tag for o in self._objects) and n == 0:
            return 1
        return n

    def _add_new_tag(self) -> None:
        tag = self._new_tag_var.get().strip()
        if not tag or tag in self._cur_tags:
            return
        self._cur_tags.insert(0, tag)
        self._tag_lb.insert(0, tag)
        self._tag_lb.selection_clear(0, "end")
        self._tag_lb.selection_set(0)
        self._new_tag_var.set("")
        self._update_preview()

    def _chosen_tag(self) -> str:
        sel = self._tag_lb.curselection()
        return self._cur_tags[sel[0]] if sel else ""

    def _combined_option(self) -> str:
        option    = self._option_var.get()    if self._option_var    else ""
        secondary = self._secondary_var.get() if self._secondary_var else ""
        if option and secondary:
            return f"{option}:{secondary}"
        return secondary or option

    def _update_preview(self, _event=None) -> None:
        obj    = self._selected_object()
        tag    = self._chosen_tag()
        ev_sel = self._ev_lb.curselection()
        if obj is None or not tag or not ev_sel:
            self._preview.config(text="Select an object, tag and event above", fg=_DIM)
            self._warn_lbl.config(text="")
            return
        ev_key   = _CI_EVENTS[ev_sel[0]]
        combined = self._combined_option()
        if self._wire_body_resolver and combined:
            rhs = self._wire_body_resolver(combined)
        else:
            rhs = self._method_display
        self._preview.config(
            text=f"Wires:  {tag}.{ev_key}  →  {rhs}", fg="#4ec9b0")
        shared = self._tag_object_count(tag)
        if shared > 1:
            self._warn_lbl.config(
                text=f"⚠  '{tag}' is on {shared} objects — this fires for all of them")
        else:
            self._warn_lbl.config(text="")

    def _do_wire(self) -> None:
        obj    = self._selected_object()
        tag    = self._chosen_tag()
        ev_sel = self._ev_lb.curselection()
        if obj is None or not tag or not ev_sel:
            return
        ev_key = _CI_EVENTS[ev_sel[0]]
        self._on_wire(obj["id"], tag, ev_key, self._combined_option())
        self.destroy()

    def _center(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")
