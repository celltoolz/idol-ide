# IDOL Roadmap

This document tracks completed milestones, work in progress, and the planned feature backlog.

---

## Phase 1 — Core IDE — COMPLETE (2026-04-27)

**Core Editor**
- Multi-tab editing with session persistence (dirty tracking, restore hardening, _restoring flag + 400ms cleanup pass)
- Pygments syntax highlighting
- Multi-cursor editing: Alt+Click to add/remove; Shift+Arrow independent per-cursor selections; Ctrl+C copies all; smart pairs and bracket matching at every cursor; click-placement aligned to nearest character boundary *(re-implemented in canvas engine 2026-05-25 — see Canvas Editor section below)*
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

## Canvas Editor & Designer Polish — SHIPPED (2026-05-22 → 2026-05-25)

**Canvas Editor**
- **Multi-cursor** — Alt+Click adds/removes secondary `|` cursors; all blink in sync with the primary; edits processed bottom-to-top; secondary selections rendered; Escape clears. Implemented entirely in `canvas_codeview.py` (`_mc_cursors`/`_mc_anchors` lists)
- **LSP hover re-wired** — `<Motion>`/`<Leave>` bound on `cv.canvas` in `_new_tab` and `_new_tab_in`; `_do_hover` uses `_coords_from_pixel()` instead of `tk.Text.index()`
- **5 new bundled themes** — Dracula, Nord, GitHub Light, Solarized Light, Dainty (7 total)

**Designer — Session & Forms Management**
- **Set as Main** — right-click or double-click a main form row; writes `main.py` with IDOL marker, pins ▶ run entry, shows **▶ FormName** in teal in the FORMS panel
- **▶ indicator sync** — tracks the active run entry file (IDOL marker / stem match) and the active editor tab in Active Tab mode; updates live on tab switch and designer re-entry
- **Session persistence** — designer state (open forms, active canvas, Set as Main) saved and restored across restarts; `designer_was_active` gates the restore path
- **Auto-load linked dialogs** — Open Form path scans the source directory for linked dialog sidecars and copies + loads them alongside the parent
- **Open .py on form load** — switching forms in the FORMS panel opens the companion `.py` as an editor tab (prefers CWD copy)
- **Missing forms in red** — session-restored forms not found on disk shown in red with tooltip; removable via right-click
- **FORMS tree X behavior** — X on a main form removes it (and linked dialogs) from the designer with confirmation; X on a linked dialog unlinks it; canvas clears when the last form is removed
- **Wizard → ▶ indicator** — `_on_project_created` sets `_designer_main_form` so the ▶ appears immediately after wizard completion; generated `main.py` carries the `# Generated by IDOL Designer` marker

---

## Next Up — Priority Bug & Feature Queue

> Start here when picking up the next session. Items are roughly in order of priority.

### Bugs — Fix First

- ~~**Zen mode → Designer kills statusbar**~~ — FIXED.

- ~~**Go to Definition not working**~~ — FIXED (2026-05-16): local `def`/`class` scan handles same-file refs (covers `self.xxx` that pylsp/jedi fails on); LSP fallback for cross-file/stdlib; `uri_to_path` now URL-decodes `%20` so paths with spaces navigate correctly; `path_to_uri` now percent-encodes outgoing URIs.

- ~~**Highlight Active Line / Active Line Color broken**~~ — FIXED: canvas engine always drew the band from `self._palette["current_line_bg"]`; `view_toggle_highlight` and `view_active_line_color` both wire correctly into `cv.highlight_active_line` / `cv._active_line_color`.

- ~~**Editor right-click menu**~~ — FIXED: replaced with new-style IDOL canvas-drawn popup; `Find && Replace` label corrected.

- ~~**Find & Replace — pre-populate from caret word**~~ — FIXED: caret word inserted and selected on Ctrl+F open.

- ~~**Canvas editor undo/redo**~~ — FIXED (2026-05-15): 200-entry stack on `self.lines` + cursor + selection; same-type coalescing (char insert, backspace, forward-delete); all mutation paths covered; Ctrl+Z/Y + `<<Undo>>`/`<<Redo>>` virtual events; Edit menu items dim when stack is empty.

- ~~**References panel — tab-aware navigation**~~ — FIXED (2026-05-15): clicking a result switches to the correct open tab (or opens the file) and positions the caret at the exact column of the matched word.

### Features

- ~~**Canvas lexer — call-site coloring**~~ — FIXED (2026-05-15): constructor call sites (e.g. `IDOL(...)`) and keyword argument keys render teal, matching VS Code's Python color scheme.

- ~~**File → Open Project opens into explorer root**~~ — FIXED (2026-05-15): Open Project dialog now defaults `initialdir` to the current explorer root.

