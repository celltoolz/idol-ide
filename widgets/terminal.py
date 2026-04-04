"""TerminalPanel — a full interactive PTY terminal embedded in the editor.

Cross-platform PTY support:
  - Windows:     pywinpty  (pip install pywinpty)
  - Linux/macOS: ptyprocess (pip install ptyprocess)

Input is typed directly into the output area (VS Code style) — no separate
input bar. All keystrokes are forwarded to the PTY; the shell echoes them back.
"""
from __future__ import annotations

import os
import platform
import queue
import re
import shutil
import threading
from tkinter import StringVar, Text, ttk
from typing import Optional

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


# ── ANSI escape code parser ────────────────────────────────────────────────────

# Matches ESC [ ... sequences — params include ? for private modes like ESC[?1004h
_ANSI_RE = re.compile(r'\x1b\[([0-9;?<=>!]*)([A-Za-z@^`])')

# Map ANSI color index → hex (Dracula palette)
_ANSI_COLORS = {
    0:  "#1e1e1e",  # black
    1:  "#ff5555",  # red
    2:  "#50fa7b",  # green
    3:  "#f1fa8c",  # yellow
    4:  "#6272a4",  # blue
    5:  "#ff79c6",  # magenta
    6:  "#8be9fd",  # cyan
    7:  "#f8f8f2",  # white
    8:  "#44475a",  # bright black
    9:  "#ff6e6e",  # bright red
    10: "#69ff94",  # bright green
    11: "#ffffa5",  # bright yellow
    12: "#d6acff",  # bright blue
    13: "#ff92df",  # bright magenta
    14: "#a4ffff",  # bright cyan
    15: "#ffffff",  # bright white
}


def _default_shell() -> list[str]:
    """Return the best available shell command for the current platform."""
    system = platform.system()
    if system == "Windows":
        for shell in ("pwsh.exe", "powershell.exe", "cmd.exe"):
            if shutil.which(shell):
                return [shell]
        return ["cmd.exe"]
    else:
        shell = os.environ.get("SHELL", "")
        if not shell or not shutil.which(shell):
            for sh in ("bash", "zsh", "sh"):
                path = shutil.which(sh)
                if path:
                    return [path]
        return [shell]


class AnsiParser:
    """Stateful ANSI SGR parser — converts escape sequences to tag names."""

    def __init__(self) -> None:
        self._fg: Optional[str] = None
        self._bg: Optional[str] = None
        self._bold = False

    def reset(self) -> None:
        self._fg = None
        self._bg = None
        self._bold = False

    def process(self, codes: str) -> None:
        """Update internal state for a semicolon-separated list of SGR codes."""
        parts = [int(x) for x in codes.split(";") if x.isdigit()]
        if not parts:
            parts = [0]

        i = 0
        while i < len(parts):
            c = parts[i]
            if c == 0:
                self.reset()
            elif c == 1:
                self._bold = True
            elif c == 22:
                self._bold = False
            elif 30 <= c <= 37:
                self._fg = _ANSI_COLORS.get(c - 30, None)
            elif c == 39:
                self._fg = None
            elif 40 <= c <= 47:
                self._bg = _ANSI_COLORS.get(c - 40, None)
            elif c == 49:
                self._bg = None
            elif 90 <= c <= 97:
                self._fg = _ANSI_COLORS.get(c - 90 + 8, None)
            elif 100 <= c <= 107:
                self._bg = _ANSI_COLORS.get(c - 100 + 8, None)
            elif c == 38 and i + 2 < len(parts) and parts[i + 1] == 5:
                self._fg = _ANSI_COLORS.get(parts[i + 2], None)
                i += 2
            elif c == 48 and i + 2 < len(parts) and parts[i + 1] == 5:
                self._bg = _ANSI_COLORS.get(parts[i + 2], None)
                i += 2
            i += 1

    def tag(self) -> str:
        parts = []
        if self._fg:
            parts.append(f"fg_{self._fg.lstrip('#')}")
        if self._bg:
            parts.append(f"bg_{self._bg.lstrip('#')}")
        if self._bold:
            parts.append("bold")
        return "_".join(parts) if parts else "plain"

    def fg(self) -> Optional[str]:
        return self._fg

    def bg(self) -> Optional[str]:
        return self._bg

    def bold(self) -> bool:
        return self._bold


