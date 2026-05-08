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
| `pip_manager.py` | Subprocess backend for pip install/uninstall/list — runs on daemon threads, delivers results via `after_fn`. Tracks active interpreter via `set_python(exe)`. |
| `project_manager.py` | Interpreter discovery and project scaffolding — finds installed Python versions, creates venvs, scaffolds starter files. Daemon-threaded. |
| `script_runner.py` | Runs Python scripts as subprocesses — pushes `(line, tag)` tuples to a thread-safe queue; sends `None` sentinel on completion. Accepts `python_path` to use the active interpreter. |
| `debug_manager.py` | DAP client for debugpy — launches debugpy subprocess, connects via TCP, drives the debug session. Accepts `debugpy_site` to inject IDOL's bundled debugpy via `PYTHONPATH` (no per-project install needed). All callbacks dispatched via `after_fn`. |
| `pyflakes_linter.py` | Local diagnostics engine — runs ruff then compile() on a debounced background thread; fires `on_diagnostics(uri, diags)` via `after_fn`. No LSP dependency. |

### `utils/` — stateless logic, content, config
Pure functions, dataclasses, config parsing, content generators. No subprocess calls,
no widget imports, no stateful objects.

| File | Role |
|---|---|
| `ollama_client.py` | HTTP client for local Ollama API |
| `schemeparser.py` | Parses `.toml` colorscheme files |
| `settings.py` | Settings load/save |
| `session.py` | Session persistence — saves/restores open tabs, layout, appearance, breakpoints, active interpreter, and active venv (re-activates in terminal on next launch). Auto-session writes to `~/.idol/session.json`; named saves write to `.idol-project` in the project root. |
| `learning_registry.py` | Registry of learning content |
| `git_diagnostics.py` | Pure classification logic for Git health panel — regex pattern sets, `FileInfo`/`Issue`/`HealthCheck` dataclasses, stateless analysis functions. Called by `source_control.py`. |
| `venv_guide.py` | Content module — exports `get_pages()` returning `GuidePage` dataclasses for the venv guide. No UI code. |
| `git_remote_guide.py` | Content module — same pattern as `venv_guide.py` for git remote guide. |
| `guide_types.py` | Shared `GuidePage` dataclass used by all guide content modules. |
| `custom_cursor.py` | Cross-platform learning-mode cursor (arrow + question mark). Uses system cursor on Windows/macOS; generates XBM bitmap on Linux where system cursor is unreliable. |
| `thread_safe_after.py` | `make_thread_safe_after(widget)` — returns an `after_fn` safe to call from daemon threads. Use this instead of `self.after` when constructing any manager that runs on background threads. |
| `ruff_rules.py` | Beginner-friendly descriptions for ruff diagnostic codes — maps rule IDs to plain-English explanations used in the Problems panel. |
| `debug_input_guide.py` | Content module — `get_pages()` returning `GuidePage` dataclasses for the input()/debugger guide. Same pattern as `venv_guide.py`. |
| `git_install_guide.py` | Content module — 3-page guide for installing git on Windows, macOS, and Linux. Opened from the Git Health panel when git is not found on PATH. |
| `git_identity_guide.py` | Content module — 4-page guide for setting git user.name/email, creating a GitHub account, and authenticating via GitHub CLI (`gh auth login`). |
| `first_commit_guide.py` | Content module — 4-page guide for making a first commit and pushing to GitHub. Opened from the Project Wizard success screen when git is enabled. |

### `widgets/` — UI only
Every file is a Tkinter widget or panel. Imports from `editor/` and `utils/` for data,
never runs subprocesses or owns protocol logic itself.

