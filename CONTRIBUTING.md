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
| `theme_loader.py` | Loads `themes/<id>.json` files — `list_themes()` + `load_theme(id)` consumed by the canvas editor + the View → Theme menu. Drop a new JSON in `themes/` to add a theme; no code change. |
| `settings.py` | Settings load/save |
| `session.py` | Session persistence — saves/restores open tabs (including split-pane tabs with dirty/temp-file state), layout, appearance, breakpoints, active interpreter, and active venv (re-activates in terminal on next launch). Auto-session writes to `~/.idol/session.json`; named saves write to `.idol-project` in the project root. |
| `recent.py` | Recent projects and files — read/write helpers for `~/.idol/recent.json`. `add_project(path)` / `add_file(path)` prepend entries (max 10 each); `remove_project` / `remove_file` delete by path; `get_show_on_startup()` / `set_show_on_startup(bool)` control the Welcome tab preference. |
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
`canvas_codeview.py`, `command_palette.py`, `completion_popup.py`, `debug_panel.py`, `designer_palette.py`,
`explorer.py`, `find_replace.py`, `guide_window.py`, `learning_manager.py`,
`learning_panel.py`, `minimap.py`, `notebook.py`, `outline.py`,
`output.py`, `package_manager.py`, `problems_panel.py`, `project_wizard.py`, `references.py`,
`sidebar.py`, `source_control.py`, `statusbar.py`, `styled_checkbox.py`, `terminal.py`,
`welcome.py`

