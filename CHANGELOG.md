# Changelog

All notable changes to **IDOL** are documented here, organized by development milestone.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2026-07-24] — Explorer root / terminal working directory

### Fixed
- **Changing the Explorer root no longer `cd`s a running terminal.** `Set as Root Directory`,
  a breadcrumb folder click, and opening a file all funnel through
  `_on_explorer_root_change`, which used to push the new root into the live shell — so
  re-rooting the tree teleported whatever you were doing in the terminal to a different
  directory. `BottomPanel.set_cwd()` is now state-only: it records the directory the *next*
  terminal session starts in and leaves running shells alone. The live-`cd` behaviour moved
  to a new explicit `BottomPanel.cd_terminal()` (which also drops the old 250 ms coalescing
  timer — an explicit user action does not need debouncing).

---

## [2026-07-24] — Designer property-panel polish

### Added
- **One-click reset for changed width/height in the designer.** A geometry row that shows an
  `(original: N)` hint now also gets a hover `×` that resets that dimension to its original value.
  This applies to a **CanvasImage** item (resets to the picture's natural pixel size — which also
  lets codegen drop the per-item resized `PhotoImage` and reuse the shared component image) and to
  a **Canvas** widget that was resized in CI mode (resets to its recorded design size). Previously
  the `(original: N)` hint was display-only.
- **The selected Properties-panel tab renders in bold.** The Properties / Events /
  Handlers / Order tabs now show the active tab's label in bold, so it is obvious at a
  glance which view you are editing. The tabs keep their existing grey / black-text look;
  only the active tab's label goes bold, via a `font` state-map on the
  `Props.TNotebook.Tab` style (`selected` → bold). The tab layout is also rebuilt without
  the `Notebook.focus` element, so the selected tab no longer draws a dotted focus ring,
  and the tab padding is trimmed to `(4, 2)` for a tighter strip.

### Fixed
- **The open editor tab now refreshes after designer code-gen.** Regeneration already
  rewrote an open `.py` tab in place, but matched the tab with `Path(fp) == py_path`, which
  on Windows is `False` when one path is relative and the other absolute — so the tab could
  keep showing stale pre-generation code until closed and reopened. The refresh loop (and the
  `_autosave_form_py` pre-read save, which had the same mismatch and could silently drop edits)
  now compare normalized absolute paths, and every matching tab is refreshed so a file open in
  the split view updates in both panes. The auto-gen debounce was also shortened from 1.5 s to
  0.6 s (`_AUTOGEN_DEBOUNCE_MS`) so switching to the editor right after an edit shows fresh code
  with much less lag.
- **An armed CanvasImage now de-arms back to the pointer.** In the Canvas Item Designer,
  arming an image sets two highlights — the `CanvasImage` type row *and* the image's row in
  the IMAGES panel — but cancelling the tool only cleared the former, so the image row stayed
  highlighted and looked armed after Escape. `DesignerPalette.reset_to_pointer()` now also
  clears the IMAGES-panel armed highlight (`_ci_img_armed_path`) and rebuilds the list. In
  addition, `DesignCanvas.exit_canvas_item_mode()` now cancels any armed tool before leaving CI
  mode, so the crosshair cursor and armed highlight can no longer bleed into normal designer
  mode when you exit via the right-click menu or programmatically (not just via Escape).
