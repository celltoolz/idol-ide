"""Minimap for CanvasCodeView — embedded scaled-down code overview.

Extracted from canvas_codeview.py (P3 decomposition). `MinimapMixin` is
inherited by `CanvasCodeView`.

The minimap is a real `tk.Text` widget embedded in the canvas via `place()`.
Font size 1 gives the same crisp glyph rasterization IDOL's textbox minimap
(canvas_editor/minimap.py) gets — `create_text` on a canvas can't render below
~4-5px. Token tags are mirrored from the active theme so colors match.

Unlike the gutter, the minimap is NOT painted inline in render(): it owns
its own widget and render() simply calls `self._update_minimap()` once per
paint. The mixin constructs its own state in `_build_minimap` (called from
CanvasCodeView._build_ui), so no `_mm_*` attrs live in _init_state.

Cross-mixin dependencies (MRO must place MinimapMixin after these):
  * TokenizerMixin._tokenize   — syntax tags in the body + hover preview
  * FoldMixin._visual_row_count + the fold-marker regexes — fold-aware
    elision and scroll sync
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from .constants import _FONT_FAMILY, _FONT_SIZE, _MINIMAP_W
from .fold import _IDOL_BEGIN_RE, _IDOL_END_RE, _SECTION_MARKER

_MINIMAP_FONT_SIZE = 1
_PREVIEW_LINES     = 14   # rows shown in the hover zoom preview
_PREVIEW_W         = 420  # min width of the hover preview Toplevel


def _lighten(hex_color: str, amount: int = 18) -> str:
    """Brighten a `#rrggbb` color by *amount* per channel. Used for the
    1-px frame around the minimap hover preview Toplevel."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{min(255, r + amount):02x}{min(255, g + amount):02x}{min(255, b + amount):02x}"
    except Exception:
        return hex_color


