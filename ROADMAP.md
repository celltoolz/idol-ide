# IDOL Roadmap

This document tracks completed milestones, work in progress, and the planned feature backlog.

---

## Phase 1 — Core IDE — COMPLETE (2026-04-27)

**Core Editor**
- Multi-tab editing with session persistence (dirty tracking, restore hardening, _restoring flag + 400ms cleanup pass)
- Pygments syntax highlighting
- Multi-cursor editing: Alt+Click to add/remove; Shift+Arrow independent per-cursor selections; Ctrl+C copies all; smart pairs and bracket matching at every cursor; click-placement aligned to nearest character boundary
- Line move/duplicate: Alt+Up/Down moves current line or selected block; Shift+Alt+Down duplicates below (cursor follows); Shift+Alt+Up duplicates below (cursor stays on original)
- Split editor with scroll sync and scroll lock (hardware Scroll Lock key synced on startup)
- Minimap, sticky scroll, fold markers
- Breadcrumb bar: path crumbs, symbol crumbs, sibling picker, locals drill-down, marquee scroll footer
- Find/Replace
- Ctrl+/ comment toggle; word occurrence highlights on cursor move and arrow-key nav
- Zen mode (F10), sidebar toggle (Ctrl+B)

**LSP & Diagnostics**
- pylsp integration: hover, diagnostics, definition, completion
- Problems panel: PROBLEMS tab in bottom bar, colored severity dots, click to jump to line/col
- Diagnostic statusbar badge: live ✕N ⚠N, clickable to open Problems panel
- Dual-track error engine: ruff subprocess + compile() fallback on a debounced background thread
- Three-tier diagnostic severity: red (error) / yellow (warning) / blue (info/hint)
- Runtime error indicators: amber gutter arrow, line highlight, Problems tab flash on run failure
- Problems panel AI: Ask AI button sends errors + file to Ollama; double-click entry for explanation; hover tooltips with beginner-friendly ruff rule descriptions

**Git**
- Source control panel: staging, unstaging, commit, push, diff view, virtual rendering for large file lists
- Git health panel: smart warnings, fix wizard, `.gitignore` creation, Add to .gitignore context menu
- Commit History panel: last 50 commits, file diff on click, filter bar, load more
- Git guides: install guide (Windows/macOS/Linux), identity guide (git config + GitHub account + `gh auth login`), remote guide, first commit guide

**Terminal**
- Integrated PTY terminal (pyte VT100 screen buffer); real PTY via `pty` module (Unix) / `winpty` (Windows)
- Venv detection with activate/deactivate/switch toolbar; venv re-activated automatically on next launch
- Terminal debug mode: launch debugpy in terminal, attach DAP client
- Output panel: copy button and right-click context menu; inline stdin bar for `input()` support

**Run & Debug**
- Run Line / Run Selection from editor right-click menu
- VS Code-style split run button: action + chevron dropdown
- Integrated Python debugger: debugpy over DAP; IDOL's bundled debugpy injected via PYTHONPATH — no per-project install needed
- Breakpoints: VSCode-style gutter with hover ghost dot and bright active dot; persist across sessions; auto-shift on line insert/delete; restore on undo/redo
- Floating debug panel: dock/undock, always-on-top, session restore; LOCALS + BREAKPOINTS subpanels
- Step controls: Continue (F5), Step Over (F10), Step Into (F11), Step Out (Shift+F11), Stop (Shift+F5)
- `input()` debug guide: detected automatically in Output debug mode, surfaces guide button

**AI**
- AI Chat panel: Ollama/qwen2.5-coder, session history, token counter, remote host config, animated "Thinking…" dots, horizontal scroll on code blocks
- Learning Mode (F1): hover any IDE element for three-section explanations with AI Ask button; custom arrow+? cursor (XBM on Linux); cursor+flash intercept replaces overlay system
- Ask AI integration in Problems panel

