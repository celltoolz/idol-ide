# IDOL Roadmap

This document tracks what's coming next, what's planned, and what's already been built.
Completed sessions live at the bottom as a historical record.

---

## 🎯 Next Up — Active Feature Queue

> Start here when picking up the next session. Roughly in priority order.

### Designer

- **ttk.Treeview widget** — Palette entry, canvas-drawn preview (header + sample rows). Props: columns (list editor like Notebook tabs), show (tree/headings/both), selectmode, height. Column editor popup defines ids/headings/widths/anchor/stretch. Events: `treeselect` (`<<TreeviewSelect>>`), `treeopen`, `treeclose` + standard mouse events. Codegen emits column defs + heading setup in `_build_ui`. Consistent with Listbox/Notebook handling.
- **Audit component-generated event visibility** — `canvas_button` done (readonly rows in Events tab). Audit Timer (`_tick`), CommonDialog handlers, Socket handlers — wherever component codegen produces bindings that aren't visible in the widget Events tab, make them visible as readonly rows.
- **Open Designer for existing (non-wizard) projects** — user may want the GUI builder without going through the New Project wizard.
- **Live Preview mode** — eye icon toggles canvas to non-editable interactive state; widgets respond to real input without running the full app; strips grid lines and handles; restores on exit.
- **Priority event sorting** — float the most relevant events to the top per widget type (e.g. `click` first for Button, `change` first for Entry).

### Editor / IDE

- **Settings panel** — `View → Settings` consolidating per-user preferences that are currently scattered or missing UI:
  - Font (family / size / bold / italic) — currently only via `View → Change Font`
  - Theme — currently only via `View → Theme`
  - Highlight active line (on/off), Active line color (color picker)
  - Autocomplete on/off, smart pairs on/off
  - Tab size
  - Codegen toggles (see below)
  - (Future) LSP on/off, ruff on/off
  Settings write to `~/.idol/settings.json` and apply live.

- **Codegen settings section** (in Settings panel above):
  - "Auto-save .py before regen" (currently always-on → make opt-out)
  - "Warn on manual .py edit detected before regen"
  - "Show confirmation before overwriting user code zones"

- **Replace `tkfontchooser`** — drop the external dependency; build a native IDOL font chooser:
  - Left: scrollable font list (`tkfont.families()`) with filter entry
  - Center: Size entry + Bold / Italic checkboxes
  - Right: live preview label in selected font
  - OK / Cancel; matches current `set_font()` API

- **Custom color chooser** — replace `tkinter.colorchooser` (bare RGB slider on Linux):
  - Canvas-drawn color wheel or HSV square
  - R/G/B sliders + numeric entries + **Hex value entry** (type `#FF00AA` directly)
  - Old / New preview swatches; same return signature as `colorchooser.askcolor`
  - Hooks into Designer color rows + Settings active-line color

- **Editor fg/bg color hover** — hovering a hex string literal (e.g. `"#FF00AA"`) shows a color swatch tooltip; clicking opens the IDOL color chooser. Canvas editor already renders inline color swatches — extend to interactive.

- **References code-peek zoom** — hovering a row in the References panel shows a small floating zoom window with the reference's surrounding code, similar to the minimap zoom but smaller. Exact sizing/layout TBD in a dedicated design session before implementation.

- **More bundled themes** — add 2–3 popular themes as `themes/*.json`. Candidates: `github-dark`, `one-dark`, `solarized-dark`.

- **Internationalization (i18n)** — UI localization (active Czech user base). `gettext`-based; `utils/i18n.py`; `locale/<lang>/LC_MESSAGES/idol.po + .mo`; language setting in `~/.idol/settings.json`; auto-detect OS locale; hot-swap via `retranslate_ui()`. Use a dedicated `feature/i18n` branch — touches every file.

### Designer — Save / Discard / Snapshot

Right now codegen runs silently on every change. Needs an explicit save/discard cycle:

- **CRC snapshot on entry** — capture a CRC of `.form.json` + `.py` on designer start; again after each explicit save
- **Discard on exit** — if CRC differs, prompt Save / Discard / Cancel when switching away or closing; discarding reverts both files to snapshot
- **Context-aware menu label** — `Designer → Save Form` vs `Designer → Save Dialog`
- **Undo stack hook** — investigate whether snapshot baseline can be derived from the undo stack bottom
- **Needs a full planning session** — design the lifecycle (where stored, when cleared, edge cases: new form, delete form, rename) before writing any code

