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

- **Search follows the interpreter** — a `conda | PyPI` source toggle appears next to the search button, defaulting to **conda**: results come from your *configured channels* (read from `~/.condarc`; plain Miniconda means `defaults`), so what you find is exactly what `conda install` can reach. Each channel's package index (`channeldata.json`) is cached locally in `~/.idol/conda_index/` and refreshed weekly, so search is instant and offline-friendly
- **Names differ between conda and PyPI** — conda's `graphviz` is the Graphviz C tool while PyPI's `graphviz` is the Python bindings (`python-graphviz` on conda). Searching the namespace you'll install from shows both with their summaries, so you pick the right one
- **Install routes by search source** — a conda result installs with `conda install` only (no silent pip fallback: swapping tools swaps *products* when names collide); a package picked with the **PyPI** toggle installs with pip inside the env, after a one-line warning that pip-in-conda can conflict with conda's dependency resolver
- **Installed list** comes from `conda list` — it honestly includes conda's non-Python packages (openssl, vc, ca-certificates, …), so a fresh env shows a few dozen entries grouped mostly under "Other"
- Packages installed via pip show a **`· pip` badge** in the list
- **Uninstall routes by origin** — pip-installed packages are removed with pip, conda packages with `conda remove`
- If the env's conda executable can't be found (e.g. the base install was removed), the panel falls back to pip inside the env with a notice
- **Terms of Service** — before the first conda-routed install/uninstall, the panel checks whether the conda installation has accepted its channels' ToS (fresh Miniconda installs haven't) and shows an Accept/Decline dialog if not; Accept runs `conda tos accept` (remembered by conda itself), Decline cancels the operation. Search never needs the ToS — the channel index is fetched over plain HTTPS, not through conda

No `conda activate` is needed for any of this — operations run with a synthesized activation environment.

## AI Integration

**✦ Ask AI for examples** — sends the selected package to AI Chat with a prompt for beginner-friendly code examples.

## Guide

**? Learn about Package Manager** — paginated guide covering:
- What packages are
- Installing and uninstalling
- Managing dependencies
- Finding the right package on PyPI
