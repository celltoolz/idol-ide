# Terminal & Output

## Integrated Terminal

Full VT100 PTY shell with a **canvas-driven renderer** for pixel-perfect output and smooth reflow on resize.

- Accurate ANSI color rendering via [pyte](https://github.com/selectel/pyte)
- Direct keyboard input
- Scrollback history stored as **logical lines** — re-wrapped automatically when the window or sash is resized, so historical output stays readable at any width
- **Viewport-anchored reflow** — your scroll position survives resizes; if you were at the bottom, you stay at the bottom
- **Mouse forwarding** — when a TUI app enables mouse mode, all click, release, drag, and right-click events are forwarded as SGR mouse sequences (`\x1b[<btn;col;rowM/m`); mouse wheel scroll sequences are also forwarded; when mouse mode is off, the wheel scrolls the history buffer instead
- **Alternate screen buffer** — full DEC 1049 support; full-screen TUI apps (vim, nano, htop, less, mc) enter and exit cleanly without corrupting the scrollback history
- **Extended TUI key forwarding** — Ctrl+Arrow (word navigation / tmux pane switching), Shift+Arrow (selection in text editors), Alt+Arrow (file manager navigation), and Insert are forwarded as proper escape sequences when the terminal has focus
- **Auto-scroll pin for repainting TUI apps** — apps that repaint by cursor-up + redraw (Rich Live tables, Textual, etc.) are viewport-pinned to the top of the redrawn block so table borders stay flush; output that doesn't cursor-up remains bottom-pinned (keeping PSReadLine prompts anchored)
- **Text selection** — click and drag to select; Copy via right-click or `Ctrl+Shift+C`; Paste via right-click or `Ctrl+Shift+V`
- **Focus-aware block cursor** — a solid block while the terminal has the keyboard, a hollow outline when it doesn't, the way real terminal emulators behave. With the editor, the split, and the terminal all on screen at once, this is what tells you where your next keystroke actually lands

Open with `Ctrl+`` ` or the **>_** button in the nav toolbar.

### Working directory

A new shell session starts in the current Explorer root. Once it is running, only two things
move it:

- **Opening, creating, or closing a project** — the shell follows to the new project root, or
  back to your home directory on close
- **Explorer right-click → Open in Terminal** — the explicit "take me there" action

Everything else leaves a running shell alone. Re-rooting the Explorer without switching
projects (Set as Root Directory, a breadcrumb folder click) only changes where the *next*
session starts, and opening a file does not move the Explorer root at all.

## Sessions Sidebar

The terminal hosts **multiple shell sessions at once** in a VS Code-style sidebar on the right.

- **Click a row** to switch sessions — the previous session keeps running in the background, its PTY untouched
- **Hover a row → ✕** to close that session; the last remaining session cannot be closed
- **Active indicator** — blue accent bar on the active row; running sessions show a small **▶** marker
- **≡ button** in the terminal tab bar toggles the sidebar with a smooth slide animation; drag the ghost sash between the terminal and the sidebar to resize it

### Creating new sessions

The sidebar footer has a split-button:

- **+** — creates a new session using the default shell (first detected on this system)
- **▾** — opens a picker listing every shell IDOL detected on this machine

Detected shells:

| Platform | Available |
|---|---|
| Windows | PowerShell, PowerShell 7 (pwsh), cmd, Git Bash, WSL, Python REPL |
| macOS / Linux | every entry in `/etc/shells` (bash, zsh, fish, …) plus Python REPL |

Each session gets a coloured icon dot matching its shell type.

## Run-Session Targeting

When you run or debug a file, IDOL sends the command to a designated **run session** so your interactive shells stay clean.

- **Right-click any session row → Set as Run Session** to choose which one receives runs
- The current run session is marked with a **▶** indicator
- New sessions auto-become the run session if none was set
- If the run session is in the background when you hit ▶, IDOL switches to it first

## Shell Integration

IDOL injects a small prompt hook on startup that emits standard escape sequences each time the shell draws its prompt. This drives several IDE features without polluting the terminal output:

| Sequence | Purpose |
|---|---|
| `OSC 133` | Startup gate — IDOL suppresses rendering until the first OSC 133 prompt event fires, then shows a clean screen; a 3-second fallback fires if the hook never arrives |
| `OSC 133;D` | Command-done event with exit code — clears the running-filename badge in the status bar |
| `OSC 7` | Current working directory — drives venv autodetection |
| `OSC 7776` | Active `$VIRTUAL_ENV` path (IDOL-private) — drives the venv toolbar |
| `OSC 7778` | Active `$CONDA_PREFIX` path (IDOL-private) — drives conda env tracking |

Supported shells: PowerShell (Windows), PowerShell 7, bash, zsh, sh. Other programs (Python REPL, custom CLIs) skip hook injection and run unmodified.

The **Python REPL** session type uses IDOL's **active interpreter** — its entry is labeled with that interpreter's version (e.g. `Python 3.14` when a conda env is active), and switching interpreters updates the next new REPL session (running ones keep theirs). Conda-interpreter REPLs launch with the synthesized activation environment, so imports resolve conda DLLs without `conda activate`.

On Windows the hook writes CWD/VENV/CONDA to a temp file (`%TEMP%\idol_state.txt`) instead of stdout to avoid any PTY cursor interference; IDOL polls the file every 500ms.

## Environment Detection (venv & conda)

The terminal toolbar shows the active environment state for the **active session**:

| State | Toolbar shows |
|---|---|
| No env found | nothing |
| `.venv` / `venv` / `env` / `.env` exists in CWD, not active | **▶ Activate venv** button |
| `.conda` env exists in CWD, not active | **▶ Activate conda env** button |
| Env in CWD is active | **⏹ Deactivate** + env name |
| A *different* env is active | **⇄ Switch env** + env name |
| An env is active but CWD has none | **⏹ Deactivate** + env name (an active env is always deactivatable) |

Closing a project (`File → Close Project`, or opening/creating another) automatically deactivates any env the terminal has active — venv or conda — before the terminal returns to your home directory, so a project-local env never outlives its project.

Venv names win when both a venv and a `.conda` env exist in the same directory. Clicking **Activate** switches the status bar and all run/debug/package operations to that env's Python automatically. Each session tracks its own env state independently.

**Conda activation** never requires `conda init`: IDOL sources the hook script explicitly — `conda-hook.ps1` for PowerShell, `etc/profile.d/conda.sh` for bash/zsh (MSYS2-converted paths for Git Bash) — then runs `conda activate <prefix>`. Deactivation sends `conda deactivate`. A conda env activated when the terminal opens is also re-activated on session restore (project-local `.conda` envs only, same containment rule as venvs).

**Run in Terminal with a conda interpreter**: typed commands run under the *shell's* environment, so if the shell hasn't activated the env yet, IDOL types the activation command first, then the run command.

**Platform notes:**
- **Git Bash on Windows** — launched with `--login -i` flags so `/etc/profile` runs and populates the MSYS2 PATH (making `sort`, `tr`, `cygpath`, etc. available); `MSYSTEM=MINGW64` and related environment variables are injected automatically
- **Venv activation on Windows (Git Bash)** — `Scripts/activate` is bypassed (it calls `cygpath`, which requires Cygwin); instead `VIRTUAL_ENV` and `PATH` are set directly in MSYS2-compatible form
- **Activation on Windows (PowerShell)** — `Set-ExecutionPolicy -Scope Process` is prepended so the unsigned `Activate.ps1` / `conda-hook.ps1` runs without changing any system policy
- **Double-activation guard** — a flag prevents both the terminal's auto-activate path and the app-level pending env path from both firing on the same session startup
- **Clean start** — child shells never inherit IDOL's own `VIRTUAL_ENV` or `CONDA_*` variables, so any env the shell reports was explicitly activated

## Run / Output Panel

Open with `Ctrl+Shift+U` or the nav toolbar **▶** button.

- Stdout and stderr with color coding
- **Inline stdin bar** — when a script calls `input()`, a `>` input field appears at the bottom of the Output panel; type your response and hit Enter; the prompt appears immediately (unbuffered), your input echoes in light blue, and the script continues — no terminal switch needed for simple scripts

## Run Working Directory

By default your program runs from your **project root**, so relative paths (e.g. `open("data/x.txt")` or `sqlite3.connect("app.db")`) resolve against your project rather than IDOL's install directory. Change it in the run dropdown (▾ next to ▶):

- **Dir: Project Root** (default) — the current Explorer root. With no project open it falls back to the running file's own directory (never IDOL's directory).
- **Dir: Script Directory** — always the running file's own folder.

