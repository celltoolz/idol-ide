"""Variable picker — shared popup for selecting or typing a tkinter variable name.

Used by both the properties panel (inline treeview editor) and the menu editor
(standalone Entry + button widget).
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

_BG      = "#1e1e1e"
_BG2     = "#2d2d2d"
_BG_HOV  = "#094771"
_FG      = "#cccccc"
_FG_DIM  = "#858585"
_FG_TYPE = "#569cd6"
_BORDER  = "#3a3a3a"


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

    # Position below anchor
    anchor.update_idletasks()
    ax = anchor.winfo_rootx()
    ay = anchor.winfo_rooty() + anchor.winfo_height()
    popup.geometry(f"+{ax}+{ay}")

    inner = tk.Frame(popup, bg=_BG2, bd=0)
    inner.pack(fill="both", expand=True, padx=1, pady=1)

    if not variables:
        tk.Label(inner, text="(no variables defined yet)",
                 bg=_BG2, fg=_FG_DIM, font=("Segoe UI", 8),
                 padx=10, pady=6).pack(fill="x")
        _bind_dismiss(popup, anchor)
        return popup

    row_widgets: list[tk.Frame] = []

    def _make_row(name: str, var_type: str) -> tk.Frame:
        row = tk.Frame(inner, bg=_BG2, cursor="hand2")
        tk.Label(row, text=name, bg=_BG2, fg=_FG,
                 font=("Segoe UI", 9), anchor="w", padx=8, pady=4).pack(side="left")
        tk.Label(row, text=f"({var_type})", bg=_BG2, fg=_FG_TYPE,
                 font=("Segoe UI", 8), anchor="e", padx=8, pady=4).pack(side="right")

        def _enter(_):
            row.config(bg=_BG_HOV)
            for child in row.winfo_children():
                child.config(bg=_BG_HOV)

        def _leave(_):
            row.config(bg=_BG2)
            for child in row.winfo_children():
                child.config(bg=_BG2)

        def _click(_):
            popup.destroy()
            on_select(name)

        row.bind("<Enter>",   _enter)
        row.bind("<Leave>",   _leave)
        row.bind("<Button-1>", _click)
        for child in row.winfo_children():
            child.bind("<Button-1>", _click)
        row.pack(fill="x")
        return row

    all_rows: list[tuple[str, str, tk.Frame]] = []
    for name, var_type in variables:
        fr = _make_row(name, var_type)
        all_rows.append((name, var_type, fr))

    # Live filter when entry_ref is supplied
    if entry_ref is not None:
        def _on_key(*_):
            term = entry_ref.get().lower()
            for name, var_type, fr in all_rows:
                if term in name.lower():
                    fr.pack(fill="x")
                else:
                    fr.pack_forget()
        entry_ref.bind("<KeyRelease>", _on_key, add=True)

    # Re-focus the entry after the popup renders so typing works immediately
    if entry_ref is not None:
        popup.after(10, lambda: entry_ref.focus_force() if entry_ref.winfo_exists() else None)

    _bind_dismiss(popup, anchor)
    return popup


def _bind_dismiss(popup: tk.Toplevel, anchor: tk.Widget) -> None:
    """Close *popup* when the user clicks outside it and outside *anchor*."""
    anchor_str = str(anchor)

    def _check_focus(event):
        w = str(event.widget)
        try:
            # Keep alive: click is inside the popup itself
            if w.startswith(str(popup)):
                return
            # Keep alive: click is on the anchor widget or any of its children
            if w == anchor_str or w.startswith(anchor_str + "."):
                return
            popup.destroy()
        except Exception:
            popup.destroy()

    popup.bind_all("<Button-1>", _check_focus, add=True)
    popup.bind("<Escape>", lambda _: popup.destroy())


class VariablePickerEntry(tk.Frame):
    """Entry + ▾ button that opens a variable picker popup.

    Parameters
    ----------
    master       : parent widget
    get_vars     : callable that returns [(name, var_type), ...] on demand
    textvariable : tk.StringVar to bind to the Entry
    width        : Entry width in characters
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
        **kwargs,
    ) -> None:
        super().__init__(master, bg=entry_bg, **kwargs)
        self._get_vars = get_vars
        self._popup: tk.Toplevel | None = None

        self.entry = tk.Entry(
            self,
            textvariable=textvariable,
            bg=entry_bg, fg=entry_fg,
            insertbackground=entry_fg,
            relief="flat", font=("Segoe UI", 9),
            width=width,
            highlightthickness=1,
            highlightcolor="#569cd6",
            highlightbackground="#3c3c3c",
        )
        self.entry.pack(side="left", fill="x", expand=True)

        self._btn = tk.Button(
            self,
            text="▾", width=2,
            bg=btn_bg, fg="#888888",
            activebackground="#4a4a4a", activeforeground="#cccccc",
            relief="flat", font=("Segoe UI", 8),
            cursor="hand2",
            command=self._open_picker,
        )
        self._btn.pack(side="left")

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
        )

    def _on_select(self, name: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, name)
        self._popup = None
