"""Learning Mode panel — displays contextual help for hovered IDE elements."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from utils.learning_registry import REGISTRY
from widgets.scrollbar import VerticalScrollbar
from utils import ollama_client
from utils.ui_font import UI_FONT


_BG         = "#1e1e1e"
_HEADER_BG  = "#252526"
_TITLE_FG   = "#569cd6"   # blue
_SECTION_FG = "#c586c0"   # purple
_BODY_FG    = "#cccccc"
_DIM_FG     = "#858585"
_ACCENT     = "#4ec9b0"   # teal for example block
_AI_BG      = "#1a1a2e"   # dark navy for AI section
_AI_FG      = "#9cdcfe"   # light blue for AI text
_BTN_BG     = "#0e639c"
_BTN_ACT    = "#1177bb"
_WARN_FG    = "#ce9178"   # orange — offline warning

_WELCOME_ID = "__welcome__"

REGISTRY[_WELCOME_ID] = {
    "title": "IDOL Learning Mode",
    "what": (
        "Learning Mode is active. Hover over any part of the IDE — "
        "panels, buttons, the editor, status bar — and this panel will explain what it does."
    ),
    "how": (
        "Each explanation has three sections:\n"
        "  WHAT IT IS — a plain-English description\n"
        "  HOW IT WORKS — the mechanics behind it\n"
        "  REAL-WORLD EXAMPLE — how you'd actually use it"
    ),
    "example": (
        "Try hovering the Outline panel on the left, the Commit button, "
        "or the branch name in the status bar."
    ),
}


class LearningPanel(tk.Frame):
    """Scrollable panel that displays what/how/example for a hovered widget."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, bg=_BG, **kwargs)
        self._current_lid: str = _WELCOME_ID
        self._ai_available: bool = False
        self._ai_label: tk.Label | None = None
        self._ai_btn: tk.Label | None = None
        self._generating: bool = False
        self._build()
        self.show(_WELCOME_ID)
        # Check Ollama availability in the background
        ollama_client.check_async(self._on_ollama_status)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self._canvas = tk.Canvas(self, bg=_BG, highlightthickness=0, bd=0)
        self._sb = VerticalScrollbar(self, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._sb.set)

        self._sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas, bg=_BG)
        self._win = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>",   self._on_mousewheel)
        self._canvas.bind("<Button-5>",   self._on_mousewheel)

    def _on_inner_configure(self, _=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._win, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-event.delta / 120), "units")

    # ── Ollama status ─────────────────────────────────────────────────────────

    def _on_ollama_status(self, available: bool) -> None:
        self._ai_available = available
        # Re-render current content to update the AI section
        try:
            self.after(0, lambda: self.show(self._current_lid))
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────────

    def show(self, lid: str) -> None:
        """Populate the panel with content for *lid*."""
        self._current_lid = lid
        self._generating = False
        payload = REGISTRY.get(lid) or REGISTRY.get(_WELCOME_ID)
        self._render(payload)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, payload: dict) -> None:
        for child in self._inner.winfo_children():
            child.destroy()
        self._ai_label = None
        self._ai_btn   = None

        pad = {"padx": 14, "pady": 0}

        # ── Title ─────────────────────────────────────────────────────────────
        tk.Frame(self._inner, bg=_BG, height=12).pack(fill="x")

        tk.Label(
            self._inner,
            text=f"📖  {payload['title']}",
            bg=_BG, fg=_TITLE_FG,
            font=(UI_FONT, 11, "bold"),
            anchor="w", justify="left",
        ).pack(fill="x", **pad)

        tk.Frame(self._inner, bg="#3c3c3c", height=1).pack(fill="x", padx=14, pady=(8, 0))

        # ── Static sections ───────────────────────────────────────────────────
        sections = [
            ("WHAT IT IS",         payload.get("what", ""),    _BODY_FG, _HEADER_BG),
            ("HOW IT WORKS",       payload.get("how", ""),     _BODY_FG, _HEADER_BG),
            ("REAL-WORLD EXAMPLE", payload.get("example", ""), _ACCENT,  "#1a2a2a"),
        ]

        for header, body, fg, bg_block in sections:
            if not body:
                continue

            tk.Frame(self._inner, bg=_BG, height=10).pack(fill="x")

            tk.Label(
                self._inner,
                text=header,
                bg=_BG, fg=_SECTION_FG,
                font=(UI_FONT, 8, "bold"),
                anchor="w",
            ).pack(fill="x", **pad)

            tk.Frame(self._inner, bg=_BG, height=4).pack(fill="x")

            block = tk.Frame(self._inner, bg=bg_block, padx=10, pady=8)
            block.pack(fill="x", padx=14)

            tk.Label(
                block,
                text=body,
                bg=bg_block, fg=fg,
                font=(UI_FONT, 9),
                anchor="nw",
                justify="left",
                wraplength=220,
            ).pack(fill="x", anchor="w")

        # ── AI section ────────────────────────────────────────────────────────
        # Don't show AI section on the welcome card
        if self._current_lid != _WELCOME_ID:
            self._render_ai_section(payload)

        tk.Frame(self._inner, bg=_BG, height=16).pack(fill="x")
        self._canvas.yview_moveto(0)
        self._bind_scroll_recursive(self._inner)

    def _render_ai_section(self, payload: dict) -> None:
        pad = {"padx": 14, "pady": 0}

        tk.Frame(self._inner, bg=_BG, height=10).pack(fill="x")

        # Section header row with status dot
        hdr_row = tk.Frame(self._inner, bg=_BG)
        hdr_row.pack(fill="x", **pad)

        tk.Label(
            hdr_row,
            text="✦ ASK LOCAL AI",
            bg=_BG, fg=_SECTION_FG,
            font=(UI_FONT, 8, "bold"),
            anchor="w",
        ).pack(side="left")

        status_dot = tk.Label(
            hdr_row,
            text="● online" if self._ai_available else "● offline",
            bg=_BG,
            fg="#4ec9b0" if self._ai_available else _DIM_FG,
            font=(UI_FONT, 7),
        )
        status_dot.pack(side="right")

        tk.Frame(self._inner, bg=_BG, height=4).pack(fill="x")

        # AI content block
        ai_block = tk.Frame(self._inner, bg=_AI_BG, padx=10, pady=8)
        ai_block.pack(fill="x", padx=14)

        if not self._ai_available:
            # Offline card — platform-specific install instructions
            import sys
            if sys.platform == "win32":
                install_cmd = "irm https://ollama.com/install.ps1 | iex"
                shell_note  = "(run in PowerShell)"
            else:
                install_cmd = "curl -fsSL https://ollama.com/install.sh | sh"
                shell_note  = "(run in Terminal)"

            tk.Label(
                ai_block,
                text="Local AI (Ollama) is not running.",
                bg=_AI_BG, fg=_WARN_FG,
                font=(UI_FONT, 9, "bold"),
                anchor="nw", justify="left",
                wraplength=220,
            ).pack(fill="x", anchor="w", pady=(0, 6))

            tk.Label(
                ai_block,
                text=(
                    "Get AI-powered explanations with no API key needed.\n\n"
                    "Step 1 — Install Ollama " + shell_note + ":"
                ),
                bg=_AI_BG, fg=_BODY_FG,
                font=(UI_FONT, 9),
                anchor="nw", justify="left",
                wraplength=220,
            ).pack(fill="x", anchor="w")

            tk.Label(
                ai_block,
                text=install_cmd,
                bg="#0d0d0d", fg="#4ec9b0",
                font=("Courier New", 8),
                anchor="nw", justify="left",
                wraplength=220, padx=6, pady=4,
            ).pack(fill="x", anchor="w", pady=(2, 8))

            tk.Label(
                ai_block,
                text="Step 2 — Install the AI model\n(Warning: ~4GB download):",
                bg=_AI_BG, fg=_BODY_FG,
                font=(UI_FONT, 9),
                anchor="nw", justify="left",
                wraplength=220,
            ).pack(fill="x", anchor="w")

            tk.Label(
                ai_block,
                text="ollama pull qwen2.5-coder",
                bg="#0d0d0d", fg="#4ec9b0",
                font=("Courier New", 8),
                anchor="nw", justify="left",
                wraplength=220, padx=6, pady=4,
            ).pack(fill="x", anchor="w", pady=(2, 8))

            tk.Label(
                ai_block,
                text="Once running, reopen the Learning tab to activate.",
                bg=_AI_BG, fg=_DIM_FG,
                font=(UI_FONT, 8, "italic"),
                anchor="nw", justify="left",
                wraplength=220,
            ).pack(fill="x", anchor="w")
        else:
            # AI response label (empty until generated)
            self._ai_label = tk.Label(
                ai_block,
                text="Click below to get an AI explanation.",
                bg=_AI_BG, fg=_DIM_FG,
                font=(UI_FONT, 9),
                anchor="nw", justify="left",
                wraplength=220,
            )
            self._ai_label.pack(fill="x", anchor="w")

            tk.Frame(self._inner, bg=_BG, height=6).pack(fill="x")

            # Ask AI button
            btn = tk.Label(
                self._inner,
                text="✦ Ask AI",
                bg=_BTN_BG, fg="white",
                font=(UI_FONT, 8, "bold"),
                cursor="hand2", padx=10, pady=4,
            )
            btn.pack(anchor="w", padx=14)
            btn.bind("<Enter>", lambda _: btn.config(bg=_BTN_ACT))
            btn.bind("<Leave>", lambda _: btn.config(bg=_BTN_BG))
            btn.bind("<Button-1>", lambda _: self._ask_ai(payload, btn))
            self._ai_btn = btn

    # ── AI generation ─────────────────────────────────────────────────────────

    def _ask_ai(self, payload: dict, btn: tk.Label) -> None:
        if self._generating:
            return
        self._generating = True

        btn.config(text="⏳ Thinking…", bg=_DIM_FG, cursor="")
        btn.unbind("<Button-1>")

        if self._ai_label:
            self._ai_label.config(text="", fg=_AI_FG)

        prompt = ollama_client.prompt_for_element(
            payload["title"], payload.get("what", "")
        )

        accumulated = []

        def _widget_ok(w: tk.Widget) -> bool:
            try:
                return bool(w.winfo_exists())
            except Exception:
                return False

        def _on_chunk(token: str) -> None:
            accumulated.append(token)
            text = "".join(accumulated)
            def _apply(t=text):
                if self._ai_label and _widget_ok(self._ai_label):
                    self._ai_label.config(text=t)
            try:
                self.after(0, _apply)
            except Exception:
                pass

        def _on_done(full: str) -> None:
            self._generating = False
            def _apply():
                if not _widget_ok(btn):
                    return
                btn.config(text="✦ Ask Again", bg=_BTN_BG, cursor="hand2")
                btn.bind("<Enter>",    lambda _: btn.config(bg=_BTN_ACT))
                btn.bind("<Leave>",    lambda _: btn.config(bg=_BTN_BG))
                btn.bind("<Button-1>", lambda _: self._ask_ai(payload, btn))
            try:
                self.after(0, _apply)
            except Exception:
                pass

        def _on_error(msg: str) -> None:
            self._generating = False
            def _apply():
                if self._ai_label and _widget_ok(self._ai_label):
                    self._ai_label.config(text=f"Error: {msg}", fg=_WARN_FG)
                if _widget_ok(btn):
                    btn.config(text="✦ Retry", bg=_BTN_BG, cursor="hand2")
                    btn.bind("<Button-1>", lambda _: self._ask_ai(payload, btn))
            try:
                self.after(0, _apply)
            except Exception:
                pass

        ollama_client.generate(
            prompt,
            on_chunk=_on_chunk,
            on_done=_on_done,
            on_error=_on_error,
        )

    def _bind_scroll_recursive(self, widget) -> None:
        """Bind mousewheel on every child so scrolling works over all content."""
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>",   self._on_mousewheel, add="+")
        widget.bind("<Button-5>",   self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_scroll_recursive(child)

    def apply_theme(self, bg: str, fg: str, _select_bg: str) -> None:
        pass
