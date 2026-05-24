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
import sys
import queue
import re
import shutil
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional
from widgets.scrollbar import VerticalScrollbar

# Platform-appropriate monospace font for the terminal canvas
_PLAT = platform.system()
if _PLAT == "Darwin":
    _TERM_FONT_FAMILY, _TERM_FONT_SIZE = "Menlo", 11
elif _PLAT == "Windows":
    _TERM_FONT_FAMILY, _TERM_FONT_SIZE = "Consolas", 10
else:
    _TERM_FONT_FAMILY, _TERM_FONT_SIZE = "DejaVu Sans Mono", 10

import pyte
from utils.ui_font import UI_FONT

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


class _RobustScreen(pyte.HistoryScreen):
    """pyte.HistoryScreen that:
    - Fixes the private SGR dispatch bug in pyte
    - Tracks whether the running app has enabled mouse reporting
    - Tags lines that exit via DECAWM wrap so scrollback can reflow on resize
    - Implements alternate screen buffer (DECSET 1049) so vim/htop/edit
      can enter and exit full-screen mode without corrupting the scrollback
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mouse_enabled = False
        self.in_alt_screen = False
        # Saved main-screen state while alternate screen is active
        self._main_buffer: dict | None = None
        self._main_cursor: tuple | None = None   # (x, y)
        # True while inside a draw() call; lets carriage_return() distinguish
        # wrap-induced CR (correct to flag as wrapped) from explicit "\r" in
        # the byte stream (NOT a wrap — e.g. PSReadLine sending \r\n after
        # Enter on a command that exactly filled the row to col == columns).
        self._draw_wrap_pending = False
        # Set whenever a cursor-up sequence (CUU / \x1b[NA) is processed in
        # the current poll frame. Cleared by _poll after each render cycle.
        # Used to detect non-alt-screen TUI repaints (Rich Live, etc.) vs
        # normal scrolling output so we can show overflow rows correctly.
        self.had_cursor_up = False
        # Minimum cursor.y reached via cursor-up in the current poll frame.
        # Records where the TUI app jumped to so _poll can scroll there.
        self.cursor_up_min_y: int | None = None

    def draw(self, data: str) -> None:
        self._draw_wrap_pending = True
        try:
            super().draw(data)
        finally:
            self._draw_wrap_pending = False

    def carriage_return(self):
        if self._draw_wrap_pending and self.cursor.x == self.columns:
            self.buffer[self.cursor.y].idol_wrapped = True
        super().carriage_return()

    def cursor_up(self, count=1):
        self.had_cursor_up = True
        dest_y = max(0, self.cursor.y - count)
        if self.cursor_up_min_y is None or dest_y < self.cursor_up_min_y:
            self.cursor_up_min_y = dest_y
        super().cursor_up(count)

    def set_mode(self, *args, private=False, **kwargs):
        if private and args:
            # Mouse tracking modes: 9=X10, 1000=normal, 1002=button, 1003=any, 1006=SGR
            if args[0] in (9, 1000, 1002, 1003, 1006):
                self.mouse_enabled = True
            # Alternate screen buffer (DEC 1049): save main screen, blank alt screen
            if args[0] == 1049 and not self.in_alt_screen:
                self._main_buffer = {y: dict(row) for y, row in self.buffer.items()}
                self._main_cursor = (self.cursor.x, self.cursor.y)
                self.buffer.clear()
                self.cursor.x = 0
                self.cursor.y = 0
                self.in_alt_screen = True
        try:
            super().set_mode(*args, private=private, **kwargs)
        except Exception:
            pass

    def reset_mode(self, *args, private=False, **kwargs):
        if private and args:
            if args[0] in (9, 1000, 1002, 1003, 1006):
                self.mouse_enabled = False
            # Alternate screen exit (DEC 1049): restore main screen
            if args[0] == 1049 and self.in_alt_screen:
                self.buffer.clear()
                if self._main_buffer is not None:
                    for y, row_dict in self._main_buffer.items():
                        for x, char in row_dict.items():
                            self.buffer[y][x] = char
                    self._main_buffer = None
                if self._main_cursor is not None:
                    self.cursor.x, self.cursor.y = self._main_cursor
                    self._main_cursor = None
                self.in_alt_screen = False
        try:
            super().reset_mode(*args, private=private, **kwargs)
        except Exception:
            pass

    def select_graphic_rendition(self, *args, private=False, **kwargs):
        if private:
            return   # ignore malformed private SGR sequences
        super().select_graphic_rendition(*args, **kwargs)


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


def _detect_available_shells() -> list[dict]:
    """Return [{name, cmd, color}] for every shell found on this system."""
    result: list[dict] = []
    system = platform.system()

    def _add(name: str, cmd: list[str], color: str) -> None:
        if not any(s["name"] == name for s in result):
            result.append({"name": name, "cmd": cmd, "color": color})

    if system == "Windows":
        if shutil.which("powershell"):
            _add("PowerShell", ["powershell.exe", "-NoLogo"], "#2671be")
        if shutil.which("pwsh"):
            _add("PowerShell 7", ["pwsh", "-NoLogo"], "#2671be")
        _add("cmd", ["cmd.exe"], "#858585")
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.exists(git_bash):
            # --login sources /etc/profile which adds Git's usr/bin to PATH
            # (needed for cygpath, sort, etc.).  -i forces interactive mode so
            # readline keybindings and PROMPT_COMMAND work correctly.
            _add("Git Bash", [git_bash, "--login", "-i"], "#4ec9b0")
        wsl_path = shutil.which("wsl.exe") or shutil.which("wsl")
        if wsl_path:
            _add("WSL", [wsl_path], "#4ec9b0")
    else:
        _SHELL_COLORS = {"bash": "#4ec9b0", "zsh": "#4ec9b0", "sh": "#4ec9b0",
                         "fish": "#4ec9b0", "dash": "#4ec9b0"}
        try:
            with open("/etc/shells") as f:
                seen: set[str] = set()
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    name = os.path.basename(line)
                    if name not in seen and shutil.which(name):
                        seen.add(name)
                        _add(name, [line], _SHELL_COLORS.get(name, "#8a8a8a"))
        except Exception:
            pass
        for sh in ("bash", "zsh", "sh"):
            path = shutil.which(sh)
            if path:
                _add(sh, [path], "#4ec9b0")

        # Promote the user's $SHELL to the front so new sessions match their login shell
        user_shell = os.environ.get("SHELL", "")
        if user_shell:
            user_name = os.path.basename(user_shell)
            for i, entry in enumerate(result):
                if entry["name"] == user_name:
                    result.insert(0, result.pop(i))
                    break

    # Python REPL — use sys.executable to avoid Windows Store stubs
    python = sys.executable
    try:
        import subprocess as _sp
        ver = _sp.check_output([python, "--version"], text=True,
                               stderr=_sp.STDOUT, timeout=3).strip()
        parts = ver.split()
        version = ".".join(parts[1].split(".")[:2]) if len(parts) > 1 else ""
        py_name = f"Python {version}" if version else "Python REPL"
    except Exception:
        py_name = "Python REPL"
    _add(py_name, [python, "-i"], "#f7cc43")

    return result


class SessionPanel(tk.Canvas):
    """Canvas-drawn VS Code-style session list (right sidebar of TerminalPanel)."""

    _ROW_H   = 28
    _FOOT_H  = 36
    _BG      = "#252526"
    _ACT_BG  = "#37373d"
    _HOV_BG  = "#2d2d30"
    _FOOT_BG = "#1e1e1e"
    _FG      = "#cccccc"
    _ACT_FG  = "#ffffff"
    _ACCENT  = "#0e7fd5"
    _BTN_FG  = "#8a8a8a"
    _BTN_HOV = "#cccccc"

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("bg", self._BG)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)

        self._sessions:   dict = {}
        self._active_key: str  = ""
        self._run_key:    str  = ""
        self._hover_row:  Optional[int] = None
        self._close_hover: bool = False
        self._btn_hover:  Optional[str] = None  # "btn_new" | "btn_dd"

        self.on_select:   Callable[[str], None]  = lambda k: None
        self.on_close:    Callable[[str], None]  = lambda k: None
        self.on_new:      Callable[[], None]     = lambda: None
        self.on_dropdown: Callable               = lambda e: None
        self.on_context:  Callable               = lambda k, x, y: None

        self.bind("<Motion>",          self._on_motion)
        self.bind("<Leave>",           self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)
        self.bind("<Button-3>",        self._on_right_click)
        self.bind("<Configure>",       lambda _: self._draw())

    def refresh(self, sessions: dict, active_key: str, run_key: str) -> None:
        self._sessions   = sessions
        self._active_key = active_key
        self._run_key    = run_key
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w = max(self.winfo_width(), 1)
        keys = list(self._sessions.keys())

        for i, key in enumerate(keys):
            self._draw_row(i * self._ROW_H, key, self._sessions[key],
                           key == self._active_key,
                           key == self._run_key,
                           self._hover_row == i)

        foot_y = len(keys) * self._ROW_H
        self.create_rectangle(0, foot_y, w, foot_y + self._FOOT_H,
                              fill=self._FOOT_BG, outline="")

        cy = foot_y + self._FOOT_H // 2
        new_fg = self._BTN_HOV if self._btn_hover == "btn_new" else self._BTN_FG
        dd_fg  = self._BTN_HOV if self._btn_hover == "btn_dd"  else self._BTN_FG
        self.create_text(14, cy, text="+", fill=new_fg,
                         font=(UI_FONT, 10, "bold"), anchor="center", tags="btn_new")
        # thin separator
        self.create_line(26, cy - 6, 26, cy + 6, fill="#3e3e42", width=1)
        self.create_text(36, cy, text="▾", fill=dd_fg,
                         font=(UI_FONT, 8), anchor="center", tags="btn_dd")

    def _draw_row(self, y: int, key: str, data: dict,
                  is_active: bool, is_run: bool, is_hover: bool) -> None:
        w   = max(self.winfo_width(), 1)
        cy  = y + self._ROW_H // 2
        rtag = f"row_{key}"
        ctag = f"close_{key}"

        bg = self._ACT_BG if is_active else (self._HOV_BG if is_hover else self._BG)
        self.create_rectangle(0, y, w, y + self._ROW_H,
                              fill=bg, outline="", tags=rtag)

        if is_active:
            self.create_rectangle(0, y, 4, y + self._ROW_H,
                                  fill=self._ACCENT, outline="", tags=rtag)

        icon = data.get("icon_color", "#8a8a8a")
        self.create_oval(11, cy - 5, 21, cy + 5,
                         fill=icon, outline="", tags=rtag)

        fg = self._ACT_FG if is_active else self._FG
        self.create_text(28, cy, text=data.get("display_name", key),
                         fill=fg, font=(UI_FONT, 9), anchor="w", tags=rtag)

        if is_hover:
            close_fg = "#ff5555" if self._close_hover else self._BTN_FG
            self.create_text(w - 8, cy, text="✕", fill=close_fg,
                             font=(UI_FONT, 8), anchor="e", tags=(rtag, ctag))
            if is_run:
                self.create_text(w - 22, cy, text="▶", fill=self._ACCENT,
                                 font=(UI_FONT, 7), anchor="e", tags=rtag)
        elif is_run:
            self.create_text(w - 8, cy, text="▶", fill=self._ACCENT,
                             font=(UI_FONT, 7), anchor="e", tags=rtag)

    def _on_motion(self, event) -> None:
        n      = len(self._sessions)
        foot_y = n * self._ROW_H
        w      = max(self.winfo_width(), 1)

        prev_hover = self._hover_row
        prev_close = self._close_hover
        prev_btn   = self._btn_hover

        if event.y >= foot_y:
            self._hover_row  = None
            self._close_hover = False
            tags_hit: set[str] = set()
            for item in self.find_overlapping(event.x, event.y, event.x, event.y):
                tags_hit.update(self.gettags(item))
            if "btn_new" in tags_hit:
                self._btn_hover = "btn_new"
            elif "btn_dd" in tags_hit:
                self._btn_hover = "btn_dd"
            else:
                self._btn_hover = None
        else:
            row = event.y // self._ROW_H
            self._hover_row   = row if row < n else None
            self._close_hover = (event.x > w - 20) and (self._hover_row is not None)
            self._btn_hover   = None

        if (self._hover_row != prev_hover or
                self._close_hover != prev_close or
                self._btn_hover != prev_btn):
            self._draw()

    def _on_leave(self, _event) -> None:
        if self._hover_row is not None or self._close_hover or self._btn_hover:
            self._hover_row   = None
            self._close_hover = False
            self._btn_hover   = None
            self._draw()

    def _on_click(self, event) -> None:
        keys = list(self._sessions.keys())
        n = len(keys)
        foot_y = n * self._ROW_H
        w = max(self.winfo_width(), 1)

        if event.y >= foot_y:
            # Footer buttons — items are stable here, tag-based hit-test is fine
            tags_hit: set[str] = set()
            for item in self.find_overlapping(event.x, event.y,
                                              event.x, event.y):
                tags_hit.update(self.gettags(item))
            if "btn_new" in tags_hit:
                self.on_new()
            elif "btn_dd" in tags_hit:
                self.on_dropdown(event)
            return

        # Row hit — geometric, not tag-based. On X11 a spurious <Leave> between
        # press and release can clear _hover_row and redraw without the "✕"
        # item, so a tag lookup would miss the close button. event.x > w - 20
        # matches the close-region rule from _on_motion.
        row = event.y // self._ROW_H
        if row < 0 or row >= n:
            return
        key = keys[row]
        if event.x > w - 20:
            self.on_close(key)
        else:
            self.on_select(key)

    def _on_right_click(self, event) -> None:
        n = len(self._sessions)
        row = event.y // self._ROW_H
        if row < n:
            key = list(self._sessions.keys())[row]
            self.on_context(key, event.x_root, event.y_root)


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
    # pyte stores 24-bit truecolor as a bare 6-char hex string e.g. "ff0000"
    # (no leading #). ConPTY on Windows converts 256-colour to 24-bit, so this
    # path is hit for all PowerShell colour output.
    if isinstance(color, str) and len(color) == 6:
        try:
            int(color, 16)
            return f"#{color}"
        except ValueError:
            pass
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

    _KEY_MAP = {
        # Basic cursor keys
        "Up":    "\x1b[A",
        "Down":  "\x1b[B",
        "Right": "\x1b[C",
        "Left":  "\x1b[D",
        "Home":  "\x1b[H",
        "End":   "\x1b[F",
        "Insert":"\x1b[2~",
        "Prior": "\x1b[5~",
        "Next":  "\x1b[6~",
        "Delete":"\x1b[3~",
        # Ctrl+arrow — word nav and TUI pane switching (tmux, vim, etc.)
        "Control-Up":    "\x1b[1;5A",
        "Control-Down":  "\x1b[1;5B",
        "Control-Right": "\x1b[1;5C",
        "Control-Left":  "\x1b[1;5D",
        # Shift+arrow — selection in edit.exe, mc, etc.
        "Shift-Up":    "\x1b[1;2A",
        "Shift-Down":  "\x1b[1;2B",
        "Shift-Right": "\x1b[1;2C",
        "Shift-Left":  "\x1b[1;2D",
        "Shift-Home":  "\x1b[1;2H",
        "Shift-End":   "\x1b[1;2F",
        # Alt+arrow — common in TUI file managers
        "Alt-Up":    "\x1b[1;3A",
        "Alt-Down":  "\x1b[1;3B",
        "Alt-Right": "\x1b[1;3C",
        "Alt-Left":  "\x1b[1;3D",
        # Function keys
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
        self.on_venv_activate:   Optional[Callable[[str], None]] = None
        self.on_venv_deactivate: Optional[Callable[[], None]]   = None
        self.on_command_done:    Optional[Callable[[Optional[int]], None]] = None
        self._running   = False
        self._cwd: Optional[str] = None

        # pyte screen — sized properly once the widget is mapped
        self._rows = 24
        self._cols = 80
        self._screen = _RobustScreen(self._cols, self._rows, history=self._SCROLLBACK)
        self._stream = pyte.ByteStream(self._screen)

        # Scrollback: list of LOGICAL lines (may be wider than self._cols).
        # Each entry: list of (text, fg, bg, bold) segments for one logical line.
        # Rendering wraps each logical line to physical canvas rows at draw time,
        # so resizing the canvas reflows scrollback at the new column count.
        self._scrollback: list[list] = []
        self._scrollback_drawn: int = 0   # logical lines already drawn to canvas
        self._scrollback_open: bool = False   # last logical line awaits continuation
        self._sb_phys_rows: int = 0           # physical canvas rows scrollback occupies
        # Maps physical scrollback row index → (logical_idx, char_start, char_end).
        # Rebuilt every redraw; used by copy-selection to extract row text.
        self._phys_to_log: list[tuple[int, int, int]] = []

        # Canvas font objects (set in _build_ui once widget exists)
        self._char_w: int = 7
        self._char_h: int = 15
        self._font:       object = None
        self._bold_font:  object = None

        self._resize_job = None
        # Selection in terminal grid coordinates: (row, col) tuples
        self._sel_anchor:    tuple | None = None
        self._sel_row_start: tuple | None = None
        self._sel_row_end:   tuple | None = None
        self._session_id = 0   # incremented on each start(); guards stale sentinels
        self._render_suppressed = False   # True during startup; suppresses _redraw_full until clear fires
        self._clear_timer: str | None = None  # after() handle for the fallback clear
        self._waiting_first_prompt = False    # lifted on first OSC 133 → triggers clean render

        # Multi-session support: numbered keys ("s1", "s2", …)
        self._sessions:         dict[str, dict] = {}   # saved background sessions
        self._active_shell_key: str             = ""
        self._sid_to_key:       dict[int, str]  = {}   # session_id → shell key, routes queue
        self._session_keys:     list[str]       = []   # ordered session keys
        self._session_counter:  int             = 0
        self._session_meta:     dict[str, dict] = {}   # key → {display_name, cmd, icon_color}
        self._run_shell_key:    str             = ""   # targeted by run_file_in_terminal
        self._detected_shells:  list[dict]      = []   # cached _detect_available_shells()
        self._panel_visible:    bool            = True
        self._session_panel_w:  int             = 160
        self._sash_ghost:       Optional[tk.Frame] = None
        self._sash_start_x:     int             = 0
        self._sash_dragging:    bool            = False
        self._anim_gen:         int             = 0   # incremented on each toggle to cancel stale callbacks

        # Venv tracking
        self._cwd_current: str = ""        # last CWD from OSC 7 / state file
        self._venv_active:  str = ""        # $VIRTUAL_ENV from shell hook ("" = none)
        self._raw_buf: str = ""            # kept for session serialization compat; not used
        # IDOL's own venv — inherited by child shells, ignore for user detection
        self._idol_venv: str = os.environ.get("VIRTUAL_ENV", "")
        # Windows: temp file used to pass CWD/VENV without polluting stdout
        self._state_file: str = ""
        self._state_file_mtime: float = 0.0

        self._build_ui()
        self._poll()

    def build_tab_controls(self, parent) -> None:
        """Populate *parent* (the tab bar slot) with terminal-specific controls."""
        _BG = "#252526"
        _FG = "#8a8a8a"

        for text, cmd in (("⟳ Restart", self._on_restart), ("✕ Clear", self.clear)):
            btn = tk.Label(
                parent, text=text,
                bg=_BG, fg=_FG,
                font=(UI_FONT, 8), cursor="hand2", pady=6, padx=4,
            )
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda _, c=cmd: c())
            btn.bind("<Enter>", lambda _, b=btn: b.config(fg="#ffffff"))
            btn.bind("<Leave>", lambda _, b=btn: b.config(fg=_FG))
            if text == "⟳ Restart":
                self._restart_btn = btn
            else:
                self._term_clear_btn = btn

        # ≡ toggle button — always visible, rightmost before venv controls
        toggle_btn = tk.Label(
            parent, text="≡",
            bg=_BG, fg=_FG,
            font=(UI_FONT, 10), cursor="hand2", pady=6, padx=6,
        )
        toggle_btn.pack(side="left", padx=(4, 2))
        toggle_btn.bind("<ButtonRelease-1>", lambda _: self._toggle_panel())
        toggle_btn.bind("<Enter>", lambda _: toggle_btn.config(fg="#ffffff"))
        toggle_btn.bind("<Leave>", lambda _: toggle_btn.config(fg=_FG))

        # Venv controls — right-aligned
        self._venv_btn = tk.Label(
            parent, text="▶ Activate venv",
            bg="#0e639c", fg="white",
            font=(UI_FONT, 8), cursor="hand2",
            padx=6, pady=1,
        )
        self._venv_btn.pack(side="right", padx=(4, 6))
        self._venv_btn.bind("<Button-1>", lambda _: self._venv_btn_click())
        self._venv_btn.bind("<Enter>",    lambda _: self._venv_btn_hover(True))
        self._venv_btn.bind("<Leave>",    lambda _: self._venv_btn_hover(False))

        self._venv_label = tk.Label(
            parent, text="",
            bg="#2d2d30", fg="#50fa7b",
            font=(UI_FONT, 8),
        )
        self._update_venv_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, shell: list[str] | None = None,
              cwd: str | None = None) -> None:
        if cwd is not None:
            self._cwd = cwd
        # Remove this session's old SID mapping; leave background sessions intact
        if self._sid_to_key.get(self._session_id) == self._active_shell_key:
            self._sid_to_key.pop(self._session_id, None)
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
            env["IDOL_TERMINAL"]  = "1"
            # macOS zsh restores ~/.zsh_sessions on startup, which can print
            # "Saving session..." text that zsh then tries to execute as a
            # command.  Disabling session history avoids this entirely.
            if sys.platform == "darwin":
                env["SHELL_SESSION_HISTORY"] = "0"
            # Strip IDOL's own venv so the child shell starts clean
            env.pop("VIRTUAL_ENV", None)
            env.pop("VIRTUAL_ENV_PROMPT", None)
            # Remove venv bin dir from PATH so the shell doesn't inherit it
            if self._idol_venv:
                venv_bin = os.path.join(self._idol_venv, "bin") + os.pathsep
                venv_scripts = os.path.join(self._idol_venv, "Scripts") + os.pathsep
                env["PATH"] = env.get("PATH", "").replace(venv_bin, "").replace(venv_scripts, "")
            # For Git Bash on Windows, replicate what git-bash.exe does before
            # handing off to bash.exe: set MSYSTEM so the MSYS2 runtime converts
            # the Windows PATH to POSIX and adds MINGW64 tool directories.
            # Without MSYSTEM the DLL skips path conversion entirely — cygpath,
            # which, tr, etc. all appear missing even though they're on disk.
            if platform.system() == "Windows" and "bash" in os.path.basename(cmd[0]).lower():
                _git_root = os.path.normpath(os.path.join(os.path.dirname(cmd[0]), ".."))
                env.setdefault("MSYSTEM", "MINGW64")
                env.setdefault("MSYS", "winsymlinks:nativestrict")
                env.setdefault("MINGW_MOUNT_POINT", "/mingw64")
                # HOMEDRIVE/HOMEPATH let bash resolve ~ correctly on Windows
                env.setdefault("HOMEDRIVE", os.environ.get("HOMEDRIVE", "C:"))
                env.setdefault("HOMEPATH",  os.environ.get("HOMEPATH",  os.path.expanduser("~").replace(os.environ.get("HOMEDRIVE","C:"), "")))
            # sh/dash don't understand zsh-style prompt codes (%{...%}); strip
            # any inherited PS1 so they fall back to their built-in default.
            _shell_base = os.path.basename(cmd[0]).lower()
            if _shell_base in ("sh", "dash", "ash"):
                env.pop("PS1", None)
            # Reassign (don't .clear()) so we break the reference shared
            # with any session just snapshotted into self._sessions. With
            # .clear() the previously-active session's saved scrollback IS
            # this list — emptying it here would erase its history, and as
            # this new session populates the list both sessions would point
            # to the same content (bleed-through on switch-back).
            self._scrollback = []
            self._scrollback_drawn = 0
            self._scrollback_open = False
            self._sb_phys_rows = 0
            self._phys_to_log = []
            # Clear any suppression/timer left over from a previous session, then
            # wipe the canvas before drawing the new empty screen. Without
            # this, _switch_session → start() leaves the old session's
            # canvas items in place and the new shell's output overlays on
            # top of them until the next session swap.
            if self._clear_timer:
                self.after_cancel(self._clear_timer)
                self._clear_timer = None
            self._waiting_first_prompt = False
            self._render_suppressed = False
            self._screen = _RobustScreen(self._cols, self._rows, history=self._SCROLLBACK)
            self._stream = pyte.ByteStream(self._screen)
            self._redraw_full()
            self._session_id += 1
            sid = self._session_id
            self._pty = _pty_spawn(cmd, dimensions=(self._rows, self._cols), env=env)
            self._running = True
            self._raw_buf  = ""
            self._cwd_current = ""
            self._venv_active  = ""
            self._venv_auto_activated = False
            self._state_file_mtime = 0.0
            self._sid_to_key[sid] = self._active_shell_key
            threading.Thread(target=self._read_loop, args=(sid, self._pty), daemon=True).start()
            self._canvas.focus_set()
            # Inject OSC 7 CWD + VENV reporting hook after shell is ready.
            # Both the cd and hook injection use _send_silently so the TTY
            # driver never echoes the commands — nothing to clear afterward.
            self.after(400, self._inject_shell_hooks)
            _cmd_name = os.path.basename(cmd[0]).lower()
            _is_shell = any(s in _cmd_name for s in ("powershell", "pwsh", "cmd", "bash", "zsh", "sh"))
            _cmd_is_cmd = "cmd" in _cmd_name and "powershell" not in _cmd_name and "pwsh" not in _cmd_name
            if not _cmd_is_cmd:
                # Suppress rendering until the first OSC 133 (shell prompt hook fires),
                # meaning setup is fully done. Fallback clears after 3s if hook never arrives.
                self._render_suppressed = True
                self._waiting_first_prompt = True
                self._clear_timer = self.after(3000, self._clear_screen_direct)
            self.after(3500, self._ensure_render_active)
            _cwd = self._cwd
            if _cwd and os.path.isdir(_cwd) and _is_shell:
                self.after(300, lambda c=_cwd: self._send_silently(f'cd "{c}"\r'))
                # Auto-source the project venv (if one exists in *cwd*) so the
                # shell starts already inside it. Skipped for cmd/sh/dash —
                # those either lack a clean activate path or use bashisms.
                self.after(600, lambda c=_cwd, n=_cmd_name: self._auto_activate_venv(c, n))
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
        if self._clear_timer:
            self.after_cancel(self._clear_timer)
            self._clear_timer = None
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

    def resize(self, rows: int, cols: int) -> bool:
        if rows == self._rows and cols == self._cols:
            return False
        old_cols = self._cols
        self._rows = rows
        self._cols = cols
        # Bypass pyte's resize() entirely: pyte's resize has two problems:
        # 1. On row-shrink it calls delete_lines(N) unconditionally from the
        #    top, but ConPTY only scrolls by max(0, cursor.y - (rows-1)).
        #    The mismatch shifts pyte's buffer relative to ConPTY, causing
        #    PSReadLine's SIGWINCH cursor-up to land on the wrong row.
        # 2. On col-shrink it pops cells beyond the new width, permanently
        #    destroying chars PSReadLine would restore via SIGWINCH.
        # _screen_to_lines() already limits rendering to self._screen.columns,
        # so retained extra-width cells are invisible until PSReadLine rewrites
        # them at the new wrapping position.
        self._screen.lines = rows
        self._screen.cursor.y = min(self._screen.cursor.y, rows - 1)
        if cols != old_cols:
            self._screen.columns = cols
        self._screen.set_margins()
        self._screen.dirty.update(range(rows))
        if self._pty and self._running:
            try:
                self._pty.setwinsize(rows, cols)
            except Exception:
                pass
        for sess in self._sessions.values():
            try:
                sess["screen"].lines = rows
                sess["screen"].cursor.y = min(sess["screen"].cursor.y, rows - 1)
                if cols != old_cols:
                    sess["screen"].columns = cols
                sess["screen"].set_margins()
                sess["screen"].dirty.update(range(rows))
                if sess["running"] and sess.get("pty"):
                    sess["pty"].setwinsize(rows, cols)
            except Exception:
                pass
        return True

    def _clear_screen_direct(self) -> None:
        """Reset pyte completely to discard startup noise, lift render suppression,
        then nudge the shell for a fresh prompt. One clean render, no flash."""
        if self._clear_timer:
            self.after_cancel(self._clear_timer)
            self._clear_timer = None
        self._scrollback.clear()
        self._scrollback_drawn = 0
        self._scrollback_open = False
        self._sb_phys_rows = 0
        self._phys_to_log = []
        self._screen = _RobustScreen(self._cols, self._rows, history=self._SCROLLBACK)
        self._stream = pyte.ByteStream(self._screen)
        self._render_suppressed = False
        self._redraw_full()
        if self._running and self._pty:
            if platform.system() == "Windows":
                self.send_text("\x0c")   # PSReadLine ClearScreen: clears + redraws prompt
            else:
                self.send_text("\r")

    def _ensure_render_active(self) -> None:
        """Fallback: if _clear_screen_direct never fired (slow system), lift
        suppression now so the terminal doesn't stay permanently blank."""
        if self._render_suppressed:
            self._render_suppressed = False
            self._redraw_full()

    def clear(self) -> None:
        """Clear terminal display directly via pyte — no shell involvement, no flash."""
        self._clear_screen_direct()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._venv_btn_state = "none"   # none | activate | active_match | active_other

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        self._body_frame = tk.Frame(self, bg="#1e1e1e")
        self._body_frame.pack(fill="both", expand=True)

        text_frame = tk.Frame(self._body_frame, bg="#1e1e1e")
        self._text_frame = text_frame
        text_frame.pack(side="left", fill="both", expand=True)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        # Terminal canvas — pixel-perfect VT100 renderer
        self._font      = tkfont.Font(family=_TERM_FONT_FAMILY, size=_TERM_FONT_SIZE)
        self._bold_font = tkfont.Font(family=_TERM_FONT_FAMILY, size=_TERM_FONT_SIZE,
                                      weight="bold")
        # Use the wider of regular/bold so column count matches both weights.
        self._char_w = max(self._font.measure("W"), self._bold_font.measure("W"))
        # Use ascent+descent (no font leading) so box-drawing chars connect
        # edge-to-edge between rows, the same way real terminal emulators do.
        # linespace adds leading that creates pixel gaps, breaking │ ─ ┬ etc.
        _m = self._font.metrics()
        self._char_h = max(1, _m["ascent"] + _m["descent"])

        self._canvas = tk.Canvas(
            text_frame,
            bg=_DEFAULT_BG,
            highlightthickness=0,
            takefocus=True,
            cursor="xterm",
        )
        vs = VerticalScrollbar(text_frame, command=self._canvas.yview)
        self._scrollbar = vs
        self._canvas.configure(yscrollcommand=vs.set)
        self._canvas.grid(row=0, column=0, sticky="nswe")
        vs.grid(row=0, column=1, sticky="ns")

        self._canvas.bind("<ButtonPress-1>",   self._on_click)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<MouseWheel>",      self._on_mousewheel)   # Windows / macOS
        self._canvas.bind("<Button-4>",        self._on_mousewheel)   # Linux scroll up
        self._canvas.bind("<Button-5>",        self._on_mousewheel)   # Linux scroll down
        self._canvas.bind("<Button-3>",        self._show_context_menu)
        self._canvas.bind("<Control-Shift-C>", lambda _: (self._copy_selection(), "break")[1])
        self._canvas.bind("<Control-Shift-V>", lambda _: (self._on_paste(),       "break")[1])
        self._canvas.bind("<Key>",             self._on_key)
        self._canvas.bind("<Return>",          lambda _: (self.send("\r"),   "break")[1])
        self._canvas.bind("<BackSpace>",       lambda _: (self.send("\x7f"), "break")[1])
        self._canvas.bind("<Tab>",             lambda _: (self.send("\t"),   "break")[1])
        self._canvas.bind("<Escape>",          lambda _: (self.send("\x1b"), "break")[1])
        self._canvas.bind("<Control-c>",       lambda _: (self.send("\x03"), "break")[1])
        self._canvas.bind("<Control-d>",       lambda _: (self.send("\x04"), "break")[1])
        self._canvas.bind("<Control-z>",       lambda _: (self.send("\x1a"), "break")[1])
        self._canvas.bind("<Control-l>",       lambda _: (self.send("\x0c"), "break")[1])
        self._canvas.bind("<Control-a>",       lambda _: (self.send("\x01"), "break")[1])
        self._canvas.bind("<Control-e>",       lambda _: (self.send("\x05"), "break")[1])
        self._canvas.bind("<Control-u>",       lambda _: (self.send("\x15"), "break")[1])
        self._canvas.bind("<Control-k>",       lambda _: (self.send("\x0b"), "break")[1])
        self._canvas.bind("<Control-w>",       lambda _: (self.send("\x17"), "break")[1])
        self._canvas.bind("<Control-r>",       lambda _: (self.send("\x12"), "break")[1])
        self._canvas.bind("<<Paste>>",         self._on_paste)
        self._canvas.bind("<Configure>",       self._on_resize)

        for keysym, seq in self._KEY_MAP.items():
            self._canvas.bind(f"<{keysym}>",
                              lambda _, s=seq: (self.send(s), "break")[1])

        # Ghost sash (4px canvas, draggable, resizes session panel)
        self._sash = tk.Canvas(self._body_frame, width=4, bg="#2d2d30",
                               cursor="sb_h_double_arrow", highlightthickness=0)
        self._sash.pack(side="left", fill="y")
        self._sash.bind("<Enter>",          self._on_sash_enter)
        self._sash.bind("<Leave>",          self._on_sash_leave)
        self._sash.bind("<ButtonPress-1>",  self._on_sash_press)
        self._sash.bind("<B1-Motion>",      self._on_sash_drag)
        self._sash.bind("<ButtonRelease-1>",self._on_sash_release)

        # Session panel (right sidebar)
        self._session_panel = SessionPanel(self._body_frame)
        self._session_panel.pack(side="left", fill="y")
        self._session_panel.pack_propagate(False)
        self._session_panel.configure(width=self._session_panel_w)

        self._session_panel.on_select   = self._switch_session
        self._session_panel.on_close    = self._close_session
        self._session_panel.on_new      = self._new_session
        self._session_panel.on_dropdown = self._show_shell_picker
        self._session_panel.on_context  = self._show_session_menu

    # ── Scrollback / scroll handling ──────────────────────────────────────────

    def _on_scroll(self, *args) -> None:
        """Scrollbar drag — scroll through combined scrollback + screen view."""
        self._canvas.yview(*args)

    def _on_yscroll_update(self, first: str, last: str) -> None:
        self._scrollbar.set(first, last)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _draw_row(self, canvas_row: int, segments: list, tags: tuple = ()) -> None:
        """Draw one row of (text, fg, bg, bold) segments at the given canvas row index."""
        y = canvas_row * self._char_h
        col = 0
        for text, fg, bg, bold in segments:
            n = len(text)
            x = col * self._char_w
            w = n * self._char_w
            if bg != _DEFAULT_BG:
                self._canvas.create_rectangle(
                    x, y, x + w, y + self._char_h,
                    fill=bg, outline="", tags=tags,
                )
            font = self._bold_font if bold else self._font
            if text.isascii():
                # Pure ASCII: Consolas (and every terminal font) is truly
                # monospace for ASCII, so one canvas item is exact.
                self._canvas.create_text(
                    x, y, text=text, fill=fg, anchor="nw",
                    font=font, tags=tags,
                )
            else:
                # Non-ASCII (box-drawing, Unicode, etc.): centre each glyph
                # within its cell so that bold/regular and heavy/light chars
                # all align regardless of individual advance widths.
                half = self._char_w // 2
                for i, ch in enumerate(text):
                    self._canvas.create_text(
                        (col + i) * self._char_w + half, y, text=ch, fill=fg, anchor="n",
                        font=font, tags=tags,
                    )
            col += n

    def _char_at_cursor(self, segments: list, cursor_x: int) -> str:
        """Return the character at column cursor_x from a segment list."""
        col = 0
        for text, _fg, _bg, _bold in segments:
            if col <= cursor_x < col + len(text):
                return text[cursor_x - col]
            col += len(text)
        return " "

    def _draw_screen_rows(self) -> None:
        """Draw current pyte screen rows tagged 'live'. Draws cursor on top."""
        sb = self._sb_phys_rows
        screen_lines = self._screen_to_lines()
        cur_y = self._screen.cursor.y
        cur_x = self._screen.cursor.x
        for row_idx, segs in enumerate(screen_lines):
            canvas_row = sb + row_idx
            self._draw_row(canvas_row, segs, ("live",))
            if row_idx == cur_y:
                cx = cur_x * self._char_w
                cy = canvas_row * self._char_h
                self._canvas.create_rectangle(
                    cx, cy, cx + self._char_w, cy + self._char_h,
                    fill=_DEFAULT_FG, outline="", tags=("cursor", "live"),
                )
                self._canvas.create_text(
                    cx, cy,
                    text=self._char_at_cursor(segs, cur_x),
                    fill=_DEFAULT_BG, anchor="nw",
                    font=self._font,
                    tags=("cursor", "live"),
                )

    def _live_used_rows(self) -> int:
        """Number of pyte visible-buffer rows that contain content or the
        cursor — i.e. the rows worth scrolling over. Empty rows below this
        are excluded from the scrollregion so the user can't scroll past
        the last meaningful row."""
        last_used = self._screen.cursor.y
        for y in range(self._screen.lines - 1, last_used, -1):
            line = self._screen.buffer.get(y)
            if not line:
                continue
            for x in range(self._screen.columns):
                ch = line.get(x)
                if ch is None:
                    continue
                if (ch.data and ch.data != " ") or ch.bg != "default":
                    last_used = y
                    break
            if last_used > self._screen.cursor.y:
                break
        return last_used + 1

    def _update_scrollregion(self, canvas_h: int = 0) -> None:
        # Accept an explicit height from _do_resize to avoid a second
        # winfo_height() call that may return stale geometry mid-resize.
        if canvas_h <= 1:
            canvas_h = self._canvas.winfo_height()
        live_h = max(canvas_h, self._rows * self._char_h) if canvas_h > 1 else self._rows * self._char_h
        total_h = self._sb_phys_rows * self._char_h + live_h
        cw = max(self._cols * self._char_w, self._canvas.winfo_width())
        self._canvas.configure(scrollregion=(0, 0, cw, total_h))

    def _canvas_to_term(self, event) -> tuple:
        """Convert a canvas mouse event to (row, col) in terminal grid coords."""
        cx = self._canvas.canvasx(event.x)
        cy = self._canvas.canvasy(event.y)
        row = max(0, int(cy // self._char_h))
        col = max(0, min(int(cx // self._char_w), self._cols - 1))
        total_rows = self._sb_phys_rows + self._rows
        row = min(row, total_rows - 1)
        return row, col

    def _get_row_text(self, row_idx: int) -> str:
        """Return the plain text for a terminal row (scrollback or live screen)."""
        if row_idx < self._sb_phys_rows:
            if row_idx >= len(self._phys_to_log):
                return ""
            log_idx, c_start, c_end = self._phys_to_log[row_idx]
            if log_idx >= len(self._scrollback):
                return ""
            full = "".join(t for t, _fg, _bg, _bold in self._scrollback[log_idx])
            return full[c_start:c_end].rstrip()
        screen_idx = row_idx - self._sb_phys_rows
        lines = self._screen_to_lines()
        if 0 <= screen_idx < len(lines):
            return "".join(t for t, _fg, _bg, _bold in lines[screen_idx]).rstrip()
        return ""

    def _draw_selection(self) -> None:
        """Draw selection highlight rectangles (behind text via tag_lower)."""
        if not self._sel_row_start or not self._sel_row_end:
            return
        r1, c1 = self._sel_row_start
        r2, c2 = self._sel_row_end
        if (r1, c1) >= (r2, c2):
            return
        for row in range(r1, r2 + 1):
            if r1 == r2:
                x1, x2 = c1 * self._char_w, c2 * self._char_w
            elif row == r1:
                x1, x2 = c1 * self._char_w, self._cols * self._char_w
            elif row == r2:
                x1, x2 = 0, c2 * self._char_w
            else:
                x1, x2 = 0, self._cols * self._char_w
            if x1 >= x2:
                continue
            y1 = row * self._char_h
            self._canvas.create_rectangle(
                x1, y1, x2, y1 + self._char_h,
                fill="#264f78", outline="", tags=("sel",),
            )
        self._canvas.tag_lower("sel")

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

    def _reflow_live_buffer(self, old_cols: int) -> None:
        """Reflow pyte's live buffer from old_cols to self._screen.columns.

        Logical lines (rows joined by DECAWM idol_wrapped=True) are merged
        and re-broken at the new column width, matching VS Code terminal
        behaviour.  Cursor position is updated so pyte's tracked row/col
        stays consistent with PSReadLine's SIGWINCH cursor-up calculation.
        Only called when not in alt-screen mode (TUI apps handle their own
        SIGWINCH reflow).
        """
        import pyte.screens as _ps
        new_cols = self._screen.columns
        if old_cols == new_cols:
            return

        buffer       = self._screen.buffer
        default_char = self._screen.default_char
        num_rows     = self._screen.lines

        actual_keys = sorted(buffer.keys())
        if not actual_keys:
            return
        max_row = actual_keys[-1]

        cur_y = self._screen.cursor.y
        cur_x = min(self._screen.cursor.x, old_cols - 1)

        def _is_real_wrap(row_obj) -> bool:
            if row_obj is None or not getattr(row_obj, "idol_wrapped", False):
                return False
            last = row_obj.get(old_cols - 1)
            if last is None:
                return False
            return (bool(last.data and last.data != " ")
                    or last.fg != "default" or last.bg != "default")

        # ── Extract logical lines ─────────────────────────────────────────
        # Each entry: (list[Char], cursor_offset_into_line | None)
        logical: list = []
        i = 0
        while i <= max_row:
            chars:    list     = []
            cur_off: int | None = None
            j = i
            while True:
                row = buffer.get(j)
                if j == cur_y:
                    cur_off = len(chars) + cur_x
                if row is not None:
                    for col in range(old_cols):
                        chars.append(row[col])    # StaticDefaultDict → default for missing
                else:
                    chars.extend([default_char] * old_cols)
                wraps = _is_real_wrap(row)
                j += 1
                if not wraps or j > max_row:
                    break
            # Strip trailing default-space cells (keep up to cursor position)
            tail = len(chars)
            while tail > 0 and chars[tail - 1] == default_char:
                tail -= 1
            if cur_off is not None:
                tail = max(tail, cur_off)
            chars = chars[:tail]
            logical.append((chars, cur_off))
            i = j

        # ── Re-wrap at new_cols ───────────────────────────────────────────
        new_buf: dict = {}
        r = 0
        new_cur_y = cur_y
        new_cur_x = cur_x

        for chars, cur_off in logical:
            if not chars:
                new_buf[r] = _ps.StaticDefaultDict(default_char)
                r += 1
                continue
            total = len(chars)
            idx   = 0
            while True:
                chunk = chars[idx:idx + new_cols]
                wraps = idx + new_cols < total
                line  = _ps.StaticDefaultDict(default_char)
                line.idol_wrapped = wraps
                for col, ch in enumerate(chunk):
                    if ch != default_char:
                        line[col] = ch
                # Track cursor: inclusive upper-bound so an offset exactly at
                # the end of a full chunk matches here (gets bumped below).
                if cur_off is not None:
                    lo, hi = idx, idx + len(chunk)
                    if lo <= cur_off <= hi:
                        new_cur_y = r
                        new_cur_x = cur_off - idx
                new_buf[r] = line
                r += 1
                idx += new_cols
                if not wraps:
                    break

        # Cursor one past the end of a full-width row → move to next row col 0
        if new_cur_x >= new_cols:
            new_cur_y += 1
            new_cur_x  = 0
            if new_cur_y not in new_buf:
                blank = _ps.StaticDefaultDict(default_char)
                blank.idol_wrapped = False
                new_buf[new_cur_y] = blank

        # ── Commit ───────────────────────────────────────────────────────
        buffer.clear()
        for row_idx, line in new_buf.items():
            buffer[row_idx] = line

        self._screen.cursor.y = max(0, min(new_cur_y, num_rows - 1))
        self._screen.cursor.x = max(0, min(new_cur_x, new_cols - 1))
        self._screen.dirty.update(range(num_rows))

    def _row_effective_wrap(self, line, wrapped: bool) -> bool:
        """Return True only if this row actually wrap-continues onto the next.
        Pyte's idol_wrapped flag is set when the cursor reached col == columns,
        but that state persists even if the line is later cleared, the cursor
        is repositioned away, or PSReadLine redraws the prompt over the row.
        Trust the flag ONLY if the row's last cell currently has content,
        which is the requirement for a real visual wrap."""
        if not wrapped:
            return False
        last_cell = line.get(self._screen.columns - 1)
        if last_cell is None:
            return False
        data = last_cell.data
        if data and data != " ":
            return True
        if last_cell.fg != "default" or last_cell.bg != "default":
            return True
        return False

    def _row_segments_for_history(self, line, wrapped: bool) -> list:
        """Build (text, fg, bg, bold) segments for one pyte history row.
        Trailing default-attribute spaces are always stripped so the logical
        line ends at its real content. We strip on wrapped rows too: shells
        like PSReadLine that redraw prompts can leave cells in a "wrapped but
        empty trailing" state where the wrap flag was set during the original
        fill but cells were subsequently erased — keeping those cells leaks
        as visible left-side gutter on reflowed continuation rows."""
        segments: list = []
        run_text = ""
        run_fg = _DEFAULT_FG
        run_bg = _DEFAULT_BG
        run_bold = False
        for col_idx in range(self._screen.columns):
            char = line[col_idx]
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

        while segments:
            t, fg, bg, bold = segments[-1]
            if fg != _DEFAULT_FG or bg != _DEFAULT_BG or bold:
                break
            stripped = t.rstrip(" ")
            if stripped == t:
                break
            if stripped:
                segments[-1] = (stripped, fg, bg, bold)
                break
            segments.pop()
        return segments

    def _split_segments(self, segments: list, cols: int) -> list:
        """Split a logical line of segments into a list of (phys_segments, width)
        rows, each at most `cols` characters wide. Empty input → one empty row."""
        if cols <= 0:
            cols = 1
        rows: list = []
        cur_segs: list = []
        cur_w = 0
        for text, fg, bg, bold in segments:
            idx = 0
            while idx < len(text):
                if cur_w >= cols:
                    rows.append((cur_segs, cur_w))
                    cur_segs = []
                    cur_w = 0
                take = min(cols - cur_w, len(text) - idx)
                cur_segs.append((text[idx:idx + take], fg, bg, bold))
                cur_w += take
                idx += take
        if cur_segs or not rows:
            rows.append((cur_segs, cur_w))
        return rows

    def _draw_logical_line(self, segments: list, canvas_row_start: int,
                           tags: tuple) -> tuple:
        """Wrap a logical line at self._cols and draw each physical chunk.
        Returns (n_physical_rows, [width_per_row])."""
        chunks = self._split_segments(segments, self._cols)
        for i, (phys_segs, _w) in enumerate(chunks):
            self._draw_row(canvas_row_start + i, phys_segs, tags)
        return len(chunks), [w for _segs, w in chunks]

    def _redraw_full(self, canvas_h: int = 0) -> None:
        """Full redraw from scratch (restart / clear / resize). Wraps scrollback
        at the current self._cols so window/sash resize reflows historical lines."""
        if self._render_suppressed:
            return
        self._canvas.delete("all")
        self._sb_phys_rows = 0
        self._phys_to_log = []
        for log_idx, segs in enumerate(self._scrollback):
            n_rows, widths = self._draw_logical_line(
                segs, self._sb_phys_rows, ("sb",))
            char_off = 0
            for w in widths:
                self._phys_to_log.append((log_idx, char_off, char_off + w))
                char_off += w
            self._sb_phys_rows += n_rows
        self._scrollback_drawn = len(self._scrollback)
        self._draw_screen_rows()
        self._draw_selection()
        self._update_scrollregion(canvas_h)
        self._canvas.yview_moveto(1.0)

    def _redraw_screen(self) -> None:
        """Rewrite only the live screen rows (scrollback already drawn on canvas)."""
        if self._render_suppressed:
            return
        self._canvas.delete("live")
        self._canvas.delete("sel")
        self._draw_screen_rows()
        self._draw_selection()
        self._update_scrollregion()

    def _flush_scrollback(self) -> None:
        """Pull rows out of pyte history, merging wrap-continued rows into one
        logical line so they can reflow at the current canvas width."""
        if not self._screen.history.top:
            return
        # If the last logical line is "open" (awaits continuation), the first
        # row pulled from history extends it — that line's physical row count
        # may grow, so we redraw fully rather than just appending new rows.
        needs_full = bool(self._scrollback_open and self._scrollback)
        while self._screen.history.top:
            row = self._screen.history.top.popleft()
            wrapped = self._row_effective_wrap(
                row, bool(getattr(row, "idol_wrapped", False)))
            segs = self._row_segments_for_history(row, wrapped)
            if self._scrollback_open and self._scrollback:
                self._scrollback[-1].extend(segs)
            else:
                self._scrollback.append(segs)
            self._scrollback_open = wrapped

        # Cap scrollback length (logical lines). Trim forces full redraw.
        if len(self._scrollback) > self._SCROLLBACK:
            trim = len(self._scrollback) - self._SCROLLBACK
            self._scrollback = self._scrollback[trim:]
            self._scrollback_drawn = max(0, self._scrollback_drawn - trim)
            needs_full = True

        if self._render_suppressed:
            return

        if needs_full:
            self._redraw_full()
            return

        # Incremental: draw only the newly-added logical lines.
        for i in range(self._scrollback_drawn, len(self._scrollback)):
            n_rows, widths = self._draw_logical_line(
                self._scrollback[i], self._sb_phys_rows, ("sb",))
            char_off = 0
            for w in widths:
                self._phys_to_log.append((i, char_off, char_off + w))
                char_off += w
            self._sb_phys_rows += n_rows
        self._scrollback_drawn = len(self._scrollback)

    # ── PTY I/O ───────────────────────────────────────────────────────────────

    def _read_loop(self, sid: int, pty) -> None:
        while pty.isalive():
            try:
                chunk = pty.read(4096)
                if chunk:
                    if isinstance(chunk, bytes):
                        chunk_str = chunk.decode("utf-8", errors="replace")
                    else:
                        chunk_str = chunk
                    chunk_str = self._process_markers(chunk_str)
                    self._queue.put((sid, chunk_str.encode("utf-8", errors="replace")))
            except EOFError:
                break
            except Exception:
                break
        self._queue.put((sid, None))

    def _poll(self) -> None:
        active_chunks = []
        active_sentinel = False
        try:
            while True:
                sid, item = self._queue.get_nowait()
                sess_key = self._sid_to_key.get(sid)
                if sess_key is None:
                    continue   # truly stale SID (killed session), discard
                if sess_key == self._active_shell_key:
                    if item is None:
                        active_sentinel = True
                        break
                    active_chunks.append(item)
                else:
                    # Background session — buffer into its own pyte screen
                    sess = self._sessions.get(sess_key)
                    if sess:
                        if item is None:
                            sess["running"] = False
                        else:
                            sess["stream"].feed(item)
        except queue.Empty:
            pass

        if active_chunks:
            for chunk in active_chunks:
                self._stream.feed(chunk)
            if not self._render_suppressed:
                # Capture scroll position before redraw — scrollback growth
                # moves live rows down in canvas space; we re-pin if the
                # user was already at the bottom so TUI title bars stay flush
                # with the top of the visible area.
                canvas_h = self._canvas.winfo_height()
                top_y = self._canvas.canvasy(0)
                live_start_y = self._sb_phys_rows * self._char_h
                was_at_bottom = canvas_h <= 1 or top_y >= live_start_y - self._char_h

                old_sb_rows = self._sb_phys_rows
                if self._screen.in_alt_screen:
                    # Alternate screen: drain pyte history without persisting
                    # to scrollback so TUI output never corrupts the main buffer.
                    while self._screen.history.top:
                        self._screen.history.top.popleft()
                else:
                    self._flush_scrollback()
                delta_sb = self._sb_phys_rows - old_sb_rows

                had_cursor_up = self._screen.had_cursor_up
                cursor_up_min_y = self._screen.cursor_up_min_y
                self._screen.had_cursor_up = False
                self._screen.cursor_up_min_y = None

                self._redraw_screen()
                if was_at_bottom:
                    if (not self._screen.in_alt_screen
                            and had_cursor_up
                            and cursor_up_min_y is not None):
                        # Non-alt-screen TUI app (Rich Live, etc.) repainted by
                        # cursor-up + redraw.  Scroll so the top of the redrawn
                        # block (= cursor_up_min_y in live-screen coords) is at
                        # the top of the viewport, making the table's top border
                        # visible.  PSReadLine cursor-up stays near the bottom
                        # (cursor_up_min_y ≈ rows-2), so frac≈1.0 and Tk clamps
                        # it to the true bottom — no visible change for PS.
                        total_h = (self._sb_phys_rows * self._char_h
                                   + max(canvas_h, self._rows * self._char_h))
                        target_y = (self._sb_phys_rows + cursor_up_min_y) * self._char_h
                        frac = min(1.0, target_y / total_h) if total_h > 0 else 0.0
                        self._canvas.yview_moveto(frac)
                    else:
                        self._canvas.yview_moveto(1.0)

        if active_sentinel:
            self._running = False
            self._scrollback.append([("[Process exited]", _DEFAULT_FG, _DEFAULT_BG, False)])
            self._redraw_full()

        self.after(30, self._poll)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_key(self, event) -> str:
        char = event.char
        if char and char not in ("\r", "\n", "\x08"):
            self._sel_row_start = None
            self._sel_row_end   = None
            self._canvas.delete("sel")
            self.send(char)
        return "break"

    def _on_mousewheel(self, event) -> str:
        """Handle mouse wheel — send SGR sequences to TUI apps, scroll view at shell."""
        up = event.num == 4 or (hasattr(event, "delta") and event.delta > 0)

        if self._screen.mouse_enabled:
            # App has mouse tracking on — send SGR wheel sequence at screen centre
            col = max(1, self._cols // 2)
            row = max(1, self._rows // 2)
            btn = 64 if up else 65
            self.send(f"\x1b[<{btn};{col};{row}M")
        else:
            # Normal shell — scroll the view
            self._canvas.yview_scroll(-3 if up else 3, "units")

        return "break"

    def _on_paste(self, _=None) -> str:
        try:
            text = self._canvas.clipboard_get()
            if text:
                self.send(text)
        except Exception:
            pass
        return "break"

    def _term_coords(self, event) -> tuple[int, int]:
        """Convert canvas event to (screen_row, col) — row relative to live screen top."""
        canvas_row, col = self._canvas_to_term(event)
        screen_row = canvas_row - self._sb_phys_rows
        return max(0, min(screen_row, self._rows - 1)), max(0, min(col, self._cols - 1))

    def _send_mouse(self, btn: int, row: int, col: int, release: bool = False) -> None:
        """Send an SGR mouse event: \x1b[<btn;col;rowM (press) or m (release)."""
        suffix = "m" if release else "M"
        self.send(f"\x1b[<{btn};{col + 1};{row + 1}{suffix}")

    def _on_click(self, event) -> str:
        dismiss = getattr(self, "_ctx_overlay_dismiss", None)
        if dismiss:
            dismiss()
        self._canvas.focus_set()
        if self._screen.mouse_enabled:
            row, col = self._term_coords(event)
            self._send_mouse(0, row, col)
            return "break"
        self._sel_anchor    = self._canvas_to_term(event)
        self._sel_row_start = None
        self._sel_row_end   = None
        self._canvas.delete("sel")
        return "break"

    def _on_release(self, event) -> str:
        if self._screen.mouse_enabled:
            row, col = self._term_coords(event)
            self._send_mouse(0, row, col, release=True)
        return "break"

    def _on_drag(self, event) -> str:
        if self._screen.mouse_enabled:
            row, col = self._term_coords(event)
            self._send_mouse(32, row, col)  # btn 32 = left-button motion
            return "break"
        if not self._sel_anchor:
            return "break"
        cur    = self._canvas_to_term(event)
        anchor = self._sel_anchor
        if anchor <= cur:
            self._sel_row_start, self._sel_row_end = anchor, cur
        else:
            self._sel_row_start, self._sel_row_end = cur, anchor
        self._canvas.delete("sel")
        self._draw_selection()
        return "break"

    def _copy_selection(self) -> None:
        if not self._sel_row_start or not self._sel_row_end:
            return
        r1, c1 = self._sel_row_start
        r2, c2 = self._sel_row_end
        if (r1, c1) >= (r2, c2):
            return
        lines = []
        for row in range(r1, r2 + 1):
            text = self._get_row_text(row)
            if r1 == r2:
                text = text[c1:c2]
            elif row == r1:
                text = text[c1:]
            elif row == r2:
                text = text[:c2]
            lines.append(text)
        result = "\n".join(lines)
        if result.strip():
            try:
                self._canvas.clipboard_clear()
                self._canvas.clipboard_append(result)
            except Exception:
                pass

    def _show_context_menu(self, event) -> str:
        if self._screen.mouse_enabled:
            # Forward right-click to the TUI app as SGR button 2
            row, col = self._term_coords(event)
            self._send_mouse(2, row, col)
            return "break"
        has_sel = bool(self._sel_row_start and self._sel_row_end
                       and self._sel_row_start < self._sel_row_end)
        items = [
            ("Copy          Ctrl+Shift+C", self._copy_selection, has_sel),
            ("Paste        Ctrl+Shift+V",  self._on_paste,       True),
        ]
        self._show_overlay(event.x_root, event.y_root, items)
        return "break"

    def _show_overlay(self, x_root: int, y_root: int, items: list) -> None:
        existing_dismiss = getattr(self, "_ctx_overlay_dismiss", None)
        if existing_dismiss:
            existing_dismiss()

        top = self._canvas.winfo_toplevel()
        rel_x = x_root - top.winfo_rootx()
        rel_y = y_root - top.winfo_rooty()

        overlay = tk.Frame(top, bg="#2d2d2d",
                           highlightthickness=1, highlightbackground="#007acc")
        self._ctx_overlay = overlay

        top_bid: list = []

        def _dismiss():
            self._ctx_overlay = None
            self._ctx_overlay_dismiss = None
            try:
                overlay.destroy()
            except Exception:
                pass
            if top_bid:
                try:
                    top.unbind("<ButtonRelease-1>", top_bid[0])
                except Exception:
                    pass

        self._ctx_overlay_dismiss = _dismiss

        def _global_click(e):
            w = e.widget
            while w is not None:
                if w is overlay:
                    return
                try:
                    w = w.master
                except AttributeError:
                    break
            _dismiss()

        for label, cmd, enabled in items:
            fg = "#cccccc" if enabled else "#555555"
            lbl = tk.Label(overlay, text=label, bg="#2d2d2d", fg=fg,
                           font=(UI_FONT, 9), anchor="w", padx=12, pady=3)
            lbl.pack(fill="x")
            if enabled:
                def _enter(e, l=lbl):  l.config(bg="#094771", fg="#ffffff")
                def _leave(e, l=lbl):  l.config(bg="#2d2d2d", fg="#cccccc")
                def _click(e, c=cmd):
                    _dismiss()
                    c()
                lbl.bind("<Enter>",           _enter)
                lbl.bind("<Leave>",           _leave)
                lbl.bind("<ButtonRelease-1>", _click)

        overlay.place(x=rel_x, y=rel_y)
        overlay.lift()
        top_bid.append(top.bind("<ButtonRelease-1>", _global_click, add=True))

    def _on_restart(self) -> None:
        cmd = self._session_meta.get(self._active_shell_key, {}).get("cmd")
        self.start(cmd, cwd=self._cwd)

    # ── Session model ─────────────────────────────────────────────────────────

    def _new_session_key(self) -> str:
        self._session_counter += 1
        return f"s{self._session_counter}"

    def _dedup_name(self, base: str) -> str:
        existing = {m["display_name"] for m in self._session_meta.values()}
        if base not in existing:
            return base
        i = 2
        while f"{base} ({i})" in existing:
            i += 1
        return f"{base} ({i})"

    def _new_session(self, shell_dict: dict | None = None,
                     cwd: str | None = None) -> None:
        """Create and switch to a new terminal session."""
        if not self._detected_shells:
            self._detected_shells = _detect_available_shells()
        if shell_dict is None:
            shell_dict = self._detected_shells[0] if self._detected_shells else {
                "name": "Shell", "cmd": _default_shell(), "color": "#8a8a8a"
            }
        if cwd is not None:
            self._cwd = cwd
        key = self._new_session_key()
        self._session_meta[key] = {
            "display_name": self._dedup_name(shell_dict["name"]),
            "cmd":          shell_dict["cmd"],
            "icon_color":   shell_dict["color"],
        }
        self._session_keys.append(key)
        if not self._run_shell_key:
            self._run_shell_key = key
        self._switch_session(key)

    def _switch_session(self, key: str) -> None:
        """Switch to a different shell session, persisting the current one."""
        if key == self._active_shell_key:
            return
        # Snapshot current session (only if we actually have one running)
        if self._active_shell_key:
            if self._clear_timer:
                self.after_cancel(self._clear_timer)
                self._clear_timer = None
            self._sessions[self._active_shell_key] = {
                "pty":               self._pty,
                "screen":            self._screen,
                "stream":            self._stream,
                "scrollback":        self._scrollback,
                "scrollback_drawn":  self._scrollback_drawn,
                "scrollback_open":   self._scrollback_open,
                "session_id":        self._session_id,
                "running":           self._running,
                "render_suppressed": self._render_suppressed,
                "raw_buf":           self._raw_buf,
                "cwd_current":       self._cwd_current,
                "venv_active":       self._venv_active,
                "state_file":        self._state_file,
                "state_file_mtime":  self._state_file_mtime,
            }
            self._pty     = None
            self._running = False

        # Restore existing session or start fresh
        if key in self._sessions and self._sessions[key]["running"]:
            sess = self._sessions.pop(key)
            self._pty                   = sess["pty"]
            self._screen                = sess["screen"]
            self._stream                = sess["stream"]
            self._scrollback            = sess["scrollback"]
            self._scrollback_drawn      = sess.get("scrollback_drawn", 0)
            self._scrollback_open       = sess.get("scrollback_open", False)
            # _sb_phys_rows + _phys_to_log are rebuilt by _redraw_full below
            self._sb_phys_rows          = 0
            self._phys_to_log           = []
            self._session_id            = sess["session_id"]
            self._running               = sess["running"]
            self._render_suppressed     = sess["render_suppressed"]
            self._raw_buf               = sess["raw_buf"]
            self._cwd_current           = sess["cwd_current"]
            self._venv_active           = sess["venv_active"]
            self._state_file            = sess["state_file"]
            self._state_file_mtime      = sess["state_file_mtime"]
            self._active_shell_key      = key
            self._refresh_venv_state()
            self._redraw_full()
            _cmd = (self._session_meta.get(key) or {}).get("cmd") or []
            _name = os.path.basename(_cmd[0]).lower() if _cmd else ""
            # Only PowerShell/pwsh treats \x0c as ClearScreen; cmd echoes "^L"
            # and bash treats it as form-feed → wipes the visible buffer.
            if platform.system() == "Windows" and any(s in _name for s in ("powershell", "pwsh")):
                self.after(150, lambda: self.send_text("\x0c"))
            if platform.system() == "Windows" and self._state_file and self._running:
                self.after(500, self._poll_state_file)
        else:
            self._active_shell_key = key
            cmd = (self._session_meta.get(key) or {}).get("cmd")
            self.start(cmd, cwd=self._cwd)

        self._refresh_session_panel()

    def _close_session(self, key: str) -> None:
        """Kill and remove a session. Won't close the last session."""
        if len(self._session_keys) <= 1:
            return
        if key == self._active_shell_key:
            idx = self._session_keys.index(key)
            other = self._session_keys[idx - 1 if idx > 0 else idx + 1]
            self._switch_session(other)
        # Kill the background session (now safely not active)
        sess = self._sessions.pop(key, None)
        if sess and sess.get("pty"):
            try:
                sess["pty"].terminate(force=True)
            except Exception:
                pass
        if key in self._session_keys:
            self._session_keys.remove(key)
        self._session_meta.pop(key, None)
        if self._run_shell_key == key:
            self._run_shell_key = self._active_shell_key
        self._refresh_session_panel()

    def _set_run_session(self, key: str) -> None:
        self._run_shell_key = key
        self._refresh_session_panel()

    def send_to_run_session(self, text: str) -> None:
        """Send text to the designated run session, switching to it if needed."""
        target = self._run_shell_key or self._active_shell_key
        if target and target != self._active_shell_key:
            self._switch_session(target)
        self.send_text(text)

    def _refresh_session_panel(self) -> None:
        if not hasattr(self, "_session_panel"):
            return
        running_keys = {k for k, v in self._sessions.items() if v.get("running")}
        if self._running and self._active_shell_key:
            running_keys.add(self._active_shell_key)
        vm = {
            k: {
                "display_name": self._session_meta[k]["display_name"],
                "icon_color":   self._session_meta[k]["icon_color"],
                "running":      k in running_keys,
            }
            for k in self._session_keys if k in self._session_meta
        }
        self._session_panel.refresh(vm, self._active_shell_key, self._run_shell_key)

    def _show_shell_picker(self, event=None) -> None:
        """Show overlay to pick a shell type for a new session."""
        if not self._detected_shells:
            self._detected_shells = _detect_available_shells()
        items = [
            (sd["name"], lambda sd=sd: self._new_session(sd), True)
            for sd in self._detected_shells
        ]
        x = self._session_panel.winfo_rootx()
        y = self._session_panel.winfo_rooty()
        self._show_overlay(x, y, items)

    def _show_session_menu(self, key: str, x_root: int, y_root: int) -> None:
        """Right-click context menu on a session row."""
        items = [
            ("Set as Run Session", lambda k=key: self._set_run_session(k), True),
        ]
        self._show_overlay(x_root, y_root, items)

    # ── Ghost sash ────────────────────────────────────────────────────────────

    _MIN_PANEL_W = 80

    def _on_sash_enter(self, _event) -> None:
        if not self._sash_dragging:
            self._sash.configure(bg="#007acc")

    def _on_sash_leave(self, _event) -> None:
        if not self._sash_dragging:
            self._sash.configure(bg="#2d2d30")

    def _on_sash_press(self, event) -> None:
        self._sash_dragging = True
        self._sash_start_x  = event.x_root
        self._sash_ghost = tk.Frame(self._body_frame, bg="#007acc", width=2)
        sash_x = self._sash.winfo_x()
        self._sash_ghost.place(x=sash_x, y=0,
                               height=self._body_frame.winfo_height())

    def _on_sash_drag(self, event) -> None:
        if not self._sash_ghost:
            return
        body_w = self._body_frame.winfo_width()
        dx = event.x_root - self._sash_start_x
        sash_x = self._sash.winfo_x()
        new_x = sash_x + dx
        new_x = max(self._MIN_PANEL_W, min(body_w - self._MIN_PANEL_W, new_x))
        self._sash_ghost.place(x=new_x, y=0,
                               height=self._body_frame.winfo_height())

    def _on_sash_release(self, event) -> None:
        self._sash_dragging = False
        self._sash.configure(bg="#2d2d30")
        if not self._sash_ghost:
            return
        ghost_x = self._sash_ghost.winfo_x()
        self._sash_ghost.destroy()
        self._sash_ghost = None
        body_w = self._body_frame.winfo_width()
        new_panel_w = max(self._MIN_PANEL_W, body_w - ghost_x - 4)
        self._session_panel_w = new_panel_w
        self._session_panel.configure(width=new_panel_w)
        self._trigger_resize_now()
        self._refresh_session_panel()

    # ── Panel animation ────────────────────────────────────────────────────────

    def _trigger_resize_now(self) -> None:
        """Cancel any pending debounce, flush geometry, then resize immediately."""
        if self._resize_job:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        self.update_idletasks()
        self._do_resize()

    def _animate_panel(self, target_w: int, cur_w: int, gen: int) -> None:
        if gen != self._anim_gen:
            return   # stale callback — a newer animation superseded this one
        if cur_w == target_w:
            if target_w == 0:
                self._sash.pack_forget()
                self._session_panel.pack_forget()
            self._trigger_resize_now()
            return
        nw = min(cur_w + 20, target_w) if target_w > cur_w else max(cur_w - 20, target_w)
        self._session_panel.configure(width=nw)
        self.after(12, lambda: self._animate_panel(target_w, nw, gen))

    def _toggle_panel(self) -> None:
        self._anim_gen += 1
        gen = self._anim_gen
        if self._panel_visible:
            self._panel_visible = False
            cur = self._session_panel.winfo_width() or self._session_panel_w
            self._animate_panel(0, cur, gen)
        else:
            self._panel_visible = True
            if not self._sash.winfo_ismapped():
                self._sash.pack(side="left", fill="y")
                self._session_panel.pack(side="left", fill="y")
            self._session_panel.configure(width=0)
            # after(0) lets Tk process the pack/configure before we start reading widths
            self.after(0, lambda: self._animate_panel(self._session_panel_w, 0, gen))

    # ── Venv tracking ─────────────────────────────────────────────────────────

    def _send_silently(self, text: str) -> None:
        """Write to the shell with TTY echo disabled so the command never appears
        in the terminal output.  Unix only — Windows falls back to plain send."""
        if not (self._running and self._pty):
            return
        sent = False
        if platform.system() != "Windows":
            try:
                import termios
                fd = self._pty.fd
                attrs = termios.tcgetattr(fd)
                silent = list(attrs)
                silent[3] = silent[3] & ~termios.ECHO
                termios.tcsetattr(fd, termios.TCSANOW, silent)
                self._pty.write(text)
                self.after(200, lambda: self._restore_echo(fd, attrs))
                sent = True
            except Exception:
                pass
        if not sent:
            self.send(text)

    def _restore_echo(self, fd: int, attrs) -> None:
        try:
            import termios
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except Exception:
            pass

    @staticmethod
    def _win_path_to_msys(win_path: str) -> str:
        """Convert C:\\path\\to\\dir → /c/path/to/dir for MSYS2/Git Bash."""
        p = Path(win_path)
        drive = p.drive  # e.g. "C:"
        if drive:
            letter = drive.rstrip(":").lower()
            rest = str(p)[len(drive):].replace("\\", "/")
            return f"/{letter}{rest}"
        return str(p).replace("\\", "/")

    @staticmethod
    def _msys_to_win_path(posix_path: str) -> str:
        """Convert /c/Users/... → C:/Users/... for filesystem ops on Windows."""
        if (len(posix_path) >= 3 and posix_path[0] == "/"
                and posix_path[1].isalpha() and posix_path[2] == "/"):
            return posix_path[1].upper() + ":/" + posix_path[3:]
        return posix_path

    def _auto_activate_venv(self, cwd: str, shell_name: str) -> None:
        """If a venv exists under *cwd*, source its activate script in the
        live shell so the prompt comes up already inside it. Supports
        PowerShell/pwsh (Activate.ps1) and bash/zsh (bin/activate). For
        bash-like shells on Windows, Scripts/activate is avoided because it
        calls cygpath (Cygwin-only); instead VIRTUAL_ENV and PATH are set
        directly using MSYS2-compatible paths. Skipped for cmd, sh, dash."""
        if not (self._running and self._pty):
            return
        is_pwsh = "powershell" in shell_name or "pwsh" in shell_name
        is_bashlike = ("bash" in shell_name or "zsh" in shell_name) and "rbash" not in shell_name
        if not (is_pwsh or is_bashlike):
            return
        subpaths = ("Scripts/Activate.ps1",) if is_pwsh else ("bin/activate", "Scripts/activate")
        activate: Path | None = None
        for name in (".venv", "venv", "env", ".env"):
            base = Path(cwd) / name
            for sub in subpaths:
                cand = base / sub
                if cand.is_file():
                    activate = cand
                    break
            if activate:
                break
        if not activate:
            return
        self._venv_auto_activated = True
        if is_pwsh:
            # Set-ExecutionPolicy -Scope Process allows running the unsigned
            # Activate.ps1 without touching the system-wide policy (same as VS Code).
            self._send_silently(f'Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned\r')
            self._send_silently(f'& "{activate}"\r')
        elif is_bashlike and platform.system() == "Windows" and "Scripts" in activate.parts:
            # Scripts/activate for Windows venvs internally calls cygpath, which is
            # Cygwin-only and not available in MSYS2/Git Bash. Replicate what
            # activate does (set VIRTUAL_ENV, prepend Scripts to PATH) directly.
            venv_dir = self._win_path_to_msys(str(activate.parent.parent))
            scripts_dir = self._win_path_to_msys(str(activate.parent))
            self._send_silently(
                f'export VIRTUAL_ENV="{venv_dir}"; '
                f'export PATH="{scripts_dir}:$PATH"; '
                f'unset PYTHONHOME\r'
            )
        else:
            self._send_silently(f'source "{activate.as_posix()}"\r')
        self._fire_venv_activate(str(activate))

    def _inject_shell_hooks(self) -> None:
        """Inject CWD + VENV reporting into the running shell."""
        if not self._running:
            return
        shell_cmd = (self._session_meta.get(self._active_shell_key) or {}).get("cmd") or _default_shell()
        shell_name = os.path.basename(shell_cmd[0]).lower() if shell_cmd else ""
        _KNOWN_SHELLS = ("powershell", "pwsh", "cmd", "bash", "zsh", "sh")
        if not any(s in shell_name for s in _KNOWN_SHELLS):
            return   # REPL or unknown program — skip hook injection
        if "cmd" in shell_name:
            return   # cmd has no per-prompt callback; injecting PS syntax would error

        if "powershell" in shell_name or "pwsh" in shell_name:
            # Write CWD/VENV to a temp file instead of stdout — avoids any PTY
            # cursor/encoding interference; Python polls the file every 500 ms.
            import tempfile
            state_path = os.path.join(tempfile.gettempdir(), "idol_state.txt")
            # Escape backslashes for embedding in a PowerShell string
            ps_path = state_path.replace("\\", "\\\\")
            self._state_file = state_path
            self._state_file_mtime = 0.0
            self.after(500, self._poll_state_file)
            hook = (
                'function prompt {'
                ' $p = $PWD.Path;'
                ' $v = if ($env:VIRTUAL_ENV) { $env:VIRTUAL_ENV } else { "" };'
                f' [System.IO.File]::WriteAllText("{ps_path}", "$p`n$v");'
                ' Write-Host -NoNewline "$([char]27)]133;D;$([int]$LASTEXITCODE)$([char]7)";'
                ' if (-not $global:_idol_cleared) { $global:_idol_cleared = $true; clear };'
                ' "PS $p> "'
                '}\r'
            )
        elif "zsh" in shell_name:
            hook = (
                'function _idol_prompt() {'
                ' local _ec=$?;'
                ' printf "\\e]133;D;%d\\a" "$_ec";'
                ' printf "\\e]7;file://%s%s\\a" "$HOST" "$PWD";'
                ' printf "\\e]7776;%s\\a" "${VIRTUAL_ENV:-}";'
                '};'
                ' precmd_functions=(_idol_prompt "${precmd_functions[@]}")\r'
            )
        else:
            # bash / sh (including Git Bash on Windows)
            # On Windows the MSYS2 runtime may skip PATH conversion when launched
            # via ConPTY, leaving /usr/bin off the path. Inject it directly if
            # cygpath (a reliable canary) isn't reachable yet.
            msys_fix = ""
            if platform.system() == "Windows" and "bash" in shell_name:
                msys_fix = (
                    'type -P cygpath >/dev/null 2>&1 ||'
                    ' export PATH="/usr/local/bin:/usr/bin:/bin:/mingw64/bin:$PATH"; '
                )
            hook = (
                f'{msys_fix}'
                'export PROMPT_COMMAND=\'_ec=$?;'
                ' printf "\\e]133;D;%d\\a" "$_ec";'
                ' printf "\\e]7;file://%s%s\\a" "$HOSTNAME" "$PWD";'
                ' printf "\\e]7776;%s\\a" "${VIRTUAL_ENV:-}"\'\r'
            )
        self._send_silently(hook)

    def _poll_state_file(self) -> None:
        """Windows-only: read CWD/VENV from temp file written by the PS prompt hook."""
        if not self._running or not self._state_file:
            return
        try:
            mtime = os.path.getmtime(self._state_file)
            if mtime != self._state_file_mtime:
                self._state_file_mtime = mtime
                with open(self._state_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
                if lines:
                    self._cwd_current = lines[0].strip()
                    self._venv_active = lines[1].strip() if len(lines) > 1 else ""
                    self._refresh_venv_state()
        except Exception:
            pass
        self.after(500, self._poll_state_file)

    def _process_markers(self, raw: str) -> str:
        """Strip IDOL-private OSC sequences from raw PTY output and fire callbacks.

        OSC 133   — shell integration: command finished + exit code
        OSC 7     — CWD (file:// URI)
        OSC 7776  — IDOL private: active venv path (replaces in-band IDOL_VENV: line)

        Windows: OSC 7 / 7776 are never emitted; CWD/VENV come from a temp file."""

        # ── OSC 133 shell integration (prompt appearing = command finished) ──
        m133 = re.search(r'\x1b\]133;[A-Z](?:;(\d*))?(?:\x07|\x1b\\)?', raw)
        if m133:
            g = m133.group(1)
            exit_code = int(g) if g else None
            if self._waiting_first_prompt:
                # Shell hook fired for the first time — setup is done. Cancel the
                # fallback timer and show a clean render right now.
                self._waiting_first_prompt = False
                if self._clear_timer:
                    self.after_cancel(self._clear_timer)
                    self._clear_timer = None
                self.after(0, self._clear_screen_direct)
            else:
                self.after(0, lambda ec=exit_code: self._on_shell_command_done(ec))
        raw = re.sub(r'\x1b\]133;[A-Z](?:;\d*)?(?:\x07|\x1b\\)?', '', raw)

        # ── OSC 7: CWD  (file://host/path) ───────────────────────────────────
        for m in re.finditer(r'\x1b\]7;file://[^/]*(/[^\x07\x1b]*)\x07', raw):
            self._cwd_current = m.group(1)
            self.after(0, self._refresh_venv_state)
        raw = re.sub(r'\x1b\]7;[^\x07]*\x07', '', raw)

        # ── OSC 7776: IDOL venv path ──────────────────────────────────────────
        venv_changed = False
        for m in re.finditer(r'\x1b\]7776;([^\x07\x1b]*)(?:\x07|\x1b\\)?', raw):
            self._venv_active = m.group(1).strip()
            venv_changed = True
        raw = re.sub(r'\x1b\]7776;[^\x07\x1b]*(?:\x07|\x1b\\)?', '', raw)
        if venv_changed:
            self.after(0, self._refresh_venv_state)

        return raw

    def _on_shell_command_done(self, exit_code: Optional[int] = None) -> None:
        if self.on_command_done:
            self.on_command_done(exit_code)

    def _refresh_venv_state(self) -> None:
        """Recompute button state based on current CWD and active venv."""
        cwd    = self._cwd_current
        active = self._venv_active

        # Check for a venv in CWD — try all common names
        venv_activate_path = ""
        cwd_venv = ""
        # Git Bash on Windows reports CWD as /c/Users/... (MSYS2 POSIX format);
        # Python's Path on Windows can't resolve that, so convert it first.
        fs_cwd = self._msys_to_win_path(cwd) if platform.system() == "Windows" else cwd
        if cwd:
            try:
                for _name in (".venv", "venv", "env", ".env"):
                    candidate = Path(fs_cwd) / _name
                    if (candidate / "bin" / "activate").exists():
                        venv_activate_path = str(candidate / "bin" / "activate")
                        cwd_venv = str(candidate)
                        break
                    elif (candidate / "Scripts" / "Activate.ps1").exists():
                        venv_activate_path = str(candidate / "Scripts" / "Activate.ps1")
                        cwd_venv = str(candidate)
                        break
            except Exception:
                pass

        def _norm(p: str) -> str:
            """Normalize path for comparison — lowercase on Windows, forward slashes."""
            p = p.replace("\\", "/").rstrip("/")
            # Convert MSYS2/Git Bash POSIX drive paths: /c/Users/... → c:/Users/...
            if len(p) >= 3 and p[0] == "/" and p[1].isalpha() and p[2] == "/":
                p = p[1].lower() + ":/" + p[3:]
            if platform.system() == "Windows":
                p = p.lower()
            return p

        # Child PTY always starts with VIRTUAL_ENV stripped, so any reported venv
        # is explicitly user-activated — no need to filter _idol_venv here.
        if active:
            na = _norm(active)
            nv = _norm(cwd_venv) if cwd_venv else ""
            if nv and (na == nv or na.startswith(nv + "/")):
                self._venv_btn_state = "active_match"
            elif nv:
                self._venv_btn_state = "active_other"
            else:
                self._venv_btn_state = "none"
        elif venv_activate_path:
            self._venv_btn_state = "activate"
        else:
            self._venv_btn_state = "none"

        self._venv_activate_path = venv_activate_path
        self._update_venv_ui()

    def _update_venv_ui(self) -> None:
        state = self._venv_btn_state
        if state == "activate":
            self._venv_btn.config(text="▶ Activate venv", bg="#0e639c",
                                  cursor="hand2", fg="white")
            self._venv_label.pack_forget()
        elif state == "active_match":
            self._venv_btn.config(text="⏹ Deactivate", bg="#1a3a1a",
                                  cursor="hand2", fg="#50fa7b")
            name = Path(self._venv_active).name if self._venv_active else ".venv"
            self._venv_label.config(text=f"({name})", fg="#50fa7b")
            self._venv_label.pack(side="right", padx=(0, 4))
        elif state == "active_other":
            self._venv_btn.config(text="⇄ Switch venv", bg="#3a2a00",
                                  cursor="hand2", fg="#f1fa8c")
            name = Path(self._venv_active).name if self._venv_active else "venv"
            self._venv_label.config(text=f"({name})", fg="#f1fa8c")
            self._venv_label.pack(side="right", padx=(0, 4))
        else:
            self._venv_btn.config(text="▶ Activate venv", bg="#3c3c3c",
                                  cursor="arrow", fg="#858585")
            self._venv_label.pack_forget()

    def _venv_btn_hover(self, entering: bool) -> None:
        if self._venv_btn_state == "none":
            return
        colors = {
            "activate":    ("#1177bb", "#0e639c"),
            "active_match":("#1a4a1a", "#1a3a1a"),
            "active_other":("#4a3a00", "#3a2a00"),
        }
        hover_bg, normal_bg = colors.get(self._venv_btn_state, ("#3c3c3c", "#3c3c3c"))
        self._venv_btn.config(bg=hover_bg if entering else normal_bg)

    def _venv_btn_click(self) -> None:
        state = self._venv_btn_state
        if state == "activate":
            path = getattr(self, "_venv_activate_path", "")
            if path:
                if platform.system() == "Windows":
                    self.send(f'& "{path}"\r')
                else:
                    self.send(f'source "{path}"\r')
                self._fire_venv_activate(path)
        elif state == "active_match":
            self.send("deactivate\r")
            if self.on_venv_deactivate:
                self.on_venv_deactivate()
        elif state == "active_other":
            # Deactivate current, then activate the one in CWD
            path = getattr(self, "_venv_activate_path", "")
            if path:
                if platform.system() == "Windows":
                    self.send(f'deactivate; & "{path}"\r')
                else:
                    self.send(f'deactivate && source "{path}"\r')
                self._fire_venv_activate(path)

    def _fire_venv_activate(self, activate_path: str) -> None:
        """Derive the venv python exe from the activate script path and notify."""
        if not self.on_venv_activate:
            return
        import os, platform as _pl
        base = os.path.dirname(activate_path)  # Scripts/ or bin/
        exe = os.path.join(base, "python.exe" if _pl.system() == "Windows" else "python")
        if os.path.isfile(exe):
            self.on_venv_activate(exe)

    def _on_resize(self, _=None) -> None:
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(50, self._do_resize)

    def _current_prompt_start_y(self) -> int:
        """Walk up from the cursor to find the first row of the current
        prompt's logical line (cursor row + any rows above that wrap-continue
        into it). Rows above this index are 'historical' content safe to
        snapshot into scrollback."""
        y = self._screen.cursor.y
        while y > 0:
            prev = self._screen.buffer.get(y - 1)
            if prev is None:
                break
            raw_wrapped = bool(getattr(prev, "idol_wrapped", False))
            if not self._row_effective_wrap(prev, raw_wrapped):
                break
            y -= 1
        return y

    def _snapshot_visible_to_scrollback(self) -> None:
        """Move rows above the current prompt's first row into our logical
        scrollback. The prompt area (cursor row + any wrap-continuation rows
        above it) stays in pyte's visible buffer so the shell doesn't need
        to redraw a fresh prompt every time the user resizes — the SIGWINCH
        from setwinsize triggers an in-place repaint at the new width.

        After capturing, the surviving rows are shifted up so the prompt
        sits at row 0, eliminating the gap between scrollback and the live
        area."""
        live_start = self._current_prompt_start_y()
        if live_start <= 0:
            return
        # Capture rows 0..live_start-1 into scrollback
        for y in range(live_start):
            line = self._screen.buffer.get(y)
            if line is None:
                continue
            raw_wrapped = bool(getattr(line, "idol_wrapped", False))
            wrapped = self._row_effective_wrap(line, raw_wrapped)
            segs = self._row_segments_for_history(line, wrapped)
            if self._scrollback_open and self._scrollback:
                self._scrollback[-1].extend(segs)
            else:
                self._scrollback.append(segs)
            self._scrollback_open = wrapped
        # Shift prompt area up: row (live_start + k) → row k
        survivors: dict = {}
        for new_y in range(self._screen.lines - live_start):
            src = self._screen.buffer.get(new_y + live_start)
            if src is not None:
                survivors[new_y] = src
        self._screen.buffer.clear()
        for new_y, line in survivors.items():
            self._screen.buffer[new_y] = line
        self._screen.cursor.y = max(0, self._screen.cursor.y - live_start)
        self._screen.dirty.update(range(self._screen.lines))

    def _do_resize(self) -> None:
        self._resize_job = None
        try:
            w = self._canvas.winfo_width()
            h = self._canvas.winfo_height()
            if w > 1 and h > 1 and self._char_w > 0 and self._char_h > 0:
                cols = max(10, w // self._char_w)
                rows = max(5,  h // self._char_h)
                if cols == self._cols and rows == self._rows:
                    return
                # Capture viewport anchor BEFORE mutating state so we can
                # restore the user's scroll position after reflow.
                # Use canvasy(0) (absolute canvas Y at viewport top) rather
                # than yview() fractions: when the canvas just resized the
                # old scrollregion makes fractions unreliable, but the
                # absolute offset stays correct.
                top_canvas_y = self._canvas.canvasy(0)
                live_start_y = self._sb_phys_rows * self._char_h
                at_bottom = top_canvas_y >= live_start_y - self._char_h
                top_anchor: Optional[tuple[int, int]] = None
                if not at_bottom and self._phys_to_log:
                    top_phys = int(self._canvas.canvasy(0) // self._char_h)
                    if 0 <= top_phys < len(self._phys_to_log):
                        log_idx, c_start, _ = self._phys_to_log[top_phys]
                        top_anchor = (log_idx, c_start)
                    else:
                        # Top of viewport is in the live area — treat as bottom.
                        at_bottom = True
                if rows < self._rows:
                    # Row-shrink (with or without a col change): scroll pyte's
                    # buffer to match what the PTY console does — keeps cursor
                    # visible so PSReadLine's absolute coordinates stay in sync.
                    # scroll_amount = rows the console scrolls up to keep
                    # cursor visible = max(0, cursor.y - (new_rows - 1)).
                    scroll_amount = max(0, self._screen.cursor.y - (rows - 1))
                    if scroll_amount > 0:
                        for y in range(scroll_amount):
                            line = self._screen.buffer.get(y)
                            if line is None:
                                continue
                            raw = bool(getattr(line, "idol_wrapped", False))
                            wrapped = self._row_effective_wrap(line, raw)
                            segs = self._row_segments_for_history(line, wrapped)
                            if self._scrollback_open and self._scrollback:
                                self._scrollback[-1].extend(segs)
                            else:
                                self._scrollback.append(segs)
                            self._scrollback_open = wrapped
                        new_buf: dict = {}
                        for new_y in range(rows):
                            src = self._screen.buffer.get(new_y + scroll_amount)
                            if src is not None:
                                new_buf[new_y] = src
                        self._screen.buffer.clear()
                        for ny, line in new_buf.items():
                            self._screen.buffer[ny] = line
                        self._screen.cursor.y = max(0,
                            self._screen.cursor.y - scroll_amount)
                # Do NOT snapshot the live buffer on col changes.  Snapshotting
                # shifts pyte's rows (prompt → row 0) without PSReadLine
                # knowing → garbled prompt with blank lines and partial text.
                # PSReadLine's own SIGWINCH handler reflows the prompt on its own.
                old_cols = self._cols   # captured before resize() mutates self._cols
                self.resize(rows, cols)
                # Immediately reflow the live buffer so the display updates
                # before PSReadLine's SIGWINCH response arrives, matching
                # VS Code terminal behaviour.  Skip for alt-screen apps (vim,
                # htop, etc.) — they handle their own SIGWINCH reflow.
                if cols != old_cols and not self._screen.in_alt_screen:
                    self._reflow_live_buffer(old_cols)
                # Selection coords live in physical canvas rows that change
                # meaning after reflow — clear rather than try to remap.
                self._sel_anchor = None
                self._sel_row_start = None
                self._sel_row_end = None
                # Pass the already-computed canvas height so _update_scrollregion
                # doesn't call winfo_height() again with potentially stale geometry.
                self._redraw_full(canvas_h=h)
                # Restore viewport anchor. _redraw_full already pegged the
                # view to the bottom, which is correct when the user was at
                # the live prompt; otherwise we map the captured logical
                # anchor to its new physical row and scroll there.
                if not at_bottom and top_anchor is not None:
                    total_new = self._sb_phys_rows + self._live_used_rows()
                    if total_new > 0:
                        log_idx, c_start = top_anchor
                        target_phys = self._sb_phys_rows
                        for i, (lidx, cs, _ce) in enumerate(self._phys_to_log):
                            if lidx > log_idx or (lidx == log_idx and cs >= c_start):
                                target_phys = i
                                break
                        self._canvas.yview_moveto(target_phys / total_new)
        except Exception:
            pass

    def _write_error(self, text: str) -> None:
        for line in text.rstrip("\n").split("\n"):
            self._scrollback.append([(line, "#ff5555", _DEFAULT_BG, False)])
        self._redraw_full()
