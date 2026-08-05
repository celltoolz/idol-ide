# IDOL IDE — TODO

Working list for the **v1.2.1** round. Longer-term plans live in `ROADMAP.md`;
this file is what's next.

## How this file is used

This file drives the work. The cycle:

1. **Raw notes** get taken while using IDOL — symptoms, not diagnoses.
2. **Audited against the code** before anything is filed. Confirm the symptom is
   real and the cause is what it looks like; see the filing rule below.
3. **Filed here** — open work in **Active Work**, defects in **Bugs**,
   unscoped ideas in **Known, not yet scoped**, open questions in
   **Needs Discussion**.
4. **Worked through**, moving each item from Active Work into **Done** as it
   ships. Anything found along the way is filed, not fixed in passing.
5. **On publishing a release**, everything in Done moves to `RELEASE.md` and
   this file starts empty, ready for the next round of raw notes.

`RELEASE.md` is local and not in git; `CHANGELOG.md` is the tracked record. The
release notes are written from the Done ledger — see `CONTRIBUTING.md`
§ Release Notes.

**Label towards what is coming, not what came.** v1.2.0 was worked on two
branches both named for v1.1.2 — the version being *fixed* rather than the one
being *shipped* — which made the ledger read as the wrong release all the way to
publication. Branches get conventional names (`feat/`, `fix/`) describing the
work, never the release they land in.

**Filing rule, learned the hard way twice.** Two entries here
were written from a plausible mechanism rather than a confirmed failure, and
both dissolved on contact: the re-arm loops (the interpreter does not do what
the entry said) and the runtime-error indicator (the symptom was expected
behaviour, mentioned in passing while testing something else). A crash observed
*while deliberately breaking something* is not evidence of a second bug. Before
an entry goes in: what was seen, what was expected instead, and was the thing
that failed already known to be broken. Analysis is not evidence — the indicator
entry contained a careful trace proving nothing was wrong, and got filed anyway.

## 🚧 Active Work

Two rounds, terminal first. **Step 2 needs a scoping pass before any code** —
the original conda work got one and it is why the four phases went in cleanly;
the deferred list below is a pile of headings, not a plan.

Each gets its own branch, since they share no theme: `feat/terminal-post-run-analysis`,
then conda.

- [ ] **Step 1 — post-run analysis for terminal runs.** Everything a failed run
      gets in OUTPUT, a failed run in the TERMINAL gets nothing: no
      missing-module offer, no runtime-error indicator, no PROBLEMS entry.
      *Run in Terminal* (`Ctrl+F5` → `run_file_in_terminal`, `app.py:10528`)
      sends output to the PTY, and `_try_fire_runtime_error` /
      `_offer_missing_module` live on `OutputPanel._finish_run`, which that
      path never touches. Currently documented as expected behaviour in
      `docs/terminal.md` — accurate, but it reads like a rule where it is
      really an absence.
      - **The hook already exists and is already wired.** `TerminalPanel`
        fires `on_command_done(exit_code)` from its OSC 133 shell integration
        (`terminal.py:2451`), and `app.py:1191` already listens to clear
        `_running_file`. So "did it fail, and when" is solved; the exit code
        is right there.
      - **What is missing is the text.** OUTPUT scans a `tk.Text` buffer;
        the terminal's output lives in the pyte screen plus `_scrollback`,
        so this needs a way to read back the last command's output as plain
        text. Scope that first — it is the whole job. Note the terminal is an
        interactive shell, so "the last command's output" has no clean
        boundary except the OSC 133 markers themselves.
      - **Only for runs IDOL started.** `_running_file` says which. Scanning
        every shell command the user types for tracebacks would offer to pip
        install things from output IDOL had no part in producing.
      - Both run paths should feed the same PROBLEMS list — `_runtime_problems`
        and `_refresh_problems` already exist and are agnostic about where the
        failure came from, so this is a caller, not a new mechanism.
- [ ] **Step 2 — conda config, round two.** The deferred list from the original
      four phases, promoted to real work. **Scope it first**: these are five
      separate features sharing a config file, not one job, and at least two
      touch `~/.condarc`, which IDOL deliberately does not own today.
      - `.condarc` writes — the decision blocking `channel_priority` editing
        too. See that entry under *Known, not yet scoped*; settle the
        "apply to `.condarc`" question once and both fall out of it.
      - Mirrors / `channel_alias` / `custom_channels` / `whitelist_channels`.
      - Authentication beyond masking tokens in the UI.
      - Per-package `conda-forge::numpy` pinning — the guide already tells
        users it exists, which makes this the one with a promise behind it.
      - mamba / micromamba — libmamba honours the same config, so mostly free.

## 🐛 Bugs

*None open.* Everything fixed for v1.2.0 is in `RELEASE.md`.

## ✨ Features

*Nothing open — the two items that were here are now **Active Work**.* What
remains below is decisions of record, kept because open entries elsewhere turn
on them.

### Conda Channels — decisions of record

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

Each phase was independently shippable, and **tests green before every commit**
— `pytest -m "not gui"` and `ruff check .`. All four phases plus the manual
index refresh shipped in v1.2.0; see `RELEASE.md`. These decisions are kept
because *Active Work* step 2 and the *channel_priority* entry under **Known,
not yet scoped** both turn on them.

## 🎨 UI/UX Polish

*None open.*

## 🗣️ Needs Discussion

*None open.*

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

## ✅ Done — release ledger

**Not a per-branch list**, despite what this heading used to say. It accumulates everything
finished for the coming v1.2.1 release, and stays intact across branches rather
than being cleared when one closes. Newest groups first; each entry is written
to be usable as release copy without rereading the diff. When a release is
published, everything here moves to `RELEASE.md` and this section starts empty.

*Empty — v1.2.0 shipped and its ledger is in `RELEASE.md`.*
