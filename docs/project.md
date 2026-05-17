# Project, Interpreter & Session

## Project Wizard

`File → New Project…` launches a guided 4-step wizard:

1. **Project type & name** — choose **Command Line App** (standard script) or **Tkinter GUI App** (visual designer enabled); set project name and location with live path preview
2. **Interpreter & venv** — auto-detects all installed Python versions; create a `.venv` virtual environment
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

**Save / Open / Close Project** — `File → Save Project` saves silently; `File → Open Project` restores the full project state including interpreter selection. The Open Project file dialog opens at the current Explorer root (or the working directory if none is set).

## Interpreter & Environment

### Interpreter Statusbar
The active Python version is always visible in the status bar (e.g. `Python 3.12.3` or `(.venv) Python 3.12.3`). Click to open a picker and switch interpreters instantly.

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

Session data is written to `~/.idol/session.json`. Named project saves write to `<name>.idol-project` in the project root.

## Status Bar

The status bar (bottom of the window) shows:
- **Diagnostic badge** — live ✕N ⚠N count; click to open Problems panel
- **Line/column** — cursor position
- **Cursor count** — shown when multiple cursors are active
- **Lexer name** — active syntax highlighter
- **Active interpreter** — Python version or venv name; click to open the interpreter picker
- **Run entry selector** — shows which file the ▶ run button targets (`Active Tab` or a pinned filename); click to change; persists with the project
- **Running filename** — while a script is running or being debugged, the current filename appears as a transient badge in the run-entry slot; it clears automatically when the command finishes (driven by the terminal's OSC 133 shell-integration event) or when you switch to a different editor tab
- **Indent mode** — spaces ↔ tabs cycle on click
- **Git branch** — current branch with live polling

## Zen Mode

**F10** (or **View → Zen Mode**) hides the sidebar, output panel, and status bar for distraction-free editing. A toast notification appears on entry. Toggle with the **ZEN** button in the nav toolbar. Entering Zen mode from the Designer normalises to the editor layout first; exiting Zen restores the Designer automatically.

## Toggle Sidebar

**Ctrl+B** (or **View → Show Sidebar**) hides/shows the entire left panel.