- **Resized canvas-item images now render at their set size in the generated app.** When you
  resized a `CanvasImage` in the Canvas Item inspector, the design canvas showed it correctly
  but codegen pointed `create_image()` at the shared `Image` component's natural-size
  `PhotoImage` — so the running app ignored the size. A **resized** image item now generates its
  own `ImageTk.PhotoImage(Image.open(...).resize((w, h), LANCZOS))` sized to the item's display
  box (pre-scaled for any designer canvas resize), matching the WYSIWYG preview. The per-item
  attribute is namespaced by canvas id (`_{canvas}_{item}_img`) so two canvases sharing an item
  id can't clobber each other's image (Tk keeps no strong reference, so a clobbered image would
  be garbage-collected). On a size-changing anchor, the `<Configure>` handler re-renders each
  item's image at `base size × live stretch factor` instead of the old natural×scale of the
  shared image. An image item left at its **natural** size skips the per-item copy entirely and
  reuses the shared component image (`create_image(image=self.comp["stem"])`) — identical pixels
  with far less generated code, so a canvas of many same-size buttons stays as compact as before
  the resize feature existed. The natural size is measured once per image via PIL at the app
  layer (`_ci_image_natural_sizes`) and passed into codegen. The auto `{canvas}_ci` Image
  component's own `PhotoImage` is still emitted so it stays a valid named reference in your code.
- **Designer property-panel tab style now lands in the theme that is rendered.** The
  panel is built before the main notebook, so its `Props.TNotebook.Tab` config ran while
  the native startup ttk theme was still active; when the notebook later switched the app
  to its `selectedtab` theme, that config was silently dropped — which is why the new bold
  state-map had no effect. `CustomNotebook.ensure_style()` is a new idempotent classmethod
  that installs the app theme once; the designer panel calls it before styling its tabs so
  the config takes.

---

## [2026-07-23] — Conda search fixes, source-aware hints, conda guides, terminal cursor fixes

