# IDOL — Claude Code Project Brief

## What IDOL Is

IDOL (Integrated Development and Objective Learning) is a Python/Tkinter desktop IDE
built for Python development. It is a full-featured IDE: multi-tab editing, syntax
highlighting, LSP integration (pylsp), Git tooling, integrated PTY terminal, AI chat
panel (Ollama/qwen2.5-coder:7b), pip package manager, learning mode, command palette,
and session persistence. It runs on Windows, macOS, and Linux.

GitHub: `celltoolz/notepad-ide`
Entry point: `python main.py` (optional: `python main.py <filepath>`)

---

## Entry Points

### `main.py` — bootstrap only (~70 lines)
Three responsibilities, nothing else:
1. Parse optional CLI file argument
2. Show splash screen
3. Instantiate `IDOL` and call `mainloop()`

### `app.py` — the application
The `IDOL` class (`tk.Tk` subclass). Owns the complete object graph: notebook, all
panels, menus, keybindings, session save/restore, file open/save, LSP, Git, terminal,
AI chat, package manager, command palette. This is the wiring layer — it connects
backends to widgets, but does not implement feature logic itself.

---

## Architecture: The Two-Layer Pattern

Every major feature is split into a **backend layer** and a **UI layer**.
This pattern is the single most important architectural rule in IDOL.

```
Backend (engine)              UI (widget)
─────────────────────         ────────────────────────
editor/git_manager.py    →    widgets/source_control.py
editor/lsp_client.py     →    (consumed via app.py)
editor/lsp_manager.py    →    (consumed via app.py)
utils/ollama_client.py   →    widgets/ai_chat_panel.py
```

### The strict import rule

```
main.py      → can import app.py only
app.py       → can import anything
widgets/     → can import from editor/, utils/ — NEVER the reverse
editor/      → can import from utils/ — NO widget imports, NO subprocess in utils/
utils/       → NO widget imports, NO subprocess calls, NO editor/ imports
```

Violations of this rule are bugs, not style issues.

---

## Package Responsibilities

### `editor/` — stateful backends
Modules that own subprocess lifecycle, protocol state, or threading.
These modules have no Tkinter widget imports.

| File | Role |
|---|---|
| `lsp_client.py` | Transport layer — spawns pylsp subprocess, speaks JSON-RPC 2.0 over stdin/stdout, routes responses to main thread via `after_fn`. Knows nothing about LSP semantics. |
| `lsp_manager.py` | Protocol layer — does the `initialize` handshake, sends `textDocument/did*` notifications, handles hover/definition/diagnostics, converts paths ↔ URIs. Built on top of `LspClient`. |
| `git_manager.py` | Git engine — all subprocess git calls on daemon threads, fires results back via `after_fn`. Owns diff/hunk parsing, file status parsing, `STATUS_COLORS`/`GUTTER_COLORS`. No UI. |
| `bracket_matcher.py` | Bracket matching logic |
| `completion.py` | Completion logic |
| `key_handler.py` | Keybinding dispatch logic |
| `multi_cursor.py` | Multi-cursor state and operations |

### `utils/` — stateless logic, content, config
Pure functions, dataclasses, config parsing, content generators. No subprocess calls,
no widget imports, no stateful objects.

| File | Role |
|---|---|
| `ollama_client.py` | HTTP client for local Ollama API |
| `schemeparser.py` | Parses `.toml` colorscheme files |
| `settings.py` | Settings load/save |
| `session.py` | Session persistence (open files, state) |
| `learning_registry.py` | Registry of learning content |
| `git_diagnostics.py` | Pure classification logic for Git health panel — regex pattern sets, `FileInfo`/`Issue`/`HealthCheck` dataclasses, stateless analysis functions. Called by `source_control.py`. |
| `venv_guide.py` | Content module — exports `get_pages()` returning `GuidePage` dataclasses for the venv guide. No UI code. |
| `git_remote_guide.py` | Content module — same pattern as `venv_guide.py` for git remote guide. |

### `widgets/` — UI only
Every file is a Tkinter widget or panel. Imports from `editor/` and `utils/` for data,
never runs subprocesses or owns protocol logic itself.

Key widgets: `ai_chat_panel.py`, `bottom_panel.py`, `breadcrumb_bar.py`, `codeview.py`,
`command_palette.py`, `explorer.py`, `find_replace.py`, `guide_window.py`,
`learning_panel.py`, `linenums.py`, `minimap.py`, `notebook.py`, `outline.py`,
`output.py`, `package_manager.py`, `project_wizard.py`, `references.py`, `sidebar.py`,
`source_control.py`, `statusbar.py`, `sticky_scroll.py`, `terminal.py`

