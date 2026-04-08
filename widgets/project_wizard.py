"""ProjectWizard — multi-step new project setup wizard."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import Frame, Label, Entry, ttk, filedialog, messagebox
from typing import Callable

from widgets.guide_window import GuideWindow
import utils.venv_guide as venv_guide
import utils.git_remote_guide as git_remote_guide

_BG      = "#252526"
_HDR_BG  = "#2d2d30"
_ITEM_BG = "#1e1e1e"
_FG      = "#cccccc"
_DIM     = "#858585"
_BTN_BG  = "#0e639c"
_BTN_ACT = "#1177bb"
_ERR     = "#f14c4c"


def _detect_pythons() -> list[tuple[str, str]]:
    """Return a list of (label, executable_path) for available Python interpreters."""
    seen:    set[str]              = set()
    results: list[tuple[str, str]] = []

    def _add(path: str) -> None:
        resolved = shutil.which(path) or (path if os.path.isfile(path) else None)
        if not resolved:
            return
        norm = os.path.normcase(os.path.realpath(resolved))
        if norm in seen:
            return
        seen.add(norm)
        try:
            out = subprocess.check_output(
                [resolved, "--version"], stderr=subprocess.STDOUT, timeout=3
            ).decode().strip()
            version = out.split()[-1]
        except Exception:
            return
        results.append((f"Python {version}  ({resolved})", resolved))

    # 1. Explicit absolute paths — generic names first so python3 wins the
    #    realpath dedup over python3.14 (both symlink to the same binary).
    for prefix in ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin",
                   os.path.expanduser("~/.pyenv/shims")):
        for name in ("python3", "python", "python3.14", "python3.13",
                     "python3.12", "python3.11", "python3.10", "python3.9"):
            _add(os.path.join(prefix, name))

    # Homebrew cellar — catches installs not yet symlinked into /usr/local/bin
    for pattern in ("/usr/local/Cellar/python*/*/bin/python3",
                    "/opt/homebrew/Cellar/python*/*/bin/python3"):
        for p in sorted(glob.glob(pattern), reverse=True):
            _add(p)

    # Windows py launcher
    py = shutil.which("py")
    if py:
        try:
            out = subprocess.check_output([py, "-0"], stderr=subprocess.STDOUT,
                                          timeout=3).decode()
            for line in out.splitlines():
                m = re.search(r"-(\d+\.\d+).*?(\S+python\S*)", line, re.IGNORECASE)
                if m:
                    _add(m.group(2))
        except Exception:
            pass

    # 2. Name-based PATH lookups — catch anything not in the known prefixes
    #    (e.g. pyenv, conda, custom installs). Venv entries will be deduped away.
    for name in ("python3", "python", "python3.14", "python3.13", "python3.12",
                 "python3.11", "python3.10", "python3.9"):
        _add(name)

    # 3. sys.executable last — deduped if it's a venv pointing at a known install.
    _add(sys.executable)

    return results if results else [("Python (system default)", sys.executable)]


def _categorize(exe: str) -> str:
    """Return 'venv', 'system', or 'user' for a given interpreter path."""
    norm = exe.replace("\\", "/").lower()
    if "/venv/" in norm or "/.venv/" in norm or norm.endswith("/venv") or norm.endswith("/.venv"):
        return "venv"
    system_prefixes = ("/usr/bin/", "/usr/local/bin/", "c:/windows/")
    if any(norm.startswith(p) for p in system_prefixes):
        return "system"
    return "user"


class ProjectWizard(tk.Toplevel):
    """Step-through wizard for creating a new Python project.

    Steps:
      1. Project details — name and location
      2. Environment    — Python interpreter, create venv
      3. Options        — git init, starter files
      4. Summary        — review and create
    """

    _STEPS = ["Details", "Environment", "Options", "Summary"]

    def __init__(self, parent, on_complete: Callable[[str], None]) -> None:
        """
        on_complete(project_path) is called after the project is created
        so the app can open it in the explorer.
        """
        super().__init__(parent)
        self.title("New Project")
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        parent.update_idletasks()
        w, h = 480, 400
        px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{px}+{py}")

        self._on_complete = on_complete
        self._step        = 0

        # Wizard state
        self._name_var    = tk.StringVar()
        self._loc_var     = tk.StringVar(value=str(Path.home()))
        self._python_var  = tk.StringVar()
        self._venv_var    = tk.BooleanVar(value=True)
        self._git_var     = tk.BooleanVar(value=True)
        self._files_var   = tk.BooleanVar(value=True)

        self._pythons: list[tuple[str, str]] = []   # all detected, populated lazily
        self._show_venv_var   = tk.BooleanVar(value=False)  # hide venv by default
        self._show_system_var = tk.BooleanVar(value=True)

        # ── Header ────────────────────────────────────────────────────────────
        self._hdr_frame = Frame(self, bg=_HDR_BG, pady=10)
        self._hdr_frame.pack(fill="x")
        self._step_lbl = Label(self._hdr_frame, text="", bg=_HDR_BG, fg=_FG,
                               font=("Segoe UI", 11, "bold"), padx=14)
        self._step_lbl.pack(anchor="w")
        self._prog_lbl = Label(self._hdr_frame, text="", bg=_HDR_BG, fg=_DIM,
                               font=("Segoe UI", 8), padx=14)
        self._prog_lbl.pack(anchor="w")

        # ── Content ───────────────────────────────────────────────────────────
        self._content = Frame(self, bg=_BG, padx=16, pady=12)
        self._content.pack(fill="both", expand=True)

        # ── Error label ───────────────────────────────────────────────────────
        self._err_lbl = Label(self, text="", bg=_BG, fg=_ERR,
                              font=("Segoe UI", 8), padx=16)
        self._err_lbl.pack(fill="x")

        # ── Navigation ────────────────────────────────────────────────────────
        nav = Frame(self, bg=_HDR_BG, pady=8)
        nav.pack(fill="x", side="bottom")

        self._prev_btn = self._nav_btn(nav, "← Back",   self._prev)
        self._prev_btn.pack(side="left", padx=8)

        self._next_btn = self._nav_btn(nav, "Next →",   self._next)
        self._next_btn.pack(side="left")

        self._nav_btn(nav, "Cancel", self.destroy).pack(side="right", padx=8)

        self._render()

    # ── Navigation helpers ────────────────────────────────────────────────────

    def _nav_btn(self, parent, text: str, command: Callable) -> Label:
        lbl = Label(parent, text=text, bg=_BTN_BG, fg="white",
                    font=("Segoe UI", 9, "bold"), cursor="hand2", padx=10, pady=3)
        lbl.bind("<Button-1>", lambda _: command())
        lbl.bind("<Enter>", lambda _: lbl.config(bg=_BTN_ACT) if lbl["cursor"] == "hand2" else None)
        lbl.bind("<Leave>", lambda _: lbl.config(bg=_BTN_BG))
        return lbl

    def _set_nav_enabled(self, lbl: Label, enabled: bool) -> None:
        lbl.config(bg=_BTN_BG if enabled else "#3c3c3c",
                   cursor="hand2" if enabled else "")

    def _prev(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._err_lbl.config(text="")
            self._render()

    def _next(self) -> None:
        if not self._validate():
            return
        if self._step < len(self._STEPS) - 1:
            self._step += 1
            self._err_lbl.config(text="")
            self._render()
        else:
            self._create_project()

    def _error(self, msg: str) -> None:
        self._err_lbl.config(text=msg)

    # ── Step rendering ────────────────────────────────────────────────────────

    def _render(self) -> None:
        for w in self._content.winfo_children():
            w.destroy()

        name = self._STEPS[self._step]
        self._step_lbl.config(text=name)
        self._prog_lbl.config(text=f"Step {self._step + 1} of {len(self._STEPS)}")

        getattr(self, f"_render_step_{self._step}")()

        is_last = self._step == len(self._STEPS) - 1
        self._next_btn.config(text="Create Project" if is_last else "Next →")
        self._set_nav_enabled(self._prev_btn, self._step > 0)

    def _row(self, label: str) -> Frame:
        """Helper: add a label + return a frame for the input widget."""
        Label(self._content, text=label, bg=_BG, fg=_DIM,
              font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(8, 2))
        row = Frame(self._content, bg=_BG)
        row.pack(fill="x")
        return row

    def _entry(self, parent, textvariable) -> Entry:
        e = Entry(parent, textvariable=textvariable,
                  bg=_ITEM_BG, fg=_FG, insertbackground=_FG,
                  relief="flat", font=("Segoe UI", 9))
        e.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 4))
        return e

    def _check(self, label: str, variable: tk.BooleanVar, detail: str = "") -> None:
        row = Frame(self._content, bg=_BG, cursor="hand2")
        row.pack(fill="x", pady=3)

        box = Label(row, bg=_BG, font=("Segoe UI", 11), cursor="hand2")
        box.pack(side="left", padx=(0, 4))

        def _refresh(*_):
            box.config(text="☑" if variable.get() else "☐",
                       fg="#569cd6" if variable.get() else _DIM)

        def _toggle(_=None):
            variable.set(not variable.get())
            _refresh()

        _refresh()
        box.bind("<Button-1>", _toggle)
        row.bind("<Button-1>", _toggle)

        lbl = Label(row, text=label, bg=_BG, fg=_FG, font=("Segoe UI", 9), cursor="hand2")
        lbl.pack(side="left")
        lbl.bind("<Button-1>", _toggle)

        if detail:
            Label(row, text=f"  {detail}", bg=_BG, fg=_DIM,
                  font=("Segoe UI", 8)).pack(side="left")

    def _mini_check(self, parent: Frame, label: str, var: tk.BooleanVar) -> None:
        """Compact inline checkbox for filter rows."""
        f = Frame(parent, bg=_BG, cursor="hand2")
        f.pack(side="left", padx=(0, 10))
        box = Label(f, bg=_BG, font=("Segoe UI", 9), cursor="hand2")
        box.pack(side="left", padx=(0, 2))
        lbl = Label(f, text=label, bg=_BG, fg=_FG, font=("Segoe UI", 8), cursor="hand2")
        lbl.pack(side="left")

        def _refresh(*_):
            box.config(text="☑" if var.get() else "☐",
                       fg="#569cd6" if var.get() else _DIM)
        def _toggle(_=None):
            var.set(not var.get())
            _refresh()

        _refresh()
        for w in (f, box, lbl):
            w.bind("<Button-1>", _toggle)

    # ── Step 0: Project details ───────────────────────────────────────────────

    def _render_step_0(self) -> None:
        Label(self._content, text="Set up your new Python project.",
              bg=_BG, fg=_DIM, font=("Segoe UI", 9)).pack(anchor="w")

        row = self._row("Project Name")
        self._entry(row, self._name_var)

        row2 = self._row("Location")
        self._entry(row2, self._loc_var)
        browse = Label(row2, text="Browse…", bg=_HDR_BG, fg=_FG,
                       font=("Segoe UI", 8), cursor="hand2", padx=6, pady=3)
        browse.pack(side="left")
        browse.bind("<Button-1>", lambda _: self._browse_location())

        # Preview of final path
        self._preview_lbl = Label(self._content, text="", bg=_BG, fg=_DIM,
                                  font=("Segoe UI", 8), anchor="w")
        self._preview_lbl.pack(fill="x", pady=(6, 0))
        self._update_preview()
        self._name_var.trace_add("write", lambda *_: self._update_preview())
        self._loc_var.trace_add("write",  lambda *_: self._update_preview())

    def _browse_location(self) -> None:
        d = filedialog.askdirectory(initialdir=self._loc_var.get(), parent=self)
        if d:
            self._loc_var.set(d)

    def _update_preview(self) -> None:
        name = self._name_var.get().strip()
        loc  = self._loc_var.get().strip()
        if name and loc:
            self._preview_lbl.config(text=f"→  {os.path.normpath(os.path.join(loc, name))}")
        else:
            self._preview_lbl.config(text="")

    # ── Step 1: Environment ───────────────────────────────────────────────────

    def _render_step_1(self) -> None:
        Label(self._content,
              text="Choose a Python interpreter and configure your virtual environment.",
              bg=_BG, fg=_DIM, font=("Segoe UI", 9), wraplength=430,
              justify="left").pack(anchor="w")

        self._row("Python Interpreter")
        if not self._pythons:
            self._pythons = _detect_pythons()
            if self._pythons:
                self._python_var.set(self._pythons[0][1])

        combo = ttk.Combobox(self._content, state="readonly", font=("Segoe UI", 9))
        combo.pack(fill="x", ipady=3)

        def _filtered() -> list[tuple[str, str]]:
            show_venv   = self._show_venv_var.get()
            show_system = self._show_system_var.get()
            out = []
            for label, exe in self._pythons:
                cat = _categorize(exe)
                if cat == "venv"   and not show_venv:   continue
                if cat == "system" and not show_system: continue
                out.append((label, exe))
            return out or self._pythons  # never leave list empty

        def _refresh_combo(*_) -> None:
            if not combo.winfo_exists():
                return
            visible = _filtered()
            combo["values"] = [label for label, _ in visible]
            cur = self._python_var.get()
            try:
                idx = next(i for i, (_, exe) in enumerate(visible) if exe == cur)
            except StopIteration:
                idx = 0
            if visible:
                combo.current(idx)
                self._python_var.set(visible[idx][1])

        def _on_select(_=None) -> None:
            visible = _filtered()
            idx = combo.current()
            if 0 <= idx < len(visible):
                self._python_var.set(visible[idx][1])

        combo.bind("<<ComboboxSelected>>", _on_select)
        self._show_venv_var.trace_add("write",   lambda *_: _refresh_combo())
        self._show_system_var.trace_add("write",  lambda *_: _refresh_combo())
        _refresh_combo()

        # Filter toggles
        filter_row = Frame(self._content, bg=_BG)
        filter_row.pack(fill="x", pady=(4, 0))
        Label(filter_row, text="Show:", bg=_BG, fg=_DIM,
              font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
        self._mini_check(filter_row, "venv",   self._show_venv_var)
        self._mini_check(filter_row, "system", self._show_system_var)

        Label(self._content, text="", bg=_BG).pack()  # spacer
        self._check("Create virtual environment (recommended)", self._venv_var,
                    detail="venv/")

        # Learn more link
        learn = Label(self._content, text="? Learn about virtual environments",
                      bg=_BG, fg="#569cd6", font=("Segoe UI", 8), cursor="hand2")
        learn.pack(anchor="w", pady=(10, 0))
        learn.bind("<Button-1>", lambda _: GuideWindow(
            self, "Virtual Environments", venv_guide.get_pages()
        ))

    # ── Step 2: Options ───────────────────────────────────────────────────────

    def _render_step_2(self) -> None:
        Label(self._content, text="Configure additional project options.",
              bg=_BG, fg=_DIM, font=("Segoe UI", 9)).pack(anchor="w")
        Label(self._content, text="", bg=_BG).pack()  # spacer

        self._check("Initialize git repository", self._git_var)
        learn_git = Label(self._content, text="? Learn about git repositories",
                          bg=_BG, fg="#569cd6", font=("Segoe UI", 8), cursor="hand2")
        learn_git.pack(anchor="w", pady=(4, 8))
        learn_git.bind("<Button-1>", lambda _: GuideWindow(
            self, "Setting Up a Git Remote", git_remote_guide.get_pages()
        ))

        self._check("Create starter files", self._files_var,
                    detail="main.py, requirements.txt, .gitignore")

    # ── Step 3: Summary ───────────────────────────────────────────────────────

    def _render_step_3(self) -> None:
        name     = self._name_var.get().strip()
        loc      = self._loc_var.get().strip()
        path     = os.path.normpath(os.path.join(loc, name))
        python   = self._python_var.get()

        Label(self._content, text="Review your project settings before creating.",
              bg=_BG, fg=_DIM, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        def _row(label: str, value: str) -> None:
            f = Frame(self._content, bg=_BG)
            f.pack(fill="x", pady=2)
            Label(f, text=label, bg=_BG, fg=_DIM,
                  font=("Segoe UI", 8), width=20, anchor="w").pack(side="left")
            Label(f, text=value, bg=_BG, fg=_FG,
                  font=("Segoe UI", 9), anchor="w").pack(side="left")

        _row("Project name:", name)
        _row("Location:", path)
        _row("Python:", os.path.basename(python))
        _row("Virtual environment:", "Yes — venv/" if self._venv_var.get() else "No")
        _row("Git repository:", "Yes" if self._git_var.get() else "No")
        _row("Starter files:", "Yes" if self._files_var.get() else "No")

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate(self) -> bool:
        if self._step == 0:
            name = self._name_var.get().strip()
            loc  = self._loc_var.get().strip()
            if not name:
                self._error("Project name cannot be empty.")
                return False
            if not re.match(r'^[\w\-. ]+$', name):
                self._error("Project name contains invalid characters.")
                return False
            if not os.path.isdir(loc):
                self._error("Location directory does not exist.")
                return False
            dest = os.path.join(loc, name)
            if os.path.exists(dest):
                self._error(f"'{name}' already exists in that location.")
                return False
        return True

    # ── Project creation ──────────────────────────────────────────────────────

    def _create_project(self) -> None:
        name   = self._name_var.get().strip()
        loc    = self._loc_var.get().strip()
        path   = os.path.join(loc, name)
        python = self._python_var.get() or sys.executable

        try:
            os.makedirs(path, exist_ok=False)
        except Exception as e:
            self._error(str(e))
            return

        self._show_progress()
        threading.Thread(target=self._run_setup,
                         args=(path, python), daemon=True).start()

    def _show_progress(self) -> None:
        """Replace wizard content with an indeterminate progress screen."""
        # Disable nav buttons
        self._set_nav_enabled(self._prev_btn, False)
        self._set_nav_enabled(self._next_btn, False)

        for w in self._content.winfo_children():
            w.destroy()

        self._step_lbl.config(text="Creating Project…")
        self._prog_lbl.config(text="Please wait")

        Label(self._content, text="Setting up your project…",
              bg=_BG, fg=_DIM, font=("Segoe UI", 9)).pack(pady=(20, 10))

        self._progress_bar = ttk.Progressbar(
            self._content, mode="indeterminate", length=300
        )
        self._progress_bar.pack(pady=8)
        self._progress_bar.start(12)

        self._status_lbl = Label(self._content, text="Initializing…",
                                 bg=_BG, fg=_DIM, font=("Segoe UI", 8))
        self._status_lbl.pack()

    def _set_status(self, text: str) -> None:
        """Thread-safe status label update."""
        self.after(0, lambda: self._status_lbl.config(text=text)
                   if self._status_lbl.winfo_exists() else None)

    def _run_setup(self, path: str, python: str) -> None:
        """Run in background thread — all UI updates go through after()."""
        error: str | None = None
        try:
            if self._venv_var.get():
                self._set_status("Creating virtual environment…")
                subprocess.run([python, "-m", "venv", os.path.join(path, "venv")],
                               check=True, timeout=120)

            if self._files_var.get():
                self._set_status("Writing starter files…")
                self._write_starter_files(path)

            if self._git_var.get():
                self._set_status("Initializing git repository…")
                subprocess.run(["git", "init", path], check=True, timeout=10)

        except subprocess.CalledProcessError as e:
            error = f"An error occurred during project setup:\n{e}"
        except Exception as e:
            error = str(e)

        self.after(0, lambda: self._finish_setup(path, error))

    def _finish_setup(self, path: str, error: str | None) -> None:
        if error:
            messagebox.showerror("Setup Error", error, parent=self)
        self.destroy()
        self._on_complete(path)

    def _write_starter_files(self, project_path: str) -> None:
        main_py = os.path.join(project_path, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write('def main():\n    print("Hello, World!")\n\n\nif __name__ == "__main__":\n    main()\n')

        req = os.path.join(project_path, "requirements.txt")
        with open(req, "w", encoding="utf-8") as f:
            f.write("# Project dependencies\n")

        gitignore = os.path.join(project_path, ".gitignore")
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write(
                "# Virtual environment\n"
                "venv/\n.venv/\n"
                "bin/\ninclude/\nlib/\nlib64\npyvenv.cfg\nshare/\n\n"
                "# Python\n__pycache__/\n*.py[cod]\n*.pyo\n\n"
                "# Build\ndist/\nbuild/\n*.egg-info/\n\n"
                "# OS\n.DS_Store\nThumbs.db\ndesktop.ini\n\n"
                "# IDE\n.vscode/\n.idea/\n"
            )
