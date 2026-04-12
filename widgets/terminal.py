"""TerminalPanel — full PTY terminal with pyte VT100 screen buffer.

Cross-platform PTY support:
  - Windows:     pywinpty  (pip install pywinpty)
  - Linux/macOS: ptyprocess (pip install ptyprocess)

pyte maintains a proper 2D character grid so zsh completions, vim, htop,
and any TUI app render correctly on all platforms.
"""
from __future__ import annotations

import os
import platform
import queue
import shutil
import threading
import tkinter as tk
from tkinter import StringVar, ttk
from typing import Optional

import pyte

PTY_AVAILABLE = False
_pty_spawn = None   # callable(cmd, dimensions, env) → pty object

if platform.system() == "Windows":
    try:
        from winpty import PtyProcess as _WinPty
        def _pty_spawn(cmd, dimensions, env):
            return _WinPty.spawn(cmd, dimensions=dimensions, env=env)
        PTY_AVAILABLE = True
    except ImportError:
        pass
else:
    try:
        from ptyprocess import PtyProcessUnicode as _UnixPty
        def _pty_spawn(cmd, dimensions, env):
            return _UnixPty.spawn(cmd, dimensions=dimensions, env=env)
        PTY_AVAILABLE = True
    except ImportError:
        pass


def _default_shell() -> list[str]:
    system = platform.system()
    if system == "Windows":
        for shell in ("pwsh.exe", "powershell.exe", "cmd.exe"):
            if shutil.which(shell):
                return [shell]
        return ["cmd.exe"]
    else:
        shell = os.environ.get("SHELL", "")
        if shell and shutil.which(shell):
            return [shell]
        for sh in ("bash", "zsh", "sh"):
            path = shutil.which(sh)
            if path:
                return [path]
        return ["sh"]


# ── Colour helpers ─────────────────────────────────────────────────────────────

# pyte default 8-colour palette (used when colour is an int 0-7 / 8-15)
_PALETTE = {
    "black":   "#1e1e1e",
    "red":     "#ff5555",
    "green":   "#50fa7b",
    "brown":   "#f1fa8c",   # pyte calls yellow "brown"
    "blue":    "#6272a4",
    "magenta": "#ff79c6",
    "cyan":    "#8be9fd",
    "white":   "#f8f8f2",
}

_PALETTE_BRIGHT = {
    "black":   "#44475a",
    "red":     "#ff6e6e",
    "green":   "#69ff94",
    "brown":   "#ffffa5",
    "blue":    "#d6acff",
    "magenta": "#ff92df",
    "cyan":    "#a4ffff",
    "white":   "#ffffff",
}

_DEFAULT_FG = "#f8f8f2"
_DEFAULT_BG = "#1e1e1e"


