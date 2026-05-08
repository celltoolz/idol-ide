"""Package Manager panel — browse installed packages, search PyPI, install/uninstall."""
from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from editor.pip_manager import PipManager
from widgets.learning_manager import LearningManager
from utils.thread_safe_after import make_thread_safe_after
from widgets.guide_window import GuideWindow, GuidePage

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
                 **kwargs) -> None:
        super().__init__(parent, bg=_BG, **kwargs)
        self._get_output_panel = get_output_panel
        self._get_ai_panel     = get_ai_panel
        self._open_ai_panel    = open_ai_panel
        self._installed: dict[str, str] = {}   # name → version
        self._selected_pkg: str = ""
        self._pypi_cache: dict[str, dict] = {}   # per-session detail cache
        self._topic_cache: dict[str, str] = {}   # name → topic (persisted)
        self._load_topic_cache()
        self._pip = PipManager(after_fn=make_thread_safe_after(self))
        self._build()
        self.after(100, self._load_installed)

    def set_python(self, exe: str) -> None:
        """Switch the active interpreter and refresh the installed package list."""
        self._pip.set_python(exe)
        self._load_installed()

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
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=10, pady=6)

        self._refresh_btn = self._make_btn(toolbar, "↻ Refresh", self._load_installed)
        self._refresh_btn.pack(side="right", padx=(0, 8), pady=4)

        self._guide_lbl = tk.Label(
            toolbar, text="? Learn about Package Manager",
            bg=_PANEL_BG, fg="#569cd6", font=("Segoe UI", 8), cursor="hand2",
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
                                      font=("Segoe UI", 10), relief="flat", bd=0,
                                      highlightthickness=1, highlightbackground=_BORDER,
                                      highlightcolor=_ACCENT)
        self._search_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(6, 0))
        self._hint_idx = 0
        self._hint_focused = False
        self._hint_after_id = None
        self._search_entry.insert(0, _HINTS[0])
        self._search_entry.config(fg=_DIM)
        self._search_entry.bind("<FocusIn>",    lambda _: self._search_focus_in())
        self._search_entry.bind("<FocusOut>",   lambda _: self._search_focus_out())
        self._search_entry.bind("<Return>",     lambda _: self._do_pypi_search())
        self._search_entry.bind("<KeyRelease>", lambda _: self._filter_installed())
        self.after(3000, self._cycle_hint)

        self._search_btn = self._make_btn(search_frame, "PyPI ↗", self._do_pypi_search)
        self._search_btn.pack(side="right", padx=(4, 4), pady=2)

        # ── Main split (left tree / right detail) ─────────────────────────────
        pane = tk.PanedWindow(self, orient="horizontal", bg=_BORDER,
                              sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # ── Left: package list ────────────────────────────────────────────────
        left = tk.Frame(pane, bg=_BG)
        pane.add(left, minsize=180)

        self._tree_label = tk.Label(left, text="INSTALLED", bg=_BG, fg=_DIM,
                                    font=("Segoe UI", 8, "bold"), anchor="w")
        self._tree_label.pack(fill="x", padx=8, pady=(4, 2))

        tree_frame = tk.Frame(left, bg=_BG)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Pkg.Treeview",
                         background=_BG, foreground=_FG,
                         fieldbackground=_BG, borderwidth=0,
                         rowheight=22, font=("Segoe UI", 9))
        style.configure("Pkg.Treeview.Heading",
                         background=_PANEL_BG, foreground=_DIM,
                         borderwidth=0, font=("Segoe UI", 8))
        style.map("Pkg.Treeview",
                  background=[("selected", _SEL_BG)],
                  foreground=[("selected", _FG)])

        self._tree = ttk.Treeview(tree_frame, style="Pkg.Treeview",
                                  show="tree", selectmode="browse")
        tree_sb = ttk.Scrollbar(tree_frame, orient="vertical",
                                command=self._tree.yview)
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
                                    on_ask_ai=self._ask_ai)
        self._detail.pack(fill="both", expand=True)
        self._register_learning()

    # ── Search placeholder / rotating hints ───────────────────────────────────

    def _search_focus_in(self) -> None:
        self._hint_focused = True
        if self._search_entry.get() in _HINTS:
            self._search_entry.delete(0, "end")
            self._search_entry.config(fg=_FG)

    def _search_focus_out(self) -> None:
        self._hint_focused = False
        if not self._search_entry.get().strip():
            self._search_entry.delete(0, "end")
            self._search_entry.insert(0, _HINTS[self._hint_idx])
            self._search_entry.config(fg=_DIM)

    def _cycle_hint(self) -> None:
        """Advance the hint text every 3 s while unfocused and empty."""
        if not self._hint_focused:
            current = self._search_entry.get()
            if current in _HINTS or not current.strip():
                self._hint_idx = (self._hint_idx + 1) % len(_HINTS)
                self._search_entry.delete(0, "end")
                self._search_entry.insert(0, _HINTS[self._hint_idx])
                self._search_entry.config(fg=_DIM)
        try:
            self.after(3000, self._cycle_hint)
        except Exception:
            pass  # widget destroyed

    # ── Load installed packages ────────────────────────────────────────────────

    def _load_installed(self) -> None:
        self._tree_label.config(text="INSTALLED  (loading…)")
        self._tree.delete(*self._tree.get_children())
        self._pip.fetch_installed(self._on_installed_fetched)

    def _on_installed_fetched(self, pkgs: dict[str, str]) -> None:
        self._installed = pkgs
        self._populate_grouped()

    def _refresh_selected_detail(self) -> None:
        """Re-render the detail panel with updated installed status after a pip op."""
        if self._selected_pkg and self._selected_pkg in self._pypi_cache:
            self._detail.show(self._selected_pkg,
                              self._pypi_cache[self._selected_pkg],
                              self._installed.get(self._selected_pkg))

    # ── Grouping (always-on, instant via builtin lookup) ─────────────────────

    def _populate_grouped(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._tree_label.config(text=f"INSTALLED  ({len(self._installed)})")

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
                self._tree.insert(cat_iid, "end", iid=f"pkg:{name}",
                                  text=f"  {name}  {ver}", tags=("installed",))

        self._tree.tag_configure("category", foreground=_DIM)
        self._tree.tag_configure("installed", foreground=_FG)
        self._refresh_selected_detail()

    # ── Local filter (instant, no network) ────────────────────────────────────

    def _filter_installed(self) -> None:
        raw = self._search_var.get().strip()
        if not raw or raw in _HINTS:
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

        # Always show a PyPI search prompt at the bottom
        self._tree.insert("", "end", iid="__pypi_hint__",
                          text=f"  ↗ Search PyPI for '{raw}'",
                          tags=("pypi_hint",))
        self._tree.tag_configure("pypi_hint", foreground=_ACCENT)

    # ── PyPI discovery search ─────────────────────────────────────────────────

    def _do_pypi_search(self) -> None:
        query = self._search_var.get().strip()
        if not query or query in _HINTS:
            return
        self._tree_label.config(text="PYPI RESULTS  (searching…)")
        self._tree.delete(*self._tree.get_children())
        threading.Thread(target=self._fetch_pypi_search,
                         args=(query,), daemon=True).start()

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
            self._do_pypi_search()
            return
        if iid.startswith("cat:"):
            return
        name = iid.replace("pkg:", "")
        self._selected_pkg = name
        self._detail.show_loading(name)
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
        self._run_pip(["install", name])

    def _uninstall_pkg(self, name: str) -> None:
        self._run_pip(["uninstall", "-y", name])

    def _run_pip(self, args: list[str]) -> None:
        output = self._get_output_panel() if self._get_output_panel else None
        if output:
            # Switch bottom panel to OUTPUT tab so user sees progress
            try:
                output.master._set_active("output")
            except Exception:
                pass
            output.write(f"\n$ pip {' '.join(args)}\n", tag="cmd")

        def _on_line(line: str) -> None:
            if output:
                output.write(line)

        self._pip.run_operation(
            args,
            on_line=_on_line,
            on_done=self._load_installed,
            on_error=(lambda e: output.write(e + "\n", tag="err")) if output else None,
        )

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
                     "in real time and groups results by category so you can quickly compare options.", "#569cd6"),
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
                       font=("Segoe UI", 8), cursor="hand2", padx=8, pady=3)
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
                 **kwargs) -> None:
        super().__init__(parent, bg=_PANEL_BG, **kwargs)
        self._on_install   = on_install
        self._on_uninstall = on_uninstall
        self._on_ask_ai    = on_ask_ai
        self._current_name = ""
        self._current_summary = ""
        self._build()
        self._show_placeholder()

    def _build(self) -> None:
        header = tk.Frame(self, bg=_PANEL_BG)
        header.pack(fill="x", padx=16, pady=(14, 0))

        self._name_lbl = tk.Label(header, text="", bg=_PANEL_BG, fg=_FG,
                                  font=("Segoe UI", 14, "bold"), anchor="w")
        self._name_lbl.pack(side="left")

        self._ver_lbl = tk.Label(header, text="", bg=_PANEL_BG, fg=_DIM,
                                 font=("Segoe UI", 10), anchor="w")
        self._ver_lbl.pack(side="left", padx=(8, 0))

        btn_row = tk.Frame(self, bg=_PANEL_BG)
        btn_row.pack(fill="x", padx=16, pady=(8, 0))

        self._install_btn = self._make_action_btn(btn_row, "⬇ Install",
                                                   _ACCENT, self._do_install)
        self._install_btn.pack(side="left", padx=(0, 6))

        self._uninstall_btn = self._make_action_btn(btn_row, "✕ Uninstall",
                                                     "#5a1a1a", self._do_uninstall)
        self._uninstall_btn.pack(side="left", padx=(0, 6))

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
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", padx=16)

        desc_frame = tk.Frame(self, bg=_PANEL_BG)
        desc_frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        self._desc_text = tk.Text(desc_frame, bg=_PANEL_BG, fg=_FG,
                                  font=("Segoe UI", 9), wrap="word",
                                  relief="flat", bd=0,
                                  state="disabled", cursor="arrow",
                                  highlightthickness=0)
        desc_sb = ttk.Scrollbar(desc_frame, orient="vertical",
                                command=self._desc_text.yview)
        self._desc_text.configure(yscrollcommand=desc_sb.set)
        desc_sb.pack(side="right", fill="y")
        self._desc_text.pack(fill="both", expand=True)

    def _meta_label(self, parent) -> tk.Label:
        lbl = tk.Label(parent, text="", bg=_PANEL_BG, fg=_DIM,
                       font=("Segoe UI", 8), anchor="w", justify="left")
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
                       font=("Segoe UI", 8), cursor="hand2",
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

    def _do_ask_ai(self) -> None:
        if self._current_name:
            self._on_ask_ai(self._current_name, self._current_summary)
