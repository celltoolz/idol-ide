# Project, Interpreter & Session

## Project Wizard

`File → New Project…` launches a guided 4-step wizard:

1. **Project type & name** — choose **Command Line App** (standard script) or **Tkinter GUI App** (visual designer enabled); set project name and location with live path preview
2. **Interpreter & venv** — auto-detects all installed Python versions (filter toggles: `venv`, `system`, `conda` for base installs, and `conda env` for previously created envs — the latter two default on/off respectively, mirroring system/venv); create a `.venv` virtual environment — or, when a **conda base interpreter** is selected, the same checkbox creates a project-local **`.conda/` conda env** instead: a yellow *Conda Environment Selected* note appears with an **Env Python version** picker (defaults to the selected interpreter's version — conda can install any version into a fresh env), and the starter files include an **`environment.yml`** (instead of `requirements.txt`) so the env can be recreated anywhere with `conda env create -f environment.yml`. With the checkbox **unchecked**, the version picker greys out and the project uses the conda base directly. Selecting an **existing conda env** greys out both the checkbox and the picker — the project uses that env as-is (never creating an env inside another env) and activates it in the terminal on open. If the conda installation hasn't accepted its channels' **Terms of Service** yet (fresh Miniconda installs haven't), clicking **Next** on an env-creating configuration shows the ToS with an Accept/Decline dialog — Accept runs `conda tos accept` (persisted by conda itself, so the conda CLI works too); Decline cancels and lets you uncheck the env box or pick another interpreter
3. **Git & starter files** — optional git init; scaffold `main.py`, `requirements.txt`, `.gitignore`; the Git option is disabled (checkbox greyed out with a status note) when git is not found on PATH or not configured
4. **Summary** — review all settings before creating

### GUI App Scaffolding
Tkinter GUI projects auto-generate:
- `<ProjectName>.py` — clean class-based boilerplate; the main form's class is derived from the project folder name (CamelCase, invalid characters stripped). For example, a project named `my-tool` scaffolds `MyTool.py` with `class MyTool(tk.Tk)`.
- `<ProjectName>.form.json` — designer state
- `main.py` — entry point that imports and launches the derived class

### Learning Guides
The wizard includes paginated guides covering:
- **Virtual environments** — what they are, why to use them, choosing an interpreter, creating/activating, best practices
- **Git remotes** — repositories, remotes, creating a GitHub repo, connecting and pushing, authentication

## Project Files

`File → New Project` auto-creates a `<name>.idol-project` file in the project root (where `<name>` matches the project name) storing:

- Open tabs
- Layout (sash widths, active panels)
- Active interpreter
- Breakpoints
- Appearance settings

### The project folder is portable

Everything inside the project folder is stored **relative to the folder itself**, so you can move it, rename it, copy it to another drive, or sync it to another machine and it still opens. Your `.venv`, your open tabs, your breakpoints, and your pinned run entry all follow.

Paths that point *outside* the project stay absolute, because there is nothing meaningful to make them relative to — a system-wide Python interpreter, or a tab you opened from some other folder. Those are checked when the project opens and quietly skipped if they no longer exist, so a project copied to a machine with a different Python layout still opens cleanly with whatever does resolve.

### Projects made before this change

A project file written by an older version of IDOL stores absolute paths. Open one and IDOL repairs it for you: if the folder has moved, every path that pointed inside the old location is re-pointed at the new one, and the file is rewritten in the portable format. It happens on open, without a prompt — the project file you just opened is the authority on where the project lives, so there is nothing to confirm. A note appears in the Output panel telling you where it used to be.

This runs once per project. After that the file is portable and nothing needs repairing again.

**Save / Open / Close Project** — `File → Save Project` saves silently; `File → Open Project` restores the full project state including interpreter selection. The Open Project file dialog opens at the current Explorer root (or the working directory if none is set).

