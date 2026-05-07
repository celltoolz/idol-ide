# IDOL Roadmap

This document tracks completed milestones, work in progress, and the planned feature backlog.

---

## Phase 1 — Core IDE — COMPLETE (2026-04-27)

- Session restore hardening and dirty-tab tracking
- Project lifecycle: new / open / close with full teardown
- Run entry file selector in statusbar
- Statusbar: Ln/Col, branch indicator, error count
- Learning Mode (F1), interpreter selector, run entry selector

---

## Phase 2 — IDOL Designer — COMPLETE (2026-05-05)

- Mode switcher: \[Editor\] / \[Designer\] per project
- Widget palette with canvas-drawn previews (14 widget types)
- Drag/drop placement, 8-handle resize, rubber-band multi-select, copy/paste, z-order
- Properties panel: color pickers, state dropdown, validate dropdown, control selector
- Events tab: auto-wire, name-prefix warning, ? Events guide
- Variable binding (StringVar / IntVar / DoubleVar / BooleanVar) + Variable Picker popup
- Code generation with full preservation: event bodies, signatures, pre/post-init zones,
  helper methods, user imports (IDOL:IMPORTS markers)
- Menu Builder: caption/name/shortcut, enabled/visible, type, variable, command, value;
  indent/insert/delete; codegen with add_checkbutton/add_radiobutton and auto self.bind()
- Widget containment: Frame/LabelFrame auto-parent dropped widgets; drag-out to reparent
- Inline list editor, color swatches, hover hint bar, × clear buttons, ✦ auto-wire
- Full widget property coverage: wraplength, onvalue/offvalue, selectmode, char_width/height,
  resolution, tickinterval, increment, labelanchor, Spinbox values-list mode, and more
- Canvas visual pass: disabled state, password dots, Listbox values, Progressbar stripes
- Form events: load / activate / deactivate / unload / resize with codegen
- Double-click event row → jump to handler in editor
- Ghost sash drag (blue line, resize on mouse-up only)
- Startup and AI-chat sash flash eliminated (pre-size from saved session)

---

## In Progress

### Widget Anchoring + Alignment Toolbar
Proportional scaling system for resizable place-geometry forms.

- **Anchor property per widget** — modes: None, Left/Right stretch, Top/Bottom stretch,
  Bottom-Right pin, All (scale proportionally)
- **3×3 Anchor Grid UI** in Properties panel — click edges to toggle axes independently
- **Codegen**: auto-emit `_on_resize` handler using stored original geometry + ratios
- **Alignment Toolbar** in canvas strip:
  - *Alignment*: Align Lefts / Rights / Tops / Bottoms, Center H/V
  - *Distribution*: Equal H/V spacing, Remove spacing (snap edge-to-edge)
  - *Sizing*: Same Width, Same Height
  - *Grid*: Snap-to-grid toggle (8px)

---

## Planned — Designer

- Font picker for text-bearing widgets
- Anchor / justify dropdowns
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