Key widgets: `ai_chat_panel.py`, `bottom_panel.py`, `breadcrumb_bar.py`, `codeview.py`,
`command_palette.py`, `completion_popup.py`, `debug_panel.py`, `designer_palette.py`,
`explorer.py`, `find_replace.py`, `guide_window.py`, `learning_manager.py`,
`learning_panel.py`, `linenums.py`, `minimap.py`, `notebook.py`, `outline.py`,
`output.py`, `package_manager.py`, `problems_panel.py`, `project_wizard.py`, `references.py`,
`sidebar.py`, `source_control.py`, `statusbar.py`, `sticky_scroll.py`, `terminal.py`

#### `guide_window.py` — reusable paginated guide UI

`GuideWindow(parent, title, pages)` is a content-agnostic paginated `Toplevel`.
Hand it a list of `GuidePage` objects; it handles navigation, layout, and styling.

**How to build a GuideWindow:**

```python
from widgets.guide_window import GuideWindow, GuidePage

GuideWindow(self, "My Feature", [
    GuidePage(
        title="What is it?",
        sections=[
            ("THE IDEA",   "Plain explanation of the concept.", "#569cd6"),
            ("HOW TO USE", "Step-by-step or bullet list.",      "#73c991"),
            ("GOTCHAS",    "Warnings or edge cases.",           "#e2c08d"),
        ],
        plain_english=(
            "One plain-English analogy paragraph shown in a highlighted box "
            "at the bottom of the page."
        ),
    ),
    GuidePage(title="Reference", sections=[...], plain_english="..."),
])
```

**Conventions:**
- `sections` is a list of `(heading, body, accent_color)` tuples. Use `#569cd6` (blue) for
  concept headings, `#73c991` (green) for how-to steps, `#e2c08d` (amber) for warnings,
  `#cccccc` (grey) for neutral reference text.
- `plain_english` is a short analogy or summary — written for a beginner, no jargon.
  It appears in a dimmed highlight box at the bottom of each page.
- Target 2–4 pages per guide. One concept per page.

**Where to put the content:**
- **Complex / reusable guides** (venv, git, pip): extract content into a `utils/*_guide.py`
  module that exports `get_pages() -> list[GuidePage]`. This keeps `widgets/` files lean.
- **Simple / widget-specific guides** (e.g. the Events guide in `designer_properties.py`):
  define the `GuidePage` list inline. Only do this when the content is tightly coupled to
  one widget and won't be reused.

### `designer/` — GUI Designer (Tkinter GUI projects only)

The visual form designer. Only active when the current project type is "Tkinter GUI App".
Follows the same two-layer pattern: pure logic modules (`model`, `registry`, `codegen`,
`persistence`) have no Tkinter widget imports; UI modules (`canvas`, `toolbar`,
`widgets/designer_palette.py`, `widgets/designer_properties.py`) have no subprocess calls.

