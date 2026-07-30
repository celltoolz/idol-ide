"""Settings — a notebook tab, rendered entirely from the schema.

Two panes: categories on the left, settings on the right, with a search box
that flattens across every category. A notebook tab rather than a modal because
that is what Package Manager and Welcome already are, and because you want to
keep it open while trying a change out.

Nothing here knows what any individual setting *means*. Rows are built from
`utils.settings.SCHEMA` by `kind`, and writes go through `settings.set`, which
notifies the app to apply them. Adding a preference stays a one-line change to
the schema — the same property that makes `HANDLER_CATALOG` cheap to extend.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from utils import settings
from utils.ui_font import UI_FONT
from widgets.color_picker import askcolor
from widgets.dark_checkbox import DarkCheckbox
from widgets.font_chooser import askfont
from widgets.scrollbar import VerticalScrollbar

# Palette shared with project_wizard.py / font_chooser.py.
_BG      = "#252526"
_NAV_BG  = "#2d2d30"
_ITEM_BG = "#1e1e1e"
_FG      = "#cccccc"
_DIM     = "#858585"
_ACCENT  = "#0e639c"
_BORDER  = "#3c3c3c"
_HOVER   = "#37373d"
_SEL     = "#094771"

_NAV_W = 168


class SettingsPanel(tk.Frame):
    """The Settings tab. Construct, pack, done — it reads the schema itself."""

    def __init__(self, parent, on_dirty: Callable[[], None] | None = None) -> None:
        super().__init__(parent, bg=_BG)
        self._on_dirty = on_dirty
        self._sections = settings.sections()
        self._active = self._sections[0] if self._sections else ""
        self._nav_labels: dict[str, tk.Label] = {}
        self._rows: list[tk.Widget] = []
        # Per-key handles so a single change updates one row instead of
        # rebuilding the pane — see `_after_change`.
        self._reset_labels: dict[str, tk.Label] = {}
        self._refreshers: dict[str, Callable[[], None]] = {}

        self._build_header()
        body = tk.Frame(self, bg=_BG)
        body.pack(fill="both", expand=True)
        self._build_nav(body)
        self._build_content(body)
        self._render()

        # Follow changes made anywhere else — the View menu toggles the same
        # keys, and an open panel showing a stale value is worse than no panel.
        # Refreshing to the value already displayed is a no-op, so reacting to
        # our own writes costs nothing.
        self._unsubscribe = settings.subscribe(self._on_external_change)
        self.bind("<Destroy>", self._on_destroy, add="+")

    # ── Chrome ────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        head = tk.Frame(self, bg=_BG)
        head.pack(fill="x", padx=16, pady=(14, 10))
        tk.Label(head, text="Settings", bg=_BG, fg=_FG,
                 font=(UI_FONT, 14, "bold")).pack(side="left")

        wrap = tk.Frame(head, bg=_BORDER, padx=1, pady=1)
        wrap.pack(side="right")
        inner = tk.Frame(wrap, bg=_ITEM_BG)
        inner.pack()
        tk.Label(inner, text="⌕", bg=_ITEM_BG, fg=_DIM,
                 font=(UI_FONT, 10)).pack(side="left", padx=(6, 2))
        self._query = tk.StringVar()
        self._query.trace_add("write", lambda *_: self._render())
        entry = tk.Entry(inner, textvariable=self._query, bg=_ITEM_BG, fg=_FG,
                         insertbackground=_FG, relief="flat", bd=0,
                         font=(UI_FONT, 9), width=28)
        entry.pack(side="left", ipady=4, padx=(0, 8))
        self._search_entry = entry

    def _build_nav(self, parent) -> None:
        nav = tk.Frame(parent, bg=_NAV_BG, width=_NAV_W)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        for name in self._sections:
            lbl = tk.Label(nav, text=name, bg=_NAV_BG, fg=_FG, anchor="w",
                           font=(UI_FONT, 10), padx=16, pady=7, cursor="hand2")
            lbl.pack(fill="x")
            lbl.bind("<ButtonRelease-1>", lambda _e, n=name: self._select(n))
            lbl.bind("<Enter>", lambda _e, w=lbl: self._nav_hover(w, True))
            lbl.bind("<Leave>", lambda _e, w=lbl: self._nav_hover(w, False))
            self._nav_labels[name] = lbl

    def _nav_hover(self, lbl: tk.Label, entering: bool) -> None:
        if lbl.cget("bg") == _SEL:
            return                      # the selected row keeps its highlight
        lbl.config(bg=_HOVER if entering else _NAV_BG)

    def _build_content(self, parent) -> None:
        holder = tk.Frame(parent, bg=_BG)
        holder.pack(side="left", fill="both", expand=True)
        self._canvas = tk.Canvas(holder, bg=_BG, highlightthickness=0)
        bar = VerticalScrollbar(holder, width=12, command=self._canvas.yview)
        bar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.configure(yscrollcommand=bar.set)

        self._inner = tk.Frame(self._canvas, bg=_BG)
        self._win = self._canvas.create_window((0, 0), window=self._inner,
                                               anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        # Match the inner frame to the canvas width so rows can right-align
        # their controls against a real edge rather than their own content.
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._win, width=e.width))
        for seq, delta in (("<MouseWheel>", None), ("<Button-4>", -1),
                           ("<Button-5>", 1)):
            self._canvas.bind(seq, lambda e, d=delta: self._on_wheel(e, d))

    def _on_wheel(self, event, direction) -> None:
        if direction is None:
            direction = -1 if event.delta > 0 else 1
        self._canvas.yview_scroll(direction, "units")

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _select(self, section: str) -> None:
        self._active = section
        if self._query.get():
            self._query.set("")         # leaving search returns to categories
        else:
            self._render()

    def _render(self) -> None:
        """Full rebuild. Only for changing section or search — never for a
        value change, which `_after_change` handles in place."""
        for w in self._rows:
            w.destroy()
        self._rows.clear()
        self._reset_labels.clear()
        self._refreshers.clear()

        query = self._query.get().strip().lower()
        searching = bool(query)
        for name, lbl in self._nav_labels.items():
            selected = (not searching) and name == self._active
            lbl.config(bg=_SEL if selected else _NAV_BG,
                       fg="#ffffff" if selected else _FG)

        if searching:
            # Search spans every category, grouped under headings, so a setting
            # is findable without knowing which category someone filed it under.
            any_hit = False
            for section in self._sections:
                hits = [s for s in settings.settings_in(section)
                        if self._matches(s, query)]
                if not hits:
                    continue
                any_hit = True
                self._add_heading(section)
                for s in hits:
                    self._add_row(s)
            if not any_hit:
                self._add_empty(f'No settings match "{self._query.get()}".')
        else:
            for s in settings.settings_in(self._active):
                self._add_row(s)

        self._canvas.yview_moveto(0)

    @staticmethod
    def _matches(setting: settings.Setting, query: str) -> bool:
        # The key is searchable too: someone reading a config file or a commit
        # message has the dotted key, not the label.
        return query in " ".join(
            (setting.label, setting.description, setting.key)).lower()

    def _add_heading(self, text: str) -> None:
        lbl = tk.Label(self._inner, text=text.upper(), bg=_BG, fg=_DIM,
                       font=(UI_FONT, 8, "bold"), anchor="w")
        lbl.pack(fill="x", padx=20, pady=(14, 2))
        self._rows.append(lbl)

    def _add_empty(self, text: str) -> None:
        lbl = tk.Label(self._inner, text=text, bg=_BG, fg=_DIM,
                       font=(UI_FONT, 9), anchor="w")
        lbl.pack(fill="x", padx=20, pady=20)
        self._rows.append(lbl)

    def _add_row(self, setting: settings.Setting) -> None:
        row = tk.Frame(self._inner, bg=_BG)
        row.pack(fill="x", padx=20, pady=(8, 8))
        self._rows.append(row)

        left = tk.Frame(row, bg=_BG)
        left.pack(side="left", fill="x", expand=True)
        title = tk.Frame(left, bg=_BG)
        title.pack(fill="x", anchor="w")
        tk.Label(title, text=setting.label, bg=_BG, fg=_FG,
                 font=(UI_FONT, 10), anchor="w").pack(side="left")

        # Reset shows only when the value differs from its default, so the row
        # also answers "have I changed this?" at a glance. The label is always
        # created at a fixed width and blanked when unchanged — same trick as
        # the Welcome tab's marker gutter. Toggling text in place means a
        # change repaints one label instead of rebuilding the pane, and
        # nothing shifts sideways as it appears.
        reset = tk.Label(title, text="", bg=_BG, fg=_DIM, width=2,
                         font=(UI_FONT, 9))
        reset.pack(side="left", padx=(6, 0))
        reset.bind("<ButtonRelease-1>", lambda _e, k=setting.key: self._reset(k))
        reset.bind("<Enter>", lambda _e, w=reset: self._reset_hover(w, True))
        reset.bind("<Leave>", lambda _e, w=reset: self._reset_hover(w, False))
        _tooltip_text(reset, "Reset to default")
        self._reset_labels[setting.key] = reset
        self._sync_reset(setting.key)

        if setting.description:
            tk.Label(left, text=setting.description, bg=_BG, fg=_DIM,
                     font=(UI_FONT, 8), anchor="w", justify="left",
                     wraplength=380).pack(fill="x", anchor="w", pady=(1, 0))

        control, refresh = self._build_control(row, setting)
        if control is not None:
            control.pack(side="right", padx=(16, 0))
        if refresh is not None:
            self._refreshers[setting.key] = refresh

    def _sync_reset(self, key: str) -> None:
        lbl = self._reset_labels.get(key)
        if lbl is None:
            return
        changed = not settings.is_default(key)
        lbl.config(text="↺" if changed else "",
                   cursor="hand2" if changed else "")

    def _reset_hover(self, lbl: tk.Label, entering: bool) -> None:
        if not lbl.cget("text"):
            return                      # blank placeholder, nothing to hover
        lbl.config(fg=_FG if entering else _DIM)

    def _build_control(self, parent, setting: settings.Setting):
        """Return `(widget, refresh)`.

        `refresh` re-reads the store into the control, for when the value
        changes behind the widget's back — resetting to default is the case
        that matters.
        """
        kind = setting.kind
        value = settings.get(setting.key)

        if kind == "bool":
            var = tk.BooleanVar(value=bool(value))
            box = DarkCheckbox(
                parent, text="", variable=var, bg=_BG,
                command=lambda k=setting.key, v=var: self._write(k, bool(v.get())),
            )
            return box, lambda k=setting.key, v=var: v.set(bool(settings.get(k)))

        if kind == "choice":
            return self._choice_control(parent, setting, value)

        if kind == "font":
            return self._font_control(parent, setting, value)

        if kind == "color":
            return self._color_control(parent, setting, value)

        if kind == "int":
            return self._entry_control(parent, setting, value, numeric=True)

        return self._entry_control(parent, setting, value, numeric=False)

    def _choice_control(self, parent, setting, value):
        options = settings.choices_for(setting)
        var = tk.StringVar(value=str(value))
        btn = tk.Label(parent, textvariable=var, bg=_ITEM_BG, fg=_FG,
                       font=(UI_FONT, 9), padx=10, pady=4, cursor="hand2",
                       anchor="w", width=20)

        def popup(_event=None):
            menu = tk.Menu(btn, tearoff=0, bg=_ITEM_BG, fg=_FG,
                           activebackground=_SEL, activeforeground="#ffffff",
                           bd=0, font=(UI_FONT, 9))
            for option in options:
                menu.add_command(
                    label=option,
                    command=lambda o=option: (var.set(o),
                                              self._write(setting.key, o)),
                )
            menu.tk_popup(btn.winfo_rootx(),
                          btn.winfo_rooty() + btn.winfo_height())

        btn.bind("<ButtonRelease-1>", popup)
        btn.bind("<Enter>", lambda _e: btn.config(bg=_HOVER))
        btn.bind("<Leave>", lambda _e: btn.config(bg=_ITEM_BG))
        return btn, lambda: var.set(str(settings.get(setting.key)))

    def _font_control(self, parent, setting, value):
        def describe(raw):
            font = settings.get_editor_font() if raw else None
            if not font:
                return "Editor default"
            family, size, weight, slant = font
            bits = [b for b in (weight if weight != "normal" else "",
                                "italic" if slant == "italic" else "") if b]
            return f"{family}, {size}" + (f", {' '.join(bits)}" if bits else "")

        var = tk.StringVar(value=describe(value))
        btn = tk.Label(parent, textvariable=var, bg=_ITEM_BG, fg=_FG,
                       font=(UI_FONT, 9), padx=10, pady=4, cursor="hand2",
                       anchor="w", width=24)

        def choose(_event=None):
            current = settings.get_editor_font()
            family, size, weight, slant = current or ("Consolas", 11,
                                                      "normal", "roman")
            picked = askfont(self.winfo_toplevel(), family=family, size=size,
                             weight=weight, slant=slant,
                             title="Editor Font", show_effects=False,
                             text="AaBbYyZz 0123 (){}[]")
            if not picked:
                return
            self._write(setting.key, [picked["family"], picked["size"],
                                      picked["weight"], picked["slant"]])
            var.set(describe(True))

        btn.bind("<ButtonRelease-1>", choose)
        btn.bind("<Enter>", lambda _e: btn.config(bg=_HOVER))
        btn.bind("<Leave>", lambda _e: btn.config(bg=_ITEM_BG))
        return btn, lambda: var.set(describe(settings.get(setting.key)))

    def _color_control(self, parent, setting, value):
        holder = tk.Frame(parent, bg=_BG)
        swatch = tk.Canvas(holder, width=34, height=20, bg=value or "#000000",
                           highlightthickness=1, highlightbackground=_BORDER,
                           cursor="hand2")
        swatch.pack(side="left")
        text = tk.Label(holder, text=str(value or "unset"), bg=_BG, fg=_DIM,
                        font=(UI_FONT, 8), width=9)
        text.pack(side="left", padx=(8, 0))

        def choose(_event=None):
            _rgb, picked = askcolor(value or "#ffffff",
                                    parent=self.winfo_toplevel())
            if not picked:
                return
            swatch.configure(bg=picked)
            text.config(text=picked)
            self._write(setting.key, picked)

        swatch.bind("<ButtonRelease-1>", choose)

        def refresh():
            current = settings.get(setting.key)
            swatch.configure(bg=current or "#000000")
            text.config(text=str(current or "unset"))

        return holder, refresh

    def _entry_control(self, parent, setting, value, numeric: bool):
        var = tk.StringVar(value="" if value is None else str(value))
        wrap = tk.Frame(parent, bg=_BORDER, padx=1, pady=1)
        entry = tk.Entry(wrap, textvariable=var, bg=_ITEM_BG, fg=_FG,
                         insertbackground=_FG, relief="flat", bd=0,
                         font=(UI_FONT, 9), width=24 if not numeric else 8,
                         justify="center" if numeric else "left")
        entry.pack(ipady=3)

        def commit(_event=None):
            raw = var.get().strip()
            if numeric:
                try:
                    parsed = int(raw)
                except ValueError:
                    var.set(str(settings.get(setting.key)))
                    return
                lo, hi = setting.minimum, setting.maximum
                if lo is not None:
                    parsed = max(lo, parsed)
                if hi is not None:
                    parsed = min(hi, parsed)
                var.set(str(parsed))     # show the clamped value back
                self._write(setting.key, parsed)
            else:
                self._write(setting.key, raw)

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)

        def refresh():
            current = settings.get(setting.key)
            var.set("" if current is None else str(current))

        return wrap, refresh

    # ── Writes ────────────────────────────────────────────────────────────────

    def _write(self, key: str, value) -> None:
        """A value the user just set through its own control.

        Only the ↺ affordance needs updating — the control already shows what
        was picked. This used to re-render the whole pane, which visibly
        flickered every other row in the section (and every row in every
        section while searching).
        """
        settings.set(key, value)
        self._sync_reset(key)
        self._notify_dirty()

    def _reset(self, key: str) -> None:
        if settings.is_default(key):
            return                      # blank placeholder was clicked
        settings.reset(key)
        refresh = self._refreshers.get(key)
        if refresh is not None:
            refresh()                   # the value moved behind the control
        self._sync_reset(key)
        self._notify_dirty()

    def _notify_dirty(self) -> None:
        if self._on_dirty is not None:
            self._on_dirty()

    def _on_external_change(self, key: str, _value) -> None:
        """A setting changed — from this panel or from anywhere else."""
        if not self.winfo_exists():
            return
        refresh = self._refreshers.get(key)
        if refresh is not None:
            try:
                refresh()
            except tk.TclError:
                return                  # row was destroyed mid-callback
        self._sync_reset(key)

    def _on_destroy(self, event) -> None:
        # <Destroy> fires for every descendant; only the panel's own teardown
        # should drop the subscription.
        if event.widget is not self:
            return
        self._unsubscribe()

    def focus_search(self) -> None:
        self._search_entry.focus_set()


def _tooltip_text(widget, text: str) -> None:
    """Minimal hover tooltip — enough for an icon-only affordance."""
    state: dict = {"win": None, "after": None}

    def show():
        if state["win"] is not None:
            return
        win = tk.Toplevel(widget)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        tk.Label(win, text=text, bg="#1e1e1e", fg=_FG, font=(UI_FONT, 8),
                 padx=6, pady=3, highlightthickness=1,
                 highlightbackground=_BORDER).pack()
        win.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + 22}")
        state["win"] = win

    def enter(_e=None):
        state["after"] = widget.after(450, show)

    def leave(_e=None):
        if state["after"]:
            widget.after_cancel(state["after"])
            state["after"] = None
        if state["win"] is not None:
            state["win"].destroy()
            state["win"] = None

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", leave, add="+")
