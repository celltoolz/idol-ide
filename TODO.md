# IDOL IDE — TODO

Working list for the `fix/v1.1.2-finish-todo-sweep` branch (`fix/idol-todo-sweep`
merged to master as `fdc00f9`). Longer-term plans live in `ROADMAP.md`; this
file is what's next.

**Filing rule, learned the hard way twice on this branch.** Two entries here
were written from a plausible mechanism rather than a confirmed failure, and
both dissolved on contact: the re-arm loops (the interpreter does not do what
the entry said) and the runtime-error indicator (the symptom was expected
behaviour, mentioned in passing while testing something else). A crash observed
*while deliberately breaking something* is not evidence of a second bug. Before
an entry goes in: what was seen, what was expected instead, and was the thing
that failed already known to be broken. Analysis is not evidence — the indicator
entry contained a careful trace proving nothing was wrong, and got filed anyway.

## 🚧 Active Work

Each step is its own commit. **Ordered by evidence now, not by dependency** —
after step 1, exactly one item here has an observed symptom, and it goes first.

- [x] **Step 1 — guard every self-re-arming `after` loop.** Shipped, but as
      **hygiene, not a bug fix** — the filed mechanism does not reproduce. See
      *The re-arm loops* under Done for what was actually true.
- [x] **Step 2 — `on_packages_changed`.** Shipped. Three producers report to
      `app._on_packages_changed` (the panel's install/uninstall, the Designer's
      install-Pillow row, `!pip` from the palette); the Designer's
      `invalidate_package_cache` is the first consumer. Fires on failure too —
      neither backend knows whether the operation worked. The re-render was the
      half that made it visible: clearing the cache alone left the stale row on
      screen until the user happened to reselect the widget.
- [ ] **Step 3 — three latent defects in `_try_fire_runtime_error`.** Found by
      reading `widgets/output.py`, **not by any reported failure** — see the
      Bugs entry for why the symptom that prompted the read turned out not to
      exist. Real defects, low urgency: the swallowed exception (`:349`),
      `matches[-1]` picking the wrong frame (`:346`), and the `"exit code 0"`
      whole-buffer substring test (`:341`).
- [ ] **Step 4 — classify a missing module from run output.** Scan for
      `No module named '<x>'` and offer to install `<x>`, routed through the
      same conda/pip decision `_on_designer_install_pillow` (`app.py:10692`)
      already makes. A genuine feature — it is what would have made the Pillow
      uninstall self-explanatory instead of a bare traceback. Wants step 3
      landed first, since it adds a consumer to the run-output path.

Step 4 changes the runtime-error indicator's behaviour, so `docs/terminal.md`
ships with it (Definition of Done). Steps 2 and 3 are both internal.

## 🐛 Bugs

