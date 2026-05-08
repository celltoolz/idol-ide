# Debugger

IDOL includes an integrated Python debugger powered by [debugpy](https://github.com/microsoft/debugpy) over the Debug Adapter Protocol (DAP). No per-project install is needed — IDOL bundles its own debugpy and injects it via `PYTHONPATH` at launch.

## Starting a Debug Session

- **F5** — launch a debug session for the current file
- **Ctrl+F5** — run the current file in the terminal without the debugger

## Breakpoints

- Click the left edge of the gutter (the dim ghost dot zone) to set or clear a breakpoint
- Red dots appear on active lines and **persist across sessions**
- VS Code-style gutter: dim ghost dot on hover, cursor switches to a hand, bright red dot on active breakpoints, subtle separator between dot column and line numbers

## Debug Targets

Choose Output or Terminal from the run menu chevron:

| Mode | Behavior |
|---|---|
| **Output** | debugpy spawns as a subprocess; stdout/stderr stream to the Output panel |
| **Terminal** | debugpy launches inside the integrated terminal PTY; `input()` works natively, ANSI colors render correctly, full interactive session |

## Step Controls

Available in the nav toolbar while a debug session is active:

| Action | Shortcut |
|---|---|
| Continue | F5 |
| Step Over | F10 |
| Step Into | F11 |
| Step Out | Shift+F11 |
| Stop | Shift+F5 |

## DEBUG Panel

Dedicated bottom tab (`Ctrl+Shift+Y`) with two panes:

- **BREAKPOINTS** — lists all set breakpoints by file and line; click any entry to navigate there
- **LOCALS** — shows every local variable in the current frame with name, value, and type, updated each time execution pauses

## Floating Debug Panel

Click **⊡** in the DEBUG tab bar to pop the panel into its own resizable window. Keeps breakpoints and locals visible while working in Output or Terminal.

- **⬅ Dock** returns it to the bottom panel
- **📌** pins it always on top
- Float geometry persists across sessions

## Current-Line Indicator

A yellow arrow in the gutter marks the line where execution is currently paused; the row is highlighted in the editor.

## Unhandled Exceptions

Unhandled exceptions automatically pause execution and navigate the editor to the crashing line.