---

## 📦 Planned — Components

### Next Candidate Components

1. **Database** — `sqlite3`; props: DatabaseFile; handlers: `_open_db` ⚡, `_close_db` ⚡, `_execute` ⚡, `_on_results`
2. **"Me" proxy** — opt-in VB-style window wrapper (`back_color`, `fore_color`, `hide()`, `show()`, `controls` dict, etc.)

### Dialog Helper Injector

A right-click option on linked dialog rows in the FORMS tree opens a picker listing opt-in helper methods to inject into the parent form class. Each helper is a preserved event stub (body survives regen).

| Helper | What it does |
|---|---|
| `_new_Dialog1()` | Destroy + recreate — full state reset |
| `_show_Dialog1()` | Alias for `_open_Dialog1` — `deiconify()` |
| `_hide_Dialog1()` | Programmatic hide — `withdraw()` |
| `_center_Dialog1()` | Center over parent window |
| `_on_Dialog1_result(data)` | Callback stub for dialog→parent data passing |

---

## 🔢 Planned — Variable & Data

- **"Used By" reverse lookup** — Variable Picker shows usage count badge; hover lists bound widgets; click navigates canvas to that widget (gold border highlight)
- **Global Variable Rename** — rename in picker → prompt to update all form.json + generated code references
- **Type-safe variable filtering** — only show compatible var types per widget slot
- **Variable Tracing / Variable Events** — wire `trace_add("write", ...)` from Events tab; codegen emits trace setup + stub

---

## ⚙️ Planned — Code Generation

- **Code Repair mode** — if IDOL:BEGIN/END markers are deleted, detect and append orphaned user code to the bottom of the file instead of discarding it silently
- **Validation substitution tooltips** — status bar hints for `%P`, `%S`, `%W` in --args rows
- **Menu Item Proxies** — generate `MenuProxy` class per item so users can write `self.mnu_file.enabled = False` instead of `entryconfig` gymnastics

---

## 🌐 Long-Term Ideas

### `canvas_codeview.py` Decomposition — Code Cleanup Session

`canvas_codeview.py` has grown to ~10 distinct widgets/subsystems crammed into one file. Needs a dedicated cleanup session — audit codebase against CONTRIBUTING.md conventions at the same time.

**Proposed split:**
| File | Contents |
|---|---|
| `widgets/canvas_codeview.py` | Core render loop, cursor, selection, key dispatch |
| `widgets/canvas_editor/tokenizer.py` | `_rules`, `_scan_triple_state`, `_tokenize*` |
| `widgets/canvas_editor/fold.py` | `folded`, `_fold_end`, `_toggle_fold`, fold rendering |
| `widgets/canvas_editor/multicursor.py` | `_mc_cursors`, `_mc_anchors`, `_mc_apply_key`, `_mc_shift_same_line` |
| `widgets/canvas_editor/autocomplete.py` | Completion popup, LSP trigger, filtering |
| `widgets/canvas_editor/minimap.py` | Minimap canvas, dirty tracking, click-to-scroll |
| `widgets/canvas_editor/gutter.py` | Line numbers, breakpoints, git-hunk margin |
| `editor/bracket_matcher.py` | Dead code — uses `tk.Text` API; either port or delete |

**Prerequisites:** no active features being built on `canvas_codeview.py`; full test pass before/after; one file at a time with syntax check after each move.

**Also clean up:** `editor/bracket_matcher.py` (dead code — still instantiated in `app.py` but not wired to canvas editor events); memory file maintenance; CONTRIBUTING.md audit pass.

### Canvas-Virtualized Side Panel Renderer
Replace Frame/Label widget trees in sidebar panels with a single `Canvas` per section — only repaint visible rows, `create_text`/`create_image` items, `tag_bind` interaction.
- Zero widget teardown = zero flicker; handles 10k-row lists; smooth expand/collapse
- Pilot: **Clipboard History** (already done); migrate Outline → References → Source Control → Explorer
- **Showcase milestone** — proves Tkinter can produce virtualized, sub-ms-repaint UI on par with Electron; a direct rebuttal of the "Tkinter can't do real UI" myth

