# IDOL — Claude Code Project Brief

## What IDOL Is

IDOL (Integrated Development and Objective Learning) is a Python/Tkinter desktop IDE
built for Python development. It is a full-featured IDE: multi-tab editing, syntax
highlighting, LSP integration (pylsp), Git tooling, integrated PTY terminal, AI chat
panel (Ollama/qwen2.5-coder:7b), pip package manager, learning mode, command palette,
and session persistence. It runs on Windows, macOS, and Linux.

GitHub: `celltoolz/idol-ide`
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
main.py                → can import app.py only
app.py                 → can import anything
widgets/               → can import from editor/, utils/ — NEVER the reverse
widgets/canvas_editor/ → mixins import canvas_editor/constants.py only — never
                         canvas_codeview.py, never each other. Shared fold
                         vocabulary (the marker regexes + the iter_visible
                         walk) lives in constants.py, so no exception is
                         needed — every fold-aware module imports it from the
                         leaf
editor/                → can import from utils/ — NO widget imports, NO subprocess in utils/
utils/                 → NO widget imports, NO subprocess calls, NO editor/ imports
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

Key widgets: `ai_chat_panel.py`, `bottom_panel.py`, `breadcrumb_bar.py`,
`canvas_codeview.py` (+ the `canvas_editor/` mixin package, below), `clipboard_history.py`,
`command_palette.py`, `completion_popup.py`, `debug_panel.py`,
`explorer.py`, `find_replace.py`, `guide_window.py`, `learning_manager.py`,
`learning_panel.py`, `notebook.py`, `outline.py`,
`output.py`, `package_manager.py`, `problems_panel.py`, `project_wizard.py`, `references.py`,
`scrollbar.py`, `sidebar.py`, `source_control.py`, `statusbar.py`, `styled_checkbox.py`,
`terminal.py`, `welcome.py`

Designer-side widgets (the UI layer of `designer/`, documented in the designer table below):
`designer_palette.py`, `designer_properties.py`, `designer_connector.py`,
`designer_component_tray.py`, `designer_img_button_builder.py`, `form_list_panel.py`,
`handler_options_editor.py`

`canvas_codeview.py` — IDOL's sole editor engine (`CanvasCodeView`). Renders text directly on a `tk.Canvas` (no `tk.Text` widget, no pygments). All state lives in `self.lines: list[str]`; cursor + selection are plain `(line, col)` tuples. Themes are loaded from `themes/*.json` via `utils/theme_loader.py` — swap by calling `set_theme(id)`. The internal layout grids in: breadcrumb (row 0), find/replace strip (row 1, reserved), main `tk.Canvas` (row 2 col 0) + `VerticalScrollbar` (row 2 col 1), `HorizontalScrollbar` (row 3 col 0). Embedded inside the canvas: line-number / fold / breakpoint gutter, sticky scope-header band (own canvas, place'd at top), and the minimap. Public API: `get_text/set_text`, `get_line/line_count`, `get_cursor/set_cursor`, `get_selection/set_selection/clear_selection/selected_text`, `insert/delete_selection/delete_range/replace_range`, `scroll_to_line/ensure_visible/visible_range`, `fold_all/unfold_all`, `set_diagnostics/set_breakpoints/set_git_hunks/set_runtime_error_line/set_debug_line/set_filepath/set_theme`. Host hooks: `on_change`, `on_cursor_move`, `on_lines_changed`, `on_copy`, `on_completion_request`, `on_breakpoint_toggle`, and the `on_request_*` family used by the right-click menu. What remains in this file: rendering/paint, scrolling, the sticky scope band, primary-cursor editing + undo/redo, selection, and input bindings (including the gutter-zone click/motion hit-testing — only the gutter *drawing* moved). Tokenization, folding, the gutter, multi-cursor, bracket/quote match highlighting, the minimap, and autocomplete are mixins in `widgets/canvas_editor/` (below).

#### `widgets/canvas_editor/` — editor mixin package

`CanvasCodeView` is decomposed into seven single-responsibility mixins (the P3
decomposition, plus the Gutter Pass A extraction):

```python
class CanvasCodeView(TokenizerMixin, FoldMixin, GutterMixin, MultiCursorMixin,
                     BracketMatcherMixin, MinimapMixin, AutocompleteMixin,
                     tk.Frame):
```

All editor state is **host-owned**: every attribute a mixin touches is initialized in
`CanvasCodeView._init_state`. Mixins operate on the host instance (`self.lines`,
`self.cur_line`, …) and keep no parallel state of their own. Only `canvas_codeview.py`
imports from this package.

| File | Role |
|---|---|
| `constants.py` | Shared editing constants — auto-pair table (`_PAIRS`, `_CLOSERS`), bracket-match sets (`_BRACKET_OPEN_TO_CLOSE`, `_BRACKET_CLOSE_TO_OPEN`, `_ALL_BRACKETS`), quote sets (`_QUOTES`, `_MATCH_CHARS`), editor font (`_FONT_FAMILY`, `_FONT_SIZE`), minimap width (`_MINIMAP_W`), the gutter palette (`_BREAKPOINT_COLOR`, `_BREAKPOINT_GHOST_COLOR`, `_GIT_HUNK_COLORS`), and the shared fold vocabulary — the marker regexes (`_SECTION_MARKER`, `_IDOL_BEGIN_RE`, `_IDOL_END_RE`) plus the `iter_visible(lines, folded)` generator (the single source of truth for the fold-skip walk; `FoldMixin._visual_row_of`/`_visual_to_physical`/`_visual_row_count` are thin adapters over it). Imports nothing internal — the safe leaf every module can import with no circular-import risk. |
| `tokenizer.py` | `TokenizerMixin` — regex-rule syntax highlighting: the `PYTHON_RULES` table, comment/string scanners, per-line triple-quote state scan. Pure logic; reads `self.language` to pick the diff vs. python path. |
| `fold.py` | `FoldMixin` — block folding + fold-aware coordinate mapping. Public fold API (`fold_all`, `unfold_all`) so the host never pokes `self.folded` directly. The visual↔physical helpers (`_visual_to_physical`, `_visual_row_count`, `_visual_row_of`) are thin adapters over `constants.iter_visible`; the fold-marker regexes they use now live in `constants.py` too (imported back here, and by `minimap.py` / `canvas_codeview.py`). |
| `gutter.py` | `GutterMixin` — the left gutter's layout + drawing. `_compute_gutter()` sets the font-aware column geometry (`_debug_w`, `_linenum_r`, `_fold_x`, `_gutter_w`, `_text_x`); `_draw_gutter_background()` paints the full-height column once per render; `_draw_gutter_row()` paints per-row content (overlay mask → git stripe → breakpoint dot → line number → fold marker), called after tokens so it overpaints horizontally-scrolled glyphs; `_draw_gutter_number()` is the shared line-number helper reused by the sticky-scroll band. Reads host state + the gutter palette from `constants.py`; calls the host's `_line_is_foldable` (FoldMixin). Gutter *click/motion* hit-testing stays in `canvas_codeview.py`'s mouse handlers — only drawing moved. |
| `multicursor.py` | `MultiCursorMixin` — Alt+Click secondary cursors; mirrors the primary editing ops (insert / delete / newline / tab / bracket-pair / move) onto every secondary cursor, applied bottom-to-top. State (`_mc_cursors: list[tuple[int,int]]`, `_mc_anchors: list[tuple[int,int]|None]`) is host-owned; `mc_count()` public helper. |
| `bracket_matcher.py` | `BracketMatcherMixin` — bracket + quote match highlighting. Brackets matched by a directional depth scan; quotes by a same-line parity scan (opener == closer defeats depth counting). Pure: reads only `self.lines` / `cur_line` / `cur_col` and the constants; render calls `_find_bracket_pair()` once per paint and outlines the returned pair. |
| `minimap.py` | `MinimapMixin` — embedded `tk.Text` minimap at font size 1, `place()`'d on the right edge; fold-aware (folded lines hidden in the minimap too); token tags mirrored from the active theme; hover zoom preview. |
| `autocomplete.py` | `AutocompleteMixin` — completion popup (lazily created `Toplevel` + `Listbox`; `render()` never touches it). Items come from the host's `on_completion_request` hook (LSP, wired by app.py) when set, else the synchronous buffer-word fallback (`_buffer_word_items`); an `_ac_seq` sequence number guards against stale async responses. |