**Project & Config**
- Project setup wizard: 4-step (name/location, interpreter/venv, git/starter files, summary + first commit guide)
- Interpreter statusbar segment: click to pick; persists per project root in `~/.idol/settings.json`; venv shown as `(.venv) Python x.x.x`, re-activated on next launch
- Run entry file selector in statusbar (▶ Active Tab or ▶ filename)
- Session persistence: open tabs, layout, appearance, breakpoints, active interpreter, active venv; auto-session writes to `~/.idol/session.json`; named saves write to `.idol-project` in project root
- Project lifecycle: new / open / close with full teardown (`_teardown_project`, `workspace_close`, `workspace_open`)

**Navigation & UI**
- Nav toolbar: split run button, panel toggles (AI, Learn, Packages), view toggles (Minimap, Sidebar, Split, Zen)
- Unified Panels menu: View → Panels submenu; Ctrl+` terminal, Ctrl+Shift+U output, Ctrl+Shift+M problems, Ctrl+Shift+Y debug; each shortcut toggles visibility
- Command palette (Ctrl+Shift+P): fuzzy search, `@` symbol search, `!pip` mode with package name autocomplete
- Explorer: rename, delete, drag/drop file/folder, new file/folder, context menus, unsaved-change guard on move
- Outline panel with locals drill-down (instance attrs, nested defs, color-coded sections)
- References panel
- GuideWindow system: content-agnostic paginated `Toplevel`; used across all guides in the app

**Package Manager**
- Pip Package Manager (F3): PyPI classifier-based topic grouping, live filter, PyPI search, install/uninstall, AI examples
- `!pip` command in command palette with package name autocomplete
- All package operations use the active interpreter

**Colorscheme system** (`.toml` files, parsed by `utils/schemeparser.py`)

**Branding:** Renamed Notepad → IDOL; splash screen; About dialog

---

## Phase 2 — IDOL Designer — COMPLETE (2026-05-05)

- Mode switcher: \[Editor\] / \[Designer\] per project
- Widget palette with canvas-drawn previews (14 widget types)
- Drag/drop placement, 8-handle resize, rubber-band multi-select, copy/paste, z-order
- Properties panel: color pickers, state dropdown, validate dropdown, control selector
- Events tab: auto-wire, name-prefix warning, ? Events guide
- **Handler picker** — `HandlerPickerEntry` in Events tab and Menu Editor Command field; ▾ button opens scrollable dropdown listing all handlers defined on the form; hover-to-preview; smart positioning (right-align, flip above anchor when maximized)
- **Font property** — `font` row opens `tkfontchooser` dialog pre-populated with current family/size/style; writes result back as a string tkinter accepts natively; supports bold, italic, underline, overstrike
- Variable binding (StringVar / IntVar / DoubleVar / BooleanVar) + Variable Picker popup
- Code generation with full preservation: event bodies, signatures, pre/post-init zones,
  helper methods, user imports (IDOL:IMPORTS markers); leading comments in handler bodies preserved on regen
- ~~Unified codegen prompt~~ — removed; code generation is now always silent
- Menu Builder: caption/name/shortcut, enabled/visible, type, variable, command, value;
  indent/insert/delete; **Separator item**; **& access-key** in captions (display_caption + underline kwarg); codegen with add_checkbutton/add_radiobutton and auto self.bind()
- Widget containment: Frame/LabelFrame auto-parent dropped widgets; drag-out to reparent
- Inline list editor, color swatches, hover hint bar, × clear buttons, ✦ auto-wire
- Full widget property coverage: wraplength, onvalue/offvalue, selectmode, char_width/height,
  resolution, tickinterval, increment, labelanchor, Spinbox values-list mode, scrollbar (Listbox/Text), and more
- Canvas visual pass: disabled state, password dots, Listbox values, Progressbar stripes
- Form events: load / activate / deactivate / unload / resize with codegen and method stubs
- Double-click event row → jump to handler in editor
- Double-click palette widget → place at form centre
- Ghost sash drag (blue line, resize on mouse-up only)
- Startup and AI-chat sash flash eliminated (pre-size from saved session)

---

## Phase 2 continued — Designer Polish (2026-05-07)

### Widget Anchoring + Alignment Toolbar — COMPLETE

- **Widget anchoring**: 9-mode anchor picker (3×3 grid in Properties); codegen emits
  `_apply_anchor_layout()`; anchor row gets mouseover × clear
- **Live anchor repositioning**: widgets reposition/resize in real time as the form is
  dragged — matches runtime behavior; **Shift+resize suppresses anchors** (widgets frozen)
- **Anchor hint**: hovering the anchor row shows description + Shift shortcut note;
  picker popup also shows the note at the bottom
- **Alignment Toolbar**: full toolbar with 4 clusters — Align L/R/T/B/H/V, Distribute
  H/V (grid-aware), Same Width/Height, Undo/Redo/Copy/Paste; all buttons disable when
  their action doesn't currently apply
- **Multi-placement mode**: single click on palette item stays armed; each canvas click
  places another widget; Escape / click outside / Pointer de-arms
- **Smart placement cursor**: crosshair over empty form (place), arrow over unselected
  widget (click selects + de-arms), fleur over selected widget(s) (drag moves immediately)
- **Form resize handles**: N/NW/NE handles now appear above the titlebar
- **Ghost sash fix**: editor/output (ttk.PanedWindow) sash now correctly detects drags
  using `sashpos()` proximity — was silently failing on Windows due to unreliable `identify()`
- **Grid layout popup**: ⊡ toolbar button → Make Grid + H/V nudge controls
- **Form recenter**: form recenters on canvas after a resize drag
- **Relief rendering**: widget `relief` prop (raised/sunken/groove/ridge/solid/flat) draws correctly on the canvas for all supported types; `borderwidth` respected; Frame keeps dashed indicator when flat
- **Draw-to-size placement**: with a palette tool armed, drag on the canvas to define the widget's bounding box; plain click still drops at default size
- **Palette drag-and-drop**: drag a widget type from the palette directly onto the canvas; ghost label follows cursor; drops at default size at cursor position

---

## Phase 2 continued — Multi-Form Designer (2026-05-08)

- **Multi-form support** — projects can contain any number of `Main` (`tk.Tk` subclass) and
  `Dialog` (`tk.Toplevel` subclass) forms; each form has its own `.form.json` sidecar and
  its own generated `.py` file
- **FORMS tree panel** — canvas-rendered tree above the widget palette; main forms appear at
  top level, linked dialogs indented below with `⧉` icon; unlinked dialogs in a dim
  "Unlinked" section at the bottom
- **Form switching** — click any row in the FORMS tree to save the current canvas and load the
  selected form; `×` unlink button appears on hover for linked dialog rows
- **Drag-to-link** — drag a dialog row and drop it onto a main form row to link it; the target
  form highlights blue during hover; a ghost tooltip (`⧉ name`, semi-transparent) follows the
  cursor; dragging a linked dialog to a different form unlinks it from the old parent first
- **Drag threshold** — mousedown on a draggable row records pending state only; drag activates
  after 5 px of movement so plain clicks pass through cleanly to selection
- **New Form dialog** — `+` button (FORMS header) and `Designer → New Form…` open a dialog
  with name entry, Main/Dialog type selector, and a **"Link to:"** dropdown listing all
  existing main forms; defaults to the first main form when creating a dialog; disables when
  Main Window type is selected; new dialog appears nested in the tree immediately
- **Dialog codegen** — dialog forms generate `tk.Toplevel` subclasses:
  `__init__(self, parent, **kwargs)` with `super().__init__(parent, **kwargs)` +
  `self.withdraw()`; no `if __name__ == "__main__":` block; `WM_DELETE_WINDOW` wired to
  `_on_close` (preserved stub, default body `self.withdraw()`) so closing hides rather than
  destroys the window
- **Dialog instances on parent** — each linked dialog is instantiated once in the parent's
  `IDOL:BEGIN` block as `self.dlg_DialogName = DialogName(self)`; opener becomes
  `self.dlg_DialogName.deiconify()`; parent has direct attribute access to the dialog at all
  times; existing projects with the old `DialogName(self).deiconify()` body are auto-migrated
  on the next regen
- **`IDOL:DIALOG_IMPORTS` zone** — auto-managed import block emitted below `IDOL:IMPORTS`;
  regenerated from `linked_dialogs` on every codegen run
- **Multi-form codegen order** — dialogs generated before main forms so imports resolve
- **Canvas scroll offset fix** — resize handles and rubber-band selection used raw event
  coordinates; now converted with `canvasx()`/`canvasy()` so both work correctly when the
  form is scrolled

---

## Designer Phase 3 continued — Linux / Cross-Platform Polish (2026-05-10)

- **`grab_set()` ordering** — `designer_new_form()` and `MenuEditor.__init__` now call `grab_set()` after `update_idletasks()` so the window is fully mapped before the grab; fixes "can't grab window" on Linux/X11
- **`StyledCheckbox`** (`widgets/styled_checkbox.py`) — reusable Unicode-glyph checkbox; identical appearance on all platforms; extracted from ProjectWizard
- **X11 saved-iid pattern** — `_prop_clear_iid`/`_ev_btn_iid` in `designer_properties.py` fix the clear button and ✦ wire button on Linux (X11 spurious `<Leave>` events were clearing hover-index before clicks fired)
- **Form `bg` clearable** — `form__bg` added to clearable props; no more `#f5f5f5` placeholder when form background is unset
- **Empty bg defaults in registry** — non-input widgets now default to `"bg": ""` so generated code doesn't hardcode Windows-gray background on other platforms
- **Tkinter clipboard** — replaced pyperclip with `clipboard_clear()` + `clipboard_append()`; `pyperclip` removed from `requirements.txt`
- **Linux mousewheel on designer canvas** — `<Button-4>`/`<Button-5>` and `<Shift-Button-4>`/`<Shift-Button-5>` added to `canvas.py`
- **Cross-platform UI font** — `utils/ui_font.py` exports `UI_FONT` (`"Segoe UI"` / `"Helvetica Neue"` / `"DejaVu Sans"` per platform)