### IDOL Custom Widget Library
Curated palette of production-quality canvas-drawn widgets that ship with IDOL and appear in the Designer palette.
- `IDOLListView` — sortable, filterable list with column headers
- `IDOLCard` — rounded-corner card with drop shadow + title bar
- `IDOLBadge` — pill-shaped colored label (status / tag / severity)
- `IDOLToast` — slide-in/out notification overlay (success / warning / error)
- `IDOLToggle` — animated iOS-style toggle switch
- `IDOLProgressRing` — circular indeterminate / determinate indicator
- `IDOLSearchBox` — styled search entry with × clear + animated placeholder
- Distribution: `widgets/idol_components/`; codegen emits `from idol_components import ...`

### Other
- **Import / Export project** — `.idolpkg` zip bundle (source, form.json, requirements.txt, manifest); import wizard with package checklist, interpreter mismatch warning, git init / remote-pull options
- **Grid / Pack layout mode** — drag-first canvas with auto-detected grid/pack lane overlay; columnspan/rowspan by dragging across cells
- **Debug Log tab** — passive trace of variable values and line numbers during debugpy sessions; reviewable after execution
- **Code peek on canvas hover** — 2s hover shows handler code preview popup; no click required
- **Multi-framework support** — PySide6 / PyQt6 backend alongside Tkinter; framework selected at wizard time; model.py already framework-agnostic; hard part is layout (absolute setGeometry first, then layout-aware mode)
- **Bidirectional designer ↔ code sync** — very long term
- **Learning Mode in Designer** — hover-driven explanations when F1 is active; needs interaction model design before code
- **Floating sticky-note mini editor** — mini panel that auto-grabs selection, stays on top, with copy helpers
- **Canvas File Dialog** — replace OS file picker with dark-theme IDOL dialog; same dialog reused for Open Form, Save Form, Export Project, Save As

---

## 🔧 Git Workflow (established practice)