### Fixed
- **Terminal block cursor stays on the prompt after a resize.** Sash drags, panel
  toggles, and window resizes could leave the block cursor rows away from the prompt —
  or parked mid-text at the bottom of the screen. Three reflow defects fixed: a cursor
  sitting alone on a blank never-written row (pyte's buffer is sparse) was skipped by
  the reflow walk, keeping its stale pre-resize row; narrowing that re-wrapped content
  into more rows than the screen has clamped the cursor onto whatever row sat at the
  viewport bottom (overflow now scrolls into scrollback like the real console); and a
  cursor at column 0 of a blank line never claimed its new row. The renderer also now
  honors cursor hide/show (DECTCEM) — no more phantom block at an intermediate position
  when a poll frame lands mid-repaint — and draws a pending-wrap cursor on the last
  column instead of past the right edge.
- **Run commands echo at the prompt, not floating mid-screen.** A wrap boundary landing
  on a space (`…) PS `, paths with spaces) was treated as a hard line break, so resize
  reflow split the logical line differently than the Windows console's own buffer. The
  two layouts disagreed about which row the prompt ends on, and later
  absolutely-positioned repaints — like the echoed Run command — landed rows below the
  prompt with a blank gap to the left. Wrap flags are now cleared at the source when
  EL/ED erase a row's tail, and trusted for any actually-written boundary cell, drawn
  spaces included, keeping IDOL's layout in lockstep with the console's.
- **Enter now runs the discovery search.** Pressing Enter in the package search box ran
  the search on key press — then the same key's *release* re-ran the installed-list
  filter and rebuilt the tree, wiping the results it had just rendered. Search appeared
  to return nothing unless the "↗ Search … for" row was clicked. The KeyRelease filter
  now skips Return/KP_Enter (numpad Enter is bound to search too), and a search issued
  while the conda channel index is still loading is queued instead of silently dropped
  (previously it stuck at "loading channel index…" until a second Enter).
- **Conda install output is readable.** Conda writes terminal-oriented output even when
  piped: backspace-drawn spinners, download bars redrawn via `\r` + cursor-up codes,
  clear-line runs of spaces — all of which landed verbatim in the Output panel.
  `_StreamCleaner` now scrubs every streamed line: spinners collapse to their final
  text, ANSI escapes are stripped, and each download bar appears once at 100% instead
  of as a redraw storm.

### Added
- **Designer Pillow install follows the interpreter.** The designer's one-click
  "⚠ install Pillow" was hardcoded to pip; conda interpreters now install the conda
  `pillow` package, with the same ToS Accept/Decline gate as the Package Manager, a pip
  fallback when no conda exe is found, and the dependency appended to `environment.yml`
  instead of `requirements.txt`. Success is verified by probing `import PIL` before
  reporting done.
- **Search hints follow the source toggle.** The rotating placeholder shows
  "Search conda…" with channel-relevant examples (`pytorch`, `python-graphviz`,
  `cudatoolkit`, …) when the search source is conda, and swaps back to the PyPI set on
  toggle — immediately, restarting the hint cycle, and never clobbering a typed query.
- **Learning guides cover conda.** The Package Manager guide gains a *Conda
  Environments* page (automatic conda routing, conda-vs-PyPI name clashes like
  `graphviz`, the `· pip` badge and origin-aware uninstall, first-run ToS dialog) and
  the venv guide gains *What About Conda?* (conda env vs venv, channels,
  `environment.yml`, how IDOL detects and activates conda envs). Anaconda now also
  appears in the "why are there multiple interpreters" list.

## [2026-07-22] — Package list view toggle, REPL follows interpreter

### Fixed
- **Run no longer opens Save As on panel tabs.** Clicking Run (or Debug/Ctrl+F5) with
  the Package Manager, Welcome, or Learn tab focused treated the panel as an untitled
  editor — retitling the tab "Untitled" and prompting Save As. `file_save`/`file_save_as`
  now no-op on tabs without an editor, so Run proceeds straight to the pinned run entry.
- **Closing a project now deactivates the active env (venv and conda).** Teardown only
  handled venvs (by statusbar label), so a conda env stayed active while the terminal
  cd'd home — where the cwd-based toolbar had no target and offered no Deactivate. Both
  kinds are now deactivated before the cwd reset, and as a belt-and-suspenders fix the
  env toolbar always offers **⏹ Deactivate** when an env is active but the CWD has none
  (previously it showed nothing — the same trap existed for venvs after a manual `cd`).

### Added
- **Completions and hovers follow the active interpreter (LSP).** pylsp still runs from
  IDOL's own environment (no per-project install, like the bundled debugpy), but its
  jedi backend is now pointed at the active interpreter via
  `pylsp.plugins.jedi.environment` (sent in `initializationOptions` and
  `workspace/didChangeConfiguration`), so autocomplete, hover docs, and go-to-definition
  resolve the selected venv/conda env's packages. Switching interpreters re-points the
  live server — no restart. Verified over real LSP stdio: `import cond…` completions
  include the conda env's package family only with the environment set. Closes the
  deferred item from the conda branch.
- **Wizard conda cases refined.** The interpreter filter row gains a **`conda env`**
  toggle (off by default, like `venv`) for previously created conda envs, while `conda`
  covers base installs. With a base interpreter and *Create virtual environment*
  **unchecked**, the version picker greys out and the note says the base env is used
  directly. Selecting an **existing conda env** greys out both the checkbox and the
  picker (its actual version shown) — the project uses the env as-is and activates it
  in the terminal on open; the summary and statusbar label say so
  (`(conda: myenv) Python 3.x`). Project-local envs are now labeled with their project
  folder (`(conda: CondaTosTest/.conda)`) so multiple `.conda` envs stay
  distinguishable. `StyledCheckbox` gains runtime `set_disabled()`.
- **Terminal Python REPL uses the active interpreter.** The REPL session type now
  launches IDOL's active interpreter (venv/conda/system) instead of IDOL's own Python,
  and its picker entry shows that interpreter's version (e.g. `Python 3.14` with a conda
  env active). Switching interpreters retargets the next new REPL session; running
  sessions keep theirs. Conda REPLs get the synthesized activation environment so
  imports resolve DLLs.
- **Grouped ↔ alphabetical view toggle** in the Package Manager: a `≡ A–Z` / `⊞ Groups`
  control right-aligned on the INSTALLED header switches the installed list between
  topic groups and a flat alphabetical list. The live filter respects the choice, and
  it persists across sessions (`pkg_group_view` in `~/.idol/settings.json`).

