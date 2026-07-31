"""Package Manager panel — browse installed packages, search PyPI, install/uninstall."""
from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable
from widgets.scrollbar import VerticalScrollbar

from editor import conda_manager as conda_backend
from editor.conda_manager import CondaManager, CondaSearchIndex
from editor.pip_manager import PipManager
from widgets.conda_channels_editor import CondaChannelsEditor
from widgets.conda_tos_dialog import CondaTosDialog
from widgets.learning_manager import LearningManager
from utils import settings as _settings
from utils.conda_channels import preview_note_channels, validate
from utils.conda_env import (channel_edit_action, create_project_environment_yml,
                             is_conda_env, mask_channel, resolve_channels,
                             write_project_channels)
from utils.thread_safe_after import make_thread_safe_after, rearm_after
from widgets.guide_window import GuideWindow, GuidePage
from utils.ui_font import UI_FONT

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

_BG       = "#1e1e1e"
_PANEL_BG = "#252526"
_INPUT_BG = "#2d2d30"
_BORDER   = "#3c3c3c"
_FG       = "#cccccc"
_DIM      = "#858585"
_ACCENT   = "#0e639c"
_GREEN    = "#4ec9b0"
_SEL_BG   = "#094771"
_WARN     = "#ce9178"
_GREY_BTN = "#3c3c3c"

# Search-scope selector: no channel chosen means "however conda would resolve
# it", which is not the same as any single channel and so needs its own label.
_SCOPE_ALL = "▾ All channels"

# Channel-bar edit label per conda_env.channel_edit_action verdict. Creating
# environment.yml is named explicitly because it is a different action from
# editing one — it drops a git-tracked file into the project.
_EDIT_LABELS = {"": "", "edit": "✎ Edit", "create": "✎ Create environment.yml"}

_CACHE_FILE   = Path.home() / ".idol" / "pkg_cache.json"
_LOOKUP_FILE  = Path(__file__).parent.parent / "data" / "idol_package_categories.json"

# Load precomputed lookup at import time — zero network cost
def _load_builtin_lookup() -> dict[str, str]:
    try:
        data = json.loads(_LOOKUP_FILE.read_text(encoding="utf-8"))
        return data.get("lookup", {})
    except Exception:
        return {}

_BUILTIN_LOOKUP: dict[str, str] = _load_builtin_lookup()


_HINTS = [
    "Search PyPI…",
    "e.g. web scraping",
    "e.g. requests",
    "e.g. image processing",
    "e.g. data analysis",
    "e.g. http client",
    "e.g. testing",
    "e.g. pandas",
    "e.g. automation",
    "e.g. pdf parser",
]

# Hints shown while the search source is conda — names that exist on conda
# channels (some under different names than PyPI, e.g. python-graphviz).
_CONDA_HINTS = [
    "Search conda…",
    "e.g. pytorch",
    "e.g. numpy",
    "e.g. python-graphviz",
    "e.g. ffmpeg",
    "e.g. image processing",
    "e.g. cudatoolkit",
    "e.g. pandas",
    "e.g. machine learning",
    "e.g. mkl",
]

# Placeholder detection must match either set — the entry can still hold the
# other source's hint right after a toggle.
_ALL_HINTS = set(_HINTS) | set(_CONDA_HINTS)

# Curated well-known packages per category — promoted in PyPI search results
_FEATURED: dict[str, list[str]] = {
    "Networking & Web":       ["requests", "httpx", "aiohttp", "urllib3", "scrapy",
                                "beautifulsoup4", "selenium", "playwright", "lxml", "mechanize",
                                "websockets", "httpcore"],
    "Web Frameworks":         ["flask", "django", "fastapi", "starlette", "tornado",
                                "bottle", "cherrypy", "sanic", "falcon", "quart"],
    "Data Science":           ["numpy", "pandas", "scipy", "matplotlib", "seaborn",
                                "polars", "pyarrow", "statsmodels", "plotly", "bokeh"],
    "Machine Learning & AI":  ["scikit-learn", "torch", "tensorflow", "keras",
                                "transformers", "xgboost", "lightgbm", "catboost",
                                "optuna", "mlflow"],
    "Computer Vision":        ["opencv-python", "pillow", "imageio", "scikit-image",
                                "torchvision", "albumentations"],
    "Desktop Automation":     ["pyautogui", "pyperclip", "pynput", "keyboard", "mouse",
                                "pywinauto", "pytweening", "pygetwindow"],
    "Testing":                ["pytest", "hypothesis", "factory-boy", "faker",
                                "coverage", "tox", "nox", "behave", "responses"],
    "CLI Tools":              ["click", "typer", "rich", "colorama", "prompt-toolkit",
                                "tqdm", "fire", "docopt", "blessed"],
    "Database":               ["sqlalchemy", "psycopg2", "pymysql", "redis", "pymongo",
                                "motor", "aiomysql", "alembic", "peewee"],
    "Security & Cryptography":["cryptography", "pycryptodome", "paramiko", "passlib",
                                "bcrypt", "pyotp", "certifi"],
    "File Formats & Parsing": ["pyyaml", "toml", "python-docx", "openpyxl", "pypdf",
                                "pillow", "markdown", "xmltodict", "chardet"],
    "System & OS":            ["psutil", "watchdog", "schedule", "apscheduler",
                                "plumbum", "invoke", "sh"],
    "Multimedia":             ["pillow", "opencv-python", "moviepy", "pygame",
                                "pydub", "librosa", "mutagen", "soundfile"],
    "GUI & UI":               ["pyqt5", "pyside6", "wxpython", "kivy",
                                "dearpygui", "customtkinter", "ttkbootstrap"],
    "Async & Concurrency":    ["asyncio", "trio", "anyio", "uvloop", "aiofiles",
                                "aiocache", "asyncpg"],
    "Cloud & DevOps":         ["boto3", "google-cloud-storage", "azure-storage-blob",
                                "docker", "kubernetes", "ansible"],
    "Packaging & Build":      ["setuptools", "wheel", "flit", "poetry", "hatch",
                                "twine", "build", "pip-tools"],
    "Code Quality & Linting": ["pylint", "flake8", "black", "isort", "mypy",
                                "bandit", "pyflakes", "autopep8"],
    "Documentation":          ["sphinx", "mkdocs", "pdoc", "pydoc-markdown"],
    "Data Visualization":     ["matplotlib", "seaborn", "plotly", "bokeh",
                                "altair", "dash", "streamlit"],
}

# Keyword → topic for summary-based fallback classification
_SUMMARY_KEYWORDS: list[tuple[list[str], str]] = [
    (["http", "request", "web", "url", "rest", "api", "scrape", "crawl", "browser", "html", "css", "wget"],
     "Networking & Web"),
    (["test", "pytest", "unittest", "mock", "assert", "fixture", "coverage"],
     "Development Tools"),
    (["data", "dataframe", "csv", "excel", "spreadsheet", "table", "sql", "database", "orm", "query"],
     "Science & Data"),
    (["image", "photo", "png", "jpg", "gif", "svg", "pixel", "render", "draw", "color", "colour"],
     "Multimedia"),
    (["audio", "sound", "music", "wav", "mp3", "video", "stream", "codec"],
     "Multimedia"),
    (["cli", "command", "terminal", "shell", "console", "argument", "argparse", "click", "subprocess"],
     "System & OS"),
    (["file", "path", "directory", "filesystem", "zip", "archive", "compress"],
     "System & OS"),
    (["encrypt", "decrypt", "hash", "ssl", "tls", "certificate", "crypto", "password", "secret", "auth"],
     "Security"),
    (["parse", "xml", "json", "yaml", "toml", "config", "serializ", "deserializ", "format"],
     "Text Processing"),
    (["text", "string", "regex", "nlp", "language", "unicode", "encode", "decode"],
     "Text Processing"),
    (["machine learning", "neural", "deep learning", "model", "train", "predict", "numpy", "scipy",
      "statistics", "math", "matrix", "tensor", "pytorch", "tensorflow"],
     "Science & Data"),
    (["gui", "widget", "window", "tkinter", "qt", "wx", "ui", "interface", "dialog"],
     "Development Tools"),
    (["log", "logging", "debug", "trace", "monitor", "metric", "profil"],
     "Development Tools"),
    (["async", "asyncio", "concurrent", "thread", "multiprocess", "parallel", "queue", "event"],
     "Development Tools"),
    (["email", "smtp", "imap", "message", "notification", "slack", "discord", "chat", "websocket"],
     "Communications"),
    (["pdf", "docx", "word", "excel", "spreadsheet", "office", "report", "document"],
     "Office & Business"),
    (["game", "pygame", "sprite", "collision", "2d", "3d", "opengl", "graphic"],
     "Games"),
    (["teach", "learn", "education", "tutorial", "course", "student", "exercise"],
     "Education"),
]


def _topic_from_summary(summary: str) -> str:
    """Keyword-scan a package summary to guess a topic bucket."""
    if not summary:
        return "Other"
    lower = summary.lower()
    for keywords, topic in _SUMMARY_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return topic
    return "Other"


