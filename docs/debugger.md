# Debugger

IDOL includes an integrated Python debugger powered by [debugpy](https://github.com/microsoft/debugpy) over the Debug Adapter Protocol (DAP). No per-project install is needed — IDOL bundles its own debugpy and injects it via `PYTHONPATH` at launch.

## Starting a Debug Session

- **F5** — launch a debug session for the current file
- **Ctrl+F5** — run the current file in the terminal without the debugger

## Breakpoints

- Click the left edge of the gutter (the dim ghost dot zone) to set or clear a breakpoint
- Red dots appear on active lines and **persist across sessions**
- VS Code-style gutter: dim ghost dot on hover, cursor switches to a hand, bright red dot on active breakpoints, subtle separator between dot column and line numbers
- **Auto-shift** — when you insert or delete lines above a breakpoint, the breakpoint moves with the code automatically
- **Undo/redo aware** — breakpoints shift back correctly when you undo or redo line insertions
- **Both panes** — the gutter works identically in the split editor. A breakpoint set in the split pane appears in the BREAKPOINTS list, saves with the session, and is picked up by a running debug session, exactly as one set in the main pane

## Debug Targets

Choose Output or Terminal from the run menu chevron:

| Mode | Behavior |
|---|---|
| **Output** | debugpy spawns as a subprocess; stdout/stderr stream to the Output panel |
| **Terminal** | debugpy launches inside the integrated terminal PTY; `input()` works natively, ANSI colors render correctly, full interactive session |

Both modes start in the same directory as a normal run — see [Run Working Directory](terminal.md#run-working-directory) — so relative paths in your code resolve identically whether you press Run or Debug. The Output panel echoes the directory as `$ cd <dir>` above each debug session.

Conda interpreters debug the same way they run: the debuggee gets a synthesized conda activation environment (env PATH + `CONDA_PREFIX`), with IDOL's bundled debugpy layered on top via `PYTHONPATH` — no `conda activate` or per-env debugpy install needed.

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
