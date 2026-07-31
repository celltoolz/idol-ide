# Package Manager

Press **F3** (or **Help → Package Manager**) to open the package manager panel.

It opens as a tab in whichever editor pane is on screen — while the [GUI Designer](designer.md) has the main area, that means the split pane, so the panel sits beside your form instead of behind it. Drag the tab between panes at any time.

## Installed Packages

All installed packages are shown **grouped by topic** instantly — no network needed, powered by a precomputed 362K-package lookup covering 46% of PyPI.

- **Live filter** — type in the search bar to instantly filter by name or topic (e.g. type "web" to see all networking packages)
- **View toggle** — the `≡ A–Z` / `⊞ Groups` control on the right of the INSTALLED header switches between topic groups and a flat alphabetical list (applies to the live filter too); the choice persists in `~/.idol/settings.json`

## PyPI Search

Press Enter or click **PyPI ↗** to search for new packages by name or keyword. Results are ranked by relevance with well-known packages promoted to the top.

## Package Details

Click any package (installed or from PyPI search) to see its details: version, author, license, and description fetched from PyPI.

## Install & Uninstall

- **⬇ Install** — runs pip in the background with live output streamed to the Output panel
- **✕ Uninstall** — same, with confirmation

All operations use the **active interpreter** — the same one shown in the status bar. Switch interpreters in the status bar and the package list updates automatically.

## Conda Environments

When the active interpreter is a **conda environment**, the panel switches to a conda backend automatically:

- **Search follows the interpreter** — a `conda | PyPI` source toggle appears next to the search button, defaulting to **conda**: results come from the channels this project actually uses (its `environment.yml` when it has one, otherwise whatever your conda is configured with — see *The CHANNELS bar* below), so what you find is exactly what `conda install` can reach. Each channel's package index (`channeldata.json`) is cached locally in `~/.idol/conda_index/` and refreshed weekly, so search is instant and offline-friendly. The cache is per channel, so switching projects re-uses what it already has and only downloads channels it hasn't seen
- **Names differ between conda and PyPI** — conda's `graphviz` is the Graphviz C tool while PyPI's `graphviz` is the Python bindings (`python-graphviz` on conda). Searching the namespace you'll install from shows both with their summaries, so you pick the right one
- **Install routes by search source** — a conda result installs with `conda install` only (no silent pip fallback: swapping tools swaps *products* when names collide); a package picked with the **PyPI** toggle installs with pip inside the env, after a one-line warning that pip-in-conda can conflict with conda's dependency resolver
- **A package picked out of the installed list is not a source choice.** It installs the way the environment normally would — conda in a conda env — unless it carries a `· pip` badge, in which case it stays on pip. Only a search result says "I want this one, from here"
- **Installed list** comes from `conda list` — it honestly includes conda's non-Python packages (openssl, vc, ca-certificates, …), so a fresh env shows a few dozen entries grouped mostly under "Other"
- Packages installed via pip show a **`· pip` badge** in the list
- **Uninstall routes by origin** — pip-installed packages are removed with pip, conda packages with `conda remove`
- If the env's conda executable can't be found (e.g. the base install was removed), the panel falls back to pip inside the env with a notice
- **Terms of Service** — before the first conda-routed install/uninstall, the panel checks whether the conda installation has accepted its channels' ToS (fresh Miniconda installs haven't) and shows an Accept/Decline dialog if not; Accept runs `conda tos accept` (remembered by conda itself), Decline cancels the operation. Search never needs the ToS — the channel index is fetched over plain HTTPS, not through conda. The check is **scoped to the channels the operation will actually search**: a project pinned to conda-forge is never asked to accept Anaconda's terms, even if your `~/.condarc` still lists `defaults`

No `conda activate` is needed for any of this — operations run with a synthesized activation environment.

### The CHANNELS bar

Above the package list, conda environments get a two-line **CHANNELS** strip.

```
CHANNELS   1 conda-forge   ·   2 pytorch    flexible priority   ✎ Edit   ?
           from environment.yml
```

- **Channels are numbered, and `1` is searched first.** The order is a real setting, not a
  display preference — it decides which channel's build of a package you get when two of them
  offer it. Numbers rather than "top"/"bottom" because conda's own flags disagree about
  direction: `conda config --add` puts a channel *first*, `--append` puts it *last*, and
  `conda install -c A -c B` ranks `A` above `B`. This is why copied setup instructions so often
  produce the reverse of what you wanted
- **The second line says where the list came from.** conda merges a system file, your
  `~/.condarc`, a file inside the environment, `$CONDARC` and `$CONDA_CHANNELS` — and
  **environment variables beat files**. A channel list shown without its origin is how you end
  up editing `~/.condarc` and seeing nothing change
- **Your project's `environment.yml` wins.** If the project has one, its `channels:` block is
  what the bar shows — that file goes into git, so `conda env create -f environment.yml` gives a
  teammate the same resolution you get. Without one, the bar shows what conda itself reports and
  says so. `~/.condarc` is what a new project's `environment.yml` is *seeded* from; after that
  the two can differ, and the project's file is the one that matters
- **Priority mode** (`strict` / `flexible` / `disabled`) is read from conda and shown, not
  edited: it applies to your whole conda installation rather than one project, and IDOL does not
  write to `~/.condarc`. Change it with `conda config --set channel_priority strict`
- Channel URLs containing a token are **masked** before display
- **?** opens the Conda Channels guide

