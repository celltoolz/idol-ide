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
        on_file_move: Callable[[str, str], bool] | None = None,
        on_root_change: Callable[[str], None] | None = None,
        on_file_delete: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, style="Sidebar.TFrame")

        self._outline_collapsed   = False
        self._refs_visible        = False   # references hidden until triggered
        self._refs_collapsed      = False
        self._sc_visible          = False   # source control hidden until triggered
        self._sc_collapsed        = False
        self._explorer_collapsed  = False

        # Desired body heights per slot (0 = unset → calculated on first layout)
        # slot: 0=outline, 1=refs, 2=sc, 3=explorer
        self._sash1_y: int = 0
        self._sash2_y: int = 0
        self._sash3_y: int = 0
        self._sash4_y: int = 0   # explorer — was always implicit; now explicit

        # Drag state — two-panel swap model
        self._drag_slot_above: int = 0
        self._drag_slot_below: int = 3
        self._drag_start_y:    int = 0
        self._drag_start_above: int = 0
        self._drag_start_below: int = 0

        self._relaying_out: bool = False   # instance-level re-entrancy guard
        self._dragging:     bool = False
        self._ghost_sash:   Frame | None = None

        # ── Sections ──────────────────────────────────────────────────────────
        self._outline_hdr = self._make_header("OUTLINE",    self._toggle_outline)
        self.outline      = OutlinePanel(self, on_navigate=on_navigate)

        self._sash1 = self._make_sash(0, 1)

        self._refs_hdr = self._make_header("REFERENCES", self._toggle_refs,
                                           closeable=True)
        self.references = ReferencesPanel(self, on_navigate=on_navigate)

        self._sash2 = self._make_sash(1, 2)

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
            on_create_gitignore=sc_cb.get("create_gitignore",    None),
            on_add_to_gitignore=sc_cb.get("add_to_gitignore",    None),
            on_untrack_venv=sc_cb.get("untrack_venv",            None),
            gitignore_check_fn=sc_cb.get("gitignore_check",      None),
            repo_root_fn=sc_cb.get("repo_root",                  None),
            on_history_diff=sc_cb.get("history_diff",            None),
            on_expand_commit=sc_cb.get("expand_commit",          None),
        )

        self._sash3 = self._make_sash(2, 3)

        self._explorer_hdr = self._make_header("EXPLORER",  self._toggle_explorer)
        # Wrap callback so clicks from the tree don't reset the explorer root
        self.explorer      = FileExplorer(self,
                                          on_open_file=lambda p: on_file_open(p, update_explorer=False),
                                          on_file_move=on_file_move,
                                          on_root_change=on_root_change,
                                          on_file_delete=on_file_delete)

        self.bind("<Configure>", self._on_configure)

    # ── Public API ────────────────────────────────────────────────────────────

    def show_references(self, word: str, codeview) -> None:
        """Show and populate the references panel."""
        self.references.show(word, codeview)
        if not self._refs_visible:
            # Steal half from outline; give it to refs
            half = max(_MIN_BODY, self._get_h(0) // 2)
            self._set_h(0, half)
            self._set_h(1, half)
        self._refs_visible   = True
        self._refs_collapsed = False
        self._refs_hdr._arrow.config(text="▾")
        self._relayout()

    def hide_references(self) -> None:
        if self._refs_visible:
            # Return refs' space to outline
            self._set_h(0, self._get_h(0) + self._get_h(1))
            self._sash2_y = 0
        self._refs_visible = False
        self._relayout()

    def show_source_control(self) -> None:
        """Make the Source Control panel visible and expanded."""
        if not self._sc_visible:
            # Steal half from the biggest expanded panel above sc
            donor_slot = 1 if self._refs_visible and not self._refs_collapsed else 0
            cur  = self._get_h(donor_slot)
            half = max(_MIN_BODY, cur // 2)
            self._set_h(donor_slot, half)
            self._set_h(2, half)
        self._sc_visible   = True
        self._sc_collapsed = False
        self._sc_hdr._arrow.config(text="▾")
        self._relayout()

    def hide_source_control(self) -> None:
        if self._sc_visible:
            # Return sc's space to its donor
            donor_slot = 1 if self._refs_visible and not self._refs_collapsed else 0
            self._set_h(donor_slot, self._get_h(donor_slot) + self._get_h(2))
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

    def _make_sash(self, slot_above: int, slot_below: int) -> Frame:
        sash = Frame(self, bg="#3c3c3c", cursor="sb_v_double_arrow",
                     height=_SASH_H)
        sash.bind("<ButtonPress-1>",
                  lambda e, a=slot_above, b=slot_below: self._sash_press(e, a, b))
        sash.bind("<B1-Motion>",        self._sash_drag)
        sash.bind("<ButtonRelease-1>",  self._sash_release)
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

    # ── Sash helpers ──────────────────────────────────────────────────────────
    # Each slot stores its own desired height: 0=outline,1=refs,2=sc,3=explorer.
    # A sash drag is a *two-panel swap*: the panel above gains what the panel
    # below loses and vice-versa. No other panels are touched.

    _SLOT_ATTR = {0: "_sash1_y", 1: "_sash2_y", 2: "_sash3_y", 3: "_sash4_y"}

    def _get_h(self, slot: int) -> int:
        return getattr(self, self._SLOT_ATTR[slot], _MIN_BODY)

    def _set_h(self, slot: int, v: int) -> None:
        setattr(self, self._SLOT_ATTR[slot], max(_MIN_BODY, v))

    # ── Sash drag ─────────────────────────────────────────────────────────────

    def _sash_press(self, event, slot_above: int, slot_below: int) -> None:
        self._dragging         = True
        self._drag_slot_above  = slot_above
        self._drag_slot_below  = slot_below
        self._drag_start_y     = event.y_root
        self._drag_start_above = self._get_h(slot_above)
        self._drag_start_below = self._get_h(slot_below)
        event.widget.grab_set()
        # Show ghost drag line — position at the sash's current y in the sidebar
        if self._ghost_sash is None:
            self._ghost_sash = Frame(self, bg="#007acc", height=2)
        self._ghost_y0 = event.widget.winfo_y() + _SASH_H // 2
        self._ghost_sash.place(x=0, y=self._ghost_y0, relwidth=1.0, height=2)
        self._ghost_sash.lift()

    def _sash_release(self, event) -> None:
        if self._ghost_sash is not None:
            self._ghost_sash.place_forget()
        delta = event.y_root - self._drag_start_y
        self._dragging = False
        try:
            event.widget.grab_release()
        except Exception:
            pass
        new_above = max(_MIN_BODY, self._drag_start_above + delta)
        actual_delta = new_above - self._drag_start_above
        new_below = max(_MIN_BODY, self._drag_start_below - actual_delta)
        self._set_h(self._drag_slot_above, new_above)
        self._set_h(self._drag_slot_below, new_below)
        self._relayout()

    def _sash_drag(self, event) -> None:
        if not self._dragging or self._ghost_sash is None:
            return
        delta = event.y_root - self._drag_start_y
        ghost_y = max(0, min(self._ghost_y0 + delta, self.winfo_height() - 2))
        self._ghost_sash.place(x=0, y=int(ghost_y), relwidth=1.0, height=2)

    def _on_configure(self, event) -> None:
        # Only respond to the sidebar frame resizing (window resize), not
        # child-widget Configure events that bubble up via bindtag propagation.
        if event.widget is not self:
            return
        self._relayout()

    # ── Layout engine ─────────────────────────────────────────────────────────

    on_relayout: Callable | None = None   # set by app to reposition overlays

    def _relayout(self) -> None:
        if self._relaying_out:
            return
        self._relaying_out = True
        try:
            self._do_relayout()
        finally:
            self._relaying_out = False
        if self.on_relayout:
            self.after(50, self.on_relayout)

    def _do_relayout(self) -> None:
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        H = _HEADER_H
        S = _SASH_H
        M = _MIN_BODY

        # Build ordered list of visible sections
        sections = [(self._outline_hdr, self.outline, self._outline_collapsed, 0)]
        if self._refs_visible:
            sections.append((self._refs_hdr, self.references, self._refs_collapsed, 1))
        if self._sc_visible:
            sections.append((self._sc_hdr, self.source_control, self._sc_collapsed, 2))
        sections.append((self._explorer_hdr, self.explorer, self._explorer_collapsed, 3))

        n = len(sections)
        free_h = max(0, h - H * n - S * (n - 1))

        # Expanded slots in display order
        exp_slots = [slot for _, _, c, slot in sections if not c]
        n_exp = max(len(exp_slots), 1)
        default_h = max(M, free_h // n_exp)

        # Seed any unset heights evenly
        for slot in exp_slots:
            if self._get_h(slot) < M:
                self._set_h(slot, default_h)

        # Desired heights for expanded panels only
        desired = {slot: self._get_h(slot) for slot in exp_slots}
        total_desired = sum(desired.values())

        body_h: dict[int, int] = {}
        if not desired:
            pass
        elif total_desired > free_h:
            # Panels overflow — proportionally squish to fit
            for slot, want in desired.items():
                ratio = want / total_desired
                body_h[slot] = max(M, int(free_h * ratio))
        else:
            # Panels fit — assign desired heights, give leftover to last expanded panel
            body_h = dict(desired)

        # Ensure total fills free_h exactly (no empty gap at the bottom)
        if body_h and exp_slots:
            used = sum(body_h.values())
            leftover = free_h - used
            if leftover != 0:
                last = exp_slots[-1]
                body_h[last] = max(M, body_h[last] + leftover)

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
                # Pass both adjacent slots so drag is a true two-panel swap
                slot_below = sections[i + 1][3]
                sw = sash_widgets[sash_idx]
                sw.bind("<Button-1>",
                        lambda e, sa=slot, sb=slot_below: self._sash_press(e, sa, sb))
                sw.place(x=0, y=y, width=w, height=S)
                y += S
                sash_idx += 1
