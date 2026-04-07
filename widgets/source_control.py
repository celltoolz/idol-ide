"""SourceControlPanel — Git Stage/Unstage/Commit/Push/Pull sidebar panel."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import Frame, Label, Menu, ttk
from typing import Callable

from utils.git_diagnostics import (
    classify_file, analyze_files, health_checks, FileInfo, Issue, HealthCheck
)
from widgets.guide_window import GuideWindow, GuidePage


_BG       = "#252526"
_ITEM_BG  = "#1e1e1e"
_HOV_BG   = "#2a2d2e"
_HDR_BG   = "#2d2d30"
_FG       = "#cccccc"
_DIM      = "#858585"
_BTN_BG   = "#0e639c"
_BTN_ACT  = "#1177bb"

STATUS_COLORS = {
    "M": "#e2c08d",
    "A": "#73c991",
    "U": "#cccccc",
    "D": "#f14c4c",
}
STATUS_LABELS = {"M": "M", "A": "A", "U": "U", "D": "D"}


class _Tooltip:
    """Simple hover tooltip."""
    def __init__(self, widget, text: str) -> None:
        self._tip = None
        widget.bind("<Enter>", lambda e: self._show(e, text))
        widget.bind("<Leave>", lambda _: self._hide())

    def _show(self, event, text: str) -> None:
        self._hide()
        x = event.widget.winfo_rootx() + event.widget.winfo_width() + 4
        y = event.widget.winfo_rooty()
        self._tip = tk.Toplevel()
        self._tip.overrideredirect(True)
        self._tip.attributes("-topmost", True)
        bg = "#1e1e1e"
        frame = Frame(self._tip, bg="#555555", padx=1, pady=1)
        frame.pack()
        Label(frame, text=text, bg=bg, fg="#cccccc",
              font=("Segoe UI", 8), justify="left",
              wraplength=220, padx=8, pady=5).pack()
        self._tip.geometry(f"+{x}+{y}")

    def _hide(self) -> None:
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


class _FileRow(Frame):
    """A single file entry row with hover highlight."""

    def __init__(self, parent, path: str, status: str,
                 on_click: Callable, on_right_click: Callable,
                 bg: str = _ITEM_BG) -> None:
        super().__init__(parent, bg=bg, cursor="hand2")
        self._bg = bg
        color = STATUS_COLORS.get(status, _FG)
        name = os.path.basename(path)

        lbl = Label(self, text=f"  {name}", bg=bg, fg=color,
                    font=("Segoe UI", 9), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        Label(self, text=f" {status} ", bg=bg, fg=color,
              font=("Segoe UI", 9, "bold")).pack(side="right", padx=(0, 4))

        for w in (self, lbl):
            w.bind("<Enter>",           lambda _: self._hover(True))
            w.bind("<Leave>",           lambda _: self._hover(False))
            w.bind("<Double-Button-1>", lambda _, p=path: on_click(p))
            w.bind("<Button-3>",        lambda e, p=path: on_right_click(e, p))

        # Hover tooltip: file classification + explanation (on row only)
        info = classify_file(path)
        _Tooltip(self, f"{info.label}\n{info.explanation}")

    def _hover(self, on: bool) -> None:
        c = _HOV_BG if on else self._bg
        self.config(bg=c)
        for w in self.winfo_children():
            w.config(bg=c)


class _Section(Frame):
    """Collapsible section header + virtually-rendered scrollable file list.

    Only the rows visible in the canvas viewport (plus a small buffer) are
    created as widgets. Rows outside the viewport are destroyed. This keeps
    memory and render time constant regardless of list size.
    """

    _ROW_H  = 22   # fixed px height per row
    _BUFFER = 4    # extra rows to keep alive above/below the visible area

    def __init__(self, parent, title: str, bg: str = _BG,
                 on_toggle: Callable | None = None) -> None:
        super().__init__(parent, bg=bg)
        self._collapsed    = False
        self._bg           = bg
        self._on_toggle    = on_toggle
        self._panel_menu_cb = None   # set by bind_panel_menu

        # Data store
        self._items: list[tuple[str, str]] = []
        self._on_click      = None
        self._on_right_click_file = None

        # Currently rendered rows: index → (canvas_window_id, _FileRow widget)
        self._rendered: dict[int, tuple[int, Frame]] = {}
        self._canvas_w: int = 1

        # ── Header ───────────────────────────────────────────────────────────
        hdr = Frame(self, bg=_HDR_BG, height=24)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self._arrow = Label(hdr, text="▾", bg=_HDR_BG, fg=_FG,
                            font=("Segoe UI", 8))
        self._arrow.pack(side="left", padx=(4, 0))

        Label(hdr, text=title, bg=_HDR_BG, fg=_FG,
              font=("Segoe UI", 8, "bold"), anchor="w").pack(
                  side="left", fill="x", expand=True)

        self._count_lbl = Label(hdr, text="", bg=_HDR_BG, fg=_DIM,
                                font=("Segoe UI", 8), padx=6)
        self._count_lbl.pack(side="right")

        for w in hdr.winfo_children():
            w.bind("<Button-1>", lambda _: self._toggle())
        hdr.bind("<Button-1>", lambda _: self._toggle())

        # ── Scrollable canvas ─────────────────────────────────────────────────
        self._scroll_frame = Frame(self, bg=_ITEM_BG)

        self._canvas = tk.Canvas(self._scroll_frame, bg=_ITEM_BG,
                                 highlightthickness=0, bd=0, height=1)
        self._vs = ttk.Scrollbar(self._scroll_frame, orient="vertical",
                                 command=self._scroll_to)
        self._canvas.configure(yscrollcommand=self._vs.set)
        self._canvas.pack(side="left", fill="both", expand=True)

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        for w in (self._canvas, self._scroll_frame):
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>",   self._on_wheel)
            w.bind("<Button-5>",   self._on_wheel)

    # ── Scroll plumbing ───────────────────────────────────────────────────────

    def _scroll_to(self, *args) -> None:
        self._canvas.yview(*args)
        self._render_visible()

    def _on_wheel(self, event) -> None:
        if event.num == 4 or event.delta > 0:
            self._canvas.yview_scroll(-1, "units")
        else:
            self._canvas.yview_scroll(1, "units")
        self._render_visible()

    def _on_canvas_configure(self, event) -> None:
        self._canvas_w = event.width
        # Update width of every already-rendered window
        for wid, _ in self._rendered.values():
            self._canvas.itemconfigure(wid, width=self._canvas_w)
        self._update_scrollbar()
        self._render_visible()

    def _update_scrollbar(self) -> None:
        total_h  = len(self._items) * self._ROW_H
        canvas_h = self._canvas.winfo_height()
        if total_h > canvas_h:
            self._vs.pack(side="right", fill="y")
        else:
            self._vs.pack_forget()

    # ── Virtual render ────────────────────────────────────────────────────────

    def _render_visible(self) -> None:
        if not self._items:
            return
        canvas_h = self._canvas.winfo_height()
        if canvas_h <= 1:
            return

        top = self._canvas.canvasy(0)
        bot = self._canvas.canvasy(canvas_h)

        first = max(0, int(top // self._ROW_H) - self._BUFFER)
        last  = min(len(self._items) - 1,
                    int(bot // self._ROW_H) + self._BUFFER)

        # Destroy rows that have scrolled out of range
        stale = [i for i in self._rendered if i < first or i > last]
        for i in stale:
            wid, widget = self._rendered.pop(i)
            self._canvas.delete(wid)
            widget.destroy()

        # Create rows that are now in range
        for i in range(first, last + 1):
            if i in self._rendered:
                continue
            path, status = self._items[i]
            row = _FileRow(self._canvas, path, status,
                           self._on_click, self._on_right_click_file,
                           bg=_ITEM_BG)
            wid = self._canvas.create_window(
                0, i * self._ROW_H,
                window=row, anchor="nw", width=self._canvas_w,
            )
            self._rendered[i] = (wid, row)
            # File rows get their own right-click; wheel forwarded to canvas
            for w in (row,) + tuple(row.winfo_children()):
                w.bind("<MouseWheel>", self._on_wheel)
                w.bind("<Button-4>",   self._on_wheel)
                w.bind("<Button-5>",   self._on_wheel)

    # ── Public API ────────────────────────────────────────────────────────────

    def populate(self, items: dict[str, str],
                 on_click: Callable, on_right_click: Callable,
                 panel_menu_cb: Callable | None = None) -> None:
        # Clear existing rendered rows
        for wid, widget in self._rendered.values():
            self._canvas.delete(wid)
            widget.destroy()
        self._rendered.clear()

        self._items               = list(items.items())
        self._on_click            = on_click
        self._on_right_click_file = on_right_click
        if panel_menu_cb:
            self._panel_menu_cb = panel_menu_cb

        total_h = len(self._items) * self._ROW_H
        self._canvas.configure(scrollregion=(0, 0, self._canvas_w, total_h))
        self._canvas.yview_moveto(0)

        self.set_count(len(self._items))
        self._update_scrollbar()
        self._render_visible()
        if not self._collapsed:
            self._repack()

    def set_count(self, n: int) -> None:
        self._count_lbl.config(text=f"({n})" if n else "")

    def bind_panel_menu(self, callback) -> None:
        self._panel_menu_cb = callback
        for w in (self, self._scroll_frame, self._canvas):
            w.bind("<Button-3>", callback)
        # Apply to already-rendered rows
        for _, widget in self._rendered.values():
            for w in (widget,) + tuple(widget.winfo_children()):
                w.bind("<Button-3>", callback)

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._arrow.config(text="▸" if self._collapsed else "▾")
        self._repack()
        if self._on_toggle:
            self._on_toggle()

    def _repack(self) -> None:
        self._scroll_frame.pack_forget()
        if not self._collapsed:
            self._scroll_frame.pack(fill="both", expand=True)
            self.after(10, self._render_visible)

    def apply_theme(self, bg: str, fg: str) -> None:
        self._bg = bg
        self.config(bg=bg)
        self._scroll_frame.config(bg=bg)
        self._canvas.config(bg=bg)


class SourceControlPanel(ttk.Frame):
    """Git source control panel: staged / unstaged file lists + commit UI."""

    _GITIGNORE_WARN_THRESHOLD = 50

    def __init__(
        self,
        parent,
        on_stage:             Callable[[str], None],
        on_unstage:           Callable[[str], None],
        on_discard:           Callable[[str], None],
        on_commit:            Callable[[str], None],
        on_push:              Callable[[], None],
        on_pull:              Callable[[], None],
        on_diff:              Callable[[str], None],
        on_create_gitignore:  Callable[[], None] | None = None,
        gitignore_check_fn:   Callable[[], bool] | None = None,
        repo_root_fn:         Callable[[], str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_stage            = on_stage
        self._on_unstage          = on_unstage
        self._on_discard          = on_discard
        self._on_commit           = on_commit
        self._on_push             = on_push
        self._on_pull             = on_pull
        self._on_diff             = on_diff
        self._on_create_gitignore = on_create_gitignore
        self._gitignore_check_fn  = gitignore_check_fn
        self._repo_root_fn        = repo_root_fn
        self._ctx_path            = ""
        self._warn_visible        = False
        self._last_staged:  dict[str, str] = {}
        self._last_unstaged: dict[str, str] = {}

        ttk.Style().configure("SC.TFrame", background=_BG)
        self.configure(style="SC.TFrame")

        self._build_commit_area()
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        self._build_health_panel()

        # Smart warning banner — shown when issues detected
        self._warn_frame = Frame(self, bg="#3c2a00", cursor="hand2")
        self._warn_lbl = Label(self._warn_frame,
                         text="", bg="#3c2a00", fg="#e2c08d",
                         font=("Segoe UI", 8), justify="left",
                         padx=8, pady=4, cursor="hand2", wraplength=180)
        self._warn_lbl.pack(side="left", fill="x", expand=True)
        self._warn_details_btn = Label(self._warn_frame, text="Details →",
                                       bg="#3c2a00", fg="#e2c08d",
                                       font=("Segoe UI", 8, "bold"),
                                       padx=6, pady=4, cursor="hand2")
        self._warn_details_btn.pack(side="right")
        for w in (self._warn_frame, self._warn_lbl, self._warn_details_btn):
            w.bind("<Button-1>", lambda _: self._open_wizard())
        self._current_issues: list[Issue] = []

        self._staged_sec   = _Section(self, "STAGED CHANGES",
                                      on_toggle=self._repack_sections)
        self._sep = ttk.Separator(self, orient="horizontal")
        self._unstaged_sec = _Section(self, "CHANGES",
                                      on_toggle=self._repack_sections)
        self._repack_sections()

        # Single unified context menu — items shown/hidden based on context
        self._ctx_menu = Menu(self, tearoff=0)
        self._ctx_menu.add_command(label="Stage Changes",    command=self._ctx_do_stage)
        self._ctx_menu.add_command(label="Unstage Changes",  command=self._ctx_do_unstage)
        self._ctx_menu.add_command(label="Discard Changes",  command=self._ctx_do_discard)
        self._ctx_menu.add_command(label="Open Diff",        command=self._ctx_do_diff)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Create .gitignore", command=self._ctx_create_gitignore)

        self._ctx_section = None  # "staged" | "changes" | None
        self.bind("<Button-3>", lambda e: self._show_ctx(e, "", None))
        self._staged_sec.bind_panel_menu(lambda e: self._show_ctx(e, "", None))
        self._unstaged_sec.bind_panel_menu(lambda e: self._show_ctx(e, "", None))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _repack_sections(self) -> None:
        """Re-pack both sections so only expanded ones get expand=True."""
        self._warn_frame.pack_forget()
        self._staged_sec.pack_forget()
        self._sep.pack_forget()
        self._unstaged_sec.pack_forget()

        staged_exp   = not self._staged_sec._collapsed
        unstaged_exp = not self._unstaged_sec._collapsed

        if self._warn_visible:
            self._warn_frame.pack(fill="x")
        self._staged_sec.pack(fill="both", expand=staged_exp)
        self._sep.pack(fill="x")
        self._unstaged_sec.pack(fill="both", expand=unstaged_exp)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, staged: dict[str, str], unstaged: dict[str, str]) -> None:
        """Re-populate both file lists and update diagnostics."""
        self._last_staged   = staged
        self._last_unstaged = unstaged

        # Smart issue detection
        fix_fns = {"create_gitignore": self._ctx_create_gitignore}
        self._current_issues = analyze_files(unstaged, fix_fns=fix_fns)

        # Update warning banner with specific message
        high_issues = [i for i in self._current_issues if i.severity == "high"]
        self._warn_visible = bool(high_issues)
        if self._warn_visible:
            if len(high_issues) == 1:
                msg = f"⚠ {high_issues[0].title}"
            else:
                msg = f"⚠ {len(high_issues)} issues detected"
            self._warn_lbl.config(text=msg)
            self._warn_frame.pack(fill="x", before=self._staged_sec)
        else:
            self._warn_frame.pack_forget()

        # Update health panel
        self._refresh_health(staged, unstaged)

        self._staged_sec.populate(
            staged,
            on_click=self._on_diff,
            on_right_click=lambda e, p: self._show_ctx(e, p, "staged"),
            panel_menu_cb=lambda e: self._show_ctx(e, "", None),
        )
        self._unstaged_sec.populate(
            unstaged,
            on_click=self._on_diff,
            on_right_click=lambda e, p: self._show_ctx(e, p, "changes"),
            panel_menu_cb=lambda e: self._show_ctx(e, "", None),
        )

    def apply_theme(self, bg: str, fg: str, select_bg: str) -> None:
        ttk.Style().configure("SC.TFrame", background=bg)
        self._staged_sec.apply_theme(bg, fg)
        self._unstaged_sec.apply_theme(bg, fg)

    # ── Commit area ───────────────────────────────────────────────────────────

    def _build_commit_area(self) -> None:
        outer = Frame(self, bg=_BG, padx=6, pady=6)
        outer.pack(fill="x")

        # Placeholder-style Text widget for commit message
        self._msg = tk.Text(
            outer,
            height=3,
            bg="#3c3c3c",
            fg=_DIM,
            insertbackground=_FG,
            font=("Segoe UI", 9),
            relief="flat",
            padx=6,
            pady=4,
            wrap="word",
        )
        self._msg.insert("1.0", "Commit message…")
        self._msg.pack(fill="x")
        self._msg.bind("<FocusIn>",  self._msg_focus_in)
        self._msg.bind("<FocusOut>", self._msg_focus_out)
        self._placeholder_active = True

        # Buttons row — Labels used instead of Buttons for consistent cross-platform styling
        btn_row = Frame(outer, bg=_BG)
        btn_row.pack(fill="x", pady=(5, 0))

        def _btn(parent, text, command):
            lbl = Label(parent, text=text, bg=_BTN_BG, fg="white",
                        font=("Segoe UI", 8, "bold"), cursor="hand2",
                        padx=8, pady=3)
            lbl.bind("<Button-1>", lambda _: command())
            lbl.bind("<Enter>", lambda _: lbl.config(bg=_BTN_ACT))
            lbl.bind("<Leave>", lambda _: lbl.config(bg=_BTN_BG))
            return lbl

        _btn(btn_row, "✓ Commit", self._do_commit).pack(side="left")
        _btn(btn_row, "↑ Push",   self._on_push).pack(side="left", padx=(4, 0))
        _btn(btn_row, "↓ Pull",   self._on_pull).pack(side="left", padx=(4, 0))

    def _msg_focus_in(self, _) -> None:
        if self._placeholder_active:
            self._msg.delete("1.0", "end")
            self._msg.config(fg=_FG)
            self._placeholder_active = False

    def _msg_focus_out(self, _) -> None:
        if not self._msg.get("1.0", "end-1c").strip():
            self._msg.delete("1.0", "end")
            self._msg.insert("1.0", "Commit message…")
            self._msg.config(fg=_DIM)
            self._placeholder_active = True

    def _do_commit(self) -> None:
        msg = self._msg.get("1.0", "end-1c").strip()
        if not msg or self._placeholder_active:
            return
        self._on_commit(msg)
        # Clear message field after commit
        self._msg.delete("1.0", "end")
        self._msg.insert("1.0", "Commit message…")
        self._msg.config(fg=_DIM)
        self._placeholder_active = True

    # ── Git Health panel ──────────────────────────────────────────────────────

    def _build_health_panel(self) -> None:
        """Build the collapsible Git Health checklist panel."""
        self._health_collapsed = True
        self._health_frame = Frame(self, bg=_BG)

        hdr = Frame(self._health_frame, bg=_HDR_BG, height=24, cursor="hand2")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self._health_arrow = Label(hdr, text="▸", bg=_HDR_BG, fg=_FG,
                                   font=("Segoe UI", 8))
        self._health_arrow.pack(side="left", padx=(4, 0))
        Label(hdr, text="GIT HEALTH", bg=_HDR_BG, fg=_FG,
              font=("Segoe UI", 8, "bold"), anchor="w").pack(
                  side="left", fill="x", expand=True)
        self._health_status_lbl = Label(hdr, text="", bg=_HDR_BG,
                                        font=("Segoe UI", 8), padx=6)
        self._health_status_lbl.pack(side="right")

        for w in hdr.winfo_children():
            w.bind("<Button-1>", lambda _: self._toggle_health())
        hdr.bind("<Button-1>", lambda _: self._toggle_health())

        self._health_body = Frame(self._health_frame, bg=_BG)
        self._health_rows: list[Frame] = []

        self._health_frame.pack(fill="x")

    def _toggle_health(self) -> None:
        self._health_collapsed = not self._health_collapsed
        self._health_arrow.config(text="▸" if self._health_collapsed else "▾")
        if self._health_collapsed:
            self._health_body.pack_forget()
        else:
            self._health_body.pack(fill="x")

    def _refresh_health(self, staged: dict[str, str], unstaged: dict[str, str]) -> None:
        """Rebuild the health checklist rows."""
        for w in self._health_body.winfo_children():
            w.destroy()

        fix_fns = {"create_gitignore": self._ctx_create_gitignore}
        # Pass repo root via gitignore_check_fn closure if available
        checks = self._get_health_checks(staged, unstaged, fix_fns)

        passed = sum(1 for c in checks if c.passed)
        total  = len(checks)
        all_ok = passed == total
        self._health_status_lbl.config(
            text=f"{passed}/{total}" ,
            fg="#73c991" if all_ok else "#e2c08d",
            bg=_HDR_BG,
        )

        for check in checks:
            row = Frame(self._health_body, bg=_BG)
            row.pack(fill="x", padx=6, pady=1)

            icon = "✓" if check.passed else "✗"
            color = "#73c991" if check.passed else "#f14c4c"
            Label(row, text=icon, bg=_BG, fg=color,
                  font=("Segoe UI", 9, "bold"), width=2).pack(side="left")
            Label(row, text=check.label, bg=_BG, fg=_FG,
                  font=("Segoe UI", 8), anchor="w").pack(side="left", fill="x", expand=True)

            if check.fix_fn:
                btn = Label(row, text=check.fix_label, bg=_BTN_BG, fg="white",
                            font=("Segoe UI", 7, "bold"), padx=4, pady=1,
                            cursor="hand2")
                btn.pack(side="right", padx=(0, 2))
                btn.bind("<Button-1>", lambda _, fn=check.fix_fn: fn())

            _Tooltip(row, check.detail)

    def _get_health_checks(self, staged, unstaged, fix_fns) -> list[HealthCheck]:
        """Get health checks using repo root from app."""
        repo_root = self._repo_root_fn() if self._repo_root_fn else ""
        return health_checks(repo_root, staged, unstaged, fix_fns=fix_fns)

    # ── Guided fix wizard ─────────────────────────────────────────────────────

    def _open_wizard(self) -> None:
        """Open the step-by-step guided fix wizard using GuideWindow."""
        if not self._current_issues:
            return
        pages = [
            GuidePage(
                title=issue.title,
                subtitle=f"Issue {i + 1} of {len(self._current_issues)}",
                sections=[
                    ("WHAT HAPPENED",  issue.what, "#e2c08d"),
                    ("WHY IT MATTERS", issue.why,  "#f14c4c"),
                    ("HOW TO FIX IT",  issue.how,  "#73c991"),
                ],
                action_label=issue.fix_label if issue.fix_fn else "",
                action_fn=issue.fix_fn,
            )
            for i, issue in enumerate(self._current_issues)
        ]
        GuideWindow(self, "Git Fix Guide", pages)

    # ── Context menu helpers ──────────────────────────────────────────────────

    def _show_ctx(self, event, path: str, section: str | None) -> None:
        self._ctx_path    = path
        self._ctx_section = section

        # Show/hide items based on context
        has_file = bool(path)
        self._ctx_menu.entryconfigure("Stage Changes",    state="normal" if has_file and section == "changes" else "disabled")
        self._ctx_menu.entryconfigure("Unstage Changes",  state="normal" if has_file and section == "staged"  else "disabled")
        self._ctx_menu.entryconfigure("Discard Changes",  state="normal" if has_file and section == "changes" else "disabled")
        self._ctx_menu.entryconfigure("Open Diff",        state="normal" if has_file else "disabled")

        self._ctx_menu.tk_popup(event.x_root, event.y_root)

    def _ctx_do_stage(self)   -> None: self._on_stage(self._ctx_path)
    def _ctx_do_unstage(self) -> None: self._on_unstage(self._ctx_path)
    def _ctx_do_discard(self) -> None: self._on_discard(self._ctx_path)
    def _ctx_do_diff(self)    -> None: self._on_diff(self._ctx_path)

    def _ctx_create_gitignore(self) -> None:
        if self._on_create_gitignore:
            self._on_create_gitignore()

