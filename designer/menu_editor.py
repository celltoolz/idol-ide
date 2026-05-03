from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .model import MenuItemDescriptor
from .var_picker import VariablePickerEntry, collect_form_variables
from widgets.guide_window import GuideWindow, GuidePage

_BG       = "#1e1e1e"
_BG2      = "#2d2d2d"
_BG3      = "#3c3c3c"
_FG       = "#cccccc"
_FG_DIM   = "#858585"
_ACCENT   = "#569cd6"
_BTN_BG   = "#3a3a3a"
_ENTRY_BG = "#3c3c3c"
_SEL_BG   = "#094771"

_FIELD_HINTS: dict[str, str] = {
    "caption":   "Text displayed in the menu. Use & before a letter for an access key (e.g. &File). Set to  -  for a separator line.",
    "name":      "Code identifier. Cascade menus → self._m_<name>. Leaf commands → self._<name>_click handler stub. Keep lowercase with underscores.",
    "shortcut":  "Keyboard accelerator label shown on the right side of the item (e.g. Ctrl+S). Display only — add the actual key binding in your code.",
    "enabled":   "When unchecked the item is greyed out at startup. Can be toggled at runtime via your handler code.",
    "visible":   "When unchecked the item is hidden at startup. Can be toggled at runtime via your handler code.",
    "type":      "Item style: Command = standard action, Checkbutton = toggle with checkmark indicator, Radiobutton = exclusive selection with bullet indicator. Only available for indent ≥ 1.",
    "variable":  "Variable name tracking check/radio state. IDOL declares self.<name> = tk.BooleanVar() for checkbuttons or tk.StringVar() for radiobuttons.",
    "command":   "Optional handler name for check/radiobutton items. Generates command=self._<name>_click and a stub in the Events section.",
    "value":     "The string written to the variable when this radiobutton is selected (e.g. 'left', 'center', 'right'). All radiobuttons sharing the same Variable are mutually exclusive.",
    "separator": "Insert a horizontal divider line below the selected item. Separators visually group related menu items and don't require a Name or handler.",
    "btn_promote":  "Move the selected item one indent level up — turns a sub-menu item back into a top-level item or a sub-sub-item back into a sub-item.",
    "btn_demote":   "Move the selected item one indent level down — nests it inside the item above, creating a sub-menu.",
    "btn_move_up":  "Swap the selected item with the one above it.",
    "btn_move_down":"Swap the selected item with the one below it.",
    "btn_next":     "Move to the next item in the list. If the selected item is last, a new blank item is inserted automatically.",
    "btn_insert":   "Insert a new blank item directly below the selected item, inheriting its indent level.",
    "btn_delete":   "Remove the selected item from the list permanently.",
}

_SHORTCUTS = [
    "(None)", "Ctrl+A", "Ctrl+C", "Ctrl+D", "Ctrl+E", "Ctrl+F",
    "Ctrl+G", "Ctrl+H", "Ctrl+I", "Ctrl+K", "Ctrl+L", "Ctrl+M",
    "Ctrl+N", "Ctrl+O", "Ctrl+P", "Ctrl+Q", "Ctrl+R", "Ctrl+S",
    "Ctrl+T", "Ctrl+U", "Ctrl+V", "Ctrl+W", "Ctrl+X", "Ctrl+Y",
    "Ctrl+Z", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8",
    "F9", "F10", "F11", "F12", "Del", "Ins",
]


