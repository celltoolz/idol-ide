from __future__ import annotations

"""Connector dialog — wires a handler to a widget event."""

import tkinter as tk
from tkinter import ttk
from typing import Callable

from designer.model import FormModel
from designer.registry import REGISTRY
from utils.ui_font import UI_FONT

_BG   = "#252526"
_LIST = "#1e1e1e"
_SEL  = "#094771"
_FG   = "#cccccc"
_DIM  = "#858585"
_ACC  = "#007acc"


class ComponentConnector(tk.Toplevel):
    """Modal dialog for wiring a handler to a widget event.

    Opens with a widget listbox on the left and an event listbox on the right.
    When options is non-empty, shows an option combobox below the lists.
    Clicking Wire calls on_wire(widget_id, event_key, option) and closes.

    For component handlers: pass component_id + handler_label (method suffix).
    For form handlers:      pass component_id="" and handler_id = full method name.
    """

    def __init__(
        self,
        parent: tk.Misc,
        form: FormModel,
        component_id: str,
        handler_id: str,
        handler_label: str,
        on_wire: Callable[[str, str, str], None],
        options: tuple[str, ...] = (),
        preselect_widget_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._form              = form
        self._comp_id           = component_id
        self._handler_id        = handler_id
        self._handler_label     = handler_label
        self._on_wire           = on_wire
        self._options           = options
        self._preselect_widget_id = preselect_widget_id

        # Build the display method name
        if component_id:
            self._method_display = f"_{component_id}{handler_label}"
        else:
            self._method_display = handler_id

        self.title(f"Connect {self._method_display} → Widget Event")
        self.resizable(False, False)
        self.configure(bg=_BG)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._center(parent)
        self.wait_window()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Title row
        tk.Label(self, text=f"Wire  {self._method_display}()  to a widget event",
                 bg=_BG, fg=_FG, font=(UI_FONT, 9), anchor="w", padx=10,
                 pady=6).pack(fill="x")

        # Two-column frame
        cols = tk.Frame(self, bg=_BG)
        cols.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        # Left: widget list
        lf = tk.LabelFrame(cols, text="Widget", bg=_BG, fg=_DIM,
                           font=(UI_FONT, 8), bd=1, relief="groove",
                           labelanchor="n")
        lf.pack(side="left", fill="both", expand=True, padx=(0, 4))

        self._wid_lb = tk.Listbox(
            lf, bg=_LIST, fg=_FG, selectbackground=_SEL,
            activestyle="none", font=("Consolas", 8),
            relief="flat", bd=0, height=12, width=22,
            exportselection=False,
        )
        self._wid_lb.pack(fill="both", expand=True, padx=2, pady=2)

        # Right: event list
        ef = tk.LabelFrame(cols, text="Event", bg=_BG, fg=_DIM,
                           font=(UI_FONT, 8), bd=1, relief="groove",
                           labelanchor="n")
        ef.pack(side="left", fill="both", expand=True, padx=(4, 0))

        self._ev_lb = tk.Listbox(
            ef, bg=_LIST, fg=_FG, selectbackground=_SEL,
            activestyle="none", font=("Consolas", 8),
            relief="flat", bd=0, height=12, width=18,
            exportselection=False,
        )
        self._ev_lb.pack(fill="both", expand=True, padx=2, pady=2)

        # Option row — only shown when options is non-empty
        self._option_var: tk.StringVar | None = None
        if self._options:
            opt_row = tk.Frame(self, bg=_BG)
            opt_row.pack(fill="x", padx=10, pady=(0, 4))
            tk.Label(opt_row, text="Option:", bg=_BG, fg=_DIM,
                     font=(UI_FONT, 8), anchor="w").pack(side="left", padx=(0, 6))
            self._option_var = tk.StringVar(value=self._options[0])
            opt_cb = ttk.Combobox(
                opt_row, textvariable=self._option_var,
                values=list(self._options), state="readonly",
                width=16, font=(UI_FONT, 9),
            )
            opt_cb.pack(side="left")
            opt_cb.bind("<<ComboboxSelected>>", lambda _: self._update_preview())

        # Preview label
        self._preview = tk.Label(
            self, text="Select a widget and event above",
            bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w", padx=10,
        )
        self._preview.pack(fill="x", pady=(0, 4))

        # Button row
        btn_row = tk.Frame(self, bg=_BG)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        self._wire_btn = tk.Label(
            btn_row, text="Wire", bg=_ACC, fg="#ffffff",
            font=(UI_FONT, 9), padx=12, pady=4, cursor="hand2",
        )
        self._wire_btn.pack(side="right", padx=(6, 0))
        self._wire_btn.bind("<ButtonRelease-1>", lambda e: self._do_wire())

        cancel_btn = tk.Label(
            btn_row, text="Cancel", bg="#3c3c3c", fg=_FG,
            font=(UI_FONT, 9), padx=12, pady=4, cursor="hand2",
        )
        cancel_btn.pack(side="right")
        cancel_btn.bind("<ButtonRelease-1>", lambda e: self.destroy())

        # Populate widget list; track preselect index
        self._widget_ids: list[str] = []
        preselect_idx: int | None = None
        for w in self._form.widgets:
            reg = REGISTRY.get(w.type, {})
            if reg.get("events"):
                if w.id == self._preselect_widget_id:
                    preselect_idx = len(self._widget_ids)
                self._wid_lb.insert("end", f"{w.id}  ({w.type})")
                self._widget_ids.append(w.id)

        self._wid_lb.bind("<<ListboxSelect>>", self._on_widget_select)
        self._ev_lb.bind("<<ListboxSelect>>",  self._update_preview)

        # Pre-select widget if requested
        if preselect_idx is not None:
            self._wid_lb.selection_set(preselect_idx)
            self._wid_lb.see(preselect_idx)
            self._on_widget_select(None)

    def _on_widget_select(self, _event) -> None:
        sel = self._wid_lb.curselection()
        if not sel:
            return
        wid = self._widget_ids[sel[0]]
        widget = self._form.get_widget(wid)
        if widget is None:
            return
        reg    = REGISTRY.get(widget.type, {})
        events = reg.get("events", [])
        self._ev_lb.delete(0, "end")
        for ev in events:
            self._ev_lb.insert("end", ev)
        self._update_preview()

    def _update_preview(self, _event=None) -> None:
        wsel = self._wid_lb.curselection()
        esel = self._ev_lb.curselection()
        if not wsel or not esel:
            self._preview.config(text="Select a widget and event above", fg=_DIM)
            return
        wid    = self._widget_ids[wsel[0]]
        ev_key = self._ev_lb.get(esel[0])
        option_str = (f"  [{self._option_var.get()}]"
                      if self._option_var else "")
        self._preview.config(
            text=f"Wires:  {wid}.{ev_key}  →  self.{self._method_display}(){option_str}",
            fg="#4ec9b0",
        )

    def _do_wire(self) -> None:
        wsel = self._wid_lb.curselection()
        esel = self._ev_lb.curselection()
        if not wsel or not esel:
            return
        wid    = self._widget_ids[wsel[0]]
        ev_key = self._ev_lb.get(esel[0])
        option = self._option_var.get() if self._option_var else ""
        self._on_wire(wid, ev_key, option)
        self.destroy()

    def _center(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")
