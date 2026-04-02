"""Sidebar — collapsible Outline + References + Explorer panels with draggable sashes."""
from __future__ import annotations

from tkinter import Frame, Label
from tkinter import ttk
from typing import Callable

from .outline import OutlinePanel
from .references import ReferencesPanel
from .explorer import FileExplorer


_HEADER_H = 28   # px height of each section header
_SASH_H   = 5    # px height of each drag sash
_MIN_BODY = 40   # minimum body height before collapsing stops


class Sidebar(ttk.Frame):
    """Left sidebar: Outline / References (closeable) / Explorer.

    Click a header to collapse/expand that section.
    Drag a sash to resize adjacent sections.
    """

    def __init__(
        self,
        parent,
        on_file_open: Callable[[str], None],
        on_navigate: Callable[[int], None],
    ) -> None:
        super().__init__(parent, style="Sidebar.TFrame")

        self._outline_collapsed   = False
        self._refs_visible        = False   # references hidden until triggered
        self._refs_collapsed      = False
        self._explorer_collapsed  = False

        # Sash positions (0 = unset, calculated on first layout)
        self._sash1_y: int = 0   # between outline and refs
        self._sash2_y: int = 0   # between refs/outline and explorer

        self._drag_sash: int = 0          # which sash is being dragged (1 or 2)
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

        self._explorer_hdr = self._make_header("EXPLORER",  self._toggle_explorer)
        self.explorer      = FileExplorer(self, on_open_file=on_file_open)

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

    def apply_theme(self, bg: str, fg: str, select_bg: str) -> None:
        self.outline.apply_theme(bg, fg, select_bg)
        self.references.apply_theme(bg, fg, select_bg)
        self.explorer.apply_theme(bg, fg, select_bg)
        for hdr in (self._outline_hdr, self._refs_hdr, self._explorer_hdr):
            hdr.config(bg=bg)
            for child in hdr.winfo_children():
                child.config(bg=bg, fg="#cccccc")
        for sash in (self._sash1, self._sash2):
            sash.config(bg="#3c3c3c")
        ttk.Style().configure("Sidebar.TFrame", background=bg)

    # ── Header / sash factories ───────────────────────────────────────────────

    def _make_header(self, title: str, command: Callable,
                     closeable: bool = False) -> Frame:
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
            close_lbl = Label(hdr, text="×", bg="#252526", fg="#858585",
                              font=("Segoe UI", 10, "bold"), cursor="hand2",
                              padx=6)
            close_lbl.pack(side="right")
            close_lbl.bind("<Enter>", lambda _: close_lbl.config(fg="#cccccc"))
            close_lbl.bind("<Leave>", lambda _: close_lbl.config(fg="#858585"))
            close_lbl.bind("<Button-1>", lambda _: self.hide_references())

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

    def _toggle_explorer(self) -> None:
        self._explorer_collapsed = not self._explorer_collapsed
        self._explorer_hdr._arrow.config(
            text="▸" if self._explorer_collapsed else "▾")
        self._relayout()

    # ── Sash drag ─────────────────────────────────────────────────────────────

    def _sash_press(self, event, which: int) -> None:
        self._drag_sash      = which
        self._drag_start_y   = event.y_root
        self._drag_start_sash = (self._sash1_y if which == 1 else self._sash2_y)

    def _sash_drag(self, event) -> None:
        delta = event.y_root - self._drag_start_y
        new_pos = self._drag_start_sash + delta
        if self._drag_sash == 1:
            self._sash1_y = new_pos
        else:
            self._sash2_y = new_pos
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

        oc = self._outline_collapsed
        rc = self._refs_collapsed
        ec = self._explorer_collapsed
        rv = self._refs_visible

        # Build list of visible sections: (header, body, collapsed)
        sections = [(self._outline_hdr, self.outline, oc)]
        if rv:
            sections.append((self._refs_hdr, self.references, rc))
        sections.append((self._explorer_hdr, self.explorer, ec))

        # Hide everything first
        for widget in (self.outline, self.references, self.explorer,
                       self._sash1, self._sash2):
            widget.place_forget()
        for hdr in (self._outline_hdr, self._refs_hdr, self._explorer_hdr):
            hdr.place_forget()

        n = len(sections)
        sash_widgets = [self._sash1, self._sash2]

        # Total space available for bodies (subtract all headers and sashes)
        n_sashes = n - 1
        free_h = h - H * n - S * n_sashes

        # Determine body heights using sash positions
        # _sash1_y is the y of the sash after section 0
        # _sash2_y is the y of the sash after section 1 (if refs visible)
        n_expanded = sum(1 for _, _, c in sections if not c)

        # Initialise sash positions if not set
        if self._sash1_y == 0:
            self._sash1_y = H + max(M, free_h // max(n_expanded, 1))
        if self._sash2_y == 0 and n == 3:
            self._sash2_y = self._sash1_y + S + H + max(M, free_h // max(n_expanded, 1))

        # Clamp sash 1
        s1_min = H + M
        if n == 3:
            s1_max = self._sash2_y - S - H - M
        else:
            s1_max = h - S - H - M
        self._sash1_y = max(s1_min, min(self._sash1_y, s1_max))

        # Clamp sash 2 (only when refs visible)
        if n == 3:
            s2_min = self._sash1_y + S + H + M
            s2_max = h - H - M
            self._sash2_y = max(s2_min, min(self._sash2_y, s2_max))

        # Calculate body heights from sash positions
        if n == 2:
            body0_h = self._sash1_y - H
            body1_h = h - self._sash1_y - S - H
        else:  # n == 3
            body0_h = self._sash1_y - H
            body1_h = self._sash2_y - self._sash1_y - S - H
            body2_h = h - self._sash2_y - S - H

        body_heights_list = []
        if n == 2:
            body_heights_list = [body0_h, body1_h]
        else:
            body_heights_list = [body0_h, body1_h, body2_h]

        # Place sections top-to-bottom
        y = 0

        for i, (hdr, body, collapsed) in enumerate(sections):
            hdr.place(x=0, y=y, width=w, height=H)
            y += H
            if not collapsed:
                bh = max(M, body_heights_list[i])
                body.place(x=0, y=y, width=w, height=bh)
                y += bh
            if i < n - 1 and i < len(sash_widgets):
                sash_widgets[i].place(x=0, y=y, width=w, height=S)
                y += S
