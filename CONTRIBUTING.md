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
| `ui_font.py` | Cross-platform font constant — exports `UI_FONT`: `"Segoe UI"` on Windows, `"Helvetica Neue"` on macOS, `"DejaVu Sans"` on Linux. Used everywhere a UI label font is needed instead of hardcoding `"Segoe UI"`. |

### `widgets/` — UI only
Every file is a Tkinter widget or panel. Imports from `editor/` and `utils/` for data,
never runs subprocesses or owns protocol logic itself.

Key widgets: `ai_chat_panel.py`, `bottom_panel.py`, `breadcrumb_bar.py`, `clipboard_history.py`,
`codeview.py`, `command_palette.py`, `completion_popup.py`, `debug_panel.py`, `designer_palette.py`,
`explorer.py`, `find_replace.py`, `guide_window.py`, `learning_manager.py`,
`learning_panel.py`, `linenums.py`, `minimap.py`, `notebook.py`, `outline.py`,
`output.py`, `package_manager.py`, `problems_panel.py`, `project_wizard.py`, `references.py`,
`sidebar.py`, `source_control.py`, `statusbar.py`, `sticky_scroll.py`, `styled_checkbox.py`, `terminal.py`

`styled_checkbox.py` — reusable Unicode-glyph checkbox (`tk.Frame` subclass): a `tk.Label` box (`☑`/`☐`) paired with a text `tk.Label`; identical appearance on all platforms (no native `tk.Checkbutton` quirks); supports disabled state, custom colors, and font sizes. Used in `project_wizard.py`.

