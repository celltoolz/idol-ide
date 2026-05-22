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
        wire_body_resolver: "Callable[[str], str] | None" = None,
        secondary_options: tuple[str, ...] = (),
        secondary_label: str = "Mode",
        initial_warning: str = "",
        show_title_entry: bool = False,
        initial_title: str = "",
        title_entry_label: str = "Title",
        show_extra_entry: bool = False,
        initial_extra: str = "",
        extra_entry_label: str = "Title",
        wire_label: str = "Wire",
        preselect_event_key: str | None = None,
        menu_items: "tuple | list" = (),
        stub_checker: "Callable[[str], bool] | None" = None,
    ) -> None:
        super().__init__(parent)
        self._form              = form
        self._comp_id           = component_id
        self._handler_id        = handler_id
        self._handler_label     = handler_label
        self._on_wire           = on_wire
        self._opt_list            = options
        self._secondary_opts      = secondary_options
        self._secondary_label     = secondary_label
        self._preselect_widget_id = preselect_widget_id
        self._wire_body_resolver  = wire_body_resolver
        self._initial_warning     = initial_warning
        self._show_title_entry    = show_title_entry
        self._initial_title       = initial_title
        self._title_entry_label   = title_entry_label
        self._show_extra_entry    = show_extra_entry
        self._initial_extra       = initial_extra
        self._extra_entry_label   = extra_entry_label
        self._wire_label          = wire_label
        self._preselect_event_key = preselect_event_key
        self._menu_items          = list(menu_items)
        self._stub_checker        = stub_checker
        self._menu_item_names:    set[str] = set()
        self._title_var: tk.StringVar | None = None
        self._extra_var: tk.StringVar | None = None

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

        # Option row(s) — shown when options or secondary_options are non-empty
        self._option_var:    tk.StringVar | None = None
        self._secondary_var: tk.StringVar | None = None
        if self._opt_list or self._secondary_opts:
            opt_row = tk.Frame(self, bg=_BG)
            opt_row.pack(fill="x", padx=10, pady=(0, 4))

            if self._opt_list:
                primary_label = "Dialog:" if self._secondary_opts else "Option:"
                tk.Label(opt_row, text=primary_label, bg=_BG, fg=_DIM,
                         font=(UI_FONT, 8), anchor="w").pack(side="left", padx=(0, 4))
                self._option_var = tk.StringVar(value=self._opt_list[0])
                opt_cb = ttk.Combobox(
                    opt_row, textvariable=self._option_var,
                    values=list(self._opt_list), state="readonly",
                    width=14, font=(UI_FONT, 9),
                )
                opt_cb.pack(side="left", padx=(0, 12))
                opt_cb.bind("<<ComboboxSelected>>", lambda _: self._update_preview())

            if self._secondary_opts:
                tk.Label(opt_row, text=f"{self._secondary_label}:", bg=_BG, fg=_DIM,
                         font=(UI_FONT, 8), anchor="w").pack(side="left", padx=(0, 4))
                self._secondary_var = tk.StringVar(value=self._secondary_opts[0])
                sec_cb = ttk.Combobox(
                    opt_row, textvariable=self._secondary_var,
                    values=list(self._secondary_opts), state="readonly",
                    width=14, font=(UI_FONT, 9),
                )
                sec_cb.pack(side="left")
                sec_cb.bind("<<ComboboxSelected>>", lambda _: self._update_preview())

        # Title entry — optional, shown for components that support per-handler titles
        if self._show_title_entry:
            title_row = tk.Frame(self, bg=_BG)
            title_row.pack(fill="x", padx=10, pady=(0, 4))
            tk.Label(title_row, text=f"{self._title_entry_label}:", bg=_BG, fg=_DIM,
                     font=(UI_FONT, 8), anchor="w", width=7).pack(side="left", padx=(0, 4))
            self._title_var = tk.StringVar(value=self._initial_title)
            title_entry = tk.Entry(
                title_row, textvariable=self._title_var,
                bg="#3c3c3c", fg="#cccccc",
                insertbackground="#cccccc",
                relief="flat", highlightthickness=1,
                highlightbackground="#555555",
                font=(UI_FONT, 9),
            )
            title_entry.pack(side="left", fill="x", expand=True)
            title_entry.bind("<KeyRelease>", lambda _: self._update_preview())

        # Extra entry (e.g. dialog title for messagebox, shown below message entry)
        if self._show_extra_entry:
            extra_row = tk.Frame(self, bg=_BG)
            extra_row.pack(fill="x", padx=10, pady=(0, 4))
            tk.Label(extra_row, text=f"{self._extra_entry_label}:", bg=_BG, fg=_DIM,
                     font=(UI_FONT, 8), anchor="w", width=7).pack(side="left", padx=(0, 4))
            self._extra_var = tk.StringVar(value=self._initial_extra)
            extra_entry = tk.Entry(
                extra_row, textvariable=self._extra_var,
                bg="#3c3c3c", fg="#cccccc",
                insertbackground="#cccccc",
                relief="flat", highlightthickness=1,
                highlightbackground="#555555",
                font=(UI_FONT, 9),
            )
            extra_entry.pack(side="left", fill="x", expand=True)
            extra_entry.bind("<KeyRelease>", lambda _: self._update_preview())

        # Preview label
        self._preview = tk.Label(
            self, text="Select a widget and event above",
            bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w", padx=10,
        )
        self._preview.pack(fill="x", pady=(0, 2))

        # Warning label — visible when selected event already has a handler,
        # or pre-populated via initial_warning (e.g. no populate targets found).
        self._warn_lbl = tk.Label(
            self, text=self._initial_warning,
            bg=_BG, fg="#e8a844", font=(UI_FONT, 8), anchor="w", padx=10,
        )
        self._warn_lbl.pack(fill="x", pady=(0, 4))

        # Parallel lists — clean event keys + in-use tracking
        self._ev_keys:  list[str] = []
        self._used_evs: set[str]  = set()

        # Button row
        btn_row = tk.Frame(self, bg=_BG)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        self._wire_btn = tk.Label(
            btn_row, text=self._wire_label, bg=_ACC, fg="#ffffff",
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

        # Add connectable menu items (non-cascade command items at indent > 0)
        items = self._menu_items
        for i, mi in enumerate(items):
            if mi.indent == 0 or mi.caption == "-" or not mi.name:
                continue
            if mi.kind in ("checkbutton", "radiobutton"):
                continue
            is_cascade = any(
                items[j].indent == mi.indent + 1
                for j in range(i + 1, len(items))
                if items[j].indent <= mi.indent + 1
            )
            if is_cascade:
                continue
            if mi.name == self._preselect_widget_id:
                preselect_idx = len(self._widget_ids)
            self._wid_lb.insert("end", f"{mi.name}  (MenuItem)")
            self._widget_ids.append(mi.name)
            self._menu_item_names.add(mi.name)

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

        if wid in self._menu_item_names:
            mi = next((m for m in self._menu_items if m.name == wid), None)
            self._ev_keys  = ["command"]
            self._used_evs = {"command"} if mi and mi.command_handler else set()
            self._ev_lb.delete(0, "end")
            label = "◆ command" if self._used_evs else "command"
            self._ev_lb.insert("end", label)
            self._warn_lbl.config(text="")
            if self._preselect_event_key == "command":
                self._ev_lb.selection_set(0)
                self._ev_lb.see(0)
            self._update_preview()
            return

        widget = self._form.get_widget(wid)
        if widget is None:
            return
        reg    = REGISTRY.get(widget.type, {})
        events = reg.get("events", [])
        self._used_evs = set(widget.events.keys())
        self._ev_keys  = list(events)
        self._ev_lb.delete(0, "end")
        for ev in events:
            label = f"◆ {ev}" if ev in self._used_evs else ev
            self._ev_lb.insert("end", label)
        self._warn_lbl.config(text="")
        if self._preselect_event_key and self._preselect_event_key in self._ev_keys:
            ev_idx = self._ev_keys.index(self._preselect_event_key)
            self._ev_lb.selection_set(ev_idx)
            self._ev_lb.see(ev_idx)
        self._update_preview()

    def _update_preview(self, _event=None) -> None:
        wsel = self._wid_lb.curselection()
        esel = self._ev_lb.curselection()
        if not wsel or not esel:
            self._preview.config(text="Select a widget and event above", fg=_DIM)
            self._warn_lbl.config(text="")
            return
        wid    = self._widget_ids[wsel[0]]
        ev_key = self._ev_keys[esel[0]]
        option    = self._option_var.get()    if self._option_var    else ""
        secondary = self._secondary_var.get() if self._secondary_var else ""
        combined  = (f"{option}:{secondary}" if option and secondary
                     else secondary if secondary else option)
        if self._wire_body_resolver and combined:
            body = self._wire_body_resolver(combined)
            mode_tag = f"  [{secondary}]" if secondary else ""
            rhs = f"{body}{mode_tag}"
        else:
            option_str = f"  [{option}]" if option else ""
            rhs = f"self.{self._method_display}(){option_str}"
        title = self._title_var.get().strip() if self._title_var else ""
        title_tag = f'  {self._title_entry_label.lower()}: "{title}"' if title else ""
        extra = self._extra_var.get().strip() if self._extra_var else ""
        extra_tag = f'  {self._extra_entry_label.lower()}: "{extra}"' if extra else ""
        self._preview.config(
            text=f"Wires:  {wid}.{ev_key}  →  {rhs}{title_tag}{extra_tag}",
            fg="#4ec9b0",
        )
        if (ev_key in self._used_evs
                and not (wid == self._preselect_widget_id
                         and ev_key == self._preselect_event_key)):
            if wid in self._menu_item_names:
                mi = next((m for m in self._menu_items if m.name == wid), None)
                raw = mi.command_handler if mi else ""
                existing_handler = raw
            else:
                existing = self._form.get_widget(wid)
                existing_handler = existing.events.get(ev_key, "") if existing else ""
            is_stub = (self._stub_checker is not None
                       and existing_handler
                       and self._stub_checker(existing_handler))
            if not is_stub:
                self._warn_lbl.config(
                    text=f"⚠  '{ev_key}' already calls {existing_handler} — wiring will overwrite it",
                )
            else:
                self._warn_lbl.config(text="")
        else:
            self._warn_lbl.config(text="")

    def _do_wire(self) -> None:
        wsel = self._wid_lb.curselection()
        esel = self._ev_lb.curselection()
        if not wsel or not esel:
            return
        wid    = self._widget_ids[wsel[0]]
        ev_key = self._ev_keys[esel[0]]
        option    = self._option_var.get()    if self._option_var    else ""
        secondary = self._secondary_var.get() if self._secondary_var else ""
        combined  = (f"{option}:{secondary}" if option and secondary
                     else secondary if secondary else option)
        title = self._title_var.get().strip() if self._title_var else ""
        extra = self._extra_var.get().strip() if self._extra_var else ""
        if extra:
            combined_final = f"{combined}|{title}|{extra}"
        elif title:
            combined_final = f"{combined}|{title}"
        else:
            combined_final = combined
        self._on_wire(wid, ev_key, combined_final)
        self.destroy()

    def _center(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")
