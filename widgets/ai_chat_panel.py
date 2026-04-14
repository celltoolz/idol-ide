"""AI Chat panel — conversational interface to local Ollama LLM."""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
from typing import Callable

from utils import ollama_client
from utils import settings as idol_settings
from utils.learning_registry import LearningManager

_HISTORY_FILE = Path.home() / ".idol" / "ai_history.json"
_HISTORY_CAP  = 20   # max messages restored from disk


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
        self._ai_introduced    = idol_settings.get("ai_introduced", False)
        self._current_ai_label: tk.Frame | None = None
        self._scroll_job = None
        self._render_job = None
        self._pending_render_text: str = ""

        self._build()
        try:
            import requests  # noqa: F401
            ollama_client.check_async(self._on_ollama_status)
        except ImportError:
            self.after(100, self._show_requests_missing)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Left border — visually separates panel from the editor
        tk.Frame(self, bg=_BORDER, width=1).pack(side="left", fill="y")

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
        # Bottom spacer — always packed last so the user can scroll the final
        # message up away from the input box rather than it sitting flush.
        self._msg_bottom_spacer = tk.Frame(self._msg_inner, bg=_BG, height=10)
        self._msg_bottom_spacer.pack(fill="x", side="bottom")
        self._msg_inner.bind("<Configure>", self._on_inner_configure)
        # Registry of wrapping Labels — updated whenever the canvas resizes.
        self._wrap_labels: list = []
        self._canvas.bind("<Configure>",    self._on_canvas_configure)

        # Linux / macOS: direct per-widget bindings work fine
        for w in (self._canvas, self._msg_inner):
            w.bind("<Button-4>", self._on_mousewheel, add="+")
            w.bind("<Button-5>", self._on_mousewheel, add="+")

        # Windows: <MouseWheel> fires on the *focused* widget, not the one
        # under the cursor.  Grab all mousewheel events while the cursor is
        # inside this panel, release them when it leaves.
        self.bind("<Enter>", self._grab_scroll,    add="+")
        self.bind("<Leave>", self._release_scroll, add="+")

        # ── Separator ─────────────────────────────────────────────────────────
        tk.Frame(self, bg=_BORDER, height=1).pack(fill="x")

        # ── Input area ────────────────────────────────────────────────────────
        tk.Frame(self, bg="#3c3c3c", height=1).pack(fill="x", side="bottom")
        input_outer = tk.Frame(self, bg=_INPUT_BG)
        input_outer.pack(fill="x", side="bottom")

        # URL row — created before ctx_row so its natural pack position is above it.
        # We use pack/pack_forget on the row itself; tkinter always restores it to
        # its creation-order slot when re-packed inside the same parent.
        self._url_row = tk.Frame(input_outer, bg=_INPUT_BG)
        tk.Label(self._url_row, text="Ollama URL:", bg=_INPUT_BG, fg=_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 4), pady=4)
        self._url_var = tk.StringVar(value=ollama_client.get_base_url())
        url_entry = tk.Entry(self._url_row, textvariable=self._url_var,
                             bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                             font=("Segoe UI", 9), relief="flat", bd=0,
                             highlightthickness=1, highlightbackground=_BORDER,
                             highlightcolor=_BTN_BG)
        url_entry.pack(side="left", fill="x", expand=True, ipady=2)
        url_entry.bind("<Return>", lambda _: self._apply_url())
        self._apply_btn = self._make_ctx_btn(self._url_row, "Apply", self._apply_url)
        self._apply_btn.pack(side="left", padx=(4, 8))
        self._url_status = tk.Label(self._url_row, text="", bg=_INPUT_BG, fg=_DIM,
                                    font=("Segoe UI", 8))
        self._url_status.pack(side="left")
        self._url_row_visible = False

        # Context buttons row — ⚙ Clear Load Save only
        ctx_row = tk.Frame(input_outer, bg=_INPUT_BG)
        self._ctx_row = ctx_row
        ctx_row.pack(fill="x", padx=8, pady=(6, 0))

        self._save_btn     = self._make_ctx_btn(ctx_row, "💾 Save",  self._save_conversation)
        self._load_btn     = self._make_ctx_btn(ctx_row, "📂 Load",  self._load_conversation)
        self._clear_btn    = self._make_ctx_btn(ctx_row, "🗑 Clear", self._clear_conversation)
        self._settings_btn = self._make_ctx_btn(ctx_row, "⚙",       self._toggle_url_row)
        self._save_btn.pack(side="right")
        self._load_btn.pack(side="right", padx=(0, 4))
        self._clear_btn.pack(side="right", padx=(0, 4))
        self._settings_btn.pack(side="right", padx=(0, 4))

        # Text input + send button
        input_row = tk.Frame(input_outer, bg=_INPUT_BG)
        input_row.pack(fill="x", padx=8, pady=(4, 4))

        # Pack send_btn BEFORE the text widget so expand=True doesn't steal its space
        send_btn = tk.Label(input_row, text="↑", bg=_SEND_BG, fg="white",
                            font=("Segoe UI", 14, "bold"),
                            cursor="hand2", width=2, pady=4)
        send_btn.pack(side="right", padx=(6, 0), fill="y")
        send_btn.bind("<Button-1>", lambda _: self._send())
        send_btn.bind("<Enter>",    lambda _: send_btn.config(bg=_BTN_ACT))
        send_btn.bind("<Leave>",    lambda _: send_btn.config(bg=_SEND_BG))

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

        # Bottom row: Send File + Selection on left, ctx label + tokens on right
        bottom_row = tk.Frame(input_outer, bg=_INPUT_BG)
        bottom_row.pack(fill="x", padx=8, pady=(0, 8))

        self._file_btn = self._make_ctx_btn(bottom_row, "📄 Send File", self._attach_file)
        self._file_btn.pack(side="left", padx=(0, 4))
        self._sel_btn  = self._make_ctx_btn(bottom_row, "✂ Selection", self._attach_selection)
        self._sel_btn.pack(side="left")

        self._ctx_label = tk.Label(bottom_row, text="", bg=_INPUT_BG, fg=_DIM,
                                   font=("Segoe UI", 8), anchor="w")
        self._ctx_label.pack(side="left", padx=(8, 0))

        self._token_label = tk.Label(bottom_row, text="", bg=_INPUT_BG, fg=_DIM,
                                     font=("Segoe UI", 7), anchor="e")
        self._token_label.pack(side="right")

        self._pending_ctx: str = ""   # attached code context

        # Register AI panel controls with Learning Mode
        LearningManager.register(self._settings_btn,  "ai_settings_btn")
        LearningManager.register(self._clear_btn,     "ai_clear_btn")
        LearningManager.register(self._load_btn,      "ai_load_btn")
        LearningManager.register(self._save_btn,      "ai_save_btn")
        LearningManager.register(self._file_btn,      "ai_send_file_btn")
        LearningManager.register(self._sel_btn,       "ai_selection_btn")
        LearningManager.register(self._token_label,   "ai_token_label")

        # Auto-load persisted history; fall back to welcome message
        if not self._auto_load_history():
            self._show_welcome()

    # ── Canvas helpers ────────────────────────────────────────────────────────

    def _on_inner_configure(self, _=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._msg_win, width=event.width)
        wl = max(80, event.width - 60)
        for lbl in self._wrap_labels:
            try:
                lbl.config(wraplength=wl)
            except Exception:
                pass

    def _grab_scroll(self, event=None) -> None:
        """Bind all mousewheel events to this panel (Windows focus workaround)."""
        try:
            self.winfo_toplevel().bind_all("<MouseWheel>", self._on_mousewheel)
        except Exception:
            pass

    def _release_scroll(self, event) -> None:
        """Unbind global mousewheel only when the cursor truly leaves the panel."""
        try:
            # winfo_containing gives us the widget now under the cursor.
            # Walk its parent chain — if we find self, still inside the panel.
            w = self.winfo_containing(event.x_root, event.y_root)
            while w:
                if w is self:
                    return          # still inside — keep the grab
                try:
                    w = w.master
                except Exception:
                    break
            self.winfo_toplevel().unbind_all("<MouseWheel>")
        except Exception:
            pass

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

    def _toggle_url_row(self) -> None:
        if self._url_row_visible:
            self._url_row.pack_forget()
            self._url_row_visible = False
        else:
            self._url_row.pack(fill="x", before=self._ctx_row)
            self._url_row_visible = True

    def _apply_url(self) -> None:
        url = self._url_var.get().strip()
        if not url:
            return
        ollama_client.set_base_url(url)
        self._url_status.config(text="Connecting…", fg=_DIM)
        def _after_check(available: bool) -> None:
            self._ai_available = available
            if available:
                self.after(0, self._clear_offline_cards)
                self.after(0, lambda: self._url_status.config(text="Connected", fg="#50fa7b"))
            else:
                self.after(0, self._show_offline_card)
                self.after(0, lambda: self._url_status.config(text="Not reachable", fg=_WARN_FG))
        ollama_client.check_async(_after_check)

    def _clear_offline_cards(self) -> None:
        """Remove all offline-card frames (and their preceding spacers) from the chat."""
        children = list(self._msg_inner.winfo_children())
        for i, widget in enumerate(children):
            if getattr(widget, "_is_offline_card", False):
                # destroy the spacer that precedes it, if any
                if i > 0:
                    try:
                        children[i - 1].destroy()
                    except Exception:
                        pass
                try:
                    widget.destroy()
                except Exception:
                    pass

    def _on_ollama_status(self, available: bool) -> None:
        self._ai_available = available
        if not available:
            try:
                self.after(0, self._show_offline_card)
            except Exception:
                pass

    def _show_requests_missing(self) -> None:
        self._add_spacer(8)
        f = tk.Frame(self._msg_inner, bg=_MSG_BG, padx=12, pady=8)
        f._is_offline_card = True
        f.pack(fill="x", padx=10)
        lbl = tk.Label(f, text="Missing dependency: requests\n\nRun this in your terminal:\n  pip install requests\n\nThen restart IDOL.",
                       bg=_MSG_BG, fg=_WARN_FG, font=("Segoe UI", 9),
                       wraplength=400, justify="left", anchor="nw")
        lbl.pack(anchor="w")
        self._wrap_labels.append(lbl)
        self._bind_scroll_recursive(f)
        self._scroll_bottom()

    def _show_offline_card(self) -> None:
        # Don't add another card if one is already visible
        for w in self._msg_inner.winfo_children():
            if getattr(w, "_is_offline_card", False):
                return
        import sys
        if sys.platform == "win32":
            install_cmd = "irm https://ollama.com/install.ps1 | iex"
            shell_note  = "PowerShell"
        else:
            install_cmd = "curl -fsSL https://ollama.com/install.sh | sh"
            shell_note  = "Terminal"

        self._add_spacer(8)
        f = tk.Frame(self._msg_inner, bg=_MSG_BG, padx=12, pady=8)
        f._is_offline_card = True
        f.pack(fill="x", padx=10)
        lbl = tk.Label(f,
                 text=(f"Local AI (Ollama) is not running.\n\n"
                       f"Step 1 — Install Ollama (run in {shell_note}):\n"
                       f"  {install_cmd}\n\n"
                       f"Step 2 — Install the AI model (~4GB):\n"
                       f"  ollama pull qwen2.5-coder\n\n"
                       f"Then reopen this tab."),
                 bg=_MSG_BG, fg=_WARN_FG,
                 font=("Segoe UI", 9), wraplength=400,
                 justify="left", anchor="nw")
        lbl.pack(anchor="w")
        self._wrap_labels.append(lbl)
        self._bind_scroll_recursive(f)
        self._scroll_bottom()

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

    # ── Persist conversation ──────────────────────────────────────────────────

    def _auto_load_history(self) -> bool:
        """Load the last _HISTORY_CAP messages from disk. Returns True if loaded."""
        try:
            if not _HISTORY_FILE.exists():
                return False
            data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, list) or not data:
                return False
            # Cap to last N messages
            data = data[-_HISTORY_CAP:]
            for msg in data:
                role    = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    display = content.split("\n\n")[-1] if "\n\n# " in content else content
                    self._append_user(display)
                elif role == "assistant":
                    bubble = self._append_ai_bubble()
                    self._current_ai_label = bubble
                    self._update_ai_bubble(content)
                self._history.append(msg)
            self._current_ai_label = None
            self._update_token_label()
            n = len(data)
            self._append_system(f"Last {n} message{'s' if n != 1 else ''} restored from previous session.")
            return True
        except Exception:
            return False

    def auto_save_history(self) -> None:
        """Persist current history to disk — called by the app on exit."""
        try:
            if not self._history:
                return
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            _HISTORY_FILE.write_text(
                json.dumps(self._history, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _clear_conversation(self) -> None:
        """Wipe conversation history from UI, memory, and disk."""
        if self._generating:
            return
        if self._history:
            if not messagebox.askyesno("Clear Conversation",
                                       "Clear the entire conversation history?"):
                return
        for w in self._msg_inner.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self._history = []
        self._current_ai_label = None
        self._update_token_label()
        try:
            if _HISTORY_FILE.exists():
                _HISTORY_FILE.unlink()
        except Exception:
            pass
        self._show_welcome()

    # ── Save / Load conversation ──────────────────────────────────────────────

    def _save_conversation(self) -> None:
        if not self._history:
            messagebox.showinfo("Save Conversation", "Nothing to save — conversation is empty.")
            return
        path = filedialog.asksaveasfilename(
            title="Save Conversation",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2, ensure_ascii=False)
            self._append_system(f"Conversation saved to {path}")
        except Exception as exc:
            messagebox.showerror("Save Failed", str(exc))

    def _load_conversation(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Conversation",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            messagebox.showerror("Load Failed", str(exc))
            return

        if not isinstance(data, list):
            messagebox.showerror("Load Failed", "Invalid conversation file.")
            return

        if self._history:
            if not messagebox.askyesno(
                "Load Conversation",
                "Loading will clear the current conversation. Continue?",
            ):
                return

        # Clear UI
        for w in self._msg_inner.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self._history = []
        self._current_ai_label = None

        # Replay history into the UI
        for msg in data:
            role    = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                # Show only the user-typed portion (strip attached context block)
                display = content.split("\n\n")[-1] if "\n\n# " not in content else content.split("\n\n")[-1]
                self._append_user(display)
            elif role == "assistant":
                bubble = self._append_ai_bubble()
                self._current_ai_label = bubble
                self._update_ai_bubble(content)
            self._history.append(msg)

        self._current_ai_label = None
        self._update_token_label()
        self._append_system(f"Conversation loaded from {path}")

    # ── Send ──────────────────────────────────────────────────────────────────

    def _on_return(self, event) -> str:
        self._send()
        return "break"

    def _on_shift_return(self, event) -> None:
        pass   # let default newline insertion happen

    def send_prefilled(self, text: str) -> None:
        """Open the AI chat (if hidden) and send a pre-built prompt directly."""
        self._input.delete("1.0", "end")
        self._input.insert("1.0", text)
        self._send()

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
        self._update_token_label()

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
            try:
                self.after(0, self._update_token_label)
            except Exception:
                pass
            # Final render — cancel any pending debounce and render immediately
            try:
                self.after(0, lambda: (
                    self._cancel_render_job(),
                    self._update_ai_bubble(full),
                    self._scroll_bottom(),
                ))
            except Exception:
                pass
            # First successful response — trigger Qwen's one-time intro after a pause
            if not self._ai_introduced:
                try:
                    self.after(600, self._trigger_intro)
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

    def _update_token_label(self) -> None:
        """Show an approximate token count for the current conversation."""
        # Rough estimate: 1 token ≈ 4 chars.  qwen2.5-coder context ≈ 32k tokens.
        _CONTEXT_TOKENS = 32_000
        total_chars = sum(len(m.get("content", "")) for m in self._history)
        tokens = total_chars // 4
        pct = min(100, int(tokens * 100 / _CONTEXT_TOKENS))
        color = _DIM if pct < 70 else (_WARN_FG if pct < 90 else "#f44747")
        try:
            self._token_label.config(
                text=f"~{tokens:,} / {_CONTEXT_TOKENS:,} tokens  ({pct}%)",
                fg=color,
            )
        except Exception:
            pass

    def _trigger_intro(self) -> None:
        """Send a hidden one-shot intro prompt so Qwen introduces herself."""
        if self._generating or self._ai_introduced:
            return
        if not self._ai_available:
            return

        self._ai_introduced = True
        idol_settings.set("ai_introduced", True)

        self._generating = True
        self._current_ai_label = self._append_ai_bubble()

        _INTRO_PROMPT = (
            "You are Qwen, a friendly AI assistant built into IDOL "
            "(Integrated Development and Objective Learning), a Python IDE for beginners. "
            "Introduce yourself in 2-3 short sentences. "
            "Mention that you can help users learn Python, understand their code, and answer questions "
            "— all without leaving the IDE. Be warm and encouraging. "
            "Do not use markdown headers, bullet lists, or code blocks."
        )

        accumulated: list[str] = []

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
            try:
                self.after(0, lambda: (
                    self._cancel_render_job(),
                    self._update_ai_bubble(full),
                    self._scroll_bottom(),
                ))
                self.after(0, self._update_token_label)
            except Exception:
                pass

        def _on_error(_: str) -> None:
            self._generating = False

        ollama_client.generate(
            _INTRO_PROMPT,
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
        lbl = tk.Label(bubble, text=text, bg=_USER_BG, fg=_USER_FG,
                       font=("Segoe UI", 10), wraplength=380,
                       justify="left", anchor="nw")
        lbl.pack(anchor="w")
        self._wrap_labels.append(lbl)
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
        stream_txt.bind("<Button-4>", self._on_mousewheel)
        stream_txt.bind("<Button-5>", self._on_mousewheel)
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
                txt.bind("<Button-4>", self._on_mousewheel)
                txt.bind("<Button-5>", self._on_mousewheel)

            else:
                # ── Plain text ────────────────────────────────────────────────
                if part.strip():
                    lbl = tk.Label(bubble, text=part, bg=_AI_BG, fg=_AI_FG,
                                   font=("Segoe UI", 10), wraplength=500,
                                   justify="left", anchor="nw")
                    lbl.pack(fill="x", anchor="w")
                    lbl.bind("<Button-4>", self._on_mousewheel)
                    lbl.bind("<Button-5>", self._on_mousewheel)
                    self._wrap_labels.append(lbl)

    def _append_system(self, text: str, color: str = _DIM) -> None:
        self._add_spacer(8)
        f = tk.Frame(self._msg_inner, bg=_MSG_BG, padx=12, pady=8)
        f.pack(fill="x", padx=10)
        lbl = tk.Label(f, text=text, bg=_MSG_BG, fg=color,
                       font=("Segoe UI", 9), wraplength=400,
                       justify="left", anchor="nw")
        lbl.pack(anchor="w")
        self._wrap_labels.append(lbl)
        self._bind_scroll_recursive(f)
        self._scroll_bottom()

    def _add_spacer(self, h: int) -> None:
        tk.Frame(self._msg_inner, bg=_BG, height=h).pack(fill="x")

    def _bind_scroll_recursive(self, widget) -> None:
        # Windows: covered by bind_all in _grab_scroll.
        # Linux / macOS: bind Button-4 / Button-5 on each child.
        widget.bind("<Button-4>", self._on_mousewheel, add="+")
        widget.bind("<Button-5>", self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_scroll_recursive(child)

    def apply_theme(self, bg: str, fg: str, _select_bg: str) -> None:
        pass