def _resolve_color(color, default: str, bright: bool = False) -> str:
    """Convert a pyte colour value to a hex string."""
    if color == "default" or color is None:
        return default
    if isinstance(color, str) and color.startswith("#"):
        return color
    if isinstance(color, int):
        # 256-colour palette — approximate with 6x6x6 cube for > 15
        if color < 8:
            palette = _PALETTE_BRIGHT if bright else _PALETTE
            names = list(_PALETTE.keys())
            return palette.get(names[color], default)
        elif color < 16:
            names = list(_PALETTE.keys())
            return _PALETTE_BRIGHT.get(names[color - 8], default)
        elif color < 232:
            # 6x6x6 colour cube
            color -= 16
            b = color % 6
            g = (color // 6) % 6
            r = color // 36
            to_hex = lambda v: 0 if v == 0 else (55 + v * 40)
            return f"#{to_hex(r):02x}{to_hex(g):02x}{to_hex(b):02x}"
        else:
            # Greyscale ramp
            v = 8 + (color - 232) * 10
            return f"#{v:02x}{v:02x}{v:02x}"
    if isinstance(color, str):
        return _PALETTE.get(color, default)
    return default


def _cell_tag(char) -> tuple[str, str, bool]:
    """Return (fg_hex, bg_hex, bold) for a pyte Char."""
    bold   = char.bold
    fg_hex = _resolve_color(char.fg, _DEFAULT_FG, bright=bold)
    bg_hex = _resolve_color(char.bg, _DEFAULT_BG)
    return fg_hex, bg_hex, bold


class TerminalPanel(ttk.Frame):
    """Interactive PTY terminal using pyte for VT100 screen buffer."""

    SHELLS = {
        "Auto":        None,
        "PowerShell":  ["powershell.exe"],
        "CMD":         ["cmd.exe"],
        "Bash":        ["bash"],
        "Zsh":         ["zsh"],
        "Python REPL": ["python"],
    }

    _KEY_MAP = {
        "Up":    "\x1b[A",
        "Down":  "\x1b[B",
        "Right": "\x1b[C",
        "Left":  "\x1b[D",
        "Home":  "\x1b[H",
        "End":   "\x1b[F",
        "Prior": "\x1b[5~",
        "Next":  "\x1b[6~",
        "Delete":"\x1b[3~",
        "F1":  "\x1bOP",   "F2":  "\x1bOQ",  "F3":  "\x1bOR",  "F4":  "\x1bOS",
        "F5":  "\x1b[15~", "F6":  "\x1b[17~","F7":  "\x1b[18~","F8":  "\x1b[19~",
        "F9":  "\x1b[20~", "F10": "\x1b[21~","F11": "\x1b[23~","F12": "\x1b[24~",
    }

    # How many rows of scrollback to keep above the live screen
    _SCROLLBACK = 500

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._pty:      object = None
        self._queue:    queue.Queue = queue.Queue()
        self._shell_var = StringVar(value="Auto")
        self._running   = False
        self._cwd: Optional[str] = None

        # pyte screen — sized properly once the widget is mapped
        self._rows = 24
        self._cols = 80
        self._screen = pyte.HistoryScreen(self._cols, self._rows, history=self._SCROLLBACK)
        self._stream = pyte.ByteStream(self._screen)

        # Scrollback: list of rendered line strings + their tag maps
        # Each entry: list of (text, fg, bg, bold) segments for one row
        self._scrollback: list[list] = []

        # Tag cache: (fg, bg, bold) → tag name
        self._tag_cache: dict[tuple, str] = {}
        self._tag_count = 0

        self._resize_job = None

        self._build_ui()
        self._poll()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, shell: list[str] | None = None,
              cwd: str | None = None) -> None:
        if cwd is not None:
            self._cwd = cwd
        self.stop()
        if not PTY_AVAILABLE:
            self._write_error("PTY library not found.\n")
            if platform.system() == "Windows":
                self._write_error("Run: pip install pywinpty\n")
            else:
                self._write_error("Run: pip install ptyprocess\n")
            return

        cmd = shell or _default_shell()
        try:
            env = os.environ.copy()
            env["TERM"]           = "xterm-256color"
            env["COLORTERM"]      = "truecolor"
            env["IDOL_TERMINAL"]  = "1"   # lets users detect our terminal in .zshrc
            self._scrollback.clear()
            self._screen = pyte.HistoryScreen(self._cols, self._rows, history=self._SCROLLBACK)
            self._stream = pyte.ByteStream(self._screen)
            self._pty = _pty_spawn(cmd, dimensions=(self._rows, self._cols), env=env)
            self._running = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            self._text.focus_set()
            _cwd = self._cwd
            if _cwd and os.path.isdir(_cwd):
                self.after(300, lambda c=_cwd: self.send_text(f'cd "{c}"\r'))
        except Exception as e:
            self._write_error(f"Failed to start shell: {e}\n")

    def send_text(self, text: str) -> None:
        if self._pty and self._running:
            try:
                self._pty.write(text)
            except Exception:
                pass

    def stop(self) -> None:
        self._running = False
        if self._pty:
            try:
                if self._pty.isalive():
                    self._pty.terminate(force=True)
            except Exception:
                pass
        self._pty = None

    def send(self, text: str) -> None:
        if self._pty and self._running:
            try:
                self._pty.write(text)
            except Exception:
                pass

    def resize(self, rows: int, cols: int) -> None:
        if rows == self._rows and cols == self._cols:
            return
        self._rows = rows
        self._cols = cols
        self._screen.resize(rows, cols)
        if self._pty and self._running:
            try:
                self._pty.setwinsize(rows, cols)
            except Exception:
                pass

    def clear(self) -> None:
        self._scrollback.clear()
        self._screen = pyte.HistoryScreen(self._cols, self._rows, history=self._SCROLLBACK)
        self._stream = pyte.ByteStream(self._screen)
        self._redraw_full()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", side="top", pady=(2, 0), padx=4)

        ttk.Label(toolbar, text="TERMINAL",
                  font=("TkDefaultFont", 8, "bold")).pack(side="left", padx=(0, 8))

        self._shell_cb = ttk.Combobox(
            toolbar, textvariable=self._shell_var,
            values=list(self.SHELLS.keys()), width=12, state="readonly",
        )
        self._shell_cb.pack(side="left", padx=2)
        self._shell_cb.bind("<<ComboboxSelected>>", self._on_shell_change)

        ttk.Button(toolbar, text="⟳ Restart", width=9,
                   command=self._on_restart).pack(side="left", padx=2)
        ttk.Button(toolbar, text="✕ Clear", width=8,
                   command=self.clear).pack(side="left", padx=2)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self._text = tk.Text(
            text_frame,
            bg=_DEFAULT_BG, fg=_DEFAULT_FG,
            font=("Consolas", 10),
            wrap="none",
            relief="flat", borderwidth=0,
            insertbackground=_DEFAULT_FG,
            cursor="xterm",
            takefocus=True,
            state="disabled",
        )
        vs = ttk.Scrollbar(text_frame, orient="vertical", command=self._on_scroll)
        self._scrollbar = vs
        self._text.configure(yscrollcommand=self._on_yscroll_update)
        self._text.grid(row=0, column=0, sticky="nswe")
        vs.grid(row=0, column=1, sticky="ns")

        # Preconfigure base tags
        self._text.tag_configure("plain", foreground=_DEFAULT_FG, background=_DEFAULT_BG)
        self._text.tag_configure("error", foreground="#ff5555")
        self._text.tag_configure("cursor_block",
                                 background=_DEFAULT_FG, foreground=_DEFAULT_BG)

        # Remove default Text bindings — we handle everything ourselves
        self._text.bindtags((str(self._text), '.', 'all'))

        self._text.bind("<ButtonPress-1>", lambda _: self._text.focus_set())
        self._text.bind("<Key>",           self._on_key)
        self._text.bind("<Return>",        lambda _: (self.send("\r"),   "break")[1])
        self._text.bind("<BackSpace>",     lambda _: (self.send("\x7f"), "break")[1])
        self._text.bind("<Tab>",           lambda _: (self.send("\t"),   "break")[1])
        self._text.bind("<Escape>",        lambda _: (self.send("\x1b"), "break")[1])
        self._text.bind("<Control-c>",     lambda _: (self.send("\x03"), "break")[1])
        self._text.bind("<Control-d>",     lambda _: (self.send("\x04"), "break")[1])
        self._text.bind("<Control-z>",     lambda _: (self.send("\x1a"), "break")[1])
        self._text.bind("<Control-l>",     lambda _: (self.send("\x0c"), "break")[1])
        self._text.bind("<Control-a>",     lambda _: (self.send("\x01"), "break")[1])
        self._text.bind("<Control-e>",     lambda _: (self.send("\x05"), "break")[1])
        self._text.bind("<Control-u>",     lambda _: (self.send("\x15"), "break")[1])
        self._text.bind("<Control-k>",     lambda _: (self.send("\x0b"), "break")[1])
        self._text.bind("<Control-w>",     lambda _: (self.send("\x17"), "break")[1])
        self._text.bind("<Control-r>",     lambda _: (self.send("\x12"), "break")[1])
        self._text.bind("<<Paste>>",       self._on_paste)
        self._text.bind("<Configure>",     self._on_resize)

        for keysym, seq in self._KEY_MAP.items():
            self._text.bind(f"<{keysym}>",
                            lambda _, s=seq: (self.send(s), "break")[1])

    # ── Scrollback / scroll handling ──────────────────────────────────────────

    def _on_scroll(self, *args) -> None:
        """Scrollbar drag — scroll through combined scrollback + screen view."""
        self._text.yview(*args)

    def _on_yscroll_update(self, first: str, last: str) -> None:
        self._scrollbar.set(first, last)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _get_tag(self, fg: str, bg: str, bold: bool) -> str:
        """Return (creating if needed) a tk tag for this fg/bg/bold combo."""
        key = (fg, bg, bold)
        if key in self._tag_cache:
            return self._tag_cache[key]
        self._tag_count += 1
        name = f"t{self._tag_count}"
        opts: dict = {"foreground": fg, "background": bg}
        if bold:
            opts["font"] = ("Consolas", 10, "bold")
        self._text.tag_configure(name, **opts)
        self._tag_cache[key] = name
        return name

    def _screen_to_lines(self) -> list[list]:
        """Convert current pyte screen to a list of segment lists."""
        lines = []
        for row_idx in range(self._screen.lines):
            row = self._screen.buffer[row_idx]
            segments = []
            run_text = ""
            run_fg = _DEFAULT_FG
            run_bg = _DEFAULT_BG
            run_bold = False
            for col_idx in range(self._screen.columns):
                char = row[col_idx]
                fg, bg, bold = _cell_tag(char)
                ch = char.data if char.data else " "
                if fg == run_fg and bg == run_bg and bold == run_bold:
                    run_text += ch
                else:
                    if run_text:
                        segments.append((run_text, run_fg, run_bg, run_bold))
                    run_text = ch
                    run_fg, run_bg, run_bold = fg, bg, bold
            if run_text:
                segments.append((run_text, run_fg, run_bg, run_bold))
            lines.append(segments)
        return lines

    def _redraw_full(self) -> None:
        """Redraw the entire text widget from scrollback + current screen."""
        self._text.config(state="normal")
        self._text.delete("1.0", "end")

        # Scrollback lines
        for seg_list in self._scrollback:
            for text, fg, bg, bold in seg_list:
                tag = self._get_tag(fg, bg, bold)
                self._text.insert("end", text, tag)
            self._text.insert("end", "\n", "plain")

        # Live screen rows
        screen_lines = self._screen_to_lines()
        cursor_row = self._screen.cursor.y
        cursor_col = self._screen.cursor.x

        for row_idx, seg_list in enumerate(screen_lines):
            col = 0
            for text, fg, bg, bold in seg_list:
                # Insert cursor block on the cursor cell
                if row_idx == cursor_row:
                    for ci, ch in enumerate(text):
                        if col + ci == cursor_col:
                            self._text.insert("end", ch, "cursor_block")
                        else:
                            tag = self._get_tag(fg, bg, bold)
                            self._text.insert("end", ch, tag)
                    col += len(text)
                else:
                    tag = self._get_tag(fg, bg, bold)
                    self._text.insert("end", text, tag)
            if row_idx < len(screen_lines) - 1:
                self._text.insert("end", "\n", "plain")

        self._text.config(state="disabled")
        self._text.see("end")

    def _flush_scrollback(self) -> None:
        """Move lines that scrolled off the top of the screen into scrollback."""
        history = self._screen.history
        # pyte stores scrolled-off lines in screen.history.top (a deque)
        while self._screen.history.top:
            row = self._screen.history.top.popleft()
            segments = []
            run_text = ""
            run_fg = _DEFAULT_FG
            run_bg = _DEFAULT_BG
            run_bold = False
            for col_idx in range(self._screen.columns):
                char = row[col_idx]
                fg, bg, bold = _cell_tag(char)
                ch = char.data if char.data else " "
                if fg == run_fg and bg == run_bg and bold == run_bold:
                    run_text += ch
                else:
                    if run_text:
                        segments.append((run_text, run_fg, run_bg, run_bold))
                    run_text = ch
                    run_fg, run_bg, run_bold = fg, bg, bold
            if run_text:
                segments.append((run_text, run_fg, run_bg, run_bold))
            self._scrollback.append(segments)

        # Cap scrollback length
        if len(self._scrollback) > self._SCROLLBACK:
            self._scrollback = self._scrollback[-self._SCROLLBACK:]

    # ── PTY I/O ───────────────────────────────────────────────────────────────

    def _read_loop(self) -> None:
        while self._running and self._pty and self._pty.isalive():
            try:
                chunk = self._pty.read(4096)
                if chunk:
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8", errors="replace")
                    self._queue.put(chunk)
            except EOFError:
                break
            except Exception:
                break
        self._queue.put(None)

    def _poll(self) -> None:
        chunks = []
        sentinel = False
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    sentinel = True
                    break
                chunks.append(item)
        except queue.Empty:
            pass

        if chunks:
            # Feed all bytes through pyte
            for chunk in chunks:
                self._stream.feed(chunk)
            self._flush_scrollback()
            self._redraw_full()

        if sentinel:
            self._running = False
            self._text.config(state="normal")
            self._text.insert("end", "\n[Process exited]\n", "plain")
            self._text.config(state="disabled")
            self._text.see("end")

        self.after(30, self._poll)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_key(self, event) -> str:
        char = event.char
        if char and char not in ("\r", "\n", "\x08"):
            self.send(char)
        return "break"

    def _on_paste(self, _=None) -> str:
        try:
            text = self._text.clipboard_get()
            if text:
                self.send(text)
        except Exception:
            pass
        return "break"

    def _on_restart(self) -> None:
        cmd = self.SHELLS.get(self._shell_var.get())
        self.start(cmd, cwd=self._cwd)

    def _on_shell_change(self, _=None) -> None:
        cmd = self.SHELLS.get(self._shell_var.get())
        self.start(cmd, cwd=self._cwd)

    def _on_resize(self, _=None) -> None:
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(50, self._do_resize)

    def _do_resize(self) -> None:
        self._resize_job = None
        try:
            font_w = self._text.tk.call("font", "measure",
                                        str(self._text.cget("font")), "0")
            font_h = self._text.tk.call("font", "metrics",
                                        str(self._text.cget("font")), "-linespace")
            w = self._text.winfo_width()
            h = self._text.winfo_height()
            if w > 0 and h > 0 and font_w > 0 and font_h > 0:
                cols = max(10, w  // font_w)
                rows = max(5,  h  // font_h)
                self.resize(rows, cols)
        except Exception:
            pass

    def _write_error(self, text: str) -> None:
        self._text.config(state="normal")
        self._text.insert("end", text, "error")
        self._text.config(state="disabled")
        self._text.see("end")