| File | Role |
|---|---|
| `model.py` | `WidgetDescriptor`, `VariableBinding`, `MenuItemDescriptor`, and `FormModel` dataclasses — the canonical source of truth for every form. `FormModel` tracks name, title, size, `border_style`, `maximize_box`, `bg`, widget list, and `menu_items` list. `VariableBinding` holds the tkinter variable (StringVar/IntVar/DoubleVar/BooleanVar) bound to a widget. `MenuItemDescriptor` holds caption, name, indent (0 = top-level cascade, 1+ = item/submenu), enabled, visible, shortcut, `kind` ("command"/"checkbutton"/"radiobutton"), `variable` (tk variable name), `value` (radiobutton value string), and `command_handler` (optional handler name for check/radio items). |
| `registry.py` | `REGISTRY` dict — one entry per widget type: tk class, default size, default props, available events (Button/Checkbutton/Radiobutton/Scale/Spinbox list `"command"` first; Combobox lists `"comboselected"` first), `color_props` list, `is_container` flag (Frame/LabelFrame), `variable_prop`/`variable_types` for variable binding, and a mini-preview drawing function |
| `codegen.py` | `FormModel → Python` — generates a class-based source file. Two `IDOL:BEGIN/END` marker pairs in `__init__` delimit user-owned zones (pre-build and post-build) that survive regeneration. `IDOL:IMPORTS:BEGIN/END` markers preserve user-added imports. Preserves event bodies, helper methods, and user `__init__` code. Handles `validatecommand`/`invalidcommand` as `(self.register(self.method), args...)`. Skips empty/default props. `_menu_lines()` emits `tk.Menu` hierarchy including `add_checkbutton`/`add_radiobutton` for check/radio items; `_menu_command_methods()` harvests leaf item names and check/radio command handlers so `_collect_methods()` stubs them automatically; `_menu_variable_decls()` emits `BooleanVar`/`StringVar` declarations for menu variables; `_menu_bind_lines()` emits `self.bind("<shortcut>", handler)` for every leaf item that has both a shortcut and a handler. `command` event key generates `command=self.method` constructor kwarg (not `.bind()`) for applicable widget types. Children store coords relative to parent content area; codegen uses `self.parent_id` as the parent arg and skips y-offset for children. |
| `persistence.py` | `.form.json` save/load with SHA-256 checksum for manual-edit detection; `extract_event_bodies`, `extract_init_user_zones`, `extract_helper_methods`, `extract_user_imports` — AST + marker-based extraction used during regeneration to splice user code back in |
| `canvas.py` | Dotted-grid drag/drop surface — canvas-primitive widget rendering (bg/fg from props applied live), click-to-select, drag-to-move, resize handles, multi-select rubber band, copy/paste with cascade-offset drift reset, arrow-key nudge (1 px), bring-to-front/send-to-back, z-order preservation on every mutation. **Widget containment**: Frame/LabelFrame act as parent containers; widgets dragged onto them are auto-parented (coords stored relative to container content area); `_abs_xy()` converts to absolute canvas coords for rendering; drag-out releases parent on drop. Fires `on_structure_changed` on add/remove/reorder. Fires `on_double_click(widget_id)` on double-click. Renders live menu bar strip below title bar from `form.menu_items`; clicking a top-level menu shows a native `tk.Menu` dropdown; clicking a command leaf or check/radio item with a `command_handler` fires `on_menu_navigate(method_name)`. |
| `menu_editor.py` | VB6-style Menu Editor `Toplevel` dialog — Caption/Name/Shortcut fields, Enabled/Visible checkboxes, Type combobox (Command/Checkbutton/Radiobutton), Variable picker (`VariablePickerEntry`), Command and Value fields, ← → ↑ ↓ arrow buttons (promote/demote/reorder), Insert/Delete/Next actions, indented listbox preview, hover hint bar (3-line, below OK/Cancel), OK/Cancel, ? guide. Accepts optional `form` arg so the variable picker can show all form-level variables. Works on a deep copy; calls `on_save(items)` only on OK. |
| `var_picker.py` | `collect_form_variables(form)` — gathers all variable names+types from widget `VariableBinding`s then menu check/radiobutton items in definition order, deduped. `show_variable_popup(anchor, variables, on_select, entry_ref)` — dark-themed `Toplevel` listing variables as `name (VarType)` rows; live-filters as the user types in `entry_ref`; refocuses entry after render; dismisses on outside click but keeps alive on anchor/entry clicks. `VariablePickerEntry` — reusable `Entry + ▾ button` widget that opens the popup on button click. Used by both the properties panel (inline treeview editor for `var__name` row) and the menu editor Variable field. |
| `toolbar.py` | Alignment/distribute/size/snap toolbar strip rendered above the design canvas — purely a UI widget |
| `widgets/designer_palette.py` | Widget toolbox panel — scrollable list of widget types with canvas-drawn mini-previews; click-to-place; lives in `widgets/` because it is a `tk.Frame` subclass |
| `widgets/designer_properties.py` | Property grid + Events tab — inline text editor for most props; **inline overlay dropdown** for enum props (`tk.Frame` overlay, item width sized to content, per-item hover hints in status bar for all prop options); color swatch + `tkinter.colorchooser` for color props; state dropdown with conditional state-color rows; validate dropdown with `--vcmd`/`--args`/`--ivcmd` rows; **inline list editor** for array-type props (e.g. Combobox `values`): floating panel with item rows + `×` remove buttons, Entry at bottom — Enter adds item and keeps focus; variable binding section; control selector dropdown at top; read-only `parent` geo row (drag on canvas to reparent); red `name_warn` tag on non-underscore handler names; `? Events` guide row at bottom of Events tab; ✦ auto-wire button on hover for unwired event rows; blue hover highlight on all rows in both tabs; `×` clear button on hover for color/optional props and wired event handlers; status-bar property/event hints on hover (wrapping label, grey, defers to timed errors) |

