# Changelog

All notable changes to **IDOL** are documented here, organized by development milestone.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — Treeview widget in the GUI Designer

### Added
- **`ttk.Treeview` is now a placeable designer widget.** Drop it from the palette like any other
  widget. `show` mode (`tree headings` / `headings` / `tree`), `selectmode` (`browse` / `extended`
  / `none`), and `scrollbar` (reuses the shared Frame + `ttk.Scrollbar` wrapping). The canvas
  renders a heading strip, the `#0` tree column when applicable, and three sample rows. Events
  `treeselect` / `treeopen` / `treeclose` are wirable.
- **Column Editor dialog** for the Treeview `columns` prop — per-column **id**, **heading**,
  **width**, **anchor** (left/center/right), and **stretch**, with add / reorder / remove. Column
  ids auto-derive a stable slug from the heading (and stay stable across renames). Columns are
  stored structurally (`list[dict]`); legacy plain-string column lists auto-migrate on load.
  A **tree heading** prop sets the `#0` tree-column heading. Codegen emits column ids in
  `columns=(…)` plus per-column `heading()` / `column(width=, anchor=, stretch=)` calls.

## [2026-06-17] — Canvas item events bind to the tag, not the instance

### Changed
- **Canvas-item event handlers are now named after the binding tag.** Wiring an event on a
  canvas item (e.g. a `CanvasImage` carrying the `button` tag) used to generate a handler named
  after the item instance (`_canvasimage1_mousedown`). It now derives the name from the tag the
  event is bound to (`_button_mousedown`), matching the tag-scoped `tag_bind` codegen emits.
- **Tag bindings propagate across every item sharing the tag.** Binding an event to a tag on one
  item now shows that handler under the Events tab of *every* canvas item carrying the same tag
  (read-only on the items that inherit it — the tag is the logical unit, not the individual item).
  Codegen already emits a single `tag_bind` per `(tag, event)`, so this also matches runtime
  behavior, where the binding fires for all items with the tag.

## [2026-06-17] — Autocomplete popup theming