#### `guide_window.py` — reusable paginated guide UI
`GuideWindow` is a content-agnostic `Toplevel` — you hand it any list of `GuidePage`
objects and it renders them. The content lives in `utils/venv_guide.py` and
`utils/git_remote_guide.py`. This is the Guide Pattern: content in `utils/`,
rendering in `widgets/`.

### `menus/`
`menubar.py` — constructs the application menubar. Kept separate from `app.py` for
size management.

### `colorschemes/`
`.toml` files parsed by `utils/schemeparser.py`. Add new themes here.

### `data/`
Static data files. Currently contains `idol_package_categories.json` (PyPI classifier-based package groupings used by the Package Manager).
Any future static data files belong here, not inside package directories.

---

## Key Technical Decisions (Don't Revisit Without Discussion)

- **Tkinter, not Qt.** This is intentional. Don't suggest Qt/PyQt/PySide alternatives.
- **Synchronous, not async.** Threading is handled via daemon threads + `after_fn` callbacks to the main thread. Don't introduce `asyncio` or `async/await`.
- **Ollama for local AI, not cloud.** The AI chat panel targets `qwen2.5-coder:7b` running locally. Don't add cloud API calls to the AI panel without explicit discussion.
- **pylsp for LSP.** Server selection is in `lsp_manager.py`. Don't change the LSP server without discussion.
- **PTY terminal.** Real PTY via `pty` module (Unix) or `winpty` (Windows). Don't replace with `subprocess.PIPE`.

---

## Naming Conventions

- Classes: `PascalCase` — `GitManager`, `LspClient`, `AiChatPanel`
- Files: `snake_case` — matches the class they primarily contain
- The app class is `IDOL` (all caps) — it's a proper noun/acronym, not a class name
- Backend/engine modules do NOT have `_ui` or `_widget` in their name
- Widget modules do NOT have `_manager`, `_client`, or `_engine` in their name
- If a new feature needs both layers: `editor/thing_manager.py` + `widgets/thing_panel.py`

---

## Threading Model

- All git and LSP subprocess calls happen on **daemon threads**
- Results are delivered to the main thread via `after_fn` (passed in at construction)
- This is always `self.after` from a `tk.Tk` or `tk.Frame` context
- **Never call Tkinter widget methods from a background thread**
- The pattern is: do work on thread → `after_fn(0, callback, result)`

---

## Current Feature State

Implemented and stable:
- Multi-tab editing with session persistence
- Pygments syntax highlighting
- pylsp LSP integration (hover, diagnostics, definition, completion)
- **Problems panel** — PROBLEMS tab in bottom bar with colored severity dots; click to jump to line/column
- **Diagnostic statusbar badge** — live ✕N ⚠N count; click to open Problems panel
- Sticky scroll, minimap
- **Breadcrumb bar** — path crumbs, symbol crumbs, sibling picker, locals drill-down, marquee scroll footer
- Multi-cursor editing
- Split editor with scroll sync
- Git integration: staging, unstaging, commit, push, diff view, health panel, inline file explanations, fix wizard
- **Commit History panel** — last 50 commits, file diff on click, filter bar, load more
- Integrated PTY terminal with venv detection (activate/deactivate/switch toolbar)
- **Run Line / Run Selection** — right-click to execute in output panel
- AI chat panel (Ollama, session history, token counter, remote host config)
- Learning Mode (F1) — hover any IDE element for three-section explanations with AI Ask button
- Pip package manager with topic grouping, PyPI search, and AI examples
- Command palette (Ctrl+Shift+P) with fuzzy search and `@` symbol search
- Project setup wizard (4-step: name/location, interpreter/venv, git/starter files, summary)
- **Integrated Python debugger** — debugpy over DAP; breakpoints, step controls, LOCALS + BREAKPOINTS panel, smart venv detection, one-click install
- Nav toolbar (back/forward, split, minimap, sidebar, zen, AI, packages, learning toggles)
- Zen mode (F10), Toggle Sidebar (Ctrl+B)
- Colorscheme system (`.toml` files)

## Planned / In Progress

- **Command Palette `!` shell mode** — visual shift + pre-populated commands + context-aware suggestions

---

## What NOT To Do

- Don't add widget imports to `editor/` or `utils/` modules
- Don't run subprocess calls from `widgets/` directly
- Don't put data files inside package directories — use `data/`
- Don't introduce async/await
- Don't suggest rewriting in a different GUI framework
- Don't create a third file for a feature that already has a backend and a widget — extend the existing pair
- Don't add top-level files to root unless they are genuine entry points or project config
