# Changelog

All notable changes to **IDOL** are documented here, organized by development milestone.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