Import rules for this package are in the strict-import-rule block above: mixins import
`constants.py` only. The shared fold vocabulary (marker regexes + `iter_visible`) lives
in `constants.py`, so there is no longer a cross-mixin import exception.

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
| `model.py` | `WidgetDescriptor`, `VariableBinding`, `MenuItemDescriptor`, `HandlerWire`, `ComponentDescriptor`, `CanvasItemDescriptor`, and `FormModel` dataclasses — the canonical source of truth for every form. `FormModel` tracks name, title, size, `border_style`, `maximize_box`, `always_on_top`, `bg`, `image` (relative path to background image, `""` = none — serialized only when non-empty for backward compat), `form_type` ("main"/"dialog"), widget list, `menu_items` list, `linked_dialogs` list, `components` list (non-visual component tray), `handler_wires` list (explicit handler→widget-event wires), and `handler_options` dict ({handler_id: option_name} for mode choices like "hide (withdraw)"/"destroy (exit)"). `VariableBinding` holds the tkinter variable (StringVar/IntVar/DoubleVar/BooleanVar) bound to a widget. `MenuItemDescriptor` holds caption, name, indent (0 = top-level cascade, 1+ = item/submenu), enabled, visible, shortcut, `kind` ("command"/"checkbutton"/"radiobutton"), `variable` (tk variable name), `value` (radiobutton value string), and `command_handler` — for check/radio items: the handler name whose `_{name}_click` stub is called; for leaf command items: either empty (uses auto-generated `_{item.name}_click`) or a full method name starting with `_` (e.g. `_cd1_show_open`) when a component handler is wired directly. `get_menu_item(name)` looks up a `MenuItemDescriptor` by name. `HandlerWire` holds `handler_id`, `widget_id`, `event_key`, and `option` (e.g. "Dialog1:hide (withdraw)") — one record per handler→widget-event connection. `ComponentDescriptor` holds `id` (auto-numbered name, e.g. "timer1"), `type` (registry key), and `props` dict. **`CanvasItemDescriptor`** holds `id` (e.g. `"ci_img1"`), `kind` (`"image"/"rectangle"/"oval"/"text"/"line"`), `x`, `y`, `width`, `height`, `tags: list[str]`, `props: dict` (kind-specific: `image_path`, `fill`, `outline`, `text`, `font`, `linewidth`), `bindings: dict[str, str]` (tk event → method name), `binding_tags: dict[str, str]` (tk event → the specific tag used for that event's `tag_bind`, since bindings are tag-scoped), and `binding_handlers: dict[str, dict]` (tk event → `{handler_id, option}` when the binding's method body comes from a `HANDLER_CATALOG` entry, e.g. `_open_dialog`, rather than a blank stub — wired via `designer_ci_connector.py`); the latter three serialized only when non-empty; `to_dict`/`from_dict` for JSON persistence. `WidgetDescriptor.canvas_items: list[CanvasItemDescriptor]` — only serialized when non-empty so existing form files load unchanged. `WidgetDescriptor.next_item_id(kind)` auto-numbers items with kind prefixes: `ci_img`, `ci_rect`, `ci_oval`, `ci_text`, `ci_line`. |
| `registry.py` | `REGISTRY` dict — one entry per widget type: tk class, default size, default props, available events, `color_props`, `is_container`, `is_notebook`, `variable_prop`/`variable_types`, and a mini-preview drawing function. **Canvas widget** added as a 16th type (`tk.Canvas`, 200×150, `bg` + `image` + `sizing` props, `_SIMPLE_EVENTS + _KEY_EVENTS` — full standard event set). **Treeview widget** added as a 17th type (`ttk.Treeview`, `show`/`selectmode`/`scrollbar` + structural `columns`/`rows`/`tree_heading` props, `treeselect`/`treeopen`/`treeclose` events); `columns` are structured `list[dict]` (id/heading/width/anchor/stretch) and `rows` are `list[dict]` ({text, values}) — both normalized via `normalize_tree_columns`/`normalize_tree_rows` (legacy plain-string columns auto-migrate). **Label and Button** gained `image` (file path, relative to project) and `compound` props; `_load_preview_image` renders PIL thumbnails on the design canvas using `Image.resize` (fills bounds exactly, matching runtime); button images inset 2px to match the native raised border. Non-input widgets default `"bg": ""` (OS default); input widgets default `"bg": "#FFFFFF"`. |
| `codegen.py` | `FormModel → Python` — generates a class-based source file. **Image codegen** — `_has_images(form)` / `_image_load_lines(form)` emit `import os`, `from PIL import Image, ImageTk`, and `self._img_{id} = ImageTk.PhotoImage(Image.open(...).resize((w,h), LANCZOS))` inside the IDOL:BEGIN block; `image` kwarg in `_widget_lines` is replaced with `image=self._img_{id}` (Canvas gets `create_image()` post-place instead); size-changing anchors (`_SIZE_ANCHORS`) trigger a `<Configure>` binding that reloads the PhotoImage at the new widget size; `import struct` added when the Socket File Transfer scaffold is active. **Socket component codegen** — `_comp_init_for` emits server (host/port/encoding/timeout/max_clients/buffer_size/server/clients/running) or client (+ retry props, conn) state; `_comp_handler_method` for Socket: `toggle_connect` emits the toggle wrapper + `_start`/`_connect` + `_accept_loop` (server) + `_recvall` (framing) + `_recv_loop` as companion methods in one block; `start`/`connect` are direct-wire alternatives; `send_text`/`send_file` use `struct.pack('>Q', size)` framing when `_scaffold_pb_transfer` is set; `recv_loop` reads the 8-byte header and reads payload with chunk-by-chunk Progressbar updates; pre-filled scaffold bodies for `on_connect`, `on_disconnect`, `on_receive_text`, `on_receive_file`, `on_send_file`, `on_timeout`, `on_error` when the corresponding scaffold widget IDs are stored in `comp.props`; `quick_send` and `pick_and_send_file` have their own handler cases and are excluded from widget-event stub generation via `comp_methods`. | Two `IDOL:BEGIN/END` marker pairs in `__init__` delimit user-owned zones (pre-build and post-build) that survive regeneration. `IDOL:IMPORTS:BEGIN/END` markers preserve user-added imports. Preserves event bodies, helper methods, and user `__init__` code. Handles `validatecommand`/`invalidcommand` as `(self.register(self.method), args...)`. Skips empty/default props. `_menu_lines()` emits `tk.Menu` hierarchy including `add_checkbutton`/`add_radiobutton` for check/radio items; leaf command items: if `item.command_handler` starts with `_` (component handler wired directly) emits `command=self.{command_handler}`, otherwise emits `command=self._{name}_click`; `_menu_command_methods()` harvests leaf item names so `_collect_methods()` stubs them automatically; `_menu_variable_decls()` emits `BooleanVar`/`StringVar` declarations for menu variables; `_menu_bind_lines()` emits `self.bind("<shortcut>", handler)` for every leaf item that has both a shortcut and a handler. `command` event key generates `command=self.method` constructor kwarg (not `.bind()`) for applicable widget types. Children store coords relative to parent content area; codegen uses `self.parent_id` as the parent arg and skips y-offset for children. Notebook children emitted inside `ttk.Notebook.add()` calls grouped by tab. **Component init block** — `_component_init_lines()` emits an `IDOL:COMPONENTS:BEGIN/END` block inside the second `IDOL:BEGIN` block (after `_build_ui()`) that initializes each component's state variables and starts enabled timers. **CommonDialog init** — emits per-handler title vars (`self._cd1_show_open_title = ""` etc.), `messagebox_type`, and `messagebox_message` vars; no global `_title` var. **Component handler methods** — `_component_handler_lines()` emits handler methods after widget event stubs; only handlers that are actually wired (or whose callbacks are reachable) are emitted; bodies preserved across regen by `extract_event_bodies()`. **Selective imports** — `_collect_component_imports()` checks which CommonDialog handler IDs are actually wired before adding `from tkinter import filedialog/colorchooser/simpledialog/messagebox`. **`parent=self`** — all dialog calls (`askopenfilename`, `askcolor`, `simpledialog.*`, `messagebox.*`) receive `parent=self` so focus returns to the correct window. **Debounced auto-generation** — any canvas or property change schedules a codegen run 1.5 s later; the timer resets on each change so rapid edits coalesce into a single run. **Image component codegen** — `_has_images(form)` also checks Image components; `_image_comp_init_lines(form)` emits Image component init (single `ImageTk.PhotoImage` or keyed dict) **before** `_build_ui()` in the second IDOL:BEGIN block so `create_image()` calls in `_build_ui` can reference them; `_component_init_lines` skips Image type (already emitted). **Canvas button codegen** — `_canvas_button_build_lines(form)` emits `create_image + tag_bind` calls at the end of `_build_ui`; `_canvas_button_handler_methods(form, bodies)` emits `_down/_up/_enter/_leave` generated methods plus a `_click` user stub; `_img_ref(comp_id, key)` returns `self.name` (single) or `self.name["key"]` (multi). **Form background image** — `form.image` path emitted as a `tk.Label(self, image=..., bd=0).place(x=0, y=0)` at the top of `_build_ui`; PIL import triggered via `_has_images`. **Canvas item tag_bind codegen** — `_canvas_item_bind_lines(form)` iterates all `WidgetDescriptor.canvas_items`, deduplicates bindings by `(tag, event)` across items sharing a tag, and emits `self.{widget_id}.tag_bind(tag, event, self.method)` calls at the end of `_build_ui`; `_canvas_items_handler_methods(form, bodies)` collects all unique method names from item bindings and emits the method bodies — when an item's `binding_handlers` maps an event to a catalog handler (e.g. `_open_dialog`) the handler's `wire_body_for(option)` is injected as the default body (saved/user-edited bodies still win), otherwise a blank `pass` stub; all preserved across regen. **Treeview codegen** — structural props `columns`/`rows`/`tree_heading` are excluded from the constructor kwargs (alongside `scrollbar`/`tabs`); the `columns=(…)` kwarg carries only column *ids*, and per-column `heading()`/`column()` calls plus per-row `insert()` calls are emitted after `place()`. |
| `persistence.py` | `.form.json` save/load with SHA-256 checksum for manual-edit detection; `extract_event_bodies`, `extract_init_user_zones`, `extract_helper_methods`, `extract_user_imports` — AST + marker-based extraction used during regeneration to splice user code back in. `IDOL:COMPONENTS:BEGIN/END` marker constants defined here (used by `codegen.py` for the component init block inside the second IDOL:BEGIN block). |
| `handlers.py` | `HANDLER_CATALOG` — list of frozen `HandlerDef` dataclasses defining every method IDOL can generate for a form. `handlers_for(form_type)` and `default_enabled_for(form_type)` helpers. Each `HandlerDef` declares: `id`, `label`, `description`, `applies_to` ("main"/"dialog"), `default_checked`, `wiring` (line emitted in `__init__`), `params`, `default_body`, plus optional fields: `connectable` (shows ⚡ button in Handlers tab), `always_wired` (always in Connected section, not removable), `display_target` (built-in event shown as wire target), `options`/`stub_option_bodies`/`wire_option_bodies` (named mode variants), `applies_to_widgets` (restrict ⚡ to specific widget types), `generates_stub` (`False` = wire body goes directly into the widget event method, no standalone `def`), `dynamic_wire_body` (template with `{option}` placeholder for runtime-resolved targets like dialog names), `multi_wire` (stays in Available after wiring — can connect to multiple targets), `secondary_options` (mode choices shown in … editor on Connected rows), `connector_options_source` (`"linked_dialogs"` = pull primary connector options from `form.linked_dialogs` at connect time instead of using the static `options` list), `edit_bodies` (descriptions shown in `HandlerOptionsEditor` alongside `secondary_options` rows), `wire_side_effects` (`"sync_dialog_close_mode"` = update linked dialog's `_on_close` handler_option when wired or mode-changed — dispatched by `_apply_wire_side_effects()` in `app.py`). **Adding a new handler requires only a `HandlerDef` entry here — no `app.py` changes needed.** |
| `component_registry.py` | `PropDef`, `ComponentHandlerDef`, `ComponentDef` frozen dataclasses + `COMPONENT_REGISTRY` dict — defines every non-visual component type: its icon, palette label, `codegen_imports` list (extra import lines emitted when any handler is wired), PropDef rows (key, label, kind, default, description), and `ComponentHandlerDef` entries (`id`, `label`, `description`, `has_connector` for ⚡ wiring, `default_body`, `applies_to_widgets` allowlist, `applies_to_modes` allowlist for socket server/client gating). Ships **Timer** (`self.after()`, no imports), **CommonDialog** (open/save file, choose dir, color picker, simple input dialog, messagebox — imports emitted selectively), **Socket** (TCP server/client; `import socket, threading` always emitted; `import struct` added when File Transfer scaffold active), and **Image** (named image references; `codegen_imports=[]` — PIL import handled by `_has_images` in codegen; one `PropDef` with `kind="image_list"` for multi-file picking; one `PropDef` with `kind="canvas_ref"` for the `parent` property — dropdown shows `None`, `Global`, and all Canvas widget IDs on the form; `canvas_button` handler with `has_connector=True` and `applies_to_widgets=("Canvas",)` — clicking ⚡ opens `ImageButtonBuilder` instead of the standard `ComponentConnector`). Prop `kind` values: `"int"`, `"bool"`, `"str"`, `"readonly"`, `"float"`, `"image_list"`, `"canvas_ref"`. Helpers: `all_component_types()`, `get_component_def(type_key)`, `default_props(type_key)`. |
| `canvas.py` | Dotted-grid drag/drop surface — canvas-primitive widget rendering (bg/fg from props applied live), click-to-select, drag-to-move, resize handles, multi-select rubber band, copy/paste with cascade-offset drift reset, **arrow-key nudge (8 px by grid, Shift+arrow 1 px fine nudge)**, bring-to-front/send-to-back, z-order preservation on every mutation. **Image preview** — `_img_cache: dict[str, ImageTk.PhotoImage]` keyed by `"{path}:{w}:{h}"` prevents GC and avoids re-loading on repaint; `_load_preview_image` uses `Image.resize((w,h), LANCZOS)` to fill the widget bounds exactly; `_project_dir` (updated via `set_project_dir(path)`) resolves relative image paths against the open project, not IDOL's own CWD; `set_project_dir` also clears the cache and redraws. **Shift+snap bypass** — holding Shift during move, resize, form resize, or widget draw disables snap (1px precision); snap toolbar button dims immediately on Shift key-down and restores on key-up via `on_snap_state_changed` callback. **Titlebar click** — clicking the form title bar tag selects the form and shows its resize handles (previously, "titlebar" was incorrectly in the `_topmost_at` skip list). **Widget containment**: Frame/LabelFrame/Notebook act as parent containers; widgets dragged or drawn onto them are auto-parented (coords stored relative to container content area); `_abs_xy()` converts to absolute canvas coords for rendering; drag-out releases parent on drop; children clamped to container bounds on drop. **Pointer cursor** — while a palette tool is armed, hovering over an existing widget shows an arrow cursor (click selects and de-arms, not places). Fires `on_structure_changed` on add/remove/reorder. Fires `on_double_click(widget_id)` on double-click. Renders live menu bar strip below title bar from `form.menu_items`; clicking a top-level menu shows a native `tk.Menu` dropdown; clicking a command leaf or check/radio item with a `command_handler` fires `on_menu_navigate(method_name)`. Resize handles and rubber-band selection use `canvasx`/`canvasy` to account for scroll offset. **Linux mousewheel** — `<Button-4>`/`<Button-5>` events bound alongside `<MouseWheel>` for X11 vertical scroll; `<Shift-Button-4>`/`<Shift-Button-5>` for horizontal scroll. **Grid visibility** — `_grid_visible` module-level flag toggled by `toggle_grid()` / `grid_visible` property; toolbar ⋯ button; `_draw_form` skips dot grid when False. **canvas_button ghost preview** — `_draw_canvas_btn_ghosts(w, wx, wy, tag)` called from `_render_widget` for Canvas-type widgets; scans `form.components` for Image components with `canvas_buttons` targeting this widget; loads normal-state image via `_load_natural_image` and renders it at the configured (x, y) with a dim tag-name label, all tagged with the widget's canvas tag so it is cleaned up with the widget. `_load_natural_image(canvas, rel_path)` — like `_load_preview_image` but no resize; cache key prefixed `"natural:"`. **Widget deletion cleanup** — `_disconnect_widget(wid)` called in `remove_selected`/`remove_widgets` before each widget is removed; strips `canvas_buttons` entries from Image components where `canvas_id==wid`, removes `handler_wires` targeting that widget, and then disables any catalog handler left with no remaining wire (drops it from `enabled_handlers` + `handler_options`, mirroring the Handlers-tab disconnect) so it doesn't linger in the Connected section after its only target is deleted. **Designer focus** — `_enter_designer_mode` calls `focus_set()` on the canvas at the end so Delete/arrows/Ctrl+Z go to the canvas without requiring a click. **Canvas Item edit mode** — `enter_canvas_item_mode(widget_id)` / `exit_canvas_item_mode()` switch `_ci_mode`; all mouse events dispatch to `_ci_on_click` / `_ci_on_motion` / `_ci_on_release` while active; double-click on a Canvas widget enters CI mode; `_ci_redraw()` replaces normal `_redraw()` in CI mode — draws the form, all widgets, the dimmed overlay (`gray25` stippled rects + blue border), then calls `_ci_draw_items()` + `_ci_draw_handles()` for the selected item; `arm_item_tool(kind)` enters placement mode (cursor changes to `crosshair`); clicking places a new `CanvasItemDescriptor` via `add_canvas_item()`; `remove_canvas_item(item_id)` deletes the selected item; `update_canvas_item(item)` re-renders after an external property change; `get_ci_widget()` / `get_ci_selected()` helpers; `ci_mode` / `ci_widget_id` / `ci_selected_id` read-only properties; Escape first de-arms the placement tool, second press exits CI mode; right-click context menu in CI mode shows "Add Item" cascade (5 item types), "Delete Item", "Exit Canvas Edit Mode"; right-click on Canvas widget in normal mode prepends "Edit Canvas Items"; fires `on_canvas_item_mode(widget_id | None)` and `on_ci_select(item | None)` callbacks. `set_tool_size(w, h)` — sets the default placement size used when arming a CI item tool (called by the IMAGES panel to pass actual PIL dimensions before auto-placing a CanvasImage). `remove_widgets(ids)` — removes a list of widget IDs from the form in a single operation (used by CI cleanup when syncing Image component paths). |
| `menu_editor.py` | VB6-style Menu Editor `Toplevel` dialog — Caption/Name/Shortcut fields, Enabled/Visible checkboxes, Type combobox (Command/Checkbutton/Radiobutton), Variable picker (`VariablePickerEntry`), Command and Value fields, ← → ↑ ↓ arrow buttons (promote/demote/reorder), Insert/Delete/Next actions, indented listbox preview, hover hint bar (3-line, below OK/Cancel), OK/Cancel, ? guide. Accepts optional `form` arg so the variable picker can show all form-level variables. Works on a deep copy; calls `on_save(items)` only on OK. |
| `var_picker.py` | `collect_form_variables(form)` — gathers all variable names+types from widget `VariableBinding`s then menu check/radiobutton items in definition order, deduped. `show_variable_popup(anchor, variables, on_select, entry_ref)` — dark-themed `Toplevel` listing variables as `name (VarType)` rows; live-filters as the user types in `entry_ref`; refocuses entry after render; dismisses on outside click but keeps alive on anchor/entry clicks. `VariablePickerEntry` — reusable `Entry + ▾ button` widget that opens the popup on button click. Used by both the properties panel (inline treeview editor for `var__name` row) and the menu editor Variable field. |
| `toolbar.py` | Alignment/distribute/size/snap toolbar strip rendered above the design canvas — purely a UI widget |
| `widgets/designer_palette.py` | Widget toolbox panel — scrollable list of widget types with canvas-drawn mini-previews; click-to-place; **COMPONENTS section** below widgets list (one row per `COMPONENT_REGISTRY` entry, icon glyph + label, click fires `on_component_add(type_key)`, no drag); lives in `widgets/` because it is a `tk.Frame` subclass |
| `widgets/designer_properties.py` | Property grid + Events + Handlers + Order tabs — **canvas-rendered Properties, Events, and Order tabs**; **image picker** (`_open_image_picker`) copies the selected file into `<project>/images/`, updates the prop, triggers `_check_pil_async` (subprocess check on daemon thread), and inserts an amber `warn_link` kind row "⚠ click to install Pillow" below the image row when Pillow is absent — clicking it calls `on_install_pillow` which runs pip via `PipManager`; `set_active_python` / `set_project_dir` reset the PIL check and image path resolution respectively. **Socket mode filtering** — `_comp_connectable_handlers()` replaces all inline `has_connector` filter expressions and additionally applies `applies_to_modes` so server-only handlers (start) are hidden for client sockets and vice versa; `_insert_comp_prop_rows()` skips `_SOCKET_SERVER_ONLY` / `_SOCKET_CLIENT_ONLY` props for the wrong mode; `_collect_comp_connections` also filters callbacks by `applies_to_modes`. with a custom dark scrollbar (no `ttk.Treeview`; rows are canvas primitives, zero widget teardown on refresh). Inline text editor for most props; **inline overlay dropdown** for enum props (`tk.Frame` overlay, item width sized to content, per-item hover hints in status bar for all prop options); color swatch + `tkinter.colorchooser` for color props; state dropdown with conditional state-color rows; validate dropdown with `--vcmd`/`--args`/`--ivcmd` rows (hovering a substitution code in the `--args` dropdown shows its meaning in the hint bar); **inline list editor** for array-type props (e.g. Combobox `values`): floating panel with item rows + `×` remove buttons, Entry at bottom — Enter adds item and keeps focus; variable binding section; control selector dropdown at top; read-only `parent` geo row (drag on canvas to reparent); red `name_warn` tag on non-underscore handler names; `? Events` guide row at bottom of Events tab; ✦ auto-wire button on hover for unwired event rows; **Events tab click behavior**: clicking the name column alone does nothing — only value-column click opens the picker; double-click on any row navigates to that handler. **Handlers tab** — **Available / Connected split** driven entirely by `HANDLER_CATALOG` (`designer/handlers.py`); no checkboxes. *Available* shows handlers not yet wired; ⚡ floating button on hover: for connectable handlers opens `ComponentConnector` to pick widget+event, for non-connectable handlers enables them immediately. *Connected* shows wired/enabled handlers with target on right; × floating button to disconnect; … floating button on handlers with `options` or `secondary_options` to open `HandlerOptionsEditor`. **Widget-selected mode**: only connectable handlers whose `applies_to_widgets` includes the widget type are shown in Available; Connected shows only wires targeting this specific widget; `multi_wire` handlers (e.g. `_open_dialog`) remain in Available after wiring. **Available Components** sub-section — foldable (▶/▼ header, expanded by default); hovering the crease recolors only the ▶/▼ triangle (teal `_ORD_HDR_FG`) while the "Available Components" label stays dim (`_ORD_DIM`) — the arrow and label are drawn as separate canvas text items for this reason; all connectable component handlers listed regardless of wiring state (reusable); ⚡ opens `ComponentConnector` pre-selecting the active canvas widget; floating buttons corrected for canvas scroll offset. **⚡ Connected Components** sub-section — component methods wired to this widget's events or menu item commands (displayed as `{item_name}.command`); × to disconnect; **… edit button** on wired rows opens `ComponentConnector` pre-populated with the existing widget+event so the binding can be changed without first disconnecting. **Component mode** (`load_component(descriptor, comp_def)`) — hides Events and Order tabs, shows PropDef rows in Properties tab (int/bool/str/readonly kinds), shows ComponentHandlerDef rows in Handlers tab (⚡ button for `has_connector=True` handlers, fires `on_component_connect(comp_id, handler_id)`); **Dialog Titles** collapsible section in Properties for CommonDialog (shows per-handler title props for every wired handler); `_exit_comp_mode()` restores tabs. **Order tab** — canvas-rendered numbered list; drag to reorder (tab key focus sequence = z-order); Notebook tab grouping with teal header rows; badge numbering scoped per tab. Blue hover highlight on all rows; `×` clear button on hover for color/optional props and wired events; status-bar hints on hover; `form__bg` clearable. **X11 saved-iid pattern** — `_prop_clear_iid`/`_ev_btn_iid` store hovered row id so click handlers survive spurious X11 `<Leave>` events. **Form image** — `load_form` inserts `form__image` row (shows basename); `_open_form_image_picker` copies file to `images/` and fires `_on_prop_change("__form__", "image", rel)`; `_form_image_hint()` returns dynamic two-line hint with PIL dimensions; `_is_prop_clearable` includes `"form__image"`. **image_list prop kind** — `_insert_comp_prop_rows` displays `"N images"` / `"(none)"` for `kind="image_list"` props; `_dispatch_comp_prop_click` routes to `_open_comp_image_picker` which calls `askopenfilenames`, copies all selected files to `images/`, and fires `_on_component_prop_change(comp_id, "paths", rel_paths)`. **canvas_button Connected display** — `_collect_comp_connections` surfaces `canvas_buttons` entries from Image components as Connected rows with `removal_key=("__canvas_btn__", tag)`; `_collect_widget_comp_handlers` for Canvas-type widgets scans Image component `canvas_buttons` targeting this canvas and appends them with `removal_key=(comp_id, "__canvas_btn__", tag)`; `_collect_canvas_img_avail` returns Image components with paths as Available entries for Canvas widgets. **canvas_button readonly Events rows** — `_populate_events` appends `kind="readonly"` rows (`mousedown`, `mouseup`, optionally `mouseenter`/`mouseleave`) for each configured canvas_button when the widget is a Canvas. All 41 widget property keys now have entries in `_PROP_HINTS`. **Wired-handler Events rows** — `_populate_events` (widgets) and `load_form` (form-level events) both consult `_wire_method_map(target_id)` — via `_wired_event_methods(widget)` for a widget id and `_wired_form_event_methods()` for `"__form__"` — and show each connected catalog handler as a `kind="readonly"` row on its event (e.g. `command  _set_always_on_top`, `load  _set_always_on_top`); the method name is parsed from `hdef.wire_body_for(...)` so it stays navigable on double-click (multi-wire `_open_dialog` resolves to `_open_Dialog1`). Component-handler methods wired into a widget event (e.g. a socket scaffold's `_sock1_toggle_connect`) are likewise shown read-only — `_form_component_methods()` returns the `f"_{comp.id}{hdef.label}"` set and any `widget.events[ev]` in it renders without the inline ×. All such connections are managed from the Handlers tab, not editable inline. `reload_after_wire()` re-populates the active view (widget or form) after a Handlers-tab wire/unwire/edit so the Events tab updates without a reselect; `app.py`'s handler connect/disconnect/edit paths call it instead of `load_handlers`. **CI Events aggregation** — for canvas items, `_populate_events` aggregates bindings by shared tag via `_ci_tag_event_methods()`: the item that owns a binding shows an editable row, while every other item carrying the same tag shows the handler as a `kind="readonly"` row (no clear/wire/edit affordance) — mirroring the single tag-scoped `tag_bind` at runtime. `_ci_default_method`/`_do_auto_wire` name the handler after the binding tag (`_button_mousedown`), not the item instance. **CI handler Connected rows** — catalog-handler wires made in CI mode live on the item's props (`_ci_binding_handlers`/`_ci_binding_tags`), not in `form.handler_wires`, so `_collect_ci_conn_rows(widget, all_defs)` surfaces them as standard Connected rows (same name/target/× /… look as widget wires; `target` = `tag.event`). Each row carries a `ci_binding` payload (`item_id`/`tk_ev`/`tag`/`event_key`/`option`); `_on_handler_disco_click`/`_on_handler_edit_click` branch on it to fire `on_ci_handler_disconnect`/`on_ci_handler_edit` (× removes the binding, … reopens the `CanvasItemConnector` pre-selected for an in-place edit) instead of the widget-wire callbacks, and double-click jumps to the row's `nav_method`. Every Connected-section row is rendered with a leading `→` arrow (added at draw time when the name doesn't already carry one from `_parse_multi_wire_name`). **Hidden internal props** — `_populate_props` skips `_ci_binding_tags`/`_ci_binding_handlers` (owned by the Canvas Item Connector) alongside the existing `_ci_orig_w`/`_ci_orig_h` skips, so they never appear as raw property rows (a future Advanced Properties view to surface them is queued in `ROADMAP.md`). |
| `widgets/designer_component_tray.py` | Horizontal 36px chip strip placed below the design canvas — one icon+name chip per `ComponentDescriptor` in `form.components`; click-to-select (blue left accent + `_CHIP_AC` bg); right-click popup → Rename / Delete; empty state label when no components; `refresh(components)` rebuilds chips, `select(comp_id)` / `deselect()` update highlight without firing callbacks; `_RenameDialog` Toplevel for inline renaming; fires `on_select`, `on_deselect`, `on_delete`, `on_rename`. `set_project_dir(path)` stores the project root used for image path resolution. **Image component chips** — `_add_chip` passes `paths` and `project_dir` to `_Chip` for Image type; `_load_chip_thumb(paths, project_dir, size=22)` loads a PIL thumbnail of the first image; `_load_gallery_thumb(path, project_dir, size=80)` loads gallery-size thumbnails. `_Chip` for Image: icon slot uses a `tk.Label` with `image=thumb` instead of glyph text; a `×N` count label is added for multi-image groups; hovering calls `self.after(400, self._show_gallery)` which opens a `tk.Toplevel` gallery above the tray showing all images with key names; `_hide_gallery()` destroys the popup on leave. |
| `widgets/designer_img_button_builder.py` | `ImageButtonBuilder` modal `Toplevel` — opened by `_open_img_button_builder` in `app.py` when the user clicks ⚡ on an Image component's `canvas_button` handler (bypasses the standard `ComponentConnector`). Left column: canvas picker combobox (existing Canvas widgets + `＋ Create New Canvas`), Normal/Hover/Pressed image key comboboxes (populated from the component's `paths` stems; hover and pressed show `(none)` sentinel for optional), X/Y position entries, tag name entry, canvas-drawn auto-size checkbox (checks PIL dimensions of all paths and resizes the target Canvas widget). Right column: live preview `tk.Canvas` that loads actual `PhotoImage`s and responds to `<Button-1>`/`<ButtonRelease-1>`/`<Enter>`/`<Leave>` so you can test all three image states before confirming. Constructor params: `comp_id`, `paths`, `canvas_ids`, `project_dir`, `on_confirm(config_dict)`, `on_create_canvas() → str` (creates a new Canvas widget and returns its id), optional `preset_canvas_id`, optional `edit_config` (pre-fills from existing canvas_button dict). `_commit` creates the canvas (if sentinel is still selected), reads all fields, computes auto-size dimensions via `_get_max_image_size()`, and calls `on_confirm`. `_NONE_KEY = "(none)"` sentinel for optional image keys. |
| `widgets/designer_connector.py` | `ComponentConnector` modal Toplevel — used for both form handlers and component handlers. Left listbox: widgets with events (from `REGISTRY`) **plus** connectable menu items (non-cascade `kind="command"` items at `indent > 0`) when `menu_items` is supplied; right listbox: events for the selected widget, or just `"command"` for menu items; optional primary `options` combobox (e.g. dialog type picker) and optional `secondary_options` combobox (e.g. Populate widget picker); `wire_body_resolver` for live preview; optional `show_title_entry`/`show_extra_entry` with configurable labels for per-handler dialog titles and extra fields; `wire_label` param renames the Wire button (e.g. `"Update"` for the edit dialog); `preselect_widget_id`/`preselect_event_key` pre-select an existing binding (suppresses overwrite warning for same slot); `stub_checker(method_name) → bool` callback suppresses the "already wired" warning when the existing handler body is just `pass`; Wire button calls `on_wire(widget_id, event_key, option)` — caller routes to `widget.events[ev]`, `menu_item.command_handler`, or `form.handler_wires`. |
| `widgets/designer_ci_connector.py` | `CanvasItemConnector` modal Toplevel — the CI-mode counterpart to `ComponentConnector`. Because canvas-item bindings are *tag-scoped* (one `tag_bind` per tag fires for every item carrying it), this is an **Object / Tag / Event** dialog rather than Widget / Event: an Object list (canvas items), a Tag list (the selected item's tags + its own id-tag + the canvas tag pool, plus a "new tag" entry; shared tags show an `×N` count and a "fires for all of them" warning), and an Event list (the eight logical CI events). Plus the same `options`/`secondary_options` comboboxes and `wire_body_resolver` preview as the standard connector. Wire calls `on_wire(item_id, tag, event_key, combined_option)`. Opened from `app.py._open_ci_handler_connector` (the CI branch of `_on_designer_handler_connect`); options come from `ci_original_form.linked_dialogs`. `preselect_item_id`/`preselect_tag`/`preselect_event_key`/`preselect_option`/`preselect_secondary` pre-fill all four fields and `wire_label` renames the button (`"Update"`) when the dialog is reopened to **edit** an existing CI binding (the … button on a Connected CI row); in edit mode `_open_ci_handler_connector` first unwires the old binding so changing tag/event doesn't orphan it. |
| `widgets/handler_options_editor.py` | `HandlerOptionsEditor` dark-themed `Toplevel` — pick a named mode for a handler stub or connected-wire body. Two-line rows: bold option name line 1, orange body description line 2 (full canvas width, no truncation). `is_wire=False` edits `form.handler_options[handler_id]` (controls stub body); `is_wire=True` edits `HandlerWire.option` (controls widget-event body). Accepts `override_options`/`override_bodies` to bypass the static HandlerDef lists — used when options are dynamic (e.g. the close-mode picker for `_open_dialog` reads `hdef.secondary_options` and `hdef.edit_bodies`). |
| `widgets/form_list_panel.py` | FORMS tree panel in the designer's left column — main forms (`⬜`), linked dialogs (`⧉`), "Unlinked" section; click to switch canvas, drag dialog onto main form to link, hover `×` to unlink/delete, missing forms in red with right-click remove; `+` button and ▶ main-form indicator in the header. |

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
- **Editor mixins operate on host-owned state.** `CanvasCodeView` is decomposed into single-responsibility mixins (`widgets/canvas_editor/`) — every attribute is initialized in `_init_state`; mixins never import the host or each other. Shared editing constants (auto-pair table, bracket/quote sets, editor font, minimap width) live in `canvas_editor/constants.py` — never duplicate them per-module.

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
- Regex-rule syntax highlighting (canvas-rendered, no pygments); **fold markers** — `▼/▶` gutter glyphs; `# ── Name ───` section headers fold to the next section header at the same indent; IDOL codegen markers (`# ── IDOL:BEGIN`, `# ── IDOL:IMPORTS:BEGIN`, etc.) fold their entire BEGIN…END block regardless of indentation; Up/Down arrow skips folded blocks; Ctrl+/ comment toggle; word occurrence highlights on cursor move (tokenizer in `canvas_editor/tokenizer.py`)
- **Bracket & quote match highlighting** — matching bracket pair outlined on cursor move via a directional depth scan; quote pairs matched by a same-line parity scan (opener == closer, so depth counting can't work); render calls `_find_bracket_pair()` once per paint (`canvas_editor/bracket_matcher.py`)
- **Multi-cursor** — Alt+Click adds/removes secondary cursors; all `|` carets blink in sync with the primary; edits applied bottom-to-top; secondary selections rendered in `select_bg`; Escape clears; `mc_count()` public helper. Implemented in `widgets/canvas_editor/multicursor.py` (`MultiCursorMixin`) operating on host-owned `_mc_cursors: list[tuple[int,int]]` and `_mc_anchors: list[tuple[int,int]|None]`
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
- Sticky scroll; **minimap** — embedded in the canvas editor (not a separate widget), fold-aware (folded lines are hidden in the minimap too), hover zoom preview (`canvas_editor/minimap.py`)
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
- Integrated PTY terminal (pyte VT100 screen buffer) with venv detection (activate/deactivate/switch toolbar); live-buffer reflow on column resize (VS Code style)
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
- **Tab / Shift+Tab on selection** — Tab indents all selected lines (`tab_size` spaces, cursor + anchor adjusted); Shift+Tab removes up to `tab_size` leading spaces from the current line or every line in the selection
- **Ghost sash — sidebar** — sidebar's custom Frame-based horizontal sashes use a 2 px `#007acc`
  ghost overlay during drag; actual resize fires on `ButtonRelease` only; also restores the
  missing `<ButtonPress-1>` binding that was never wired to `_sash_press`

### GUI Designer — shipped summary

Dated, per-session shipping notes live in `CHANGELOG.md`; full feature detail in
`docs/designer.md`; per-file implementation detail in the `designer/` table above.
Current shipped state:

- **Design canvas** — drag/drop with snap grid (Shift bypasses for 1 px precision on move/resize/draw/form-resize), resize handles, multi-select rubber band (primary amber with handles, secondaries blue), copy/paste with cascade offset, arrow-key nudge (8 px, Shift+arrow 1 px), bring-to-front/send-to-back with z-order preservation, draw-to-size placement, palette drag-and-drop + multi-placement mode, smart placement cursors, container parenting (Frame/LabelFrame/Notebook with tab grouping, cascade delete, draw-inside, drag-out reparent), grid visibility toggle, form recenter, undo/redo (50 snapshots), alignment/distribute/same-size toolbar with state-aware button dimming
- **Properties panel** — canvas-rendered Properties/Events/Order tabs (zero widget teardown); inline editors: text, enum overlay dropdowns with hover hints, color swatches + chooser, font chooser, list editor, validate rows (`--vcmd`/`--args`/`--ivcmd`), state-conditional color rows; variable bindings + variable picker; anchoring (3×3 picker, live repositioning, Shift suppresses); multi-select editing (shared-prop intersection; font/list editors blocked by design); Order tab drag-to-reorder with Notebook tab grouping
- **Events & Handlers** — catalog-driven Handlers tab (Available/Connected split; ⚡ wire, × disconnect, … options editor) powered entirely by `HANDLER_CATALOG` — adding a handler is one `HandlerDef` entry, zero `app.py` changes; `ComponentConnector` for widget/event/menu-item picking; `HandlerOptionsEditor` for mode variants; double-click navigation to handlers; `command` constructor-kwarg events; form events (load/activate/deactivate/unload/resize)
- **Menu Builder** — VB6-style editor (caption/name/shortcut, check/radio items with variables, separators, `&` access keys, indent arrows); live menu bar strip on canvas with handler navigation; full `tk.Menu` codegen including variable declarations and shortcut bindings; menu items wirable directly to component handlers
- **Multi-form projects** — FORMS tree (main forms, linked dialogs, unlink/delete, missing-form detection in red); dialog codegen as `tk.Toplevel` subclasses with reuse-on-deiconify openers; Set as Main (▶ run-entry sync); auto-enter Designer mode on project open; Explorer right-click `.form.json` → Open in Designer; designer session persistence (active state, form names, main form, sash widths); Save Form + Save/Don't Save/Cancel exit prompt; dual dirty flags (`_designer_dirty` codegen / `_designer_forms_dirty` JSON)
- **Components (non-visual)** — palette COMPONENTS section + chip tray below canvas (rename/delete; Image chips show thumbnails with hover gallery); **Timer** (`self.after` loop), **CommonDialog** (file/dir/color/input/messagebox with per-handler titles, target-widget file read/write, selective imports, `parent=self`), **Socket** (TCP server/client with mode-gated props and handlers, setup dialog with Connect/Chat/File-Transfer scaffold kits, length-prefixed framing via `struct`), **Image** (named references, multi-file groups, `canvas_button` builder with live 3-state preview and auto-size)
- **Image support** — `image` prop on Label/Button/Canvas; files copied to `<project>/images/` (conflict-safe naming, forward-slash relative paths); design-time PIL previews with cache; Pillow-missing warning row with one-click install; anchor-aware runtime reload on resize; form background image
- **Canvas Item Designer** — double-click a Canvas widget to place image/rectangle/oval/text/line items inline (dimmed overlay, amber selection, 8 resize handles, Esc to exit); per-item props/events in the Properties panel; codegen with `tag_bind` dedup, design-time pre-scaling + runtime stretch scaling (fonts and line widths scale by geometric mean), fonts always emitted as tuples (multi-word family fix)
- **Codegen guarantees** — `IDOL:BEGIN/END`, `IDOL:IMPORTS`, `IDOL:DIALOG_IMPORTS`, `IDOL:COMPONENTS` marker blocks; event bodies, helper methods, user imports, user `__init__` zones, and leading comments all survive regeneration; SHA-256 manual-edit detection; silent debounced auto-generation (1.5 s); Run-while-dirty prompt
- **Cross-platform polish** — labels-as-buttons and canvas-drawn checkboxes everywhere, X11 saved-iid hover pattern, Linux mousewheel bindings, `UI_FONT`, custom scrollbars throughout, `grab_set()` ordering, macOS fullscreen + Linux maximize session restore

## Planned / In Progress

- **GUI Designer — remaining roadmap:** grid layout mode; live preview (run form in subprocess).

---

## Definition of Done

**A feature is not done until its documentation ships in the same commit. No exceptions.**
"Code now, docs later" is not done — the docs change is part of the feature. A commit
that adds or changes behavior without the matching doc updates is incomplete.

A change is done when:
1. The code works — manually verified (run the feature's checklist)
2. This file is updated (rules below)
3. The matching `docs/` page is updated (table below)
4. `README.md`, `CHANGELOG.md`, and `ROADMAP.md` are updated where applicable

### This file (`CONTRIBUTING.md`)
- When you add a file to `editor/`, `utils/`, `widgets/`, `widgets/canvas_editor/`, or `designer/`, add a row to the relevant table
- When a planned feature ships, move it from **Planned / In Progress** to **Current Feature State**
- When a key technical decision changes (threading model, import rules, etc.), update the relevant section
- Do **not** add dated "SHIPPED" sections here — dated shipping history belongs in `CHANGELOG.md`

### `CHANGELOG.md`
- Every shipped feature gets a dated entry — per-session shipping detail lives there; this file keeps only the current-state summary

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
- Don't import from `widgets/canvas_editor/` anywhere except `canvas_codeview.py`; don't let mixins import the host or each other
- Don't add dated "SHIPPED" changelog sections to this file — shipping history goes in `CHANGELOG.md`