Opening, creating, or closing a project moves the **terminal** as well as the Explorer: a running shell is `cd`'d to the new project root (or back to your home directory on close), and a shell you have not started yet will open there. This is deliberate — a project switch is the one root change that takes the terminal with it. See [Working directory](terminal.md#working-directory).

## Interpreter & Environment

### Interpreter Statusbar
The active Python version is always visible in the status bar (e.g. `Python 3.12.3` or `(.venv) Python 3.12.3`). Click to open a picker and switch interpreters instantly.

### Conda Environments
Conda environments (Miniconda/Anaconda/Miniforge) are discovered automatically — from
`~/.conda/environments.txt` plus the default install locations — and appear in the
picker as `Python 3.x  (conda: base)` / `(conda: myenv)`. The Project Wizard's
interpreter list gains a `conda` filter toggle alongside `venv` and `system`.

Project-local `.conda/` envs are auto-detected the same way `.venv` is: opening a
file inside a project that contains one selects its Python automatically, and no
`conda init` is ever required — IDOL runs conda pythons with a synthesized
activation environment (the env's PATH entries and `CONDA_PREFIX` set on the child
process), so Run, Debug, and package operations work without activating a shell.

### Persistent Per-Project Selection
The chosen interpreter is saved per project root in `~/.idol/settings.json` and restored automatically on next open.

### Venv Activation
Clicking **Activate** in the terminal toolbar:
- Switches the status bar to show `(.venv) Python x.x.x`
- All run/debug/package operations use the venv Python
- Venv is re-activated automatically on next launch

**Deactivate** reverts to the system interpreter.

### One Source of Truth
Run, Run in Terminal, Run Selection, Debug, and the Package Manager all use the selected interpreter.

## Session Persistence

On exit, IDOL auto-saves:
- Open tabs (unsaved changes go to temp files, restored on next launch)
- Layout and explorer root
- Appearance settings
- Breakpoints
- Active interpreter and venv (venv is re-activated in the terminal on next launch)
- Run preferences — run target (Output/Terminal), run/debug action, pinned entry file, and the [run working directory](terminal.md#run-working-directory) mode
- **Designer state** — open forms, active canvas, and the Set as Main selection; if the designer was active, it re-opens automatically on the next launch with the same forms loaded

Session data is written to `~/.idol/session.json`. Named project saves write to `<name>.idol-project` in the project root.

A saved tab whose file has since been deleted or moved is skipped on restore. If that turns out to be *every* tab — renaming a project folder outside IDOL is the usual way — you get the Welcome tab (or a blank one, depending on your **Show on startup** setting) rather than an empty editor.

## Status Bar

The status bar (bottom of the window) shows:
- **Diagnostic badge** — live ✕N ⚠N count; click to open Problems panel
- **Line/column** — cursor position
- **Cursor count** — shown when multiple cursors are active
- **Lexer name** — active syntax highlighter
- **Active interpreter** — Python version or venv name; click to open the interpreter picker
- **Run entry selector** — shows which file the ▶ run button targets (`Active Tab` or a pinned filename); click to change; persists with the project. In the Designer, **Set as Main** (right-click a form row) writes `main.py` and pins it automatically
- **Running filename** — while a script is running or being debugged, the current filename appears as a transient badge in the run-entry slot; it clears automatically when the command finishes (driven by the terminal's OSC 133 shell-integration event) or when you switch to a different editor tab
- **Indent mode** — spaces ↔ tabs cycle on click
- **Git branch** — current branch with live polling

## Zen Mode

**F10** (or **View → Zen Mode**) hides the sidebar, output panel, and status bar for distraction-free editing. A toast notification appears on entry. Toggle with the **ZEN** button in the nav toolbar. Entering Zen mode from the Designer normalises to the editor layout first; exiting Zen restores the Designer automatically.

## Toggle Sidebar

**Ctrl+B** (or **View → Show Sidebar**) hides/shows the entire left panel.