### Editing the channel list

**✎ Edit** opens a two-pane picker. **Available** is IDOL's catalog of well-known channels
(conda-forge, defaults, bioconda, pytorch, nvidia, intel, rapidsai) plus anything you type in
the custom box — a bare name, a full URL, an `owner/label` channel like
`pytorch/label/nightly`, or a `file:///path` local channel. **Searched** is your ordered list;
`▲` `▼` move a channel, `✕` removes it. Selecting any channel shows what it is, and any
caveats worth knowing (bioconda is Linux/macOS only, for instance).

- **Save writes your project's `environment.yml`** — only the `channels:` block, leaving your
  dependencies, comments and everything else exactly as they were
- **On a folder with no `environment.yml`**, the label reads **✎ Create environment.yml** and
  asks before creating one, seeded with the channels conda is currently using. It's a
  git-tracked file appearing in your project, so it isn't done behind your back
- **Removing `defaults` writes `nodefaults`**, which is how `environment.yml` says "and don't
  add Anaconda's default channels". That's why there's no separate switch for it — and why a
  teammate whose own `~/.condarc` lists `defaults` won't silently get it back
- **There's no enable/disable toggle.** conda has no concept of a disabled channel, so a
  portable file can't express one. Removing a channel and re-adding it from Available is the
  same gesture — and **↺ Restore** puts the last removed channel back at the position it came
  from, since dropping it at the bottom of a list where order is the configuration would be a
  silent misconfiguration
- **An empty list can't be saved.** conda treats an absent or empty `channels:` as
  `[defaults]`, which is the opposite of what emptying the list means — Save greys out and the
  reason is shown rather than the click silently doing nothing

### What it warns you about

A strip below the description box updates as you edit — you see a problem while you're making
it, not in a dialog after you click Save.

- **"bioconda needs conda-forge searched before it"** — some channels only resolve correctly
  with another above them. Comes with a **Fix order** button that moves just what has to move,
  leaving the rest of your order alone
- **"conda-forge and defaults are built against different compiler and BLAS stacks"** — the
  classic conda breakage. With flexible priority the solver can take some packages from each,
  which surfaces later as import errors. Prefer one, or switch to strict priority. This warning
  **disappears under strict priority**, because that is the actual fix rather than something to
  nag about
- **"this channel URL contains a credential"** — a tokenized channel has to be written to
  `environment.yml` literally or it won't work, and that file normally goes into git. conda's own
  guidance is to keep tokenized channels in `~/.condarc`. Displayed and logged masked everywhere
  else
- **"publishes no searchable package index"** — some channels (local ones especially) don't ship
  the index file search relies on. Informational only: installing from such a channel works
  normally, you just won't find its packages by searching here

The bar itself shows the worst of these on its second line, with a count of the rest, so you
don't have to open the editor to know something is off.

Once saved, installs run with `-c` flags in your order plus `--override-channels`, so
`conda install` searches exactly what the bar shows and nothing else. Search re-indexes
straight away, fetching only channels it hasn't cached. New conda projects get the same
treatment at creation: `conda create` is scoped to the channels the project's
`environment.yml` declares, so the environment and the file agree from the start.

A project **without** an `environment.yml` is left exactly as it was — conda uses its own
configuration and IDOL adds no flags of its own.

### Where a package came from

Installed packages carry a badge when — and only when — there is something to say:

- **`· pip`** — installed with pip rather than conda
- **`· defaults`** (or any channel name) — came from a channel other than the one searched
  first

Packages from your primary channel get no badge. A badge on every row would be a badge on
nothing; the useful signal is the odd one out, which is usually what explains surprising
behaviour.

### Searching or installing from one channel

The **▾ All channels** chip beside the `conda | PyPI` toggle narrows both search and install to
a single channel.

- **Search** then looks only in that channel's own index — including packages another channel
  also offers, which the normal merged view hides behind whichever channel ranks higher
- **Install** runs with `-c <channel> --override-channels`, so you get that channel's build and
  no other

It's a temporary lens, not a setting: it doesn't change your project's channel list, isn't
saved, and clears when you switch interpreters or search PyPI.

### ⇢ Preview — what would actually happen

On any package you haven't installed, **⇢ Preview** solves the install *without performing it*
and writes the result to the Output panel:

```
✓ 4 package(s) would be installed:
    numpy         1.26.4       conda-forge
    mkl           2023.1       defaults
    ...
  Note: 1 channel(s) other than conda-forge would be used — defaults.
```

That last note compares against your **first** channel — a package arriving from further down the
list is the interesting case. If you've narrowed the search with the channel chip, it compares
against *that* channel instead, so a scoped preview stays quiet rather than announcing the channel
you just scoped it to.

If it can't be solved, you get conda's own conflict message — which names the packages actually
in conflict, and is the fastest way to find out which channel is causing a problem. Combined
with the channel chip, that's how you answer "is bioconda the reason this won't install?"
without touching your `environment.yml` to run the experiment.

Preview still solves and still downloads channel indexes, so it takes about as long as the
thinking part of an install — it just never changes anything.

## AI Integration

**✦ Ask AI for examples** — sends the selected package to AI Chat with a prompt for beginner-friendly code examples.

## Guide

**? Learn about Package Manager** — paginated guide covering:
- What packages are
- Installing and uninstalling
- Managing dependencies
- Finding the right package on PyPI
