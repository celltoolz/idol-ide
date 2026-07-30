"""ProjectWizard — multi-step new project setup wizard."""
from __future__ import annotations

import os
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import Frame, Label, Entry, ttk, filedialog, messagebox
from typing import Callable

from editor import conda_manager
from editor.git_manager import probe_identity
from editor.project_manager import ProjectManager, categorize_interpreter
from utils.conda_env import (conda_prefix_for, env_name_for, find_conda_exe,
                             is_conda_base)
from utils import starter_templates
from utils.thread_safe_after import make_thread_safe_after
from widgets.conda_tos_dialog import CondaTosDialog
from widgets.guide_window import GuideWindow
import utils.venv_guide as venv_guide
import utils.git_remote_guide as git_remote_guide
import utils.git_install_guide as git_install_guide
import utils.git_identity_guide as git_identity_guide
import utils.first_commit_guide as first_commit_guide
from designer.model import FormModel
from designer.codegen import generate as designer_codegen
from designer.persistence import save as designer_save, compute_checksum
from utils.ui_font import UI_FONT
from widgets.styled_checkbox import StyledCheckbox

_BG      = "#252526"
_HDR_BG  = "#2d2d30"
_ITEM_BG = "#1e1e1e"
_FG      = "#cccccc"
_DIM     = "#858585"
_BTN_BG  = "#0e639c"
_BTN_ACT = "#1177bb"
_ERR     = "#f14c4c"
_WARN    = "#e2c08d"


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
        self.withdraw()
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

        # Git availability — checked once at startup
        self._git_ok, self._git_warning = self._check_git()

        # Wizard state
        self._name_var    = tk.StringVar()
        self._loc_var     = tk.StringVar(value=str(Path.home()))
        self._python_var  = tk.StringVar()
        self._venv_var    = tk.BooleanVar(value=True)
        self._git_var     = tk.BooleanVar(value=self._git_ok)
        self._files_var   = tk.BooleanVar(value=True)
        self._type_var    = tk.StringVar(value="cli")   # "cli" | "gui"

        self._pythons: list[tuple[str, str]] = []   # populated by background thread
        self._detecting = True
        self._pm = ProjectManager(after_fn=make_thread_safe_after(self))
        self._show_venv_var      = tk.BooleanVar(value=False)  # hide venv by default
        self._show_system_var    = tk.BooleanVar(value=True)
        self._show_conda_var     = tk.BooleanVar(value=True)   # conda base installs
        self._show_conda_env_var = tk.BooleanVar(value=False)  # created conda envs — hidden by default
        self._conda_ver_var   = tk.StringVar()   # python version for a new .conda env
        self._safe_after      = make_thread_safe_after(self)
        self._tos_ok_for: set[str] = set()       # conda exes whose ToS check passed
        self._tos_checking    = False
        self._venv_check_disabled = False        # env checkbox greyed for existing conda envs
        self._venv_saved_value    = True         # user's checkbox value while greyed out
        self._note_updating       = False        # reentrancy guard (trace fires on our own .set)
        self._venv_var.trace_add("write", lambda *_: self._update_conda_note())

        # ── Header ────────────────────────────────────────────────────────────
        self._hdr_frame = Frame(self, bg=_HDR_BG, pady=10)
        self._hdr_frame.pack(fill="x")
        self._step_lbl = Label(self._hdr_frame, text="", bg=_HDR_BG, fg=_FG,
                               font=(UI_FONT, 11, "bold"), padx=14)
        self._step_lbl.pack(anchor="w")
        self._prog_lbl = Label(self._hdr_frame, text="", bg=_HDR_BG, fg=_DIM,
                               font=(UI_FONT, 8), padx=14)
        self._prog_lbl.pack(anchor="w")

        # ── Content ───────────────────────────────────────────────────────────
        self._content = Frame(self, bg=_BG, padx=16, pady=12)
        self._content.pack(fill="both", expand=True)

        # ── Error label ───────────────────────────────────────────────────────
        self._err_lbl = Label(self, text="", bg=_BG, fg=_ERR,
                              font=(UI_FONT, 8), padx=16)
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
        self.deiconify()

    # ── Git availability check ────────────────────────────────────────────────

    @staticmethod
    def _check_git() -> tuple[bool, str]:
        """Return (ok, warning_message) — see `git_manager.probe_identity`.

        Kept as a seam rather than inlining the call: it is what `__init__`
        reads, and what tests stub to keep three git subprocesses out of a
        wizard test that is about something else.
        """
        return probe_identity()

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
                    font=(UI_FONT, 9, "bold"), cursor="hand2", padx=10, pady=3)
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

        # Reset the Next button before the step renders. A step may disable it
        # (step 1 does, while interpreters are still being detected) and the
        # success screen re-points it at _open_project, so both the enabled
        # state and the binding have to come back to the wizard's own defaults
        # here — otherwise arriving at a step leaves Next dead or still wired
        # to the previous screen's action.
        self._set_nav_enabled(self._next_btn, True)
        self._next_btn.unbind("<Button-1>")
        self._next_btn.bind("<Button-1>", lambda _: self._next())

        getattr(self, f"_render_step_{self._step}")()

        is_last = self._step == len(self._STEPS) - 1
        self._next_btn.config(text="Create Project" if is_last else "Next →")
        self._set_nav_enabled(self._prev_btn, self._step > 0)

    def _row(self, label: str) -> Frame:
        """Helper: add a label + return a frame for the input widget."""
        Label(self._content, text=label, bg=_BG, fg=_DIM,
              font=(UI_FONT, 8), anchor="w").pack(fill="x", pady=(8, 2))
        row = Frame(self._content, bg=_BG)
        row.pack(fill="x")
        return row

    def _entry(self, parent, textvariable) -> Entry:
        e = Entry(parent, textvariable=textvariable,
                  bg=_ITEM_BG, fg=_FG, insertbackground=_FG,
                  relief="flat", font=(UI_FONT, 9))
        e.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 4))
        return e

    def _check(self, label: str, variable: tk.BooleanVar, detail: str = "",
               disabled: bool = False) -> StyledCheckbox:
        """Build a styled checkbox row; returns the checkbox (its optional
        detail Label attached as .detail_lbl) so callers can retext or
        grey it out at runtime."""
        cb = StyledCheckbox(self._content, label, variable, bg=_BG, disabled=disabled)
        cb.pack(fill="x", pady=3)
        cb.detail_lbl = None
        if detail:
            cb.detail_lbl = Label(cb, text=f"  {detail}", bg=_BG, fg=_DIM,
                                  font=(UI_FONT, 8))
            cb.detail_lbl.pack(side="left")
        return cb

    def _mini_check(self, parent: Frame, label: str, var: tk.BooleanVar) -> None:
        """Compact inline checkbox for filter rows."""
        StyledCheckbox(
            parent, label, var, bg=_BG, font_size=8, box_font_size=9,
        ).pack(side="left", padx=(0, 10))

    # ── Step 0: Project details ───────────────────────────────────────────────

    def _render_step_0(self) -> None:
        Label(self._content, text="Set up your new Python project.",
              bg=_BG, fg=_DIM, font=(UI_FONT, 9)).pack(anchor="w", pady=(0, 6))

        # ── Project type ──────────────────────────────────────────────────────
        Label(self._content, text="Project Type", bg=_BG, fg=_DIM,
              font=(UI_FONT, 8)).pack(anchor="w")
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
                activeforeground=_FG, font=(UI_FONT, 9), text=label,
                highlightthickness=0, relief="flat",
            )
            rb.pack(side="left")
            Label(rb_frame, text=detail, bg=_BG, fg=_DIM,
                  font=(UI_FONT, 8)).pack(side="left", padx=(4, 0))

        row = self._row("Project Name")
        self._entry(row, self._name_var)

        row2 = self._row("Location")
        self._entry(row2, self._loc_var)
        browse = Label(row2, text="Browse…", bg=_HDR_BG, fg=_FG,
                       font=(UI_FONT, 8), cursor="hand2", padx=6, pady=3)
        browse.pack(side="left")
        browse.bind("<Button-1>", lambda _: self._browse_location())

        # Preview of final path
        self._preview_lbl = Label(self._content, text="", bg=_BG, fg=_DIM,
                                  font=(UI_FONT, 8), anchor="w")
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
              bg=_BG, fg=_DIM, font=(UI_FONT, 9), wraplength=430,
              justify="left").pack(anchor="w")

        self._row("Python Interpreter")

        combo = ttk.Combobox(self._content, font=(UI_FONT, 9))
        combo.pack(fill="x", ipady=3)

        if self._detecting:
            # ── Loading state: detection still running in background ──────────
            combo.configure(state="disabled")
            combo["values"] = ["Detecting Python interpreters…"]
            combo.current(0)
            self._set_nav_enabled(self._next_btn, False)
            Label(self._content, text="Scanning for interpreters, please wait…",
                  bg=_BG, fg=_DIM, font=(UI_FONT, 8)).pack(anchor="w", pady=(2, 0))
        else:
            # ── Ready: populate combo with detected interpreters ──────────────
            combo.configure(state="readonly")

            def _filtered() -> list[tuple[str, str]]:
                show_venv      = self._show_venv_var.get()
                show_system    = self._show_system_var.get()
                show_conda     = self._show_conda_var.get()
                show_conda_env = self._show_conda_env_var.get()
                out = []
                for label, exe in self._pythons:
                    cat = categorize_interpreter(exe)
                    if cat == "venv"   and not show_venv:   continue
                    if cat == "system" and not show_system: continue
                    if cat == "conda":
                        # base installs and created envs filter separately
                        if is_conda_base(exe):
                            if not show_conda:
                                continue
                        elif not show_conda_env:
                            continue
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
                self._update_conda_note()

            def _on_select(_=None) -> None:
                visible = _filtered()
                idx = combo.current()
                if 0 <= idx < len(visible):
                    self._python_var.set(visible[idx][1])
                self._update_conda_note()

            combo.bind("<<ComboboxSelected>>", _on_select)
            self._show_venv_var.trace_add("write",  lambda *_: _refresh_combo())
            self._show_system_var.trace_add("write", lambda *_: _refresh_combo())
            self._show_conda_var.trace_add("write",  lambda *_: _refresh_combo())
            self._show_conda_env_var.trace_add("write", lambda *_: _refresh_combo())
            _refresh_combo()

            # Filter toggles
            filter_row = Frame(self._content, bg=_BG)
            filter_row.pack(fill="x", pady=(4, 0))
            Label(filter_row, text="Show:", bg=_BG, fg=_DIM,
                  font=(UI_FONT, 8)).pack(side="left", padx=(0, 6))
            self._mini_check(filter_row, "venv",   self._show_venv_var)
            self._mini_check(filter_row, "system", self._show_system_var)
            self._mini_check(filter_row, "conda",  self._show_conda_var)
            self._mini_check(filter_row, "conda env", self._show_conda_env_var)

        # Yellow note shown when the selected interpreter is a conda python —
        # the env checkbox below then creates a conda env instead of a venv.
        self._conda_note = Label(
            self._content,
            text="⚠  Conda Environment Selected — a conda env (.conda/) will be "
                 "created instead of a venv",
            bg=_BG, fg=_WARN, font=(UI_FONT, 8), anchor="w", justify="left",
            wraplength=430,
        )

        # Python-version picker for the new conda env (conda can install any
        # version into a fresh env, unlike venv which reuses the interpreter).
        self._conda_ver_row = Frame(self._content, bg=_BG)
        Label(self._conda_ver_row, text="Env Python version:", bg=_BG, fg=_DIM,
              font=(UI_FONT, 8)).pack(side="left", padx=(0, 6))
        self._conda_ver_combo = ttk.Combobox(
            self._conda_ver_row, textvariable=self._conda_ver_var,
            state="readonly", width=8, font=(UI_FONT, 9),
            values=("3.14", "3.13", "3.12", "3.11", "3.10", "3.9"),
        )
        self._conda_ver_combo.pack(side="left")

        spacer = Label(self._content, text="", bg=_BG)
        spacer.pack()
        self._conda_note_anchor = spacer
        self._venv_check_disabled = False   # fresh widget each render
        self._venv_check = self._check(
            "Create virtual environment (recommended)", self._venv_var,
            detail=".venv/")
        self._venv_detail_lbl = self._venv_check.detail_lbl
        self._update_conda_note()

        # Learn more link
        learn = Label(self._content, text="? Learn about virtual environments & choosing a Python interpreter",
                      bg=_BG, fg="#569cd6", font=(UI_FONT, 8), cursor="hand2")
        learn.pack(anchor="w", pady=(10, 0))
        learn.bind("<Button-1>", lambda _: GuideWindow(
            self, "Virtual Environments", venv_guide.get_pages()
        ))

    def _conda_selected(self) -> bool:
        """True when the currently selected wizard interpreter is a conda python."""
        exe = self._python_var.get()
        return bool(exe) and categorize_interpreter(exe) == "conda"

    def _selected_python_mm(self) -> str:
        """major.minor of the selected interpreter, parsed from its label."""
        exe = self._python_var.get()
        for lbl, path in getattr(self, "_pythons", []):
            if path == exe:
                m = re.search(r"Python\s+(\d+\.\d+)", lbl)
                if m:
                    return m.group(1)
        return ""

    def _update_conda_note(self) -> None:
        """Sync the conda note, version row, and env checkbox to the selection.

        Three conda cases:
        - base + create checked   → note (env will be created) + version picker
        - base + create unchecked → note (base used directly), picker greyed
        - existing conda env      → checkbox AND picker greyed; the env is
          used as-is (never create an env from inside another env)
        """
        note = getattr(self, "_conda_note", None)
        if not note or not note.winfo_exists() or self._note_updating:
            return
        self._note_updating = True
        try:
            conda = self._conda_selected()
            existing_env = conda and not is_conda_base(self._python_var.get())

            # Env checkbox: greyed while an existing conda env is selected
            check = getattr(self, "_venv_check", None)
            if check and check.winfo_exists():
                if existing_env and not self._venv_check_disabled:
                    self._venv_saved_value = self._venv_var.get()
                    self._venv_var.set(False)
                    check.set_disabled(True)
                    self._venv_check_disabled = True
                elif not existing_env and self._venv_check_disabled:
                    check.set_disabled(False)
                    self._venv_var.set(self._venv_saved_value)
                    self._venv_check_disabled = False

            if self._venv_detail_lbl and self._venv_detail_lbl.winfo_exists():
                self._venv_detail_lbl.config(
                    text="  .conda/" if conda else "  .venv/")

            if not conda:
                note.pack_forget()
                self._conda_ver_row.pack_forget()
                return

            mm = self._selected_python_mm()
            if existing_env:
                prefix = conda_prefix_for(self._python_var.get())
                name = env_name_for(prefix) if prefix else "env"
                note.config(
                    text=f"⚠  Existing Conda Environment Selected ({name}) — the "
                         "project will use this environment directly; no new "
                         "env is created")
            elif self._venv_var.get():
                note.config(
                    text="⚠  Conda Environment Selected — a conda env (.conda/) "
                         "will be created instead of a venv")
            else:
                note.config(
                    text="⚠  Conda Interpreter Selected — no environment will be "
                         "created; the project will use the conda base "
                         "environment directly")
            note.pack(fill="x", pady=(6, 0), before=self._conda_note_anchor)

            # Version picker: choosable only when a fresh env will be created;
            # otherwise greyed, showing the version the project actually gets.
            creating = self._venv_var.get() and not existing_env
            self._conda_ver_row.pack(fill="x", pady=(4, 0),
                                     before=self._conda_note_anchor)
            if creating:
                self._conda_ver_combo.config(state="readonly")
                if mm:
                    values = list(self._conda_ver_combo["values"])
                    if mm not in values:
                        values.insert(0, mm)
                        self._conda_ver_combo["values"] = values
                    if not self._conda_ver_var.get():
                        self._conda_ver_var.set(mm)
            else:
                if mm:
                    self._conda_ver_var.set(mm)
                self._conda_ver_combo.config(state="disabled")
        finally:
            self._note_updating = False

    # ── Step 2: Options ───────────────────────────────────────────────────────

    def _render_step_2(self) -> None:
        Label(self._content, text="Configure additional project options.",
              bg=_BG, fg=_DIM, font=(UI_FONT, 9)).pack(anchor="w")
        Label(self._content, text="", bg=_BG).pack()  # spacer

        self._check("Initialize git repository", self._git_var,
                    disabled=not self._git_ok)

        if not self._git_ok:
            Label(self._content, text=f"⚠  {self._git_warning}",
                  bg=_BG, fg=_WARN, font=(UI_FONT, 8),
                  anchor="w").pack(fill="x", pady=(2, 0))
            if "not installed" in self._git_warning:
                guide_text, guide_title, guide_pages = (
                    "? How to install Git",
                    "Installing Git",
                    git_install_guide.get_pages(),
                )
            else:
                guide_text, guide_title, guide_pages = (
                    "? How to configure Git identity",
                    "Git Identity",
                    git_identity_guide.get_pages(),
                )
            guide_lnk = Label(self._content, text=guide_text,
                              bg=_BG, fg="#569cd6", font=(UI_FONT, 8), cursor="hand2")
            guide_lnk.pack(anchor="w", pady=(2, 8))
            guide_lnk.bind("<Button-1>", lambda _, t=guide_title, p=guide_pages:
                           GuideWindow(self, t, p))
        else:
            learn_git = Label(self._content, text="? Learn about git repositories",
                              bg=_BG, fg="#569cd6", font=(UI_FONT, 8), cursor="hand2")
            learn_git.pack(anchor="w", pady=(4, 8))
            learn_git.bind("<Button-1>", lambda _: GuideWindow(
                self, "Setting Up a Git Remote", git_remote_guide.get_pages()
            ))

        deps_file = "environment.yml" if self._conda_selected() else "requirements.txt"
        self._check("Create starter files", self._files_var,
                    detail=f"<ProjectName>.py / main.py, {deps_file}, .gitignore")

    # ── Step 3: Summary ───────────────────────────────────────────────────────

    def _render_step_3(self) -> None:
        name     = self._name_var.get().strip()
        loc      = self._loc_var.get().strip()
        path     = os.path.normpath(os.path.join(loc, name))
        python   = self._python_var.get()

        Label(self._content, text="Review your project settings before creating.",
              bg=_BG, fg=_DIM, font=(UI_FONT, 9)).pack(anchor="w", pady=(0, 8))

        def _row(label: str, value: str) -> None:
            f = Frame(self._content, bg=_BG)
            f.pack(fill="x", pady=2)
            Label(f, text=label, bg=_BG, fg=_DIM,
                  font=(UI_FONT, 8), width=20, anchor="w").pack(side="left")
            Label(f, text=value, bg=_BG, fg=_FG,
                  font=(UI_FONT, 9), anchor="w").pack(side="left")

        type_label = "Tkinter GUI App" if self._type_var.get() == "gui" else "Command Line App"
        _row("Project type:", type_label)
        _row("Project name:", name)
        _row("Location:", path)
        _row("Python:", os.path.basename(python))
        if self._venv_var.get():
            if self._conda_selected():
                ver = self._conda_ver_var.get()
                env_val = f"Yes — .conda/ (conda, python={ver})" if ver else "Yes — .conda/ (conda)"
            else:
                env_val = "Yes — .venv/"
        elif self._conda_selected():
            if is_conda_base(python):
                env_val = "No — using conda base directly"
            else:
                prefix = conda_prefix_for(python)
                name = env_name_for(prefix) if prefix else "env"
                env_val = f"No — using existing conda env ({name})"
        else:
            env_val = "No"
        _row("Virtual environment:", env_val)
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
        if self._step == 1 and self._venv_var.get() and self._conda_selected():
            # Creating a conda env downloads packages from Anaconda's
            # channels, which require accepted Terms of Service. Gate the
            # Next click on that check so the failure isn't discovered
            # mid-creation.
            if not self._conda_tos_ready():
                return False
        return True

    # ── Conda Terms of Service gate ───────────────────────────────────────────

    def _conda_tos_ready(self) -> bool:
        """True when the selected conda install's ToS is known-accepted.

        Otherwise starts an async check (the interrupted Next click resumes
        automatically once the check/dialog resolves) and returns False.
        """
        conda_exe = find_conda_exe(conda_prefix_for(self._python_var.get()))
        if not conda_exe:
            return True   # scaffold_project surfaces its own error for this
        if conda_exe in self._tos_ok_for:
            return True
        if not self._tos_checking:
            self._tos_checking = True
            self._error("Checking conda Terms of Service…")
            # Scoped to the channels `conda create` will search — the same list
            # that goes into environment.yml. `conda tos` reports on every
            # channel the installation knows about, including ones this env
            # creation cannot reach.
            conda_manager.fetch_tos_pending(
                conda_exe, self._safe_after,
                lambda pending: self._on_tos_status(conda_exe, pending),
                channels=self._project_channels())
        return False

    def _on_tos_status(self, conda_exe: str, pending: dict[str, str]) -> None:
        self._tos_checking = False
        if not self.winfo_exists():
            return
        if not pending:
            self._tos_ok_for.add(conda_exe)
            self._error("")
            self._next()   # resume the Next click that started the check
            return
        CondaTosDialog(
            self, pending,
            on_accept=lambda: self._on_tos_accept(conda_exe),
            on_decline=self._on_tos_decline,
        )

    def _on_tos_accept(self, conda_exe: str) -> None:
        self._error("Accepting conda Terms of Service…")
        conda_manager.accept_tos(
            conda_exe, self._safe_after,
            lambda ok, msg: self._on_tos_accepted(conda_exe, ok, msg))

    def _on_tos_accepted(self, conda_exe: str, ok: bool, msg: str) -> None:
        if not self.winfo_exists():
            return
        if ok:
            self._tos_ok_for.add(conda_exe)
            self._error("")
            self._next()
        else:
            self._error(f"Could not accept the Terms of Service: {msg}")

    def _on_tos_decline(self) -> None:
        if self.winfo_exists():
            self._error(
                "Conda env creation needs the Terms of Service accepted — "
                "uncheck the environment box or pick a different interpreter.")

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
            conda_py_version=(self._conda_ver_var.get() or None
                              if self._conda_selected() else None),
            # The same list `_write_starter_files` puts in environment.yml, so
            # the env is solved against the channels the project declares
            # rather than against whatever ~/.condarc says at create time.
            conda_channels=(self._project_channels()
                            if self._conda_selected() else None),
        )

    def _project_channels(self) -> list[str]:
        """Channels for a new conda project — seeded from the user's ~/.condarc.

        One accessor so `conda create` and the generated environment.yml cannot
        disagree; ~/.condarc is the seed and the project's file becomes the
        store from here on (see `utils/conda_env.project_channels`).
        """
        from utils.conda_env import configured_channels
        return configured_channels()

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
              bg=_BG, fg=_DIM, font=(UI_FONT, 9)).pack(pady=(20, 10))

        self._progress_bar = ttk.Progressbar(
            self._content, mode="indeterminate", length=300
        )
        self._progress_bar.pack(pady=8)
        self._progress_bar.start(12)

        self._status_lbl = Label(self._content, text="Initializing…",
                                 bg=_BG, fg=_DIM, font=(UI_FONT, 8))
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
              font=(UI_FONT, 11, "bold")).pack(anchor="w", pady=(16, 4))

        Label(self._content,
              text="Your project folder, virtual environment, and git repository\n"
                   "have all been set up. You're ready to start coding.",
              bg=_BG, fg=_DIM, font=(UI_FONT, 9),
              justify="left").pack(anchor="w", pady=(0, 16))

        if self._git_var.get():
            sep = Frame(self._content, bg=_HDR_BG, height=1)
            sep.pack(fill="x", pady=(0, 12))
            Label(self._content,
                  text="Ready to make your first commit?",
                  bg=_BG, fg=_FG, font=(UI_FONT, 9, "bold")).pack(anchor="w")
            Label(self._content,
                  text="Open the Source Control panel, stage your files, write a\n"
                       "commit message, and push to GitHub.",
                  bg=_BG, fg=_DIM, font=(UI_FONT, 9),
                  justify="left").pack(anchor="w", pady=(2, 8))
            guide_btn = Label(self._content, text="? First Commit Guide",
                              bg=_BG, fg="#569cd6",
                              font=(UI_FONT, 8), cursor="hand2")
            guide_btn.pack(anchor="w")
            guide_btn.bind("<Button-1>", lambda _: GuideWindow(
                self, "Your First Commit", first_commit_guide.get_pages()
            ))

        # Swap nav: rename Next to "Open Project →" and re-bind it to close +
        # open. Both buttons were greyed out by `_show_progress`, and they are
        # live again here — the finish screen is not a dead end, Back returns
        # to the Summary step — so re-enable them or they keep the disabled
        # look and lose the hand cursor every other button has.
        self._set_nav_enabled(self._prev_btn, True)
        self._set_nav_enabled(self._next_btn, True)
        self._next_btn.config(text="Open Project →")
        self._next_btn.unbind("<Button-1>")
        self._next_btn.bind("<Button-1>", lambda _: self._open_project(path))

    def _get_venv_activate_path(self, project_path: str) -> "str | None":
        """Return the activate script path if a venv was created, else None."""
        import platform as _pl
        if not self._venv_var.get() or self._conda_selected():
            return None
        base = os.path.join(project_path, ".venv")
        if _pl.system() == "Windows":
            p = os.path.join(base, "Scripts", "Activate.ps1")
        else:
            p = os.path.join(base, "bin", "activate")
        return p if os.path.isfile(p) else None

    def _get_conda_prefix(self, project_path: str) -> "str | None":
        """The conda env prefix the project should activate, else None.

        Either the freshly created .conda/ env, or — when the user picked an
        existing (non-base) conda env as the interpreter — that env itself.
        """
        if self._venv_var.get():
            prefix = os.path.join(project_path, ".conda")
            if os.path.isdir(os.path.join(prefix, "conda-meta")):
                return prefix
            return None
        exe = self._python_var.get()
        if exe and self._conda_selected() and not is_conda_base(exe):
            return conda_prefix_for(exe)
        return None

    def _open_project(self, path: str) -> None:
        self.destroy()
        self._on_complete(
            path, *self._selected_python(),
            self._get_venv_activate_path(path),
            self._type_var.get(),
            self._get_conda_prefix(path),
        )

    def _selected_python(self) -> tuple[str, str]:
        """Return (exe_path, short_label) for the currently selected interpreter."""
        import sys as _sys, re as _re
        exe = self._python_var.get() or _sys.executable
        for lbl, path in getattr(self, "_pythons", []):
            if path == exe:
                m = _re.match(r"(Python\s+\S+)", lbl)
                short = m.group(1) if m else lbl.split("(")[0].strip()
                mconda = _re.search(r"\(conda: ([^)]+)\)", lbl)
                if mconda:
                    short = f"(conda: {mconda.group(1)}) {short}"
                return exe, short
        return exe, "Python"

    @staticmethod
    def _form_name_from_project(project_name: str) -> str:
        """Convert a folder name to a valid Python class identifier."""
        import re as _re
        parts = _re.split(r"[\s\-_]+", project_name)
        name = "".join(p.capitalize() for p in parts if p)
        name = _re.sub(r"[^A-Za-z0-9_]", "", name)
        name = name.lstrip("0123456789")
        return name or "Form"

    def _write_starter_files(self, project_path: str) -> None:
        is_gui = self._type_var.get() == "gui"
        project_name = os.path.basename(project_path)

        if is_gui:
            form_name = self._form_name_from_project(project_name)
            form = FormModel(
                name=form_name,
                title=project_name,
                width=800,
                height=600,
            )
            form_py_path   = Path(project_path) / f"{form_name}.py"
            form_json_path = Path(project_path) / f"{form_name}.form.json"
            code = designer_codegen(form)
            form_py_path.write_text(code, encoding="utf-8")
            checksum = compute_checksum(form_py_path)
            designer_save(form, form_json_path, py_checksum=checksum)

            # main.py — entry point that imports and runs the form. Shared with
            # app.py's Set as Main Form, which rewrites this same file; the two
            # used to carry separate literals and disagreed on blank lines.
            main_py = os.path.join(project_path, "main.py")
            with open(main_py, "w", encoding="utf-8") as f:
                f.write(starter_templates.idol_main_py(form_name))
        else:
            main_py = os.path.join(project_path, "main.py")
            with open(main_py, "w", encoding="utf-8") as f:
                f.write('def main():\n    print("Hello, World!")\n\n\nif __name__ == "__main__":\n    main()\n')

        if self._conda_selected():
            # Conda projects declare dependencies in environment.yml (the
            # conda-native equivalent of requirements.txt): recreate the env
            # anywhere with `conda env create -f environment.yml`. This file is
            # the *store* for the project's channels from here on — ~/.condarc
            # only seeds it, and the Package Manager edits it (see
            # utils/conda_env.write_project_channels).
            from utils.conda_env import render_channels_block
            ver = self._conda_ver_var.get()
            env_yml = os.path.join(project_path, "environment.yml")
            with open(env_yml, "w", encoding="utf-8") as f:
                f.write(f"name: {project_name}\n")
                f.writelines(render_channels_block(self._project_channels()))
                f.write("dependencies:\n"
                        + (f"  - python={ver}\n" if ver else "  - python\n"))
        else:
            req = os.path.join(project_path, "requirements.txt")
            with open(req, "w", encoding="utf-8") as f:
                f.write("# Project dependencies\n")

        gitignore = os.path.join(project_path, ".gitignore")
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write(
                "# Virtual environment\n"
                "venv/\n.venv/\n.conda/\n"
                "bin/\ninclude/\nlib/\nlib64\npyvenv.cfg\nshare/\n\n"
                "# Python\n__pycache__/\n*.py[cod]\n*.pyo\n\n"
                "# Build\ndist/\nbuild/\n*.egg-info/\n\n"
                "# OS\n.DS_Store\nThumbs.db\ndesktop.ini\n\n"
                "# IDE\n.vscode/\n.idea/\n"
            )
