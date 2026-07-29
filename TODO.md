# IDOL IDE — TODO

## 🐛 Bugs
- [x] **Clipboard history paste crash** — `CanvasCodeView.insert()` only takes 2 positional args, but `_paste()` in `app.py` called it with 3. *(fixed — also fixed the focus call on the next line, and made `insert()` undoable)*
- [x] **Ruff LSP formatting flags differ by OS** — *root cause found and fixed; needs a Linux re-test to close.*
  - **Real cause: ruff version drift, not OS and not a user-level config.** Ruff 0.16 expanded its stable default rule set from 59 rules to 413, which pulls in `I001` ("Import block is un-sorted or un-formatted" — the reported message verbatim). Debian was on 0.16.0, Windows on 0.15.11. `requirements.txt` said `ruff>=0.4`, which is what let two machines diverge. The user-level-config theory was **disproven** — there was no such file on the Linux box.
  - Fixed in three parts: pinned `ruff>=0.15,<0.16`; `_run_ruff` now honors a project's own ruff config and otherwise applies an explicit IDOL baseline (`E4,E7,E9,F`) instead of whatever ruff's defaults happen to be; and codegen now emits lint-clean import blocks.
  - **Re-test on Linux after pulling**, since the diagnosis was made there.
- [x] **File open/save dialogs render poorly on Linux** — *fixed and confirmed on Linux.* Cause was `theme_create(parent="alt")` in `widgets/notebook.py` not inheriting TEntry's `-selectbackground`/`-selectforeground`; Tk's X11 file dialog reads exactly those two values to colour its `::tk::IconList` selection, so both came back `""` and the clicked file was drawn with `-fill ""`. Windows/macOS use the native dialog and never ran that code. Fixed by styling (`style.configure` after `theme_use`), no custom dialog. Also removed a dead `option_add("*Listbox.…")` block that had claimed to fix this — the dialog has no Listbox in it.
- [x] **Auto-close split breaks when toggling Editor/Designer** — *resolved by removing auto-close entirely.* The split now closes only on the user's own toggle or the pane's ×. Four paths used to take it down automatically; the Designer one combined with the close-last-tab one to lose a split outright across a mode switch. Pinned by an allowlist test so a new auto-close fails CI.

## ✨ Features
- [ ] **Settings panel** — plan agreed 2026-07-28. Four commits, each shippable.
  - **Organizing principle — three scopes, and the rule that decides where anything goes:**
    - **Preference** ("how do I like my IDE?") → `~/.idol/settings.json`, follows the *user* across every project.
    - **Workspace state** ("what was I doing here?") → `.idol-project` / `session.json`, follows the *project*.
    - **Project config** ("how is this codebase built?") → files in the repo (`ruff.toml`, `environment.yml`), follows the *code* into git.
  - **The bug this fixes:** `session.restore()` applies `appearance.theme`, `appearance.font` and `minimap_visible` from whichever file it reads — including a project's `.idol-project`. Opening a different project silently changes your theme and editor font. The Ollama server URL is per-project for the same reason.
  - **Not persisted at all today:** Highlight Active Line, Active Line Color, Show Sidebar, Show Panels, active panel tab, Zen Mode, tab size.
  - **Phase 1** — grow `utils/settings.py` into a real store (schema + defaults + change notification); migrate the leaking preferences out of the session, silently.
  - **Phase 2** — the panel: a notebook tab like Package Manager, two-pane with a category list and a search box, rendered from the schema.
  - ~~**Phase 3**~~ — done. Persisted Highlight Active Line, Active Line Colour, Show Sidebar, Show bottom panel; added tab size, autocomplete and auto-close pairs. Two classification calls: the **active panel tab** went to *workspace* state (it is "what was I doing here"), and **Zen Mode is deliberately not persisted** — transient focus state, and restoring into it would open IDOL with everything hidden.
  - ~~**Phase 4**~~ — done. Change Font, Highlight Active Line, Active Line Color and Show Minimap moved into Settings; Show Sidebar, Show Panels, Zen Mode and the Theme submenu stayed in View, bound to the same stored value. Also moved `show_on_startup` out of `recent.json` into `general.show_welcome_on_startup`, and replaced the Welcome tab's last `tk.Checkbutton` with `DarkCheckbox`.
  - **All four phases complete.** Preferences now live in one place, and `settings.json` holds only what differs from the defaults.
  - Categories: Editor · Appearance · Python · Diagnostics · Run & Debug · Designer · AI · General.
  - Run target / action / cwd mode stay **workspace** state — the run config belongs to the project.
  - Ruff rules: the panel **edits the project's `ruff.toml`**, never mirrors rules into `settings.json`. Two sources of truth for lint config is the exact divergence the ruff work just fixed.
- [ ] **Package Manager nav shortcut** — clicking Package Manager (nav bar / Help) while in Designer should switch to Editor with the Package Manager tab visible.

## 🎨 UI/UX Polish
- [ ] **New Project Wizard cursor fix** — 'Open Project' and 'Back' buttons on the finish screen should use a hand cursor.