**Designer layout (when active):**
```
┌─────────────┬──────────────────────────┬──────────────────┐
│ Palette     │  [Editor]  [Designer]    │ Properties       │
│ (reuses     │  Canvas (dotted grid)    │ Panel            │
│  explorer   │                          │                  │
│  slot)      │  ┌────────────────────┐  │ Name: btn1       │
│             │  │ Form1              │  │ Text: Click Me   │
│ [Button]    │  │  [Click Me]        │  │ Width: 90        │
│ [Label]     │  └────────────────────┘  │ ── Events ──     │
│ [Entry] ... │                          │ Click: [stub ▼]  │
└─────────────┴──────────────────────────┴──────────────────┘
```

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

### Designer-specific decisions

- **One-way codegen.** Designer → Python only. Parsing arbitrary Python edits back into a widget model is a compiler problem — not worth it for v1.
- **Manual-edits warning on Generate Code only.** When the user clicks Generate Code and the `.py` has been manually edited since last generation (detected via SHA-256 checksum stored in `.form.json`), a dialog warns them. The warning is NOT shown on Designer mode-switch — too disruptive. Event handlers, helper methods, and user `__init__` code are always preserved.
- **IDOL:BEGIN/END markers.** Generated `__init__` wraps the auto-generated form setup and `_build_ui()` call each in `# ── IDOL:BEGIN` / `# ── IDOL:END` block pairs. The two gaps between those blocks are user-owned zones (pre-build and post-build) that survive regeneration without being overwritten.
- **Helper method preservation.** The `# ── Functions ──` section at the bottom of the generated class is fully user-owned. Any public method defined there is extracted verbatim and re-injected on regeneration. A comment explains this to the user.
- **`place()` geometry manager.** Absolute positioning only in v1. `pack()` and `grid()` can't be represented as drag-to-coordinate visually. A "convert to grid layout" option is a future feature.
- **`.form.json` sidecar.** `Form1.py` (generated code) lives next to `Form1.form.json` (designer state). The JSON is the source of truth; the `.py` is a build artifact.
- **Variable bindings.** `WidgetDescriptor.variable` holds an optional `VariableBinding(name, var_type, initial)`. The properties panel shows a Variable section for widgets that support it. Codegen emits `self.name = tk.VarType(...)` declarations inside the IDOL:BEGIN block and wires the `textvariable=`/`variable=` kwarg automatically.
- **Color props.** `registry.py` declares `color_props` per widget type. Empty color props are skipped in codegen (no `bg=""` passed to tkinter). Canvas draw functions read `props.get("bg"/"fg")` with hardcoded fallbacks so color changes reflect live on the design surface.
- **Border style and maximize box.** `FormModel.border_style` ("sizable"/"fixed"/"none") and `maximize_box` (bool) replace the old `resizable_x`/`resizable_y` fields. Old `.form.json` files are auto-migrated on load. "none" generates `overrideredirect(True)`; "fixed" or `maximize_box=False` generates `resizable(False, False)`.
- **Dirty tracking.** `app.py` tracks `_designer_dirty` — set on every prop/event/structure change, cleared on form load and after Generate Code. Clicking Run while dirty prompts the user to generate first.
- **`form_type` field reserved.** `FormModel.form_type` exists now but is always `"main"` in v1. v2 will use `"dialog"` to generate `tk.Toplevel` subclasses without a data model migration.
- **Contextual left panel.** Entering Designer mode swaps the explorer out and the palette in — same slot, no floating windows. Exiting Designer restores the explorer.
- **No external image assets in palette.** Widget mini-previews are drawn procedurally on `tk.Canvas` per widget type. Defined in `registry.py` alongside the widget's other metadata.
- **Enum dropdowns use `tk.Menu`, not `ttk.Combobox`.** Combobox embedded inside a Treeview fights with the tree's Button-1 binding (focus stealing, event bubbling). A `tk.Menu` popup posted below the cell is simpler and conflict-free.

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
- **Never pass `self.after` directly as `after_fn`** — on macOS Python 3.14+, `tkinter.after()` calls `tk.createcommand()` internally and must only be called from the main thread
- Always use `make_thread_safe_after(self)` from `utils/thread_safe_after.py` instead: it queues callbacks from any thread and drains them on the main thread via a 16ms poll loop
- The pattern is: do work on thread → `after_fn(0, callback, *args)`