`canvas_codeview.py` — IDOL's sole editor engine. Renders text directly on a `tk.Canvas` (no `tk.Text` widget, no pygments). All state lives in `self.lines: list[str]`; cursor + selection are plain `(line, col)` tuples; tokenization is a regex-rule pass driven by `_rules` in `_init_state`. Themes are loaded from `themes/*.json` via `utils/theme_loader.py` — swap by calling `set_theme(id)`. The internal layout grids in: breadcrumb (row 0), find/replace strip (row 1, reserved), main `tk.Canvas` (row 2 col 0) + `VerticalScrollbar` (row 2 col 1), `HorizontalScrollbar` (row 3 col 0). Embedded inside the canvas: line-number / fold / breakpoint gutter, sticky scope-header band (own canvas, place'd at top), minimap (embedded `tk.Text` at font size 1, place'd on the right). Public API: `get_text/set_text`, `get_line/line_count`, `get_cursor/set_cursor`, `get_selection/set_selection/clear_selection/selected_text`, `insert/delete_selection/delete_range/replace_range`, `scroll_to_line/ensure_visible/visible_range`, `set_diagnostics/set_breakpoints/set_git_hunks/set_runtime_error_line/set_debug_line/set_filepath/set_theme`. Host hooks: `on_change`, `on_cursor_move`, `on_lines_changed`, `on_copy`, `on_completion_request`, `on_breakpoint_toggle`, and the `on_request_*` family used by the right-click menu. **Multi-cursor state**: `_mc_cursors: list[tuple[int,int]]` (secondary positions) and `_mc_anchors: list[tuple[int,int]|None]` (secondary selection anchors); Alt+click in `_on_alt_click`; edits via `_mc_apply_key`; `mc_count()` public helper.

`styled_checkbox.py` — reusable Unicode-glyph checkbox (`tk.Frame` subclass): a `tk.Label` box (`☑`/`☐`) paired with a text `tk.Label`; identical appearance on all platforms (no native `tk.Checkbutton` quirks); supports disabled state, custom colors, and font sizes. Used in `project_wizard.py`.

`clipboard_history.py` — canvas-virtualized clipboard ring (`ClipboardHistoryPanel`). Rows are
drawn as `Canvas` primitives (background rect + text items); hover state updated via
`itemconfigure` on the background rect only — zero widget teardown, zero full redraw. Ring buffer
of 50 entries; deduplication by content; per-entry pin (right-click); search/filter bar; keyboard
nav (Up/Down/Enter/Ctrl+C); pin-to-top toolbar button. Opened as a persistent hidden `Toplevel`
(Ctrl+Shift+H); `push(text, source)` is called from `app.py` whenever the editor copies or cuts.
Pilot for the canvas-renderer pattern that will eventually back all sidebar panels.

`welcome.py` — Welcome tab panel shown on first launch and whenever the main notebook is otherwise empty. Sections: **Start** (new file / open file / open folder / new project / open project action links), **Explore** (Learning Mode / GUI Designer / Package Manager), **What's New** (live `CHANGELOG.md` viewer with ‹ › section navigation, syntax-styled content, isolated mousewheel scroll), **Recent Projects** and **Recent Files** (from `utils/recent.py`; click to open, × to remove), rotating **Tips** (8-second cycle), and a **Show on startup** checkbox (persisted to `~/.idol/recent.json`). Global `<Enter>`/`<Leave>` activate `bind_all` wheel scrolling for the outer canvas; `_cl_text` returns `"break"` from its handler so the changelog box scrolls independently. `WelcomePanel` is constructed with eight `on_*` callbacks wired in `app.py`. `_parse_changelog(path)` splits `CHANGELOG.md` on `## ` headings into `{title, lines}` dicts; `_cl_render()` inserts them into the text widget with `h3`/`bullet`/`dim` tags.

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
| `model.py` | `WidgetDescriptor`, `VariableBinding`, `MenuItemDescriptor`, `HandlerWire`, `ComponentDescriptor`, `CanvasItemDescriptor`, and `FormModel` dataclasses — the canonical source of truth for every form. `FormModel` tracks name, title, size, `border_style`, `maximize_box`, `always_on_top`, `bg`, `image` (relative path to background image, `""` = none — serialized only when non-empty for backward compat), `form_type` ("main"/"dialog"), widget list, `menu_items` list, `linked_dialogs` list, `components` list (non-visual component tray), `handler_wires` list (explicit handler→widget-event wires), and `handler_options` dict ({handler_id: option_name} for mode choices like "hide (withdraw)"/"destroy (exit)"). `VariableBinding` holds the tkinter variable (StringVar/IntVar/DoubleVar/BooleanVar) bound to a widget. `MenuItemDescriptor` holds caption, name, indent (0 = top-level cascade, 1+ = item/submenu), enabled, visible, shortcut, `kind` ("command"/"checkbutton"/"radiobutton"), `variable` (tk variable name), `value` (radiobutton value string), and `command_handler` — for check/radio items: the handler name whose `_{name}_click` stub is called; for leaf command items: either empty (uses auto-generated `_{item.name}_click`) or a full method name starting with `_` (e.g. `_cd1_show_open`) when a component handler is wired directly. `get_menu_item(name)` looks up a `MenuItemDescriptor` by name. `HandlerWire` holds `handler_id`, `widget_id`, `event_key`, and `option` (e.g. "Dialog1:hide (withdraw)") — one record per handler→widget-event connection. `ComponentDescriptor` holds `id` (auto-numbered name, e.g. "timer1"), `type` (registry key), and `props` dict. **`CanvasItemDescriptor`** holds `id` (e.g. `"ci_img1"`), `kind` (`"image"/"rectangle"/"oval"/"text"/"line"`), `x`, `y`, `width`, `height`, `tags: list[str]`, `props: dict` (kind-specific: `image_path`, `fill`, `outline`, `text`, `font`, `linewidth`), and `bindings: dict[str, str]` (tk event → method name); `to_dict`/`from_dict` for JSON persistence. `WidgetDescriptor.canvas_items: list[CanvasItemDescriptor]` — only serialized when non-empty so existing form files load unchanged. `WidgetDescriptor.next_item_id(kind)` auto-numbers items with kind prefixes: `ci_img`, `ci_rect`, `ci_oval`, `ci_text`, `ci_line`. |
| `registry.py` | `REGISTRY` dict — one entry per widget type: tk class, default size, default props, available events, `color_props`, `is_container`, `is_notebook`, `variable_prop`/`variable_types`, and a mini-preview drawing function. **Canvas widget** added as a 16th type (`tk.Canvas`, 200×150, `bg` + `image` + `sizing` props, `_SIMPLE_EVENTS + _KEY_EVENTS` — full standard event set). **Label and Button** gained `image` (file path, relative to project) and `compound` props; `_load_preview_image` renders PIL thumbnails on the design canvas using `Image.resize` (fills bounds exactly, matching runtime); button images inset 2px to match the native raised border. Non-input widgets default `"bg": ""` (OS default); input widgets default `"bg": "#FFFFFF"`. |
| `codegen.py` | `FormModel → Python` — generates a class-based source file. **Image codegen** — `_has_images(form)` / `_image_load_lines(form)` emit `import os`, `from PIL import Image, ImageTk`, and `self._img_{id} = ImageTk.PhotoImage(Image.open(...).resize((w,h), LANCZOS))` inside the IDOL:BEGIN block; `image` kwarg in `_widget_lines` is replaced with `image=self._img_{id}` (Canvas gets `create_image()` post-place instead); size-changing anchors (`_SIZE_ANCHORS`) trigger a `<Configure>` binding that reloads the PhotoImage at the new widget size; `import struct` added when the Socket File Transfer scaffold is active. **Socket component codegen** — `_comp_init_for` emits server (host/port/encoding/timeout/max_clients/buffer_size/server/clients/running) or client (+ retry props, conn) state; `_comp_handler_method` for Socket: `toggle_connect` emits the toggle wrapper + `_start`/`_connect` + `_accept_loop` (server) + `_recvall` (framing) + `_recv_loop` as companion methods in one block; `start`/`connect` are direct-wire alternatives; `send_text`/`send_file` use `struct.pack('>Q', size)` framing when `_scaffold_pb_transfer` is set; `recv_loop` reads the 8-byte header and reads payload with chunk-by-chunk Progressbar updates; pre-filled scaffold bodies for `on_connect`, `on_disconnect`, `on_receive_text`, `on_receive_file`, `on_send_file`, `on_timeout`, `on_error` when the corresponding scaffold widget IDs are stored in `comp.props`; `quick_send` and `pick_and_send_file` have their own handler cases and are excluded from widget-event stub generation via `comp_methods`. | Two `IDOL:BEGIN/END` marker pairs in `__init__` delimit user-owned zones (pre-build and post-build) that survive regeneration. `IDOL:IMPORTS:BEGIN/END` markers preserve user-added imports. Preserves event bodies, helper methods, and user `__init__` code. Handles `validatecommand`/`invalidcommand` as `(self.register(self.method), args...)`. Skips empty/default props. `_menu_lines()` emits `tk.Menu` hierarchy including `add_checkbutton`/`add_radiobutton` for check/radio items; leaf command items: if `item.command_handler` starts with `_` (component handler wired directly) emits `command=self.{command_handler}`, otherwise emits `command=self._{name}_click`; `_menu_command_methods()` harvests leaf item names so `_collect_methods()` stubs them automatically; `_menu_variable_decls()` emits `BooleanVar`/`StringVar` declarations for menu variables; `_menu_bind_lines()` emits `self.bind("<shortcut>", handler)` for every leaf item that has both a shortcut and a handler. `command` event key generates `command=self.method` constructor kwarg (not `.bind()`) for applicable widget types. Children store coords relative to parent content area; codegen uses `self.parent_id` as the parent arg and skips y-offset for children. Notebook children emitted inside `ttk.Notebook.add()` calls grouped by tab. **Component init block** — `_component_init_lines()` emits an `IDOL:COMPONENTS:BEGIN/END` block inside the second `IDOL:BEGIN` block (after `_build_ui()`) that initializes each component's state variables and starts enabled timers. **CommonDialog init** — emits per-handler title vars (`self._cd1_show_open_title = ""` etc.), `messagebox_type`, and `messagebox_message` vars; no global `_title` var. **Component handler methods** — `_component_handler_lines()` emits handler methods after widget event stubs; only handlers that are actually wired (or whose callbacks are reachable) are emitted; bodies preserved across regen by `extract_event_bodies()`. **Selective imports** — `_collect_component_imports()` checks which CommonDialog handler IDs are actually wired before adding `from tkinter import filedialog/colorchooser/simpledialog/messagebox`. **`parent=self`** — all dialog calls (`askopenfilename`, `askcolor`, `simpledialog.*`, `messagebox.*`) receive `parent=self` so focus returns to the correct window. **Debounced auto-generation** — any canvas or property change schedules a codegen run 1.5 s later; the timer resets on each change so rapid edits coalesce into a single run. **Image component codegen** — `_has_images(form)` also checks Image components; `_image_comp_init_lines(form)` emits Image component init (single `ImageTk.PhotoImage` or keyed dict) **before** `_build_ui()` in the second IDOL:BEGIN block so `create_image()` calls in `_build_ui` can reference them; `_component_init_lines` skips Image type (already emitted). **Canvas button codegen** — `_canvas_button_build_lines(form)` emits `create_image + tag_bind` calls at the end of `_build_ui`; `_canvas_button_handler_methods(form, bodies)` emits `_down/_up/_enter/_leave` generated methods plus a `_click` user stub; `_img_ref(comp_id, key)` returns `self.name` (single) or `self.name["key"]` (multi). **Form background image** — `form.image` path emitted as a `tk.Label(self, image=..., bd=0).place(x=0, y=0)` at the top of `_build_ui`; PIL import triggered via `_has_images`. **Canvas item tag_bind codegen** — `_canvas_item_bind_lines(form)` iterates all `WidgetDescriptor.canvas_items`, deduplicates bindings by `(tag, event)` across items sharing a tag, and emits `self.{widget_id}.tag_bind(tag, event, self.method)` calls at the end of `_build_ui`; `_canvas_item_stub_methods(form, bodies)` collects all unique method names from item bindings and emits user stubs (preserved across regen). |
| `persistence.py` | `.form.json` save/load with SHA-256 checksum for manual-edit detection; `extract_event_bodies`, `extract_init_user_zones`, `extract_helper_methods`, `extract_user_imports` — AST + marker-based extraction used during regeneration to splice user code back in. `IDOL:COMPONENTS:BEGIN/END` marker constants defined here (used by `codegen.py` for the component init block inside the second IDOL:BEGIN block). |
| `handlers.py` | `HANDLER_CATALOG` — list of frozen `HandlerDef` dataclasses defining every method IDOL can generate for a form. `handlers_for(form_type)` and `default_enabled_for(form_type)` helpers. Each `HandlerDef` declares: `id`, `label`, `description`, `applies_to` ("main"/"dialog"), `default_checked`, `wiring` (line emitted in `__init__`), `params`, `default_body`, plus optional fields: `connectable` (shows ⚡ button in Handlers tab), `always_wired` (always in Connected section, not removable), `display_target` (built-in event shown as wire target), `options`/`stub_option_bodies`/`wire_option_bodies` (named mode variants), `applies_to_widgets` (restrict ⚡ to specific widget types), `generates_stub` (`False` = wire body goes directly into the widget event method, no standalone `def`), `dynamic_wire_body` (template with `{option}` placeholder for runtime-resolved targets like dialog names), `multi_wire` (stays in Available after wiring — can connect to multiple targets), `secondary_options` (mode choices shown in … editor on Connected rows), `connector_options_source` (`"linked_dialogs"` = pull primary connector options from `form.linked_dialogs` at connect time instead of using the static `options` list), `edit_bodies` (descriptions shown in `HandlerOptionsEditor` alongside `secondary_options` rows), `wire_side_effects` (`"sync_dialog_close_mode"` = update linked dialog's `_on_close` handler_option when wired or mode-changed — dispatched by `_apply_wire_side_effects()` in `app.py`). **Adding a new handler requires only a `HandlerDef` entry here — no `app.py` changes needed.** |
| `component_registry.py` | `PropDef`, `ComponentHandlerDef`, `ComponentDef` frozen dataclasses + `COMPONENT_REGISTRY` dict — defines every non-visual component type: its icon, palette label, `codegen_imports` list (extra import lines emitted when any handler is wired), PropDef rows (key, label, kind, default, description), and `ComponentHandlerDef` entries (`id`, `label`, `description`, `has_connector` for ⚡ wiring, `default_body`, `applies_to_widgets` allowlist, `applies_to_modes` allowlist for socket server/client gating). Ships **Timer** (`self.after()`, no imports), **CommonDialog** (open/save file, choose dir, color picker, simple input dialog, messagebox — imports emitted selectively), **Socket** (TCP server/client; `import socket, threading` always emitted; `import struct` added when File Transfer scaffold active), and **Image** (named image references; `codegen_imports=[]` — PIL import handled by `_has_images` in codegen; one `PropDef` with `kind="image_list"` for multi-file picking; one `PropDef` with `kind="canvas_ref"` for the `parent` property — dropdown shows `None`, `Global`, and all Canvas widget IDs on the form; `canvas_button` handler with `has_connector=True` and `applies_to_widgets=("Canvas",)` — clicking ⚡ opens `ImageButtonBuilder` instead of the standard `ComponentConnector`). Prop `kind` values: `"int"`, `"bool"`, `"str"`, `"readonly"`, `"float"`, `"image_list"`, `"canvas_ref"`. Helpers: `all_component_types()`, `get_component_def(type_key)`, `default_props(type_key)`. |
| `canvas.py` | Dotted-grid drag/drop surface — canvas-primitive widget rendering (bg/fg from props applied live), click-to-select, drag-to-move, resize handles, multi-select rubber band, copy/paste with cascade-offset drift reset, **arrow-key nudge (8 px by grid, Shift+arrow 1 px fine nudge)**, bring-to-front/send-to-back, z-order preservation on every mutation. **Image preview** — `_img_cache: dict[str, ImageTk.PhotoImage]` keyed by `"{path}:{w}:{h}"` prevents GC and avoids re-loading on repaint; `_load_preview_image` uses `Image.resize((w,h), LANCZOS)` to fill the widget bounds exactly; `_project_dir` (updated via `set_project_dir(path)`) resolves relative image paths against the open project, not IDOL's own CWD; `set_project_dir` also clears the cache and redraws. **Shift+snap bypass** — holding Shift during move, resize, form resize, or widget draw disables snap (1px precision); snap toolbar button dims immediately on Shift key-down and restores on key-up via `on_snap_state_changed` callback. **Titlebar click** — clicking the form title bar tag selects the form and shows its resize handles (previously, "titlebar" was incorrectly in the `_topmost_at` skip list). **Widget containment**: Frame/LabelFrame/Notebook act as parent containers; widgets dragged or drawn onto them are auto-parented (coords stored relative to container content area); `_abs_xy()` converts to absolute canvas coords for rendering; drag-out releases parent on drop; children clamped to container bounds on drop. **Pointer cursor** — while a palette tool is armed, hovering over an existing widget shows an arrow cursor (click selects and de-arms, not places). Fires `on_structure_changed` on add/remove/reorder. Fires `on_double_click(widget_id)` on double-click. Renders live menu bar strip below title bar from `form.menu_items`; clicking a top-level menu shows a native `tk.Menu` dropdown; clicking a command leaf or check/radio item with a `command_handler` fires `on_menu_navigate(method_name)`. Resize handles and rubber-band selection use `canvasx`/`canvasy` to account for scroll offset. **Linux mousewheel** — `<Button-4>`/`<Button-5>` events bound alongside `<MouseWheel>` for X11 vertical scroll; `<Shift-Button-4>`/`<Shift-Button-5>` for horizontal scroll. **Grid visibility** — `_grid_visible` module-level flag toggled by `toggle_grid()` / `grid_visible` property; toolbar ⋯ button; `_draw_form` skips dot grid when False. **canvas_button ghost preview** — `_draw_canvas_btn_ghosts(w, wx, wy, tag)` called from `_render_widget` for Canvas-type widgets; scans `form.components` for Image components with `canvas_buttons` targeting this widget; loads normal-state image via `_load_natural_image` and renders it at the configured (x, y) with a dim tag-name label, all tagged with the widget's canvas tag so it is cleaned up with the widget. `_load_natural_image(canvas, rel_path)` — like `_load_preview_image` but no resize; cache key prefixed `"natural:"`. **Widget deletion cleanup** — `_disconnect_widget(wid)` called in `remove_selected` before each widget is removed; strips `canvas_buttons` entries from Image components where `canvas_id==wid` and removes orphaned `handler_wires` targeting that widget. **Designer focus** — `_enter_designer_mode` calls `focus_set()` on the canvas at the end so Delete/arrows/Ctrl+Z go to the canvas without requiring a click. **Canvas Item edit mode** — `enter_canvas_item_mode(widget_id)` / `exit_canvas_item_mode()` switch `_ci_mode`; all mouse events dispatch to `_ci_on_click` / `_ci_on_motion` / `_ci_on_release` while active; double-click on a Canvas widget enters CI mode; `_ci_redraw()` replaces normal `_redraw()` in CI mode — draws the form, all widgets, the dimmed overlay (`gray25` stippled rects + blue border), then calls `_ci_draw_items()` + `_ci_draw_handles()` for the selected item; `arm_item_tool(kind)` enters placement mode (cursor changes to `crosshair`); clicking places a new `CanvasItemDescriptor` via `add_canvas_item()`; `remove_canvas_item(item_id)` deletes the selected item; `update_canvas_item(item)` re-renders after an external property change; `get_ci_widget()` / `get_ci_selected()` helpers; `ci_mode` / `ci_widget_id` / `ci_selected_id` read-only properties; Escape first de-arms the placement tool, second press exits CI mode; right-click context menu in CI mode shows "Add Item" cascade (5 item types), "Delete Item", "Exit Canvas Edit Mode"; right-click on Canvas widget in normal mode prepends "Edit Canvas Items"; fires `on_canvas_item_mode(widget_id | None)` and `on_ci_select(item | None)` callbacks. `set_tool_size(w, h)` — sets the default placement size used when arming a CI item tool (called by the IMAGES panel to pass actual PIL dimensions before auto-placing a CanvasImage). `remove_widgets(ids)` — removes a list of widget IDs from the form in a single operation (used by CI cleanup when syncing Image component paths). |
| `menu_editor.py` | VB6-style Menu Editor `Toplevel` dialog — Caption/Name/Shortcut fields, Enabled/Visible checkboxes, Type combobox (Command/Checkbutton/Radiobutton), Variable picker (`VariablePickerEntry`), Command and Value fields, ← → ↑ ↓ arrow buttons (promote/demote/reorder), Insert/Delete/Next actions, indented listbox preview, hover hint bar (3-line, below OK/Cancel), OK/Cancel, ? guide. Accepts optional `form` arg so the variable picker can show all form-level variables. Works on a deep copy; calls `on_save(items)` only on OK. |
| `var_picker.py` | `collect_form_variables(form)` — gathers all variable names+types from widget `VariableBinding`s then menu check/radiobutton items in definition order, deduped. `show_variable_popup(anchor, variables, on_select, entry_ref)` — dark-themed `Toplevel` listing variables as `name (VarType)` rows; live-filters as the user types in `entry_ref`; refocuses entry after render; dismisses on outside click but keeps alive on anchor/entry clicks. `VariablePickerEntry` — reusable `Entry + ▾ button` widget that opens the popup on button click. Used by both the properties panel (inline treeview editor for `var__name` row) and the menu editor Variable field. |
| `toolbar.py` | Alignment/distribute/size/snap toolbar strip rendered above the design canvas — purely a UI widget |
| `widgets/designer_palette.py` | Widget toolbox panel — scrollable list of widget types with canvas-drawn mini-previews; click-to-place; **COMPONENTS section** below widgets list (one row per `COMPONENT_REGISTRY` entry, icon glyph + label, click fires `on_component_add(type_key)`, no drag); lives in `widgets/` because it is a `tk.Frame` subclass |
| `widgets/designer_properties.py` | Property grid + Events + Handlers + Order tabs — **canvas-rendered Properties, Events, and Order tabs**; **image picker** (`_open_image_picker`) copies the selected file into `<project>/images/`, updates the prop, triggers `_check_pil_async` (subprocess check on daemon thread), and inserts an amber `warn_link` kind row "⚠ click to install Pillow" below the image row when Pillow is absent — clicking it calls `on_install_pillow` which runs pip via `PipManager`; `set_active_python` / `set_project_dir` reset the PIL check and image path resolution respectively. **Socket mode filtering** — `_comp_connectable_handlers()` replaces all inline `has_connector` filter expressions and additionally applies `applies_to_modes` so server-only handlers (start) are hidden for client sockets and vice versa; `_insert_comp_prop_rows()` skips `_SOCKET_SERVER_ONLY` / `_SOCKET_CLIENT_ONLY` props for the wrong mode; `_collect_comp_connections` also filters callbacks by `applies_to_modes`. with a custom dark scrollbar (no `ttk.Treeview`; rows are canvas primitives, zero widget teardown on refresh). Inline text editor for most props; **inline overlay dropdown** for enum props (`tk.Frame` overlay, item width sized to content, per-item hover hints in status bar for all prop options); color swatch + `tkinter.colorchooser` for color props; state dropdown with conditional state-color rows; validate dropdown with `--vcmd`/`--args`/`--ivcmd` rows (hovering a substitution code in the `--args` dropdown shows its meaning in the hint bar); **inline list editor** for array-type props (e.g. Combobox `values`): floating panel with item rows + `×` remove buttons, Entry at bottom — Enter adds item and keeps focus; variable binding section; control selector dropdown at top; read-only `parent` geo row (drag on canvas to reparent); red `name_warn` tag on non-underscore handler names; `? Events` guide row at bottom of Events tab; ✦ auto-wire button on hover for unwired event rows; **Events tab click behavior**: clicking the name column alone does nothing — only value-column click opens the picker; double-click on any row navigates to that handler. **Handlers tab** — **Available / Connected split** driven entirely by `HANDLER_CATALOG` (`designer/handlers.py`); no checkboxes. *Available* shows handlers not yet wired; ⚡ floating button on hover: for connectable handlers opens `ComponentConnector` to pick widget+event, for non-connectable handlers enables them immediately. *Connected* shows wired/enabled handlers with target on right; × floating button to disconnect; … floating button on handlers with `options` or `secondary_options` to open `HandlerOptionsEditor`. **Widget-selected mode**: only connectable handlers whose `applies_to_widgets` includes the widget type are shown in Available; Connected shows only wires targeting this specific widget; `multi_wire` handlers (e.g. `_open_dialog`) remain in Available after wiring. **Available Components** sub-section — foldable (▶/▼ header, collapsed by default); all connectable component handlers listed regardless of wiring state (reusable); ⚡ opens `ComponentConnector` pre-selecting the active canvas widget; floating buttons corrected for canvas scroll offset. **⚡ Connected Components** sub-section — component methods wired to this widget's events or menu item commands (displayed as `{item_name}.command`); × to disconnect; **… edit button** on wired rows opens `ComponentConnector` pre-populated with the existing widget+event so the binding can be changed without first disconnecting. **Component mode** (`load_component(descriptor, comp_def)`) — hides Events and Order tabs, shows PropDef rows in Properties tab (int/bool/str/readonly kinds), shows ComponentHandlerDef rows in Handlers tab (⚡ button for `has_connector=True` handlers, fires `on_component_connect(comp_id, handler_id)`); **Dialog Titles** collapsible section in Properties for CommonDialog (shows per-handler title props for every wired handler); `_exit_comp_mode()` restores tabs. **Order tab** — canvas-rendered numbered list; drag to reorder (tab key focus sequence = z-order); Notebook tab grouping with teal header rows; badge numbering scoped per tab. Blue hover highlight on all rows; `×` clear button on hover for color/optional props and wired events; status-bar hints on hover; `form__bg` clearable. **X11 saved-iid pattern** — `_prop_clear_iid`/`_ev_btn_iid` store hovered row id so click handlers survive spurious X11 `<Leave>` events. **Form image** — `load_form` inserts `form__image` row (shows basename); `_open_form_image_picker` copies file to `images/` and fires `_on_prop_change("__form__", "image", rel)`; `_form_image_hint()` returns dynamic two-line hint with PIL dimensions; `_is_prop_clearable` includes `"form__image"`. **image_list prop kind** — `_insert_comp_prop_rows` displays `"N images"` / `"(none)"` for `kind="image_list"` props; `_dispatch_comp_prop_click` routes to `_open_comp_image_picker` which calls `askopenfilenames`, copies all selected files to `images/`, and fires `_on_component_prop_change(comp_id, "paths", rel_paths)`. **canvas_button Connected display** — `_collect_comp_connections` surfaces `canvas_buttons` entries from Image components as Connected rows with `removal_key=("__canvas_btn__", tag)`; `_collect_widget_comp_handlers` for Canvas-type widgets scans Image component `canvas_buttons` targeting this canvas and appends them with `removal_key=(comp_id, "__canvas_btn__", tag)`; `_collect_canvas_img_avail` returns Image components with paths as Available entries for Canvas widgets. **canvas_button readonly Events rows** — `_populate_events` appends `kind="readonly"` rows (`mousedown`, `mouseup`, optionally `mouseenter`/`mouseleave`) for each configured canvas_button when the widget is a Canvas. All 41 widget property keys now have entries in `_PROP_HINTS`. |
| `widgets/designer_component_tray.py` | Horizontal 36px chip strip placed below the design canvas — one icon+name chip per `ComponentDescriptor` in `form.components`; click-to-select (blue left accent + `_CHIP_AC` bg); right-click popup → Rename / Delete; empty state label when no components; `refresh(components)` rebuilds chips, `select(comp_id)` / `deselect()` update highlight without firing callbacks; `_RenameDialog` Toplevel for inline renaming; fires `on_select`, `on_deselect`, `on_delete`, `on_rename`. `set_project_dir(path)` stores the project root used for image path resolution. **Image component chips** — `_add_chip` passes `paths` and `project_dir` to `_Chip` for Image type; `_load_chip_thumb(paths, project_dir, size=22)` loads a PIL thumbnail of the first image; `_load_gallery_thumb(path, project_dir, size=80)` loads gallery-size thumbnails. `_Chip` for Image: icon slot uses a `tk.Label` with `image=thumb` instead of glyph text; a `×N` count label is added for multi-image groups; hovering calls `self.after(400, self._show_gallery)` which opens a `tk.Toplevel` gallery above the tray showing all images with key names; `_hide_gallery()` destroys the popup on leave. |
| `widgets/designer_img_button_builder.py` | `ImageButtonBuilder` modal `Toplevel` — opened by `_open_img_button_builder` in `app.py` when the user clicks ⚡ on an Image component's `canvas_button` handler (bypasses the standard `ComponentConnector`). Left column: canvas picker combobox (existing Canvas widgets + `＋ Create New Canvas`), Normal/Hover/Pressed image key comboboxes (populated from the component's `paths` stems; hover and pressed show `(none)` sentinel for optional), X/Y position entries, tag name entry, canvas-drawn auto-size checkbox (checks PIL dimensions of all paths and resizes the target Canvas widget). Right column: live preview `tk.Canvas` that loads actual `PhotoImage`s and responds to `<Button-1>`/`<ButtonRelease-1>`/`<Enter>`/`<Leave>` so you can test all three image states before confirming. Constructor params: `comp_id`, `paths`, `canvas_ids`, `project_dir`, `on_confirm(config_dict)`, `on_create_canvas() → str` (creates a new Canvas widget and returns its id), optional `preset_canvas_id`, optional `edit_config` (pre-fills from existing canvas_button dict). `_commit` creates the canvas (if sentinel is still selected), reads all fields, computes auto-size dimensions via `_get_max_image_size()`, and calls `on_confirm`. `_NONE_KEY = "(none)"` sentinel for optional image keys. |
| `widgets/designer_connector.py` | `ComponentConnector` modal Toplevel — used for both form handlers and component handlers. Left listbox: widgets with events (from `REGISTRY`) **plus** connectable menu items (non-cascade `kind="command"` items at `indent > 0`) when `menu_items` is supplied; right listbox: events for the selected widget, or just `"command"` for menu items; optional primary `options` combobox (e.g. dialog type picker) and optional `secondary_options` combobox (e.g. Populate widget picker); `wire_body_resolver` for live preview; optional `show_title_entry`/`show_extra_entry` with configurable labels for per-handler dialog titles and extra fields; `wire_label` param renames the Wire button (e.g. `"Update"` for the edit dialog); `preselect_widget_id`/`preselect_event_key` pre-select an existing binding (suppresses overwrite warning for same slot); `stub_checker(method_name) → bool` callback suppresses the "already wired" warning when the existing handler body is just `pass`; Wire button calls `on_wire(widget_id, event_key, option)` — caller routes to `widget.events[ev]`, `menu_item.command_handler`, or `form.handler_wires`. |
| `widgets/handler_options_editor.py` | `HandlerOptionsEditor` dark-themed `Toplevel` — pick a named mode for a handler stub or connected-wire body. Two-line rows: bold option name line 1, orange body description line 2 (full canvas width, no truncation). `is_wire=False` edits `form.handler_options[handler_id]` (controls stub body); `is_wire=True` edits `HandlerWire.option` (controls widget-event body). Accepts `override_options`/`override_bodies` to bypass the static HandlerDef lists — used when options are dynamic (e.g. the close-mode picker for `_open_dialog` reads `hdef.secondary_options` and `hdef.edit_bodies`). |

**Designer layout (when active):**
```
┌─────────────┬──────────────────────────┬──────────────────┐
│ Palette     │  [Editor]  [Designer]    │ Properties       │
│ (reuses     │  Canvas (dotted grid)    │ Panel            │
│  explorer   │                          │                  │
│  slot)      │  ┌────────────────────┐  │ Name: btn1       │
│             │  │ Form1              │  │ Text: Click Me   │
│ WIDGETS     │  │  [Click Me]        │  │ Width: 90        │
│ [Button]    │  └────────────────────┘  │ ── Events ──     │
│ [Label] ... │  ⏱ timer1  │ ...       │ Click: [stub ▼]  │
│ COMPONENTS  ├──────────────────────────┤                  │
│ ⏱ Timer    │      Component Tray      │                  │
└─────────────┴──────────────────────────┴──────────────────┘
```

### `menus/`
`menubar.py` — constructs the application menubar. Kept separate from `app.py` for
size management.

### `themes/`
`<theme-id>.json` files parsed by `utils/theme_loader.py`. Each file
holds a `palette` block (UI colors) and a `tokens` block
(category → `{"color": "#hex", "italic": bool}`). Drop a new file
and it appears in the View → Theme menu on next launch — no code
change. Seven themes are bundled: `monokai-bright`, `dark-plus`,
`dracula`, `nord`, `github-light`, `solarized-light`, `dainty`.

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
- Regex-rule syntax highlighting (canvas-rendered, no pygments); **fold markers** — `▼/▶` gutter glyphs; `# ── Name ───` section headers fold to the next section header at the same indent; IDOL codegen markers (`# ── IDOL:BEGIN`, `# ── IDOL:IMPORTS:BEGIN`, etc.) fold their entire BEGIN…END block regardless of indentation; Up/Down arrow skips folded blocks; Ctrl+/ comment toggle; word occurrence highlights on cursor move
- **Multi-cursor** — Alt+Click adds/removes secondary cursors; all `|` carets blink in sync with the primary; edits applied bottom-to-top; secondary selections rendered in `select_bg`; Escape clears; `mc_count()` public helper. Implemented entirely in `canvas_codeview.py` using `_mc_cursors: list[tuple[int,int]]` and `_mc_anchors: list[tuple[int,int]|None]`
- pylsp **hover docs re-wired** for canvas codeview — `<Motion>`/`<Leave>` bound on `cv.canvas` in `_new_tab` and `_new_tab_in`; `_do_hover` uses `cv._coords_from_pixel(mx, my)` instead of `tk.Text.index()`; popup positioned from `cv.canvas.winfo_rootx()`
- **Smart Home key** — first press goes to first non-whitespace; second press goes to column 0 (position-based, no state needed)
- **Center-on-navigate** — outline and references panel navigation centers the target line in the editor
- pylsp LSP integration (hover, diagnostics, definition, completion)
- **Problems panel** — PROBLEMS tab in bottom bar with colored severity dots; click to jump to line/column; hover tooltips with beginner-friendly ruff rule descriptions; Ask AI button + double-click for AI explanation
- **Dual-track error engine** — ruff subprocess + compile() fallback on debounced background thread; three-tier severity: red (error) / yellow (warning) / blue (info/hint); runtime error indicators: amber gutter arrow, line highlight, Problems tab flash
- **Diagnostic statusbar badge** — live ✕N ⚠N count; click to open Problems panel
- **Interpreter statusbar segment** — shows active Python version; click to open interpreter picker popup; selection persists per project root in `~/.idol/settings.json`; venv activation (from terminal toolbar or project wizard) shown as `(.venv) Python x.x.x` and re-activated automatically on next launch
- **Git ahead/behind statusbar** — live `↑N ↓N` badge in statusbar showing unpushed/unpulled commit counts relative to the remote tracking branch
- **Fix Encoding nav pill** — non-ASCII paste into an ASCII file surfaces a yellow pill in the breadcrumb bar offering to re-open the file with UTF-8 encoding; pill dismissed once file is saved with the new encoding
- Sticky scroll; **minimap** — embedded in the canvas editor (not a separate widget), fold-aware (folded lines are hidden in the minimap too), hover zoom preview
- **View → Change Font** — font chooser (family, size, bold/italic) wired to all open canvas tabs; selection persists across restart via `~/.idol/settings.json`
- **Breadcrumb bar** — path crumbs, symbol crumbs, sibling picker, locals drill-down, marquee scroll footer
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
- **Theme system** (`themes/*.json` files loaded by `utils/theme_loader.py`; View → Theme menu; drop a new JSON to add a theme with no code change; seven bundled themes: `monokai-bright`, `dark-plus`, `dracula`, `nord`, `github-light`, `solarized-light`, `dainty`)
- **Clipboard History panel** (`widgets/clipboard_history.py`) — canvas-virtualized ring of the
  last 50 clipboard entries; opened via Ctrl+Shift+H as a persistent hidden `Toplevel`; canvas
  rows (rect + text) with hover via `itemconfigure`, keyboard nav, pin/unpin (right-click), and
  search filter; `on_copy` callback on the canvas editor delivers text directly on Ctrl+C
- **Undo / Redo on the canvas editor** — 200-entry stack on `self.lines` + cursor + selection state; consecutive same-type edits (char insert, backspace, forward-delete) coalesce into one step; all mutation paths push a snapshot (insert, newline, delete, cut, paste, comment toggle, line move/duplicate, indent, unindent); `Ctrl+Z`/`Ctrl+Y` wired as key bindings and `<<Undo>>`/`<<Redo>>` virtual events; Edit menu items dim when stack is empty
- **Shift+Tab unindent** — removes up to `tab_size` leading spaces from the current line or every line in the selection
- **Ghost sash — sidebar** — sidebar's custom Frame-based horizontal sashes use a 2 px `#007acc`
  ghost overlay during drag; actual resize fires on `ButtonRelease` only; also restores the
  missing `<ButtonPress-1>` binding that was never wired to `_sash_press`

## Planned / In Progress

- **GUI Designer — remaining roadmap:** grid layout mode; live preview (run form in subprocess).

---

### Designer — Canvas Item Designer — SHIPPED (2026-06-08)

Inline design surface for placing and configuring tkinter canvas items directly inside a Canvas widget on the designer.

#### Entry / Exit
- **Double-click** a Canvas widget on the design canvas → enters Canvas Item edit mode (same as double-clicking enters code for other widgets, but for Canvas widgets it opens the item editor)
- **Right-click → "Edit Canvas Items"** when a single Canvas widget is selected
- **Escape** exits item edit mode (first Escape de-arms any active placement tool; second Escape exits the mode)
- **Right-click → "Exit Canvas Edit Mode"** from within item edit mode

#### Visual design surface
- The Canvas widget itself becomes the active editing area; surrounding form is dimmed with a `gray25` stipple overlay (4 rectangles around the widget bounds, no transparency tricks)
- Blue `#007acc` 2 px border on the active canvas widget; mode label `"Canvas Items: {id}  (Esc to exit)"` drawn at the top of the overlay
- Canvas items rendered at their stored `(x, y)` relative to the widget's top-left corner; selection highlighted in amber `#e8a844`
- 8 amber resize handles (corners + edge midpoints) when an item is selected; drag-to-resize with optional Shift-snap bypass
- Gray tag-name label shown at the top-left of each item for easy identification

#### Item types supported
`image`, `rectangle`, `oval`, `text`, `line` — added via right-click context menu "Add Item" cascade or by arming a tool and clicking inside the canvas

#### Drag and resize
- Click to select an item; drag selected item to move; drag a handle to resize
- Snap grid honours the existing canvas snap state; Shift bypasses snap (1 px precision)
- Drag state stored in `_ci_drag: dict` — modes `"move"` and one of 8 named handles

#### Properties panel integration
- Selecting a canvas item loads it into the existing Properties/Events tabs via `load_canvas_item(item, canvas_widget_id)` on `DesignerProperties`
- **Properties**: kind (readonly), id (readonly), x, y, width, height, tags (comma-separated string), kind-specific props: `image_path` (image items — file picker copies to `images/`), `fill`/`outline` (rectangle/oval/text — color picker), `text`/`font` (text items), `linewidth` (line items)
- **Events**: `<Button-1>` (mousedown), `<ButtonRelease-1>` (mouseup), `<Enter>` (mouseenter), `<Leave>` (mouseleave), `<B1-Motion>` (drag) — each maps to a method name on the form class
- Image picker (`_open_ci_image_picker`) copies the selected file to `<project>/images/` (conflict-safe `_1/_2` suffix naming) and stores the relative path in `item.props["image_path"]`
- Color picker opens `tkinter.colorchooser` for `fill` / `outline` props

#### Data model
- `CanvasItemDescriptor` dataclass in `designer/model.py` — `id`, `kind`, `x`, `y`, `width`, `height`, `tags: list[str]`, `props: dict[str, Any]`, `bindings: dict[str, str]` (event → method name); `to_dict` / `from_dict` for persistence
- `WidgetDescriptor.canvas_items: list[CanvasItemDescriptor]` — only serialized when non-empty; existing `.form.json` files load without change (backward-compatible)
- `WidgetDescriptor.next_item_id(kind)` auto-numbers new items using kind-based prefixes: `ci_img`, `ci_rect`, `ci_oval`, `ci_text`, `ci_line`

#### Code generation
`_canvas_items_build_lines(form)` in `codegen.py`:
- Iterates all Canvas widgets that have `canvas_items`; emits `create_image/rectangle/oval/text/line()` calls with positional args and props kwargs (fill, outline, text, font, width, tags tuple) at the end of `_build_ui`
- `tag_bind()` calls are **deduplicated** across items sharing a tag — each `(tag, event)` pair emits exactly one `tag_bind` call even if multiple items share the tag
- **Resize scaling (decoupled from bg image).** Items are stored in the canvas's `_ci_orig_w/h` coordinate space (the dimensions captured on first CI-mode entry). Two independent scaling behaviors, neither requiring a background image:
  - *Design-time resize* — initial item coords are **always** pre-scaled `coord * w.width / _ci_orig_w` so a canvas resized in the designer after items were placed renders the items at the matching position/size at runtime (no-op when the canvas hasn't been resized since placement).
  - *Runtime stretch* — when the canvas has a size-changing `anchor` (`_runtime`), `_canvas_items_build_lines` captures each item's iid into `_{canvas}_item_coords` (orig-space coords) and the `<Configure>` handler in `_widget_lines` rescales/repositions every item by `e.width / _ci_orig_w`. The handler is emitted whenever a canvas has items **and** a stretch anchor, independent of `image`; bg-image reload lines (`self._img_*`, `delete("_bg")` + recreate) are gated separately on `_has_bg_img`, and disk-reload of item images only runs for Image-component-backed `image` items. Shapes/lines/images scale by bbox coords; **text font size and line width also scale** by a uniform factor `_s = (_sx * _sy) ** 0.5` (geometric mean) — originals captured in `_{canvas}_item_fonts` (parsed `(family, size, styles)`) and `_{canvas}_item_lws`.
  - *Font emission (all fonts)* — `_parse_font_spec(spec)` splits a `"Family size styles"` string (family may contain spaces) and `_font_tuple_literal(spec)` emits `repr(tuple(...))` so fonts are always emitted as a proper **tuple** (`('Segoe UI', 12, 'bold')`); a bare spaced-family string is parsed by Tk as a list and raises `expected integer`. Used by **both** `create_text` (canvas items) **and** `_prop_str` (every widget `font=` kwarg) — multi-word family fonts (Segoe UI, Times New Roman, …) previously crashed the generated app for all widgets, not just canvas text.

`_canvas_items_handler_methods(form, bodies)`:
- Emits user handler stub methods for every unique method name referenced in `item.bindings`
- Preserves body from `bodies` dict (same extraction mechanism as all other event stubs)

#### `app.py` wiring
- `on_canvas_item_mode=self._on_designer_canvas_item_mode` — called when CI mode is entered (`widget_id`) or exited (`None`); exits CI mode in the properties panel on `None`
- `on_ci_select=self._on_designer_ci_select` — called when an item is selected or deselected; routes to `props_panel.load_canvas_item(item, widget_id)` or `props_panel.clear()`
- `_on_designer_prop_change` handles `widget_id == "__canvas_item__"` by calling `update_canvas_item(ci_item)` to redraw without pushing an undo step

---

### Designer — Image Support & Socket Component — SHIPPED (2026-05-26)

#### Image support (Label, Button, Canvas)

- **`image` prop** on Label, Button, and the new Canvas widget — click the property row to open a file picker; the selected file is copied into `<project>/images/` (conflict-safe `_1/_2` suffix naming); path stored as a forward-slash relative string so generated code is cross-platform
- **Canvas design-time preview** — `_img_cache: dict[str, ImageTk.PhotoImage]` on `DesignerCanvas` keyed by `"{resolved_path}:{w}:{h}"`; `_load_preview_image` uses `Image.resize((w,h), LANCZOS)` to fill widget bounds exactly; Button images inset 2px (`w-4, h-4` at `x+2, y+2`) to match the native raised border; text is hidden when an image is set (WYSIWYG — text is invisible at runtime too); `[img]` badge shown when the file can't be loaded
- **`_project_dir` on both `DesignerCanvas` and `DesignerProperties`** — `set_project_dir(path)` called from `_on_explorer_root_change`; resolves relative image paths against the open project instead of IDOL's own CWD; `DesignerCanvas.set_project_dir` also clears the image cache and redraws
- **PIL warning row** — `_check_pil_async` spawns a daemon thread running `subprocess.run([python, "-c", "import PIL"])`; if Pillow is absent, an amber `warn_link` row is inserted below the `image` row; click calls `on_install_pillow` → `_on_designer_install_pillow` in `app.py` → `PipManager.run_operation(["install", "pillow"], ...)` with streaming output in the Output panel; row removed on success
- **Image codegen** — `_has_images(form)` / `_image_load_lines(form)` emit `import os`, `from PIL import Image, ImageTk`, and `self._img_{id} = ImageTk.PhotoImage(...)` inside the IDOL:BEGIN block; `image` kwarg swapped for `image=self._img_{id}` reference; Canvas widgets get `create_image(0,0,anchor="nw",...)` post-place; `compound` skipped when empty
- **Anchor-aware resize** — widgets with `image` set and a size-changing anchor (`_SIZE_ANCHORS = {"all","top","bottom","left","right"}`) get a `<Configure>` binding that reloads the `PhotoImage` at the new widget dimensions; only the resizing axis uses `event.width`/`event.height`; the fixed axis uses the design-time pixel value

#### Socket non-visual component

- **`Socket` ComponentDef** in `component_registry.py` — icon `⬡`, `default_name="sock"`, `codegen_imports=["import socket","import threading"]`; 11 PropDefs (7 shared + 2 server-only + 2 client-only); 16 ComponentHandlerDefs; new `applies_to_modes: tuple[str,...]` field on `ComponentHandlerDef` gates handlers to "server" or "client" mode
- **Setup dialog** — modal `Toplevel` shown when Socket is dropped from the palette (not after); Server/Client radio + Host/Port fields + 3 scaffold checkboxes; scaffold widget IDs stored as `_scaffold_*` hidden props so codegen can reference them at generation time
- **Scaffold kits:**
  - *Connect/Disconnect* — `btn_connect` (toggle) wired to `_toggle_connect`; `lbl_status` updated by pre-filled `on_connect` / `on_disconnect` bodies
  - *Chat* — `txt_chat` (Text+scrollbar), `ent_message`, `btn_send` wired to `_quick_send`; `on_receive_text` pre-filled to append to txt_chat; `_quick_send` echoes `[You] text` in the log
  - *File Transfer* — `pb_transfer`, `lbl_file`, `btn_send_file` wired to `_pick_and_send_file`; framing protocol activated; `struct` import added; `pb_transfer` updates chunk-by-chunk on send and receive
- **Codegen** — `toggle_connect` handler emits: toggle wrapper + `_start`/`_connect` + `_accept_loop` (server) + `_recvall` (framing) + `_recv_loop` as companion methods in one block; `start`/`connect` are direct-wire alternatives; framing: `struct.pack('>Q',size)` prepended to every send when `_scaffold_pb_transfer` set; `recv_loop` reads 8-byte header then reads payload in chunks updating Progressbar; `conn.settimeout(None)` set after connect so recv blocks indefinitely (prevent 5-second auto-disconnect); all `on_*` callbacks have scaffold-aware pre-filled bodies; `quick_send` and `pick_and_send_file` are registered as `has_connector=False` handler_defs (prevents stub generation, contributes to `comp_methods` exclusion set)
- **Properties panel** — `_comp_connectable_handlers()` applies `applies_to_modes` filtering; `_insert_comp_prop_rows()` skips server-only/client-only props for the wrong mode; `_collect_comp_connections` filters callback stubs by mode

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
- **Tkinter clipboard** — editor copy uses `clipboard_clear()` + `clipboard_append()`; `pyperclip` removed from `requirements.txt`
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

### Designer — CommonDialog Component & Menu Item Wiring — SHIPPED (2026-05-20/2026-05-21)

#### CommonDialog component

- **Handlers** — `_show_open` (askopenfilename), `_show_save` (asksaveasfilename), `_choose_dir` (askdirectory), `_ask_open_file` (read file → populate target widget), `_ask_save_file` (write file from target widget), `_choose_color` (askcolor), `_ask_input` (simpledialog string/integer/float), `_messagebox` (askyesno/askokcancel/askretrycancel/askquestion); all `has_connector=True` with `applies_to_widgets=("Button", "Label")`
- **Callbacks** — `_on_file_selected`, `_on_file_opened` (when no target widget), `_on_color_selected`, `_on_input_result`, `_on_messagebox_result`; `has_connector=False`, appear in Connected Components once any sibling is wired
- **`ask_input` connector** — primary combobox picks type (string/integer/float); stored in `comp.props["ask_input_type"]`
- **`messagebox` connector** — primary combobox picks dialog function; Message entry + Title entry; stored as `comp.props["messagebox_type"/"messagebox_message"/"messagebox_title"]`; info/warning/error types excluded (triggered manually, not from a button click)
- **Per-handler dialog titles** — Title entry in connector for every file/color/input handler; stored in `comp.props[f"{handler_id}_title"]`; emitted as `self._cd1_show_open_title or None` (suppresses blank title)
- **`parent=self`** — all dialog calls pass `parent=self` so focus returns to the originating window, not the main form
- **Selective imports** — `_collect_component_imports()` only emits `from tkinter import filedialog/colorchooser/simpledialog/messagebox` for the handler types that are actually wired
- **File-object handlers** — `_ask_open_file`/`_ask_save_file` connector secondary combobox picks a target Entry/Text/Listbox widget (or `"(none)"`); content read/written automatically; `_on_file_opened` fires when no target
- **… edit button** — wired Connected Component rows show a `…` floating button; opens `ComponentConnector` pre-populated with the existing widget+event; `wire_label="Update"`; old binding cleared if widget or event changes; overwrite warning suppressed for the same slot

#### Menu item wiring

- **Connector shows menu items** — non-cascade `kind="command"` items at `indent > 0` appear at the bottom of the left listbox as `{name}  (MenuItem)`; selecting one shows only `"command"` in the event pane
- **Wire stores method directly** — `item.command_handler` is set to the full component method name (e.g. `_cd1_show_open`); codegen emits `command=self._cd1_show_open` for leaf items when `command_handler` starts with `_`
- **Stub-checker warning suppression** — `stub_checker(method_name) → bool` callback reads the generated `.py` file and checks if the method body is just `pass`; if so the "already wired" overwrite warning is hidden
- **Connected Components panel** — menu item connections displayed as `{item_name}.command`; × to disconnect clears `item.command_handler`; … to edit re-opens connector pre-selecting the menu item

#### Other designer UX (this window)

- **Auto-enter Designer mode** — creating a new GUI project or opening an existing project whose last active form was in Designer mode restores Designer automatically; encoding pill cleared on mode switch
- **Explorer context menu** — right-click a `.form.json` file → "Open in Designer" switches to the designer for that form
- **Delete forms** — `×` button on non-linked form/dialog rows in the Forms panel deletes the form (with confirmation); linked dialogs still show `×` as "Unlink"
- **Canvas editor** — Tab with active selection indents all selected lines (adds `tab_size` spaces to each line's start, adjusts cursor + anchor); right-click preserves the current selection; member autocomplete Shift-dismiss fixed; `on_bad_paste` hook detects non-ASCII paste characters
- **Terminal** — live-buffer reflow on column resize (VS Code style): expands/wraps all existing lines when the terminal column width changes, keeping visible content in sync with the pyte screen buffer

---

### Designer — Handlers System & Components Panel (2026-05-16 / 2026-05-18)

#### Components Panel (Timer) — SHIPPED (2026-05-16)

- **Component tray** — horizontal 36px chip strip below canvas; one chip per `ComponentDescriptor`; right-click → Rename / Delete; empty-state label when no components
- **Palette COMPONENTS section** — click-to-add; one row per `COMPONENT_REGISTRY` entry
- **Timer component** — `self.after()` periodic callback (no threading); props: Interval (ms), Enabled; handlers: `_tick` (always wired to form init), `_start` (⚡ connectable), `_stop` (⚡ connectable)
- **Component mode in Properties panel** — selecting a tray chip hides Events + Order tabs, shows PropDef rows and ComponentHandlerDef rows; ⚡ button fires `on_component_connect`
- **Component codegen** — `IDOL:COMPONENTS:BEGIN/END` block inside second `IDOL:BEGIN` block initializes state variables and starts enabled timers; component handler methods emitted after widget event stubs; bodies preserved across regen by existing `extract_event_bodies()` mechanism
- **Wiring storage** — `widget.events[event_key] = "_comp_id_handler_label"` (same slot as all other event wiring; codegen/persistence handle it automatically)

#### Handlers Tab Redesign — SHIPPED (2026-05-18)

- **Available / Connected split** — no checkboxes; Available shows unwired/disabled handlers, Connected shows wired/enabled handlers with target label; sections driven entirely by `HANDLER_CATALOG`
- **⚡ button (Available)** — connectable handlers open `ComponentConnector` to pick widget + event; non-connectable handlers enable immediately
- **× button (Connected)** — disconnects a wire or disables the handler
- **… button (Connected)** — opens `HandlerOptionsEditor` for handlers with `options` or `secondary_options` (e.g. change close mode on a wired `_open_dialog` row)
- **`HandlerOptionsEditor`** (`widgets/handler_options_editor.py`) — two-line rows (bold option name + orange description below); `is_wire` flag controls whether it edits `form.handler_options` or `HandlerWire.option`; `override_options`/`override_bodies` for dynamic option lists
- **Widget-selected mode** — only connectable handlers compatible with the widget type shown in Available; Connected shows only wires targeting this specific widget; `multi_wire` handlers stay in Available after wiring
- **Available Components sub-section** — foldable (▶/▼ header, collapsed by default); shows **all** connectable component handlers regardless of whether already wired (handlers are reusable); ⚡ button opens `ComponentConnector`; floating buttons corrected for canvas scroll offset; present in both widget-selected and form-selected views
- **`_open_dialog` handler** — `generates_stub=False` (no standalone method emitted); `multi_wire=True` (stays in Available for multiple targets); `dynamic_wire_body="self._open_{option}()"` resolves dialog name at wire time; two-dropdown connector (Dialog + Mode); wiring auto-updates the linked dialog's `_on_close` handler_option
- **`_on_close` / `_on_escape` options** — renamed to `"hide (withdraw)"` / `"destroy (exit)"` with backward-compat prefix matching via `_resolve_option()`
- **Single source of truth** — `HandlerDef` fields drive all behavior; `connector_options_source`, `edit_bodies`, and `wire_side_effects` eliminate all handler-specific `if handler_id ==` branches from `app.py`; adding a new handler requires only a `HandlerDef` entry in `handlers.py`

---

### Designer — Session, Set as Main & FORMS Improvements — SHIPPED (2026-05-25)

- **Set as Main** — right-click or double-click a main form row in the FORMS panel to designate it as the entry point; writes `main.py` with a `# Generated by IDOL Designer` marker, pins the file as the ▶ run entry in the statusbar, and shows **▶ FormName** in teal in the FORMS panel header; `_designer_main_form` persisted in session
- **▶ indicator sync** — `_effective_designer_main()` in `app.py` computes the display form from the active run entry (detected via IDOL marker + `from X import X` regex, or direct stem match), active tab in Active Tab mode, and `_designer_main_form` as fallback; `_set_run_entry` and `_on_tab_changed` both trigger a form list refresh; designer re-entry also refreshes when no entry is pinned
- **Session persistence** — designer state saved/restored across restarts: `designer_was_active`, `designer_form_names`, `designer_main_form` in `session.json`; `_enter_designer_mode` always sets `_designer_project_type = "gui"`; `designer_close_form` clears `_designer_form_names`, `_designer_missing_dialogs`, `_designer_main_form` on teardown; session restore gates form-name restore + `_enter_designer_mode` call behind `designer_was_active = True`
- **Auto-load linked dialogs** — `_open_form_json_in_designer` and the Explorer "Open in Designer" path both scan the source directory for linked dialog `.form.json` files and copy + load them alongside the parent form; overwrite prompt when a file already exists in CWD
- **Open .py on form load** — switching to a form in the designer opens the companion `.py` as an editor tab; prefers the CWD copy over the source directory
- **Missing forms shown in red** — session-restored form names that can no longer be found on disk render red in the FORMS tree with a tooltip; tracked in `_designer_missing_dialogs`; removable via right-click
- **FORMS tree X behavior** — X on a main form row removes it (and linked dialogs) from the designer with a confirmation prompt; X on a linked dialog row unlinks it first; canvas clears (`delete("all")`) when the last form is removed
- **Wizard creates GUI project → ▶ indicator** — `_on_project_created` sets `_designer_main_form` so the ▶ indicator appears immediately after wizard completion; project_wizard.py adds the `# Generated by IDOL Designer` marker to the generated `main.py`

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
