# Getting Started

## Requirements

Python 3.11 or later.

## Install (recommended: in a virtual environment)

A venv keeps IDOL's dependencies isolated from your system Python so nothing else on your machine is affected. If you're new to Python, this is the safe default.

From the IDOL folder:

**Windows (PowerShell)**
```
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` covers everything: PTY, LSP (`python-lsp-server`), diagnostics (`ruff`), debugger (`debugpy`), and the rest.

## Running IDOL

With the venv active:

```
python main.py
```

Optionally open a file directly:

```
python main.py path/to/file.py
```

Next time you open a new terminal, re-activate the venv first (`.\.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` elsewhere) before running `python main.py`.

## Welcome Tab

On first launch (or whenever no editor tabs are open), IDOL shows a **Welcome** tab instead of a blank Untitled file.

- **Start** — quick links to New File, Open File, Open Folder, New Project, and Open Project
- **Explore** — one-click access to Learning Mode, the GUI Designer, and the Package Manager
- **Recent Projects / Recent Files** — last 10 of each, persisted in `~/.idol/recent.json`; click to reopen, × to remove. Opening an entry moves it back to the top, so the list stays ordered by when you last used it
  - An entry whose folder or file is no longer on disk is flagged with a red **⊗** and reads `· not found` under the name. Click it and IDOL tells you where it used to be and offers to drop it from the list — the entry is never removed without asking
- **Unsaved Files** — unsaved work whose tab is no longer open, offered back so it can be recovered
  - IDOL never discards an unsaved buffer. Closing a project (or quitting) writes each dirty tab to a scratch file under `~/.idol/tmp` so reopening brings it back exactly as it was. But if you had an unsaved tab with *no project open* and closed the project, nothing points at that scratch file any more — the work is on disk with no way to reach it. This list is that way
  - Each row is named after the tab it came from, with the file it was destined for (or *never saved to a file*) and how long ago it was written. Click to reopen it as a dirty tab, still targeting its original file — `Ctrl+S` then writes where you always meant it to go. The file on disk is not touched until you do
  - × discards the unsaved contents for good, after a confirmation
  - Buffers that are currently open are not listed: that work is not lost, and offering it would just open a second copy of something already on screen
- **What's New** — live view of `CHANGELOG.md` with ‹ › navigation between milestone sections
- **Tips** — rotating keyboard shortcut hints at the bottom
- **Show on startup** checkbox — uncheck to skip the Welcome tab on next launch (reopen anytime via **Help → Welcome**)

Each of the three right-hand lists shows **five rows** and scrolls within itself, so a full set of recents can't push the rest of the page out of reach. The scrollbar appears only when a list actually overflows, and a wheel scroll aimed at a list moves that list rather than the page.

## First Steps

1. **Open a file** — `Ctrl+O` or `File → Open File`
2. **Create a project** — `File → New Project…` launches the 4-step wizard; it sets up your interpreter, optional venv, and git
3. **Explore features** — press `F1` to open Learning Mode and hover any IDE element for a plain-English explanation

## Creating a GUI Project (Designer)

The visual GUI designer is only active for **Tkinter GUI App** projects:

1. `File → New Project…`
2. Select **Tkinter GUI App** as the project type
3. Complete the wizard — IDOL scaffolds `Form1.py`, `Form1.form.json`, and a `main.py` entry point
4. The canvas opens automatically in Designer mode

See [designer.md](designer.md) for full designer documentation.

## Setting Up Git Features

The Source Control panel (branch indicator, stage/unstage, commit, push/pull, history) requires **Git** to be installed and on your PATH.

1. Install Git from [git-scm.com](https://git-scm.com) (Windows) or via your package manager (`brew install git`, `apt install git`, etc.)
2. Set your identity so commits are attributed correctly:
   ```
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
3. Open a project folder that is already a git repo, or initialise one:
   ```
   git init
   ```
4. IDOL detects the repo automatically — the branch name appears in the status bar and the Source Control tab populates

**GitHub / remote push & pull** — works out of the box if you have SSH keys or a credential helper configured (e.g. `git config --global credential.helper store` on Linux, or Git Credential Manager on Windows/macOS).

## Setting Up AI Features

The AI Chat panel and AI-powered explanations require [Ollama](https://ollama.com) running locally:

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull the recommended model:
   ```
   ollama pull qwen2.5-coder
   ```
3. Press `F2` in IDOL to open the AI Chat panel

No API key required — runs fully offline.