- **Designer save / discard / snapshot** — right now codegen runs silently on every change;
  we need an explicit save/discard cycle so users can exit without committing edits:
  - **Context-aware menu label** — `Designer → Save Form` when a main form is active,
    `Designer → Save Dialog` when a dialog is active
  - **CRC snapshot on entry** — capture a CRC of the `.form.json` + `.py` on designer start
    (and again after each explicit save) so we know whether there are unsaved changes
  - **Discard on exit** — if the CRC differs, prompt "Save / Discard / Cancel" when switching
    away from designer mode or closing the project; discarding reverts both files to the
    snapshot state
  - **Applies to both files** — snapshot must cover the `.form.json` sidecar *and* the
    generated `.py`; a partial save is not useful
  - **Undo stack hook** — the designer undo stack is already implemented; investigate whether
    the snapshot baseline can be derived from the stack bottom rather than a separate CRC file
  - **Needs a full planning session** — do not implement ad-hoc; design the snapshot
    lifecycle (where stored, when cleared, edge cases: new form, delete form, rename) before
    writing any code

- **Settings menu** — `View → Settings` (or `Edit → Settings`) panel consolidating per-user preferences that are currently scattered or missing UI:
  - Font (family / size / bold / italic) — currently only reachable via `View → Change Font`
  - Theme — currently only via `View → Theme`
  - Highlight active line (on/off)
  - Active line color (color picker)
  - Autocomplete on/off, smart pairs on/off
  - Tab size
  - (Future) LSP on/off, ruff on/off
  Settings write to `~/.idol/settings.json` and apply live.

- **Replace `tkfontchooser`** — drop the external dependency; build a native IDOL font chooser dialog (needs to work on Windows, macOS, Linux):
  - Left: scrollable `Listbox` of system fonts (use `tkfont.families()`); filter entry at top
  - Center: Size entry + Bold / Italic checkboxes
  - Right: live preview label (`"The quick brown fox…"`) in selected font
  - OK / Cancel buttons; result tuple `(family, size, weight, slant)` matches current `set_font()` API
  - Replace all current `tkfontchooser` call sites in `designer/properties.py` and the View → Change Font dialog

- **Custom color chooser** — replace the default `tkinter.colorchooser` with a native IDOL dialog (the default is the OS picker: great on Windows, a bare RGB slider on Linux):
  - Color wheel or HSV square (canvas-drawn)
  - R/G/B sliders with numeric entries
  - **Hex value entry** (type `#FF00AA` directly)
  - Old / New color preview swatches
  - OK / Cancel; same return signature as `colorchooser.askcolor`
  - Hook into Designer Properties color rows and the new Settings panel active-line color

- **Editor fg/bg color hover** — hovering over a string literal that is a valid hex color (e.g. `"#FF00AA"`) should show a small color swatch popup/tooltip and optionally open the IDOL color chooser on click, similar to VS Code's color provider. The canvas editor already renders inline color swatches — extend this to be interactive.

- **More bundled themes** — add 2–3 popular themes as `themes/*.json` entries. Candidates: `github-dark`, `one-dark`, `solarized-dark`. Not blocking — add alongside other work.

### Git Workflow (established practice)