Multi-session features use a dedicated branch merged into master when complete:
```
git checkout -b feature/my-big-thing
# ... commit freely ...
git checkout master && git merge feature/my-big-thing
git branch -d feature/my-big-thing && git push origin --delete feature/my-big-thing
git fetch --prune
```
Use a fresh name for each new feature branch (don't reuse merged names). Master stays stable; the feature diff is always visible with `git diff master...feature/my-big-thing`.

---

## 🐛 Known Bugs

- ~~macOS: 20px canvas/codegen offsets need audit~~ — CONFIRMED NOT AN ISSUE (2026-05-11): macOS handles offsets natively, no code changes needed
- **Linux:** IDOL window maximize state has a visible flash on restore — WM session management re-maximizes asynchronously; `_force_normal` at 300 ms fights it but can't eliminate the flash; accepted limitation
- **Debugger:** global hotkeys (F5/F10/F11/Shift+F11/Shift+F5) need a low-level keyboard hook (pynput or keyboard lib) to fire when IDOL doesn't have focus; hook installed only during active debug session
- **Codegen:** removing the last widget reference to a handler method silently drops its body on next regen; should warn "handler `_on_x` has a body but nothing calls it — remove?"
- **Codegen:** `_`-prefixed methods with decorators (e.g. `@staticmethod def _helper()`) lose their decorator on regen — event stub bodies are extracted separately and the `def` line is rebuilt by codegen, so decorator info is never captured. Uncommon pattern for event handlers but worth fixing eventually; would require plumbing decorator data through `extract_event_bodies` and `generate()`.

---
---

# ✅ Completed — Historical Record

---

## Phase 1 — Core IDE — COMPLETE (2026-04-27)

**Core Editor**
- Multi-tab editing with session persistence (dirty tracking, restore hardening, _restoring flag + 400ms cleanup pass)
- Pygments syntax highlighting → migrated to custom canvas-based tokenizer (see Canvas Editor below)
- Multi-cursor editing: Alt+Click to add/remove; Shift+Arrow independent per-cursor selections; Ctrl+C copies all; smart pairs and bracket matching at every cursor
- Line move/duplicate: Alt+Up/Down moves current line or selected block; Shift+Alt+Down duplicates below
- Split editor with scroll sync and scroll lock (hardware Scroll Lock key synced on startup)
- Minimap, sticky scroll, fold markers
- Breadcrumb bar: path crumbs, symbol crumbs, sibling picker, locals drill-down, marquee scroll footer
- Find/Replace; Ctrl+/ comment toggle; word occurrence highlights
- Zen mode (F10), sidebar toggle (Ctrl+B)

**LSP & Diagnostics**
- pylsp integration: hover, diagnostics, definition, completion
- Problems panel: PROBLEMS tab in bottom bar, colored severity dots, click to jump to line/col
- Diagnostic statusbar badge: live ✕N ⚠N, clickable to open Problems panel
- Dual-track error engine: ruff subprocess + compile() fallback on debounced background thread
- Three-tier diagnostic severity: red (error) / yellow (warning) / blue (info/hint)
- Runtime error indicators: amber gutter arrow, line highlight, Problems tab flash on run failure
- Problems panel AI: Ask AI button; double-click for explanation; hover tooltips with ruff rule descriptions

**Git**
- Source control panel: staging, unstaging, commit, push, diff view, virtual rendering for large file lists
- Git health panel: smart warnings, fix wizard, `.gitignore` creation
- Commit History panel: last 50 commits, file diff on click, filter bar, load more
- Git guides: install, identity (git config + GitHub account + `gh auth login`), remote, first commit
- Git ahead/behind statusbar: `⎇ branch ↑N ↓N` indicator via async `rev-list --left-right --count`

**Terminal**
- Integrated PTY terminal (pyte VT100 screen buffer); real PTY via `pty` / `winpty`
- Venv detection with activate/deactivate/switch toolbar; re-activated automatically on next launch
- Terminal debug mode: launch debugpy in terminal, attach DAP client
- Output panel: copy button and right-click context menu; inline stdin bar for `input()` support

**Run & Debug**
- Run Line / Run Selection; VS Code-style split run button
- Integrated Python debugger: debugpy over DAP; bundled debugpy injected via PYTHONPATH
- Breakpoints: hover ghost dot + bright active dot; persist; auto-shift on line insert/delete; restore on undo/redo
- Floating debug panel: dock/undock, always-on-top; LOCALS + BREAKPOINTS subpanels
- Step controls: Continue (F5), Step Over (F10), Step Into (F11), Step Out (Shift+F11), Stop (Shift+F5)

**AI**
- AI Chat panel: Ollama/qwen2.5-coder, session history, token counter, remote host config, animated "Thinking…" dots
- Learning Mode (F1): hover any IDE element for three-section explanations with AI Ask button; custom cursor
- Ask AI integration in Problems panel

**Project & Config**
- Project setup wizard: 4-step (name/location, interpreter/venv, git/starter files, summary)
- Interpreter statusbar segment: click to pick; persists per project root; venv re-activated on next launch
- Run entry file selector in statusbar (▶ Active Tab or ▶ filename)
- Session persistence: open tabs, layout, appearance, breakpoints, active interpreter, active venv
- Project lifecycle: new / open / close with full teardown

**Navigation & UI**
- Command palette (Ctrl+Shift+P): fuzzy search, `@` symbol search, `!pip` mode
- Explorer: rename, delete, drag/drop file/folder, new file/folder, context menus
- Outline panel with locals drill-down; References panel; GuideWindow system
- Welcome tab: Quick Actions, Recent Projects/Files, live CHANGELOG viewer, rotating tips
- Clipboard History (Ctrl+Shift+H): canvas-virtualized ring buffer of 50 entries; pinned entries; keyboard nav

**Package Manager**
- Pip Package Manager (F3): PyPI topic grouping, live filter, PyPI search, install/uninstall, AI examples
- `!pip` command in command palette with package name autocomplete

---

## Phase 2 — IDOL Designer — COMPLETE (2026-05-05)

- Mode switcher: [Editor] / [Designer] per project; hidden for CLI projects
- Widget palette with canvas-drawn previews (14 → 16 widget types)
- Drag/drop placement, 8-handle resize, rubber-band multi-select, copy/paste, z-order, undo/redo (50 states)
- Properties panel: color pickers, state dropdown, validate dropdown, font picker, control selector, variable binding, inline list editor, anchor picker, image picker (PIL)
- Events tab: auto-wire ✦, name-prefix warning, ? Events guide, handler picker ▾, readonly rows for canvas_button
- **Handler picker** — `HandlerPickerEntry` in Events tab + Menu Editor; lists all handlers on the form with live preview
- Handlers tab: Available/Connected split, ⚡ connector, form handlers + component handlers, × disconnect, … options
- Order tab: drag-to-reorder z/tab sequence; Notebook tab grouping
- Code generation: full preservation of event bodies, signatures, pre/post-init zones, helper methods, user imports; auto-save .py before regen
- Auto-regen debounce (1.5s); Ctrl+Shift+G manual trigger
- Widget containment: Frame/LabelFrame/Notebook auto-parent; drag-out to reparent; container cascade delete
- Menu Builder (VB6-style): Caption/Name/Shortcut, Command/Check/Radio types, variable picker, handler picker; codegen with add_checkbutton/add_radiobutton, `self.bind()` for shortcuts
- Full widget property coverage: wraplength, onvalue/offvalue, selectmode, char_width/height, resolution, tickinterval, increment, labelanchor, scrollbar, Spinbox values-list mode, and more
- All 41 widget property keys have status-bar hover descriptions (`_PROP_HINTS`)
- Canvas visual pass: disabled state, password dots, Listbox values, Progressbar stripes, relief rendering
- Form events: load / activate / deactivate / unload / resize with codegen + stubs
- Form background image: `image` property; renders at natural size behind dot grid; PIL check + warning row
- Canvas `border` property (True/False): when False emits `highlightthickness=0, bd=0`

### Widget Anchoring + Alignment Toolbar — COMPLETE (2026-05-07)

- **Widget anchoring**: 9-mode anchor picker; live repositioning during form resize; Shift+resize suppresses; codegen emits `_apply_anchor_layout()`
- **Alignment Toolbar**: Align L/R/T/B/H/V; Distribute H/V (grid-aware); Same Width/Height; Undo/Redo/Copy/Paste; buttons dim when action doesn't apply
- **Multi-placement mode**: palette tool stays armed; Escape / click outside / Pointer de-arms
- **Smart placement cursor**: crosshair (empty area), arrow (unselected widget), fleur (selected widget)
- **Draw-to-size placement**: drag on canvas to define bounding box; plain click drops at default size
- **Palette drag-and-drop**: drag widget type from palette to canvas; ghost label follows cursor
- **Snap-to-grid** (⊞) toggle; **Show/hide grid** (⋯) toggle; **Tab order** (⇥) toggle
- **Grid Layout popup** ⊡: Make Grid + H/V nudge controls; dismisses on outside click or app focus loss
- **Ghost sash fix**: editor/output PanedWindow sash uses `sashpos()` proximity — was failing on Windows

### Multi-Form Designer — COMPLETE (2026-05-08)

- Multi-form support: Main (`tk.Tk`) + Dialog (`tk.Toplevel`) forms; each has its own `.form.json` + `.py`
- FORMS tree panel: main forms at top level; linked dialogs indented; unlinked dialogs in dim section
- Form switching: click to save current + load selected; `×` unlink button on hover
- Drag-to-link: drag dialog row onto main form row; 5px threshold; ghost tooltip follows cursor
- New Form dialog: name entry, Main/Dialog type, Link-to dropdown; creates `.form.json` + `.py` immediately
- Dialog codegen: `tk.Toplevel` subclass; `__init__(self, parent, **kwargs)` + `self.withdraw()`; `WM_DELETE_WINDOW` → `_on_close` (preserved stub, default body `self.withdraw()`)
- Dialog instances stored on parent: `self.dlg_DialogName = DialogName(self)` in IDOL:BEGIN block
- `IDOL:DIALOG_IMPORTS` zone: auto-managed from `linked_dialogs` on every codegen run
- Multi-form codegen order: dialogs generated before main forms so imports resolve
- Canvas scroll offset fix: `canvasx()`/`canvasy()` used for resize handles and rubber-band

### Designer Phase 3 — Linux / Cross-Platform Polish (2026-05-10)

- `grab_set()` ordering fix; `StyledCheckbox` extracted to `widgets/styled_checkbox.py`
- X11 saved-iid pattern in `designer_properties.py` (spurious `<Leave>` events)
- Form `bg` clearable; empty bg defaults in registry; tkinter clipboard (replace pyperclip)
- Linux mousewheel on designer canvas; cross-platform UI font (`utils/ui_font.py`)

### Canvas Editor Full Migration (2026-05-13 to 2026-05-19)

- **Canvas-rendered code editor** — complete rewrite from `tk.Text` + Pygments to custom canvas-based engine. All state in `self.lines: list[str]`; cursor + selection are plain `(line, col)` tuples; tokenization via regex-rule pass.
- Themes via `themes/*.json` with live switching; horizontal scroll; scope-bounded indent guides; undo/redo with coalescing; Shift+Tab unindent; multi-cursor (Alt+Click); breakpoints + git-hunk gutter; autocomplete + LSP wired; all right-click menu items at full parity
- Go to Definition (F12): local buffer scan first, LSP fallback, LocationLink support, URI percent-encoding
- **5 bundled themes**: Dracula, Nord, GitHub Light, Solarized Light, Dainty (7 total)
- Legacy `tk.Text` editor removed; Pygments removed from requirements.txt

### Canvas Editor & Designer Polish (2026-05-22 to 2026-05-25)

- **Set as Main**: right-click / double-click FORMS row; writes `main.py` with IDOL marker; pins ▶ run entry; shows **▶ FormName** in teal
- Session persistence: designer state (open forms, active canvas, Set as Main) saved and restored
- Auto-load linked dialogs: Open Form scans source directory for linked sidecars; copies + loads them
- **Designer codegen**: trailing comment lines in handler bodies preserved on regen; `self.focus()` after dialog `__init__` calls

### Image Support + Socket Component (2026-05-26)

**Image support (Label, Button, Canvas widget)**
- 16th palette type: Canvas (tk.Canvas, 200×150, bg + image + sizing + border props)
- `image` prop on Label, Button, Canvas: file picker, auto-copy to `images/`; PIL thumbnail in `_img_cache`
- `compound` prop for Label/Button; anchor-aware resize codegen
- PIL warning row: amber ⚠ installs Pillow via PipManager with streaming output

**Socket non-visual component**
- Server/Client setup dialog + three scaffold kits (Connect/Disconnect, Chat, File Transfer)
- Length-prefix framing (`struct.pack('>Q', size)`) when File Transfer scaffold active
- All I/O on daemon threads; `self.after(0, ...)` for tkinter updates
- Server/client mode filtering via `applies_to_modes` on `ComponentHandlerDef`

### Phase 3 — IDOL Components (2026-05-16 → 2026-06-03)

**Architecture:** `designer/component_registry.py` (ComponentDef, PropDef, ComponentHandlerDef + COMPONENT_REGISTRY), `ComponentDescriptor` in `designer/model.py`, `widgets/designer_component_tray.py` (chip strip), `widgets/designer_connector.py` (⚡ wiring dialog).

- ✅ **Timer** (2026-05-16) — `self.after()` periodic callback. Props: Interval, Enabled. Handlers: `_tick`, `_start` ⚡, `_stop` ⚡
- ✅ **CommonDialog** (2026-05-22) — open/save/dir/color/input/messagebox wrappers. Selective imports. `parent=self` on all calls.
- ✅ **Socket** (2026-05-26) — TCP server/client on daemon threads. Three scaffold kits. Length-prefix framing.
- ✅ **Image** (2026-06-03) — Named image references. Multi-file picker → single `PhotoImage` or `{stem: PhotoImage}` dict. Tray chip shows PIL thumbnail + ×N badge; hover gallery popup. `canvas_button` handler ⚡ opens Image Button Builder (canvas picker, Normal/Hover/Pressed dropdowns, x/y, tag name, auto-size checkbox, live preview). Codegen: `create_image + tag_bind` in `_build_ui`; `_down/_up/_enter/_leave` generated; `_click` user stub. Ghost preview on designer canvas. Connected/edit on both sides. Canvas Events tab shows readonly event rows.

### 2026-06-03 to 2026-06-04 — Canvas Polish & Bug Fixes

**Added:** Form background image property; Show/hide grid toggle (⋯); Canvas `border` property; all 41 widget prop hints; Canvas events corrected to `_SIMPLE_EVENTS + _KEY_EVENTS`; auto-save .py before codegen (`_autosave_form_py`)

**Fixed:** Props hover IndexError; paste order (set → ordered form.widgets iteration); paste offset drift (reset on move drag); tab badges after delete/paste; gallery + grid popups dismiss on app focus loss; canvas_button Events tab deduplication (inline in existing row, not appended); designer canvas focus_set on mode enter; widget deletion cleans up canvas_button wires and orphaned handler_wires