- [x] **Uninstalling Pillow leaves the Designer believing it is still there,
      and the run just crashes.** *First half fixed (`on_packages_changed`);
      the second half — classifying a missing module from run output — is
      Active Work step 4 and stays open.* Remove Pillow from the Package Manager in a
      conda env, and the Designer keeps rendering image props as healthy — no
      "⚠ click to install Pillow" row — then Run fails with a bare
      `ModuleNotFoundError: No module named 'PIL'` from the generated
      `from PIL import Image, ImageTk`.
      - **Cause is a one-directional cache.** `DesignerProperties._pil_available`
        (`widgets/designer_properties.py:109`) memoises the
        `python -c "import PIL"` probe, and `_check_pil_async` short-circuits on
        it — so once it is `True`, re-selecting the widget re-runs nothing. It
        is invalidated in exactly two places: `set_active_python`
        (`designer_properties.py:2118`) and `app._on_pillow_install_done`
        (`app.py:10780`). **Install invalidates it; uninstall never does.**
        That asymmetry is why this reads as a regression — installing Pillow
        *from the Designer* has always cleared the warning correctly, so the
        mechanism looks like it works. It was never wired the other way.
        Nothing here changed in the conda-channels work.
      - The real gap is that **`PackageManagerPanel` has no outbound
        notification at all**. `_exec_backend_op` finishes with
        `on_done=self._load_installed`, which refreshes its own tree and tells
        nobody. Any consumer that caches "is package X present" has the same
        bug latent; Pillow is just the one with a visible surface. Fix wants an
        `on_packages_changed` callback wired in `app._build_packages_tab`,
        firing after install *and* uninstall, with the Designer's invalidation
        hanging off it — not another special case for Pillow.
      - **Second, separable half: nothing classifies a run failure.**
        `grep -rn "ModuleNotFoundError"` over the repo returns zero hits.
        `app._on_runtime_error` (`app.py:2554`) is purely line-based — it jumps
        to the line, paints the amber gutter triangle and flashes the Problems
        tab. For a missing import that lands on a generated `import` line
        inside the IDOL:BEGIN block, which is both unhelpful and un-editable.
        Wants the run output scanned for `No module named '<x>'` and an
        offer to install `<x>` — routed through the same conda/pip decision
        `app._on_designer_install_pillow` (`app.py:10692`) already makes. Worth
        scoping separately: it is a general feature (any missing dependency),
        not a Pillow fix, and it is the half that actually tells a beginner
        what to do.
      - **The Problems panel cannot help here, and that is expected** — worth
        recording so it is not re-filed as a defect. `editor/pyflakes_linter.py`
        is ruff plus `compile()`: ruff is a static linter that never resolves
        imports and has no missing-module rule, and `compile()` only raises on
        syntax — imports are not executed at compile time. Neither can know
        `PIL` is gone. pylsp does not fill the gap either (its pyflakes plugin
        reports *unused* imports, not unresolvable ones). So a missing
        dependency is invisible until the run, which is precisely why the
        run-output classification above is the right place to catch it rather
        than a new diagnostic.

