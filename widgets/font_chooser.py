"""IDOL's font chooser — replaces `tkfontchooser`.

Layout follows the native Windows font dialog, because that arrangement is what
everyone already knows: family list with a filter on the left, style in the
middle, size on the right, effects and a live preview underneath.

Font discovery is `tkinter.font.families()`. That is what `tkfontchooser` used
too, and it is the cross-platform answer — Tk asks the platform's own font
system, so the list is correct on Windows, X11 and macOS without special cases.

Two things the old dialog got wrong that this one is built around:

* **It opens on the current font.** Both IDOL call sites *tried* to pass one and
  neither worked — `askfont(master, title=..., font=init)` put the whole dict
  into `**font_args` under the key "font", where nothing read it, and the editor
  passed no font at all. Here the initial font is an explicit argument.
* **The preview cannot resize the dialog.** A 72pt sample renders inside a
  fixed box that scrolls, rather than pushing the window wider than the screen.

Effects (underline / strikeout) are opt-in via `show_effects`. They matter for
Designer widget fonts; the code editor has no use for them, so its caller leaves
them off rather than showing controls that do nothing.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from utils.ui_font import UI_FONT
from widgets.dark_checkbox import DarkCheckbox
from widgets.scrollbar import HorizontalScrollbar, VerticalScrollbar

# Palette lifted from project_wizard.py so the dialogs read as one product.
_BG      = "#252526"
_HDR_BG  = "#2d2d30"
_ITEM_BG = "#1e1e1e"
_FG      = "#cccccc"
_DIM     = "#858585"
_BTN_BG  = "#0e639c"
_BTN_ACT = "#1177bb"
_BORDER  = "#3c3c3c"
_SEL_BG  = "#094771"

_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72]

#: (label, weight, slant) — Tk exposes only these two axes.
_STYLES = [
    ("Regular",     "normal", "roman"),
    ("Italic",      "normal", "italic"),
    ("Bold",        "bold",   "roman"),
    ("Bold Italic", "bold",   "italic"),
]

_PREVIEW_W, _PREVIEW_H = 300, 96
_BAR = 12               # scrollbar thickness reserved in the preview box
_LIST_H = 9             # rows visible in each list


def _families() -> list[str]:
    """Installed families, de-duplicated and sorted, @-prefixed ones dropped.

    Windows lists vertical-writing variants of CJK fonts as "@Name"; they are
    the same family rotated and only confuse a picker.
    """
    seen = {f for f in tkfont.families() if f and not f.startswith("@")}
    return sorted(seen, key=str.lower)


class FontChooserDialog(tk.Toplevel):
    """Modal font picker. Prefer the module-level `askfont`."""

    def __init__(self, parent, family: str | None = None, size: int = 10,
                 weight: str = "normal", slant: str = "roman",
                 underline: bool = False, overstrike: bool = False,
                 title: str = "Choose Font", show_effects: bool = True,
                 preview_text: str = "AaBbYyZz 0123") -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: dict | None = None
        self._preview_text = preview_text
        self._all_families = _families()
        self._preview_font = tkfont.Font(family=family or "TkDefaultFont",
                                         size=size)

        self._family = family if family in self._all_families else (
            self._all_families[0] if self._all_families else "TkDefaultFont")
        self._size = int(size) if size else 10
        self._weight = weight if weight in ("normal", "bold") else "normal"
        self._slant = slant if slant in ("roman", "italic") else "roman"

        self._underline_var = tk.BooleanVar(value=bool(underline))
        self._overstrike_var = tk.BooleanVar(value=bool(overstrike))

        self._build(show_effects)
        self._sync_selection_to_state()
        self._refresh_preview()
        self._center(parent)
        self.bind("<Escape>", lambda _: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self, show_effects: bool) -> None:
        body = tk.Frame(self, bg=_BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        lists = tk.Frame(body, bg=_BG)
        lists.pack(side="top", fill="x")

        self._family_entry, self._family_list = self._labelled_list(
            lists, "Font:", width=24, on_type=self._on_family_typed)
        self._style_entry, self._style_list = self._labelled_list(
            lists, "Font style:", width=13, on_type=None)
        self._size_entry, self._size_list = self._labelled_list(
            lists, "Size:", width=6, on_type=self._on_size_typed)

        for name in self._all_families:
            self._family_list.insert("end", name)
        for label, _w, _s in _STYLES:
            self._style_list.insert("end", label)
        for value in _SIZES:
            self._size_list.insert("end", str(value))

        self._family_list.bind("<<ListboxSelect>>", self._on_family_pick)
        self._style_list.bind("<<ListboxSelect>>", self._on_style_pick)
        self._size_list.bind("<<ListboxSelect>>", self._on_size_pick)

        lower = tk.Frame(body, bg=_BG)
        lower.pack(side="top", fill="x", pady=(12, 0))

        if show_effects:
            fx = self._group(lower, "Effects",
                             side="left", fill="both", padx=(0, 12))
            DarkCheckbox(fx, text="Strikeout", variable=self._overstrike_var,
                         command=self._refresh_preview, bg=_HDR_BG).pack(
                anchor="w", pady=(2, 6))
            DarkCheckbox(fx, text="Underline", variable=self._underline_var,
                         command=self._refresh_preview, bg=_HDR_BG).pack(
                anchor="w")

        prev = self._group(lower, "Preview", side="left", fill="both",
                           expand=True)
        holder = tk.Frame(prev, bg=_BORDER, padx=1, pady=1)
        holder.pack(fill="both", expand=True)
        # Fixed box with propagation off. Without this the autohide scrollbars
        # add their own thickness to the frame's requested size the moment they
        # appear, and the whole dialog grows when the sample outgrows the box —
        # exactly what a fixed preview is supposed to prevent.
        grid = tk.Frame(holder, bg=_ITEM_BG,
                        width=_PREVIEW_W + _BAR, height=_PREVIEW_H + _BAR)
        grid.pack(fill="both", expand=True)
        grid.grid_propagate(False)
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_columnconfigure(0, weight=1)

        self._preview = tk.Canvas(grid, width=_PREVIEW_W, height=_PREVIEW_H,
                                  bg=_ITEM_BG, highlightthickness=0)
        self._preview.grid(row=0, column=0, sticky="nsew")
        # autohide needs grid — the bars appear only when the sample overflows,
        # which is the whole point of a fixed-size preview box.
        self._pv_v = VerticalScrollbar(grid, autohide=True, height=1,
                                       command=self._preview.yview)
        self._pv_v.grid(row=0, column=1, sticky="ns")
        self._pv_h = HorizontalScrollbar(grid, autohide=True, width=1,
                                         command=self._preview.xview)
        self._pv_h.grid(row=1, column=0, sticky="ew")
        self._preview.configure(yscrollcommand=self._pv_v.set,
                                xscrollcommand=self._pv_h.set)

        btns = tk.Frame(self, bg=_BG)
        btns.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        self._button(btns, "OK", self._ok, primary=True).pack(side="right")
        self._button(btns, "Cancel", self._cancel).pack(side="right", padx=(0, 8))

    def _labelled_list(self, parent, label: str, width: int, on_type):
        """A column: caption, entry, then a bordered listbox with a scrollbar."""
        col = tk.Frame(parent, bg=_BG)
        col.pack(side="left", fill="y", padx=(0, 12))
        tk.Label(col, text=label, bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8)).pack(anchor="w")

        ent_wrap = tk.Frame(col, bg=_BORDER, padx=1, pady=1)
        ent_wrap.pack(fill="x", pady=(2, 4))
        entry = tk.Entry(ent_wrap, bg=_ITEM_BG, fg=_FG, insertbackground=_FG,
                         relief="flat", font=(UI_FONT, 9), width=width, bd=0)
        entry.pack(fill="x", ipady=3)
        if on_type is not None:
            entry.bind("<KeyRelease>", on_type)

        wrap = tk.Frame(col, bg=_BORDER, padx=1, pady=1)
        wrap.pack(fill="both", expand=True)
        inner = tk.Frame(wrap, bg=_ITEM_BG)
        inner.pack(fill="both", expand=True)
        bar = VerticalScrollbar(inner, height=1)
        bar.pack(side="right", fill="y")
        lst = tk.Listbox(inner, bg=_ITEM_BG, fg=_FG, selectbackground=_SEL_BG,
                         selectforeground="#ffffff", font=(UI_FONT, 9),
                         relief="flat", bd=0, highlightthickness=0,
                         activestyle="none", exportselection=False,
                         width=width, height=_LIST_H,
                         yscrollcommand=bar.set)
        lst.pack(side="left", fill="both", expand=True)
        bar.configure(command=lst.yview)
        return entry, lst

    @staticmethod
    def _group(parent, title: str, **pack_kw) -> tk.Frame:
        """A titled panel, echoing the reference dialog's grouped sections.

        Packs the caption+box itself and returns the padded interior, so
        callers get one frame to fill and never juggle an outer/inner pair.
        """
        outer = tk.Frame(parent, bg=_BG)
        outer.pack(**pack_kw)
        tk.Label(outer, text=f"{title}:", bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8)).pack(anchor="w")
        inner = tk.Frame(outer, bg=_HDR_BG, padx=10, pady=8)
        inner.pack(fill="both", expand=True, pady=(2, 0))
        return inner

    @staticmethod
    def _button(parent, text: str, command, primary: bool = False) -> tk.Label:
        bg = _BTN_BG if primary else "#3c3c3c"
        act = _BTN_ACT if primary else "#4a4a4a"
        lbl = tk.Label(parent, text=text, bg=bg, fg="#ffffff",
                       font=(UI_FONT, 9), padx=18, pady=5, cursor="hand2")
        lbl.bind("<ButtonRelease-1>", lambda _: command())
        lbl.bind("<Enter>", lambda _: lbl.config(bg=act))
        lbl.bind("<Leave>", lambda _: lbl.config(bg=bg))
        return lbl

    def _center(self, parent) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px = py = 0
            pw, ph = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{px + max((pw - w) // 2, 0)}+{py + max((ph - h) // 3, 0)}")

    # ── State <-> widgets ─────────────────────────────────────────────────────

    def _style_label(self) -> str:
        for label, w, s in _STYLES:
            if w == self._weight and s == self._slant:
                return label
        return "Regular"

    def _sync_selection_to_state(self) -> None:
        """Select and scroll each list to the current font — the requirement
        the old dialog silently failed."""
        self._select_in(self._family_list, self._family)
        self._select_in(self._style_list, self._style_label())
        self._select_in(self._size_list, str(self._size))
        for entry, value in ((self._family_entry, self._family),
                             (self._style_entry, self._style_label()),
                             (self._size_entry, str(self._size))):
            entry.delete(0, "end")
            entry.insert(0, value)

    @staticmethod
    def _select_in(listbox: tk.Listbox, value: str) -> None:
        items = listbox.get(0, "end")
        if value not in items:
            return
        idx = items.index(value)
        listbox.selection_clear(0, "end")
        listbox.selection_set(idx)
        listbox.see(idx)

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_family_typed(self, event=None) -> None:
        # Enter/arrows must not re-filter: a KeyRelease for Return arrives after
        # the handler that acted on it and would wipe the list out from under
        # the selection.
        if event is not None and event.keysym in (
                "Return", "KP_Enter", "Up", "Down", "Escape"):
            return
        needle = self._family_entry.get().strip().lower()
        self._family_list.delete(0, "end")
        for name in self._all_families:
            if not needle or needle in name.lower():
                self._family_list.insert("end", name)
        if self._family_list.size():
            first = self._family_list.get(0)
            self._family_list.selection_set(0)
            self._family = first
            self._refresh_preview()

    def _on_family_pick(self, _event=None) -> None:
        sel = self._family_list.curselection()
        if not sel:
            return
        self._family = self._family_list.get(sel[0])
        self._family_entry.delete(0, "end")
        self._family_entry.insert(0, self._family)
        self._refresh_preview()

    def _on_style_pick(self, _event=None) -> None:
        sel = self._style_list.curselection()
        if not sel:
            return
        label = self._style_list.get(sel[0])
        for name, weight, slant in _STYLES:
            if name == label:
                self._weight, self._slant = weight, slant
                break
        self._style_entry.delete(0, "end")
        self._style_entry.insert(0, label)
        self._refresh_preview()

    def _on_size_typed(self, event=None) -> None:
        if event is not None and event.keysym in (
                "Return", "KP_Enter", "Up", "Down", "Escape"):
            return
        raw = self._size_entry.get().strip()
        try:
            value = int(raw)
        except ValueError:
            return                   # mid-typing; leave the last good size
        if 1 <= value <= 400:        # Tk renders absurd sizes very slowly
            self._size = value
            self._select_in(self._size_list, str(value))
            self._refresh_preview()

    def _on_size_pick(self, _event=None) -> None:
        sel = self._size_list.curselection()
        if not sel:
            return
        self._size = int(self._size_list.get(sel[0]))
        self._size_entry.delete(0, "end")
        self._size_entry.insert(0, str(self._size))
        self._refresh_preview()

    # ── Preview ───────────────────────────────────────────────────────────────

    def _refresh_preview(self) -> None:
        self._preview_font.configure(
            family=self._family, size=self._size, weight=self._weight,
            slant=self._slant, underline=bool(self._underline_var.get()),
            overstrike=bool(self._overstrike_var.get()),
        )
        c = self._preview
        c.delete("all")
        c.create_text(6, 4, text=self._preview_text, anchor="nw",
                      fill=_FG, font=self._preview_font)
        # Scrollregion from the drawn extent, so an oversized sample scrolls
        # inside the fixed box instead of the box growing to fit it.
        bbox = c.bbox("all") or (0, 0, 0, 0)
        c.configure(scrollregion=(0, 0, max(bbox[2] + 6, _PREVIEW_W),
                                  max(bbox[3] + 4, _PREVIEW_H)))

    # ── Result ────────────────────────────────────────────────────────────────

    def _ok(self) -> None:
        self.result = {
            "family": self._family,
            "size": self._size,
            "weight": self._weight,
            "slant": self._slant,
            "underline": bool(self._underline_var.get()),
            "overstrike": bool(self._overstrike_var.get()),
        }
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.grab_release()
        self.destroy()


def askfont(parent=None, family: str | None = None, size: int = 10,
            weight: str = "normal", slant: str = "roman",
            underline: bool = False, overstrike: bool = False,
            title: str = "Choose Font", show_effects: bool = True,
            text: str = "AaBbYyZz 0123", **_ignored) -> dict | None:
    """Open the font chooser; return the chosen font dict, or None on cancel.

    The result keys match what `tkfontchooser.askfont` returned — family, size,
    weight, slant, underline, overstrike — so existing call sites only change
    their import. Unlike that function, the initial font is a real argument
    rather than something swallowed by `**kwargs`.
    """
    if parent is None:
        raise ValueError("askfont requires a parent window")
    dlg = FontChooserDialog(
        parent, family=family, size=size, weight=weight, slant=slant,
        underline=underline, overstrike=overstrike, title=title,
        show_effects=show_effects, preview_text=text,
    )
    return dlg.result