---

## Current Feature State

Implemented and stable:
- Multi-tab editing with session persistence
- Pygments syntax highlighting
- pylsp LSP integration (hover, diagnostics, definition, completion)
- **Problems panel** — PROBLEMS tab in bottom bar with colored severity dots; click to jump to line/column
- **Diagnostic statusbar badge** — live ✕N ⚠N count; click to open Problems panel
- **Interpreter statusbar segment** — shows active Python version; click to open interpreter picker popup; selection persists per project root in `~/.idol/settings.json`; venv activation (from terminal toolbar or project wizard) shown as `(.venv) Python x.x.x` and re-activated automatically on next launch
- Sticky scroll, minimap
- **Breadcrumb bar** — path crumbs, symbol crumbs, sibling picker, locals drill-down, marquee scroll footer
- **Multi-cursor editing** — Alt+Click to add/remove cursors; Shift+Arrow for independent per-cursor selections; Ctrl+C copies all selections; smart pairs and bracket matching work at every cursor; click-placement aligned to nearest character boundary
- **Line move & duplicate** — Alt+Up/Down moves current line or selected block; Shift+Alt+Down duplicates below (cursor follows); Shift+Alt+Up duplicates below (cursor stays on original)
- **Unified Panels menu** — View → Panels submenu switches between Output/Terminal/Problems/Debug tabs; Ctrl+` terminal, Ctrl+Shift+U output, Ctrl+Shift+M problems, Ctrl+Shift+Y debug; each shortcut toggles visibility if already active
- Split editor with scroll sync
- Git integration: staging, unstaging, commit, push, diff view, health panel, inline file explanations, fix wizard
- **Commit History panel** — last 50 commits, file diff on click, filter bar, load more
- Integrated PTY terminal with venv detection (activate/deactivate/switch toolbar)
- **Run Line / Run Selection** — right-click to execute in output panel
- AI chat panel (Ollama, session history, token counter, remote host config, animated "Thinking..." dots while awaiting response)
- Learning Mode (F1) — hover any IDE element for three-section explanations with AI Ask button
- Pip package manager with topic grouping, PyPI search, and AI examples
- Command palette (Ctrl+Shift+P) with fuzzy search and `@` symbol search
- Project setup wizard (4-step: name/location, interpreter/venv, git/starter files, summary)
- **Integrated Python debugger** — debugpy over DAP; breakpoints, step controls, LOCALS + BREAKPOINTS panel; IDOL's bundled debugpy injected via PYTHONPATH — no per-project install needed
- Nav toolbar (back/forward, split, minimap, sidebar, zen, AI, packages, learning toggles)
- Zen mode (F10), Toggle Sidebar (Ctrl+B)
- Colorscheme system (`.toml` files)

## Planned / In Progress

- **GUI Designer — remaining roadmap:** font picker; anchor/justify dropdowns; tab order / z-order panel; dialog/Toplevel forms (`form_type="dialog"` slot exists); grid layout mode; live preview (run form in subprocess); startup sash jump fix (apply h_sash width from session.json before sidebar is added to `_h_pane` to prevent layout jump on launch — palette/properties sash widths are already persisted).

## Designer — Shipped (Phase 2)

- Drag/drop canvas with snap grid, resize handles, multi-select rubber band, copy/paste with cascade-offset drift reset, arrow-key nudge (1 px), bring-to-front/send-to-back, z-order preservation on every mutation
- Properties panel: inline editor, color picker with live canvas preview, variable binding (StringVar/IntVar/DoubleVar/BooleanVar), border style / maximize box dropdowns
- **Control selector dropdown** at top of properties panel — lists all widgets + form; selecting navigates canvas
- **State property** with conditional state-color rows (`readonlybackground`, `disabledbackground`, `disabledforeground`) that appear only when state is readonly/disabled; auto-fills default colors on state change
- **Validate support** for Entry/Spinbox — `validatecommand` / `--args` / `invalidcommand` rows; `--args` dropdown with common substitution code presets (`%P`, `%P, %S`, etc.)
- **Red `name_warn` tag** on event handler names and vcmd method names that don't start with `_`
- **Hover interactions** — blue `#569cd6` highlight on all rows in both Properties and Events tabs; `×` clear button on hover for color/optional props and wired event handlers; status-bar hints (grey, wrapping, defers to timed errors) describe each property/event on hover; ✦ auto-wire button on hover for unwired event rows
- Events tab: click event name to auto-wire handler; edit handler name inline; `? Events` guide row opens paginated GuideWindow
- **`command` event** at top of Events tab for Button, Checkbutton, Radiobutton, Scale, Spinbox — generates `command=self.method` constructor kwarg (not `.bind()`)
- **`comboselected` event** for Combobox — generates `.bind("<<ComboboxSelected>>", ...)`
- **Double-click widget** → auto-generates code if dirty, then switches to editor and navigates to first event handler; double-click with no events → switches to Events tab
- **Menu Builder** — VB6-style `MenuEditor` dialog (Caption/Name/Shortcut, Enabled/Visible, Type combobox, Variable picker, Command, Value fields, indent arrows, Insert/Delete/Next, preview listbox, hover hint bar below OK/Cancel); `menu bar` row in form properties opens it; live menu bar strip rendered on canvas below the title bar; clicking a top-level name opens a native dropdown; clicking a leaf command item or a check/radiobutton item with a `command_handler` navigates to its handler; codegen emits full `tk.Menu` hierarchy including `add_checkbutton`/`add_radiobutton` with variable/value/command kwargs, auto-stubs leaf command methods and check/radio command handlers, emits `BooleanVar`/`StringVar` declarations for menu variables, and emits `self.bind("<event>", handler)` for every item that has both a shortcut and a handler
- **Variable picker** — `VariablePickerEntry` (Entry + ▾ button) opens a dark-themed popup listing all form-level variables (from widget bindings and menu check/radio items) as `name (VarType)` rows; live-filters as the user types; used in both the properties panel (`var__name` row) and the Menu Editor Variable field; `collect_form_variables(form)` gathers variables in definition order, deduped
- **Inline overlay dropdown** for all enum props — `tk.Frame` overlay (not `tk.Menu`) with item width sized to content and per-item hover hints shown in status bar; covers state, validate, border_style, maximize_box, type, colorize, justify, relief, orient
- **Menu bar widget shift** — adding a menu bar shifts all top-level widgets down 20 px and increases form height; removing shifts up 20 px and shrinks form height
- **Persist designer sash widths** — palette and properties panel widths saved to `session.json` under `designer_palette_width`/`designer_props_width`; applied via `configure(width=)` before adding panes to avoid timing issues
- **Widget containment** — Frame and LabelFrame act as parent containers; dropping a widget onto one auto-parents it (coords relative to container content area, matching tkinter's placement); drag out of a container to reparent to the form or another container; `parent` row in properties is read-only (drag to reparent); codegen uses container as parent arg; LabelFrame applies 17 px label-area offset
- **Inline list editor** for array-type props (e.g. Combobox `values`) — floating panel with existing items + `×` remove buttons; Entry at bottom: Enter adds item, entry stays focused for rapid entry; Escape dismisses
- Code generation: `IDOL:BEGIN/END` markers preserve user `__init__` zones; `IDOL:IMPORTS:BEGIN/END` markers preserve user imports; helper methods and event bodies survive regeneration
- Manual-edits detection via SHA-256 checksum (warning on Generate Code, not on mode-switch)
- Dirty tracking: Run prompts to generate first; double-click auto-generates silently
- Default bg/fg on new widgets; auto state-color defaults on state change
- bg/fg color props for all applicable widget types, reflected live on canvas
- **Relief rendering** — `_relief_border` helper draws raised/sunken/groove/ridge/solid/flat borders live on the canvas for Button, Label, Entry, Text, Listbox, Frame, LabelFrame, and Spinbox; reads the `relief` and `borderwidth` props; Frame keeps its dashed design-time indicator when relief is flat
- **Draw-to-size placement** — after arming a palette tool, drag on the canvas to draw the widget's bounding box; placed at drawn size (grid-snapped, min 2×GRID) on mouseup; plain click drops at default size; container parenting works in both modes
- **Palette drag-and-drop** — drag a widget type directly from the palette onto the canvas; ghost label follows cursor; releases outside canvas cancel silently; `on_drag_drop` callback in `DesignerPalette` → `canvas.drop_widget(type_key, cx, cy)`

---

## Keeping Docs Current

**Rule: every feature change ships with a docs change. No exceptions.**

### This file (`CONTRIBUTING.md`)
- When you add a file to `editor/`, `utils/`, `widgets/`, or `designer/`, add a row to the relevant table
- When a planned feature ships, move it from **Planned / In Progress** to **Current Feature State**
- When a key technical decision changes (threading model, import rules, etc.), update the relevant section

### `README.md`
- Keep feature summaries (3–5 bullets per section) accurate — update wording if behavior changes
- Add a new feature section (with screenshot link) when a major feature ships
- If a feature is removed or renamed, update or remove its entry

### `docs/`
Each file in `docs/` maps to a feature area. When you change a feature, update the matching doc:

| Changed area | Update this doc |
|---|---|
| Editor, multi-cursor, split, breadcrumb, minimap | `docs/editor.md` |
| Diagnostics, Problems panel, LSP | `docs/intelligence.md` |
| Explorer, command palette, outline, references | `docs/navigation.md` |
| Git panel, health, history, wizards | `docs/git.md` |
| Terminal, output, run line/selection | `docs/terminal.md` |
| Debugger, breakpoints, DAP | `docs/debugger.md` |
| AI Chat panel | `docs/ai-chat.md` |
| Package Manager | `docs/package-manager.md` |
| Learning Mode | `docs/learning-mode.md` |
| Project wizard, interpreter, session, status bar | `docs/project.md` |
| GUI Designer (any part) | `docs/designer.md` |
| Keyboard shortcuts | `docs/keyboard-shortcuts.md` |
| Install, requirements, first-run flow | `docs/getting-started.md` |

### `ROADMAP.md`
- When a planned item ships, move it from the backlog to the Shipped section with a date
- Add new planned items as they are decided

---

## What NOT To Do

- Don't add widget imports to `editor/` or `utils/` modules
- Don't run subprocess calls from `widgets/` directly
- Don't put data files inside package directories — use `data/`
- Don't introduce async/await
- Don't suggest rewriting in a different GUI framework
- Don't create a third file for a feature that already has a backend and a widget — extend the existing pair
- Don't add top-level files to root unless they are genuine entry points or project config
