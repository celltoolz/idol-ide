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
- [ ] **Color swatch → color picker in editor** — clicking a color swatch should let you choose a color (see `ROADMAP.md`).
- [ ] **Custom color chooser** — replace the temporary `tkinter.colorchooser` with a custom implementation.
- [ ] **Custom font chooser** — drop `tkfontchooser` and build our own for IDOL. Requirements:
  - Must open already scoped to the currently selected font/size/style
  - Must work on macOS, Linux, and Windows
  - Appearance doesn't matter — function only
  - Before dropping it, look at how `tkfontchooser` handles "open to current selection" — it does this well
- [ ] **Settings menu** — build it out; would be the right home for conda channel management.
  - **Also the right home for LSP + ruff rule configuration.** The project now has a `ruff.toml` with a deliberately narrow rule set (bug rules on, house-style rules off). Surfacing that as a settings page — toggle rule groups, per-project overrides — is a natural fit, and pairs with the existing "LSP on/off, ruff on/off" idea already in `ROADMAP.md`.
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
- [x] **Test suite + CI** — 94 pytest tests in `tests/`, GitHub Actions across Linux + Windows on 3.11/3.13, lint and tests both gating. Closes the gap where nothing linted generated projects. See the Testing section in `CONTRIBUTING.md`.

## 📌 Known, not yet scoped
- **`_project_root_cwd()` still uses the explorer root**, not the latched project. It drives the Run/Debug "project" cwd mode, so *Set as Root Directory* on a subfolder makes runs use that subfolder. That may well be what you want when you deliberately re-root — left alone rather than changed silently. Decide the intended behaviour before touching it.
- **Ruff's ceiling should be raised deliberately.** `ruff>=0.15,<0.16` holds the known-good 59-rule default set. Now that `_run_ruff` passes an explicit `--select` when a project has no config of its own, moving to 0.16+ is much safer than it was — but it needs a pass over what the newer rules would show a beginner before the pin is lifted.
