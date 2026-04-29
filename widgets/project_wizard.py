"""ProjectWizard — multi-step new project setup wizard."""
from __future__ import annotations

import os
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import Frame, Label, Entry, ttk, filedialog, messagebox
from typing import Callable

from editor.project_manager import ProjectManager, categorize_interpreter
from utils.thread_safe_after import make_thread_safe_after
from widgets.guide_window import GuideWindow
import utils.venv_guide as venv_guide
import utils.git_remote_guide as git_remote_guide
import utils.first_commit_guide as first_commit_guide
from designer.model import FormModel
from designer.codegen import generate as designer_codegen
from designer.persistence import save as designer_save, compute_checksum

_BG      = "#252526"
_HDR_BG  = "#2d2d30"
_ITEM_BG = "#1e1e1e"
_FG      = "#cccccc"
_DIM     = "#858585"
_BTN_BG  = "#0e639c"
_BTN_ACT = "#1177bb"
_ERR     = "#f14c4c"


class ProjectWizard(tk.Toplevel):
    """Step-through wizard for creating a new Python project.

    Steps:
      1. Project details — name and location
      2. Environment    — Python interpreter, create venv
      3. Options        — git init, starter files
      4. Summary        — review and create
    """

    _STEPS = ["Details", "Environment", "Options", "Summary"]

    def __init__(self, parent, on_complete: Callable[[str, str, str, "str | None"], None]) -> None:
        """
        on_complete(project_path, python_exe, python_label, venv_activate_path) is called
        after the project is created. venv_activate_path is the activate script path when
        a venv was created, or None otherwise.
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
        self._type_var    = tk.StringVar(value="cli")   # "cli" | "gui"

        self._pythons: list[tuple[str, str]] = []   # populated by background thread
        self._detecting = True
        self._pm = ProjectManager(after_fn=make_thread_safe_after(self))
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

        self._pm.discover_interpreters(self._on_pythons_ready)
        self._render()

    # ── Python detection (background) ─────────────────────────────────────────

    def _on_pythons_ready(self, results: list[tuple[str, str]]) -> None:
        """Called on the main thread when detection finishes."""
        if not self.winfo_exists():
            return
        self._pythons = results
        self._detecting = False
        if self._step == 1:
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
        if self._step == 1 and self._detecting:
            return
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
              bg=_BG, fg=_DIM, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))

        # ── Project type ──────────────────────────────────────────────────────
        Label(self._content, text="Project Type", bg=_BG, fg=_DIM,
              font=("Segoe UI", 8)).pack(anchor="w")
        type_row = Frame(self._content, bg=_BG)
        type_row.pack(fill="x", pady=(2, 10))

        for value, label, detail in (
            ("cli", "Command Line App",  "Standard script — no visual designer"),
            ("gui", "Tkinter GUI App",   "Visual designer enabled — drag-and-drop UI builder"),
        ):
            rb_frame = Frame(type_row, bg=_BG, cursor="hand2")
            rb_frame.pack(fill="x", pady=1)
            rb = tk.Radiobutton(
                rb_frame, variable=self._type_var, value=value,
                bg=_BG, fg=_FG, selectcolor=_BG, activebackground=_BG,
                font=("Segoe UI", 9), text=label,
            )
            rb.pack(side="left")
            Label(rb_frame, text=detail, bg=_BG, fg=_DIM,
                  font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))

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
            self._loc_var.set(os.path.normpath(d))

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

        combo = ttk.Combobox(self._content, font=("Segoe UI", 9))
        combo.pack(fill="x", ipady=3)

        if self._detecting:
            # ── Loading state: detection still running in background ──────────
            combo.configure(state="disabled")
            combo["values"] = ["Detecting Python interpreters…"]
            combo.current(0)
            self._set_nav_enabled(self._next_btn, False)
            Label(self._content, text="Scanning for interpreters, please wait…",
                  bg=_BG, fg=_DIM, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
        else:
            # ── Ready: populate combo with detected interpreters ──────────────
            combo.configure(state="readonly")

            def _filtered() -> list[tuple[str, str]]:
                show_venv   = self._show_venv_var.get()
                show_system = self._show_system_var.get()
                out = []
                for label, exe in self._pythons:
                    cat = categorize_interpreter(exe)
                    if cat == "venv"   and not show_venv:   continue
                    if cat == "system" and not show_system: continue
                    out.append((label, exe))
                return out

            def _refresh_combo(*_) -> None:
                if not combo.winfo_exists():
                    return
                visible = _filtered()
                if not visible:
                    combo["values"] = ["(no interpreters match filters)"]
                    combo.current(0)
                    self._python_var.set("")
                    return
                combo["values"] = [label for label, _ in visible]
                cur = self._python_var.get()
                try:
                    idx = next(i for i, (_, exe) in enumerate(visible) if exe == cur)
                except StopIteration:
                    idx = 0
                combo.current(idx)
                self._python_var.set(visible[idx][1])

            def _on_select(_=None) -> None:
                visible = _filtered()
                idx = combo.current()
                if 0 <= idx < len(visible):
                    self._python_var.set(visible[idx][1])

            combo.bind("<<ComboboxSelected>>", _on_select)
            self._show_venv_var.trace_add("write",  lambda *_: _refresh_combo())
            self._show_system_var.trace_add("write", lambda *_: _refresh_combo())
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
                    detail=".venv/")

        # Learn more link
        learn = Label(self._content, text="? Learn about virtual environments & choosing a Python interpreter",
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
                    detail="Form1.py / main.py, requirements.txt, .gitignore")

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

        type_label = "Tkinter GUI App" if self._type_var.get() == "gui" else "Command Line App"
        _row("Project type:", type_label)
        _row("Project name:", name)
        _row("Location:", path)
        _row("Python:", os.path.basename(python))
        _row("Virtual environment:", "Yes — .venv/" if self._venv_var.get() else "No")
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
        self._pm.scaffold_project(
            path=path,
            python=python,
            create_venv=self._venv_var.get(),
            create_git=self._git_var.get(),
            on_status=self._set_status,
            on_done=lambda error: self._finish_setup(path, error),
            write_files_fn=self._write_starter_files if self._files_var.get() else None,
        )

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
        if self._status_lbl.winfo_exists():
            self._status_lbl.config(text=text)

    def _finish_setup(self, path: str, error: str | None) -> None:
        if error:
            messagebox.showerror("Setup Error", error, parent=self)
            self.destroy()
            self._on_complete(path, *self._selected_python(), None)
            return
        self._show_success(path)

    def _show_success(self, path: str) -> None:
        """Replace progress screen with a success + first-commit-guide screen."""
        if hasattr(self, "_progress_bar"):
            self._progress_bar.stop()
        for w in self._content.winfo_children():
            w.destroy()

        self._step_lbl.config(text="Project Created!")
        self._prog_lbl.config(text=os.path.normpath(path))

        Label(self._content,
              text=f"✓  {os.path.basename(path)} is ready.",
              bg=_BG, fg="#73c991",
              font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(16, 4))

        Label(self._content,
              text="Your project folder, virtual environment, and git repository\n"
                   "have all been set up. You're ready to start coding.",
              bg=_BG, fg=_DIM, font=("Segoe UI", 9),
              justify="left").pack(anchor="w", pady=(0, 16))

        if self._git_var.get():
            sep = Frame(self._content, bg=_HDR_BG, height=1)
            sep.pack(fill="x", pady=(0, 12))
            Label(self._content,
                  text="Ready to make your first commit?",
                  bg=_BG, fg=_FG, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            Label(self._content,
                  text="Open the Source Control panel, stage your files, write a\n"
                       "commit message, and push to GitHub.",
                  bg=_BG, fg=_DIM, font=("Segoe UI", 9),
                  justify="left").pack(anchor="w", pady=(2, 8))
            guide_btn = Label(self._content, text="? First Commit Guide",
                              bg=_BG, fg="#569cd6",
                              font=("Segoe UI", 8), cursor="hand2")
            guide_btn.pack(anchor="w")
            guide_btn.bind("<Button-1>", lambda _: GuideWindow(
                self, "Your First Commit", first_commit_guide.get_pages()
            ))

        # Swap nav: hide Back, rename Next to "Open Project →"
        self._set_nav_enabled(self._prev_btn, False)
        self._next_btn.config(text="Open Project →")
        # Re-bind next to just close + open
        self._next_btn.unbind("<Button-1>")
        self._next_btn.bind("<Button-1>", lambda _: self._open_project(path))

    def _get_venv_activate_path(self, project_path: str) -> "str | None":
        """Return the activate script path if a venv was created, else None."""
        import platform as _pl
        if not self._venv_var.get():
            return None
        base = os.path.join(project_path, ".venv")
        if _pl.system() == "Windows":
            p = os.path.join(base, "Scripts", "Activate.ps1")
        else:
            p = os.path.join(base, "bin", "activate")
        return p if os.path.isfile(p) else None

    def _open_project(self, path: str) -> None:
        self.destroy()
        self._on_complete(
            path, *self._selected_python(),
            self._get_venv_activate_path(path),
            self._type_var.get(),
        )

    def _selected_python(self) -> tuple[str, str]:
        """Return (exe_path, short_label) for the currently selected interpreter."""
        import sys as _sys, re as _re
        exe = self._python_var.get() or _sys.executable
        for lbl, path in getattr(self, "_pythons", []):
            if path == exe:
                m = _re.match(r"(Python\s+\S+)", lbl)
                return exe, (m.group(1) if m else lbl.split("(")[0].strip())
        return exe, "Python"

    def _write_starter_files(self, project_path: str) -> None:
        is_gui = self._type_var.get() == "gui"
        project_name = os.path.basename(project_path)

        if is_gui:
            # Generate Form1.py + Form1.form.json
            form = FormModel(
                name="Form1",
                title=project_name,
                width=800,
                height=600,
            )
            form_py_path   = Path(project_path) / "Form1.py"
            form_json_path = Path(project_path) / "Form1.form.json"
            code = designer_codegen(form)
            form_py_path.write_text(code, encoding="utf-8")
            checksum = compute_checksum(form_py_path)
            designer_save(form, form_json_path, py_checksum=checksum)
        else:
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