- [ ] **Three latent defects in `_try_fire_runtime_error`** (`widgets/output.py`).
      **No reported symptom — do not treat these as urgent.** They were found
      while investigating "the runtime-error indicator fires unreliably", which
      **was a misfiling and has been withdrawn**: the `ModuleNotFoundError`
      that prompted it was the *expected* result of deliberately uninstalling
      Pillow to test the Designer's "click to install Pillow" row. The crash
      was mentioned in passing, read as a second defect, and written up as one.
      Nobody ever observed the indicator failing to fire.
      - **The withdrawn entry's own analysis found nothing wrong**, which
        should have been the tell. `script_runner` joins both drain threads
        before writing the exit line and the sentinel
        (`script_runner.py:86-98`); `OutputPanel._poll` writes every queued
        line before the sentinel reaches `_finish_run` (`output.py:358-370`);
        `run()`/`run_code()` clear first (`:286`, `:303`); `_TRACEBACK_RE`
        (`:12`) matches both `ModuleNotFoundError` shapes. It should have
        fired, and as far as anyone knows it did.
      - **Still worth fixing, at the weight of latent defects:** each is wrong
        on its own terms, none has a known victim.
      - **`except Exception: pass`** (`output.py:349`) swallows every failure
        inside `_on_runtime_error` — a stale path, `_open_file_at` raising,
        anything. Logging it costs nothing and means a *future* report of this
        shape arrives diagnosable instead of as a code-reading exercise.
      - **`matches[-1]` is the wrong frame to pick** (`output.py:346`). It
        takes the innermost frame in the buffer, so an exception raised inside
        a dependency points at a `site-packages` file and IDOL opens a library
        instead of your code; a chained traceback ("During handling of the
        above exception…") picks the wrong exception's frame entirely. It
        should prefer the innermost frame whose file exists *and* sits inside
        the project, falling back to the first frame after `Traceback`.
      - **`"exit code 0" in text` is a whole-buffer substring test**
        (`output.py:341`). Mostly correct today because every run path clears
        first — but the Package Manager writes into this same panel *without*
        clearing (`get_output_panel` in `app._build_packages_tab`), so this is
        one refactor away from a permanently-disabled indicator. **And it is
        already poisonable now, not only after that refactor:** a user program
        that prints the string "exit code 0" anywhere suppresses the indicator
        for its own crash. Should key off the actual return code, which
        `script_runner` already knows.
      - **Not a defect, but worth knowing before the next report:** *Run in
        Terminal* (`Ctrl+F5` → `run_file_in_terminal`, `app.py:10528`) never
        reaches this code at all — output goes to the PTY, not the Output
        panel. A run started that way is *expected* to show no indicator.
        **Ask which Run was used before filing an indicator bug at all.**

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
- [x] **Phase 3 — guardrails.** All five checks live in one pure place,
      `utils/conda_channels.validate` → `list[ChannelIssue]` worst-first, so the
      editor strip, the channel bar's one-line summary and the tests cannot
      disagree. `empty` is the only **error** (the sole thing that may block
      Save); `conflict` is **suppressed under `channel_priority: strict`**,
      since strict is conda's own documented fix and warning about it would be
      wrong; `order` carries `fix="reorder"` wired to a stable
      `reorder_for_requirements` that moves only what must move; `credential`
      warns about a git-tracked `environment.yml` rather than refusing (the raw
      spec has to reach disk or the channel does not work); `unindexed` is
      **info** — install still works, only search is empty. Both Phase 2
      findings closed: the tokenized-URL warning exists, and the empty-list
      refusal now greys Save and shows the reason instead of silently doing
      nothing.
- [x] **Phase 4 — provenance and probing.** Badges mark only the *exception*
      (`· pip`, or a channel other than the one searched first) — a badge on
      every row is a badge on nothing. `origins` now carries the real channel
      rather than a conda/pypi flag, which is a **superset** of the old value:
      conda reports the literal `"pypi"` for pip-installed packages, so every
      `origin == "pypi"` routing check still means what it did. The `▾ All
      channels` chip scopes search *and* install; scoping search needed
      per-channel maps in `CondaSearchIndex`, because the merged view drops
      every package a higher channel already claimed and filtering it would
      have reported that `defaults` does not offer numpy. `⇢ Preview` runs
      `conda install --dry-run --json` and reports per-package channel
      provenance, or conda's own conflict text on failure.
      - **Also fixed, found by this work:** the test suite's `tk_root` fixture
        now forces a `gc.collect()`. `tkinter.Variable.__del__` calls into Tcl,
        so a `StringVar` orphaned by a GUI test was finalized during whatever
        unrelated test later triggered a generational collection — raising
        "main thread is not in main loop", reporting a
        `PytestUnraisableExceptionWarning` against the **wrong** test, and
        costing ~14 s. Full suite 27 s → 14.6 s, warning gone. Same family as
        the open `make_thread_safe_after` bug below.
      - **Three follow-ups, all found by looking at screenshots of real
        solves rather than by re-reading the code:** the detail pane went stale
        after any install started from a *conda* search — `_refresh_selected_detail`
        re-rendered only what was in `_pypi_cache`, which a channel-index result
        never enters, so the pane still offered **Install** for a package whose
        tree row had already grown a version and a badge (the bug predates this
        branch; Phase 4 made it visible by giving the row something to
        contradict, and `_conda_detail_data` now feeds both paths). The preview's
        "other channels" note measured against the primary channel even under a
        scope, so a conda-forge-scoped preview in a defaults-first project
        reported conda-forge as unexpected on *every* run — handing back what the
        user had just asked for, styled as a warning; the baseline is now the
        scope when one is set, extracted to `conda_channels.preview_note_channels`
        because the subtlety is the choice of baseline, not the set difference.
        And the preview table hardcoded `:<12` for the version column while
        measuring the name column, so one long conda version
        (`libwinpthread 12.0.0.r4.gg4f2fc60ca`) shunted its channel nine columns
        out of line — in a provenance table the channel is the column you scan.
- [ ] **Refresh the channel index by hand.** `CondaSearchIndex.ensure_loaded`
      already takes `force=True` and the per-channel on-disk cache makes a
      rebuild cheap, but nothing in the UI calls it — the index refreshes only on
      its weekly expiry. So a channel that published a package today cannot be
      searched for it until the cache ages out, with no way to say "look again".
      Small: a refresh affordance on the channel bar plus the in-flight state, no
      backend work. Filed because `CONTRIBUTING.md`'s `CondaSearchIndex` row
      already promises it as "Phase 5's Refresh" — a phase that was never scoped
      into the four above, so the reference currently points at nothing.

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

**Bugs**
- [x] **The re-arm loops — filed as a crash, shipped as hygiene.** The entry
      claimed an unguarded `widget.after(16, _pump)` raises
      `RuntimeError: main thread is not in main loop` once the widget is gone,
      and that this made panels untestable at the widget level. **Neither
      reproduces.** `Misc.destroy()` deletes every Tcl command the widget
      registered, and `Misc.after()` registers its callback as exactly such a
      command — so the pending tick invokes a command that no longer exists,
      which dies at the Tcl level and never re-enters Python. Measured for both
      shapes IDOL has (loop on the destroyed widget; loop that touches the
      widget first): no `report_callback_exception`, no unraisable exception.
      Constructing `PackageManagerPanel` and `OutputPanel` and letting the
      `tk_root` fixture destroy them passes with unraisable warnings promoted
      to errors, **against the unfixed code**. The four
      `PytestUnraisableExceptionWarning`s that motivated the entry were almost
      certainly `tkinter.Variable.__del__` — the mechanism documented in the
      Phase 4 note and already closed by the `gc.collect()` in `tk_root`.
      - **Shipped anyway, because one shape genuinely does raise:** a loop
        registered on widget A that re-arms against a *different*, destroyed
        widget B — B's commands are gone while A keeps the loop alive. No site
        in IDOL has that shape. `utils.thread_safe_after.rearm_after` now owns
        every re-arm (ten sites, six of which the original entry never listed —
        including a 25 ms perpetual loop in `app._highlight_active_line` and
        the caret blink in `canvas_codeview`), and the AST allowlist in
        `tests/test_after_rearm.py` is what stops a variant-B loop being added.
        It returns the after-id rather than a bool: three sites store theirs to
        `after_cancel` on an explicit stop, and a bool would have forced them
        back onto bare `widget.after`.
      - **The lesson worth keeping:** the structural test was red against all
        ten sites; the three behavioural tests written alongside it passed
        against knowingly unfixed code and were deleted. *Prove it fails
        without the fix* caught this one — a plausible mechanism, traced
        carefully through the code, that the interpreter simply does not do.
        Measure the failure before writing the guard for it.
- [x] **The remembered interpreter was machine-global, not per-project** —
      `self._explorer_root` was read by three sites and assigned by none, so
      every read fell through to its fallback and two of them keyed
      `interpreter:<home>` instead of `interpreter:<project root>`. It never
      looked like a bug because the write and the read were wrong *consistently*
      — the value round-tripped, just under the wrong name. Symptom: open
      project A on 3.11 and project B on 3.13, and B comes up on A's
      interpreter. Fixed by latching the root in `_on_explorer_root_change`
      (`Explorer.set_root` fires it unconditionally, so it is the one place
      every change passes through). **Latching alone was not enough:**
      `_init_interpreter` runs from `_build_layout`, before the startup path
      that opens a project, so its settings read had to move inside the
      `discover_interpreters` callback — which is delivered via `_safe_after`
      and so cannot fire until the mainloop starts. Left as-is, the latch would
      have fixed the write and left the read looking up a key nothing writes.
      Verified against a real boot: the same script wrote
      `interpreter:C:\Users\Alex` twice before and the two real project paths
      after. Three tests in `tests/test_project_root.py`, all confirmed failing
      against the unfixed `app.py`.

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
