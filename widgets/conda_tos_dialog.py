"""CondaTosDialog — Accept/Decline dialog for Anaconda channel Terms of Service.

Shown before the first conda operation that downloads packages (wizard env
creation, Package Manager install) when the conda installation hasn't
accepted its channels' ToS yet. Accepting runs `conda tos accept` via
editor/conda_manager.py — the caller owns that; this dialog only collects
the user's decision.
"""
from __future__ import annotations

import tkinter as tk
import webbrowser
from typing import Callable

from utils.ui_font import UI_FONT

_BG      = "#1e1e1e"
_PANEL   = "#252526"
_FG      = "#cccccc"
_DIM     = "#858585"
_LINK    = "#569cd6"
_WARN    = "#e2c08d"
_ACCENT  = "#0e639c"
_ACCENT_H = "#1177bb"
_GREY    = "#3c3c3c"
_GREY_H  = "#4a4a4a"

_TOS_URL = "https://anaconda.com/legal/terms/terms-of-service"


class CondaTosDialog(tk.Toplevel):
    """Modal dark-themed ToS dialog. Calls exactly one of the two callbacks."""

    def __init__(self, parent, pending: dict[str, str],
                 on_accept: Callable[[], None],
                 on_decline: Callable[[], None]) -> None:
        super().__init__(parent)
        self._on_accept = on_accept
        self._on_decline = on_decline
        self._answered = False

        self.title("Conda — Terms of Service")
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())

        body = tk.Frame(self, bg=_BG)
        body.pack(fill="both", expand=True, padx=16, pady=(14, 10))

        tk.Label(body, text="⚠  Anaconda Terms of Service", bg=_BG, fg=_WARN,
                 font=(UI_FONT, 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(
            body,
            text="Conda needs to download packages from Anaconda's channels, "
                 "which require accepting their Terms of Service first. "
                 "This conda installation has not accepted them yet:",
            bg=_BG, fg=_FG, font=(UI_FONT, 9), anchor="w", justify="left",
            wraplength=470,
        ).pack(fill="x", pady=(6, 8))

        channels = tk.Frame(body, bg=_PANEL)
        channels.pack(fill="x", pady=(0, 8))
        for url, text in pending.items():
            tk.Label(channels, text=url, bg=_PANEL, fg=_LINK,
                     font=(UI_FONT, 9, "bold"), anchor="w").pack(
                fill="x", padx=10, pady=(8, 0))
            if text:
                tk.Label(channels, text=text, bg=_PANEL, fg=_DIM,
                         font=(UI_FONT, 8), anchor="w", justify="left",
                         wraplength=440).pack(fill="x", padx=10, pady=(2, 6))

        link = tk.Label(body, text="Read the full Terms of Service ↗",
                        bg=_BG, fg=_LINK, font=(UI_FONT, 8, "underline"),
                        cursor="hand2", anchor="w")
        link.pack(fill="x")
        link.bind("<ButtonRelease-1>", lambda _: webbrowser.open(_TOS_URL))

        tk.Label(
            body,
            text="Accept runs “conda tos accept” for this conda installation — "
                 "the acceptance is remembered by conda itself, so the conda "
                 "command line works too. Decline cancels the operation.",
            bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w", justify="left",
            wraplength=470,
        ).pack(fill="x", pady=(8, 0))

        btns = tk.Frame(self, bg=_BG)
        btns.pack(fill="x", padx=16, pady=(2, 14))
        self._btn(btns, "Accept", _ACCENT, _ACCENT_H, "white",
                  self._accept).pack(side="right")
        self._btn(btns, "Decline", _GREY, _GREY_H, _FG,
                  self._decline).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._decline)
        self.bind("<Escape>", lambda _: self._decline())

        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{px + max((pw - w) // 2, 0)}+{py + max((ph - h) // 3, 0)}")
        self.grab_set()

    def _btn(self, parent, text: str, bg: str, hover_bg: str, fg: str,
             command: Callable[[], None]) -> tk.Label:
        lbl = tk.Label(parent, text=text, bg=bg, fg=fg,
                       font=(UI_FONT, 9), padx=16, pady=5, cursor="hand2")
        lbl.bind("<Enter>", lambda _: lbl.config(bg=hover_bg))
        lbl.bind("<Leave>", lambda _: lbl.config(bg=bg))
        lbl.bind("<ButtonRelease-1>", lambda _: command())
        return lbl

    def _accept(self) -> None:
        if self._answered:
            return
        self._answered = True
        self.destroy()
        self._on_accept()

    def _decline(self) -> None:
        if self._answered:
            return
        self._answered = True
        self.destroy()
        self._on_decline()
