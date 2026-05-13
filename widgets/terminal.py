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
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional
from widgets.scrollbar import VerticalScrollbar

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
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mouse_enabled = False

    def set_mode(self, *args, private=False, **kwargs):
        # Mouse tracking modes: 9=X10, 1000=normal, 1002=button, 1003=any, 1006=SGR
        if private and args and args[0] in (9, 1000, 1002, 1003, 1006):
            self.mouse_enabled = True
        try:
            super().set_mode(*args, private=private, **kwargs)
        except Exception:
            pass

    def reset_mode(self, *args, private=False, **kwargs):
        if private and args and args[0] in (9, 1000, 1002, 1003, 1006):
            self.mouse_enabled = False
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
            _add("Git Bash", [git_bash], "#4ec9b0")
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
        tags_hit: set[str] = set()
        for item in self.find_overlapping(event.x, event.y, event.x, event.y):
            tags_hit.update(self.gettags(item))

        for tag in tags_hit:
            if tag.startswith("close_"):
                self.on_close(tag[len("close_"):])
                return

        if "btn_new" in tags_hit:
            self.on_new()
            return
        if "btn_dd" in tags_hit:
            self.on_dropdown(event)
            return

        for tag in tags_hit:
            if tag.startswith("row_"):
                key = tag[len("row_"):]
                if key in self._sessions:
                    self.on_select(key)
                return

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

        # Scrollback: list of rendered line strings + their tag maps
        # Each entry: list of (text, fg, bg, bold) segments for one row
        self._scrollback: list[list] = []
        self._scrollback_in_widget: int = 0   # lines already appended to text widget

        # Tag cache: (fg, bg, bold) → tag name
        self._tag_cache: dict[tuple, str] = {}
        self._tag_count = 0

        self._resize_job = None
        self._sel_start: str | None = None
        self._sel_end:   str | None = None
        self._session_id = 0   # incremented on each start(); guards stale sentinels
        self._render_suppressed = False   # True during startup; suppresses _redraw_full until clear fires
        self._clear_timer: str | None = None  # after() handle for the fallback clear

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
            self._scrollback.clear()
            self._screen = _RobustScreen(self._cols, self._rows, history=self._SCROLLBACK)
            self._stream = pyte.ByteStream(self._screen)
            self._session_id += 1
            sid = self._session_id
            self._pty = _pty_spawn(cmd, dimensions=(self._rows, self._cols), env=env)
            self._running = True
            self._raw_buf  = ""
            self._cwd_current = ""
            self._venv_active  = ""
            self._state_file_mtime = 0.0
            self._sid_to_key[sid] = self._active_shell_key
            threading.Thread(target=self._read_loop, args=(sid, self._pty), daemon=True).start()
            self._text.focus_set()
            # Inject OSC 7 CWD + VENV reporting hook after shell is ready.
            # Both the cd and hook injection use _send_silently so the TTY
            # driver never echoes the commands — nothing to clear afterward.
            self.after(400, self._inject_shell_hooks)
            if platform.system() != "Windows":
                self._render_suppressed = True
                self._clear_timer = self.after(700, self._clear_screen_direct)
                self.after(1500, self._ensure_render_active)
            _cmd_name = os.path.basename(cmd[0]).lower()
            _is_shell = any(s in _cmd_name for s in ("powershell", "pwsh", "cmd", "bash", "zsh", "sh"))
            _cwd = self._cwd
            if _cwd and os.path.isdir(_cwd) and _is_shell:
                self.after(300, lambda c=_cwd: self._send_silently(f'cd "{c}"\r'))
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
        for sess in self._sessions.values():
            try:
                sess["screen"].resize(rows, cols)
                if sess["running"] and sess.get("pty"):
                    sess["pty"].setwinsize(rows, cols)
            except Exception:
                pass

    def _clear_screen_direct(self) -> None:
        """Reset pyte completely to discard startup noise, lift render suppression,
        then nudge the shell for a fresh prompt. One clean render, no flash."""
        if self._clear_timer:
            self.after_cancel(self._clear_timer)
            self._clear_timer = None
        self._scrollback.clear()
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
        text_frame.pack(side="left", fill="both", expand=True)
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
            pady=4,
        )
        vs = VerticalScrollbar(text_frame, command=self._on_scroll)
        self._scrollbar = vs
        self._text.configure(yscrollcommand=self._on_yscroll_update)
        self._text.grid(row=0, column=0, sticky="nswe")
        vs.grid(row=0, column=1, sticky="ns")

        # Preconfigure base tags
        self._text.tag_configure("plain", foreground=_DEFAULT_FG, background=_DEFAULT_BG)
        self._text.tag_configure("error", foreground="#ff5555")
        self._text.tag_configure("cursor_block",
                                 background=_DEFAULT_FG, foreground=_DEFAULT_BG)
        # sel tag needs explicit colours — disabled widget won't show default highlight
        self._text.tag_configure("sel", background="#264f78", foreground=_DEFAULT_FG)
        self._text.tag_raise("sel")

        # Remove default Text bindings — we handle everything ourselves
        self._text.bindtags((str(self._text), '.', 'all'))

        self._text.bind("<ButtonPress-1>",   self._on_click)
        self._text.bind("<B1-Motion>",      self._on_drag)
        self._text.bind("<MouseWheel>",     self._on_mousewheel)   # Windows
        self._text.bind("<Button-4>",       self._on_mousewheel)   # Linux scroll up
        self._text.bind("<Button-5>",       self._on_mousewheel)   # Linux scroll down
        self._text.bind("<Button-3>",       self._show_context_menu)
        self._text.bind("<Control-Shift-C>",lambda _: (self._copy_selection(), "break")[1])
        self._text.bind("<Control-Shift-V>",lambda _: (self._on_paste(),       "break")[1])
        self._text.bind("<Key>",            self._on_key)
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
        """Full redraw from scratch (restart / clear). Resets incremental counter."""
        if self._render_suppressed:
            return
        self._scrollback_in_widget = 0
        self._text.config(state="normal")
        self._text.delete("1.0", "end")

        # Scrollback lines
        for seg_list in self._scrollback:
            for text, fg, bg, bold in seg_list:
                tag = self._get_tag(fg, bg, bold)
                self._text.insert("end", text, tag)
            self._text.insert("end", "\n", "plain")
        self._scrollback_in_widget = len(self._scrollback)

        self._insert_screen_rows()

        self._text.config(state="disabled")
        if self._sel_start and self._sel_end:
            try:
                self._text.tag_add("sel", self._sel_start, self._sel_end)
                self._text.tag_raise("sel")
            except Exception:
                pass
        cursor_line = len(self._scrollback) + self._screen.cursor.y + 1
        self._text.see(f"{cursor_line}.0")
        self._text.xview_moveto(0)

    def _redraw_screen(self) -> None:
        """Rewrite only the live screen rows (scrollback already appended)."""
        if self._render_suppressed:
            return
        screen_start = self._scrollback_in_widget + 1
        self._text.config(state="normal")
        self._text.delete(f"{screen_start}.0", "end")
        self._insert_screen_rows()
        self._text.config(state="disabled")
        if self._sel_start and self._sel_end:
            try:
                self._text.tag_add("sel", self._sel_start, self._sel_end)
                self._text.tag_raise("sel")
            except Exception:
                pass
        cursor_line = self._scrollback_in_widget + self._screen.cursor.y + 1
        self._text.see(f"{cursor_line}.0")
        self._text.xview_moveto(0)

    def _insert_screen_rows(self) -> None:
        """Insert the current pyte screen rows into the text widget (state=normal assumed)."""
        screen_lines = self._screen_to_lines()
        cursor_row = self._screen.cursor.y
        cursor_col = self._screen.cursor.x
        for row_idx, seg_list in enumerate(screen_lines):
            col = 0
            for text, fg, bg, bold in seg_list:
                if row_idx == cursor_row:
                    for ci, ch in enumerate(text):
                        if col + ci == cursor_col:
                            self._text.insert("end", ch, "cursor_block")
                        else:
                            self._text.insert("end", ch, self._get_tag(fg, bg, bold))
                    col += len(text)
                else:
                    self._text.insert("end", text, self._get_tag(fg, bg, bold))
            if row_idx < len(screen_lines) - 1:
                self._text.insert("end", "\n", "plain")

    def _flush_scrollback(self) -> None:
        """Move lines scrolled off the pyte screen into our list, then append new ones to widget."""
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
            trim = len(self._scrollback) - self._SCROLLBACK
            self._scrollback = self._scrollback[trim:]
            self._scrollback_in_widget = max(0, self._scrollback_in_widget - trim)

        # Append any new scrollback lines to the text widget
        if self._scrollback_in_widget < len(self._scrollback) and not self._render_suppressed:
            self._text.config(state="normal")
            for seg_list in self._scrollback[self._scrollback_in_widget:]:
                for text, fg, bg, bold in seg_list:
                    self._text.insert("end", text, self._get_tag(fg, bg, bold))
                self._text.insert("end", "\n", "plain")
            self._scrollback_in_widget = len(self._scrollback)
            self._text.config(state="disabled")

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
                self._flush_scrollback()   # appends new scrollback lines to widget
                self._redraw_screen()      # rewrites only live screen rows

        if active_sentinel:
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
            self._sel_start = None
            self._sel_end   = None
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
            self._text.yview_scroll(-3 if up else 3, "units")

        return "break"

    def _on_paste(self, _=None) -> str:
        try:
            text = self._text.clipboard_get()
            if text:
                self.send(text)
        except Exception:
            pass
        return "break"

    def _on_click(self, event) -> str:
        dismiss = getattr(self, "_ctx_overlay_dismiss", None)
        if dismiss:
            dismiss()
        self._text.focus_set()
        # Clear existing selection and set the drag anchor
        self._sel_start = None
        self._sel_end   = None
        self._sel_anchor = self._text.index(f"@{event.x},{event.y}")
        self._text.tag_remove("sel", "1.0", "end")
        return "break"

    def _on_drag(self, event) -> str:
        if not self._sel_anchor:
            return "break"
        cur = self._text.index(f"@{event.x},{event.y}")
        anchor = self._sel_anchor
        if self._text.compare(anchor, "<=", cur):
            start, end = anchor, cur
        else:
            start, end = cur, anchor
        self._sel_start = start
        self._sel_end   = end
        self._text.tag_remove("sel", "1.0", "end")
        self._text.tag_add("sel", start, end)
        self._text.tag_raise("sel")
        return "break"

    def _copy_selection(self) -> None:
        try:
            text = self._text.get("sel.first", "sel.last")
            if text:
                self._text.clipboard_clear()
                self._text.clipboard_append(text)
        except Exception:
            pass

    def _show_context_menu(self, event) -> str:
        has_sel = False
        try:
            self._text.index("sel.first")
            has_sel = True
        except Exception:
            pass

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

        top = self._text.winfo_toplevel()
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
                    top.unbind("<Button-1>", top_bid[0])
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
                lbl.bind("<Enter>",    _enter)
                lbl.bind("<Leave>",    _leave)
                lbl.bind("<Button-1>", _click)

        overlay.place(x=rel_x, y=rel_y)
        overlay.lift()
        top_bid.append(top.bind("<Button-1>", _global_click, add=True))

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
                "scrollback_in_widget": self._scrollback_in_widget,
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
            self._scrollback_in_widget  = sess.get("scrollback_in_widget", 0)
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
            _KNOWN = ("powershell", "pwsh", "cmd", "bash", "zsh", "sh")
            if platform.system() == "Windows" and any(s in _name for s in _KNOWN):
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
        """Cancel any pending debounce and resize on the next event loop tick.
        Used after layout changes where we know the final size (animation end, sash
        release) — avoids the 50ms debounce delay that would otherwise leave the PTY
        with wrong dimensions."""
        if self._resize_job:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        self.after(0, self._do_resize)

    def _animate_panel(self, target_w: int, cur_w: int, gen: int) -> None:
        if gen != self._anim_gen:
            return   # stale callback — a newer animation superseded this one
        if cur_w == target_w:
            if target_w == 0:
                self._sash.pack_forget()
                self._session_panel.pack_forget()
            # Resize immediately — don't wait for the 50ms <Configure> debounce
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

    def _inject_shell_hooks(self) -> None:
        """Inject CWD + VENV reporting into the running shell."""
        if not self._running:
            return
        sys = platform.system()
        shell_cmd = (self._session_meta.get(self._active_shell_key) or {}).get("cmd") or _default_shell()
        shell_name = os.path.basename(shell_cmd[0]).lower() if shell_cmd else ""
        _KNOWN_SHELLS = ("powershell", "pwsh", "cmd", "bash", "zsh", "sh")
        if not any(s in shell_name for s in _KNOWN_SHELLS):
            return   # REPL or unknown program — skip hook injection

        if sys == "Windows":
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
            # bash / sh
            hook = (
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
        if cwd:
            try:
                for _name in (".venv", "venv", "env", ".env"):
                    candidate = Path(cwd) / _name
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
            else:
                self._venv_btn_state = "active_other"
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
                rows = max(5,  (h - 8) // font_h)  # -8 accounts for pady=4 top+bottom
                self.resize(rows, cols)
        except Exception:
            pass

    def _write_error(self, text: str) -> None:
        self._text.config(state="normal")
        self._text.insert("end", text, "error")
        self._text.config(state="disabled")
        self._text.see("end")