The choice applies to every way you start your program — Run and Debug, in both the Output panel and the terminal — so relative paths resolve the same no matter which button you press. It is also available from the command palette and persists with the project. The Output panel echoes the directory as `$ cd <dir>` above each run. (Run Line / Run Selection always use the project root, since they execute a temporary file.)

When the active interpreter is a **conda environment**, Output-panel runs get a synthesized activation environment automatically — the env's PATH entries (including `Library\bin` on Windows, where conda keeps its DLLs) plus `CONDA_PREFIX`/`CONDA_DEFAULT_ENV` — so scripts import conda packages correctly without `conda activate` and without conda being on your PATH.

## Run Line & Run Selection

Right-click any line or highlighted block and choose **Run Line** or **Run Selection**. Selection execution auto-dedents indented blocks before running.

## Dynamic Tab Bar Controls

The right side of the bottom panel tab bar shows context-sensitive controls for the active tab:

| Tab | Controls |
|---|---|
| OUTPUT | Clear |
| TERMINAL | ⟳ Restart, ✕ Clear, ≡ Sessions toggle, venv toolbar |
| DEBUG | Float button |

**⟳ Restart** kills and respawns the active session's shell, keeping the session row in place.

## Runtime Error Indicators

When a script crashes:
1. IDOL jumps to the offending line
2. Applies an amber highlight to that line
3. Draws a right-pointing amber triangle (▶) in the gutter
4. Flashes the PROBLEMS tab

All indicators clear on the next keystroke.
