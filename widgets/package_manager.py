"""Package Manager panel — browse installed packages, search PyPI, install/uninstall."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

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

_CACHE_FILE = Path.home() / ".notepad_ide" / "pkg_cache.json"


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
                 **kwargs) -> None:
        super().__init__(parent, bg=_BG, **kwargs)
        self._get_output_panel = get_output_panel
        self._get_ai_panel     = get_ai_panel
        self._installed: dict[str, str] = {}   # name → version
        self._selected_pkg: str = ""
        self._pypi_cache: dict[str, dict] = {}   # per-session detail cache
        self._topic_cache: dict[str, str] = {}   # name → topic (persisted)
        self._grouped = False
        self._grouping_active = False
        self._load_topic_cache()
        self._build()
        self.after(100, self._load_installed)

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

        self._group_btn = self._make_btn(toolbar, "⊞ Group by Topic", self._toggle_group)
        self._group_btn.pack(side="right", padx=(0, 4), pady=4)

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
        self._search_entry.insert(0, "Search PyPI…")
        self._search_entry.config(fg=_DIM)
        self._search_entry.bind("<FocusIn>",  lambda _: self._search_focus_in())
        self._search_entry.bind("<FocusOut>", lambda _: self._search_focus_out())
        self._search_entry.bind("<Return>",   lambda _: self._do_search())

        self._search_btn = self._make_btn(search_frame, "Search", self._do_search)
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

    # ── Search placeholder helpers ─────────────────────────────────────────────

    def _search_focus_in(self) -> None:
        if self._search_entry.get() == "Search PyPI…":
            self._search_entry.delete(0, "end")
            self._search_entry.config(fg=_FG)

    def _search_focus_out(self) -> None:
        if not self._search_entry.get().strip():
            self._search_entry.insert(0, "Search PyPI…")
            self._search_entry.config(fg=_DIM)

    # ── Load installed packages ────────────────────────────────────────────────

    def _load_installed(self) -> None:
        self._grouped = False
        self._group_btn.config(text="⊞ Group by Topic")
        self._tree_label.config(text="INSTALLED  (loading…)")
        self._tree.delete(*self._tree.get_children())
        threading.Thread(target=self._fetch_installed, daemon=True).start()

    def _fetch_installed(self) -> None:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True, text=True, timeout=15
            )
            pkgs = json.loads(result.stdout)
            self._installed = {p["name"]: p["version"] for p in pkgs}
        except Exception:
            self._installed = {}
        self.after(0, self._populate_flat)

    def _populate_flat(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._tree_label.config(text=f"INSTALLED  ({len(self._installed)})")
        for name in sorted(self._installed, key=str.lower):
            ver = self._installed[name]
            self._tree.insert("", "end", iid=f"pkg:{name}",
                              text=f"  {name}  {ver}", tags=("installed",))
        self._tree.tag_configure("installed", foreground=_FG)

    # ── Grouping ──────────────────────────────────────────────────────────────

    def _toggle_group(self) -> None:
        if self._grouping_active:
            return   # already fetching
        if self._grouped:
            # Switch back to flat
            self._grouped = False
            self._group_btn.config(text="⊞ Group by Topic")
            self._populate_flat()
            return

        # Need to fetch topics for packages not yet cached
        missing = [n for n in self._installed if n not in self._topic_cache]
        if missing:
            self._grouping_active = True
            self._group_btn.config(text=f"  Fetching 0/{len(missing)}…")
            threading.Thread(target=self._fetch_topics,
                             args=(missing,), daemon=True).start()
        else:
            self._grouped = True
            self._group_btn.config(text="⊟ Flat list")
            self._populate_grouped()

    def _fetch_topics(self, names: list[str]) -> None:
        total = len(names)
        for i, name in enumerate(names):
            if name in self._topic_cache:
                continue
            topic = "Other"
            if _REQUESTS_OK:
                try:
                    r = _requests.get(f"https://pypi.org/pypi/{name}/json",
                                      timeout=6)
                    if r.status_code == 200:
                        data = r.json()
                        classifiers = data.get("info", {}).get("classifiers", [])
                        topic = _topic_from_classifiers(classifiers)
                        # Also cache the full data for the detail panel
                        self._pypi_cache[name] = data
                except Exception:
                    pass
            self._topic_cache[name] = topic
            progress = i + 1
            self.after(0, lambda p=progress, t=total:
                       self._group_btn.config(text=f"  Fetching {p}/{t}…"))

        self._save_topic_cache()
        self.after(0, self._on_topics_ready)

    def _on_topics_ready(self) -> None:
        self._grouping_active = False
        self._grouped = True
        self._group_btn.config(text="⊟ Flat list")
        self._populate_grouped()

    def _populate_grouped(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._tree_label.config(text=f"INSTALLED  ({len(self._installed)})  — by topic")

        groups: dict[str, list[str]] = {}
        for name in sorted(self._installed, key=str.lower):
            topic = self._topic_cache.get(name, "Other")
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

    # ── PyPI search ────────────────────────────────────────────────────────────

    def _do_search(self) -> None:
        query = self._search_var.get().strip()
        if not query or query == "Search PyPI…":
            return
        self._tree_label.config(text="SEARCH RESULTS  (searching…)")
        self._tree.delete(*self._tree.get_children())
        threading.Thread(target=self._fetch_search,
                         args=(query,), daemon=True).start()

    def _fetch_search(self, query: str) -> None:
        results = []
        if _REQUESTS_OK:
            # Exact match first
            try:
                r = _requests.get(f"https://pypi.org/pypi/{query}/json", timeout=5)
                if r.status_code == 200:
                    results = [query]
            except Exception:
                pass
            # XML-RPC search
            try:
                import xmlrpc.client
                client = xmlrpc.client.ServerProxy("https://pypi.org/pypi")
                hits = client.search({"name": query, "summary": query}, "or")
                results = list({h["name"] for h in hits[:30]})
            except Exception:
                pass
        self.after(0, lambda: self._populate_search(results))

    def _populate_search(self, results: list[str]) -> None:
        self._tree.delete(*self._tree.get_children())
        self._tree_label.config(text=f"SEARCH RESULTS  ({len(results)})")
        for name in sorted(results, key=str.lower):
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
            output.write(f"\n$ pip {' '.join(args)}\n", tag="cmd")

        def _run():
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "pip"] + args,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True
                )
                for line in proc.stdout:
                    if output:
                        self.after(0, lambda l=line: output.write(l))
                proc.wait()
                self.after(0, self._load_installed)
            except Exception as e:
                if output:
                    self.after(0, lambda: output.write(str(e) + "\n", tag="err"))

        threading.Thread(target=_run, daemon=True).start()

    # ── Ask AI ─────────────────────────────────────────────────────────────────

    def _ask_ai(self, name: str, summary: str) -> None:
        ai = self._get_ai_panel() if self._get_ai_panel else None
        if not ai:
            return
        prompt = (f"Show me practical beginner-friendly usage examples for the "
                  f"Python package **{name}**."
                  f"{(' It is described as: ' + summary) if summary else ''} "
                  f"Include 2-3 short, real-world code snippets with comments.")
        ai.send_prefilled(prompt)

    # ── Helpers ────────────────────────────────────────────────────────────────

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
        btn = tk.Label(parent, text=text, bg=bg, fg="white",
                       font=("Segoe UI", 8), cursor="hand2",
                       padx=10, pady=4)
        btn.bind("<Button-1>", lambda _: cmd())
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