## 🗣️ Needs Discussion
- [ ] **Bracket/quote matching behavior** — should not trigger while writing inside a comment. Also general setup of matching doesn't feel right in the editor — needs more context/investigation before scoping.
- [ ] **Conda channel handling in Package Manager** — start with conda-forge; figure out the overall approach.

## ✅ Done this pass
- [x] **Find/Replace undo** — the public mutation API never snapshotted the buffer, so every replace was invisible to undo. Added `begin_undo_group`/`end_undo_group` so Replace All undoes as one step. Also fixed `delete_selection` never firing `on_change` (Replace All with an empty replacement left the tab clean and the linter stale).
- [x] **Per-project clipboard history** — `utils/clipboard_store.py`; project open → that project's history (50 entries), no project → scratch history (20). Both persist. Stored in `~/.idol/clipboard/`, never in the project folder.
- [x] **Ruff config** — `ruff check .` went 483 → 0. Added `ruff.toml`; 446 were house-style rules now configured off with reasoning, 37 were genuine and fixed. One was live: `_palette_run_pip` closed over an `except ... as e` name inside a deferred lambda, so a failed pip command reported nothing to the Output panel.
- [x] **Tracked project root** — `_project_path` is now latched by the deliberate project paths instead of re-derived from the explorer root on every read.
- [x] **Ruff OS divergence** — diagnosed on Debian, fixed in three commits (pin, lint policy, codegen). See the Bugs entry above.
- [x] **Test suite + CI** — pytest suite in `tests/`, GitHub Actions across Linux + Windows on 3.11/3.13, lint and tests both gating. Closes the gap where nothing linted generated projects. See the Testing section in `CONTRIBUTING.md`.
- [x] **Color swatch → color picker in editor** — hover a hex swatch, VS Code style, no alpha. `widgets/color_picker.py` is split into a reusable `ColorPicker` frame and a `ColorPickerPopup` that owns the hover lifetime. Live edits, one undo step per session. Fixed on the way: colours drifted a channel per open (`int()` truncation on the HSV round trip), and scroll-dismiss never fired because the engine's wheel handlers return `"break"`, which suppresses `add="+"` bindings.
- [x] **Swatch column math** — selection, multi-cursor selection and find highlights all measured with a raw `font.measure`, so they drifted by the swatch's width; `_col_from_x` had the same bug in reverse, misplacing clicks. All four now use `_measure_to_col`.
- [x] **Stale Problems panel on delete** — Backspace/Delete over a selection never fired `on_change`, so a diagnostic outlived the code that caused it until the next keystroke.
- [x] **Custom color chooser** — `ColorChooserDialog` + a drop-in `askcolor` in `widgets/color_picker.py`, wrapping the same `ColorPicker` as the editor popup with old/new swatches, R/G/B fields and OK/Cancel. Replaced `tkinter.colorchooser` in the Designer properties panel and View → Active Line Color. Generated user projects still use the stdlib chooser, which is correct.
- [x] **Custom font chooser** — `widgets/font_chooser.py`; `tkfontchooser` dropped from `requirements.txt`. Windows-dialog layout, project-wizard palette, effects opt-in (Designer only — the editor has no use for underline/strikeout), fixed-size scrolling preview that cannot resize the window. **Both call sites now open on the current font, which neither did before**: the Designer passed `font=init`, which landed in `**font_args` where nothing read it, and the editor passed nothing at all. Also promoted the canvas-drawn checkbox out of `designer/menu_editor.py` into `widgets/dark_checkbox.py` rather than making a second copy.

## 📌 Known, not yet scoped
- **`_project_root_cwd()` still uses the explorer root**, not the latched project. It drives the Run/Debug "project" cwd mode, so *Set as Root Directory* on a subfolder makes runs use that subfolder. That may well be what you want when you deliberately re-root — left alone rather than changed silently. Decide the intended behaviour before touching it.
- **Ruff rule editing from Settings** — its own piece of work, planned separately. The panel edits the project's `ruff.toml` directly; needs a design pass on presenting rule groups, what happens when no config exists yet, and how to show which rules a project inherited vs chose. Pairs with the "LSP on/off, ruff on/off" idea in `ROADMAP.md`.
- **Conda channel management from Settings** — also its own piece. Edits `~/.condarc` (and a project's `environment.yml` channels), which is project config, not a preference. Start from the conda-forge question already in Needs Discussion.
- **Per-project setting overrides** — VS Code's User vs Workspace split. The Phase 1 schema is designed to allow it; building it is deliberately out of the first pass. Decide the precedence rules and the UI for "this is overridden here" before starting.
- **Ruff's ceiling should be raised deliberately.** `ruff>=0.15,<0.16` holds the known-good 59-rule default set. Now that `_run_ruff` passes an explicit `--select` when a project has no config of its own, moving to 0.16+ is much safer than it was — but it needs a pass over what the newer rules would show a beginner before the pin is lifted.