`clipboard_history.py` — canvas-virtualized clipboard ring (`ClipboardHistoryPanel`). Rows are
drawn as `Canvas` primitives (background rect + text items); hover state updated via
`itemconfigure` on the background rect only — zero widget teardown, zero full redraw. Ring buffer
of 50 entries; deduplication by content; per-entry pin (right-click); search/filter bar; keyboard
nav (Up/Down/Enter/Ctrl+C); pin-to-top toolbar button. Opened as a persistent hidden `Toplevel`
(Ctrl+Shift+H); `push(text, source)` is called from `app.py` whenever the editor copies or cuts.
Pilot for the canvas-renderer pattern that will eventually back all sidebar panels.

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
| `model.py` | `WidgetDescriptor`, `VariableBinding`, `MenuItemDescriptor`, and `FormModel` dataclasses — the canonical source of truth for every form. `FormModel` tracks name, title, size, `border_style`, `maximize_box`, `always_on_top`, `bg`, `form_type` ("main"/"dialog"), widget list, `menu_items` list, and `linked_dialogs` list. `VariableBinding` holds the tkinter variable (StringVar/IntVar/DoubleVar/BooleanVar) bound to a widget. `MenuItemDescriptor` holds caption, name, indent (0 = top-level cascade, 1+ = item/submenu), enabled, visible, shortcut, `kind` ("command"/"checkbutton"/"radiobutton"), `variable` (tk variable name), `value` (radiobutton value string), and `command_handler` (optional handler name for check/radio items). |
| `registry.py` | `REGISTRY` dict — one entry per widget type: tk class, default size, default props, available events (Button/Checkbutton/Radiobutton/Scale/Spinbox list `"command"` first; Combobox lists `"comboselected"` first), `color_props` list, `is_container` flag (Frame/LabelFrame/Notebook), `is_notebook` flag (Notebook only — canvas uses this to render tab strip, hide inactive children, and route tab-change events), `variable_prop`/`variable_types` for variable binding, and a mini-preview drawing function. Non-input widgets (Button, Label, Checkbutton, Radiobutton, Frame, LabelFrame, Scale) have `"bg": ""` so no `bg=` kwarg is emitted on new widgets — they inherit the OS default background. Input widgets (Entry, Text, Listbox, Spinbox) default to `"bg": "#FFFFFF"`. |
| `codegen.py` | `FormModel → Python` — generates a class-based source file. Two `IDOL:BEGIN/END` marker pairs in `__init__` delimit user-owned zones (pre-build and post-build) that survive regeneration. `IDOL:IMPORTS:BEGIN/END` markers preserve user-added imports. Preserves event bodies, helper methods, and user `__init__` code. Handles `validatecommand`/`invalidcommand` as `(self.register(self.method), args...)`. Skips empty/default props. `_menu_lines()` emits `tk.Menu` hierarchy including `add_checkbutton`/`add_radiobutton` for check/radio items; `_menu_command_methods()` harvests leaf item names and check/radio command handlers so `_collect_methods()` stubs them automatically; `_menu_variable_decls()` emits `BooleanVar`/`StringVar` declarations for menu variables; `_menu_bind_lines()` emits `self.bind("<shortcut>", handler)` for every leaf item that has both a shortcut and a handler. `command` event key generates `command=self.method` constructor kwarg (not `.bind()`) for applicable widget types. Children store coords relative to parent content area; codegen uses `self.parent_id` as the parent arg and skips y-offset for children. Notebook children emitted inside `ttk.Notebook.add()` calls grouped by tab. **Debounced auto-generation** — any canvas or property change schedules a codegen run 1.5 s later; the timer resets on each change so rapid edits coalesce into a single run. |
| `persistence.py` | `.form.json` save/load with SHA-256 checksum for manual-edit detection; `extract_event_bodies`, `extract_init_user_zones`, `extract_helper_methods`, `extract_user_imports` — AST + marker-based extraction used during regeneration to splice user code back in |
| `canvas.py` | Dotted-grid drag/drop surface — canvas-primitive widget rendering (bg/fg from props applied live), click-to-select, drag-to-move, resize handles, multi-select rubber band, copy/paste with cascade-offset drift reset, **arrow-key nudge (8 px by grid, Shift+arrow 1 px fine nudge)**, bring-to-front/send-to-back, z-order preservation on every mutation. **Shift+snap bypass** — holding Shift during move, resize, form resize, or widget draw disables snap (1px precision); snap toolbar button dims immediately on Shift key-down and restores on key-up via `on_snap_state_changed` callback. **Titlebar click** — clicking the form title bar tag selects the form and shows its resize handles (previously, "titlebar" was incorrectly in the `_topmost_at` skip list). **Widget containment**: Frame/LabelFrame/Notebook act as parent containers; widgets dragged or drawn onto them are auto-parented (coords stored relative to container content area); `_abs_xy()` converts to absolute canvas coords for rendering; drag-out releases parent on drop; children clamped to container bounds on drop. **Pointer cursor** — while a palette tool is armed, hovering over an existing widget shows an arrow cursor (click selects and de-arms, not places). Fires `on_structure_changed` on add/remove/reorder. Fires `on_double_click(widget_id)` on double-click. Renders live menu bar strip below title bar from `form.menu_items`; clicking a top-level menu shows a native `tk.Menu` dropdown; clicking a command leaf or check/radio item with a `command_handler` fires `on_menu_navigate(method_name)`. Resize handles and rubber-band selection use `canvasx`/`canvasy` to account for scroll offset. **Linux mousewheel** — `<Button-4>`/`<Button-5>` events bound alongside `<MouseWheel>` for X11 vertical scroll; `<Shift-Button-4>`/`<Shift-Button-5>` for horizontal scroll. |
| `menu_editor.py` | VB6-style Menu Editor `Toplevel` dialog — Caption/Name/Shortcut fields, Enabled/Visible checkboxes, Type combobox (Command/Checkbutton/Radiobutton), Variable picker (`VariablePickerEntry`), Command and Value fields, ← → ↑ ↓ arrow buttons (promote/demote/reorder), Insert/Delete/Next actions, indented listbox preview, hover hint bar (3-line, below OK/Cancel), OK/Cancel, ? guide. Accepts optional `form` arg so the variable picker can show all form-level variables. Works on a deep copy; calls `on_save(items)` only on OK. |
| `var_picker.py` | `collect_form_variables(form)` — gathers all variable names+types from widget `VariableBinding`s then menu check/radiobutton items in definition order, deduped. `show_variable_popup(anchor, variables, on_select, entry_ref)` — dark-themed `Toplevel` listing variables as `name (VarType)` rows; live-filters as the user types in `entry_ref`; refocuses entry after render; dismisses on outside click but keeps alive on anchor/entry clicks. `VariablePickerEntry` — reusable `Entry + ▾ button` widget that opens the popup on button click. Used by both the properties panel (inline treeview editor for `var__name` row) and the menu editor Variable field. |
| `toolbar.py` | Alignment/distribute/size/snap toolbar strip rendered above the design canvas — purely a UI widget |
| `widgets/designer_palette.py` | Widget toolbox panel — scrollable list of widget types with canvas-drawn mini-previews; click-to-place; lives in `widgets/` because it is a `tk.Frame` subclass |
| `widgets/designer_properties.py` | Property grid + Events + Handlers + Order tabs — **canvas-rendered Properties, Events, and Order tabs** with a custom dark scrollbar (no `ttk.Treeview`; rows are canvas primitives, zero widget teardown on refresh). Inline text editor for most props; **inline overlay dropdown** for enum props (`tk.Frame` overlay, item width sized to content, per-item hover hints in status bar for all prop options); color swatch + `tkinter.colorchooser` for color props; state dropdown with conditional state-color rows; validate dropdown with `--vcmd`/`--args`/`--ivcmd` rows (hovering a substitution code in the `--args` dropdown shows its meaning in the hint bar); **inline list editor** for array-type props (e.g. Combobox `values`): floating panel with item rows + `×` remove buttons, Entry at bottom — Enter adds item and keeps focus; variable binding section; control selector dropdown at top; read-only `parent` geo row (drag on canvas to reparent); red `name_warn` tag on non-underscore handler names; `? Events` guide row at bottom of Events tab; ✦ auto-wire button on hover for unwired event rows; **Events tab click behavior**: clicking the name column alone does nothing — only value-column click opens the picker; double-click on any row navigates to that handler. **Handlers tab** — catalog-driven list of every method IDOL can generate for the selected widget (event callbacks + utility methods like `_set_always_on_top`); checkbox column (x ≤ 28 px) toggles on/off; single-click on name column does nothing; double-click on checked row navigates to handler, double-click on unchecked row enables it; hint bar at bottom describes hovered handler; refreshes on any selection change. **Order tab** — canvas-rendered numbered list; drag to reorder (tab key focus sequence = z-order); **Notebook tab grouping**: Notebook children appear indented under teal tab-header rows in their `tabs` property order; dragging a child across a tab header reassigns `widget.tab` and fires `on_prop_change` to sync canvas + codegen; badge numbering is scoped per tab. Blue hover highlight on all rows in all tabs; `×` clear button on hover for color/optional props and wired event handlers; status-bar property/event hints on hover (wrapping label, grey, defers to timed errors); `form__bg` clearable (clears the form background to OS default). **X11 saved-iid pattern** — `_prop_clear_iid` and `_ev_btn_iid` fields store the hovered row's iid when an overlay button is shown; click handlers read these fields instead of `_props_hov_idx`/`_events_hov_idx`, which X11 spurious `<Leave>` events clear before the click fires — fixes the clear button and ✦ wire button on Linux. `_prop_clearing`/`_ev_clearing` flags suppress the orphaned `<ButtonRelease-1>` X11 delivers to the canvas when an overlay label is hidden between press and release. |

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
- **No codegen confirmation.** Code is regenerated silently — on the 1.5 s auto-gen debounce, on explicit `Ctrl+Shift+G`, and on Run when dirty. Event handlers, helper methods, and user `__init__` code are always preserved, so overwriting the `.py` is always safe.
- **IDOL:BEGIN/END markers.** Generated `__init__` wraps the auto-generated form setup and `_build_ui()` call each in `# ── IDOL:BEGIN` / `# ── IDOL:END` block pairs. The two gaps between those blocks are user-owned zones (pre-build and post-build) that survive regeneration without being overwritten.
- **Helper method preservation.** The `# ── Functions ──` section at the bottom of the generated class is fully user-owned. Any public method defined there is extracted verbatim and re-injected on regeneration. A comment explains this to the user.
- **`place()` geometry manager.** Absolute positioning only in v1. `pack()` and `grid()` can't be represented as drag-to-coordinate visually. A "convert to grid layout" option is a future feature.
- **`.form.json` sidecar.** `Form1.py` (generated code) lives next to `Form1.form.json` (designer state). The JSON is the source of truth; the `.py` is a build artifact.
- **Variable bindings.** `WidgetDescriptor.variable` holds an optional `VariableBinding(name, var_type, initial)`. The properties panel shows a Variable section for widgets that support it. Codegen emits `self.name = tk.VarType(...)` declarations inside the IDOL:BEGIN block and wires the `textvariable=`/`variable=` kwarg automatically.
- **Color props.** `registry.py` declares `color_props` per widget type. Empty color props are skipped in codegen (no `bg=""` passed to tkinter). Canvas draw functions read `props.get("bg"/"fg")` with hardcoded fallbacks so color changes reflect live on the design surface.
- **Border style and maximize box.** `FormModel.border_style` ("sizable"/"fixed"/"none") and `maximize_box` (bool) replace the old `resizable_x`/`resizable_y` fields. Old `.form.json` files are auto-migrated on load. "none" generates `overrideredirect(True)`; "fixed" or `maximize_box=False` generates `resizable(False, False)`.
- **Dirty tracking.** `app.py` tracks two dirty flags set together via `_set_designer_dirty()`: `_designer_dirty` (codegen tracking — cleared on form load and after Generate Code; clicking Run while dirty prompts the user to generate first) and `_designer_forms_dirty` (JSON save tracking — cleared after Save Form or Generate Code; triggers Save/Don't Save/Cancel prompt on exit).
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
- Multi-tab editing with session persistence (dirty tracking, restore hardening); **CRC dirty tracking** — undo/redo clears the dirty flag automatically when content returns to the last-saved state
- Pygments syntax highlighting; fold markers (including `# ── Name ───` section-marker folds); Ctrl+/ comment toggle; word occurrence highlights on cursor move
- **Smart Home key** — first press goes to first non-whitespace; second press goes to column 0 (position-based, no state needed)
- **Center-on-navigate** — outline and references panel navigation centers the target line in the editor
- pylsp LSP integration (hover, diagnostics, definition, completion)
- **Problems panel** — PROBLEMS tab in bottom bar with colored severity dots; click to jump to line/column; hover tooltips with beginner-friendly ruff rule descriptions; Ask AI button + double-click for AI explanation
- **Dual-track error engine** — ruff subprocess + compile() fallback on debounced background thread; three-tier severity: red (error) / yellow (warning) / blue (info/hint); runtime error indicators: amber gutter arrow, line highlight, Problems tab flash
- **Diagnostic statusbar badge** — live ✕N ⚠N count; click to open Problems panel
- **Interpreter statusbar segment** — shows active Python version; click to open interpreter picker popup; selection persists per project root in `~/.idol/settings.json`; venv activation (from terminal toolbar or project wizard) shown as `(.venv) Python x.x.x` and re-activated automatically on next launch
- **Git ahead/behind statusbar** — live `↑N ↓N` badge in statusbar showing unpushed/unpulled commit counts relative to the remote tracking branch
- **Fix Encoding nav pill** — non-ASCII paste into an ASCII file surfaces a yellow pill in the breadcrumb bar offering to re-open the file with UTF-8 encoding; pill dismissed once file is saved with the new encoding
- Sticky scroll, minimap
- **Breadcrumb bar** — path crumbs, symbol crumbs, sibling picker, locals drill-down, marquee scroll footer
- **Multi-cursor editing** — Alt+Click to add/remove cursors; Shift+Arrow for independent per-cursor selections; Ctrl+C copies all selections; smart pairs and bracket matching work at every cursor; click-placement aligned to nearest character boundary
- **Line move & duplicate** — Alt+Up/Down moves current line or selected block; Shift+Alt+Down duplicates below (cursor follows); Shift+Alt+Up duplicates below (cursor stays on original)
- **Unified Panels menu** — View → Panels submenu switches between Output/Terminal/Problems/Debug tabs; Ctrl+` terminal, Ctrl+Shift+U output, Ctrl+Shift+M problems, Ctrl+Shift+Y debug; each shortcut toggles visibility if already active
- Split editor with scroll sync; scroll lock (hardware Scroll Lock key synced on startup)
- Find/Replace
- **Explorer** — rename, delete, drag/drop file/folder, new file/folder, context menus, unsaved-change guard on move
- **Outline panel** — symbol tree with locals drill-down (instance attrs, nested defs, color-coded sections)
- References panel
- Git integration: staging, unstaging, commit, push, diff view, health panel (smart warnings + fix wizard), Add to .gitignore
- **Git guides** — install guide (Windows/macOS/Linux), identity guide (git config + GitHub account + `gh auth login`), remote guide, first commit guide
- **Commit History panel** — last 50 commits, file diff on click, filter bar, load more
- Integrated PTY terminal (pyte VT100 screen buffer) with venv detection (activate/deactivate/switch toolbar)
- **Terminal debug mode** — launch debugpy in terminal, attach DAP client
- **Output panel** — copy button and right-click context menu; inline stdin bar for `input()` support
- **Run Line / Run Selection** — right-click to execute in output panel
- AI chat panel (Ollama, session history, token counter, remote host config, animated "Thinking..." dots, horizontal scroll on code blocks)
- **Learning Mode (F1)** — hover any IDE element for three-section explanations with AI Ask button; custom arrow+? cursor; cursor+flash intercept system
- Pip package manager with topic grouping, PyPI search, AI examples, and active-interpreter awareness
- Command palette (Ctrl+Shift+P) with fuzzy search, `@` symbol search, `!pip` mode with package autocomplete, and designer commands (Generate Code, Fold All, Unfold All)
- Project setup wizard (4-step: name/location, interpreter/venv, git/starter files, summary + first commit guide)
- **Session persistence** — open tabs, layout, appearance, breakpoints, active interpreter, active venv; auto-session (`~/.idol/session.json`); named saves (`.idol-project` in project root)
- **Integrated Python debugger** — debugpy over DAP; breakpoints with VSCode-style gutter (hover ghost dot, bright active dot), session persistence, auto-shift on line insert/delete; step controls (F5/F10/F11/Shift+F11/Shift+F5); LOCALS + BREAKPOINTS panel; IDOL's bundled debugpy injected via PYTHONPATH — no per-project install needed
- **Floating debug panel** — dock/undock, always-on-top, session restore
- Nav toolbar (split run button, panel toggles: AI/Learn/Packages; view toggles: Minimap/Sidebar/Split/Zen)
- Zen mode (F10), Toggle Sidebar (Ctrl+B)
- **GuideWindow system** — content-agnostic paginated `Toplevel` used across all guides; see `widgets/guide_window.py`
- Colorscheme system (`.toml` files)
- **Clipboard History panel** (`widgets/clipboard_history.py`) — canvas-virtualized ring of the
  last 50 clipboard entries; opened via Ctrl+Shift+H as a persistent hidden `Toplevel`; canvas
  rows (rect + text) with hover via `itemconfigure`, keyboard nav, pin/unpin (right-click), and
  search filter; `on_copy` callback on `codeview` delivers text directly on Ctrl+C (bypasses
  the `<<Copy>>` virtual event which `_copy()` suppresses with `return "break"`)
- **Undo tag-snapshot** — `_capture_token_tags()` grabs all `Token.*` tag ranges via a single
  `dump -tag` Tcl call; stored per undo burst (gated by `_undo_pending_save`); `_restore_token_tags()`
  replays them via a batched `tk.eval` script on undo/redo, skipping Pygments entirely when tags
  are available; eliminates the white-flash and fold-marker lag on Ctrl+Z
- **Ghost sash — sidebar** — sidebar's custom Frame-based horizontal sashes use a 2 px `#007acc`
  ghost overlay during drag; actual resize fires on `ButtonRelease` only; also restores the
  missing `<ButtonPress-1>` binding that was never wired to `_sash_press`

## Planned / In Progress

- **GUI Designer — remaining roadmap:** grid layout mode; live preview (run form in subprocess).

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
- **Double-click palette widget** → place at form centre (default size)
- **Font property** — `font` row opens `tkfontchooser` dialog pre-populated with the current value; writes result back as `"Family size bold italic"` string; supports bold, italic, underline, overstrike
- **Handler picker** — `HandlerPickerEntry` (Entry + ▾ button) in the Events tab and Menu Editor Command field; opens a scrollable popup listing all handlers defined on the form; hover row to preview name in entry; max 10 visible with mousewheel scroll; smart positioning (right-aligned, flips above when maximised)
- **Form events** — load / activate / deactivate / unload / resize in the Events tab; codegen emits `.bind()` calls and stubs the handler methods
- **Double-click wired event row** → auto-generates code if dirty, then jumps to that handler in the editor; double-clicking the property name column in the Properties panel does the same
- **Preserve leading comments** in event handler bodies — comment lines before the first non-comment line of a handler are extracted and re-injected on regeneration
- ~~Unified codegen prompt~~ — removed; code generation is now always silent (auto-gen + Run silently regenerate; manual edits are always preserved)
- **Scrollbar property** for Listbox and Text — adds `yscrollcommand` wiring and a paired `ttk.Scrollbar` in codegen
- **Separator item** in Menu Editor — Separator button adds a menu separator row; rendered as `---` in the listbox preview; codegen emits `add_separator()`
- **& access-key in captions** — `&File` renders as `File` with underline=0; codegen emits `underline=N` kwarg; display_caption strips the `&` for canvas rendering

### Widget Anchoring + Alignment Toolbar — SHIPPED (2026-05-07)

- **Widget anchoring** — `anchor` property per widget; 3×3 picker grid in Properties; `× clear` on hover; codegen emits `_apply_anchor_layout()` which repositions/resizes anchored widgets relative to the form at runtime
- **Live anchor repositioning** — widgets with anchors reposition and resize in real time as the form is dragged on the canvas, matching the runtime behavior of `_apply_anchor_layout()`; **Shift+resize suppresses anchors** so widgets stay frozen while the form is dragged
- **Anchor hint** — hovering the anchor row shows a description + "Hold Shift while resizing to ignore all anchors"; anchor picker popup shows the Shift note at the bottom
- **Alignment Toolbar** — right-aligned strip in the designer toolbar with four clusters: (1) Align L/R/T/B, Center H/V; (2) Distribute H/V equal spacing (grid-aware: clusters into rows/columns, assigns uniform positions); (3) Same Width / Same Height; (4) Undo ↶ / Redo ↷ / Copy ⧉ / Paste ⎘
- **Toolbar button states** — all buttons disable (dim to #555555, ignore clicks) when their action doesn't currently apply: alignment/distribute/size require ≥2/3 selected; undo/redo track stack depth; copy requires selection; paste requires clipboard
- **Undo/Redo** — snapshot-based history (max 50); `push_undo()` called before every mutation; Ctrl+Z/Y; toolbar buttons; right-click menu Undo/Redo at top
- **Multi-select properties** — intersection of all selected widgets' shared props shown; blank for mixed values; full editing via dropdown/color/text; font and list editors blocked in multi-select by design
- **Primary selection** in amber (#e8a844) with full resize handles; secondary selections show blue border only; resize delta propagates to all selected widgets
- **Canvas scrollbars** — custom `VerticalScrollbar`/`HorizontalScrollbar` (from `widgets/scrollbar.py`) on canvas with `_MARGIN` padding and all-platform mousewheel support (Windows/macOS via `<MouseWheel>`; Linux via `<Button-4>`/`<Button-5>`; Shift variants for horizontal scroll)
- **Edit menu context-aware** — Undo/Redo/Cut/Copy/Paste/Select All route to designer when in designer mode; Find & Replace is greyed out in designer mode and re-enabled on editor switch

### Designer Polish Session — SHIPPED (2026-05-07 continued)

- **Multi-placement mode** — single click on a palette widget keeps the tool armed; each canvas click places another widget of that type; Escape / click outside canvas / Pointer tool de-arms
- **Smart placement cursor** — crosshair over empty form area (will place), arrow over unselected widget (click selects + de-arms), fleur over selected widget(s) (click selects + de-arms, drag moves immediately without second click)
- **Form resize handles** — N/NW/NE handles now appear above the title bar instead of overlapping the form content
- **Ghost sash fix** — `ttk.PanedWindow` (editor/output vertical sash) now correctly detects sash hits using `sashpos()` proximity instead of unreliable `identify()` — fixes ghost drag line on Windows
- **Grid layout popup** — ⊡ toolbar button opens a `Toplevel` with Make Grid + H/V nudge controls; H/V nudge buttons step by 8px, or 1px when Shift is held
- **Form recenter** — form recenters on canvas after a form resize drag (mouse-up)
- **Events guide on second double-click** — double-clicking a widget that has no wired events a second time opens the Events GuideWindow

### Designer — Linux / Cross-Platform Polish — SHIPPED (2026-05-10)

- **`grab_set()` ordering** — `designer_new_form()` and `MenuEditor.__init__` now call `grab_set()` after `update_idletasks()` so the window is fully mapped; fixes "can't grab window" errors on Linux/X11
- **`StyledCheckbox`** (`widgets/styled_checkbox.py`) — reusable Unicode-glyph checkbox extracted from `project_wizard.py`; identical appearance on all platforms
- **X11 saved-iid pattern** — `_prop_clear_iid`/`_ev_btn_iid` fields in `designer_properties.py`; fixes clear button and ✦ wire button on Linux (spurious `<Leave>` events cleared hover-index before clicks fired)
- **Form `bg` clearable** — `form__bg` added to clearable props; `load_form` no longer substitutes a placeholder when `bg` is empty; clearing the form bg restores the OS default
- **Empty bg defaults** — non-input widget registry entries (`"bg": ""`) so generated code doesn't hardcode Windows-gray `bg` on new widgets; OS default background used instead
- **Tkinter clipboard** — `codeview.py` copy replaced pyperclip with `clipboard_clear()` + `clipboard_append()`; `pyperclip` removed from `requirements.txt` entirely
- **Linux mousewheel on designer canvas** — `<Button-4>`/`<Button-5>` and `<Shift-Button-4>`/`<Shift-Button-5>` added to `canvas.py`
- **Cross-platform UI font** (`utils/ui_font.py`) — `UI_FONT` constant (`"Segoe UI"` / `"Helvetica Neue"` / `"DejaVu Sans"` per platform) used in place of hardcoded `"Segoe UI"` across all widget files

### Designer Phase 4 — Notebook, Scrollbars & Polish (2026-05-11)

- **ttk.Notebook widget** — first-class container in the designer; canvas renders a tab strip matching the native ttk.Notebook look (active tab raised, inactive tabs dimmer, no white fill); each child carries a `widget.tab` string; switching tabs on the canvas selects the Notebook and shows/hides children; `<<NotebookTabChanged>>` event in Events tab; codegen emits full Notebook hierarchy; `is_notebook` flag in registry used by canvas, Order panel, and `_should_render` guard (inactive-tab children never bleed through on form resize or move)
- **Order panel — Notebook tab grouping** — Notebook children appear indented under teal tab-header rows in `tabs` property order; drag a child across a header to reassign its tab; badge numbering scoped per tab
- **Draw inside containers** — drawing a new widget while the cursor is over a Frame/LabelFrame auto-parents it and clamps to container bounds; same for Notebook active tab's content area
- **Container cascade delete** — deleting a Frame/LabelFrame/Notebook removes all descendant widgets
- **Arrow-key nudge rework** — default nudge is now 8 px (matches snap grid); Shift+arrow gives 1 px fine nudge; nudge respects the snap-to-grid toggle
- **Debounced auto-codegen** — any canvas or property change schedules a codegen run 1.5 s later; rapid edits coalesce into a single run
- **Menu editor polish** — `tk.Label` + hover bindings replace all `tk.Button` instances (labels-as-buttons pattern); `tk.Checkbutton` replaced with canvas-drawn dark checkboxes; Caption→Name autofill on Tab
- **var_picker** — ▾ button replaced with `tk.Label` (labels-as-buttons)
- **Custom IDOL scrollbars throughout** — all `ttk.Scrollbar` instances in IDOL's own UI replaced with `VerticalScrollbar`/`HorizontalScrollbar` from `widgets/scrollbar.py`; editor scrollbars 16 px wide; all panel scrollbars 12 px; up/down arrow buttons removed; `command=` accepted in constructor; `autohide=True` uses `grid_remove()`/`grid()` to hide when content fits
- **macOS fullscreen persist** — fullscreen state saved to `session.json`; restored via `wm_attributes("-fullscreen", True)` with a 500 ms sash delay; removed from Known Bugs
- **Linux maximize session** — maximize state saved via a `<Configure>`-tracked `_window_maximized` flag (reading `attributes("-zoomed")` at close time is unreliable on X11); on restore when `window_maximized=False`, `_force_normal` fires at 300 ms with 4 retries to override WM session management; a visible flash remains (WM re-maximizes asynchronously) — accepted limitation, **do not** attempt `withdraw()`/`deiconify()` here as it makes the flash worse

---

### Designer Phase 3 — SHIPPED (2026-05-08 / 2026-05-09)

- **Tab Order panel** — Order tab in Properties panel shows all widgets as a canvas-rendered numbered list; drag rows to reorder (tab focus sequence = z-order); `⇥` toolbar button toggles numbered blue badges on canvas widgets; permanent hint in status bar when Order tab is active
- **Multi-form designer** — project can contain multiple forms (main windows + dialogs); FORMS tree in left panel shows hierarchy (`⬜` main, `⧉` linked dialog, "Unlinked" section); click any row to switch canvas; `+` button and `Designer → New Form…` dialog (name, type, optional link-to-parent); drag dialog row onto a main form row to link; hover `×` to unlink; canvas scroll offset correctly accounted for in resize handles and rubber-band selection
- **Dialog codegen** — dialogs generate `tk.Toplevel` subclasses; `WM_DELETE_WINDOW` wired to `_on_close(self.withdraw)` (preserved stub); parent form stores instance as `self.dlg_DialogName` (created once in `__init__`, reused via `deiconify()`); `_open_DialogName()` opener stub auto-generated on parent; `IDOL:DIALOG_IMPORTS` block fully auto-managed from link state; dialogs generated before main forms so imports resolve
- **Handlers tab** — catalog-driven panel listing every method the designer can generate for the selected widget (event callbacks + utility methods like `_set_always_on_top`); checkbox column (x ≤ 28 px) toggles wiring; double-click checked row navigates to handler; double-click unchecked row enables it; hint bar describes hovered handler; refreshes on any selection change
- **Canvas-rendered Properties, Events, and Order tabs** — all three tabs rebuilt as canvas-primitive renderers with a custom dark scrollbar; zero widget teardown on refresh; hover highlights, `×` buttons, and inline editors all implemented via canvas item `itemconfigure`
- **`always_on_top` form property** — boolean flag in `FormModel`; Properties panel checkbox; codegen emits `self.wm_attributes("-topmost", True)`; `_set_always_on_top` utility handler in Handlers catalog
- **Handler/event navigation** — Events tab name column single-click does nothing (only value-column click opens picker); double-click on any wired Events row navigates to that handler; Handlers tab double-click navigate/enable behavior; `_handlers_dbl_pending` flag prevents the second `ButtonRelease-1` Tkinter fires after a double-click from incorrectly toggling the checkbox
- **Titlebar click selects form** — clicking the form title bar tag selects the form and shows its resize handles; root fix: "titlebar" was incorrectly in the `_topmost_at` skip list alongside "grid"/"shadow"; `select_form()` guards `_on_deselect` with `was_selected` so re-clicking an already-selected title bar doesn't re-fire side effects
- **Shift+snap bypass** — holding Shift disables snap-to-grid across all four operations: widget move, widget resize, form resize, and widget draw (all at 1px precision, minimum draw size drops to 1px); snap toolbar button dims immediately on `<KeyPress-Shift>` and restores on `<KeyRelease-Shift>` via `on_snap_state_changed` → `toolbar.refresh_snap()`; snap-bypass lambdas cast to `int()` (raw `canvasx`/`canvasy` floats caused `range()` TypeError)
- **Save Form + exit prompt** — `Designer → Save Form` writes all open form JSONs immediately; menu item enabled when `_designer_forms_dirty` is set; on exit, if any form has unsaved changes a Save/Don't Save/Cancel dialog replaces silent autosave; `Generate Code` also saves form JSON and clears both dirty flags as a side effect
- **Dirty flag separation** — `_designer_dirty` (codegen tracking) and `_designer_forms_dirty` (JSON save tracking) both set via `_set_designer_dirty()` helper but cleared independently

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