## [2026-07-21] — Conda environment support

### Added
- **Conda interpreters are first-class citizens.** Conda envs (Miniconda/Anaconda/Miniforge)
  are discovered automatically — `~/.conda/environments.txt` plus the default install
  locations — and appear in the interpreter picker and Project Wizard as
  `Python 3.x (conda: base)` / `(conda: myenv)`; the wizard gains a `conda` filter toggle.
  `categorize_interpreter` returns a new `"conda"` category (a venv created *from* a conda
  python still counts as a venv).
- **No `conda init` required, ever.** Run, Debug, and all package operations execute conda
  pythons with a synthesized activation environment — the env's PATH entries (including
  `Library\bin`, where conda keeps its DLLs on Windows) plus `CONDA_PREFIX` /
  `CONDA_DEFAULT_ENV` — so unactivated conda pythons no longer fail importing `ssl` /
  numpy / pip. Terminal activation sources the hook scripts explicitly
  (`conda-hook.ps1` for PowerShell, `etc/profile.d/conda.sh` for bash/zsh with
  MSYS2-converted paths for Git Bash).
- **Package Manager conda backend** (`editor/conda_manager.py`). With a conda interpreter
  active the installed list comes from `conda list --json`, pip-installed packages show a
  `· pip` badge, and uninstalls route to whichever tool installed the package. If the
  env's conda executable can't be located, the panel falls back to pip inside the env
  with a notice.
- **Search follows the interpreter — no more name-collision traps.** With a conda env
  active, package search runs against your *configured conda channels* (from `~/.condarc`;
  each channel's `channeldata.json` is cached in `~/.idol/conda_index/`, refreshed weekly,
  fuzzy-searched locally — instant and offline-friendly). A `conda | PyPI` toggle next to
  the search button lets you still reach PyPI-only packages. Installs route by the source
  the package was picked from: conda results install via `conda install` **only** (no
  silent pip fallback — conda's `graphviz` is the Graphviz C tool while PyPI's is the
  Python bindings, so swapping tools silently installs the wrong product), and PyPI picks
  install via pip inside the env after a one-line warning that pip-in-conda can conflict
  with conda's dependency resolver. Conda search results show channel + summary details
  from the index; search itself never needs the ToS (plain HTTPS, not conda).
- **Terminal conda awareness.** The env toolbar now tracks `$CONDA_PREFIX` (new
  IDOL-private OSC 7778 marker on bash/zsh; a third state-file line on PowerShell) and
  handles conda targets: **▶ Activate conda env** for a project-local `.conda/`,
  **⏹ Deactivate** (sends `conda deactivate`), **⇄ Switch env** across kinds. Child
  shells start with IDOL's own `CONDA_*` variables stripped. Run-in-Terminal and
  Debug-in-Terminal type the activation command before the run command when the shell
  hasn't activated the conda interpreter yet.