---

## Planned — Designer

- Open Designer for existing (non-wizard) projects
- Live Preview mode — eye icon toggles canvas to interactive state without running the app
- Priority event sorting — most relevant events floated to top per widget type

---

## Planned — Variable & Data

- **"Used By" reverse lookup** — Variable Picker shows usage count badge; hover lists bound
  widgets; click navigates canvas to that widget (gold border highlight)
- **Global Variable Rename** — rename in picker → prompt to update all widget references in
  form.json and generated code automatically
- **Type-safe variable filtering** — only show compatible var types per widget slot
- **Variable Tracing / Variable Events** — wire a handler to `trace_add("write", ...)` from
  the Events tab; codegen emits trace setup + method stub

---

## Planned — Code Generation

- **Code Repair mode** — if IDOL:BEGIN/END markers are accidentally deleted, detect and
  append orphaned user code to the bottom of the file instead of discarding it
- **Validation substitution tooltips** — status bar hints for `%P`, `%S`, `%W` in --args rows
- **Menu Item Proxies** — generate a `MenuProxy` class per menu item so users can write
  `self.mnu_file.enabled = False` instead of `entryconfig` index gymnastics

---

## Designer Phase 4 — Notebook, Scrollbars & Polish (2026-05-11)

- **ttk.Notebook widget** — first-class container; canvas renders native-style tab strip; each child carries a `widget.tab` string; switching tabs selects the Notebook and hides inactive children; `<<NotebookTabChanged>>` event + codegen
- **Order panel — Notebook tab grouping** — children indented under teal tab-header rows in `tabs` property order; drag across a header to reassign tab; badges scoped per tab
- **Draw inside containers** — drawing a widget while cursor is over a Frame/LabelFrame auto-parents it; children clamped to container bounds
- **Container cascade delete** — deleting a Frame/LabelFrame/Notebook removes all descendants
- **Arrow-key nudge** — 8 px by default (matches snap grid); Shift+arrow = 1 px; respects snap toggle
- **Debounced auto-codegen** — any change schedules a codegen run 1.5 s later; rapid edits coalesce
- **Menu editor polish** — labels-as-buttons throughout; canvas-drawn dark checkboxes; Caption→Name autofill on Tab
- **Custom IDOL scrollbars** — all `ttk.Scrollbar` instances in IDOL's own UI replaced with canvas-drawn `VerticalScrollbar`/`HorizontalScrollbar`; editor 16 px wide; panels 12 px; no up/down arrows; autohide via `grid_remove()`
- **macOS fullscreen persist** — state saved to `session.json` and restored on launch
- **Linux maximize session** — `<Configure>`-tracked flag + `_force_normal` retry at 300 ms to fight WM session management; flash accepted (do not attempt `withdraw()`/`deiconify()`)

