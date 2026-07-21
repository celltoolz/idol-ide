# Package Manager

Press **F3** (or **Help → Package Manager**) to open the package manager panel.

## Installed Packages

All installed packages are shown **grouped by topic** instantly — no network needed, powered by a precomputed 362K-package lookup covering 46% of PyPI.

- **Live filter** — type in the search bar to instantly filter by name or topic (e.g. type "web" to see all networking packages)

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

- **Installed list** comes from `conda list` — it honestly includes conda's non-Python packages (openssl, vc, ca-certificates, …), so a fresh env shows a few dozen entries grouped mostly under "Other"
- **Install** is **conda-first with pip fallback** — `conda install -y` runs first; if conda can't provide the package (not on its channels), the panel automatically retries with pip inside the env and says so in the Output panel
- Packages installed via pip show a **`· pip` badge** in the list
- **Uninstall routes by origin** — pip-installed packages are removed with pip, conda packages with `conda remove`
- If the env's conda executable can't be found (e.g. the base install was removed), the panel falls back to pip inside the env with a notice

No `conda activate` is needed for any of this — operations run with a synthesized activation environment.

## AI Integration

**✦ Ask AI for examples** — sends the selected package to AI Chat with a prompt for beginner-friendly code examples.

## Guide

**? Learn about Package Manager** — paginated guide covering:
- What packages are
- Installing and uninstalling
- Managing dependencies
- Finding the right package on PyPI