class MinimapMixin:
    """Embedded minimap + hover preview, mixed into CanvasCodeView.

    Reads host state (`self.lines`, `self.folded`, `self.scroll_y`,
    `self._palette`, `self._token_style`, `self._theme_name`, `self.canvas`,
    `self._text_x`, `self._line_h`) and calls host/cross-mixin methods
    (`self.render`, `self._scroll`, `self._tokenize`, `self._visual_row_count`)."""

    def _build_minimap(self) -> None:
        """Create the embedded minimap Text widget + hover-preview state.
        Called once from `_build_ui`."""
        self._mm_text = tk.Text(
            self.canvas,
            bd=0, highlightthickness=0,
            state="disabled", wrap="none",
            cursor="arrow", takefocus=False,
            font=(_FONT_FAMILY, _MINIMAP_FONT_SIZE),
            padx=2, pady=0,
            spacing1=0, spacing2=0, spacing3=0,
        )
        # `place()` (not create_window) so the canvas's `delete("all")` in
        # render() can't unmap the widget. Track the last place args to
        # avoid redundant geometry calls on every render.
        self._mm_last_place: tuple[int, int, int, int] | None = None
        self._mm_lines_cache: list[str] = []
        self._mm_last_theme: str | None = None
        # Host-toggleable visibility (View → "Show Minimap"). Mirrors
        # the legacy CodeView.show_minimap / hide_minimap contract.
        self._mm_visible: bool = True

        # Hover preview Toplevel — lazily created in `_mm_show_preview`.
        self._mm_preview: tk.Toplevel | None = None
        self._mm_preview_text: tk.Text | None = None
        self._mm_preview_after: str | None = None
        self._mm_last_preview_line: int = -1

        # Elide tag — hides minimap lines that are folded in the editor.
        self._mm_text.tag_configure("mm_elide", elide=True)
        self._mm_last_folded: frozenset = frozenset()

        self._mm_text.bind("<ButtonPress-1>", self._on_mm_press)
        self._mm_text.bind("<B1-Motion>",     self._on_mm_drag)
        self._mm_text.bind("<Motion>",        self._on_mm_hover)
        self._mm_text.bind("<Leave>",         self._on_mm_leave)
        self._mm_text.bind("<MouseWheel>",    self._on_mm_wheel)
        self._mm_text.bind("<Button-4>",      self._on_mm_wheel)
        self._mm_text.bind("<Button-5>",      self._on_mm_wheel)

    def show_minimap(self) -> None:
        """Make the minimap visible. Idempotent."""
        if not self._mm_visible:
            self._mm_visible = True
            self.render()

    def hide_minimap(self) -> None:
        """Hide the minimap and reclaim its column. Idempotent."""
        if self._mm_visible:
            self._mm_visible = False
            self._mm_text.place_forget()
            self._mm_last_place = None
            self.render()

    def _update_minimap(self) -> None:
        """Reposition/resize the embedded widget, rebuild content if the
        buffer changed, refresh tag colors on theme switch, and sync the
        scroll position with the editor viewport. Called from `render`."""
        c = self.canvas
        cw, ch = c.winfo_width(), c.winfo_height()
        mm_x = cw - _MINIMAP_W
        # Hide when the user toggled it off, or when the canvas is too
        # narrow to host both editor + minimap.
        if not self._mm_visible or mm_x < self._text_x + 20 or ch < 2:
            if self._mm_last_place is not None:
                self._mm_text.place_forget()
                self._mm_last_place = None
            return
        cur = (mm_x, 0, _MINIMAP_W, ch)
        if cur != self._mm_last_place:
            self._mm_text.place(x=mm_x, y=0,
                                width=_MINIMAP_W, height=ch)
            self._mm_text.lift()  # ensure widget sits above canvas items
            self._mm_last_place = cur
        if self._mm_last_theme != self._theme_name:
            self._mm_apply_palette()
            self._mm_last_theme = self._theme_name
        # Cheap fast path: if buffer is unchanged, list-compare bails on
        # the first differing entry (or instantly when nothing changed).
        cur_folded = frozenset(self.folded)
        if self._mm_lines_cache != self.lines:
            self._mm_rebuild_content()
            self._mm_apply_folds(cur_folded)
        elif cur_folded != self._mm_last_folded:
            self._mm_apply_folds(cur_folded)
        self._mm_sync_scroll()

    def _mm_apply_palette(self) -> None:
        """Push the active palette + token colors onto the minimap widget."""
        p = self._palette
        bg = p.get("minimap_bg", p["bg"])
        self._mm_text.configure(
            bg=bg, fg=p["fg"],
            insertbackground=bg,
            selectbackground=bg, selectforeground=p["fg"],
        )
        for cat, (color, _italic) in self._token_style.items():
            self._mm_text.tag_configure(f"tok_{cat}", foreground=color)

    def _mm_rebuild_content(self) -> None:
        """Insert every line into the minimap with token tags applied.
        Called only when `self.lines` differs from the cached snapshot."""
        pt = self._mm_text
        pt.configure(state="normal")
        pt.delete("1.0", "end")
        total = len(self.lines)
        for i, line in enumerate(self.lines, start=1):
            col = 0
            for txt, cat in self._tokenize(line, i - 1):
                pt.insert("end", txt)
                if cat is not None:
                    pt.tag_add(f"tok_{cat}",
                               f"{i}.{col}", f"{i}.{col + len(txt)}")
                col += len(txt)
            if i < total:
                pt.insert("end", "\n")
        pt.configure(state="disabled")
        self._mm_lines_cache = list(self.lines)

    def _mm_apply_folds(self, cur_folded: frozenset) -> None:
        """Elide minimap lines that are hidden by the editor's fold state."""
        pt = self._mm_text
        pt.tag_remove("mm_elide", "1.0", "end")
        if cur_folded:
            skip = None
            for i, line in enumerate(self.lines):
                if skip is not None:
                    if skip == -1:
                        lnum = i + 1
                        pt.tag_add("mm_elide", f"{lnum}.0", f"{lnum + 1}.0")
                        if _IDOL_END_RE.match(line):
                            skip = None
                        continue
                    if skip <= -2:
                        si = -(skip + 2)
                        if line.strip():
                            ind = len(line) - len(line.lstrip())
                            if ind < si or (ind == si and _SECTION_MARKER.match(line)):
                                skip = None  # terminating line is not elided
                            else:
                                lnum = i + 1
                                pt.tag_add("mm_elide", f"{lnum}.0", f"{lnum + 1}.0")
                                continue
                        else:
                            lnum = i + 1
                            pt.tag_add("mm_elide", f"{lnum}.0", f"{lnum + 1}.0")
                            continue
                    else:
                        ind = len(line) - len(line.lstrip())
                        if line.strip() and ind <= skip:
                            skip = None
                        else:
                            lnum = i + 1
                            pt.tag_add("mm_elide", f"{lnum}.0", f"{lnum + 1}.0")
                            continue
                if i in cur_folded:
                    if _IDOL_BEGIN_RE.match(line):
                        skip = -1
                    elif _SECTION_MARKER.match(line):
                        skip = -(len(line) - len(line.lstrip()) + 2)
                    else:
                        skip = len(line) - len(line.lstrip())
        self._mm_last_folded = cur_folded

    def _mm_sync_scroll(self) -> None:
        """Move the minimap's yview so it tracks the editor scroll proportionally.

        The old approach used top_phys/n which clamped the minimap to its bottom
        while the editor still had rows to scroll — because yview_moveto(frac)
        positions frac of the document at the minimap TOP, so fracs above
        (1 - mm_visible_fraction) are silently clamped.

        Fix: normalise the editor's scroll position to 0→1 over its own scrollable
        range, then map that onto 0→mm_max_top so the minimap reaches its bottom
        exactly when the editor reaches its bottom.
        """
        if not self.lines:
            return
        try:
            total   = max(1, self._visual_row_count())
            visible = max(1, self.canvas.winfo_height() // self._line_h)

            editor_max_top = max(0.0, 1.0 - visible / total)
            if editor_max_top == 0.0:
                self._mm_text.yview_moveto(0.0)
                return

            editor_norm = max(0.0, min(1.0, (self.scroll_y / total) / editor_max_top))

            mm_top, mm_bot = self._mm_text.yview()
            mm_max_top = max(0.0, 1.0 - (mm_bot - mm_top))

            self._mm_text.yview_moveto(editor_norm * mm_max_top)
        except Exception:
            pass

    # ── Minimap interaction ───────────────────────────────────────────────────

    def _on_mm_press(self, event):
        # Focus the canvas so keyboard input still goes to the editor
        # after a minimap click.
        self.canvas.focus_set()
        self._mm_hide_preview()
        self._mm_scroll_to(event.y)
        return "break"

    def _on_mm_drag(self, event):
        self._mm_scroll_to(event.y)
        return "break"

    def _mm_scroll_to(self, widget_y: int) -> None:
        """Translate a y-coord inside the minimap into a main-editor
        scroll position, centering the clicked line in the viewport."""
        try:
            idx = self._mm_text.index(f"@0,{widget_y}")
            phys = max(0, min(len(self.lines) - 1, int(idx.split(".")[0]) - 1))
        except Exception:
            return
        # Convert physical line → visual row (account for folds).
        v = 0
        skip = None
        for i, line in enumerate(self.lines):
            if skip is not None:
                if skip == -1:
                    if _IDOL_END_RE.match(line):
                        skip = None
                    continue
                if skip <= -2:
                    si = -(skip + 2)
                    if line.strip():
                        ind = len(line) - len(line.lstrip())
                        if ind < si or (ind == si and _SECTION_MARKER.match(line)):
                            skip = None
                        else:
                            continue
                    else:
                        continue
                else:
                    ind = len(line) - len(line.lstrip())
                    if line.strip() and ind <= skip:
                        skip = None
                    else:
                        continue
            if i == phys:
                break
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
            v += 1
        h = self.canvas.winfo_height()
        v_rows = max(1, h // self._line_h)
        self.scroll_y = max(0, v - v_rows // 2)
        self.render()

    def _on_mm_wheel(self, event):
        if getattr(event, "num", 0) == 4:
            self._scroll(-3)
        elif getattr(event, "num", 0) == 5:
            self._scroll(+3)
        else:
            self._scroll(-3 if event.delta > 0 else +3)
        # Refresh preview so the centered line tracks the new scroll pos.
        if self._mm_preview is not None:
            self._mm_last_preview_line = -1
            try:
                idx = self._mm_text.index(f"@0,{event.y}")
                self._mm_show_preview(int(idx.split(".")[0]), event.y_root)
            except Exception:
                pass
        return "break"

    # ── Minimap hover zoom-box ────────────────────────────────────────────────

    def _on_mm_hover(self, event):
        try:
            idx = self._mm_text.index(f"@0,{event.y}")
            line = int(idx.split(".")[0])
        except Exception:
            return
        if line == self._mm_last_preview_line and self._mm_preview is not None:
            self._mm_reposition_preview(event.y_root)
            return
        if self._mm_preview_after:
            self.after_cancel(self._mm_preview_after)
        self._mm_preview_after = self.after(
            16, lambda ln=line, y=event.y_root: self._mm_show_preview(ln, y)
        )

    def _on_mm_leave(self, _event):
        if self._mm_preview_after:
            self.after_cancel(self._mm_preview_after)
        self._mm_preview_after = self.after(120, self._mm_hide_preview)

    def _mm_show_preview(self, center_line: int, mouse_y_root: int) -> None:
        n = len(self.lines)
        if n == 0:
            return
        half  = _PREVIEW_LINES // 2
        first = max(1, center_line - half)
        last  = min(n, first + _PREVIEW_LINES - 1)
        first = max(1, last - _PREVIEW_LINES + 1)

        if self._mm_preview is None:
            self._mm_preview = tk.Toplevel(self)
            self._mm_preview.overrideredirect(True)
            self._mm_preview.attributes("-topmost", True)
            self._mm_preview.withdraw()
            outer = tk.Frame(self._mm_preview, padx=1, pady=1)
            outer.pack(fill="both", expand=True)
            self._mm_preview_text = tk.Text(
                outer, bd=0, highlightthickness=0,
                state="disabled", wrap="none", takefocus=False,
                padx=8, pady=4,
                font=(_FONT_FAMILY, _FONT_SIZE),
            )
            self._mm_preview_text.pack(fill="both", expand=True)
            self._mm_preview_text.bind("<Enter>", lambda _e: (
                self.after_cancel(self._mm_preview_after)
                if self._mm_preview_after else None
            ))
            self._mm_preview_text.bind("<Leave>", lambda _e: self._mm_hide_preview())
            # Italic variant for comment-like tokens
            self._mm_preview_text_italic_font = tkfont.Font(
                family=_FONT_FAMILY, size=_FONT_SIZE, slant="italic"
            )

        pt = self._mm_preview_text
        p  = self._palette
        pt.configure(
            bg=p["bg"], fg=p["fg"],
            insertbackground=p["bg"],
            selectbackground=p["select_bg"],
        )
        # 1-px frame in a lighter shade of the editor bg
        outer = pt.master  # type: ignore[union-attr]
        outer.configure(bg=_lighten(p["bg"], 35))
        self._mm_preview.configure(bg=_lighten(p["bg"], 35))

        # Apply token tag colors + italic for the categories that want it
        for cat, (color, italic) in self._token_style.items():
            if italic:
                pt.tag_configure(f"tok_{cat}", foreground=color,
                                 font=self._mm_preview_text_italic_font)
            else:
                pt.tag_configure(f"tok_{cat}", foreground=color)

        pt.configure(state="normal", height=_PREVIEW_LINES)
        pt.delete("1.0", "end")
        for ln in range(first, last + 1):
            line = self.lines[ln - 1] if 0 <= ln - 1 < n else ""
            col = 0
            preview_row = ln - first + 1
            for txt, cat in self._tokenize(line, ln - 1):
                pt.insert("end", txt)
                if cat is not None:
                    pt.tag_add(f"tok_{cat}",
                               f"{preview_row}.{col}",
                               f"{preview_row}.{col + len(txt)}")
                col += len(txt)
            if ln < last:
                pt.insert("end", "\n")
        pt.configure(state="disabled")

        # Position to the LEFT of the minimap, vertically centered on mouse.
        cw = self.canvas.winfo_width()
        pw = max(_PREVIEW_W, int(cw * 0.75))
        ph = self._mm_preview.winfo_reqheight() or _PREVIEW_LINES * 16
        mm_x_root = self._mm_text.winfo_rootx()
        px = mm_x_root - pw - 9
        screen_h = self._mm_preview.winfo_screenheight()
        py = max(0, min(mouse_y_root - ph // 2, screen_h - ph))

        self._mm_last_preview_line = center_line
        self._mm_preview.geometry(f"{pw}x{ph}+{px}+{py}")
        self._mm_preview.deiconify()

    def _mm_reposition_preview(self, mouse_y_root: int) -> None:
        if self._mm_preview is None:
            return
        pw = self._mm_preview.winfo_width()
        ph = self._mm_preview.winfo_height()
        px = self._mm_text.winfo_rootx() - pw - 9
        screen_h = self._mm_preview.winfo_screenheight()
        py = max(0, min(mouse_y_root - ph // 2, screen_h - ph))
        self._mm_preview.geometry(f"{pw}x{ph}+{px}+{py}")

    def _mm_hide_preview(self) -> None:
        if self._mm_preview_after:
            self.after_cancel(self._mm_preview_after)
            self._mm_preview_after = None
        self._mm_last_preview_line = -1
        if self._mm_preview is not None:
            self._mm_preview.withdraw()