---

## Phase 2 continued — Editor & UX Polish (2026-05-08)

- **Designer Shift+click nudge** — holding Shift while clicking any nudge arrow steps by 1 px
  instead of 8 px (`e.state & 0x1` in `designer/toolbar.py`)
- **Git ahead/behind statusbar** — `⎇ branch ↑N ↓N` indicator; async
  `rev-list --left-right --count` in `editor/git_manager.py`; refreshes after commit/push/pull
- **Validation substitution tooltips** — hover hint bar in Properties shows `%P`, `%S`, `%d`
  descriptions for `vcmd_args` dropdown items
- **Non-ASCII paste detection** — `_BAD_PASTE_CHARS` frozenset in `codeview.py`; fires
  `<<BadPaste>>` virtual event; nav bar shows amber "Fix Encoding" pill that replaces bad chars
  with space (zero-width stripped entirely)
- **Panel redraw flicker eliminated** — source control uses diff-based row reconciliation
  (unchanged rows kept on screen); outline uses `_fingerprint()` pre-check to skip full rebuild
  when visible structure hasn't changed
- **Ghost sash fix — sidebar** — sidebar's custom Frame-based sashes now use ghost drag (blue
  2 px overlay line tracks mouse; actual panel resize fires on mouse-up only); also fixes the
  missing `<ButtonPress-1>` binding that was never connected to `_sash_press`