class MenuEditor(tk.Toplevel):
    """VB6-style Menu Editor dialog.

    Parameters
    ----------
    parent      : tk widget — owner window
    items       : current menu items list (will be deep-copied internally)
    on_save     : called with the new list when the user clicks OK
    """

    def __init__(
        self,
        parent: tk.Widget,
        items: list[MenuItemDescriptor],
        on_save: Callable[[list[MenuItemDescriptor]], None],
        form=None,
    ) -> None:
        super().__init__(parent)
        self.title("Menu Editor")
        self.resizable(False, False)
        self.configure(bg=_BG)
        self.grab_set()

        self._on_save = on_save
        self._form = form
        self._items: list[MenuItemDescriptor] = copy.deepcopy(items)
        self._selected_idx: int | None = None
        self._updating = False

        self._build_ui()
        self._refresh_listbox()
        if self._items:
            self._select(0)

        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        pw = parent.winfo_rootx() + parent.winfo_width() // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"{w}x{h}+{pw - w // 2}+{ph - h // 2}")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}

        # ── fields frame ──────────────────────────────────────────────────────
        fields = tk.Frame(self, bg=_BG)
        fields.pack(fill="x", **pad)

        def _label(parent, text, row, col):
            tk.Label(parent, text=text, bg=_BG, fg=_FG_DIM,
                     font=("Segoe UI", 9), anchor="w"
                     ).grid(row=row, column=col, sticky="w", padx=(0, 4), pady=3)

        def _entry(parent, row, col, width=24):
            e = tk.Entry(parent, bg=_ENTRY_BG, fg=_FG, insertbackground=_FG,
                         relief="flat", font=("Segoe UI", 9), width=width,
                         highlightthickness=1, highlightcolor=_ACCENT,
                         highlightbackground=_BG3)
            e.grid(row=row, column=col, sticky="ew", padx=(0, 12), pady=3)
            return e

        _label(fields, "Caption:", 0, 0)
        self._caption_var = tk.StringVar()
        self._caption_entry = _entry(fields, 0, 1)
        self._caption_entry.config(textvariable=self._caption_var)

        _label(fields, "Name:", 1, 0)
        self._name_var = tk.StringVar()
        self._name_entry = _entry(fields, 1, 1)
        self._name_entry.config(textvariable=self._name_var)

        _label(fields, "Shortcut:", 0, 2)
        self._shortcut_var = tk.StringVar(value="(None)")
        sc_frame = tk.Frame(fields, bg=_BG)
        sc_frame.grid(row=0, column=3, sticky="w", pady=3)
        self._shortcut_cb = ttk.Combobox(
            sc_frame, textvariable=self._shortcut_var,
            values=_SHORTCUTS, state="readonly",
            width=12, font=("Segoe UI", 9),
        )
        _style_combobox(self._shortcut_cb)
        self._shortcut_cb.pack()

        # checkboxes row
        chk_frame = tk.Frame(fields, bg=_BG)
        chk_frame.grid(row=1, column=2, columnspan=2, sticky="w", pady=3)
        self._enabled_var = tk.BooleanVar(value=True)
        self._visible_var = tk.BooleanVar(value=True)
        self._enabled_chk = tk.Checkbutton(
            chk_frame, text="Enabled", variable=self._enabled_var,
            bg=_BG, fg=_FG, selectcolor=_BG3, activebackground=_BG,
            activeforeground=_FG, font=("Segoe UI", 9),
            command=self._on_field_change,
        )
        self._enabled_chk.grid(row=0, column=0, padx=(0, 12))
        self._visible_chk = tk.Checkbutton(
            chk_frame, text="Visible", variable=self._visible_var,
            bg=_BG, fg=_FG, selectcolor=_BG3, activebackground=_BG,
            activeforeground=_FG, font=("Segoe UI", 9),
            command=self._on_field_change,
        )
        self._visible_chk.grid(row=0, column=1, padx=(0, 12))

        # type / variable / value row
        _label(fields, "Type:", 2, 0)
        self._kind_var = tk.StringVar(value="Command")
        kind_frame = tk.Frame(fields, bg=_BG)
        kind_frame.grid(row=2, column=1, sticky="w", pady=3)
        self._kind_cb = ttk.Combobox(
            kind_frame, textvariable=self._kind_var,
            values=["Command", "Checkbutton", "Radiobutton"],
            state="readonly", width=13, font=("Segoe UI", 9),
        )
        _style_combobox(self._kind_cb)
        self._kind_cb.pack()

        _label(fields, "Variable:", 2, 2)
        self._variable_var = tk.StringVar()
        self._variable_picker = VariablePickerEntry(
            fields,
            get_vars=self._get_form_variables,
            textvariable=self._variable_var,
            width=10,
            entry_bg=_ENTRY_BG, entry_fg=_FG, btn_bg=_BTN_BG,
        )
        self._variable_picker.grid(row=2, column=3, sticky="w", pady=3)
        self._variable_entry = self._variable_picker.entry

        _label(fields, "Command:", 3, 0)
        self._command_handler_var = tk.StringVar()
        self._command_handler_entry = _entry(fields, 3, 1, width=24)
        self._command_handler_entry.config(textvariable=self._command_handler_var)

        _label(fields, "Value:", 3, 2)
        self._value_var = tk.StringVar()
        self._value_entry = _entry(fields, 3, 3, width=14)
        self._value_entry.config(textvariable=self._value_var)

        fields.columnconfigure(1, weight=1)

        # ── arrow / action buttons ────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=_BG)
        btn_frame.pack(fill="x", padx=8, pady=(0, 4))

        def _wire_hover(b: tk.Button) -> None:
            b.bind("<Enter>", lambda _: b.config(fg="#ffffff"), add=True)
            b.bind("<Leave>", lambda _: b.config(fg=_FG),       add=True)

        arrow_frame = tk.Frame(btn_frame, bg=_BG)
        arrow_frame.pack(side="left")

        for sym, tip, hint_key, cmd in [
            ("←", "Promote (unindent)",    "btn_promote",   self._promote),
            ("→", "Demote (make submenu)", "btn_demote",    self._demote),
            ("↑", "Move up",               "btn_move_up",   self._move_up),
            ("↓", "Move down",             "btn_move_down", self._move_down),
        ]:
            b = tk.Button(
                arrow_frame, text=sym, width=3,
                bg=_BTN_BG, fg=_FG, activebackground=_BG3, activeforeground=_FG,
                relief="flat", font=("Segoe UI", 10), cursor="hand2",
                command=cmd,
            )
            b.pack(side="left", padx=2)
            _bind_tooltip(b, tip)
            _wire_hover(b)
            setattr(self, f"_{hint_key}_btn", b)

        action_frame = tk.Frame(btn_frame, bg=_BG)
        action_frame.pack(side="right")

        for text, width, hint_key, cmd in [
            ("Next",      7, "btn_next",    self._next),
            ("Insert",    7, "btn_insert",  self._insert),
            ("Delete",    7, "btn_delete",  self._delete),
            ("Separator", 9, "separator",   self._insert_separator),
        ]:
            b = tk.Button(
                action_frame, text=text, width=width,
                bg=_BTN_BG, fg=_FG, activebackground=_BG3, activeforeground=_FG,
                relief="flat", font=("Segoe UI", 9), cursor="hand2",
                command=cmd,
            )
            b.pack(side="left", padx=2)
            _wire_hover(b)
            setattr(self, f"_{hint_key}_btn", b)

        # ── listbox ───────────────────────────────────────────────────────────
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8)
        lb_frame = tk.Frame(self, bg=_BG)
        lb_frame.pack(fill="both", expand=True, padx=8, pady=6)

        sb = tk.Scrollbar(lb_frame, orient="vertical", bg=_BG2, troughcolor=_BG,
                          width=10, relief="flat", borderwidth=0)
        self._listbox = tk.Listbox(
            lb_frame, bg=_BG2, fg=_FG,
            selectbackground=_SEL_BG, selectforeground="#ffffff",
            font=("Segoe UI", 9), relief="flat", borderwidth=0,
            activestyle="none", height=10, width=48,
            yscrollcommand=sb.set,
        )
        sb.config(command=self._listbox.yview)
        sb.pack(side="right", fill="y")
        self._listbox.pack(side="left", fill="both", expand=True)
        self._listbox.bind("<<ListboxSelect>>", self._on_listbox_select)
        self._listbox.bind("<Button-3>",        self._on_listbox_right_click)
        self._listbox.bind("<Button-2>",        self._on_listbox_right_click)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8)
        ok_frame = tk.Frame(self, bg=_BG)
        ok_frame.pack(fill="x", padx=8, pady=6)

        tk.Button(
            ok_frame, text="OK", width=9,
            bg=_ACCENT, fg="#ffffff", activebackground="#4a8ec2",
            activeforeground="#ffffff", relief="flat",
            font=("Segoe UI", 9, "bold"), cursor="hand2",
            command=self._ok,
        ).pack(side="right", padx=(4, 0))
        tk.Button(
            ok_frame, text="Cancel", width=9,
            bg=_BTN_BG, fg=_FG, activebackground=_BG3, activeforeground=_FG,
            relief="flat", font=("Segoe UI", 9), cursor="hand2",
            command=self.destroy,
        ).pack(side="right")
        tk.Label(
            ok_frame, text="? Menu Editor", bg=_BG, fg=_ACCENT,
            font=("Segoe UI", 9), cursor="hand2",
        ).pack(side="left")
        ok_frame.winfo_children()[-1].bind("<Button-1>", lambda _: self._open_guide())

        # ── hint bar ──────────────────────────────────────────────────────────
        self._hint_label = tk.Label(
            self, text="", bg=_BG2, fg="#888888",
            font=("Segoe UI", 8), anchor="nw", padx=8, pady=4,
            wraplength=460, justify="left", height=3,
        )
        self._hint_label.pack(fill="x", padx=8, pady=(0, 8))
        self._hint_label.bind(
            "<Configure>",
            lambda e: self._hint_label.config(wraplength=max(1, e.width - 16)),
        )

        # wire field-change callbacks after all widgets exist
        self._caption_var.trace_add("write", lambda *_: self._on_field_change())
        self._name_var.trace_add("write", lambda *_: self._on_field_change())
        self._shortcut_var.trace_add("write", lambda *_: self._on_field_change())
        self._kind_var.trace_add("write", lambda *_: self._on_field_change())
        self._variable_var.trace_add("write", lambda *_: self._on_field_change())
        self._command_handler_var.trace_add("write", lambda *_: self._on_field_change())
        self._value_var.trace_add("write", lambda *_: self._on_field_change())

        # hover hints
        _h = self._bind_hint
        _h(self._caption_entry,         "caption")
        _h(self._name_entry,            "name")
        _h(self._shortcut_cb,           "shortcut")
        _h(self._enabled_chk,           "enabled")
        _h(self._visible_chk,           "visible")
        _h(self._kind_cb,               "type")
        _h(self._variable_entry,        "variable")
        _h(self._command_handler_entry, "command")
        _h(self._value_entry,           "value")
        _h(self._btn_promote_btn,   "btn_promote")
        _h(self._btn_demote_btn,    "btn_demote")
        _h(self._btn_move_up_btn,   "btn_move_up")
        _h(self._btn_move_down_btn, "btn_move_down")
        _h(self._btn_next_btn,      "btn_next")
        _h(self._btn_insert_btn,    "btn_insert")
        _h(self._btn_delete_btn,    "btn_delete")
        _h(self._separator_btn,     "separator")

    def _get_form_variables(self) -> list[tuple[str, str]]:
        """Collect all defined variables — from the form (if available) plus current menu items."""
        base = collect_form_variables(self._form) if self._form is not None else []
        seen = {name for name, _ in base}
        extra = []
        for item in self._items:
            if item.variable and item.variable not in seen:
                seen.add(item.variable)
                var_type = "BooleanVar" if item.kind == "checkbutton" else "StringVar"
                extra.append((item.variable, var_type))
        return base + extra

    # ── Hint bar ──────────────────────────────────────────────────────────────

    def _show_hint(self, text: str) -> None:
        self._hint_label.config(text=text)

    def _clear_hint(self) -> None:
        self._hint_label.config(text="")

    def _bind_hint(self, widget: tk.Widget, key: str) -> None:
        text = _FIELD_HINTS.get(key, "")
        widget.bind("<Enter>", lambda _: self._show_hint(text), add=True)
        widget.bind("<Leave>", lambda _: self._clear_hint(),    add=True)

    # ── Listbox helpers ───────────────────────────────────────────────────────

    def _refresh_listbox(self) -> None:
        self._listbox.delete(0, "end")
        for item in self._items:
            prefix = "    " * item.indent
            label = item.display_caption if item.caption else "(new item)"
            if item.caption == "-":
                label = "  ─────────────────"
                prefix = "    " * item.indent + " "
            self._listbox.insert("end", f"{prefix}{label}")
        if self._selected_idx is not None and self._items:
            idx = min(self._selected_idx, len(self._items) - 1)
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(idx)
            self._listbox.see(idx)

    def _select(self, idx: int) -> None:
        self._selected_idx = idx
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        self._load_fields(self._items[idx])

    def select_item(self, idx: int) -> None:
        if 0 <= idx < len(self._items):
            self._select(idx)

    def flash_command_field(self) -> None:
        entry = self._command_handler_entry
        orig  = entry.cget("bg")

        def _toggle(n: int, on: bool) -> None:
            if n == 0:
                entry.config(bg=orig)
                return
            entry.config(bg="#7a1a1a" if on else orig)
            self.after(180, lambda: _toggle(n - 1, not on))

        _toggle(6, True)
        entry.focus_set()

    def _load_fields(self, item: MenuItemDescriptor) -> None:
        self._updating = True
        self._caption_var.set(item.caption)
        self._name_var.set(item.name)
        sc = item.shortcut if item.shortcut else "(None)"
        self._shortcut_var.set(sc if sc in _SHORTCUTS else "(None)")
        self._enabled_var.set(item.enabled)
        self._visible_var.set(item.visible)
        self._kind_var.set(item.kind.capitalize() if item.kind else "Command")
        self._variable_var.set(item.variable)
        self._command_handler_var.set(item.command_handler)
        self._value_var.set(item.value)
        self._updating = False
        self._update_kind_state(item)

    def _current_item(self) -> MenuItemDescriptor | None:
        if self._selected_idx is None or not self._items:
            return None
        return self._items[self._selected_idx]

    # ── Field-change callback ─────────────────────────────────────────────────

    def _update_kind_state(self, item: MenuItemDescriptor) -> None:
        """Enable/disable Variable, Command, and Value entries based on type and indent."""
        is_leaf = item.indent > 0 and item.caption != "-"
        kind = self._kind_var.get().lower()
        is_check_radio = is_leaf and kind in ("checkbutton", "radiobutton")
        kind_state = "readonly" if is_leaf else "disabled"
        var_state  = "normal" if is_check_radio else "disabled"
        cmd_state  = "normal" if is_check_radio else "disabled"
        val_state  = "normal" if is_leaf and kind == "radiobutton" else "disabled"
        self._kind_cb.configure(state=kind_state)
        self._variable_entry.configure(state=var_state)
        self._command_handler_entry.configure(state=cmd_state)
        self._value_entry.configure(state=val_state)

    def _on_field_change(self) -> None:
        if self._updating:
            return
        item = self._current_item()
        if item is None:
            return
        item.caption  = self._caption_var.get()
        item.name     = self._name_var.get()
        sc = self._shortcut_var.get()
        item.shortcut = "" if sc == "(None)" else sc
        item.enabled  = self._enabled_var.get()
        item.visible  = self._visible_var.get()
        item.kind            = self._kind_var.get().lower()
        item.variable        = self._variable_var.get()
        item.command_handler = self._command_handler_var.get()
        item.value           = self._value_var.get()
        self._update_kind_state(item)
        self._refresh_listbox()

    # ── Listbox selection ─────────────────────────────────────────────────────

    def _on_listbox_select(self, _event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        self._selected_idx = sel[0]
        self._load_fields(self._items[self._selected_idx])

    # ── Arrow / action buttons ────────────────────────────────────────────────

    def _promote(self) -> None:
        item = self._current_item()
        if item and item.indent > 0:
            item.indent -= 1
            self._refresh_listbox()

    def _demote(self) -> None:
        item = self._current_item()
        if item is None:
            return
        idx = self._selected_idx
        max_indent = (self._items[idx - 1].indent + 1) if idx and idx > 0 else 0
        if item.indent < max_indent:
            item.indent += 1
            self._refresh_listbox()

    def _move_up(self) -> None:
        idx = self._selected_idx
        if idx is None or idx == 0:
            return
        self._items[idx], self._items[idx - 1] = self._items[idx - 1], self._items[idx]
        self._selected_idx = idx - 1
        self._refresh_listbox()

    def _move_down(self) -> None:
        idx = self._selected_idx
        if idx is None or idx >= len(self._items) - 1:
            return
        self._items[idx], self._items[idx + 1] = self._items[idx + 1], self._items[idx]
        self._selected_idx = idx + 1
        self._refresh_listbox()

    def _next(self) -> None:
        idx = self._selected_idx
        if idx is None:
            return
        next_idx = idx + 1
        if next_idx >= len(self._items):
            self._insert()
        else:
            self._select(next_idx)

    def _insert(self) -> None:
        indent = 0
        if self._selected_idx is not None and self._items:
            indent = self._items[self._selected_idx].indent
        new_item = MenuItemDescriptor(caption="", name="", indent=indent)
        insert_at = (self._selected_idx + 1) if self._selected_idx is not None else len(self._items)
        self._items.insert(insert_at, new_item)
        self._selected_idx = insert_at
        self._refresh_listbox()
        self._load_fields(new_item)
        self._caption_entry.focus_set()

    def _delete(self) -> None:
        idx = self._selected_idx
        if idx is None or not self._items:
            return
        self._items.pop(idx)
        if not self._items:
            self._selected_idx = None
            self._listbox.delete(0, "end")
            self._caption_var.set("")
            self._name_var.set("")
            return
        new_idx = min(idx, len(self._items) - 1)
        self._selected_idx = new_idx
        self._refresh_listbox()
        self._load_fields(self._items[new_idx])

    def _insert_separator(self) -> None:
        indent = 0
        if self._selected_idx is not None and self._items:
            indent = self._items[self._selected_idx].indent
        sep = MenuItemDescriptor(caption="-", indent=indent)
        insert_at = (self._selected_idx + 1) if self._selected_idx is not None else len(self._items)
        self._items.insert(insert_at, sep)
        self._selected_idx = insert_at
        self._refresh_listbox()
        self._load_fields(sep)

    def _toggle_enabled(self) -> None:
        item = self._current_item()
        if item is None:
            return
        item.enabled = not item.enabled
        self._enabled_var.set(item.enabled)

    def _toggle_visible(self) -> None:
        item = self._current_item()
        if item is None:
            return
        item.visible = not item.visible
        self._visible_var.set(item.visible)

    def _on_listbox_right_click(self, event: tk.Event) -> None:
        idx = self._listbox.nearest(event.y)
        if 0 <= idx < len(self._items):
            self._select(idx)
        item = self._current_item()

        m = tk.Menu(self, tearoff=0,
                    bg=_BG2, fg=_FG,
                    activebackground=_SEL_BG, activeforeground="#ffffff",
                    relief="flat", bd=1, font=("Segoe UI", 9))

        m.add_command(label="← Promote",   command=self._promote)
        m.add_command(label="→ Demote",    command=self._demote)
        m.add_separator()
        m.add_command(label="↑ Move Up",   command=self._move_up)
        m.add_command(label="↓ Move Down", command=self._move_down)
        m.add_separator()
        m.add_command(label="Next",        command=self._next)
        m.add_command(label="Insert",      command=self._insert)
        m.add_command(label="Delete",      command=self._delete)
        m.add_separator()
        if item is not None:
            en_label = "Disable item" if item.enabled else "Enable item"
            vi_label = "Hide item"    if item.visible else "Show item"
            m.add_command(label=en_label,  command=self._toggle_enabled)
            m.add_command(label=vi_label,  command=self._toggle_visible)
            m.add_separator()
        m.add_command(label="Add Separator", command=self._insert_separator)

        m.tk_popup(event.x_root, event.y_root)

    # ── Guide ─────────────────────────────────────────────────────────────────

    def _open_guide(self) -> None:
        GuideWindow(self, "Menu Editor Guide", [
            GuidePage(
                title="Building a Menu Bar",
                sections=[
                    ("THE IDEA",
                     "A menu bar sits at the top of your form window and gives users a standard "
                     "way to access commands — File → Open, Edit → Cut, Help → About, etc. "
                     "IDOL generates the full tk.Menu hierarchy and stubs out every command handler "
                     "automatically so you can jump straight to writing the logic.",
                     "#569cd6"),
                    ("STRUCTURE",
                     "Menus are a flat list with an indent level:\n"
                     "  indent 0 — top-level menu name on the bar (e.g. File, Edit, Help)\n"
                     "  indent 1 — item inside that menu (e.g. Open, Save, Exit)\n"
                     "  indent 2 — sub-menu item nested one level deeper\n\n"
                     "Use → to demote an item (increase indent) and ← to promote it. "
                     "You can only demote an item one level deeper than the item above it.",
                     "#73c991"),
                    ("SEPARATORS",
                     "Set Caption to  -  (a single hyphen) to insert a separator line. "
                     "Separators don't need a Name and won't generate a handler.",
                     "#e2c08d"),
                ],
                plain_english=(
                    "Think of the indent levels like a tree: the trunk is the menu bar, "
                    "the branches are the top-level menus (File, Edit…), and the leaves "
                    "are the clickable items. Leaves get handler stubs; branches don't."
                ),
            ),
            GuidePage(
                title="Fields Reference",
                sections=[
                    ("CAPTION",
                     "The text the user sees in the menu. Use & before a letter to set an "
                     "access key (e.g. &File underlines the F on Windows). "
                     "Set to  -  for a separator line.", "#569cd6"),
                    ("NAME",
                     "The code identifier for this item. IDOL generates "
                     "self._m_<name> for cascade menus and calls self._<name>_click "
                     "for leaf commands. Keep it lowercase with underscores (e.g. open_file, exit). "
                     "Leave blank for separators.", "#73c991"),
                    ("SHORTCUT",
                     "Optional keyboard accelerator shown on the right of the menu item "
                     "(e.g. Ctrl+S). This only displays the label — you still need to add "
                     "the actual key binding in your code.", "#e2c08d"),
                    ("ENABLED / VISIBLE",
                     "Enabled controls whether the item is greyed out at startup. "
                     "Visible controls whether it appears at all. "
                     "Both can be toggled at runtime from your handler code.", "#cccccc"),
                    ("TYPE",
                     "Controls what kind of menu item is generated (enabled for indent ≥ 1 only):\n\n"
                     "  Command     — standard clickable item, generates command=self._<name>_click\n"
                     "  Checkbutton — toggleable on/off item with a checkmark indicator\n"
                     "  Radiobutton — mutually exclusive selection item with a bullet indicator\n\n"
                     "Type is disabled for top-level cascade items (indent 0) and separators.",
                     "#bd93f9"),
                    ("VARIABLE  /  VALUE  /  COMMAND",
                     "These three fields activate when Type is Checkbutton or Radiobutton:\n\n"
                     "  Variable — name of the tk variable on self that tracks the state, e.g. "
                     "word_wrap_var. IDOL declares self.word_wrap_var = tk.BooleanVar() for "
                     "checkbuttons and tk.StringVar() for radiobuttons.\n\n"
                     "  Value    — (radiobutton only) the string written to the variable when this "
                     "item is selected, e.g. 'left', 'center', 'right'.\n\n"
                     "  Command  — optional handler name. If set, IDOL generates "
                     "command=self._<name>_click and a stub in the Events section. "
                     "Leave blank if you only need the variable.",
                     "#ff79c6"),
                ],
                plain_english=(
                    "For a group of radiobuttons give them all the same Variable and different "
                    "Values — tkinter keeps them in sync automatically. "
                    "A Command is only needed when you want to run extra logic the moment the "
                    "selection changes; otherwise just read the variable whenever you need it."
                ),
            ),
            GuidePage(
                title="Tips & Generated Code",
                sections=[
                    ("ARROW BUTTONS",
                     "←  Promote — moves item one indent level up (e.g. sub-item → item)\n"
                     "→  Demote  — moves item one indent level down (makes a sub-menu)\n"
                     "↑  Move Up   — swap with the item above\n"
                     "↓  Move Down — swap with the item below\n\n"
                     "Insert adds a new item below the current one. "
                     "Next moves to the next item or inserts if you're at the end.", "#569cd6"),
                    ("WHAT GETS GENERATED",
                     "For each top-level menu IDOL emits:\n"
                     "    self._m_file = tk.Menu(self._menu_bar, tearoff=0)\n"
                     "    self._menu_bar.add_cascade(label='File', menu=self._m_file)\n\n"
                     "For a checkbutton item:\n"
                     "    self.word_wrap_var = tk.BooleanVar()          # in __init__\n"
                     "    self._m_view.add_checkbutton(label='Word Wrap',\n"
                     "        variable=self.word_wrap_var)\n\n"
                     "For a radiobutton group:\n"
                     "    self.align_var = tk.StringVar()               # in __init__\n"
                     "    self._m_format.add_radiobutton(label='Left',\n"
                     "        variable=self.align_var, value='left')\n\n"
                     "For a leaf command:\n"
                     "    self._m_file.add_command(label='Exit', command=self._exit_click)\n\n"
                     "And in the Events section:\n"
                     "    def _exit_click(self, *args):\n"
                     "        pass  # TODO", "#73c991"),
                    ("CANVAS PREVIEW",
                     "After closing this editor the menu bar appears live on the designer canvas "
                     "below the title bar. Click any top-level menu name to see the dropdown. "
                     "Command items and check/radiobutton items with a Command set will navigate "
                     "straight to their handler stub when clicked.", "#e2c08d"),
                ],
                plain_english=(
                    "Generate Code (Ctrl+Shift+G) after building your menu and all the stubs "
                    "will be waiting for you in the Events section — just fill in the logic."
                ),
            ),
        ])

    # ── OK ────────────────────────────────────────────────────────────────────

    def _ok(self) -> None:
        self._on_save(self._items)
        self.destroy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _style_combobox(cb: ttk.Combobox) -> None:
    style = ttk.Style()
    name = f"MenuEd.TCombobox"
    style.configure(name, fieldbackground=_ENTRY_BG, background=_BTN_BG,
                    foreground=_FG, selectbackground=_SEL_BG,
                    selectforeground="#ffffff", arrowcolor=_FG_DIM)
    cb.configure(style=name)


def _bind_tooltip(widget: tk.Widget, text: str) -> None:
    tip: tk.Toplevel | None = None

    def _show(e):
        nonlocal tip
        tip = tk.Toplevel(widget)
        tip.overrideredirect(True)
        tip.configure(bg="#252526")
        tk.Label(tip, text=text, bg="#252526", fg=_FG,
                 font=("Segoe UI", 8), padx=4, pady=2).pack()
        tip.geometry(f"+{e.x_root + 12}+{e.y_root + 16}")

    def _hide(_e):
        nonlocal tip
        if tip:
            tip.destroy()
            tip = None

    widget.bind("<Enter>", _show)
    widget.bind("<Leave>", _hide)
