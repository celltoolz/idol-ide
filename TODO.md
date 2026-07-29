# IDOL IDE — TODO

Working list for the `fix/idol-todo-sweep` branch. Longer-term plans live in
`ROADMAP.md`; this file is what's next.

## 🐛 Bugs

- [ ] **`self._explorer_root` is never assigned, so the remembered interpreter
      is global instead of per-project.** Three sites read it via
      `getattr(self, "_explorer_root", None) or <fallback>` and every one of
      them always takes the fallback — the attribute is written nowhere in the
      repo (`_set_explorer_root` sets the *explorer's* root and relies on
      `on_root_change`; it never stores a copy on the app).
      - `workspace_save` (`app.py:4446`) is **harmless** — its fallback is
        `self._sidebar.explorer._root or os.getcwd()`, which is the right
        answer anyway.
      - `_init_interpreter` (`app.py:10609`) and `_set_interpreter`
        (`app.py:10660`) both fall back to `os.path.expanduser("~")`, so the
        interpreter is stored and read as `interpreter:<home>` rather than
        `interpreter:<project root>`. They are wrong *consistently*, which is
        why this never looked like a bug: the write and the read agree, so the
        value round-trips. The symptom is that there is only ever one
        remembered interpreter for the whole machine — open project A, then
        project B, and B comes up on A's interpreter.
      - Fix is to read the explorer root the way `_add_to_environment_yml` and
        `PackageManagerPanel.set_project_dir` do, or to actually latch the
        attribute in `_on_explorer_root_change`. Prefer the latch — three call
        sites already expect it to exist.
      - **Touches the conda channel work:** the channel bar reads the project's
        `environment.yml` while installs run against the active interpreter, so
        an interpreter that does not follow the project can leave the bar
        describing project A's channels next to project B's environment. Not a
        blocker for Phase 2 (both are per-project once the interpreter is
        right), but fix it before Phase 4's per-package provenance badges.

## ✨ Features

### Conda Channels

Scoped 2026-07-29. Three decisions settled before any code: the store is the
project's **`environment.yml` `channels:` block** (not IDOL settings — a shadow
copy of project config is what `utils/settings.py`'s scope rule forbids); the
surface is the **Package Manager**, not Settings (the panel already owns every
conda concern, and Settings renders from `SCHEMA` by `kind` and would need a
bespoke pane for one non-preference feature); and **there is no enable/disable
toggle** — a conda-native portable file can only represent *active* channels,
because that is all conda has. Removing `defaults` from the list writes
`nodefaults`, so the "don't use Anaconda defaults" toggle is redundant too.

`~/.condarc` is the **seed**, not the store: it already feeds a new project's
`environment.yml` at creation (`project_wizard.py`). Chain is `~/.condarc` →
seeds `environment.yml` → project edits are local. That is why no
import/export round-trip is needed.

Each phase is independently shippable. **Tests green before every commit** —
`pytest -m "not gui"` and `ruff check .`.

- [x] **Phase 1 — the channel bar, read-only.** A `CHANNELS` strip between the
      search bar and the package list, conda interpreters only (same condition
      as the existing `conda | PyPI` toggle). Numbered active list
      (`1 conda-forge · 2 pytorch` — never top/bottom language), effective
      `channel_priority`, and a dim source line (`from environment.yml` /
      `from ~/.condarc (no environment.yml)` / `from $CONDA_CHANNELS`) so the
      UI cannot lie about which config won. Tokenized URLs render masked.
      Ships: `data/idol_conda_channels.json` catalog;
      `utils/conda_env.project_channels(root)` reading `environment.yml` (pure
      file parse — correct home, next to `configured_channels`); a read layer in
      `editor/conda_manager.py` over `conda config --show` / `--show-sources
      --json`, passing `env=build_env(prefix)` so the env-level `.condarc`
      actually merges; `utils/conda_channels_guide.py` + `GuideWindow`. Zero
      writes.