---

## Phase 3 — IDOL Components (not yet started)

VB6-style non-visual components — drag onto a component tray below the canvas, codegen emits
the import + pre-wired class skeleton.

**Candidate components (priority order):**
1. `threading.Timer` — periodic callback skeleton
2. `sqlite3` — connection + cursor + query helpers
3. `socket` — TCP client or server skeleton
4. `tkinter.filedialog` — open/save dialog helpers
5. `smtplib / email` — send-mail skeleton
6. `csv / json` — file read/write helpers
7. `http.server` — simple HTTP server skeleton
8. **"Me" proxy** — opt-in VB-style window wrapper (`back_color`, `hide()`, `show()`,
   `controls`, etc.); user drags from tray, not autogenned by default

### Dialog Helper Injector

When a form has linked dialogs, a **Dialog Helpers** component (or right-click option on a
linked dialog row in the FORMS tree) opens a picker dialog listing opt-in helper methods the
user can inject into their form class. Clicking a helper appends the stub to the Functions
section (or a new Helpers zone) on next codegen.

**Candidate helpers (per linked dialog):**

| Helper | What it does |
|---|---|
| `_new_Dialog1()` | Destroys and recreates the instance — `self.dlg_Dialog1.destroy(); self.dlg_Dialog1 = Dialog1(self)` — useful for a full state reset |
| `_show_Dialog1()` | Alias for `_open_Dialog1` — `self.dlg_Dialog1.deiconify()` |
| `_hide_Dialog1()` | Programmatically hide — `self.dlg_Dialog1.withdraw()` |
| `_center_Dialog1()` | Position the dialog centered over the parent window |
| `_on_Dialog1_result(data)` | Callback stub — wire from inside the dialog to pass data back to the parent |

**Design notes:**
- Nothing is autogenned by default — user explicitly opts in via the picker
- Each helper is a preserved event stub, so the body survives regeneration
- The picker could live as a right-click context menu on a linked dialog row in the FORMS
  tree, or as a dedicated "Dialog Helpers" entry in the Components tray
- `_on_Dialog1_result` pairs naturally with a `self.master._on_Dialog1_result(...)` call
  inside the dialog's own event handlers — forms a clean parent↔dialog communication pattern

---

## Long-Term Ideas

### Clipboard History Panel
A dedicated panel (or Command Palette overlay) showing the last N clipboard entries.
- Ring buffer of copied text (configurable depth, e.g. 50 entries); each entry stores content +
  timestamp + source file/line
