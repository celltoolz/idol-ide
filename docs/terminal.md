# Terminal & Output

## Integrated Terminal

Full VT100 PTY shell (PowerShell on Windows, bash/zsh on Unix) with:

- Accurate ANSI color rendering via [pyte](https://github.com/selectel/pyte)
- Direct keyboard input
- Scrollback history
- **Mouse wheel scrolling** — passes SGR scroll sequences to TUI apps (vim, htop) when mouse mode is active, otherwise scrolls the history buffer
- **Text selection** — click and drag to select; Copy via right-click or `Ctrl+Shift+C`; Paste via right-click or `Ctrl+Shift+V`

Open with `Ctrl+`` ` or the **>_** button in the nav toolbar.

## Virtual Environment Detection

The terminal toolbar shows the active venv state:

| State | Toolbar shows |
|---|---|
| No venv found | nothing |
| `.venv` / `venv` exists, not active | **Activate** button |
| Venv active | venv name + **Deactivate** button |
| Different venv active | **Switch** button |

Clicking **Activate** switches the status bar and all run/debug/package operations to the venv Python automatically.

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
| TERMINAL | Shell selector, Restart, Clear, venv toolbar |
| DEBUG | Float button |

## Runtime Error Indicators

When a script crashes:
1. IDOL jumps to the offending line
2. Applies an amber highlight to that line
3. Draws a right-pointing amber triangle (▶) in the gutter
4. Flashes the PROBLEMS tab

All indicators clear on the next keystroke.
