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

        self._drag_slot: int = 0
        self._drag_start_y: int = 0
        self._drag_start_sash: int = 0

        # ── Sections ──────────────────────────────────────────────────────────
        self._outline_hdr = self._make_header("OUTLINE",    self._toggle_outline)
        self.outline      = OutlinePanel(self, on_navigate=on_navigate)

        self._sash1 = self._make_sash()

        self._refs_hdr = self._make_header("REFERENCES", self._toggle_refs,
                                           closeable=True)
        self.references = ReferencesPanel(self, on_navigate=on_navigate)

        self._sash2 = self._make_sash()

        self._sc_hdr = self._make_header("SOURCE CONTROL", self._toggle_sc,
                                         closeable=True,
                                         on_close=self.hide_source_control)
        sc_cb = sc_callbacks or {}
        self.source_control = SourceControlPanel(
            self,
            on_stage=sc_cb.get("stage",                  lambda p: None),
            on_unstage=sc_cb.get("unstage",              lambda p: None),
            on_discard=sc_cb.get("discard",              lambda p: None),
            on_commit=sc_cb.get("commit",                lambda m: None),
            on_push=sc_cb.get("push",                    lambda: None),
            on_pull=sc_cb.get("pull",                    lambda: None),
            on_diff=sc_cb.get("diff",                    lambda p: None),
            on_create_gitignore=sc_cb.get("create_gitignore", None),
            gitignore_check_fn=sc_cb.get("gitignore_check",  None),
            repo_root_fn=sc_cb.get("repo_root",          None),
        )

        self._sash3 = self._make_sash()

        self._explorer_hdr = self._make_header("EXPLORER",  self._toggle_explorer)
        # Wrap callback so clicks from the tree don't reset the explorer root
        self.explorer      = FileExplorer(self, on_open_file=lambda p: on_file_open(p, update_explorer=False))

        self.bind("<Configure>", lambda _: self._relayout())

    # ── Public API ────────────────────────────────────────────────────────────

    def show_references(self, word: str, codeview) -> None:
        """Show and populate the references panel."""
        self.references.show(word, codeview)
        if not self._refs_visible:
            # Give refs half of outline's current height so space is shared evenly
            half = max(_MIN_BODY, self._sash1_y // 2)
            self._sash1_y = half
            self._sash2_y = half
        self._refs_visible   = True
        self._refs_collapsed = False
        self._refs_hdr._arrow.config(text="▾")
        self._relayout()

    def hide_references(self) -> None:
        if self._refs_visible:
            # Return refs' space back to outline
            self._sash1_y = max(_MIN_BODY, self._sash1_y + self._sash2_y)
            self._sash2_y = 0
        self._refs_visible = False
        self._relayout()

    def show_source_control(self) -> None:
        """Make the Source Control panel visible and expanded."""
        if not self._sc_visible:
            # Take half from whichever expanded panel is above sc (refs or outline)
            donor = 1 if self._refs_visible and not self._refs_collapsed else 0
            attr  = "_sash2_y" if donor == 1 else "_sash1_y"
            cur   = getattr(self, attr)
            half  = max(_MIN_BODY, cur // 2)
            setattr(self, attr, half)
            self._sash3_y = half
        self._sc_visible   = True
        self._sc_collapsed = False
        self._sc_hdr._arrow.config(text="▾")
        self._relayout()

    def hide_source_control(self) -> None:
        if self._sc_visible:
            # Return sc's space to its donor
            donor = 1 if self._refs_visible and not self._refs_collapsed else 0
            attr  = "_sash2_y" if donor == 1 else "_sash1_y"
            setattr(self, attr, max(_MIN_BODY, getattr(self, attr) + self._sash3_y))
            self._sash3_y = 0
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

    def _make_sash(self) -> Frame:
        sash = Frame(self, bg="#3c3c3c", cursor="sb_v_double_arrow",
                     height=_SASH_H)
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
    # _sash1_y / _sash2_y / _sash3_y store the *desired body height* of slots
    # 0 (outline), 1 (refs), 2 (sc) — NOT absolute y positions.
    # Sashes are re-bound in _relayout with the correct slot each time sections
    # change, so dragging always affects the right panel regardless of visibility.

    _SLOT_SASH = {0: "_sash1_y", 1: "_sash2_y", 2: "_sash3_y"}

    def _sash_press(self, event, slot: int) -> None:
        self._drag_slot    = slot
        self._drag_start_y = event.y_root
        attr = self._SLOT_SASH.get(slot)
        self._drag_start_sash = getattr(self, attr) if attr else 0

    def _sash_drag(self, event) -> None:
        delta = event.y_root - self._drag_start_y
        new_h = max(_MIN_BODY, self._drag_start_sash + delta)
        attr = self._SLOT_SASH.get(self._drag_slot)
        if attr:
            setattr(self, attr, new_h)
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

        # Build list of visible sections: (header, body, collapsed, slot_index)
        # slot_index: 0=outline, 1=refs, 2=sc, 3=explorer
        sections = [(self._outline_hdr, self.outline, self._outline_collapsed, 0)]
        if self._refs_visible:
            sections.append((self._refs_hdr, self.references, self._refs_collapsed, 1))
        if self._sc_visible:
            sections.append((self._sc_hdr, self.source_control, self._sc_collapsed, 2))
        sections.append((self._explorer_hdr, self.explorer, self._explorer_collapsed, 3))

        n = len(sections)
        n_sashes = n - 1
        free_h = max(0, h - H * n - S * n_sashes)

        # Expanded section slot indices
        expanded = [slot for _, _, c, slot in sections if not c]
        n_exp = len(expanded)

        # Initialize outline height on first layout only.
        # Refs and SC heights are set when those panels are shown/hidden.
        default_h = max(M, free_h // max(n_exp, 1))
        if self._sash1_y == 0:
            self._sash1_y = default_h

        desired = {
            0: max(M, self._sash1_y),
            1: max(M, self._sash2_y),
            2: max(M, self._sash3_y),
        }

        # Guarantee Explorer a minimum slice, then proportionally
        # squish the other panels into whatever is left.
        EXPLORER_MIN = 120  # px always reserved for explorer when expanded

        explorer_expanded = 3 in expanded
        if explorer_expanded:
            other_budget = max(0, free_h - EXPLORER_MIN)
        else:
            other_budget = free_h

        other_expanded = [s for s in expanded if s != 3]
        other_desired_total = sum(desired.get(s, default_h) for s in other_expanded)

        body_h: dict[int, int] = {}

        if other_expanded:
            if other_desired_total > other_budget:
                # Panels overflow — proportionally squish to fit budget
                for slot in other_expanded:
                    want = desired.get(slot, default_h)
                    ratio = want / other_desired_total
                    body_h[slot] = max(M, int(other_budget * ratio))
            elif not explorer_expanded:
                # Explorer is collapsed — scale panels up to fill all free space
                scale = other_budget / other_desired_total if other_desired_total else 1
                for slot in other_expanded:
                    want = desired.get(slot, default_h)
                    body_h[slot] = max(M, int(want * scale))
            else:
                # Explorer is expanded — panels get desired height; explorer gets the rest
                for slot in other_expanded:
                    body_h[slot] = desired.get(slot, default_h)

        if explorer_expanded:
            used_by_others = sum(body_h.get(s, 0) for s in other_expanded)
            body_h[3] = max(EXPLORER_MIN, free_h - used_by_others)

        # Hide everything, then re-place top-to-bottom
        for widget in (self.outline, self.references, self.source_control,
                       self.explorer, self._sash1, self._sash2, self._sash3):
            widget.place_forget()
        for hdr in (self._outline_hdr, self._refs_hdr, self._sc_hdr,
                    self._explorer_hdr):
            hdr.place_forget()

        sash_widgets = [self._sash1, self._sash2, self._sash3]
        y = 0
        sash_idx = 0
        for i, (hdr, body, collapsed, slot) in enumerate(sections):
            hdr.place(x=0, y=y, width=w, height=H)
            y += H
            if not collapsed:
                bh = body_h.get(slot, M)
                body.place(x=0, y=y, width=w, height=bh)
                y += bh
            if i < n - 1:
                sw = sash_widgets[sash_idx]
                # Re-bind with the slot of the section above this sash so
                # dragging always adjusts the correct panel's height.
                sw.bind("<Button-1>", lambda e, s=slot: self._sash_press(e, s))
                sw.place(x=0, y=y, width=w, height=S)
                y += S
                sash_idx += 1