### Changed
- **The autocomplete popup now follows the active theme.** Its colors were hardcoded dark
  (`#252526` / `#cccccc` / `#094771` / white), so the dropdown stayed dark-blue on light themes.
  It now pulls `sticky_bg` / `fg` / `select_bg` from the active palette (selected-row text uses
  `fg`, not white, so it stays readable on light themes' pale `select_bg`). Colors are reapplied
  on every show, so switching themes updates the cached popup too.

## [2026-06-17] — Multi-cursor shifted selection (Shift+Home/End et al.)

### Fixed
- **Shift+movement now extends every secondary cursor's selection on the first press.**
  `_mc_apply_key`'s shifted branch dropped the anchor but skipped the actual move on the first
  keystroke, so a secondary cursor lagged one press behind the primary — most visibly,
  **Shift+Home / Shift+End** appeared to do nothing. The shifted path now anchors (if needed)
  and always advances, matching the primary cursor in `canvas_codeview._on_key`. Affects
  Shift + Left/Right/Up/Down/Home/End/PageUp/PageDown for all secondary cursors; non-shift
  collapse-to-edge and plain movement are unchanged.

## [2026-06-17] — Public fold API

### Changed
- **`fold_all()` / `unfold_all()` are now public `CanvasCodeView` methods** (on `FoldMixin`).
  `app.py`'s View → Fold All / Unfold All commands previously reached into editor internals
  (`cv.lines`, `cv._line_is_foldable`, `cv.folded`, `cv.render`); they now call the public API,
  matching how the gutter and command palette drive the editor. No behavior change.

## [2026-06-17] — Status bar multi-cursor count

### Fixed
- **Status bar now shows the live multi-cursor count** — the cursor-count argument was
  hardcoded to `1`, so the documented `N cursors` indicator never appeared. The active-line
  loop now passes `cv.mc_count()`, so adding secondary cursors (Alt+Click) updates the status
  bar to `Ln x, Col y  |  N cursors`. The count was lost when the old `_multi_cursors` dict was
  removed in the P2 decomposition.

### Removed
- Dead `IDOL._update_cursor_status` — uncalled, and broken (it called `cv.index("insert")`, a
  `tk.Text` API the canvas editor doesn't implement). The 25 ms active-line loop already keeps
  the status bar current.

## [2026-06-17] — Fold-walk dedup: `iter_visible`

### Changed
- **One fold-skip walk instead of seven** — the inline loop that maps physical lines onto the
  visible rows (skipping folded blocks) is now a single `iter_visible(lines, folded)` generator
  in `canvas_editor/constants.py`. `FoldMixin._visual_to_physical`/`_visual_row_count`/
  `_visual_row_of` became thin adapters over it; `canvas_codeview.py` (`scroll_to_line`,
  `_ensure_visible`) and `minimap.py` (fold elision + scroll sync) now reuse those helpers
  instead of carrying their own copies. The render loop keeps its own walk — it has an extra
  `skip_close_char` bracket-inclusion rule the others don't. Behavior verified identical across
  53k+ checks over every fold-state subset of representative documents.
- **Fold-marker regexes moved to `constants.py`** — `_SECTION_MARKER`, `_IDOL_BEGIN_RE`, and
  `_IDOL_END_RE` now live in the constants leaf alongside `iter_visible` (which needs them).
  This retires the previous cross-mixin import exception: every fold-aware module now imports
  the shared vocabulary from `constants.py`, not from `fold.py`.

## [2026-06-16] — Gutter Pass A: GutterMixin extraction

### Changed
- **Gutter drawing extracted into `GutterMixin`** (`canvas_editor/gutter.py`) — the gutter's
  layout math (`_compute_gutter`), full-height background fill, per-row content (git stripe,
  breakpoint dot, line number, fold marker), and a shared line-number helper now live in their
  own mixin. The sticky-scroll band reuses the same line-number helper. Behavior is unchanged;
  gutter click/motion hit-testing stays in `canvas_codeview.py`'s mouse handlers.
- **Gutter color constants moved to `canvas_editor/constants.py`** — `_BREAKPOINT_COLOR`,
  `_BREAKPOINT_GHOST_COLOR`, and `_GIT_HUNK_COLORS` now live alongside the other shared editor
  constants so the new mixin can import them without reaching into `canvas_codeview.py`.

## [2026-06-11] — Editor Engine Decomposition (P3 audit)

### Added
- **Quote match highlighting** — placing the cursor on a quote now highlights its matching
  partner, alongside the existing bracket-pair highlight. Quotes are matched within the same
  line by a parity scan (opener and closer are the same character, so depth counting can't
  work); escaped quotes (`\"`) are ignored.

### Changed
- **Editor engine decomposed into six mixins** — tokenizer (syntax highlighting), folding,
  multi-cursor, bracket/quote matcher, minimap, and autocomplete each moved from
  `canvas_codeview.py` into single-responsibility modules in `widgets/canvas_editor/`. All
  editor state remains host-owned; mixins never import the host or each other.
- **Shared editing constants** extracted to `canvas_editor/constants.py` — auto-pair table,
  bracket/quote sets, editor font, minimap width — one definition instead of per-module copies.
- `canvas_codeview.py` shrank from ~3,900 to 2,690 lines (includes removal of dead gutter
  layout constants).

### Removed
- Dead, no-longer-imported editor modules: `editor/bracket_matcher.py`,
  `editor/key_handler.py`, `editor/multi_cursor.py`.
- `widgets/minimap.py` — the minimap now lives in the canvas editor's mixin package.

## [2026-06-11] — Maintenance: docs rewrite and memory cleanup (P4/P5)

### Changed
- **CONTRIBUTING.md rewritten** for the post-audit codebase — current architecture tables,
  the canvas-editor mixin package and its import rules, and the Definition of Done.
- `CLAUDE.md` converted from UTF-16 LE to UTF-8.

## [2026-06-08 to 2026-06-10] — Canvas Item Tags, Scaling & Font Fixes

### Added
- **Canvas-item tag system (two dialogs)** — tags now live in a per-canvas pool (`_canvas_tags`). **Canvas Tags** (Dialog A) manages the available pool (add/remove, protected `_bg` shown greyed); **Item Tags** (Dialog B) assigns pool tags to specific item(s) via a dropdown that picks one item or **All items**. Both are canvas-drawn with scrollable, hover-highlighted lists and a custom `VerticalScrollbar`. Pressing **Enter** in the tag entry adds a tag without closing the dialog; canvas selection and the item dropdown stay in sync bidirectionally; wiring a canvas-item event opens Dialog B in radio "wiring mode" to pick a single tag.
- **Proportional canvas-item scaling** — canvas items track the canvas through both a **design-time resize** (initial coords pre-scaled from the captured original size) and a **runtime stretch** (a `<Configure>` handler repositions/resizes every item when the canvas has a size-changing anchor), independent of whether a background image is set. The `<Configure>` handler also rescales **text font size** and **line thickness** by a uniform factor. The background image uses a protected `_bg` tag so item rescaling never disturbs it.
- **Canvas `sizing` property** — `sizable` (fills placed bounds, freely resizable) or `fit image` (locks the canvas to the natural dimensions of its background image; resize handles disabled). Setting an image defaults sizing to `sizable`.
- **Grid panel row/column inputs** — the Make Grid popup now takes explicit row/col counts and works in Canvas Item mode; the panel stays open after Make Grid and back-fills auto-detected row/col values.
- **Component connections in the Events tab** — selecting a non-visual component lists its wired widget-event connections (`comp_wire` rows) with a dedicated edit button and a `···` button that opens the Connect Widget Events dialog.

### Changed
- **Fonts emitted as tuples everywhere** — both widget `font=` kwargs (`_prop_str`) and canvas `create_text` calls now emit `('Family', size, 'style')` tuples via `_parse_font_spec` / `_font_tuple_literal`. A bare `"Segoe UI 12 bold"` string is parsed by Tk as a list and crashes the generated app with `expected integer`; multi-word family names (Segoe UI, Times New Roman, …) now work for all widgets and canvas text.
- **Canvas border split into integer props** — the old True/False `border` prop became `highlightthickness` + `bd` ints; a freshly dropped Canvas defaults both to `0` (no highlight ring).
- **Codegen skips leading-underscore props** — IDOL-internal props (e.g. `_ci_orig_w`, `_canvas_tags`) are no longer passed as tkinter kwargs.
- **Canvas item editor polish** — hover effects on the `+`/`−`/`×` buttons; a confirmation prompt before "clear all".

### Fixed
- **CI image palette paths dropped on restart** — images associated with a canvas now survive a session reload.
- **Canvas-item position sync** — un-scale item positions correctly in the live codegen sync-back; scale items on CI-mode enter/exit and when the form is resized in the designer; restore the original canvas size when its anchor is cleared; clear the amber "(original: w × h)" annotation when the original size is re-entered.
- **CI validation** — canvas tag names are validated; the Order tab behaves correctly in the CI deselect state.
- **Terminal REPL** — fixed `^L` being echoed in the Python REPL on session start and a double-prompt on launch.

## [2026-06-05 to 2026-06-08] — Canvas Item Designer

### Added
- **Canvas Item Designer (CI mode)** — double-click any Canvas widget on the design canvas to enter CI mode. A synthetic `FormModel` is built from the canvas's `canvas_items` list and loaded into the existing designer, so all normal designer machinery (select, move, resize, Properties panel, Events tab, undo/redo) works on canvas items without any new infrastructure.
- **Ghost overlay** — when CI mode is active, the surrounding form is dimmed with a `gray25` stipple overlay (four rectangles around the canvas), a `#007acc` 2 px border is drawn around the canvas, and a mode label is shown. Exiting CI mode (Escape or right-click → "Exit Canvas Edit Mode") converts the sub-form descriptors back into `CanvasItemDescriptor` objects on the original canvas widget.
- **CI palette** — the left palette swaps to show only CI item types: `CanvasRect`, `CanvasOval`, `CanvasText`, `CanvasLine`, `CanvasImage`. An **IMAGES** section appears below listing every Image component associated with this canvas.
- **IMAGES panel** — `[+]` adds images (copies to `project/images/`, auto-places on canvas at actual PIL dimensions); `[-]` fully deletes an image (removes from canvas AND from the Image component's `paths`); `[×]` clears all. Each image row: **click** to arm the CanvasImage placement tool; **double-click** to auto-place at center with PIL dims; **right-click** for Delete menu; **▲▼** buttons to reorder the list. Up/down reorder and palette double-click/delete images added in a follow-up pass.
- **CI Properties panel** — selecting a CI item loads it into the Properties tab: `id` (readonly), `type` (readonly), `x`, `y`, `width`, `height`, `tags` (click opens tag editor dialog), `image_path` (click opens dropdown of available images), `fill`/`outline` (color picker), `text`/`font` (text items).
- **CI Events tab** — same wire-and-stub flow as widget events. Supported events: `click`, `dblclick`, `rightclick`, `mousedown`, `mouseup`, `mousemove`, `mouseenter`, `mouseleave`. CI items must have at least one tag before events can be wired (enforced by the UI).
- **Tag editor dialog** — clicking the `tags` row opens a dark-themed modal checklist of all tags in use on the canvas, with an "add new tag" entry field.
- **`image_path` dropdown** — clicking the `image_path` row shows a dropdown of all images from Image components connected to this canvas (canvas-specific + Global images).
- **Image component `parent` property** — Image components now have a `parent` prop (`canvas_ref` kind dropdown): `None` (reference-only, no auto-placement), `Global` (visible from every canvas's IMAGES palette), or a specific canvas widget ID. The IMAGES palette section is populated from Image components where `parent == canvas_id OR parent == "Global"`.
- **CanvasImage auto-sync** — placing a `CanvasImage` item auto-creates or updates an Image component on the original form with `parent = canvas_id`. The Image component's `paths` list is kept in sync with placed CanvasImage items.
- **CI double-click navigation** — double-clicking a CI item (while in CI mode) jumps to its handler in the editor; double-clicking a wired event row in the Events tab also jumps. Both use the original form's `.py` file path (not the synthetic sub-form name).
- **CI arrow-key nudge and Delete key** — arrow keys nudge the selected CI item; Delete removes it. Shift+snap bypass works in CI mode too.
- **Item-order badges** — tab order badges are shown on CI items in CI mode.
- **Canvas item codegen** — `CanvasItemDescriptor.bindings: dict[str, str]` maps tk event strings to method names. Codegen emits `canvas.tag_bind(tag, event, self.method)` calls for each binding (deduplicated by tag+event across items sharing the same tag) and stub methods for each unique method name.
- **Canvas `border` property** — Canvas widget now has a `border` prop (True/False) controlling `highlightthickness` (0 when False, 1 when True).
- **`canvas_button` methods inline** — canvas_button handler methods now appear inline in the existing Connected event rows rather than being appended as separate rows.

### Changed
- **Paste preserves widget order** — fixed set iteration in `copy_selected` so copied widgets paste in their original z-order.
- **Auto-save form `.py` before codegen reads it** — the form `.py` is written to disk before any codegen subprocess reads it, preventing stale-read mismatches.

### Fixed
- **Tab badges on paste** — tab order badges now appear immediately on pasted widgets.
- **Tab badges after deletion** — badges now refresh correctly after any widget deletion.
- **Paste offset reset after move drag** — paste cascade offset is reset when a move drag completes so the next paste lands at the correct position.
- **Gallery and grid popup dismissal** — both the image gallery popup and the grid layout popup now dismiss when the app loses focus.
- **CI props panel clear** — fixed `_on_designer_ci_select` clearing the properties panel immediately after CI item selection.
- **CI properties refresh on exit** — properties panel now refreshes correctly when exiting canvas editor mode.
- **CI widget selector** — fixed widget selector, image rendering, and Image component sync issues in the initial CI implementation.
- **CI `_props_insert` crash** — fixed crash when inserting rows in the props panel during CI mode.
- **CI designer jump-to-handler** — fixed `_designer_jump_to_handler` using the sub-form name instead of the original form's file path.

---

## [2026-06-05 to 2026-06-08] — Editor Improvements + Codegen

### Added
- **Multiline string syntax highlighting** — triple-quoted strings (`"""..."""` and `'''...'''`) are now correctly highlighted as strings across all lines. Typing `"""` or `'''` auto-inserts the matching closing triple-quote.
- **VS Code-style comment hash alignment** — `Ctrl+/` now aligns `#` characters at the minimum indentation level of the selected lines (VS Code style), rather than inserting at column 0.
- **Enter on folded line unfolds first** — pressing Enter while the cursor is on a folded section header now unfolds the section first, then inserts a newline after the header line (previously inserted after the last hidden line).
- **Viewport centering on navigation** — when jumping to a handler or definition from the designer or Go to Definition, the editor scrolls so the target line is vertically centered in the viewport instead of appearing at the top.
- **Decorator preservation in codegen** — `@property`, `@staticmethod`, `@classmethod`, and any other decorator on methods in the `# ── Functions ──` section are now preserved verbatim across code regeneration.

### Fixed
- **Multi-cursor drift on shared line** — fixed cursor position drift when two or more cursors are on the same line.
- **Minimap scroll tracking** — fixed the minimap not tracking the editor scroll position correctly; now maps the editor's visible range to the minimap range accurately.
- **Fold index corruption** — fixed fold index corruption that could occur after Enter, Backspace, or Delete near a fold boundary.

---

## [2026-06-03 to 2026-06-04] — Image Resources + Canvas Button Builder

### Added
- **Image component** — new non-visual component for named image references. Click `COMPONENTS → Image` to add one to the tray; click the `images` row to pick one or more files via a multi-select dialog (all copied to `<project>/images/` automatically). Single file → `self.name = ImageTk.PhotoImage(...)`. Multiple files → `self.name = {"stem": ImageTk.PhotoImage(...), ...}` keyed dict. Component tray chip shows a live thumbnail of the first image plus a `×N` count badge; hovering the chip (400 ms delay) opens a gallery popup above the tray showing 80 px thumbnails with key names for every image in the group.
- **Canvas Button handler on Image component** — `canvas_button` handler with a ⚡ wire button. Clicking ⚡ opens the **Image Button Builder** dialog:
  - Canvas picker with a `＋ Create New Canvas` option (auto-creates a Canvas widget on the form)
  - Normal / Hover / Pressed image key dropdowns populated from the component's paths dict
  - X and Y position fields; editable Tag name (tkinter tag used for `itemconfigure` and `tag_bind`)
  - **Auto-size canvas** checkbox (checked by default) — reads PIL dimensions of all images and resizes the target Canvas widget to the largest width × height
  - Live preview pane showing the actual image, responds to clicks to preview pressed/hover states
  - Multiple wires supported — one Image component can drive any number of canvas buttons on any number of canvases
- **Canvas button codegen** — generates in `_build_ui`: `create_image()` + `tag_bind()` calls for `<Button-1>` / `<ButtonRelease-1>` and (if hover is configured) `<Enter>` / `<Leave>`. Generates in the Component Handlers section: `_btn_X_down` / `_btn_X_up` / `_btn_X_enter` / `_btn_X_leave` (always overwritten), plus a `_btn_X_click` user stub (never overwritten, safe to customize).
- **Canvas ghost preview** — when a canvas_button is configured, the designer canvas renders the normal image as a ghost at the configured (x, y) position on the Canvas widget so you can see layout without running the app.
- **canvas_button Connected display** — canvas buttons appear in the Connected section on both sides: in the Image component's Handlers tab (label `canvas1 · btn_tag`) and in the Canvas widget's Handlers tab. ✏ on either side reopens the builder pre-filled with the existing config; × deletes the button.
- **Readonly event rows for canvas_button** — the Canvas widget's Events tab now shows read-only `mousedown`, `mouseup`, and (if hover configured) `mouseenter` / `mouseleave` rows indicating the generated `tag_bind` methods.
- **Form background image** — new `image` property on Form/Dialog. Click to open a file picker; the image is copied to `images/` and rendered at natural size on the designer canvas behind the dot grid. Codegen emits a `tk.Label(self, image=self._form_bg_img, bd=0).place(x=0, y=0)` as the first child in `_build_ui`. Hovering the image property row shows `Background Image` + `filename  Width: W  Height: H` when an image is set (reads dimensions via PIL or `tk.PhotoImage` fallback).
- **Show/hide grid button** — `⋯` toggle button in the designer toolbar between Snap and Tab Order; defaults on; same blue active style as Snap. Redraws the canvas dot grid on each toggle.
- **Complete prop hint coverage** — all 41 widget property keys now have status-bar hover descriptions; previously missing: `image`, `compound`, `sizing`, `scrollbar`, `tabs`, `value`.

### Fixed
- **Props hover IndexError** — `_props_redraw_row` would crash with `IndexError: list index out of range` when hovering the props panel after PIL row removal shifted row indices. Fixed by adding an `idx >= len(self._props_rows)` bounds guard.
- **Canvas widget event set** — Canvas events were incorrectly `["click", "dblclick", "motion"]`; `"motion"` is not a valid `_BINDINGS` key (`"mousemove"` is). Updated to `_SIMPLE_EVENTS + _KEY_EVENTS` — the full standard event set matching all other interactive widgets.
- **Image component init ordering** — `self.img1 = {...}` was emitted after `self._build_ui()` but `_build_ui` references it for `create_image()`. Image component init now runs before `_build_ui`.
- **Builder OK with no canvases** — when no Canvas widgets existed on the form, the builder combobox initialized to `＋ Create New Canvas` and the trace never fired (value never changed), so OK returned early. Canvas creation now happens in `_commit` regardless of how the picker reached that value.
- **Widget deletion leaves orphaned codegen** — deleting a Canvas widget that had canvas_button connections left `comp.props["canvas_buttons"]` entries intact, generating dead code referencing the removed canvas. `_disconnect_widget()` now runs before each widget removal, stripping both canvas_button entries from Image components and orphaned `handler_wires` entries.
- **Designer mode focus** — clicking the `[Designer]` button left keyboard focus in the code editor, so pressing Delete removed text instead of deleting the selected widget. `_enter_designer_mode` now calls `self._design_canvas.focus_set()` immediately.

---

## [2026-06-01] — Split Editor Overhaul + Welcome Tab

### Added
- **Welcome tab** — shown on first launch (or when all tabs are closed) with Quick Actions, Recent Projects, Recent Files, Get Started links, rotating tips, and a "Show on startup" toggle. Reopenable via **Help → Welcome**.
- **Recent Projects / Recent Files** — persisted in `~/.idol/recent.json`; click to open, × to remove. Projects recorded on create/open, files on every open.
- **Live changelog viewer** in Welcome tab's What's New section — parses `CHANGELOG.md` on load; ‹ › navigation between milestone sections; `### Added/Changed/Fixed` headings styled in teal; mousewheel scroll isolated from outer panel.
- **CHANGELOG.md** — full project history distilled from 1,000 commits across 12 milestone sections.
- Split editor now supports **drag from split → main** with a blue drop zone on the left pane.
- Split editor **right-click menus** are now directional: main tabs show "Open in Split Editor", split tabs show "Open in Main Editor".
- Split editor **session restore** — split tabs (including dirty/unsaved ones) persist across app restarts exactly like main editor tabs.

### Changed
- **SPLIT button** now hides/shows the split pane without destroying tabs. Tabs survive behind the scenes.
- SPLIT button first open: moves the current tab when multiple tabs exist; opens fresh Untitled when only one tab is present.
- **Drag main → split** now *moves* the tab (removes from main). Right-click "Open in Split Editor" *copies* it (keeps in both panes).
- SPLIT button indicator: blue only when split is both active *and* visible; gray when hidden.
- Closing the last split tab via its individual X now fully closes the pane (nothing to preserve).
- Designer mode now *hides* the split pane instead of closing it; returning to editor mode restores it with all tabs intact.
- Welcome tab is immune to drag-to-split.

### Fixed
- Fixed blank grey square in main pane when the last tab was dragged to split.
- Fixed `_on_tab_changed` crash (`Invalid slave specification`) during tab moves.
- Fixed `_open_file` `ValueError` when active pane was split during project open.
- Fixed sidebar panels not themed on fresh launch (Welcome tab is the only tab).
- Fixed SPLIT button staying blue when split was hidden (hover leave handler was using the wrong active condition).
- Fixed Welcome tip showing `Ctrl+P` for Command Palette — corrected to `Ctrl+Shift+P`.
- Fixed `[Editor | Designer]` mode bar not appearing when entering designer mode from the Welcome tab button (was calling `_refresh_mode_bar` instead of `_show_mode_bar`).
- Fixed "New Project" dialog always prompting even with only the Welcome tab open (non-editor tabs now excluded from the has-project check; designer only counts if a form is loaded AND dirty).
- Fixed Explorer defaulting to IDOL's own directory on first launch — now defaults to home directory.
- Fixed bottom panels collapsing to near-invisible height; ghost sash now enforces an 80px minimum for the output pane.
- Run button (▶) now grays out when a non-editor tab is active (Welcome, Package Manager, Learning Mode) and no run entry file is pinned — clicking it no longer prompts to save.

---

## [2026-05-29 to 2026-05-31] — Socket Component + Designer Wiring

### Added
- **Socket non-visual component** — server and client modes with configurable host, port, encoding, buffer size, and max clients.
- Three fully-wired scaffold kits for Socket (send text, receive text, file transfer).
- Handler stubs now call through from widget events to generated form methods.
- Outline panel follows the focused split pane.

### Fixed
- Socket server reconnect after client disconnect (button state and `_running` flag).
- Socket `toggle_connect`-only wiring no longer omits `_disconnect`.
- Socket code generation registration for scaffold methods.
- Socket auto-disconnect timeout handling.

---

## [2026-05-25 to 2026-05-29] — Image Support + Designer Polish

### Added
- **Image support** for Label, Button, and Canvas widgets in the designer — browse project images, auto-copy to project directory, live preview on canvas.
- Images resize with their widget when a size-changing anchor is set.
- **Themes**: Dracula, Nord, GitHub Light, Solarized Light, and Dainty added alongside existing Monokai Bright.
- **Set as Main** — double-click a form in the FORMS tree to set it as the project entry point; writes `main.py`, pins run entry, shows ▶ indicator.
- Linked dialogs auto-loaded from source directory; missing ones shown in red with tooltip.
- Open Form copies `.form.json` and `.py` to project directory with overwrite prompt.
- Designer mode and form state now persist across app restarts.
- Double-click form to open its `.py` file in the editor.

### Fixed
- Stale designer form names loading wrong forms on session restore.
- Designer persisting across explorer root changes (wrong project loading).
- FORMS tree X button: linked dialogs unlink first, forms cascade-remove correctly.

---

## [2026-05-20 to 2026-05-24] — CommonDialog + Component Handler System

### Added
- **CommonDialog component** — open/save file dialogs, directory chooser, color picker, message boxes (question types). Each handler fires a corresponding `_on_*` callback.
- **Handler connector** — options dropdown for wiring component handlers to menu items or widget events; pre-selects the active canvas widget.
- Available Components / Connected Components split in the Handlers tab.
- Foldable Available Components section; all connectable handlers shown.
- × disconnect button on Connected Components rows (form and widget views).
- Handler options editor (… button) to change wire options after connection.
- Canvas editor: Tab with selection indents all selected lines.

### Fixed
- Canvas editor member autocomplete (flush didChange before dot trigger).
- Canvas editor: selection preserved on right-click.
- Component wire/disconnect not refreshing in form-selected mode.
- AI panel Send Selection for canvas codeview.
- Terminal: live-buffer reflow on column resize (VS Code style).

---

## [2026-05-13 to 2026-05-19] — Canvas Editor (Full Migration)

### Added
- **Canvas-rendered code editor** — complete rewrite from `tk.Text` + Pygments to a custom canvas-based rendering engine. Ships as the default editor.
  - Themes via `themes/*.json` with live switching (`View > Change Theme`).
  - Horizontal scroll with accurate per-glyph measurement; italic-aware content width.
  - Scope-bounded indent guides.
  - Undo/redo with coalescing, wired to Edit menu and keyboard shortcuts.
  - Shift+Tab unindent, respects status bar indent size.
  - Tab with selection indents selected lines.
  - Go to Definition (F12) with LSP `LocationLink` support.
  - IDOL codegen marker folding and section fold ranges.
  - Multi-file font persistence across restarts.
  - View > Change Font wired to canvas editor.
  - Debug breakpoints and git-hunk gutter on canvas tabs.
  - Diagnostics, Find/Replace, autocomplete, LSP completion all wired to canvas tabs.
  - Right-click context menu at full parity with legacy editor.
  - Multi-cursor via Alt+click with synced blinking carets.
- **References panel** tab-aware navigation with caret at word start.
- Terminal: alternate screen buffer, mouse forwarding, extended key map, auto-scroll pin.
- Designer/Explorer: open `.form.json` directly in designer from explorer tree.
- Multi-session terminal: isolated scrollback between sessions.

### Changed
- Legacy `tk.Text` editor removed; canvas engine is now the only code editor.
- Themes extracted to `themes/*.json`; `utils/theme_loader.py` added.
- `requirements.txt`: Pygments and toml removed (unused post-migration).

### Fixed
- Text bleeding into gutter after tab switches.
- Canvas editor autocomplete leak and focus gap on designer/editor switch.
- References navigation crash.
- Terminal garbled output on non-alt-screen viewport scroll.
- Terminal PSReadLine prompt reflow on column resize.

---

## [2026-05-11 to 2026-05-12] — Notebook Widget + Designer Phase 3.5

### Added
- **ttk.Notebook as designer widget** — add tabbed containers to forms; tab order panel groups Notebook children by tab.
- **Tab order badges** on canvas following dragged widgets.
- **Order panel** in properties — drag to reorder widget stacking and Notebook tab order.
- **Custom scrollbars** (`HorizontalScrollbar` + `VerticalScrollbar`) replacing all `ttk.Scrollbar` widgets app-wide.
- Designer: arrow key nudge (8 px grid, Shift+arrow for 1 px fine nudge); snap-to-grid toggle.
- Designer: draw inside frames; children clamped to parent bounds.
- Terminal: session sidebar with per-session isolation.
- macOS: native fullscreen state persists across restarts.
- Menu editor: dark canvas-drawn checkboxes; captions auto-fill Name field.
- Linux: cross-platform resize-handle cursors; fix VTE/X11 spurious Leave events.

### Fixed
- Form-resize bleed-through (inactive-tab Notebook children visible on canvas).
- Tab drag off-by-one in nearest-tab detection.
- Linux maximize state not restoring correctly on restart.
- Ghost sash drag on `ttk.PanedWindow` on Windows.
- Horizontal scrollbar shrinking on shorter lines.

---

## [2026-05-07 to 2026-05-10] — Designer Phase 3 + Cross-Platform Polish

### Added
- **Multi-form designer** — Toplevel/dialog support with form tree linking.
- **FORMS tree** — new panel listing all forms; X to remove, right-click for Delete/Unlink.
- **Dialog helper**: `WM_DELETE_WINDOW` + `_on_close(self.withdraw)` codegen; dialog instances stored as `self.dlg_DialogName`.
- **Tab Order panel** (Order tab in properties) with canvas badges.
- **Drag-and-drop widget placement** from palette to canvas.
- **Draw-to-size placement** mode.
- **Multi-placement mode** — palette tool stays armed between placements.
- **Grid layout popup** in designer toolbar.
- **Undo/redo** in designer with toolbar buttons and Ctrl+Z/Ctrl+Y.
- **Anchor picker** with per-item hover descriptions.
- **Multi-select**: rubber-band, Ctrl+Click, Ctrl+A; resize propagates to the group; shared property editing.
- **Widget containment** for Frame and LabelFrame; children clip and drag within parent.
- Designer scrollbars and mousewheel scroll on canvas.
- Canvas menu bar: live preview, click-to-navigate to menu item handler.
- Designer: Shift bypasses snap during resize and new widget draw.
- Cross-platform font: `UI_FONT` constant replaces hardcoded Segoe UI.
- Project file saved as `<name>.idol-project`.
- Save Form menu item; prompt on exit with unsaved changes.
- `StyledCheckbox` widget replacing `tk.Checkbutton` throughout designer.

### Fixed
- Canvas resize handles and rubber-band selection offset when canvas is scrolled.
- LabelFrame child y-offset (17 px label area).
- Designer mode persisting when switching explorer roots.
- Venv detection and radiobutton styling on Linux.
- Project wizard flash (withdraw before render, deiconify after).

---

## [2026-05-01 to 2026-05-06] — Designer Phase 2 + Menu Builder

### Added
- **Menu Builder** (VB6-style Menu Editor) — add/remove/reorder menu items, separators, check/radio types, variable bindings, shortcut auto-bind, command handler picker. Live menu bar rendered on canvas.
- **Variable picker** popup for properties panel and menu editor (`StringVar`, `IntVar`, `DoubleVar`, `BooleanVar`).
- **Font picker** (tkfontchooser) for font property.
- **State property** with conditional `--bg`/`--fg` color rows.
- **Validatecommand / invalidcommand** props for Entry and Spinbox with `%P/%S/...` substitution codes.
- **Combobox, Listbox** values list editors and corresponding events.
- **Event auto-wire button** on event rows.
- Form events (load, activate, deactivate, unload, resize).
- Widget property coverage: `char_width`, `char_height`, `show`, `state`, `labelanchor`, `scrollbar`, Checkbutton `StringVar`.
- IDOL:BEGIN/END markers in `__init__` — two user-owned code zones preserved across regeneration.
- Preserved user imports block (IDOL:IMPORTS markers).
- Form background color picker; widget bg/fg color pickers.
- **Ghost sash** drag line with deferred resize on mouse-up across all panes.
- **Clipboard History** panel (Ctrl+Shift+H) with paste-on-click.
- Git ahead/behind count in status bar.
- Non-ASCII paste detection with "Fix Encoding" nav pill.
- CRC-based dirty tracking (undo/redo clears dirty when content matches saved).
- Startup: eliminate sash jump by pre-sizing panes from saved session layout.
- Outline: preserve expanded/collapsed state across refreshes.
- `About` dialog shows Python, pip, and OS environment info.

### Fixed
- Pre-init user zone erased on Generate Code.
- Sticky scroll scope detection and navigation offset.
- Problems panel not clearing LSP errors on tab close.
- AI Chat scroll-to-bottom on session restore.
- Exception navigation resetting explorer root to crash file's directory.
- Fold section-marker comment click jumping cursor.

---

## [2026-04-21 to 2026-04-30] — Designer Phase 1 + Debugger + AI Improvements

### Added
- **GUI Designer Phase 1** — visual Tkinter form builder with:
  - Canvas widget placement and drag-to-move.
  - Properties panel (canvas-rendered) with live color editing.
  - Events tab with handler catalog wiring and double-click-to-navigate.
  - Handlers tab.
  - Python code generation (`<name>.py`) with IDOL marker zones.
  - Session persistence (form state survives restarts).
  - Project Wizard: GUI project type creates starter `main.py` + `<Form>.py`.
  - Mode bar `[Editor | Designer]` tab strip.
- **Integrated Python Debugger** (debugpy + DAP):
  - Breakpoints with hover ghost dot and active dot in gutter; persist across sessions; shift when lines inserted/deleted; restore on undo/redo.
  - Debug toolbar (Continue F5, Step Over F10, Step Into F11, Step Out Shift+F11, Stop).
  - Floating debug panel with dock/undock and always-on-top.
  - Terminal debug mode (launch debugpy in terminal, attach DAP client).
  - Inline stdin bar in output panel for `input()` support.
  - Runtime error indicators: amber gutter arrow, line highlight, Problems tab flash.
- **Problems panel** — LSP + ruff diagnostic list; hover tooltips with rule descriptions; Ask AI button for beginner-friendly fix suggestions; double-click to ask AI.
- **Dual-track error engine**: ruff subprocess + pyflakes fallback; three-tier severity (red/yellow/blue).
- Multi-cursor: smart pairs, bracket matching, cursor visibility; independent Shift+arrow selection; Alt+click removes existing cursor; Ctrl+C copy from multiple cursors.
- Alt+Up/Down line move; Shift+Alt+Up/Down line duplicate.
- Run Selection / Run Line in editor right-click menu.
- Learning mode: debug toolbar entries, guide for `input()` detection.
- Active line highlight with color picker (`View > Active Line Color`).
- Find/Replace pre-populates from word under caret.
- Right-click context menu IDOL overlay style; shortcut keys right-aligned.
- Breakpoints on unsaved files via temp-path with panel warning.
- Editor right-click: two-column layout with right-aligned shortcut keys.
- Collapsed selection on Left/Right arrow key.
- Smart Home key (position-based toggle, no state required).

### Fixed
- Selection anchor desync on Shift+Up/Down.
- Minimap flicker when scrolling with folded lines.
- Fold marker state after inserting lines above a folded block.
- Autocomplete popup dismissal and dot-trigger completions.
- AI Chat: `Send Selection` for canvas editor; scroll-to-bottom on restore.
- PowerShell 256-colour support in terminal (truecolor hex strings).

---

## [2026-04-11 to 2026-04-20] — AI Chat, Learning Mode, Package Manager + Terminal Rewrite

### Added
- **AI Chat panel** (F2) — persistent right-side panel powered by local Ollama; code-block copy buttons; animated "Thinking..." dots; session history persistence; configurable server URL; horizontal scrollbar on code blocks.
- **Learning Mode** (F1) — hover-driven contextual help: hover any IDE element for What/How/Example explanations. Custom arrow+? cursor on Linux.
- **Package Manager** (F3) — instant topic grouping, live filter, PyPI search and install; `!pip` mode in command palette.
- **Nav toolbar** strip above the tab bar with toggle buttons for Split, Map, Zen, AI, Packages, Learning.
- **Sidebar toggle** (Ctrl+B).
- **AI local explanations** in Learning Mode via Ollama.
- **Zen Mode** (F10) — full-screen editor, fading pill toast.
- **Project file system**: `.idol-project` file; `workspace_open`, `workspace_save`, `workspace_close` flow.
- **Interpreter selector** in status bar — persist and sync across run/debug/packages.
- **Run entry file selector** in status bar.
- **Seamless debugpy**: inject IDOL's bundled copy via `PYTHONPATH`.
- Splash screen and About dialog with IDOL logo.
- Output panel: copy button and right-click context menu.
- Explorer: "Add to .gitignore" context menu item.
- `!pip install <package>` mode in command palette.
- Git: "Add to .gitignore" in SC panel; two-stage push/pull confirmation.
- Git identity health check + GitHub login guide in SC panel.
- First commit guide + Project Wizard success screen.
- Breadcrumb bar locals picker: instance attrs, color-coded sections, hover preview strip.
- HISTORY section in Source Control panel with commit log.
- Tab tooltip showing full file path on hover.
- Cmd+W tab close on macOS.
- Ctrl+Click as right-click on macOS across all context menus.
- Unified Panels submenu in View menu with hotkeys.
- Fix Encoding nav pill for non-ASCII paste detection.

### Changed
- Terminal completely rewritten with pyte VT100 screen buffer — proper ANSI escape handling, SGR colors, cursor movement.
- Terminal: venv detection, text selection, context menu.
- Renamed Notepad → **IDOL** throughout the codebase.

### Fixed
- macOS Python 3.14 crash: all thread callbacks routed through a queue.
- Sidebar collapsing to 0 width on Linux/macOS.
- Terminal: prompt disappearing on first keypress (Windows); PSReadLine garbling; cursor drift on sash resize.
- Fold marker clicks in line gutter and outline panel.
- LSP diagnostic highlights snapping to word boundaries.
- Autocomplete hang: LSP stdin writes moved to background writer thread.
- Split editor crash on last tab close; scroll lock re-patched on every tab change.

---

## [2026-04-07 to 2026-04-10] — Git, Explorer, Project Wizard + Cross-Platform

### Added
- **Project Wizard** — guided new project creation with Python interpreter selection, venv creation, git init; GUI project type.
- **GuideWindow** — multi-page learning guides (venv setup, git remote, first commit).
- **Explorer drag/drop** — rename, delete, new file/folder, drag-to-move with unsaved-changes guard.
- **Git learning features** — Git Health panel, smart warnings, tooltips, install wizard, identity check.
- **venv auto-activation** — project venv activates automatically on terminal open; persists across restarts.
- Source Control: full overhaul with virtual rendering, space sharing, HISTORY section, right-click context menus.
- Terminal CWD sync: follows explorer root changes; persists across restarts.
- Zen Mode (F11 → moved to F10).
- Breadcrumb bar with clickable symbol picker; local variable / nested-def tree in outline and breadcrumb.
- Add show/hide venv and system interpreter filters to Project Wizard.

### Fixed
- Terminal CWD wrong on launch — routed all root changes through `_set_explorer_root`.
- LSP `uri_to_path` leading slash on macOS/Linux.
- Explorer stale item IDs; dirty state preservation on drag-move.
- Sidebar sash debounce, re-entrancy guard, session validation.
- macOS button rendering (all `tk.Button` replaced with `tk.Label` + bindings).

---

## [2026-04-02 to 2026-04-06] — Initial Release + Core Editor

### Added
- **Initial commit** — Tkinter-based code editor for Python.
- Syntax highlighting (Monokai theme).
- LSP integration (pyright/pylsp) — completions, diagnostics squiggles, hover.
- Multi-cursor editing.
- Minimap (right-edge overview with zoom window).
- Integrated terminal (PTY-backed, Windows + Linux + macOS).
- Autocomplete popup with LSP hook.
- Find/Replace bar (Ctrl+F).
- Code folding — section markers (`# ── Name ───`) and standard fold ranges.
- Sticky scroll (top of viewport shows current scope header).
- Outline panel — symbol tree with locals.
- Split editor (drag tab to right edge to open in split pane; scroll lock sync).
- Source Control panel — Phase 1 and Phase 2 git integration (stage, unstage, commit, diff view).
- Command palette (Ctrl+P) — symbol search, file open, editor commands.
- References panel — find all usages.
- Session persistence — open tabs, layouts, explorer root, interpreter survive restarts.
- Breadcrumb bar.
- Minimap scroll and zoom.
- Insert/overwrite mode toggle.
- Smart Home key, smart pairs, bracket matching.
- Scroll Lock key syncs split pane scrolling.
- Word-occurrence highlights.
- Ctrl+/ comment toggle.
- Line move (Alt+Up/Down) and duplicate (Shift+Alt+Up/Down).

---

*1000 commits · April 2 – June 1, 2026 · IDOL by gitPIDE*