Multi-session features use a dedicated branch merged into master when complete:
```
git checkout -b feature/my-big-thing   # create + switch
# ... commit freely ...
git checkout master && git merge feature/my-big-thing
git branch -d feature/my-big-thing && git push origin --delete feature/my-big-thing
git fetch --prune
```
Use a fresh name for each new feature branch (don't reuse merged names). Master stays stable; the feature diff is always visible with `git diff master...feature/my-big-thing`.

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

## Terminal & Editor Polish (2026-05-15 / 2026-05-16)

**Terminal**
- **Alternate screen buffer (DEC 1049)** — vim, nano, htop, less, mc enter and exit cleanly without corrupting scrollback history
- **Full mouse forwarding** — click, release, drag, and right-click forwarded as SGR mouse sequences when TUI apps enable mouse mode; wheel scroll sequences also forwarded; scroll falls back to scrollback when mouse mode is off
- **Extended TUI key map** — Ctrl+Arrow, Shift+Arrow, Alt+Arrow, and Insert forwarded as correct escape sequences; covers tmux pane switching, text selection, and file manager nav in TUI apps
- **Auto-scroll pin for repainting TUI apps** — Rich Live tables, Textual, and other cursor-up-repaint apps are viewport-pinned to the redrawn block's top border; bottom-pin preserved for PSReadLine / prompt output
- **OSC 133-gated startup** — rendering suppressed until the injected hook fires its first OSC 133 prompt event; 3-second fallback fires if the hook never arrives; eliminates startup noise on Windows
- **Git Bash on Windows** — launched with `--login -i` so `/etc/profile` populates MSYS2 PATH; `MSYSTEM=MINGW64` injected; cygpath canary check injects `/usr/bin` when MSYS2 runtime skips conversion
- **Venv activation on Windows (Git Bash)** — `Scripts/activate` bypassed (requires Cygwin); `VIRTUAL_ENV` and `PATH` set directly in MSYS2-compatible form
- **Venv activation on Windows (PowerShell)** — `Set-ExecutionPolicy -Scope Process Bypass` prepended so unsigned `Activate.ps1` runs without policy changes
- **Double-activation guard** — flag prevents both the terminal auto-activate and app-level pending venv path from firing on the same session startup
- **TUI column-cell rendering** — box-drawing and non-ASCII glyphs rendered per cell within column width, eliminating drift in table borders at high character widths

**Canvas Editor**
- **Undo / Redo** — 200-entry stack on `self.lines` + cursor + selection; consecutive same-type ops coalesce; all mutation paths covered; Ctrl+Z/Y + `<<Undo>>`/`<<Redo>>` virtual events; Edit menu dims when stack is empty
- **Shift+Tab unindent** — removes up to `tab_size` leading spaces from the current line or every line in the selection
- **Active line highlight / color wired live** — `View → Highlight Active Line` and `View → Active Line Color` now apply immediately to all open canvas codeviews (previously stubs)
- **Right-click context menu** — replaced native `tk.Menu` with IDOL-style dark overlay; two-column label+shortcut layout; Go to Definition disabled when LSP is not ready
- **Find & Replace pre-populates from caret word** — when no selection exists, the identifier under the caret is inserted and selected in the search field on Ctrl+F open

**Go to Definition**
- **Local buffer scan** — scans current buffer for matching `def`/`class` first (no LSP round-trip); covers same-file refs that pylsp/jedi often misses
- **LSP fallback** — fires only when local scan fails and LSP is connected and ready
- **LocationLink support** — accepts both `Location` and `LocationLink` LSP response formats
- **URI percent-encoding** — incoming URIs decoded, outgoing URIs encoded; paths with spaces and special chars now navigate correctly
- **F12 binding** — global app-level `<F12>` binding added

**Other**
- **References panel** — tab-aware navigation; clicking a result switches to the correct open tab and positions caret at the exact match column
- **Lexer** — constructor call sites and keyword argument keys render teal, matching VS Code's Python color scheme
- **Designer codegen** — trailing comment lines in handler bodies now preserved on regeneration; `self.focus()` emitted after all dialog `__init__` calls to restore main window focus

---

## Phase 3 — IDOL Components (Timer 2026-05-16 · CommonDialog 2026-05-22)

VB6-style non-visual components placed in a chip tray below the canvas. Click a component in
the palette COMPONENTS section to add it; the tray shows icon+name chips; selecting a chip
shows its properties and handlers in the Properties panel; codegen emits init variables and
handler stubs into the generated `.py`.

**Architecture:** `designer/component_registry.py` (`ComponentDef`, `PropDef`,
`ComponentHandlerDef` + `COMPONENT_REGISTRY`), `ComponentDescriptor` in `designer/model.py`,
`widgets/designer_component_tray.py` (chip strip), `widgets/designer_connector.py` (⚡ wiring
dialog). Component handlers are underscore-prefixed methods so `extract_event_bodies()` in
`persistence.py` picks them up with no changes — user bodies survive regen automatically.
Wiring a handler to a widget event stores `widget.events[event_key] = method_name` — existing
codegen emits the `.bind()` call with no changes.

**Connector enhancements (2026-05-22):**
- Menu item wiring — the Connector lists non-cascade command menu items alongside widget events; wiring sets `MenuItemDescriptor.command_handler` so codegen emits the method reference directly instead of a `_{name}_click` wrapper
- Stub checker — connector suppresses the "already wired" overwrite warning when the existing handler body is only `pass` (reads the generated `.py` via regex; treats missing file as stub)
- Available Components sub-section is foldable (▶/▼ header, collapsed by default) and always shows all connectable handlers regardless of wiring state — handlers are reusable across multiple widgets and menu items
- Scroll offset fix — floating ⚡/×/… buttons now track correctly when the Handlers canvas is scrolled

**Shipped:**
- ✅ **Timer** — `self.after()` periodic callback (no threading, no locks). Props: Interval
  (ms), Enabled. Handlers: `_tick` (user logic), `_start` (⚡ connectable), `_stop` (⚡ connectable).
- ✅ **CommonDialog** — multi-mode wrapper around tkinter's built-in dialog functions; all five
  handlers independently wired (⚡ connectable to any widget event or menu item); each handler
  carries its own title; `_show_message` also carries message body and messagebox type. Handlers:
  `_show_open` (filedialog.askopenfilename), `_show_save` (asksaveasfilename),
  `_show_color` (colorchooser.askcolor), `_show_input` (simpledialog.askstring),
  `_show_message` (messagebox). Result stored in `_{id}_result`; callback stubs: `_on_file_selected`,
  `_on_color_selected`, `_on_input_received`, `_on_message_result`. Selective imports —
  codegen only emits `from tkinter import filedialog/colorchooser/simpledialog/messagebox`
  for handlers that are actually wired. All dialog calls pass `parent=self`.

**Candidate components (next up):**
1. **Socket** — `socket` module; props: Protocol (TCP/UDP), RemoteHost, RemotePort, LocalPort, State (readonly); handlers: `_connect` (⚡), `_listen` (⚡), `_send` (⚡), `_disconnect` (⚡), `_on_data_received`, `_on_connected`, `_on_error`
2. **Database** — `sqlite3`; props: DatabaseFile; handlers: `_open_db` (⚡), `_close_db` (⚡), `_execute` (⚡), `_on_results`
3. **"Me" proxy** — opt-in VB-style window wrapper (`back_color`, `hide()`, `show()`, `controls`, etc.)

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
