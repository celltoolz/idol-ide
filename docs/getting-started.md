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

## Setting Up AI Features

The AI Chat panel and AI-powered explanations require [Ollama](https://ollama.com) running locally:

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull the recommended model:
   ```
   ollama pull qwen2.5-coder
   ```
3. Press `F2` in IDOL to open the AI Chat panel

No API key required — runs fully offline.