def _topic_from_classifiers(classifiers: list[str]) -> str:
    """Extract a short human-readable topic from PyPI classifiers."""
    # Walk the Topic :: hierarchy and return the top-level bucket
    mapping = {
        "Software Development": "Development Tools",
        "Scientific/Engineering": "Science & Data",
        "Internet": "Networking & Web",
        "Text Processing": "Text Processing",
        "System": "System & OS",
        "Database": "Database",
        "Security": "Security",
        "Multimedia": "Multimedia",
        "Education": "Education",
        "Games/Entertainment": "Games",
        "Office/Business": "Office & Business",
        "Communications": "Communications",
        "Utilities": "Utilities",
    }
    for c in classifiers:
        if c.startswith("Topic :: "):
            parts = c.split(" :: ")
            if len(parts) >= 2:
                top = parts[1]
                for key, label in mapping.items():
                    if key.lower() in top.lower():
                        return label
                return top   # use raw top-level if no mapping hit
    return "Other"


class PackageManagerPanel(tk.Frame):
    """Left/right split: treeview of packages on the left, detail panel on the right."""

    def __init__(self, parent,
                 get_output_panel: Callable | None = None,
                 get_ai_panel: Callable | None = None,
                 open_ai_panel: Callable | None = None,
                 on_packages_changed: Callable | None = None,
                 **kwargs) -> None:
        super().__init__(parent, bg=_BG, **kwargs)
        self._get_output_panel = get_output_panel
        self._get_ai_panel     = get_ai_panel
        self._open_ai_panel    = open_ai_panel
        #: Fired after an install or uninstall finishes. This panel is the only
        #: place that changes what is installed, and until this existed it told
        #: nobody — it refreshed its own tree and left every other cache of
        #: "is package X present" stale. See app._on_packages_changed.
        self._on_packages_changed = on_packages_changed
        self._installed: dict[str, str] = {}   # name → version
        self._origins: dict[str, str] = {}     # name → "conda" | "pypi" (conda backend only)
        self._selected_pkg: str = ""
        self._pypi_cache: dict[str, dict] = {}   # per-session detail cache
        self._topic_cache: dict[str, str] = {}   # name → topic (persisted)
        self._load_topic_cache()
        _after = make_thread_safe_after(self)
        self._after_fn = _after
        self._pip = PipManager(after_fn=_after)
        self._conda = CondaManager(after_fn=_after)
        self._backend = self._pip
        self._tos_ok_exe: str | None = None   # conda exe whose ToS check passed
        self._conda_index = CondaSearchIndex(after_fn=_after)
        self._search_source = "pypi"          # "pypi" | "conda" — where search looks
        #: What the tree is currently showing: "installed" | "pypi" | "conda".
        #: Set by the three population methods, read by _on_select — a
        #: selection only expresses a source preference when it came from a
        #: search, and the installed list is not one.
        self._listing = "installed"
        #: Which source the user *chose* for the selected package: "pypi",
        #: "conda", or "" for no choice at all (selected from the installed
        #: list). The empty state is load-bearing — see _wants_pip.
        self._selected_src = ""
        self._conda_results: dict[str, dict] = {}   # last conda search results by name
        self._project_dir: str = ""            # folder whose environment.yml we read
        self._chan_cfg: conda_backend.ChannelConfig | None = None
        #: One channel to scope search and install to, or "" for all of them.
        #: Transient by design — a view of the project's channels, never a
        #: change to them, so it is not persisted and resets with the env.
        self._scope_channel: str = ""
        self._group_view = bool(_settings.get("pkg_group_view", True))
        self._build()
        self.after(100, self._load_installed)

    def set_python(self, exe: str) -> None:
        """Switch the active interpreter and refresh the installed package list.

        Conda interpreters route package operations through CondaManager
        (conda-first install with pip fallback); if the env's conda
        executable can't be located, pip inside the env is used instead.
        """
        self._pip.set_python(exe)
        self._conda.set_python(exe)
        if is_conda_env(exe) and self._conda.available:
            self._backend = self._conda
        else:
            if is_conda_env(exe):
                self._notify("conda executable not found — using pip inside the env\n")
            self._backend = self._pip
        # Search source follows the interpreter: conda envs search conda's
        # channels (what conda install can reach), everything else PyPI.
        self._set_search_source(
            "conda" if self._backend is self._conda else "pypi")
        # A config read from the previous env must not outlive it, and a scope
        # naming one of the old env's channels is meaningless in the new one.
        self._chan_cfg = None
        self._scope_channel = ""
        self._detail.set_preview_visible(self._backend is self._conda)
        self._sync_channel_bar()
        if self._backend is self._conda:
            # Pre-warm in the background, for the channels this project uses.
            self._conda_index.ensure_loaded(self._effective_channels())
        self._load_installed()

    def set_project_dir(self, path: str) -> None:
        """Point the channel bar at *path*'s environment.yml.

        Follows the explorer root, which is the same folder
        `app._add_to_environment_yml` appends dependencies to — the bar and the
        writer have to agree about which environment.yml they mean.
        """
        if self._project_dir == str(path or ""):
            return
        self._project_dir = str(path or "")
        if self._backend is self._conda:
            self._render_channel_bar()
            self._apply_channels()

    # ── Channel bar ───────────────────────────────────────────────────────────

    def _resolve_channels(self) -> tuple[list[str], bool]:
        """`(channels, stated)` for this project — see `conda_env.resolve_channels`."""
        cfg = self._chan_cfg
        reported = list(cfg.channels) if cfg and cfg.ok else []
        return resolve_channels(self._project_dir, reported)

    def _effective_channels(self) -> list[str]:
        """The channels this project actually searches and installs from."""
        return self._resolve_channels()[0]

    def _apply_channels(self) -> None:
        """Push the effective list to the install backend and the search index.

        Installs are pinned only for a project that states its channels (see
        `resolve_channels` for why). Search takes the effective list either
        way — it is a read, and it should show what conda will actually reach.
        """
        channels, stated = self._resolve_channels()
        self._conda.set_channels(channels if stated else [], override=stated)
        if channels and not self._conda_index.is_loaded_for(channels):
            self._conda_index.ensure_loaded(channels)

    def _sync_channel_bar(self) -> None:
        """Show and refresh the bar for conda interpreters; hide it otherwise."""
        if self._backend is not self._conda:
            self._chan_frame.pack_forget()
            return
        self._chan_frame.pack(fill="x", pady=(2, 4), before=self._pane)
        self._render_channel_bar()
        # Asked even when the project states its own channels: channel_priority
        # is never in environment.yml, so conda is the only source for it.
        conda_backend.fetch_channel_config(
            self._conda.conda_exe, self._conda.prefix,
            self._after_fn, self._on_channel_config)

    def _on_channel_config(self, cfg: conda_backend.ChannelConfig) -> None:
        self._chan_cfg = cfg
        self._render_channel_bar()
        self._apply_channels()

    def _render_channel_bar(self) -> None:
        """Paint the bar from the project file first, conda's own config second."""
        cfg = self._chan_cfg
        channels, stated = self._resolve_channels()
        if stated:
            source = "from environment.yml"
        elif cfg is None:
            channels, source = [], "reading conda configuration…"
        elif not cfg.ok:
            channels = []
            source = "conda could not report its channel configuration"
        else:
            channels = list(cfg.channels)
            source = f"from {cfg.source}" if cfg.source else "conda's built-in default"
            if self._project_dir:
                source += "  ·  this project has no environment.yml"
        # Numbered, never spatial: "top" and "bottom" mean opposite things
        # across conda's own CLI flags, and users read position wrong every
        # time it is phrased that way.
        self._chan_lbl.config(
            text="   ·   ".join(f"{i} {mask_channel(c)}"
                                for i, c in enumerate(channels, 1)) or "—",
            fg=_FG if channels else _DIM)
        # Guardrails: worst issue only, on the source line. The full list lives
        # in the editor, where it can be acted on — a bar that grows a paragraph
        # every time a channel is added would just be noise.
        issues = validate(channels, cfg.priority if cfg and cfg.ok else "",
                          self._conda_index.missing_channels) if channels else []
        if issues:
            worst = issues[0]
            glyph = "✕" if worst.severity == "error" else (
                "⚠" if worst.severity == "warning" else "ⓘ")
            extra = f"  ·  +{len(issues) - 1} more" if len(issues) > 1 else ""
            source = f"{source}     {glyph} {worst.short}{extra}"
        self._chan_src.config(
            text=source,
            fg=_WARN if issues and issues[0].severity != "info" else _DIM)
        self._chan_prio.config(
            text=f"{cfg.priority} priority" if cfg and cfg.ok and cfg.priority else "")
        self._chan_edit.config(text=_EDIT_LABELS[
            channel_edit_action(self._project_dir, stated)])

    def _open_channel_guide(self) -> None:
        from utils.conda_channels_guide import get_pages
        GuideWindow(self, "Conda Channels", get_pages())

    def _edit_channels(self) -> None:
        """Open the channel editor, adopting the folder as a conda project first.

        Creating environment.yml declares the folder a conda project and drops a
        git-tracked file into it, so it is asked rather than done as a side
        effect of clicking Edit.
        """
        from tkinter import messagebox

        seed, stated = self._resolve_channels()
        action = channel_edit_action(self._project_dir, stated)
        if not action:
            return
        if action == "create":
            if not seed:
                self._notify("Still reading conda's channel configuration — "
                             "try again in a moment\n")
                return
            if not messagebox.askyesno(
                "Create environment.yml",
                f"This project has no environment.yml.\n\n"
                f"Create one in {self._project_dir} so the channel list travels "
                f"with your code?\n\n"
                f"It will start with the channels conda is using now: "
                f"{', '.join(mask_channel(c) for c in seed)}",
                parent=self,
            ):
                return
            name = os.path.basename(os.path.abspath(self._project_dir))
            if not create_project_environment_yml(self._project_dir, name, seed):
                self._notify("Could not create environment.yml — check folder "
                             "permissions\n")
                return
            self._render_channel_bar()

        cfg = self._chan_cfg
        CondaChannelsEditor(
            self, self._effective_channels(),
            os.path.join(os.path.basename(os.path.abspath(self._project_dir)),
                         "environment.yml"),
            on_save=self._on_channels_saved,
            # channel_priority decides whether a mixed-stack pair is a real
            # risk; the index knows which channels have nothing to search.
            priority=cfg.priority if cfg and cfg.ok else "",
            missing=self._conda_index.missing_channels,
        )

    def _on_channels_saved(self, channels: list[str]) -> None:
        """Persist the edited list, then re-point search and installs at it."""
        if not write_project_channels(self._project_dir, channels):
            self._notify("Could not write environment.yml — the channel list "
                         "was not saved\n")
            return
        self._render_channel_bar()
        self._apply_channels()
        # The index is keyed by channel set, so this refetches only the delta.
        self._conda_index.ensure_loaded(
            channels, on_done=lambda n: self._notify(
                f"Channel index rebuilt — {n} packages searchable\n"))

    def _set_search_source(self, source: str) -> None:
        """Switch the search namespace and sync the toggle/button UI."""
        self._search_source = source
        if self._backend is self._conda:
            self._src_frame.pack(side="right", padx=(4, 0), pady=2)
        else:
            self._src_frame.pack_forget()
        for src, lbl in self._src_lbls.items():
            active = src == source
            lbl.config(fg="white" if active else _DIM,
                       bg=_ACCENT if active else _INPUT_BG)
        self._search_btn.config(
            text="conda ↗" if source == "conda" else "PyPI ↗")
        # A channel scope means nothing to a PyPI search — drop it rather than
        # leave a chip that silently stops applying.
        if source != "conda":
            self._scope_channel = ""
        self._sync_scope_label()
        # Placeholder follows the source: swap the displayed hint (and restart
        # the cycle) unless the user is typing a real query.
        if (not self._hint_focused
                and self._search_entry.get() in _ALL_HINTS):
            self._hint_idx = 0
            self._search_entry.delete(0, "end")
            self._search_entry.insert(0, self._active_hints()[0])
            self._search_entry.config(fg=_DIM)

    # ── Search scope ([All] or one channel) ───────────────────────────────────

    def _sync_scope_label(self) -> None:
        """Show the scope chip only where it means something, and say which."""
        if self._backend is not self._conda or self._search_source != "conda":
            self._scope_lbl.pack_forget()
            return
        self._scope_lbl.pack(side="right", padx=(4, 0), pady=2)
        scoped = bool(self._scope_channel)
        self._scope_lbl.config(
            text=f"▾ {mask_channel(self._scope_channel)}" if scoped else _SCOPE_ALL,
            fg="white" if scoped else _DIM,
            bg=_ACCENT if scoped else _INPUT_BG)

    def _open_scope_menu(self, event) -> None:
        channels = self._effective_channels()
        menu = tk.Menu(self, tearoff=0, bg=_PANEL_BG, fg=_FG,
                       activebackground=_ACCENT, activeforeground="white",
                       bd=0, font=(UI_FONT, 9))
        menu.add_command(label="All channels",
                         command=lambda: self._set_scope(""))
        if channels:
            menu.add_separator()
        for i, channel in enumerate(channels, 1):
            menu.add_command(label=f"{i}   {mask_channel(channel)}",
                             command=lambda c=channel: self._set_scope(c))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _set_scope(self, channel: str) -> None:
        """Narrow search and install to one channel, or back to all of them."""
        if channel == self._scope_channel:
            return
        self._scope_channel = channel
        self._sync_scope_label()
        # Re-run whatever is on screen so the list matches the new scope
        # instead of sitting there looking authoritative and being stale.
        query = self._search_var.get().strip()
        if query and query not in _ALL_HINTS and self._search_source == "conda":
            self._do_conda_search(query)

    def _active_hints(self) -> list[str]:
        """The rotating hint set for the current search source."""
        return _CONDA_HINTS if self._search_source == "conda" else _HINTS

    def _notify(self, msg: str) -> None:
        """One-line notice in the Output panel, if available."""
        output = self._get_output_panel() if self._get_output_panel else None
        if output:
            output.write(msg, tag="err")

    # ── Disk cache ────────────────────────────────────────────────────────────

    def _load_topic_cache(self) -> None:
        try:
            if _CACHE_FILE.exists():
                self._topic_cache = json.loads(
                    _CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._topic_cache = {}

    def _save_topic_cache(self) -> None:
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(
                json.dumps(self._topic_cache, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Top toolbar ───────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg=_PANEL_BG)
        toolbar.pack(fill="x")

        tk.Label(toolbar, text="📦 Package Manager", bg=_PANEL_BG, fg=_FG,
                 font=(UI_FONT, 10, "bold")).pack(side="left", padx=10, pady=6)

        self._refresh_btn = self._make_btn(toolbar, "↻ Refresh", self._load_installed)
        self._refresh_btn.pack(side="right", padx=(0, 8), pady=4)

        self._guide_lbl = tk.Label(
            toolbar, text="? Learn about Package Manager",
            bg=_PANEL_BG, fg="#569cd6", font=(UI_FONT, 8), cursor="hand2",
        )
        self._guide_lbl.bind("<Button-1>", lambda _: self._open_guide())
        self._guide_lbl.pack(side="right", padx=(0, 8), pady=4)

        tk.Frame(self, bg=_BORDER, height=1).pack(fill="x")

        # ── Search bar ────────────────────────────────────────────────────────
        search_frame = tk.Frame(self, bg=_INPUT_BG)
        search_frame.pack(fill="x", padx=8, pady=6)

        self._search_var = tk.StringVar()
        self._search_entry = tk.Entry(search_frame, textvariable=self._search_var,
                                      bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                                      font=(UI_FONT, 10), relief="flat", bd=0,
                                      highlightthickness=1, highlightbackground=_BORDER,
                                      highlightcolor=_ACCENT)
        self._search_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(6, 0))
        self._hint_idx = 0
        self._hint_focused = False
        self._hint_after_id = None
        self._search_entry.insert(0, self._active_hints()[0])
        self._search_entry.config(fg=_DIM)
        self._search_entry.bind("<FocusIn>",    lambda _: self._search_focus_in())
        self._search_entry.bind("<FocusOut>",   lambda _: self._search_focus_out())
        self._search_entry.bind("<Return>",     lambda _: self._do_search())
        self._search_entry.bind("<KP_Enter>",   lambda _: self._do_search())
        # Enter's KeyRelease must not run the installed filter — it fires
        # right after <Return> and would wipe the search results it produced.
        self._search_entry.bind(
            "<KeyRelease>",
            lambda e: None if e.keysym in ("Return", "KP_Enter")
            else self._filter_installed())
        self.after(3000, self._cycle_hint)

        self._search_btn = self._make_btn(search_frame, "PyPI ↗", self._do_search)
        self._search_btn.pack(side="right", padx=(4, 4), pady=2)

        # Source toggle (conda | PyPI) — only shown for conda interpreters,
        # where the search namespace genuinely differs (conda's `graphviz`
        # is the C tool; PyPI's is the Python bindings).
        self._src_frame = tk.Frame(search_frame, bg=_INPUT_BG)
        self._src_lbls: dict[str, tk.Label] = {}
        for src, text in (("conda", "conda"), ("pypi", "PyPI")):
            lbl = tk.Label(self._src_frame, text=text, bg=_INPUT_BG, fg=_DIM,
                           font=(UI_FONT, 8), padx=8, pady=3, cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<ButtonRelease-1>",
                     lambda _e, s=src: self._set_search_source(s))
            self._src_lbls[src] = lbl

        # ── Channel bar (conda interpreters only) ─────────────────────────────
        # Answers "what will this actually search?" without a click. Built
        # here but packed by _sync_channel_bar, which needs `before=self._pane`
        # to land above the split every time it reappears.
        #
        # Read-only in this phase, and deliberately carrying no edit
        # affordance: a `✎ Edit` label with nothing behind it reads as a dead
        # button, so it arrives with the editor rather than ahead of it.
        self._chan_frame = tk.Frame(self, bg=_BG)
        chan_top = tk.Frame(self._chan_frame, bg=_BG)
        chan_top.pack(fill="x")
        tk.Label(chan_top, text="CHANNELS", bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8, "bold")).pack(side="left", padx=(8, 8))
        self._chan_help = tk.Label(chan_top, text="?", bg=_BG, fg="#569cd6",
                                   font=(UI_FONT, 8, "bold"), cursor="hand2")
        self._chan_help.bind("<ButtonRelease-1>", lambda _: self._open_channel_guide())
        self._chan_help.bind("<Enter>", lambda _: self._chan_help.config(fg=_FG))
        self._chan_help.bind("<Leave>",
                             lambda _: self._chan_help.config(fg="#569cd6"))
        self._chan_help.pack(side="right", padx=(4, 10))
        self._chan_edit = tk.Label(chan_top, text="", bg=_BG, fg=_DIM,
                                   font=(UI_FONT, 8), cursor="hand2")
        self._chan_edit.bind("<ButtonRelease-1>", lambda _: self._edit_channels())
        self._chan_edit.bind("<Enter>", lambda _: self._chan_edit.config(fg=_FG))
        self._chan_edit.bind("<Leave>", lambda _: self._chan_edit.config(fg=_DIM))
        self._chan_edit.pack(side="right", padx=(0, 12))
        self._chan_prio = tk.Label(chan_top, text="", bg=_BG, fg=_DIM,
                                   font=(UI_FONT, 8))
        self._chan_prio.pack(side="right", padx=(0, 12))
        # Packed last so the two right-hand labels reserve their width first
        # and a long channel list truncates instead of pushing them off.
        self._chan_lbl = tk.Label(chan_top, text="", bg=_BG, fg=_FG,
                                  font=(UI_FONT, 9), anchor="w")
        self._chan_lbl.pack(side="left", fill="x", expand=True)
        self._chan_src = tk.Label(self._chan_frame, text="", bg=_BG, fg=_DIM,
                                  font=(UI_FONT, 8), anchor="w")
        self._chan_src.pack(fill="x", padx=(8, 0))

        # Scope selector — [All] or one channel. Packed into the search bar
        # beside the source toggle, since it narrows the same thing the toggle
        # switches. A tk.Menu popup rather than a Combobox, per the house rule.
        self._scope_lbl = tk.Label(search_frame, text=_SCOPE_ALL, bg=_INPUT_BG,
                                   fg=_DIM, font=(UI_FONT, 8), padx=8, pady=3,
                                   cursor="hand2")
        self._scope_lbl.bind("<ButtonRelease-1>", self._open_scope_menu)
        self._scope_lbl.bind("<Enter>", lambda _: self._scope_lbl.config(fg=_FG))
        self._scope_lbl.bind("<Leave>", lambda _: self._sync_scope_label())

        # ── Main split (left tree / right detail) ─────────────────────────────
        pane = tk.PanedWindow(self, orient="horizontal", bg=_BORDER,
                              sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True)
        self._pane = pane

        # ── Left: package list ────────────────────────────────────────────────
        left = tk.Frame(pane, bg=_BG)
        pane.add(left, minsize=180)

        header = tk.Frame(left, bg=_BG)
        header.pack(fill="x", padx=8, pady=(4, 2))
        self._tree_label = tk.Label(header, text="INSTALLED", bg=_BG, fg=_DIM,
                                    font=(UI_FONT, 8, "bold"), anchor="w")
        self._tree_label.pack(side="left", fill="x", expand=True)
        # Grouped ↔ alphabetical view toggle — the label shows the view a
        # click switches TO.
        self._view_toggle = tk.Label(header, bg=_BG, fg=_DIM,
                                     font=(UI_FONT, 8), cursor="hand2")
        self._view_toggle.pack(side="right")
        self._view_toggle.bind("<Enter>",
                               lambda _: self._view_toggle.config(fg=_FG))
        self._view_toggle.bind("<Leave>",
                               lambda _: self._view_toggle.config(fg=_DIM))
        self._view_toggle.bind("<ButtonRelease-1>", lambda _: self._toggle_view())
        self._sync_view_toggle()

        tree_frame = tk.Frame(left, bg=_BG)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Pkg.Treeview",
                         background=_BG, foreground=_FG,
                         fieldbackground=_BG, borderwidth=0,
                         rowheight=22, font=(UI_FONT, 9))
        style.configure("Pkg.Treeview.Heading",
                         background=_PANEL_BG, foreground=_DIM,
                         borderwidth=0, font=(UI_FONT, 8))
        style.map("Pkg.Treeview",
                  background=[("selected", _SEL_BG)],
                  foreground=[("selected", _FG)])

        self._tree = ttk.Treeview(tree_frame, style="Pkg.Treeview",
                                  show="tree", selectmode="browse")
        tree_sb = VerticalScrollbar(tree_frame, command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_sb.set)
        tree_sb.pack(side="right", fill="y")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Right: detail panel ───────────────────────────────────────────────
        right = tk.Frame(pane, bg=_PANEL_BG)
        pane.add(right, minsize=300)

        self._detail = _DetailPanel(right,
                                    on_install=self._install_pkg,
                                    on_uninstall=self._uninstall_pkg,
                                    on_ask_ai=self._ask_ai,
                                    on_preview=self._preview_install)
        self._detail.pack(fill="both", expand=True)
        self._register_learning()

    # ── Search placeholder / rotating hints ───────────────────────────────────

    def _search_focus_in(self) -> None:
        self._hint_focused = True
        if self._search_entry.get() in _ALL_HINTS:
            self._search_entry.delete(0, "end")
            self._search_entry.config(fg=_FG)

    def _search_focus_out(self) -> None:
        self._hint_focused = False
        if not self._search_entry.get().strip():
            hints = self._active_hints()
            self._search_entry.delete(0, "end")
            self._search_entry.insert(0, hints[self._hint_idx % len(hints)])
            self._search_entry.config(fg=_DIM)

    def _cycle_hint(self) -> None:
        """Advance the hint text every 3 s while unfocused and empty."""
        if not self._hint_focused:
            current = self._search_entry.get()
            if current in _ALL_HINTS or not current.strip():
                hints = self._active_hints()
                self._hint_idx = (self._hint_idx + 1) % len(hints)
                self._search_entry.delete(0, "end")
                self._search_entry.insert(0, hints[self._hint_idx])
                self._search_entry.config(fg=_DIM)
        rearm_after(self, 3000, self._cycle_hint)

    # ── Load installed packages ────────────────────────────────────────────────

    def _load_installed(self) -> None:
        self._tree_label.config(text="INSTALLED  (loading…)")
        self._tree.delete(*self._tree.get_children())
        self._backend.fetch_installed(self._on_installed_fetched)

    def _on_installed_fetched(self, pkgs: dict[str, str],
                              origins: dict[str, str]) -> None:
        self._installed = pkgs
        self._origins = origins
        self._populate_grouped()

    def _conda_detail_data(self, name: str) -> dict | None:
        """Detail payload built from the conda channel index, or None.

        Shared by selection and post-operation refresh so the two cannot render
        the same package from different sources.
        """
        if self._search_source != "conda" or name not in self._conda_results:
            return None
        meta = self._conda_results[name]
        summary = meta["summary"] or "(no summary in channel metadata)"
        # Where it is installed *from* is the interesting fact once it is
        # installed; before that, which channel offers it.
        origin = self._origins.get(name, "")
        provenance = (f"installed from: {mask_channel(origin)}"
                      if origin and origin != "conda"
                      else f"channel: {mask_channel(meta['channel'])}")
        return {"info": {
            "summary": f"{summary}\n\nconda package — {provenance}",
            "version": meta["version"],
            "home_page": meta["home"],
            "license": meta["license"],
        }}

    def _refresh_selected_detail(self) -> None:
        """Re-render the detail panel so its buttons match the installed list.

        Runs after every install/uninstall, and has to mirror `_on_select`'s
        source branching. It used to refresh only what was in `_pypi_cache` —
        but a conda search result never lands there, so installing one left the
        panel offering **Install** for a package whose tree row, inches away,
        had just grown a version and a channel badge.
        """
        name = self._selected_pkg
        if not name:
            return
        data = self._conda_detail_data(name)
        if data is None:
            data = self._pypi_cache.get(name)
        if data is not None:
            self._detail.show(name, data, self._installed.get(name))

    # ── Grouped / alphabetical view toggle ────────────────────────────────────

    def _sync_view_toggle(self) -> None:
        self._view_toggle.config(
            text="≡ A–Z" if self._group_view else "⊞ Groups")

    def _toggle_view(self) -> None:
        self._group_view = not self._group_view
        _settings.set("pkg_group_view", self._group_view)
        self._sync_view_toggle()
        # Re-render only when the installed list is on screen (search results
        # are already flat); a live filter re-applies through the same path.
        if self._tree_label.cget("text").startswith("INSTALLED"):
            self._filter_installed()

    # ── Grouping (instant via builtin lookup) ─────────────────────────────────

    def _origin_badge(self, name: str) -> str:
        """Provenance suffix for a row — blank when there is nothing to say.

        A badge on every package would be a badge on nothing: a fresh env has
        dozens of rows all from the same channel. Only the *exception* is
        worth marking — pip-installed, or a package that came from somewhere
        other than the channel searched first. That is exactly the case where
        provenance explains behaviour.
        """
        origin = self._origins.get(name, "")
        if origin == "pypi":
            return "  · pip"
        primary = self._primary_channel()
        if not origin or origin == "conda" or not primary:
            return ""
        return "" if origin == primary else f"  · {mask_channel(origin)}"

    def _populate_grouped(self) -> None:
        self._listing = "installed"
        self._tree.delete(*self._tree.get_children())
        self._tree_label.config(text=f"INSTALLED  ({len(self._installed)})")

        if not self._group_view:
            for name in sorted(self._installed, key=str.lower):
                ver = self._installed[name]
                badge = self._origin_badge(name)
                self._tree.insert("", "end", iid=f"pkg:{name}",
                                  text=f"  {name}  {ver}{badge}", tags=("installed",))
            self._tree.tag_configure("installed", foreground=_FG)
            self._refresh_selected_detail()
            return

        groups: dict[str, list[str]] = {}
        for name in sorted(self._installed, key=str.lower):
            # 1. Persisted cache hit
            topic = self._topic_cache.get(name)
            # 2. Builtin lookup (instant, no network)
            if topic is None:
                topic = _BUILTIN_LOOKUP.get(name.lower())
                if topic:
                    self._topic_cache[name] = topic
            # 3. Keyword scan on the package name as last resort
            if topic is None:
                topic = _topic_from_summary(name) or "Other"
                self._topic_cache[name] = topic
            groups.setdefault(topic, []).append(name)

        for cat in sorted(groups):
            pkgs = groups[cat]
            cat_iid = f"cat:{cat}"
            self._tree.insert("", "end", iid=cat_iid,
                              text=f"  {cat}  ({len(pkgs)})",
                              tags=("category",), open=True)
            for name in pkgs:
                ver = self._installed[name]
                badge = self._origin_badge(name)
                self._tree.insert(cat_iid, "end", iid=f"pkg:{name}",
                                  text=f"  {name}  {ver}{badge}", tags=("installed",))

        self._tree.tag_configure("category", foreground=_DIM)
        self._tree.tag_configure("installed", foreground=_FG)
        self._refresh_selected_detail()

    # ── Local filter (instant, no network) ────────────────────────────────────

    def _filter_installed(self) -> None:
        self._listing = "installed"
        raw = self._search_var.get().strip()
        if not raw or raw in _ALL_HINTS:
            self._populate_grouped()
            return

        query_words = raw.lower().split()

        matches: dict[str, str] = {}
        for name, ver in self._installed.items():
            topic = (self._topic_cache.get(name)
                     or _BUILTIN_LOOKUP.get(name.lower())
                     or "Other").lower()
            if any(w in name.lower() or w in topic for w in query_words):
                matches[name] = ver

        self._tree.delete(*self._tree.get_children())

        label = (f"INSTALLED  ({len(matches)} matching)"
                 if matches else "INSTALLED  (no matches)")
        self._tree_label.config(text=label)

        if matches:
            if not self._group_view:
                for name in sorted(matches, key=str.lower):
                    self._tree.insert("", "end", iid=f"pkg:{name}",
                                      text=f"  {name}  {matches[name]}",
                                      tags=("installed",))
            else:
                groups: dict[str, list[str]] = {}
                for name in sorted(matches, key=str.lower):
                    topic = (self._topic_cache.get(name)
                             or _BUILTIN_LOOKUP.get(name.lower())
                             or "Other")
                    groups.setdefault(topic, []).append(name)

                for cat in sorted(groups):
                    pkgs = groups[cat]
                    cat_iid = f"cat:{cat}"
                    self._tree.insert("", "end", iid=cat_iid,
                                      text=f"  {cat}  ({len(pkgs)})",
                                      tags=("category",), open=True)
                    for name in pkgs:
                        self._tree.insert(cat_iid, "end", iid=f"pkg:{name}",
                                          text=f"  {name}  {matches[name]}", tags=("installed",))
                self._tree.tag_configure("category", foreground=_DIM)
            self._tree.tag_configure("installed", foreground=_FG)

        # Always show a discovery-search prompt at the bottom (source-aware)
        src_label = "conda" if self._search_source == "conda" else "PyPI"
        self._tree.insert("", "end", iid="__pypi_hint__",
                          text=f"  ↗ Search {src_label} for '{raw}'",
                          tags=("pypi_hint",))
        self._tree.tag_configure("pypi_hint", foreground=_ACCENT)

    # ── Package discovery search (PyPI or conda, by source) ───────────────────

    def _do_search(self) -> None:
        query = self._search_var.get().strip()
        if not query or query in _ALL_HINTS:
            return
        if self._search_source == "conda":
            self._do_conda_search(query)
            return
        self._tree_label.config(text="PYPI RESULTS  (searching…)")
        self._tree.delete(*self._tree.get_children())
        threading.Thread(target=self._fetch_pypi_search,
                         args=(query,), daemon=True).start()

    def _do_conda_search(self, query: str) -> None:
        # Keyed on the channel set, not a bare "loaded" flag: opening a
        # different project with the same interpreter changes the channels
        # without firing any interpreter change to hang a refresh off.
        channels = self._effective_channels()
        if not self._conda_index.is_loaded_for(channels):
            self._tree_label.config(text="CONDA RESULTS  (loading channel index…)")
            self._tree.delete(*self._tree.get_children())
            self._conda_index.ensure_loaded(
                channels, on_done=lambda _n, q=query: self._run_conda_search(q))
            return
        self._run_conda_search(query)

    def _run_conda_search(self, query: str) -> None:
        self._listing = "conda"
        scope = self._scope_channel or None
        results = self._conda_index.search(query, channel=scope)
        self._conda_results = {r["name"]: r for r in results}
        self._tree.delete(*self._tree.get_children())
        where = f" in {mask_channel(scope)}" if scope else ""
        if not results:
            self._tree_label.config(text=f"CONDA RESULTS{where}  (none found)")
        else:
            self._tree_label.config(
                text=f"CONDA RESULTS{where}  ({len(results)})")
        for r in results:
            name = r["name"]
            installed = name in self._installed
            tag = "found_installed" if installed else "search"
            label = f"  {name}  ✓" if installed else f"  {name}"
            self._tree.insert("", "end", iid=f"pkg:{name}", text=label, tags=(tag,))
        self._tree.tag_configure("found_installed", foreground=_GREEN)
        self._tree.tag_configure("search", foreground=_FG)
        self._tree.insert("", "end", iid="__back__",
                          text="  ← Back to installed", tags=("back",))
        self._tree.tag_configure("back", foreground=_DIM)

    def _fetch_pypi_search(self, query: str) -> None:
        q = query.lower()
        words = q.split()

        # 1. Search the local 362K package name index — instant, no network.
        #    Tier 1: exact match
        #    Tier 2: starts with query
        #    Tier 3: query word in package name
        #    Tier 4: featured packages whose category matches a query word
        #    Tier 5: any package whose category matches a query word
        exact, starts, name_hit, feat_hit, cat_hit = [], [], [], [], []
        matching_cats = {cat for cat, pkgs in _FEATURED.items()
                         if any(w in cat.lower() for w in words)}

        for pkg, cat in _BUILTIN_LOOKUP.items():
            if pkg == q:
                exact.append(pkg)
            elif pkg.startswith(q):
                starts.append(pkg)
            elif any(w in pkg for w in words):
                name_hit.append(pkg)
            elif any(w in cat.lower() for w in words):
                cat_hit.append(pkg)

        # Promote featured packages that belong to a matched category
        starts.sort(key=len)
        name_hit.sort(key=len)
        cat_hit.sort(key=len)

        # Promote featured packages from matched categories (alphabetical order
        # so "Networking & Web" comes before "Web Frameworks", etc.)
        seen = set(exact + starts + name_hit)
        for cat_name in sorted(matching_cats):
            for pkg in _FEATURED.get(cat_name, []):
                if pkg not in seen and pkg in _BUILTIN_LOOKUP:
                    feat_hit.append(pkg)
                    seen.add(pkg)

        # Deduplicate while preserving rank order
        seen2: set[str] = set()
        results: list[str] = []
        for pkg in exact + starts[:3] + name_hit[:5] + feat_hit + cat_hit[:5]:
            if pkg not in seen2:
                results.append(pkg)
                seen2.add(pkg)
            if len(results) == 20:
                break

        # 2. If the query looks like an exact name and isn't in the lookup,
        #    confirm it exists on PyPI (handles very new / obscure packages).
        if not results and _REQUESTS_OK:
            try:
                r = _requests.get(f"https://pypi.org/pypi/{query}/json",
                                  timeout=6)
                if r.status_code == 200:
                    results = [query]
            except Exception:
                pass

        self.after(0, lambda: self._populate_search(results))

    def _populate_search(self, results: list[str]) -> None:
        self._listing = "pypi"
        self._tree.delete(*self._tree.get_children())
        if not results:
            self._tree_label.config(text="PYPI RESULTS  (none found)")
        else:
            self._tree_label.config(text=f"PYPI RESULTS  ({len(results)})")
        for name in results:   # keep PyPI's relevance order
            installed = name in self._installed
            tag = "found_installed" if installed else "search"
            label = f"  {name}  ✓" if installed else f"  {name}"
            self._tree.insert("", "end", iid=f"pkg:{name}", text=label, tags=(tag,))
        self._tree.tag_configure("found_installed", foreground=_GREEN)
        self._tree.tag_configure("search", foreground=_FG)
        self._tree.insert("", "end", iid="__back__",
                          text="  ← Back to installed", tags=("back",))
        self._tree.tag_configure("back", foreground=_DIM)

    # ── Selection ──────────────────────────────────────────────────────────────

    def _on_select(self, _=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "__back__":
            self._load_installed()
            return
        if iid == "__pypi_hint__":
            self._do_search()
            return
        if iid.startswith("cat:"):
            return
        name = iid.replace("pkg:", "")
        self._selected_pkg = name
        self._detail.show_loading(name)
        # Conda search result — details come from the channel index, not PyPI
        # (the same name may be a different product there).
        conda_data = self._conda_detail_data(name)
        if conda_data is not None:
            self._selected_src = "conda"
            self._detail.show(name, conda_data, self._installed.get(name))
            return
        # Only a search result expresses a source preference. A row picked out
        # of the installed list expresses none, and recording "pypi" for it is
        # what used to send a conda package's re-install through pip.
        self._selected_src = "pypi" if self._listing == "pypi" else ""
        if name in self._pypi_cache:
            self._detail.show(name, self._pypi_cache[name],
                              self._installed.get(name))
        else:
            threading.Thread(target=self._fetch_pypi,
                             args=(name,), daemon=True).start()

    def _fetch_pypi(self, name: str) -> None:
        data = {}
        if _REQUESTS_OK:
            try:
                r = _requests.get(f"https://pypi.org/pypi/{name}/json", timeout=8)
                if r.status_code == 200:
                    data = r.json()
            except Exception:
                pass
        self._pypi_cache[name] = data
        self.after(0, lambda: self._detail.show(
            name, data, self._installed.get(name)))

    # ── Install / Uninstall ────────────────────────────────────────────────────

    def _install_pkg(self, name: str) -> None:
        if self._backend is self._conda and self._wants_pip(name):
            # PyPI pick in a conda env → pip inside the env. Never
            # conda-install a PyPI name (conda's `graphviz` is the C tool,
            # PyPI's is the Python bindings — same name, different product).
            self._notify(
                "⚠ Installing via pip in a conda environment can conflict with "
                "conda's dependency resolver — prefer conda packages when available\n")
            self._run_backend_op("install", name, force_pip=True)
            return
        self._run_backend_op("install", name)

    def _wants_pip(self, name: str) -> bool:
        """Should this install go through pip rather than the conda backend?

        Yes in exactly two cases: the user picked a PyPI search result, or the
        package is installed and pip is where it came from (re-installing it
        with conda would swap the product underneath them).

        The third case is the point. A package selected from the *installed*
        list carries no source choice, and `_selected_src` used to record
        "pypi" for it anyway — so uninstalling a conda package and clicking
        Install on the row still in front of you silently reinstalled it from
        PyPI, warning included. With no choice and no origin on record, the
        environment's own backend is the answer.
        """
        if self._selected_src == "pypi":
            return True
        if self._selected_src:
            return False
        return self._origins.get(name, "") == "pypi"

    def _uninstall_pkg(self, name: str) -> None:
        self._run_backend_op("uninstall", name)

    def _run_backend_op(self, verb: str, name: str, force_pip: bool = False) -> None:
        # Conda-routed operations download from Anaconda's channels, which
        # require accepted Terms of Service — check before the op so the
        # user gets an Accept/Decline dialog instead of a raw conda error.
        # (pip-routed ops and the pip backend need no gate; conda list is
        # local and unaffected.)
        conda_routed = self._backend is self._conda and not force_pip and (
            verb == "install" or self._origins.get(name, "pypi") != "pypi"
        )
        if conda_routed and self._conda.conda_exe != self._tos_ok_exe:
            self._notify("Checking conda Terms of Service…\n")
            # Scoped to the channels this install will actually search — a
            # conda-forge-only project whose ~/.condarc still lists defaults
            # would otherwise be asked to accept Anaconda's ToS for a channel
            # `--override-channels` is about to exclude.
            conda_backend.fetch_tos_pending(
                self._conda.conda_exe, self._after_fn,
                lambda pending: self._on_tos_status(pending, verb, name),
                channels=self._conda.channels or None)
            return
        self._exec_backend_op(verb, name, force_pip)

    def _on_tos_status(self, pending: dict[str, str], verb: str, name: str) -> None:
        if not pending:
            self._tos_ok_exe = self._conda.conda_exe
            self._exec_backend_op(verb, name)
            return
        CondaTosDialog(
            self, pending,
            on_accept=lambda: self._on_tos_accept(verb, name),
            on_decline=lambda: self._notify(
                f"{verb} of '{name}' cancelled — conda Terms of Service not accepted\n"),
        )

    def _on_tos_accept(self, verb: str, name: str) -> None:
        self._notify("Accepting conda Terms of Service…\n")

        def _done(ok: bool, msg: str) -> None:
            if ok:
                self._tos_ok_exe = self._conda.conda_exe
                self._exec_backend_op(verb, name)
            else:
                self._notify(f"Could not accept the Terms of Service: {msg}\n")

        conda_backend.accept_tos(self._conda.conda_exe, self._after_fn, _done)

    def _exec_backend_op(self, verb: str, name: str, force_pip: bool = False) -> None:
        output = self._get_output_panel() if self._get_output_panel else None
        origin = self._origins.get(name, "pypi")
        backend = self._pip if force_pip else self._backend
        if backend is self._conda:
            scope = f" -c {mask_channel(self._scope_channel)} --override-channels" \
                if self._scope_channel else ""
            echo = {"install": f"$ conda install -y{scope} {name}",
                    "uninstall": (f"$ pip uninstall -y {name}" if origin == "pypi"
                                  else f"$ conda remove -y {name}")}[verb]
        else:
            echo = {"install": f"$ pip install {name}",
                    "uninstall": f"$ pip uninstall -y {name}"}[verb]
        if output:
            # Switch bottom panel to OUTPUT tab so user sees progress
            try:
                output.master._set_active("output")
            except Exception:
                pass
            output.write(f"\n{echo}\n", tag="cmd")

        def _on_line(line: str) -> None:
            if output:
                output.write(line)

        on_error = (lambda e: output.write(e + "\n", tag="err")) if output else None
        if verb == "install":
            if backend is self._conda and self._scope_channel:
                backend.install(name, on_line=_on_line,
                                on_done=self._op_done, on_error=on_error,
                                only_channel=self._scope_channel)
            else:
                backend.install(name, on_line=_on_line,
                                on_done=self._op_done, on_error=on_error)
        else:
            backend.uninstall(name, origin, on_line=_on_line,
                              on_done=self._op_done, on_error=on_error)

    def _op_done(self) -> None:
        """Refresh our own tree, then tell everyone else the environment moved.

        Deliberately fires on failure too — both backends call on_done whether
        or not the operation succeeded, and the honest response to "we don't
        know what happened" is to make every cached answer re-derive itself. A
        needless re-probe costs a subprocess; a missed one is the bug this
        callback exists for.
        """
        self._load_installed()
        if self._on_packages_changed:
            self._on_packages_changed()

    # ── Install preview (dry run) ─────────────────────────────────────────────

    def _preview_install(self, name: str) -> None:
        """Solve *name* without installing it and report what conda would do.

        The answer to "where would this actually come from, and is something
        here fighting?" without installing anything or editing a git-tracked
        file to run the experiment.
        """
        if self._backend is not self._conda:
            return
        output = self._get_output_panel() if self._get_output_panel else None
        scope = self._scope_channel or None
        flags = (f" -c {mask_channel(scope)} --override-channels" if scope
                 else "")
        if output:
            try:
                output.master._set_active("output")
            except Exception:
                pass
            output.write(f"\n$ conda install --dry-run{flags} {name}\n", tag="cmd")
            output.write("Solving — nothing will be installed…\n", tag="info")

        def _done(ok: bool, packages: list, message: str) -> None:
            if not output:
                return
            if not ok:
                output.write(f"\n✗ {name} cannot be installed as configured.\n",
                             tag="err")
                # conda's own conflict text names the packages involved, which
                # is the part that actually identifies the culprit channel.
                if message:
                    output.write(message.rstrip() + "\n", tag="err")
                return
            if not packages:
                output.write(f"✓ {message or 'Nothing to do.'}\n", tag="info")
                return
            output.write(f"\n✓ {len(packages)} package(s) would be installed:\n",
                         tag="info")
            # Both columns are measured, not just the name. A conda version can
            # be far wider than any fixed guess (`12.0.0.r4.gg4f2fc60ca`), and
            # one overflowing row shunts its channel out of line — which is the
            # column you are actually scanning down.
            name_w = max(len(p[0]) for p in packages)
            ver_w = max(len(p[1]) for p in packages)
            for pkg, version, channel in sorted(packages):
                output.write(f"    {pkg.ljust(name_w)}  {version.ljust(ver_w)}  "
                             f"{mask_channel(channel)}\n")
            # `preview_note_channels` owns which channel this is measured
            # against; the label has to name the same one or the note reads as
            # a non-sequitur.
            baseline = self._scope_channel or self._primary_channel()
            others = preview_note_channels(packages, self._scope_channel,
                                           self._primary_channel())
            if others:
                output.write(
                    f"\n  Note: {len(others)} channel(s) other than "
                    f"{mask_channel(baseline) or 'the first'} would be used — "
                    f"{', '.join(mask_channel(c) for c in others)}.\n",
                    tag="info")

        self._conda.dry_run(name, _done, only_channel=scope)

    def _primary_channel(self) -> str:
        """The channel searched first, which is what a badge is measured against."""
        channels = self._effective_channels()
        return channels[0] if channels else ""

    # ── Ask AI ─────────────────────────────────────────────────────────────────

    def _ask_ai(self, name: str, summary: str) -> None:
        if self._open_ai_panel:
            self._open_ai_panel()
        ai = self._get_ai_panel() if self._get_ai_panel else None
        if not ai:
            return
        prompt = (f"Show me practical beginner-friendly usage examples for the "
                  f"Python package **{name}**."
                  f"{(' It is described as: ' + summary) if summary else ''} "
                  f"Include 2-3 short, real-world code snippets with comments.")
        ai.send_prefilled(prompt)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _open_guide(self) -> None:
        GuideWindow(self, "Package Manager", [
            GuidePage(
                title="What is a Package?",
                sections=[
                    ("THE IDEA",
                     "A package is a bundle of reusable Python code written by someone else "
                     "that you can drop into your project. Instead of writing everything from scratch, "
                     "you install a package and call its functions.", "#569cd6"),
                    ("EXAMPLES",
                     "• requests — send HTTP requests in two lines of code\n"
                     "• pandas — load, filter, and analyse tables of data\n"
                     "• pillow — open, crop, resize, and save images\n"
                     "• pytest — run automated tests on your code\n"
                     "• flask — build a web server with almost no boilerplate", "#cccccc"),
                    ("WHERE THEY COME FROM",
                     "Most Python packages live on PyPI — the Python Package Index at pypi.org. "
                     "PyPI hosts over 500,000 packages. When you run 'pip install requests', "
                     "pip downloads the package from PyPI and installs it into your environment.", "#e2c08d"),
                ],
                plain_english=(
                    "Think of packages like apps on your phone. You don't build a GPS engine "
                    "to get directions — you install Google Maps. Someone already solved the hard "
                    "part, packaged it up, and shared it. You just install it and use it."
                ),
            ),
            GuidePage(
                title="Installing & Uninstalling",
                sections=[
                    ("INSTALL",
                     "pip install <name>\n\n"
                     "Use the search bar above to find a package on PyPI, then click Install "
                     "in the detail panel. You can also type the exact name you want.", "#73c991"),
                    ("UNINSTALL",
                     "pip uninstall <name>\n\n"
                     "Select an installed package from the list on the left and click Uninstall "
                     "in the detail panel. The package is removed from your current environment.", "#f14c4c"),
                    ("VERSION PINNING",
                     "To install a specific version: pip install requests==2.31.0\n\n"
                     "Useful when a newer version breaks your code. Pin the version in "
                     "requirements.txt to keep things stable.", "#cccccc"),
                ],
                plain_english=(
                    "Installing a package is like downloading an app — one command and it's ready. "
                    "The Package Manager here does both install and uninstall with a click "
                    "so you never have to leave the IDE."
                ),
            ),
            GuidePage(
                title="Managing Dependencies",
                sections=[
                    ("requirements.txt",
                     "pip freeze > requirements.txt\n\n"
                     "Creates a text file listing every installed package and its exact version. "
                     "Commit this file so teammates can recreate the same environment.", "#569cd6"),
                    ("RESTORING",
                     "pip install -r requirements.txt\n\n"
                     "Anyone who clones your project runs this one command and gets an identical "
                     "environment instantly.", "#73c991"),
                    ("USE A VIRTUAL ENVIRONMENT",
                     "Always install packages inside a virtual environment (venv) rather than "
                     "globally. This keeps your project's dependencies isolated and prevents "
                     "conflicts. See '? Learn about virtual environments' in the New Project wizard.", "#e2c08d"),
                ],
                plain_english=(
                    "requirements.txt is your project's shopping list. Don't commit the groceries "
                    "(the venv) — just the list. Anyone who needs to restock reads the list and "
                    "buys exactly what's needed. Fast, repeatable, clean."
                ),
            ),
            GuidePage(
                title="Finding the Right Package",
                sections=[
                    ("SEARCH PyPI",
                     "Use the search bar at the top of the Package Manager. It searches PyPI "
                     "in real time and groups results by category so you can quickly compare options. "
                     "In a conda environment a conda | PyPI toggle appears — conda mode searches "
                     "your configured conda channels instead.", "#569cd6"),
                    ("WHAT TO LOOK FOR",
                     "• Download count — high numbers mean battle-tested\n"
                     "• Last release date — actively maintained?\n"
                     "• License — MIT/Apache are permissive; GPL has restrictions\n"
                     "• Dependencies — fewer is usually safer", "#cccccc"),
                    ("ASK THE AI",
                     "Not sure which package fits? Click 'Ask AI ✦' in the detail panel or open "
                     "AI Chat (F5) and describe what you're trying to do. The AI can compare "
                     "packages and suggest the best fit.", "#e2c08d"),
                ],
                plain_english=(
                    "With 500,000+ packages on PyPI, picking the right one matters. "
                    "A package last updated in 2017 or with open security issues is a liability. "
                    "When in doubt, ask the AI — it's read the docs so you don't have to."
                ),
            ),
            GuidePage(
                title="Conda Environments",
                sections=[
                    ("WHEN CONDA TAKES OVER",
                     "If your active interpreter is a conda environment, this panel automatically "
                     "routes installs and uninstalls through conda instead of pip, and a "
                     "conda | PyPI toggle appears next to the search bar. Conda search looks "
                     "through your configured channels — exactly what 'conda install' can reach.", "#569cd6"),
                    ("SAME NAME, DIFFERENT PACKAGE",
                     "Conda channels and PyPI sometimes reuse a name for different products. "
                     "On conda, 'graphviz' is the C drawing tool and the Python bindings are "
                     "'python-graphviz' — while on PyPI, 'graphviz' IS the Python bindings. "
                     "Check the summary in the detail panel before installing.", "#e2c08d"),
                    ("MIXING PIP INTO A CONDA ENV",
                     "Pip-installed packages inside a conda env show a '· pip' badge in the "
                     "installed list, and Uninstall automatically uses the right tool for each. "
                     "Prefer conda packages first; flip the search toggle to PyPI when a package "
                     "isn't on your channels.", "#cccccc"),
                    ("FIRST-TIME SETUP",
                     "Anaconda's default channels require accepting their Terms of Service once. "
                     "If that's still pending, the panel shows an Accept/Decline dialog before "
                     "the first conda operation — your acceptance is stored by conda itself.", "#73c991"),
                ],
                plain_english=(
                    "Think of conda and PyPI as two different app stores. Most apps exist in "
                    "both, but a few share a name and aren't the same thing at all. When your "
                    "project lives in a conda environment, this panel shops at the conda store "
                    "by default — and clearly labels anything that came from the other store."
                ),
            ),
        ])

    def _register_learning(self) -> None:
        """Register package manager widgets with Learning Mode (called after _build)."""
        LearningManager.register(self._search_entry,       "pkg_search")
        LearningManager.register(self._search_btn,         "pkg_search")
        LearningManager.register(self._tree,               "pkg_list")
        LearningManager.register(self._detail._install_btn,   "pkg_install")
        LearningManager.register(self._detail._uninstall_btn, "pkg_uninstall")

    def _make_btn(self, parent, text: str, cmd: Callable) -> tk.Label:
        btn = tk.Label(parent, text=text, bg=_INPUT_BG, fg=_FG,
                       font=(UI_FONT, 8), cursor="hand2", padx=8, pady=3)
        btn.bind("<Button-1>", lambda _: cmd())
        btn.bind("<Enter>",    lambda _: btn.config(bg="#505050"))
        btn.bind("<Leave>",    lambda _: btn.config(bg=_INPUT_BG))
        return btn


# ── Detail Panel ──────────────────────────────────────────────────────────────

class _DetailPanel(tk.Frame):
    """Right-side panel showing package metadata and action buttons."""

    def __init__(self, parent,
                 on_install: Callable,
                 on_uninstall: Callable,
                 on_ask_ai: Callable,
                 on_preview: Callable | None = None,
                 **kwargs) -> None:
        super().__init__(parent, bg=_PANEL_BG, **kwargs)
        self._on_install   = on_install
        self._on_uninstall = on_uninstall
        self._on_ask_ai    = on_ask_ai
        self._on_preview   = on_preview
        self._current_name = ""
        self._current_summary = ""
        self._build()
        self._show_placeholder()

    def _build(self) -> None:
        header = tk.Frame(self, bg=_PANEL_BG)
        header.pack(fill="x", padx=16, pady=(14, 0))

        self._name_lbl = tk.Label(header, text="", bg=_PANEL_BG, fg=_FG,
                                  font=(UI_FONT, 14, "bold"), anchor="w")
        self._name_lbl.pack(side="left")

        self._ver_lbl = tk.Label(header, text="", bg=_PANEL_BG, fg=_DIM,
                                 font=(UI_FONT, 10), anchor="w")
        self._ver_lbl.pack(side="left", padx=(8, 0))

        btn_row = tk.Frame(self, bg=_PANEL_BG)
        btn_row.pack(fill="x", padx=16, pady=(8, 0))

        self._install_btn = self._make_action_btn(btn_row, "⬇ Install",
                                                   _ACCENT, self._do_install)
        self._install_btn.pack(side="left", padx=(0, 6))

        self._uninstall_btn = self._make_action_btn(btn_row, "✕ Uninstall",
                                                     "#5a1a1a", self._do_uninstall)
        self._uninstall_btn.pack(side="left", padx=(0, 6))

        # Shown only for conda-backed panels — pip has no equivalent solve to
        # preview, so the button would be a promise pip cannot keep.
        self._preview_btn = self._make_action_btn(btn_row, "⇢ Preview",
                                                   _GREY_BTN, self._do_preview)

        self._ai_btn = self._make_action_btn(btn_row, "✦ Ask AI for examples",
                                              "#1a3a2a", self._do_ask_ai)
        self._ai_btn.pack(side="left")

        tk.Frame(self, bg=_BORDER, height=1).pack(fill="x", padx=16, pady=10)

        meta = tk.Frame(self, bg=_PANEL_BG)
        meta.pack(fill="x", padx=16)

        self._author_lbl  = self._meta_label(meta)
        self._license_lbl = self._meta_label(meta)
        self._home_lbl    = self._meta_label(meta)

        tk.Frame(self, bg=_BORDER, height=1).pack(fill="x", padx=16, pady=10)

        tk.Label(self, text="DESCRIPTION", bg=_PANEL_BG, fg=_DIM,
                 font=(UI_FONT, 8, "bold"), anchor="w").pack(fill="x", padx=16)

        desc_frame = tk.Frame(self, bg=_PANEL_BG)
        desc_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        self._desc_text = tk.Text(desc_frame, bg=_PANEL_BG, fg=_FG,
                                  font=(UI_FONT, 9), wrap="word",
                                  relief="flat", bd=0,
                                  state="disabled", cursor="arrow",
                                  highlightthickness=0)
        desc_sb = VerticalScrollbar(desc_frame, command=self._desc_text.yview)
        self._desc_text.configure(yscrollcommand=desc_sb.set)
        desc_sb.pack(side="right", fill="y")
        self._desc_text.pack(fill="both", expand=True)

    def _meta_label(self, parent) -> tk.Label:
        lbl = tk.Label(parent, text="", bg=_PANEL_BG, fg=_DIM,
                       font=(UI_FONT, 8), anchor="w", justify="left")
        lbl.pack(fill="x", pady=1)
        return lbl

    def _make_action_btn(self, parent, text: str,
                         bg: str, cmd: Callable) -> tk.Label:
        def _hover_color(base: str) -> str:
            # Lighten the hex color slightly for hover
            try:
                r = min(255, int(base[1:3], 16) + 30)
                g = min(255, int(base[3:5], 16) + 30)
                b = min(255, int(base[5:7], 16) + 30)
                return f"#{r:02x}{g:02x}{b:02x}"
            except Exception:
                return base

        btn = tk.Label(parent, text=text, bg=bg, fg="white",
                       font=(UI_FONT, 8), cursor="hand2",
                       padx=10, pady=4)
        btn._base_bg = bg

        # Keep a direct reference to the original config so hover bindings
        # never accidentally mutate _base_bg.
        _orig_config = btn.config

        def _enter(_):
            if btn.cget("state") != "disabled":
                _orig_config(bg=_hover_color(btn._base_bg))

        def _leave(_):
            _orig_config(bg=btn._base_bg)

        btn.bind("<Button-1>", lambda _: cmd() if btn.cget("state") != "disabled" else None)
        btn.bind("<Enter>", _enter)
        btn.bind("<Leave>", _leave)

        # Patch public config so callers that change bg (enable/disable) also
        # update _base_bg so the next hover uses the right base color.
        def _patched_config(*a, **kw):
            _orig_config(*a, **kw)
            if "bg" in kw:
                btn._base_bg = kw["bg"]
        btn.config = _patched_config

        return btn

    def _show_placeholder(self) -> None:
        self._name_lbl.config(text="Select a package")
        self._ver_lbl.config(text="")
        self._author_lbl.config(text="")
        self._license_lbl.config(text="")
        self._home_lbl.config(text="")
        self._install_btn.config(state="disabled")
        self._uninstall_btn.config(state="disabled")
        self._preview_btn.config(state="disabled")
        self._ai_btn.config(state="disabled")
        self._set_desc("Click any package on the left to see its details.")

    def show_loading(self, name: str) -> None:
        self._current_name = name
        self._name_lbl.config(text=name)
        self._ver_lbl.config(text="")
        self._author_lbl.config(text="")
        self._license_lbl.config(text="")
        self._home_lbl.config(text="")
        self._set_desc("Loading…")

    def show(self, name: str, data: dict, installed_ver: str | None) -> None:
        if name != self._current_name:
            return
        info = data.get("info", {})
        self._current_summary = info.get("summary", "")

        self._name_lbl.config(text=name)
        latest = info.get("version", "")
        if installed_ver:
            ver_text = f"v{installed_ver} installed"
            if latest and latest != installed_ver:
                ver_text += f"  (latest: {latest})"
        else:
            ver_text = f"latest: {latest}" if latest else ""
        self._ver_lbl.config(text=ver_text)

        author = info.get("author") or info.get("author_email") or ""
        self._author_lbl.config(text=f"Author: {author}" if author else "")
        lic = info.get("license") or ""
        self._license_lbl.config(text=f"License: {lic}" if lic else "")
        home = info.get("home_page") or info.get("project_url") or ""
        self._home_lbl.config(text=f"Homepage: {home}" if home else "")

        if installed_ver:
            self._install_btn.config(state="disabled", bg="#333333", cursor="arrow")
            self._uninstall_btn.config(state="normal", bg="#5a1a1a", cursor="hand2")
        else:
            self._install_btn.config(state="normal", bg=_ACCENT, cursor="hand2")
            self._uninstall_btn.config(state="disabled", bg="#333333", cursor="arrow")
        self._preview_btn.config(
            state="disabled" if installed_ver else "normal",
            bg="#333333" if installed_ver else _GREY_BTN,
            cursor="arrow" if installed_ver else "hand2")
        self._ai_btn.config(state="normal", bg="#1a3a2a", cursor="hand2")

        desc = info.get("summary") or ""
        if not data:
            desc = "Could not fetch package information from PyPI."
        self._set_desc(desc)

    def _set_desc(self, text: str) -> None:
        self._desc_text.config(state="normal")
        self._desc_text.delete("1.0", "end")
        self._desc_text.insert("1.0", text)
        self._desc_text.config(state="disabled")

    def _do_install(self) -> None:
        if self._current_name:
            self._on_install(self._current_name)

    def _do_uninstall(self) -> None:
        if self._current_name:
            self._on_uninstall(self._current_name)

    def _do_preview(self) -> None:
        if self._current_name and self._on_preview:
            self._on_preview(self._current_name)

    def set_preview_visible(self, visible: bool) -> None:
        """Show ⇢ Preview only for a conda backend — pip has no solve to show."""
        if visible:
            self._preview_btn.pack(side="left", padx=(0, 6),
                                   before=self._ai_btn)
        else:
            self._preview_btn.pack_forget()

    def _do_ask_ai(self) -> None:
        if self._current_name:
            self._on_ask_ai(self._current_name, self._current_summary)