- **Project Wizard creates conda envs.** The existing *Create virtual environment*
  checkbox is conda-aware: with a conda interpreter selected, a yellow **Conda
  Environment Selected** note appears with an **Env Python version** picker (defaults
  to the selected interpreter's version — conda installs any version into a fresh env),
  and project creation runs `conda create -p <project>/.conda -y python=<X.Y>`
  (conda's stderr surfaced verbatim on failure). Conda projects get an
  **`environment.yml`** starter instead of `requirements.txt`, with the channel list
  mirroring the user's `~/.condarc`. The starter `.gitignore`
  covers `.conda/`, the Git health panel classifies committed `.conda/` / `conda-meta/`
  files, and project-local `.conda` envs are auto-detected like `.venv` (interpreter
  auto-select on file open).
- **Terms of Service handled in-app.** Anaconda's channels require accepted ToS before
  conda can download packages (fresh Miniconda installs haven't accepted). The wizard
  checks on **Next** (conda interpreter + create-env checked) and the Package Manager
  checks before the first conda-routed install/uninstall; both show the channel ToS
  text with an **Accept/Decline dialog** (`widgets/conda_tos_dialog.py`). Accept runs
  `conda tos accept` — persisted by conda itself, so the user's own CLI works too;
  Decline cancels the operation.
- **Session persistence.** The active conda env's prefix is saved
  (`interpreter["conda_prefix"]`) and project-local `.conda` envs re-activate in the
  terminal on restore, under the same project-containment guard as venvs.

### Notes
- Verified on Windows against a default Miniconda3 install (discovery, synthesized-env
  runs, pip-in-conda, conda list/install-fallback/uninstall round-trip, ToS failure
  surfacing). Linux/macOS code paths structurally mirror the shipped venv POSIX paths
  but haven't been exercised on real systems yet.
- LSP diagnostics/completions still run from IDOL's own environment — threading the
  active interpreter into pylsp is queued next in `ROADMAP.md`.

## [2026-07-16] — Debugging honors the run working directory

### Fixed
- **Debugging now starts in the same directory as running.** The Output-panel debugger set its
  working directory to the script's own folder regardless of the Run working-directory setting, so
  with the default **Project Root** mode a program that ran correctly could still fail under the
  debugger — a relative path like `sqlite3.connect("app.db")` resolving against a subfolder instead
  of the project root. Debug now uses the same directory as Run (`DebugManager.launch` takes a
  `cwd`), so relative paths resolve identically whichever button you press. The debug header echoes
  `$ cd <dir>` like the run header does. Terminal debugging already followed the setting and is
  unchanged.

## [2026-07-16] — Run working directory follows your project

### Fixed
- **Runs launched from the Run button now start in your project directory, not IDOL's.**
  Previously the Output-panel run inherited IDOL's own working directory, so relative paths in
  your code (e.g. `sqlite3.connect("data.db")`) resolved against the install dir and failed —
  while the integrated terminal, which already set a cwd, worked. The two run paths no longer
  diverge: both honor a single working-directory mode.

### Added
- **Run working-directory setting (Run menu → Dir: Project Root / Script Directory).** Chooses
  where a run starts: the project root (default) or the running file's own directory. "Project
  Root" reuses the explorer root and falls back to the script's directory when no project is open
  (never IDOL's launch dir). The mode governs both the Output-panel and terminal run paths
  (including terminal debug); Run Line / Run Selection always use the project root since they
  execute off a temp file. Persisted per project in the session layout, and also reachable from
  the command palette. The output header now echoes `$ cd <dir>` so the run directory is visible.

## [2026-06-27] — Event/widget rename keeps user code

### Fixed
- **Renaming an event handler no longer drops its body.** Preserved bodies are keyed by method
  name, so retyping a handler (e.g. `_canvas1_mousedown` → `_gameboard_mousedown`) used to miss the
  lookup on regen and emit a clean stub, discarding the user's code. The body (and any custom
  signature) now carries to the new name via a per-form rename map applied during extraction, with
  chain-collapse for repeated renames (A→B→C).

### Added
- **Renaming a widget now keeps its handlers and code in sync.** It (1) renames the widget's
  auto-derived event handlers that still follow the `_{id}_{event}` convention (custom-named
  handlers are left alone), and (2) rewrites `self.<old_id>` references throughout user event/helper
  bodies to `self.<new_id>` so they don't raise `AttributeError` at runtime. The reference rewrite is
  a `tokenize` pass (`persistence.rename_self_attributes`) — safe against strings, comments,
  substrings (`canvas1` ≠ `canvas10`), and same-named locals. Rename maps are keyed by form name so a
  default id like `canvas1` reused on two forms can't cross-contaminate during regen.
- **Rename collision guard.** The name editor now rejects a rename that would shadow an existing
  attribute (reverting with a status-bar reason) instead of generating broken or clobbering code:
  Python keywords (`self.class = …` would be a `SyntaxError`), other widget ids, components, tk
  variables, menu variables, linked-dialog instances (`self.dlg_X`), scrollbar-derived attrs
  (`{id}_vsb/_hsb/_frame`), and the user's own `self.<name>` assignments (scanned from the `.py`).

## [2026-06-27] — Drop duplicate keydown event (use keypress)

### Changed
- **The `keydown` designer event has been removed — it was an exact duplicate of `keypress`.** Both
  bound `<KeyPress>`, so wiring both emitted two `.bind("<KeyPress>", …)` calls and one silently
  overwrote the other. Widgets now expose `keypress` / `keyup` only. Existing forms migrate on load
  (`WidgetDescriptor.from_dict`): a wired `keydown` becomes `keypress`, and if both were wired the
  `keypress` wire is kept. (`keydown` remains in the codegen binding table as a safety net.)

## [2026-06-27] — Button command/click collision resolved

### Changed
- **A Button no longer has both a `command` and a `click` event — they were the same event under two
  names.** On a Button, `click` was folded into the `command=` constructor kwarg (and skipped in
  `.bind()`), so wiring both silently dropped `click` (`command` won). Button now exposes a single
  activation event, **`click`**, which still wires as `command=self.method` — preserving keyboard
  activation and `state=disabled` behaviour (a raw `<Button-1>` bind would lose both). `command` is
  unchanged on Checkbutton/Radiobutton/Scale/Spinbox, where it and `click` fire independently.
- **Existing forms migrate on load.** A Button with a wired `command` event is rewritten to `click`
  (`WidgetDescriptor.from_dict`); if both were wired, `command` wins (matching the old codegen). The
  Events tab and guide now show Button's `click` as `command=` (Fired on click), not `<Button-1>`.

## [2026-06-26] — Auto CI image component no longer duplicates/resurrects

### Fixed
- **A deleted `{canvas}_ci` Image component no longer reappears on restart.** The auto-sync that backs
  CanvasImage items (`_sync_ci_image_component`) created a `_ci` component for *every* CI image path —
  even paths already provided by another Image component on the same canvas. Codegen resolves a CI
  image item to the first matching Image component, so the `_ci` duplicate was dead code that couldn't
  be deleted (the next load recreated it). The sync now excludes paths already covered by another
  Image component targeting that canvas (or `Global`); when all CI paths are covered, the `_ci`
  component is omitted/removed. Generated code is unchanged (items still resolve to the covering
  component).

## [2026-06-25] — Component management works in CI mode

### Fixed
- **Renaming, connecting, disconnecting, editing, and deleting components now work while in
  Canvas-Item edit mode.** `_on_comp_rename`, `_on_comp_connect`, `_on_comp_disconnect`,
  `_on_comp_edit`, and `_on_comp_delete` all looked the component up on `self._design_canvas.form` —
  the synthetic CI sub-form, which has no components — so they silently bailed (the ⚡/×/… buttons and
  tray rename/delete did nothing in CI mode). They now resolve the original form via `ci_original_form`
  in CI mode, matching `_on_comp_select`/`_on_comp_prop_change`; the connector correctly lists the
  original form's real widgets, rename refreshes via `load_component(form=…)`, and delete clears the
  panel + refreshes CI palette images.

## [2026-06-25] — Dialog close-mode rename + unload/_on_close

### Changed
- **Dialog `unload` event now shows as wired to `_on_close`.** Both bind the
  `WM_DELETE_WINDOW` protocol, so a separately-wired `unload` would silently collide with the
  always-wired `_on_close`. On dialog forms the `unload` Events row is now read-only and displays
  `_on_close`; choose hide/exit via its **…** options on the Handlers tab. Double-clicking the row
  jumps to `_on_close`.
- **Close-mode option renamed `destroy (exit)` → `exit (destroy)`.** Applies to `_on_close`,
  `_on_escape`, and the `open_dialog` mode picker. Existing `.form.json` files are migrated on load
  (`_migrate_close_mode` rewrites `handler_options` + `HandlerWire.option`), and `_resolve_option`
  keeps a legacy alias so older saved projects keep their chosen mode.

## [2026-06-25] — Designer handler-wiring fixes + split-tab crash

### Fixed
- **A catalog handler wired to a form event now appears on the form's Events tab.** Connecting e.g.
  `_set_always_on_top` to the form's `load` event via the Handlers tab left the Events tab blank —
  the wired-handler visibility added for widget events never covered form-level events. `load_form`
  now consults the same wire lookup (`_wire_method_map("__form__")`) and shows the connected handler
  as a read-only row (`load   _set_always_on_top`), matching the widget Events tab.
- **The Events tab refreshes immediately after wiring.** Handlers-tab wire/unwire/edit only redrew
  the Handlers tab, so a freshly wired handler didn't show on Events until the form/widget was
  reselected. The connect/disconnect/edit paths now call `reload_after_wire()`, which re-populates
  the active view (widget or form).
- **Deleting a widget now fully disconnects handlers wired to it.** Removing a widget that a catalog
  handler was wired to (e.g. `_set_always_on_top` on a button) stripped the wire but left the handler
  in the Connected section as an enabled-but-targetless entry. `_disconnect_widget` now also drops the
  handler from `enabled_handlers` / `handler_options` when no other wire references it. (CI objects
  were already covered — their bindings live on the item and go with it.)
- **Dragging a tab into the split no longer crashes with `'NoneType' has no attribute 'add'`.** After
  moving the split's last tab back to main (which hides, not closes, the pane), dragging a tab back in
  re-showed the now-empty pane — which tore it down via `_close_split` mid-flight and left the caller
  adding a tab to a `None` notebook. `_ensure_split_shown` now rebuilds the pane in that case so it
  always hands back a live notebook.
- **Double-clicking a wired form-event row jumps to the form event, not the handler.** A form event
  with a connected catalog handler (e.g. `load` → `_set_always_on_top`) displays the handler name, so
  double-clicking it navigated to `_set_always_on_top` instead of the form's `_on_load` stub. It now
  jumps to the event's own method (`_on_load`); the connected handler is still reached from the
  Handlers tab. (Widget event rows are unchanged — they jump to the connected handler.)

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
- **Row Editor dialog** for the Treeview `rows` prop — seed rows inserted at startup. The grid is
  derived from the current columns (a `(tree)` cell for the `#0` label when shown, then one cell per
  data column); add / reorder / remove rows. Rows are stored as `{text, values}` dicts and drive the
  canvas preview (falling back to placeholder rows when empty). Codegen emits an
  `insert("", "end", text=…, values=(…))` call per row (`text=` only when the tree column is shown).

### Changed
- **Available Components** (Handlers tab) now **expands by default** (▼) instead of starting
  collapsed, so the connectable component handlers are visible without an extra click.
- Hovering the **▶/▼ crease** of the Available Components header now highlights **only the
  triangle** (teal) while the "Available Components" label stays dim — signalling the header is
  clickable. The arrow and label are drawn as separate canvas items to keep the recolor scoped to
  the glyph.

## [2026-06-23] — Canvas-item handler wires appear in the Connected section

### Added
- **CI handler wires now show as Connected handlers.** After wiring a catalog handler to a canvas
  item's tag event in CI mode, the binding appears in the **Connected** section of the Handlers tab
  with the same look as widget wires — the resolved action as the row name (e.g. `→ Dialog1`) and
  `tag.event` as the target. Previously the wire was only visible on the Events tab.
- **× disconnect** on a Connected CI row removes the tag-event binding from both the canvas item and
  the live sub-form widget, pruning the tag from the item when no other binding on it still uses it.
- **… edit** on a Connected CI row reopens the **Canvas Item Connector** pre-selected to the existing
  object, tag, event, and option (button reads **Update**); applying replaces the old binding so
  changing the tag or event never orphans the previous one. Double-clicking the row jumps to the
  generated tag-bound method.

### Changed
- **Every Connected handler row now leads with the `→` arrow**, not just multi-wire/CI rows — a
  consistent visual for "this is wired."
- **Wired catalog handlers now appear on the widget's Events tab.** When a handler is connected to a
  widget event via the Handlers tab (e.g. `_set_always_on_top` → `command`), the matching Events row
  shows it as a read-only entry (`command   _set_always_on_top`); multi-target handlers like
  `open_dialog` show the resolved opener (`_open_Dialog1`). Managed from the Handlers tab; double-click
  still jumps to the handler. (CI mode already surfaced tag-bound handlers this way.)

### Fixed
- **Component-wired Events rows no longer show a stray `×` clear button.** Widget events wired to a
  component handler (e.g. a Socket scaffold's Connect button → `_sock1_toggle_connect`) are now
  rendered read-only like catalog wires, since the connection is owned by the Handlers tab. Previously
  hovering the row offered an inline `×` that didn't belong there.

### Fixed
- **Internal CI binding maps are no longer shown as raw property rows.** `_ci_binding_tags` and
  `_ci_binding_handlers` are hidden in the Properties tab (the Canvas Item Connector owns them),
  matching how the other internal CI fields are already suppressed. (A future **Advanced Properties
  view** to surface all such hidden fields is queued in `ROADMAP.md`.)

## [2026-06-19] — Wire catalog handlers to canvas items inside CI mode

### Added
- **Catalog handlers can now be wired to canvas-item events while in Canvas-Item edit mode.**
  Clicking ⚡ on a connectable handler (e.g. `open_dialog`) with a canvas item selected opens a new
  **`CanvasItemConnector`** — an **Object / Tag / Event** dialog (instead of the widget-scoped
  `ComponentConnector`). Pick the item, the binding tag (its own id-tag affects only that item; a
  shared tag fires for every item carrying it — surfaced with an `×N` count and a warning), and the
  event. Dialog options are read from the *original* form's `linked_dialogs`, not the synthetic
  sub-form.

### Changed
- `CanvasItemDescriptor` gained `binding_handlers` (`tk_event → {handler_id, option}`), persisted only
  when non-empty and carried through `ci_to_widget`/`widget_to_ci`. Codegen injects the catalog
  handler's wire body into the tag-bound method instead of a blank stub (user-edited bodies still win).
- Clearing a canvas-item event now also drops its tag binding and any attached catalog-handler body.

### Fixed
- **Double-click on a tag-inheriting canvas item now jumps to its handler.** A CI item that inherits
  its binding from a sibling sharing the same tag (so it has no own `events` entry) used to flash the
  Events tab instead of navigating; it now resolves the tag-aggregated handler.
- **Switching/removing forms while editing canvas items no longer wipes them.** Leaving a form mid-CI
  (FORMS-list click, form remove, or form delete) now commits the CI sub-form back to its real form
  first. Previously the canvas kept a stale CI state on the newly loaded form and a later Escape
  rebuilt the original form's `canvas_items` from the wrong widget list, deleting every item.
  `DesignerCanvas.load_form` now guards this for *all* form switches.
- **Treeview generated code crashed with `unknown option "-rows"`.** The designer-only `rows` (seed
  rows) prop was missing from the structural-prop skip list, so codegen passed `rows=…` to
  `ttk.Treeview()` instead of emitting only the `insert()` calls.
- **Split editor sash positioning is now robust.** Opening/reopening the split (notably in designer
  mode) could crash with "sash index 0 out of range" or reopen jammed against the right edge, because
  `sashpos()` set right after `PanedWindow.add()` is undone by tkinter's later geometry pass. A short,
  generation-guarded re-assert chain (`_position_split_sash`) holds the target across the relayout,
  waits for two realized panes, and falls back to the midpoint for stale/edge positions.

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
