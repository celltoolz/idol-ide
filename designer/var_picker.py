"""Variable / handler picker — shared popups for the GUI Designer.

Used by both the properties panel (inline treeview editor) and the menu editor
(standalone Entry + button widget).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable
from utils.ui_font import UI_FONT

_BG      = "#1e1e1e"
_BG2     = "#2d2d2d"
_BG_HOV  = "#094771"
_FG      = "#cccccc"
_FG_DIM  = "#858585"
_FG_TYPE = "#569cd6"
_BORDER  = "#3a3a3a"

_ROW_H   = 26   # approximate px per row
_MAX_VIS = 10   # rows visible before scrollbar appears
_LIST_W  = 220  # popup list width in px


# ── Scrollable list helper ────────────────────────────────────────────────────

def _scrollable_list(inner: tk.Frame, num_rows: int):
    """Build a canvas+scrollbar inside *inner*.  Returns (scroll_frame, canvas, wheel_fn)."""
    vis_h  = min(num_rows, _MAX_VIS) * _ROW_H
    canvas = tk.Canvas(inner, bg=_BG2, highlightthickness=0,
                       height=vis_h, width=_LIST_W, bd=0)
    sf  = tk.Frame(canvas, bg=_BG2)
    win = canvas.create_window((0, 0), window=sf, anchor="nw")

    sf.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>",
                lambda e: canvas.itemconfig(win, width=e.width))

    def _wheel(e):
        canvas.yview_scroll(-1 * (1 if e.delta > 0 else -1), "units")

    canvas.bind("<MouseWheel>", _wheel)
    sf.bind("<MouseWheel>", _wheel)

    if num_rows > _MAX_VIS:
        sb = ttk.Scrollbar(inner, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

    canvas.pack(side="left", fill="both", expand=True)
    return sf, canvas, _wheel


def _place_popup(popup: tk.Toplevel, anchor: tk.Widget, num_rows: int) -> None:
    """Position popup below anchor; when maximized/fullscreen flip above and right-align."""
    import sys
    anchor.update_idletasks()
    ax    = anchor.winfo_rootx()
    ay    = anchor.winfo_rooty() + anchor.winfo_height()
    est_h = min(num_rows, _MAX_VIS) * _ROW_H + 4
    root  = anchor.winfo_toplevel()

    is_large = (root.state() == 'zoomed') or (
        sys.platform == "darwin" and bool(root.wm_attributes("-fullscreen"))
    )
    if is_large:
        # Right-align to IDOL's right edge, open above anchor
        sb_w = 18 if num_rows > _MAX_VIS else 0   # ttk scrollbar width
        ax = root.winfo_rootx() + root.winfo_width() - _LIST_W - sb_w - 4
        above = anchor.winfo_rooty() - est_h
        ay = above if above >= 4 else ay

    popup.geometry(f"+{ax}+{ay}")


# ── Variable picker ───────────────────────────────────────────────────────────

def collect_form_variables(form) -> list[tuple[str, str]]:
    """Return [(name, var_type), ...] for every variable defined on *form*.

    Pulls from widget VariableBindings first (in widget order), then from
    menu check/radiobutton variable fields. Deduped by name; first occurrence wins.
    """
    seen: set[str] = set()
    result: list[tuple[str, str]] = []

    for w in form.widgets:
        vb = w.variable
        if vb and vb.name and vb.name not in seen:
            seen.add(vb.name)
            result.append((vb.name, vb.var_type))

    for item in form.menu_items:
        if item.variable and item.variable not in seen:
            seen.add(item.variable)
            var_type = "BooleanVar" if item.kind == "checkbutton" else "StringVar"
            result.append((item.variable, var_type))

    return result


def show_variable_popup(
    anchor: tk.Widget,
    variables: list[tuple[str, str]],
    on_select: Callable[[str], None],
    entry_ref: tk.Entry | None = None,
    on_remove: Callable[[str], None] | None = None,
) -> tk.Toplevel | None:
    """Show a dark-themed popup below *anchor* listing *variables*.

    anchor    : widget whose bottom-left sets the popup position.
    variables : [(name, var_type), ...] list to display.
    on_select : called with the chosen variable name.
    entry_ref : if given, typing in this Entry filters the popup list live.

    Returns the Toplevel (caller may close it), or None if list is empty.
    """
    popup = tk.Toplevel(anchor)
    popup.overrideredirect(True)
    popup.configure(bg=_BORDER)

    inner = tk.Frame(popup, bg=_BG2, bd=0)
    inner.pack(fill="both", expand=True, padx=1, pady=1)

    if not variables:
        tk.Label(inner, text="(no variables defined yet)",
                 bg=_BG2, fg=_FG_DIM, font=(UI_FONT, 8),
                 padx=10, pady=6).pack(fill="x")
        _place_popup(popup, anchor, 1)
        _bind_dismiss(popup, anchor)
        return popup

    sf, canvas, _wheel = _scrollable_list(inner, len(variables))
    _place_popup(popup, anchor, len(variables))

    def _make_row(name: str, var_type: str) -> tk.Frame:
        row = tk.Frame(sf, bg=_BG2, cursor="hand2")
        tk.Label(row, text=name, bg=_BG2, fg=_FG,
                 font=(UI_FONT, 9), anchor="w", padx=8, pady=4).pack(side="left")
        tk.Label(row, text=f"({var_type})", bg=_BG2, fg=_FG_TYPE,
                 font=(UI_FONT, 8), anchor="e", padx=8, pady=4).pack(side="right")
        x_lbl = None
        if on_remove is not None:
            x_lbl = tk.Label(row, text="×", bg=_BG2, fg=_BG2,
                             font=(UI_FONT, 10, "bold"), cursor="hand2", padx=6)
            x_lbl.pack(side="right")

        def _set_hover(active: bool):
            bg = _BG_HOV if active else _BG2
            row.config(bg=bg)
            for child in row.winfo_children():
                child.config(bg=bg)
            if x_lbl is not None:
                x_lbl.config(fg=("#cc5555" if active else _BG2))
            if active and entry_ref is not None:
                entry_ref.delete(0, "end")
                entry_ref.insert(0, name)

        def _click(_):
            popup.destroy()
            on_select(name)

        def _remove_click(e):
            if on_remove:
                on_remove(name)
            row.pack_forget()
            try:
                sf.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass
            return "break"

        row.bind("<Enter>",          lambda e: _set_hover(True))
        row.bind("<Leave>",          lambda e: _set_hover(False))
        row.bind("<ButtonRelease-1>", _click)
        row.bind("<MouseWheel>",     _wheel)
        for child in row.winfo_children():
            child.bind("<Enter>",          lambda e: _set_hover(True))
            child.bind("<Leave>",          lambda e: _set_hover(False))
            child.bind("<MouseWheel>",     _wheel)
            if child is not x_lbl:
                child.bind("<ButtonRelease-1>", _click)
        if x_lbl is not None:
            x_lbl.bind("<Button-1>", _remove_click)
        row.pack(fill="x")
        return row

    all_rows: list[tuple[str, str, tk.Frame]] = []
    for name, var_type in variables:
        fr = _make_row(name, var_type)
        all_rows.append((name, var_type, fr))

    if entry_ref is not None:
        def _on_key_var(*_):
            try:
                if not popup.winfo_exists():
                    return
            except Exception:
                return
            term = entry_ref.get().lower()
            for _name, _vtype, fr in all_rows:
                try:
                    if term in _name.lower():
                        fr.pack(fill="x")
                    else:
                        fr.pack_forget()
                except Exception:
                    pass
            try:
                sf.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass
        entry_ref.bind("<KeyRelease>", _on_key_var, add=True)

    if entry_ref is not None:
        popup.after(10, lambda: entry_ref.focus_force() if entry_ref.winfo_exists() else None)

    _bind_dismiss(popup, anchor)
    return popup


# ── Handler picker ────────────────────────────────────────────────────────────

def collect_form_handlers(form) -> list[str]:
    """Return [handler_name, ...] for every event handler defined on *form*.

    Pulls from widget events first (in widget order), then from menu item
    command handlers. Deduped by name; first occurrence wins.
    """
    seen: set[str] = set()
    result: list[str] = []

    for w in form.widgets:
        for handler in w.events.values():
            if handler and handler not in seen:
                seen.add(handler)
                result.append(handler)

    for item in form.menu_items:
        if item.command_handler and item.command_handler not in seen:
            seen.add(item.command_handler)
            result.append(item.command_handler)

    for handler in form.form_events.values():
        if handler and handler not in seen:
            seen.add(handler)
            result.append(handler)

    return result


def show_handler_popup(
    anchor: tk.Widget,
    handlers: list[str],
    on_select: Callable[[str], None],
    entry_ref: tk.Entry | None = None,
    on_remove: Callable[[str], None] | None = None,
) -> tk.Toplevel | None:
    """Show a dark-themed popup below *anchor* listing *handlers*.

    anchor    : widget whose bottom-left sets the popup position.
    handlers  : [handler_name, ...] list to display.
    on_select : called with the chosen handler name.
    entry_ref : if given, typing in this Entry filters the popup list live.

    Returns the Toplevel (caller may close it), or None if list is empty.
    """
    popup = tk.Toplevel(anchor)
    popup.overrideredirect(True)
    popup.configure(bg=_BORDER)

    inner = tk.Frame(popup, bg=_BG2, bd=0)
    inner.pack(fill="both", expand=True, padx=1, pady=1)

    if not handlers:
        tk.Label(inner, text="(no handlers defined yet)",
                 bg=_BG2, fg=_FG_DIM, font=(UI_FONT, 8),
                 padx=10, pady=6).pack(fill="x")
        _place_popup(popup, anchor, 1)
        _bind_dismiss(popup, anchor)
        return popup

    sf, canvas, _wheel = _scrollable_list(inner, len(handlers))
    _place_popup(popup, anchor, len(handlers))

    def _make_row(name: str) -> tk.Frame:
        row = tk.Frame(sf, bg=_BG2, cursor="hand2")
        tk.Label(row, text=name, bg=_BG2, fg=_FG,
                 font=(UI_FONT, 9), anchor="w", padx=8, pady=4).pack(side="left")
        tk.Label(row, text="(handler)", bg=_BG2, fg=_FG_DIM,
                 font=(UI_FONT, 8), anchor="e", padx=8, pady=4).pack(side="right")
        x_lbl = None
        if on_remove is not None:
            x_lbl = tk.Label(row, text="×", bg=_BG2, fg=_BG2,
                             font=(UI_FONT, 10, "bold"), cursor="hand2", padx=6)
            x_lbl.pack(side="right")

        def _set_hover(active: bool):
            bg = _BG_HOV if active else _BG2
            row.config(bg=bg)
            for child in row.winfo_children():
                child.config(bg=bg)
            if x_lbl is not None:
                x_lbl.config(fg=("#cc5555" if active else _BG2))
            if active and entry_ref is not None:
                entry_ref.delete(0, "end")
                entry_ref.insert(0, name)

        def _click(_):
            popup.destroy()
            on_select(name)

        def _remove_click(e):
            if on_remove:
                on_remove(name)
            row.pack_forget()
            try:
                sf.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass
            return "break"

        row.bind("<Enter>",           lambda e: _set_hover(True))
        row.bind("<Leave>",           lambda e: _set_hover(False))
        row.bind("<ButtonRelease-1>", _click)
        row.bind("<MouseWheel>",      _wheel)
        for child in row.winfo_children():
            child.bind("<Enter>",           lambda e: _set_hover(True))
            child.bind("<Leave>",           lambda e: _set_hover(False))
            child.bind("<MouseWheel>",      _wheel)
            if child is not x_lbl:
                child.bind("<ButtonRelease-1>", _click)
        if x_lbl is not None:
            x_lbl.bind("<Button-1>", _remove_click)
        row.pack(fill="x")
        return row

    all_rows: list[tuple[str, tk.Frame]] = []
    for name in handlers:
        fr = _make_row(name)
        all_rows.append((name, fr))

    if entry_ref is not None:
        def _on_key_hdl(*_):
            try:
                if not popup.winfo_exists():
                    return
            except Exception:
                return
            term = entry_ref.get().lower()
            for _name, fr in all_rows:
                try:
                    if term in _name.lower():
                        fr.pack(fill="x")
                    else:
                        fr.pack_forget()
                except Exception:
                    pass
            try:
                sf.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass
        entry_ref.bind("<KeyRelease>", _on_key_hdl, add=True)

    if entry_ref is not None:
        popup.after(10, lambda: entry_ref.focus_force() if entry_ref.winfo_exists() else None)

    _bind_dismiss(popup, anchor)
    return popup


# ── Dismiss helper ────────────────────────────────────────────────────────────

def _bind_dismiss(popup: tk.Toplevel, anchor: tk.Widget) -> None:
    """Close *popup* when the user clicks outside it and outside *anchor*."""
    anchor_str = str(anchor)

    def _check_focus(event):
        w = str(event.widget)
        try:
            if w.startswith(str(popup)):
                return
            if w == anchor_str or w.startswith(anchor_str + "."):
                return
            popup.destroy()
        except Exception:
            popup.destroy()

    popup.bind_all("<Button-1>", _check_focus, add=True)
    popup.bind("<Escape>", lambda _: popup.destroy())


# ── Picker entry widgets ──────────────────────────────────────────────────────

class HandlerPickerEntry(tk.Frame):
    """Entry + ▾ button that opens a handler picker popup.

    Parameters
    ----------
    master        : parent widget
    get_handlers  : callable that returns [handler_name, ...] on demand
    textvariable  : tk.StringVar to bind to the Entry
    width         : Entry width in characters
    on_remove     : optional callback(name) called when × is clicked on a row
    """

    def __init__(
        self,
        master: tk.Widget,
        get_handlers: Callable[[], list[str]],
        textvariable: tk.StringVar | None = None,
        width: int = 14,
        entry_bg: str = "#3c3c3c",
        entry_fg: str = "#cccccc",
        btn_bg: str = "#3a3a3a",
        on_remove: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=entry_bg, **kwargs)
        self._get_handlers = get_handlers
        self._on_remove = on_remove
        self._popup: tk.Toplevel | None = None

        self.entry = tk.Entry(
            self,
            textvariable=textvariable,
            bg=entry_bg, fg=entry_fg,
            insertbackground=entry_fg,
            relief="flat", font=(UI_FONT, 9),
            width=width,
            highlightthickness=1,
            highlightcolor="#569cd6",
            highlightbackground="#3c3c3c",
        )
        self.entry.pack(side="left", fill="x", expand=True)

        self._btn = tk.Label(
            self,
            text="▾",
            bg=btn_bg, fg="#888888",
            font=(UI_FONT, 8),
            cursor="hand2",
            padx=4, pady=1,
        )
        self._btn.pack(side="left")
        self._btn.bind("<Button-1>",  lambda _: self._open_picker())
        self._btn.bind("<Enter>", lambda _: self._btn.config(fg="#cccccc"))
        self._btn.bind("<Leave>", lambda _: self._btn.config(fg="#888888"))

    def _open_picker(self) -> None:
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            return
        handlers = self._get_handlers()
        self._popup = show_handler_popup(
            anchor=self,
            handlers=handlers,
            on_select=self._on_select,
            entry_ref=self.entry,
            on_remove=self._on_remove,
        )

    def _on_select(self, name: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, name)
        self._popup = None


class VariablePickerEntry(tk.Frame):
    """Entry + ▾ button that opens a variable picker popup.

    Parameters
    ----------
    master       : parent widget
    get_vars     : callable that returns [(name, var_type), ...] on demand
    textvariable : tk.StringVar to bind to the Entry
    width        : Entry width in characters
    on_remove    : optional callback(name) called when × is clicked on a row
    """

    def __init__(
        self,
        master: tk.Widget,
        get_vars: Callable[[], list[tuple[str, str]]],
        textvariable: tk.StringVar | None = None,
        width: int = 14,
        entry_bg: str = "#3c3c3c",
        entry_fg: str = "#cccccc",
        btn_bg: str = "#3a3a3a",
        on_remove: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=entry_bg, **kwargs)
        self._get_vars = get_vars
        self._on_remove = on_remove
        self._popup: tk.Toplevel | None = None

        self.entry = tk.Entry(
            self,
            textvariable=textvariable,
            bg=entry_bg, fg=entry_fg,
            insertbackground=entry_fg,
            relief="flat", font=(UI_FONT, 9),
            width=width,
            highlightthickness=1,
            highlightcolor="#569cd6",
            highlightbackground="#3c3c3c",
        )
        self.entry.pack(side="left", fill="x", expand=True)

        self._btn = tk.Label(
            self,
            text="▾",
            bg=btn_bg, fg="#888888",
            font=(UI_FONT, 8),
            cursor="hand2",
            padx=4, pady=1,
        )
        self._btn.pack(side="left")
        self._btn.bind("<Button-1>",  lambda _: self._open_picker())
        self._btn.bind("<Enter>", lambda _: self._btn.config(fg="#cccccc"))
        self._btn.bind("<Leave>", lambda _: self._btn.config(fg="#888888"))

    def _open_picker(self) -> None:
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            return
        variables = self._get_vars()
        self._popup = show_variable_popup(
            anchor=self,
            variables=variables,
            on_select=self._on_select,
            entry_ref=self.entry,
            on_remove=self._on_remove,
        )

    def _on_select(self, name: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, name)
        self._popup = None
