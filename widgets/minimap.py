"""Minimap — peer text widget minimap with hover code preview."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .codeview import CodeView

WIDTH        = 90   # minimap width in pixels
PREVIEW_W    = 420  # hover preview width in pixels
PREVIEW_LINES = 14  # number of lines shown in the preview


def _lighten(hex_color: str, amount: int = 18) -> str:
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{min(255,r+amount):02x}{min(255,g+amount):02x}{min(255,b+amount):02x}"
    except Exception:
        return hex_color


class Minimap(tk.Frame):
    """Real-time minimap using a peer Text widget.

    The peer shares the B-tree with the main CodeView so all content and
    Token.* tag positions are mirrored automatically. A refresh loop keeps
    the peer scrolled so the currently visible region stays centred.
    Hovering shows a full-size syntax-highlighted preview to the left of
    the scrollbar. Click or drag to scroll the main editor.
    """

    def __init__(self, parent: tk.Widget, codeview: "CodeView") -> None:
        super().__init__(parent, width=WIDTH, bd=0, highlightthickness=0)
        self._cv = codeview
        self._bg = "#1e1e1e"

        # Thin separator between scrollbar and minimap
        self._border = tk.Frame(parent, width=1, bg="#404040")

        # ── Peer Text Widget ──────────────────────────────────────────────────
        self._peer = tk.Text(
            self,
            bd=0, highlightthickness=0,
            state="disabled", wrap="none",
            cursor="arrow", takefocus=False,
        )
        peer_path = self._peer._w

        try:
            self._peer.tk.call("destroy", peer_path)
            codeview.tk.call(
                codeview._orig, "peer", "create", peer_path,
                "-bd", 0,
                "-highlightthickness", 0,
                "-state", "disabled",
                "-wrap", "none",
                "-cursor", "arrow",
                "-takefocus", 0,
            )
        except Exception as e:
            print(f"[Minimap] peer creation failed: {e}")

        self._peer.place(x=0, y=0, relwidth=1, relheight=1)
        self._peer.bind("<ButtonPress-1>", self._on_press)
        self._peer.bind("<B1-Motion>",     self._on_drag)
        self._peer.bind("<Motion>",        self._on_hover)
        self._peer.bind("<Leave>",         self._on_leave)

        # ── Hover Preview ─────────────────────────────────────────────────────
        self._preview: tk.Toplevel | None = None
        self._preview_text: tk.Text | None = None
        self._preview_after: str | None = None
        self._last_preview_line: int = -1

        self._refresh_loop()

    # ── Grid helpers — border in col 3, minimap frame in col 4 ───────────────

    def grid(self, **kwargs) -> None:
        self._border.grid(row=0, column=3, sticky="ns")
        super().grid(row=0, column=4, sticky="ns", **kwargs)

    def grid_remove(self) -> None:
        self._border.grid_remove()
        super().grid_remove()
        self._hide_preview()

    # ── Public API ────────────────────────────────────────────────────────────

    def apply_colors(self, bg: str, fg: str) -> None:
        """Sync background and font with the active theme."""
        self._bg = bg
        self.configure(bg=bg)
        self._border.configure(bg=_lighten(bg))
        try:
            cv_font = self._cv.cget("font")
            face = cv_font.split()[0] if isinstance(cv_font, str) else cv_font[0]
        except Exception:
            face = "Fira Mono"
        try:
            self._peer.configure(
                bg=bg,
                fg=fg,
                font=(face, 1),
                insertbackground=bg,
                selectbackground=bg,
                selectforeground=fg,
            )
        except Exception:
            pass

    # ── Scroll tracking ───────────────────────────────────────────────────────

    def _refresh_loop(self) -> None:
        try:
            top_frac, bot_frac = self._cv.yview()
            mid      = (top_frac + bot_frac) / 2
            vp_span  = bot_frac - top_frac
            peer_top = max(0.0, min(1.0, mid - vp_span * 0.5))
            self._peer.yview_moveto(peer_top)
        except Exception:
            pass
        self.after(80, self._refresh_loop)

    # ── Hover preview ─────────────────────────────────────────────────────────

    def _on_hover(self, event) -> None:
        """Show a full-size code preview to the left of the scrollbar."""
        try:
            idx    = self._peer.index(f"@{event.x},{event.y}")
            lineno = int(idx.split(".")[0])
        except Exception:
            return

        # Skip rebuild if the center line hasn't moved — just reposition
        if lineno == self._last_preview_line and self._preview is not None:
            self._reposition_preview(event.y_root)
            return

        if self._preview_after:
            self.after_cancel(self._preview_after)
        # Very short delay so rapid movement stays fluid
        self._preview_after = self.after(16, lambda: self._show_preview(lineno, event.y_root))

    def _on_leave(self, event) -> None:
        # Small delay so moving into the preview window doesn't close it
        if self._preview_after:
            self.after_cancel(self._preview_after)
        self._preview_after = self.after(120, self._hide_preview)

    def _show_preview(self, center_line: int, mouse_y_root: int) -> None:
        cv = self._cv
        total = int(cv.index("end-1c").split(".")[0])

        half   = PREVIEW_LINES // 2
        first  = max(1, center_line - half)
        last   = min(total, first + PREVIEW_LINES - 1)
        first  = max(1, last - PREVIEW_LINES + 1)

        # ── Create or reuse Toplevel ──────────────────────────────────────────
        if self._preview is None:
            self._preview = tk.Toplevel(self)
            self._preview.overrideredirect(True)
            self._preview.attributes("-topmost", True)
            self._preview.configure(bg=self._bg)

            # Rounded-ish border via a 1px highlight frame
            outer = tk.Frame(
                self._preview,
                bg=_lighten(self._bg, 35),
                padx=1, pady=1,
            )
            outer.pack(fill="both", expand=True)

            self._preview_text = tk.Text(
                outer,
                bd=0, highlightthickness=0,
                state="disabled", wrap="none",
                takefocus=False,
                padx=8, pady=4,
            )
            self._preview_text.pack(fill="both", expand=True)

            self._preview_text.bind("<Enter>", lambda _: (
                self.after_cancel(self._preview_after)
                if self._preview_after else None
            ))
            self._preview_text.bind("<Leave>", lambda _: self._hide_preview())

        pt = self._preview_text

        # Apply editor colors and full-size font
        bg  = cv.cget("background")
        fg  = cv.cget("foreground")
        fnt = cv.cget("font")
        pt.configure(
            bg=bg, fg=fg, font=fnt,
            insertbackground=bg,
            selectbackground=cv.cget("selectbackground"),
        )
        self._preview.configure(bg=_lighten(bg, 35))

        # Copy token tag colours from the main editor
        for tag in cv.tag_names():
            if tag.startswith("Token"):
                try:
                    tfg = cv.tag_cget(tag, "foreground")
                    if tfg:
                        pt.tag_configure(tag, foreground=tfg)
                except Exception:
                    pass

        # Populate text and tags
        pt.configure(state="normal")
        pt.delete("1.0", "end")

        for ln in range(first, last + 1):
            line_text = cv.get(f"{ln}.0", f"{ln}.end")
            pt.insert("end", line_text)
            if ln < last:
                pt.insert("end", "\n")

        # Copy token tag ranges for the visible lines into the preview
        offset = first - 1  # line number offset: source line → preview line
        for tag in cv.tag_names():
            if not tag.startswith("Token"):
                continue
            ranges = cv.tag_ranges(tag)
            for i in range(0, len(ranges), 2):
                r_start = str(ranges[i])
                r_end   = str(ranges[i + 1])
                try:
                    sl, sc = r_start.split(".")
                    el, ec = r_end.split(".")
                    sl_i, el_i = int(sl), int(el)
                    if el_i < first or sl_i > last:
                        continue
                    # Clamp to preview range
                    pl_s = max(sl_i, first) - offset
                    pc_s = sc if sl_i >= first else "0"
                    pl_e = min(el_i, last) - offset
                    pc_e = ec if el_i <= last else "end"
                    pt.tag_add(tag, f"{pl_s}.{pc_s}", f"{pl_e}.{pc_e}")
                except Exception:
                    continue

        pt.configure(state="disabled", height=PREVIEW_LINES)

        # ── Position the preview ──────────────────────────────────────────────
        self._preview.update_idletasks()
        pw = max(PREVIEW_W, int(cv.winfo_width() * 0.75))
        ph = self._preview.winfo_reqheight()

        # X: just to the left of the minimap (which is right of the scrollbar)
        mm_x = self._peer.winfo_rootx()
        px   = mm_x - pw - 4

        # Y: centre on mouse, clamped to screen
        screen_h = self._preview.winfo_screenheight()
        py = max(0, min(mouse_y_root - ph // 2, screen_h - ph))

        self._last_preview_line = center_line
        self._preview.geometry(f"{pw}x{ph}+{px}+{py}")
        self._preview.deiconify()

    def _reposition_preview(self, mouse_y_root: int) -> None:
        """Move an already-visible preview vertically without rebuilding it."""
        if self._preview is None:
            return
        pw  = self._preview.winfo_width()
        ph  = self._preview.winfo_height()
        px  = self._peer.winfo_rootx() - pw - 4
        screen_h = self._preview.winfo_screenheight()
        py  = max(0, min(mouse_y_root - ph // 2, screen_h - ph))
        self._preview.geometry(f"{pw}x{ph}+{px}+{py}")

    def _hide_preview(self) -> None:
        if self._preview_after:
            self.after_cancel(self._preview_after)
            self._preview_after = None
        self._last_preview_line = -1
        if self._preview is not None:
            self._preview.withdraw()

    # ── Interaction ───────────────────────────────────────────────────────────

    def _on_press(self, event) -> None:
        self._hide_preview()
        self._scroll_to(event.y)

    def _on_drag(self, event) -> None:
        self._scroll_to(event.y)

    def _scroll_to(self, widget_y: int) -> None:
        try:
            h = self._peer.winfo_height()
            if h <= 0:
                return
            pt, pb = self._peer.yview()
            frac   = pt + (widget_y / h) * (pb - pt)
            self._cv.yview_moveto(max(0.0, min(1.0, frac)))
        except Exception:
            pass
