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
- **Unified codegen prompt** — single dark-themed dialog (replacing per-action confirmations) with per-session "don't ask again" suppress
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

## Planned — Designer

- Tab order panel — drag widgets in Outline tree to set Tab key sequence
- Toplevel / dialog form support (multi-form)
- Multi-form management panel — add / remove / import / export forms, easy switching
- Persist designer sash positions across sessions
- New Form / Add Form in designer menu
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

## Planned — Editor

- **Non-ASCII paste detection** — on paste, scan for `\xa0` / non-ASCII characters that cause
  silent Python syntax errors; flash a "Fix Encoding" button in the nav bar (no dialog)
- **Git ahead/behind status** — statusbar shows when local branch is behind the remote

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

---

## Long-Term Ideas

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

- macOS: fullscreen state not remembered across sessions
- macOS: 20px canvas/codegen offsets need audit after macOS testing session
- Debugger: global hotkeys (F5/F10/F11/Shift+F11/Shift+F5) require a low-level keyboard hook
  (pynput or keyboard lib) to fire when IDOL doesn't have focus
- Codegen: removing the last widget reference to a handler silently drops its body on regen
