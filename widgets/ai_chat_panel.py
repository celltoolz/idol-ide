"""AI Chat panel — conversational interface to local Ollama LLM."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from utils import ollama_client


_BG         = "#1e1e1e"
_MSG_BG     = "#252526"
_USER_BG    = "#0e3a5c"
_AI_BG      = "#1a2a1a"
_CODE_BG    = "#0d0d0d"
_INPUT_BG   = "#2d2d30"
_BORDER     = "#3c3c3c"
_FG         = "#cccccc"
_USER_FG    = "#9cdcfe"
_AI_FG      = "#b5cea8"
_CODE_FG    = "#4ec9b0"
_DIM        = "#858585"
_BTN_BG     = "#0e639c"
_BTN_ACT    = "#1177bb"
_WARN_FG    = "#ce9178"
_SEND_BG    = "#0e639c"


class AiChatPanel(tk.Frame):
    """Full chat interface: scrollable history + input box + context buttons."""

    def __init__(self, parent,
                 get_file_content: Callable[[], tuple[str, str]] | None = None,
                 get_selection: Callable[[], str] | None = None,
                 **kwargs) -> None:
        super().__init__(parent, bg=_BG, **kwargs)
        self._get_file_content = get_file_content  # () -> (filename, content)
        self._get_selection    = get_selection      # () -> selected text
        self._generating       = False
        self._history: list[dict] = []              # [{role, content}]
        self._ai_available     = False
        self._current_ai_label: tk.Frame | None = None
        self._scroll_job = None
        self._render_job = None
        self._pending_render_text: str = ""

        self._build()
        ollama_client.check_async(self._on_ollama_status)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Message scroll area ───────────────────────────────────────────────
        msg_frame = tk.Frame(self, bg=_BG)
        msg_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(msg_frame, bg=_BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(msg_frame, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._msg_inner = tk.Frame(self._canvas, bg=_BG)
        self._msg_win = self._canvas.create_window((0, 0), window=self._msg_inner,
                                                   anchor="nw")
        self._msg_inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>",    self._on_canvas_configure)
        # Bind scroll on both canvas and inner frame so it fires regardless
        # of which child widget the pointer is over
        for w in (self._canvas, self._msg_inner):
            w.bind("<MouseWheel>", self._on_mousewheel, add="+")
            w.bind("<Button-4>",   self._on_mousewheel, add="+")
            w.bind("<Button-5>",   self._on_mousewheel, add="+")

        # ── Separator ─────────────────────────────────────────────────────────
        tk.Frame(self, bg=_BORDER, height=1).pack(fill="x")

        # ── Input area ────────────────────────────────────────────────────────
        input_outer = tk.Frame(self, bg=_INPUT_BG)
        input_outer.pack(fill="x", side="bottom")

        # Context buttons row
        ctx_row = tk.Frame(input_outer, bg=_INPUT_BG)
        ctx_row.pack(fill="x", padx=8, pady=(6, 0))

        self._file_btn = self._make_ctx_btn(ctx_row, "📄 Send File",  self._attach_file)
        self._file_btn.pack(side="left", padx=(0, 4))
        self._sel_btn  = self._make_ctx_btn(ctx_row, "✂ Selection",  self._attach_selection)
        self._sel_btn.pack(side="left")

        self._ctx_label = tk.Label(ctx_row, text="", bg=_INPUT_BG, fg=_DIM,
                                   font=("Segoe UI", 8), anchor="w")
        self._ctx_label.pack(side="left", padx=(8, 0))

        # Text input + send button
        input_row = tk.Frame(input_outer, bg=_INPUT_BG)
        input_row.pack(fill="x", padx=8, pady=(4, 8))

        self._input = tk.Text(input_row, bg=_INPUT_BG, fg=_FG,
                              insertbackground=_FG,
                              font=("Segoe UI", 10),
                              height=3, wrap="word",
                              relief="flat", bd=0,
                              highlightthickness=1,
                              highlightbackground=_BORDER,
                              highlightcolor=_BTN_BG)
        self._input.pack(side="left", fill="both", expand=True)
        self._input.bind("<Return>",       self._on_return)
        self._input.bind("<Shift-Return>", self._on_shift_return)

        send_btn = tk.Label(input_row, text="↑", bg=_SEND_BG, fg="white",
                            font=("Segoe UI", 14, "bold"),
                            cursor="hand2", width=2, pady=4)
        send_btn.pack(side="right", padx=(6, 0), fill="y")
        send_btn.bind("<Button-1>", lambda _: self._send())
        send_btn.bind("<Enter>",    lambda _: send_btn.config(bg=_BTN_ACT))
        send_btn.bind("<Leave>",    lambda _: send_btn.config(bg=_SEND_BG))

        self._pending_ctx: str = ""   # attached code context

        # Show welcome message
        self._show_welcome()

    # ── Canvas helpers ────────────────────────────────────────────────────────

    def _on_inner_configure(self, _=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._msg_win, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _scroll_bottom(self) -> None:
        """Debounced scroll-to-bottom — coalesces rapid calls into one."""
        if self._scroll_job:
            try:
                self.after_cancel(self._scroll_job)
            except Exception:
                pass
        try:
            self._scroll_job = self.after(50, self._do_scroll_bottom)
        except Exception:
            pass

    def _do_scroll_bottom(self) -> None:
        self._scroll_job = None
        try:
            self._canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ── Ollama status ─────────────────────────────────────────────────────────

    def _on_ollama_status(self, available: bool) -> None:
        self._ai_available = available
        if not available:
            try:
                self.after(0, self._show_offline_card)
            except Exception:
                pass

    def _show_offline_card(self) -> None:
        import sys
        if sys.platform == "win32":
            install_cmd = "irm https://ollama.com/install.ps1 | iex"
            shell_note  = "PowerShell"
        else:
            install_cmd = "curl -fsSL https://ollama.com/install.sh | sh"
            shell_note  = "Terminal"

        self._append_system(
            f"Local AI (Ollama) is not running.\n\n"
            f"Step 1 — Install Ollama (run in {shell_note}):\n"
            f"  {install_cmd}\n\n"
            f"Step 2 — Install the AI model (~4GB):\n"
            f"  ollama pull qwen2.5-coder\n\n"
            f"Then reopen this tab.",
            color=_WARN_FG,
        )

    # ── Welcome ───────────────────────────────────────────────────────────────

    def _show_welcome(self) -> None:
        self._append_system(
            "Hi! I'm your local AI assistant, running fully offline via Ollama.\n\n"
            "Ask me anything about Python, your code, or how the IDE works.\n\n"
            "📄 Send File — attaches your currently open file as context\n"
            "✂ Selection — attaches highlighted text from the editor\n\n"
            "After clicking either button, type your question and send.\n"
            "Press Enter to send  ·  Shift+Enter for a new line."
        )

    # ── Context buttons ───────────────────────────────────────────────────────

    def _make_ctx_btn(self, parent, text: str, cmd: Callable) -> tk.Label:
        lbl = tk.Label(parent, text=text, bg="#3c3c3c", fg=_FG,
                       font=("Segoe UI", 8), cursor="hand2",
                       padx=6, pady=2)
        lbl.bind("<Button-1>", lambda _: cmd())
        lbl.bind("<Enter>",    lambda _: lbl.config(bg="#505050"))
        lbl.bind("<Leave>",    lambda _: lbl.config(bg="#3c3c3c"))
        return lbl

    def _attach_file(self) -> None:
        if not self._get_file_content:
            return
        filename, content = self._get_file_content()
        if not content:
            return
        self._pending_ctx = f"# File: {filename}\n\n{content}"
        short = filename if len(filename) < 30 else "..." + filename[-27:]
        self._ctx_label.config(text=f"📄 {short}", fg=_USER_FG)

    def _attach_selection(self) -> None:
        if not self._get_selection:
            return
        sel = self._get_selection()
        if not sel.strip():
            return
        self._pending_ctx = f"# Selected code:\n\n{sel}"
        preview = sel.strip()[:40].replace("\n", " ")
        self._ctx_label.config(text=f"✂ {preview}…", fg=_USER_FG)

    def _clear_ctx(self) -> None:
        self._pending_ctx = ""
        self._ctx_label.config(text="")

    # ── Send ──────────────────────────────────────────────────────────────────

    def _on_return(self, event) -> str:
        self._send()
        return "break"

    def _on_shift_return(self, event) -> None:
        pass   # let default newline insertion happen

    def _send(self) -> None:
        if self._generating:
            return
        user_text = self._input.get("1.0", "end-1c").strip()
        if not user_text:
            return

        self._input.delete("1.0", "end")

        # Build full message with optional context
        full_msg = user_text
        if self._pending_ctx:
            full_msg = f"{self._pending_ctx}\n\n{user_text}"
            self._clear_ctx()

        # Display user bubble (show only the user's typed text, not the full ctx blob)
        self._append_user(user_text)

        # Add to history
        self._history.append({"role": "user", "content": full_msg})

        if not self._ai_available:
            self._append_system("Ollama is not running. See setup instructions above.", _WARN_FG)
            return

        self._generating = True
        self._current_ai_label = self._append_ai_bubble()

        # Build prompt from full history
        prompt = self._build_prompt()

        accumulated = []

        def _on_chunk(token: str) -> None:
            accumulated.append(token)
            self._pending_render_text = "".join(accumulated)
            try:
                self.after(0, self._schedule_render)
            except Exception:
                pass


        def _on_done(full: str) -> None:
            self._generating = False
            self._history.append({"role": "assistant", "content": full})
            # Final render — cancel any pending debounce and render immediately
            try:
                self.after(0, lambda: (
                    self._cancel_render_job(),
                    self._update_ai_bubble(full),
                    self._scroll_bottom(),
                ))
            except Exception:
                pass

        def _on_error(msg: str) -> None:
            self._generating = False
            try:
                self.after(0, lambda: self._append_system(f"Error: {msg}", _WARN_FG))
            except Exception:
                pass

        ollama_client.generate(
            prompt,
            on_chunk=_on_chunk,
            on_done=_on_done,
            on_error=_on_error,
        )

    def _build_prompt(self) -> str:
        """Flatten history into a single prompt string."""
        parts = [
            "You are a helpful Python tutor and IDE assistant inside IDOL, "
            "a beginner-friendly Python IDE. Be concise and practical. "
            "Use plain text — no markdown bold/italic. "
            "For code, wrap in triple backticks.\n"
        ]
        for msg in self._history:
            role = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role}: {msg['content']}")
        parts.append("Assistant:")
        return "\n\n".join(parts)

    # ── Bubble rendering ──────────────────────────────────────────────────────

    def _append_user(self, text: str) -> None:
        self._add_spacer(6)
        row = tk.Frame(self._msg_inner, bg=_BG)
        row.pack(fill="x", padx=10, pady=0)

        bubble = tk.Frame(row, bg=_USER_BG, padx=10, pady=6)
        bubble.pack(side="right", anchor="e")

        tk.Label(bubble, text="You", bg=_USER_BG, fg=_DIM,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")
        tk.Label(bubble, text=text, bg=_USER_BG, fg=_USER_FG,
                 font=("Segoe UI", 10), wraplength=380,
                 justify="left", anchor="nw").pack(anchor="w")
        self._scroll_bottom()

    def _append_ai_bubble(self) -> tk.Frame:
        """Add an AI bubble with a plain streaming Text widget."""
        self._add_spacer(6)
        row = tk.Frame(self._msg_inner, bg=_BG)
        row.pack(fill="x", padx=10)

        bubble = tk.Frame(row, bg=_AI_BG, padx=10, pady=6)
        bubble.pack(side="left", anchor="w", fill="x", expand=True)

        tk.Label(bubble, text="🤖 AI", bg=_AI_BG, fg=_DIM,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w")

        # Single plain-text widget used during streaming — replaced on completion
        stream_txt = tk.Text(bubble, bg=_AI_BG, fg=_AI_FG,
                             font=("Segoe UI", 10),
                             wrap="word", relief="flat", bd=0,
                             highlightthickness=0,
                             state="disabled", cursor="arrow",
                             height=1)
        stream_txt.pack(fill="x", anchor="w")
        stream_txt.bind("<MouseWheel>", self._on_mousewheel)
        stream_txt.bind("<Button-4>",   self._on_mousewheel)
        stream_txt.bind("<Button-5>",   self._on_mousewheel)
        bubble._stream_txt = stream_txt   # type: ignore[attr-defined]

        return bubble

    def _schedule_render(self) -> None:
        """Stream update — just update the plain-text widget, no rebuilding."""
        text = self._pending_render_text
        bubble = self._current_ai_label
        if not bubble:
            return
        try:
            if not bubble.winfo_exists():
                return
        except Exception:
            return
        # Update the single streaming Text widget in-place — no destroy/rebuild
        txt = getattr(bubble, "_stream_txt", None)
        if txt:
            try:
                if not txt.winfo_exists():
                    return
                txt.config(state="normal")
                txt.delete("1.0", "end")
                txt.insert("1.0", text)
                lines = int(txt.index("end-1c").split(".")[0])
                txt.config(height=max(1, lines), state="disabled")
            except Exception:
                pass
        self._scroll_bottom()

    def _cancel_render_job(self) -> None:
        if self._render_job:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
            self._render_job = None

    def _flush_render(self) -> None:
        self._render_job = None

    def _update_ai_bubble(self, text: str) -> None:
        """Final render — replace streaming widget with formatted code blocks."""
        bubble = self._current_ai_label
        if not bubble:
            return
        try:
            if not bubble.winfo_exists():
                return
        except Exception:
            return

        # Remove all content below the header label (including stream widget)
        children = bubble.winfo_children()
        for w in children[1:]:
            try:
                w.destroy()
            except Exception:
                pass

        self._render_message(bubble, text)
        self._bind_scroll_recursive(bubble)
        self._scroll_bottom()

    def _render_message(self, bubble: tk.Frame, text: str) -> None:
        """Render text + code blocks as child widgets of *bubble*."""
        parts = text.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # ── Code block ────────────────────────────────────────────────
                lines = part.split("\n")
                # Strip language hint (e.g. "python", "bash") from first line
                if lines and lines[0].strip().replace("-", "").replace("_", "").isidentifier():
                    lines = lines[1:]
                code = "\n".join(lines).strip()
                if not code:
                    continue
                code_lines = code.count("\n") + 1

                # Outer frame — black background, slight padding
                code_frame = tk.Frame(bubble, bg=_CODE_BG, pady=0)
                code_frame.pack(fill="x", anchor="w", pady=(4, 0))

                # Header row: "code" label + Copy button
                hdr = tk.Frame(code_frame, bg=_CODE_BG)
                hdr.pack(fill="x", padx=6, pady=(4, 0))

                tk.Label(hdr, text="code", bg=_CODE_BG, fg=_DIM,
                         font=("Segoe UI", 7)).pack(side="left")

                copy_btn = tk.Label(hdr, text="⎘ Copy", bg=_CODE_BG, fg=_DIM,
                                    font=("Segoe UI", 7), cursor="hand2")
                copy_btn.pack(side="right")

                # Bind copy — capture code value
                def _copy(_, c=code):
                    try:
                        bubble.clipboard_clear()
                        bubble.clipboard_append(c)
                    except Exception:
                        pass

                def _copy_enter(_, btn=copy_btn): btn.config(fg=_AI_FG)
                def _copy_leave(_, btn=copy_btn): btn.config(fg=_DIM)

                copy_btn.bind("<Button-1>", _copy)
                copy_btn.bind("<Enter>",    _copy_enter)
                copy_btn.bind("<Leave>",    _copy_leave)

                # Code text widget
                txt = tk.Text(code_frame, bg=_CODE_BG, fg=_CODE_FG,
                              font=("Courier New", 9),
                              wrap="none", relief="flat", bd=0,
                              highlightthickness=0,
                              state="normal", cursor="arrow",
                              height=code_lines + 1)  # +1 = empty line at bottom
                txt.pack(fill="x", padx=6, pady=(2, 4))
                txt.insert("1.0", code + "\n")        # trailing newline = bottom padding
                txt.config(state="disabled")
                txt.bind("<MouseWheel>", self._on_mousewheel)
                txt.bind("<Button-4>",   self._on_mousewheel)
                txt.bind("<Button-5>",   self._on_mousewheel)

            else:
                # ── Plain text ────────────────────────────────────────────────
                if part.strip():
                    lbl = tk.Label(bubble, text=part, bg=_AI_BG, fg=_AI_FG,
                                   font=("Segoe UI", 10), wraplength=500,
                                   justify="left", anchor="nw")
                    lbl.pack(fill="x", anchor="w")
                    lbl.bind("<MouseWheel>", self._on_mousewheel)
                    lbl.bind("<Button-4>",   self._on_mousewheel)
                    lbl.bind("<Button-5>",   self._on_mousewheel)

    def _append_system(self, text: str, color: str = _DIM) -> None:
        self._add_spacer(8)
        f = tk.Frame(self._msg_inner, bg=_MSG_BG, padx=12, pady=8)
        f.pack(fill="x", padx=10)
        tk.Label(f, text=text, bg=_MSG_BG, fg=color,
                 font=("Segoe UI", 9), wraplength=400,
                 justify="left", anchor="nw").pack(anchor="w")
        self._bind_scroll_recursive(f)
        self._scroll_bottom()

    def _add_spacer(self, h: int) -> None:
        tk.Frame(self._msg_inner, bg=_BG, height=h).pack(fill="x")

    def _bind_scroll_recursive(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>",   self._on_mousewheel, add="+")
        widget.bind("<Button-5>",   self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_scroll_recursive(child)

    def apply_theme(self, bg: str, fg: str, _select_bg: str) -> None:
        pass