- Accessible via `Ctrl+Shift+V` or a panel tab; click-to-paste or keyboard nav + Enter
- Search/filter bar across all entries; single × to delete an entry; "Clear All" button
- Entries pinned with a 📌 icon survive "Clear All"
- Storage: in-memory only (never written to disk — clipboard content is sensitive)
- Implementation sketch: hook `codeview` paste and intercept Ctrl+C/X at the app level;
  render entries as a canvas-virtualized list (ties directly into the canvas panel idea below)

### Canvas-Virtualized Side Panel Renderer
Replace the Frame/Label widget trees in the sidebar panels with a single `Canvas` per section,
drawing rows as canvas items and only repainting visible rows.
- Motivation: zero widget teardown → zero flicker; handles 10 000-row symbol lists without
  slowdown; enables smooth animated expand/collapse and VS Code-style hover highlights
- Each panel section gets one `Canvas` + a vertical `Scrollbar`; rows are `create_text` /
  `create_image` items; `tag_bind` handles clicks, hovers, and context menus
- Approach: build it first on a new surface (Clipboard History is the ideal pilot) to prove out
  the pattern before migrating the four existing panels (Outline, References, Source Control,
  Explorer)
- This is also a **showcase milestone** — demonstrating that raw Tkinter can produce
  virtualized, sub-millisecond-repaint UI on par with Electron-based editors; Tkinter is
  systematically underestimated and IDOL is a direct rebuttal of that. A Canvas renderer that
  handles real IDE workloads (large file trees, live symbol updates, commit history) is exactly
  the kind of thing that shifts that conversation

### IDOL Custom Widget Library
A curated palette of pre-built, production-quality Tkinter widgets that ship with IDOL and appear
as first-class entries in the Designer palette alongside the standard Tk widgets.
- **Motivation**: same Tk showcase goal as the canvas renderer — prove that Tkinter can produce
  polished, professional UI components without Qt or Electron; Clipboard History is the first
  proof of concept (canvas-rendered rows, pinned entries, animated hover, keyboard nav)
- **Candidate widgets (first batch):**
  - `IDOLListView` — canvas-virtualized, sortable, filterable list with column headers
  - `IDOLCard` — rounded-corner card with drop shadow, title bar, and content slot
  - `IDOLBadge` — pill-shaped colored label (status, tag, severity indicator)
  - `IDOLToast` — slide-in/out notification overlay (success / warning / error variants)
  - `IDOLToggle` — animated iOS-style toggle switch (replaces Checkbutton)
  - `IDOLProgressRing` — circular indeterminate / determinate progress indicator
  - `IDOLSearchBox` — styled search entry with clear × button and animated placeholder
- **Distribution**: widgets live in `widgets/idol_components/`; codegen emits
  `from idol_components import IDOLListView` and a dependency note
- **Designer integration**: each component has a canvas preview thumbnail (same system as
  standard widgets); Properties panel exposes its custom properties; double-click to place

### Other Ideas
- **Import / Export project** — bundle to single `.idolpkg` file (zip-based); import wizard
  with package checklist, interpreter mismatch warning, and git init / remote-pull options
- **Grid / Pack layout mode** — drag-first canvas with auto-detected grid overlay
- **Debug Log tab** — passive trace of variable values and line numbers during debugpy sessions
- **Code peek on canvas hover** — 2s hover shows handler code preview popup
- **Multi-framework support** — PySide6 / PyQt6 backend alongside Tkinter
- **Bidirectional designer ↔ code sync** — very long term
- **Canvas, Treeview, Notebook** widget types
- **Learning Mode in Designer** — hover-driven explanations when F1 is active
- **Floating sticky-note mini editor** — mini panel that grabs current selection, stays on top
- **Rename project to "IDOL"** — at feature-complete milestone

---

## Known Bugs

- macOS: 20px canvas/codegen offsets need audit after macOS testing session
- Linux: IDOL window maximize state has a visible flash on restore (normal → maximize → normal) — WM session management re-maximizes windows asynchronously; `_force_normal` at 300 ms fights it but can't eliminate the flash; `withdraw()`/`deiconify()` makes it worse — accepted limitation
- Debugger: global hotkeys (F5/F10/F11/Shift+F11/Shift+F5) require a low-level keyboard hook
  (pynput or keyboard lib) to fire when IDOL doesn't have focus
- Codegen: removing the last widget reference to a handler silently drops its body on regen
