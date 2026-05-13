# Terminal & Output

## Integrated Terminal

Full VT100 PTY shell with a **canvas-driven renderer** for pixel-perfect output and smooth reflow on resize.

- Accurate ANSI color rendering via [pyte](https://github.com/selectel/pyte)
- Direct keyboard input
- Scrollback history stored as **logical lines** — re-wrapped automatically when the window or sash is resized, so historical output stays readable at any width
- **Viewport-anchored reflow** — your scroll position survives resizes; if you were at the bottom, you stay at the bottom
- **Mouse wheel scrolling** — passes SGR scroll sequences to TUI apps (vim, htop) when mouse mode is active, otherwise scrolls the history buffer
- **Text selection** — click and drag to select; Copy via right-click or `Ctrl+Shift+C`; Paste via right-click or `Ctrl+Shift+V`

Open with `Ctrl+`` ` or the **>_** button in the nav toolbar.

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
| `OSC 133;D` | Command-done event with exit code — clears the running-filename badge in the status bar |
| `OSC 7` | Current working directory — drives venv autodetection |
| `OSC 7776` | Active `$VIRTUAL_ENV` path (IDOL-private) — drives the venv toolbar |

Supported shells: PowerShell (Windows), PowerShell 7, bash, zsh, sh. Other programs (Python REPL, custom CLIs) skip hook injection and run unmodified.

On Windows the hook writes CWD/VENV to a temp file (`%TEMP%\idol_state.txt`) instead of stdout to avoid any PTY cursor interference; IDOL polls the file every 500ms.

## Virtual Environment Detection

The terminal toolbar shows the active venv state for the **active session**:

| State | Toolbar shows |
|---|---|
| No venv found | nothing |
| `.venv` / `venv` / `env` / `.env` exists in CWD, not active | **▶ Activate venv** button |
| Venv in CWD is active | **⏹ Deactivate** + venv name |
| A *different* venv is active | **⇄ Switch venv** + venv name |

Clicking **Activate** switches the status bar and all run/debug/package operations to the venv Python automatically. Each session tracks its own venv state independently.

## Run / Output Panel

Open with `Ctrl+Shift+U` or the nav toolbar **▶** button.

- Stdout and stderr with color coding
- **Inline stdin bar** — when a script calls `input()`, a `>` input field appears at the bottom of the Output panel; type your response and hit Enter; the prompt appears immediately (unbuffered), your input echoes in light blue, and the script continues — no terminal switch needed for simple scripts

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