- [x] **Phase 2 — make the list real.** The editor modal (dark `Toplevel`,
      `ComponentConnector` precedent): Available / Searched two-pane, `Add →`,
      `▲ ▼ ✕` on the right only, catalog description box below. Writes
      `channels:` / `nodefaults` to `environment.yml`. `-c` threading through
      **both** conda call sites — `CondaManager.install` and
      `project_manager`'s `conda create` — with `--override-channels` only when
      the project has an `environment.yml`. `CondaSearchIndex.ensure_loaded`
      takes the channel list as an argument and derives loaded-ness from the
      channel set (today it calls `configured_channels()` itself, so it cannot
      be told about a per-project list, and a project switch that keeps the same
      interpreter never re-fires). `file://` branch in `channeldata_urls` (a
      local channel currently builds
      `https://conda.anaconda.org/file:///…`). ToS `pending` filtered to the
      active list — otherwise conda-forge-only users get a `defaults` ToS
      dialog for a channel the install will not touch.
      *Edit and threading ship together: an editor that writes a file which
      does not change what installs is the UI lying, one phase early.*
- [ ] **Phase 3 — guardrails.** `defaults` + `conda-forge` mixed-channel warning
      under flexible priority. `requires_order_below` one-click `[ Fix order ]`.
      "Channel published no searchable index" signal — `CondaSearchIndex`
      already tracks it as `missing_channels`, nothing displays it yet.
      Two things Phase 2 surfaced that belong here:
      - **A tokenized channel URL is written to `environment.yml` verbatim**, and
        that file is git-tracked. It has to be, or the channel doesn't work — so
        the answer is a warning at add time ("this URL contains a credential and
        environment.yml is usually committed; conda's own guidance is to keep
        tokenized channels in `~/.condarc`"), not a refusal. Display and logging
        are already masked via `conda_env.mask_channel`; this is the one path
        where the raw spec legitimately lands on disk.
      - **Empty-list refusal is currently silent.** `write_project_channels` and
        the editor's Save both refuse, so nothing breaks, but Save simply does
        nothing and the user is told nothing. Needs the real warning.
- [ ] **Phase 4 — provenance and probing.** `[All] / specific channel` selector
      in the search bar (`-c X --override-channels`). Per-package channel badges
      — nearly free, `conda list --json` already reports `channel` and
      `conda_manager` already parses it. Transient `conda install --dry-run`
      conflict probe with a modified `-c` set, so "is bioconda causing this?"
      never dirties a git-tracked file.

**Deferred, note-and-move-on:** `.condarc` writes; `channel_priority` editing
(see *Known, not yet scoped*); mirrors / `channel_alias` / `custom_channels` /
`whitelist_channels`; auth beyond token masking; per-package
`conda-forge::numpy` pinning (the guide mentions it exists); mamba/micromamba
(libmamba honours the same config, so mostly free).

## 🎨 UI/UX Polish

*None open.* See **Done** below.

## 🗣️ Needs Discussion

*None open.* Conda channels is scoped — see **Features** above.

## 📌 Known, not yet scoped
- **`_project_root_cwd()` still uses the explorer root**, not the latched project. It drives the Run/Debug "project" cwd mode, so *Set as Root Directory* on a subfolder makes runs use that subfolder. That may well be what you want when you deliberately re-root — left alone rather than changed silently. Decide the intended behaviour before touching it.
- **Ruff rule editing from Settings** — its own piece of work. The panel edits the project's `ruff.toml` directly, never mirrors rules into `settings.json`; two sources of truth for lint config is the exact divergence the ruff work fixed. Needs a design pass on presenting rule groups, what happens when no config exists yet, and how to show which rules a project inherited vs chose. Pairs with the "LSP on/off, ruff on/off" idea in `ROADMAP.md`.
- **Per-project setting overrides** — VS Code's User vs Workspace split. The settings schema is designed to allow it; building it was deliberately out of scope. Decide precedence rules and the "this is overridden here" UI before starting.
- **Empty Settings categories** — the panel currently has Appearance, Editor, AI and General. Python, Diagnostics, Run & Debug and Designer were planned but have no settings yet; sections only appear once something lands in them.
- **`channel_priority` has no home under the environment.yml store.** Conda's
  three-way `channel_priority` (`strict` / `flexible` / `disabled`) changes what
  channel *order* means, so the Conda Channels work needs to show it — but
  `environment.yml` has no `channel_priority` key. It is genuinely a
  user/machine-level conda setting, which puts it in `~/.condarc`, a file IDOL
  deliberately does not own (see the Conda Channels decisions under
  **Features**). Phase 1 therefore *displays* the effective value read-only and
  the guide gives the `conda config` command to change it; the display is the
  load-bearing part, since you cannot debug a mixed-channel env without knowing
  which mode you are in. Making it editable means either an explicit
  "Apply to `.condarc`" action with a diff preview and snapshot-restore, or
  accepting a fourth store. Decide which before building a selector.
- **Raise ruff's ceiling deliberately.** `ruff>=0.15,<0.16` holds the known-good 59-rule default set. Now that `_run_ruff` passes an explicit `--select` when a project has no config of its own, moving to 0.16+ is much safer — but it needs a pass over what the newer rules would show a beginner before the pin is lifted.
- **The bracket match scan is still comment-unaware**, though the *candidate* under the cursor is now gated on being code. `_scan_forward`/`_scan_backward` in `canvas_editor/bracket_matcher.py` count every `([{` and `)]}` they walk past, so a stray unbalanced bracket inside a comment or a string between your bracket and its real partner still throws the depth off and highlights the wrong one. Deliberately left: fixing it means calling `_caret_contexts` on every line the scan touches, and the scan runs once per paint and walks to EOF whenever a bracket is unmatched — so on a large file with one stray `(` that is the whole buffer re-classified on every keystroke. Wants a per-line context cache invalidated on edit, which is its own piece of work; scope that before touching the scan. Documented in the module docstring and the CONTRIBUTING row so it doesn't read as an oversight.
- **In `ROADMAP.md`, not here:** macOS CI, expanding the test suite (terminal, git, session persistence, codegen preservation, conda paths), and bumping the GitHub Actions versions off the deprecated Node 20 runtime.

## ✅ Done on this branch

**Panel tabs and the designer**
- [x] **Panel tabs open where you can see them** — Welcome, Packages, Learning Mode and Settings are single-instance tabs that now live in whichever notebook opened them, not always the main one. Designer mode `pack_forget`s `self.notebook` (the canvas takes its slot), so clicking Package Manager / Welcome / Learning / Settings from the nav bar or the menus added a tab nobody could see and read as a dead button. They now open in the split pane while the designer is up, opening the split if it isn't. `_PANEL_TAB_SLOTS` + `_panel_tab_home` / `_toggle_panel_tab` / `_build_panel_tab` replace four hand-rolled copies of the same toggle.
- [x] **File > New and File > Open follow the same rule** — both landed in the hidden main notebook while in designer mode. Every `_open_file` caller benefits, so clicking a Problems-panel entry from the designer now shows the file too.
- [x] **Panel tabs can be dragged between panes** — dragging one used to open a blank Untitled in the split and close the tab that was dragged, because the move path only knew how to copy a code buffer. Tk cannot reparent a widget, so a move is close + rebuild. Welcome is draggable too now (it was pinned to main); `_backfill_main_notebook` is what keeps the main notebook from ever being left blank.

**UI/UX**
- [x] **New Project Wizard cursor fix** — 'Open Project →' and '← Back' on the finish screen kept the greyed-out look and lost the hand cursor, because `_show_progress` disables both and `_show_success` never re-enabled them. Both are live there, so both are enabled. `_render` now also resets the Next button's state *and* its binding before each step draws — otherwise Back out of the success screen landed on a Summary step whose Next still re-opened the project just created.
- [x] **Wizard git probe hardened** — `_check_git` ran three bare `subprocess.run` calls with only the first wrapped in a `try`/`except`, from `__init__` on the main thread, so a slow or wedged `git config` raised `TimeoutExpired` and took the New Project dialog with it. Replaced by `git_manager.probe_identity()`, which is total by construction (everything goes through `_run_git`). Also puts the subprocess calls back on the right side of the import rule — `widgets/project_wizard.py` no longer imports `subprocess` at all.

**Editor**
- [x] **Bracket/quote matching is code-only, and openers skip over** — two separate faults behind one complaint. *Openers never skipped:* skip-over was gated on `_CLOSERS`, and the "don't pair mid-word" guard only refuses on an alphanumeric next char, so typing `(` in front of an existing `(` fell through to auto-pair and made `def __init__|(self):` into `def __init__()(self):` — while the mirror-image `)` case behaved correctly. Openers are now in `_SKIP_OVER` too, for `[` and `{` as well. *Pairing was context-blind:* a `(` in a comment paired and the apostrophe in `# don't` became `# don''t`. Auto-pairing is now code-only — suppressed in comments, in strings and docstrings, and in saved plain-text files (an unsaved Untitled buffer still pairs; `language` is `"text"` for both, so the filepath is what separates them). Inside a string only quotes may still skip, because the closing quote *was* auto-inserted and typing over it is how you leave the string — which is also what keeps `"""` docstring completion working. Match *highlighting* got the same rule: a bracket in a comment no longer outlines against real code, and quotes highlight only when they genuinely delimit a string, which fixed `'''`/`"""` pairing outer-to-outer instead of to its own neighbour. The shared machinery is `TokenizerMixin._caret_contexts`. Selection-wrap is untouched — that is an explicit gesture, so it still works inside a string. Two bugs fell out on the way: `self.language` was only ever assigned by `set_filepath`, so a view that never got one had no attribute at all; and multi-cursor `_mc_insert_char` ignored the smart-pairs preference outright.
- [x] **Clipboard history paste crash** — `_paste()` called `CanvasCodeView.insert()` with the old `tk.Text` signature. Also fixed the focus call on the next line (it focused the frame, not the canvas that owns the key bindings) and made `insert()` undoable.
- [x] **Find/Replace undo** — the public mutation API never snapshotted the buffer, so every replace was invisible to undo. Added `begin_undo_group`/`end_undo_group` so Replace All undoes as one step. Also fixed `delete_selection` never firing `on_change`, which left the tab clean and the linter stale after a Replace All with an empty replacement.
- [x] **Stale Problems panel on delete** — Backspace/Delete over a selection never fired `on_change`, so a diagnostic outlived the code that caused it until the next keystroke.
- [x] **Swatch column math** — selection, multi-cursor selection and find highlights all measured with a raw `font.measure`, so they drifted by an inline swatch's width; `_col_from_x` had the same bug in reverse, misplacing clicks. All four now use `_measure_to_col`.
- [x] **Auto-close split** — removed entirely; the split now closes only on the user's own toggle or the pane's ×. Four paths used to take it down automatically, and the Designer one combined with the close-last-tab one to lose a split outright across a mode switch. Pinned by an allowlist test so a new auto-close fails CI.

**Colour and font**
- [x] **Colour picker in the editor** — hover a hex swatch, VS Code style, no alpha. `widgets/color_picker.py` splits into a reusable `ColorPicker` frame and a `ColorPickerPopup` owning the hover lifetime. Live edits, one undo step per session. Fixed on the way: colours drifted a channel per open (`int()` truncation on the HSV round trip), and scroll-dismiss never fired because the engine's wheel handlers return `"break"`, which suppresses `add="+"` bindings.
- [x] **Custom colour chooser** — `ColorChooserDialog` + a drop-in `askcolor`, wrapping the same `ColorPicker` with old/new swatches, R/G/B fields and OK/Cancel. Replaced `tkinter.colorchooser` in IDOL's own UI; generated user projects still use the stdlib one, which is correct.
- [x] **Custom font chooser** — `widgets/font_chooser.py`; `tkfontchooser` dropped from `requirements.txt`. Effects opt-in (Designer only), fixed-size scrolling preview that cannot resize the window. **Both call sites now open on the current font, which neither did before**: the Designer passed `font=init`, which landed in `**font_args` where nothing read it, and the editor passed nothing at all.

**Settings** *(four phases, all complete)*
- [x] **Preferences are a real store** — `utils/settings.py` grew a schema (key, default, type, section, label, description), defaults separate from stored values, reset-to-default, and change notification. Fixed a real leak: `session.restore()` applied theme, font and minimap from whichever file it read, including a project's `.idol-project`, so **opening a project silently changed your theme and editor font**. The Ollama URL was per-project for the same reason.
- [x] **Settings panel** — a notebook tab, two-pane with a category list and a search box that spans every category and matches the dotted key. Rendered entirely from the schema, so adding a preference is a one-line change. Reachable via View → Settings, `Ctrl+,` and the Welcome tab.
- [x] **Persisted the toggles that never were** — Highlight Active Line, Active Line Colour, Show Sidebar, Show bottom panel; added tab size, autocomplete and auto-close pairs. Active panel tab went to *workspace* state; **Zen Mode is deliberately not persisted** (transient focus state — restoring into it would open IDOL with everything hidden).
- [x] **View menu migrated** — settings-shaped items moved into the panel; Show Sidebar, Show Panels, Zen Mode and the Theme submenu stayed as menu toggles bound to the same stored value. Also moved `show_on_startup` out of `recent.json` and replaced the Welcome tab's last `tk.Checkbutton` with `DarkCheckbox`.
- The scope rule this established, documented at the top of `utils/settings.py`: **preference** (follows the user) vs **workspace state** (follows the project) vs **project config** (follows the code into git).

**Tooling and cross-platform**
- [x] **Ruff config** — `ruff check .` went 483 → 0. Added `ruff.toml`; 446 were house-style rules configured off with reasoning, 37 were genuine and fixed. One was live: `_palette_run_pip` closed over an `except … as e` name inside a deferred lambda, so a failed pip command reported nothing to the Output panel.
- [x] **Ruff OS divergence** — *diagnosed and re-verified on Debian; closed.* Not the OS and not a user-level config: ruff 0.16 expanded its stable default rule set from 59 rules to 413, pulling in `I001` ("Import block is un-sorted or un-formatted" — the reported message verbatim). Debian had 0.16.0, Windows 0.15.11, and `requirements.txt` said `ruff>=0.4`. Fixed by pinning `>=0.15,<0.16`, having `_run_ruff` honour a project's own ruff config and otherwise apply an explicit IDOL baseline, and making codegen emit lint-clean import blocks. A leftover gap in the project wizard's `main.py` template was caught by the Linux re-test and fixed.
- [x] **Linux file dialogs** — *fixed and confirmed on Linux.* `theme_create(parent="alt")` did not inherit TEntry's `-selectbackground`/`-selectforeground`, and Tk's X11 file dialog reads exactly those two values to colour its `::tk::IconList` selection — so both came back `""` and the clicked file was drawn with `-fill ""`. Windows/macOS use the native dialog and never ran that code. Fixed by styling; also removed a dead `option_add("*Listbox.…")` block that had claimed to fix it, when the dialog contains no Listbox at all.
- [x] **Tracked project root** — `_project_path` is latched by the deliberate project paths instead of re-derived from the explorer root on every read. *Set as Root Directory* on a subfolder used to hide the project file and silently stop `_autosave_workspace` writing it.
- [x] **Per-project clipboard history** — `utils/clipboard_store.py`; project open → that project's history (50 entries), no project → a scratch history (20). Both persist, stored in `~/.idol/clipboard/` and never in the project folder.
- [x] **Test suite + CI** — pytest suite in `tests/`, GitHub Actions across Linux and Windows on 3.11/3.13, lint and tests both gating. Closes the gap where nothing linted generated projects. See the Testing section in `CONTRIBUTING.md`.
