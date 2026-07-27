# IDOL IDE — TODO

## 🐛 Bugs
- [x] **Clipboard history paste crash** — `CanvasCodeView.insert()` only takes 2 positional args, but `_paste()` in `app.py` called it with 3. *(fixed — also fixed the focus call on the next line, and made `insert()` undoable)*
- [ ] **Ruff LSP formatting flags differ by OS** — on Linux it flags the top lines of `main.py` and `<projectname>.py` as un-sorted/un-formatted; doesn't happen on Windows.
  - **Likely already fixed** by the new `ruff.toml`. The repo had no ruff config at all, so ruff fell back to its defaults and then to a *user-level* config (`~/.config/ruff/ruff.toml` on Linux, `%APPDATA%\ruff\ruff.toml` on Windows) — different config per machine, different rules. "Un-sorted imports" is `I001`, which is **not** in ruff's defaults, so something on the Linux box was selecting it. A checked-in config wins over the user-level one.
  - **Needs re-testing on Linux to confirm.**
- [ ] **File open/save dialogs render poorly on Linux** — look fine on Windows, but clicking a file/folder on Linux makes it render invisible. Try fixing via styling first before considering a custom dialog — reuse over rebuild.
- [ ] **Auto-close split breaks when toggling Editor/Designer** — needs a fix.

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

## 📌 Known, not yet scoped
- **`_project_root_cwd()` still uses the explorer root**, not the latched project. It drives the Run/Debug "project" cwd mode, so *Set as Root Directory* on a subfolder makes runs use that subfolder. That may well be what you want when you deliberately re-root — left alone rather than changed silently. Decide the intended behaviour before touching it.
