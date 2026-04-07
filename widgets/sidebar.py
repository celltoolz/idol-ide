"""Sidebar — collapsible Outline + References + Explorer panels with draggable sashes."""
from __future__ import annotations

from tkinter import Frame, Label
from tkinter import ttk
from typing import Callable

from .outline import OutlinePanel
from .references import ReferencesPanel
from .explorer import FileExplorer
from .source_control import SourceControlPanel


_HEADER_H = 28   # px height of each section header
_SASH_H   = 5    # px height of each drag sash
_MIN_BODY = 40   # minimum body height before collapsing stops


class Sidebar(ttk.Frame):
    """Left sidebar: Outline / References (closeable) / Source Control (closeable) / Explorer.

    Click a header to collapse/expand that section.
    Drag a sash to resize adjacent sections.
    """

    def __init__(
        self,
        parent,
        on_file_open: Callable[[str], None],
        on_navigate: Callable[[int], None],
        sc_callbacks: dict | None = None,
    ) -> None:
        super().__init__(parent, style="Sidebar.TFrame")

        self._outline_collapsed   = False
        self._refs_visible        = False   # references hidden until triggered
        self._refs_collapsed      = False
        self._sc_visible          = False   # source control hidden until triggered
        self._sc_collapsed        = False
        self._explorer_collapsed  = False

        # Sash positions (0 = unset, calculated on first layout)
        self._sash1_y: int = 0   # outline body height
        self._sash2_y: int = 0   # refs body height
        self._sash3_y: int = 0   # source control body height

        self._drag_sash: int = 0
        self._drag_start_y: int = 0
        self._drag_start_sash: int = 0

        # ── Sections ──────────────────────────────────────────────────────────
        self._outline_hdr = self._make_header("OUTLINE",    self._toggle_outline)
        self.outline      = OutlinePanel(self, on_navigate=on_navigate)

        self._sash1 = self._make_sash(1)

        self._refs_hdr = self._make_header("REFERENCES", self._toggle_refs,
                                           closeable=True)
        self.references = ReferencesPanel(self, on_navigate=on_navigate)

        self._sash2 = self._make_sash(2)

        self._sc_hdr = self._make_header("SOURCE CONTROL", self._toggle_sc,
                                         closeable=True,
                                         on_close=self.hide_source_control)
        sc_cb = sc_callbacks or {}
        self.source_control = SourceControlPanel(
            self,
            on_stage=sc_cb.get("stage",              lambda p: None),
            on_unstage=sc_cb.get("unstage",          lambda p: None),
            on_discard=sc_cb.get("discard",          lambda p: None),
            on_commit=sc_cb.get("commit",            lambda m: None),
            on_push=sc_cb.get("push",                lambda: None),
            on_pull=sc_cb.get("pull",                lambda: None),
            on_diff=sc_cb.get("diff",                lambda p: None),
            on_create_gitignore=sc_cb.get("create_gitignore", None),
        )

        self._sash3 = self._make_sash(3)

        self._explorer_hdr = self._make_header("EXPLORER",  self._toggle_explorer)
        # Wrap callback so clicks from the tree don't reset the explorer root
        self.explorer      = FileExplorer(self, on_open_file=lambda p: on_file_open(p, update_explorer=False))

        self.bind("<Configure>", lambda _: self._relayout())

    # ── Public API ────────────────────────────────────────────────────────────

    def show_references(self, word: str, codeview) -> None:
        """Show and populate the references panel."""
        self.references.show(word, codeview)
        self._refs_visible   = True
        self._refs_collapsed = False
        self._refs_hdr._arrow.config(text="▾")
        self._relayout()

    def hide_references(self) -> None:
        self._refs_visible = False
        self._relayout()

    def show_source_control(self) -> None:
        """Make the Source Control panel visible and expanded."""
        self._sc_visible   = True
        self._sc_collapsed = False
        self._sc_hdr._arrow.config(text="▾")
        self._relayout()

    def hide_source_control(self) -> None:
        self._sc_visible = False
        self._relayout()

    def apply_theme(self, bg: str, fg: str, select_bg: str, codeview=None) -> None:
        self.outline.apply_theme(bg, fg, select_bg)
        # Pull accent + comment colors from the active theme's token tags
        accent = "#569cd6"
        comment = "#6a9955"
        if codeview is not None:
            try:
                accent  = codeview.tag_cget("Token.Name.Function", "foreground") or accent
                comment = codeview.tag_cget("Token.Comment.Single", "foreground") or comment
            except Exception:
                pass
        self.references.apply_theme(bg, fg, select_bg, accent=accent, comment=comment)
        self.source_control.apply_theme(bg, fg, select_bg)
        self.explorer.apply_theme(bg, fg, select_bg)
        for hdr in (self._outline_hdr, self._refs_hdr, self._sc_hdr, self._explorer_hdr):
            hdr.config(bg=bg)
            for child in hdr.winfo_children():
                child.config(bg=bg, fg="#cccccc")
        for sash in (self._sash1, self._sash2, self._sash3):
            sash.config(bg="#3c3c3c")
        ttk.Style().configure("Sidebar.TFrame", background=bg)

    # ── Header / sash factories ───────────────────────────────────────────────

    def _make_header(self, title: str, command: Callable,
                     closeable: bool = False,
                     on_close: Callable | None = None) -> Frame:
        hdr = Frame(self, bg="#252526", cursor="hand2", height=_HEADER_H)
        hdr.pack_propagate(False)

        arrow = Label(hdr, text="▾", bg="#252526", fg="#cccccc",
                      font=("Segoe UI", 9))
        arrow.pack(side="left", padx=(6, 0))
        hdr._arrow = arrow

        lbl = Label(hdr, text=title, bg="#252526", fg="#cccccc",
                    font=("Segoe UI", 9, "bold"), anchor="w")
        lbl.pack(side="left", fill="both", expand=True)

        if closeable:
            _close_fn = on_close if on_close else self.hide_references
            close_lbl = Label(hdr, text="×", bg="#252526", fg="#858585",
                              font=("Segoe UI", 10, "bold"), cursor="hand2",
                              padx=6)
            close_lbl.pack(side="right")
            close_lbl.bind("<Enter>", lambda _: close_lbl.config(fg="#cccccc"))
            close_lbl.bind("<Leave>", lambda _: close_lbl.config(fg="#858585"))
            close_lbl.bind("<Button-1>", lambda _: _close_fn())

        for widget in (hdr, arrow, lbl):
            widget.bind("<Button-1>", lambda _, c=command: c())

        return hdr

    def _make_sash(self, which: int) -> Frame:
        sash = Frame(self, bg="#3c3c3c", cursor="sb_v_double_arrow",
                     height=_SASH_H)
        sash.bind("<Button-1>",  lambda e, w=which: self._sash_press(e, w))
        sash.bind("<B1-Motion>", self._sash_drag)
        return sash

    # ── Collapse toggles ──────────────────────────────────────────────────────

    def _toggle_outline(self) -> None:
        self._outline_collapsed = not self._outline_collapsed
        self._outline_hdr._arrow.config(
            text="▸" if self._outline_collapsed else "▾")
        self._relayout()

    def _toggle_refs(self) -> None:
        self._refs_collapsed = not self._refs_collapsed
        self._refs_hdr._arrow.config(
            text="▸" if self._refs_collapsed else "▾")
        self._relayout()

    def _toggle_sc(self) -> None:
        self._sc_collapsed = not self._sc_collapsed
        self._sc_hdr._arrow.config(
            text="▸" if self._sc_collapsed else "▾")
        self._relayout()

    def _toggle_explorer(self) -> None:
        self._explorer_collapsed = not self._explorer_collapsed
        self._explorer_hdr._arrow.config(
            text="▸" if self._explorer_collapsed else "▾")
        self._relayout()

    # ── Sash drag ─────────────────────────────────────────────────────────────
    # _sash1_y / _sash2_y store the *desired body height* of section 0 (outline)
    # and section 1 (refs) respectively — NOT absolute y positions.
    # This means collapsing any section automatically gives its space to neighbors.

    def _sash_press(self, event, which: int) -> None:
        self._drag_sash    = which
        self._drag_start_y = event.y_root
        if which == 1:
            self._drag_start_sash = self._sash1_y
        elif which == 2:
            self._drag_start_sash = self._sash2_y
        else:
            self._drag_start_sash = self._sash3_y

    def _sash_drag(self, event) -> None:
        delta = event.y_root - self._drag_start_y
        new_h = max(_MIN_BODY, self._drag_start_sash + delta)
        if self._drag_sash == 1:
            self._sash1_y = new_h
        elif self._drag_sash == 2:
            self._sash2_y = new_h
        else:
            self._sash3_y = new_h
        self._relayout()

    # ── Layout engine ─────────────────────────────────────────────────────────

    def _relayout(self) -> None:
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        H = _HEADER_H
        S = _SASH_H
        M = _MIN_BODY
        EXPLORER_MIN = 120

        # Non-explorer sections (placed top-to-bottom)
        ne_sections = [(self._outline_hdr, self.outline, self._outline_collapsed, 0)]
        if self._refs_visible:
            ne_sections.append((self._refs_hdr, self.references, self._refs_collapsed, 1))
        if self._sc_visible:
            ne_sections.append((self._sc_hdr, self.source_control, self._sc_collapsed, 2))
        ne = len(ne_sections)

        # Fixed space: all ne headers + explorer header + one sash after each ne section
        # (the last sash separates the final ne section from the explorer body)
        fixed = H * (ne + 1) + S * ne
        free = max(0, h - fixed)

        # Budget for non-explorer bodies; explorer gets what's left (min EXPLORER_MIN)
        exp_expanded = not self._explorer_collapsed
        ne_budget = max(0, free - EXPLORER_MIN) if exp_expanded else free

        # Default / initialize sash positions
        ne_expanded_slots = [slot for _, _, c, slot in ne_sections if not c]
        default_h = max(M, ne_budget // max(len(ne_expanded_slots), 1))
        if self._sash1_y == 0:
            self._sash1_y = default_h
        if self._sash2_y == 0:
            self._sash2_y = default_h
        if self._sash3_y == 0:
            self._sash3_y = default_h

        desired = {
            0: max(M, self._sash1_y),
            1: max(M, self._sash2_y),
            2: max(M, self._sash3_y),
        }
        desired_total = sum(desired.get(s, default_h) for s in ne_expanded_slots)

        body_h: dict[int, int] = {}
        if ne_expanded_slots:
            if desired_total <= ne_budget:
                for slot in ne_expanded_slots:
                    body_h[slot] = desired.get(slot, default_h)
            else:
                for slot in ne_expanded_slots:
                    want = desired.get(slot, default_h)
                    ratio = want / desired_total if desired_total else 1
                    body_h[slot] = max(M, int(ne_budget * ratio))

        # Explorer body fills remaining space
        used_by_ne = sum(body_h.get(s, 0) for s in ne_expanded_slots)
        exp_body_h = max(EXPLORER_MIN, free - used_by_ne) if exp_expanded else 0

        # Hide everything
        for widget in (self.outline, self.references, self.source_control,
                       self.explorer, self._sash1, self._sash2, self._sash3):
            widget.place_forget()
        for hdr in (self._outline_hdr, self._refs_hdr, self._sc_hdr,
                    self._explorer_hdr):
            hdr.place_forget()

        # Place non-explorer sections top-to-bottom; sash after every ne section
        sash_widgets = [self._sash1, self._sash2, self._sash3]
        y = 0
        for i, (hdr, body, collapsed, slot) in enumerate(ne_sections):
            hdr.place(x=0, y=y, width=w, height=H)
            y += H
            if not collapsed:
                bh = body_h.get(slot, M)
                body.place(x=0, y=y, width=w, height=bh)
                y += bh
            sash_widgets[i].place(x=0, y=y, width=w, height=S)
            y += S

        # Explorer body fills from y to just above the pinned header
        if exp_expanded:
            self.explorer.place(x=0, y=y, width=w, height=exp_body_h)

        # Explorer header always pinned to the very bottom
        self._explorer_hdr.place(x=0, y=h - H, width=w, height=H)