class TerminalPanel(ttk.Frame):
    """Interactive PTY terminal panel.

    Spawns a real shell in a pseudo-terminal. Output is rendered in a
    tk.Text widget with ANSI colour support. Typing goes directly into
    the output area — keystrokes are forwarded to the PTY (VS Code style).
    """

    SHELLS = {
        "Auto":        None,
        "PowerShell":  ["powershell.exe"],
        "CMD":         ["cmd.exe"],
        "Bash":        ["bash"],
        "Zsh":         ["zsh"],
        "Python REPL": ["python"],
    }

    # Special key → byte sequence to send to PTY
    _KEY_MAP = {
        "Up":    "\x1b[A",
        "Down":  "\x1b[B",
        "Right": "\x1b[C",
        "Left":  "\x1b[D",
        "Home":  "\x1b[H",
        "End":   "\x1b[F",
        "Prior": "\x1b[5~",  # Page Up
        "Next":  "\x1b[6~",  # Page Down
        "Delete":"\x1b[3~",
        "F1":  "\x1bOP", "F2": "\x1bOQ", "F3": "\x1bOR", "F4": "\x1bOS",
        "F5":  "\x1b[15~", "F6": "\x1b[17~", "F7": "\x1b[18~",
        "F8":  "\x1b[19~", "F9": "\x1b[20~", "F10": "\x1b[21~",
        "F11": "\x1b[23~", "F12": "\x1b[24~",
    }

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._pty: object = None
        self._queue:  queue.Queue = queue.Queue()
        self._parser  = AnsiParser()
        self._tags:   set[str] = set()
        self._shell_var = StringVar(value="Auto")
        self._running = False

        self._build_ui()
        self._poll()

        if PTY_AVAILABLE:
            self.after(100, self.start)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, shell: list[str] | None = None) -> None:
        """Spawn a new shell session, killing any existing one first."""
        self.stop()
        if not PTY_AVAILABLE:
            self._write("\n  PTY library not found.\n", "error")
            if platform.system() == "Windows":
                self._write("  Run: pip install pywinpty\n\n", "error")
            else:
                self._write("  Run: pip install ptyprocess\n\n", "error")
            return

        cmd = shell or _default_shell()
        try:
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            self._pty = _pty_spawn(cmd, dimensions=(24, 80), env=env)
            self._running = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            self._text.focus_set()
        except Exception as e:
            self._write(f"\n  Failed to start shell: {e}\n", "error")

    def stop(self) -> None:
        """Terminate the current PTY process."""
        self._running = False
        if self._pty and self._pty.isalive():
            try:
                self._pty.terminate(force=True)
            except Exception:
                pass
        self._pty = None

    def send(self, text: str) -> None:
        """Write text directly to the PTY stdin."""
        if self._pty and self._pty.isalive():
            try:
                self._pty.write(text)
            except Exception:
                pass

    def resize(self, rows: int, cols: int) -> None:
        """Notify the PTY of a terminal size change."""
        if self._pty and self._pty.isalive():
            try:
                self._pty.setwinsize(rows, cols)
            except Exception:
                pass

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", side="top", pady=(2, 0), padx=4)

        ttk.Label(toolbar, text="TERMINAL",
                  font=("TkDefaultFont", 8, "bold")).pack(side="left", padx=(0, 8))

        shells = list(self.SHELLS.keys())
        self._shell_cb = ttk.Combobox(
            toolbar, textvariable=self._shell_var,
            values=shells, width=12, state="readonly",
        )
        self._shell_cb.pack(side="left", padx=2)
        self._shell_cb.bind("<<ComboboxSelected>>", self._on_shell_change)

        ttk.Button(toolbar, text="⟳ Restart", width=9,
                   command=self._on_restart).pack(side="left", padx=2)
        ttk.Button(toolbar, text="✕ Clear", width=8,
                   command=self.clear).pack(side="left", padx=2)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # ── Output / input area ───────────────────────────────────────────────
        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self._text = Text(
            text_frame,
            bg="#1e1e1e", fg="#f8f8f2",
            font=("Consolas", 10),
            wrap="word",
            relief="flat", borderwidth=0,
            insertbackground="#f8f8f2",
            cursor="xterm",
            takefocus=True,
        )
        vs = ttk.Scrollbar(text_frame, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vs.set)
        self._text.grid(row=0, column=0, sticky="nswe")
        vs.grid(row=0, column=1, sticky="ns")

        # Remove the 'Text' class bindings so the widget never auto-inserts
        # typed characters — we forward everything to the PTY ourselves.
        self._text.bindtags((str(self._text), '.', 'all'))

        # Click anywhere in the output → grab focus so typing works
        self._text.bind("<ButtonPress-1>", lambda _: self._text.focus_set())

        # Forward all keystrokes to the PTY
        self._text.bind("<Key>",       self._on_key)
        self._text.bind("<Return>",    lambda _: (self.send("\r"),    "break")[1])
        self._text.bind("<BackSpace>", lambda _: (self.send("\x7f"),  "break")[1])
        self._text.bind("<Tab>",       lambda _: (self.send("\t"),    "break")[1])
        self._text.bind("<Escape>",    lambda _: (self.send("\x1b"),  "break")[1])
        self._text.bind("<Control-c>", lambda _: (self.send("\x03"),  "break")[1])
        self._text.bind("<Control-d>", lambda _: (self.send("\x04"),  "break")[1])
        self._text.bind("<Control-z>", lambda _: (self.send("\x1a"),  "break")[1])
        self._text.bind("<Control-l>", lambda _: (self.send("\x0c"),  "break")[1])
        self._text.bind("<Control-a>", lambda _: (self.send("\x01"),  "break")[1])
        self._text.bind("<Control-e>", lambda _: (self.send("\x05"),  "break")[1])
        self._text.bind("<Control-u>", lambda _: (self.send("\x15"),  "break")[1])
        self._text.bind("<Control-k>", lambda _: (self.send("\x0b"),  "break")[1])
        self._text.bind("<Control-w>", lambda _: (self.send("\x17"),  "break")[1])
        self._text.bind("<Control-r>", lambda _: (self.send("\x12"),  "break")[1])

        # Paste → send clipboard to PTY rather than inserting into widget
        self._text.bind("<<Paste>>",   self._on_paste)

        # Arrow / navigation keys → ANSI escape sequences
        for keysym, seq in self._KEY_MAP.items():
            self._text.bind(f"<{keysym}>",
                            lambda _, s=seq: (self.send(s), "break")[1])

        # Resize → update PTY dimensions
        self._text.bind("<Configure>", self._on_resize)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_key(self, event) -> str:
        """Forward printable characters to the PTY."""
        char = event.char
        if char and char not in ("\r", "\n", "\x08"):
            self.send(char)
        return "break"

    def _on_paste(self, _=None) -> str:
        """Send clipboard text to PTY instead of inserting into the widget."""
        try:
            text = self._text.clipboard_get()
            if text:
                self.send(text)
        except Exception:
            pass
        return "break"

    def _on_restart(self) -> None:
        cmd = self.SHELLS.get(self._shell_var.get())
        self.start(cmd)

    def _on_shell_change(self, _=None) -> None:
        cmd = self.SHELLS.get(self._shell_var.get())
        self.start(cmd)

    def _on_resize(self, _=None) -> None:
        """Update PTY dimensions when the widget resizes."""
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

    # ── Output rendering ──────────────────────────────────────────────────────

    def clear(self) -> None:
        self._text.delete("1.0", "end")
        self._text.mark_set("insert", "end")

    def _write(self, text: str, tag: str = "plain") -> None:
        self._text.mark_set("insert", "end")
        self._text.insert("insert", text, tag)
        self._text.see("end")

    def _ensure_tag(self, tag: str, fg: str | None, bg: str | None, bold: bool) -> None:
        if tag in self._tags or tag == "plain":
            return
        opts: dict = {}
        if fg:
            opts["foreground"] = fg
        if bg:
            opts["background"] = bg
        if bold:
            opts["font"] = ("Consolas", 10, "bold")
        if opts:
            self._text.tag_configure(tag, **opts)
        self._tags.add(tag)

    def _render_chunk(self, chunk: str) -> None:
        """Render PTY output with proper CR/LF/BS/ANSI handling."""
        # Normalize \r\n → \n so they are treated as a single line-feed.
        # Lone \r (carriage return without LF) is handled separately below.
        chunk = chunk.replace('\r\n', '\n')

        # Position write cursor at the logical end of existing content.
        self._text.mark_set("insert", "end-1c")

        i = 0
        n = len(chunk)
        while i < n:
            c = chunk[i]

            if c == '\r':
                # Lone carriage return: move to column 0 of current line.
                line = int(self._text.index("insert").split('.')[0])
                self._text.mark_set("insert", f"{line}.0")
                i += 1

            elif c == '\n':
                # Line feed: append a newline at the END of the current line
                # (not at the cursor, which may be mid-line after a \r), then
                # advance the cursor to the start of the new line.
                line = int(self._text.index("insert").split('.')[0])
                self._text.insert(f"{line}.end", "\n")
                self._text.mark_set("insert", f"{line + 1}.0")
                i += 1

            elif c == '\x08':
                # Backspace: delete the character left of the cursor.
                if self._text.compare("insert", ">", "insert linestart"):
                    self._text.delete("insert-1c", "insert")
                i += 1

            elif c == '\x1b':
                m = _ANSI_RE.match(chunk, i)
                if m:
                    code, letter = m.group(1), m.group(2)
                    p = [int(x) for x in code.split(';') if x.isdigit()]

                    if letter == 'm':
                        self._parser.process(code)

                    elif letter == 'K':
                        # Erase in line
                        n = p[0] if p else 0
                        if n == 0:
                            self._text.delete("insert", "insert lineend")
                        elif n == 1:
                            self._text.delete("insert linestart", "insert")
                        elif n == 2:
                            self._text.delete("insert linestart", "insert lineend")

                    elif letter == 'G':
                        # Cursor Horizontal Absolute — ESC[nG moves to column n (1-based)
                        col = (p[0] - 1) if p else 0
                        line = int(self._text.index("insert").split('.')[0])
                        self._text.mark_set("insert", f"{line}.{max(0, col)}")

                    elif letter in ('H', 'f'):
                        # Cursor Position — ESC[row;colH (1-based, default 1)
                        col = (p[1] - 1) if len(p) >= 2 else 0
                        line = int(self._text.index("insert").split('.')[0])
                        self._text.mark_set("insert", f"{line}.{max(0, col)}")

                    elif letter == 'C':
                        # Cursor Forward n columns
                        n = p[0] if p else 1
                        self._text.mark_set("insert", f"insert+{n}c")

                    elif letter == 'D':
                        # Cursor Back n columns (don't go past line start)
                        n = p[0] if p else 1
                        new_idx = f"insert-{n}c"
                        if self._text.compare(new_idx, "<", "insert linestart"):
                            new_idx = "insert linestart"
                        self._text.mark_set("insert", new_idx)

                    # All other sequences silently consumed
                    i = m.end()
                else:
                    i += 1

            else:
                # Collect a run of printable characters.
                j = i + 1
                while j < n and chunk[j] not in ('\r', '\n', '\x08', '\x1b'):
                    j += 1
                segment = chunk[i:j]
                tag = self._parser.tag()
                self._ensure_tag(tag, self._parser.fg(), self._parser.bg(), self._parser.bold())
                # When the cursor is mid-line (e.g. after a \r), overwrite the
                # existing characters rather than inserting in front of them.
                if self._text.compare("insert", "<", "insert lineend"):
                    del_to = f"insert+{len(segment)}c"
                    if self._text.compare(del_to, ">", "insert lineend"):
                        del_to = "insert lineend"
                    self._text.delete("insert", del_to)
                self._text.insert("insert", segment, tag)
                i = j

        self._text.see("end")

    # ── PTY read loop ─────────────────────────────────────────────────────────

    def _read_loop(self) -> None:
        """Read from the PTY in a background thread and push to the queue."""
        while self._running and self._pty and self._pty.isalive():
            try:
                chunk = self._pty.read(4096)
                if chunk:
                    self._queue.put(chunk)
            except EOFError:
                break
            except Exception:
                break
        self._queue.put(None)  # sentinel

    def _poll(self) -> None:
        """Drain the queue every 30 ms on the main thread."""
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    self._running = False
                    self._write("\n[Process exited]\n", "plain")
                    break
                self._render_chunk(item)
        except queue.Empty:
            pass
        self.after(30, self._poll)
