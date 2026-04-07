# Notepad IDE

A lightweight Python IDE built with tkinter.

![Editor Screenshot](screenshots/editor.png)

## Features

### Editor
- Multi-tab editor with drag reorder, hover close button, and right-click tab menu
- Syntax highlighting via [Pygments](https://pygments.org/) with multiple color schemes (Dracula, Monokai, Ayu, Material, and more)
- Line numbers with code folding (click ⊟/⊞ markers to collapse/expand blocks)
- Sticky scroll — enclosing scope pins to the top while you scroll, fully syntax highlighted
- Minimap — live scaled-down view with hover zoom preview and mouse wheel scrolling
- Multi-cursor editing — Alt+Click to place additional cursors; all cursors edit in sync
- Insert key mode — toggles overwrite mode with block cursor and OVR status bar indicator
- Bracket matching, auto-indent, auto-close pairs, wrap selection in brackets/quotes

### Intelligence (LSP)
- Diagnostics — error and warning squiggles powered by [pylsp](https://github.com/python-lsp/python-lsp-server)
- Hover documentation — rest the mouse over any symbol for inline docs
- Go to Definition — F12 or right-click menu
- Autocomplete — dropdown with kind labels, keyboard navigation (↑↓ to move, Tab/Enter to accept, Escape to dismiss)

### Navigation & Search
- Command palette — Ctrl+Shift+P; fuzzy search all commands, type @ to search symbols by name
- AST-based Outline panel (classes, functions, parameters, attributes, variables)
- File Explorer with lazy loading, directory navigation, and drag-to-resize sash
  - Right-click menu: New File, New Folder, Rename, Delete, Set as Root Directory
  - Drag and drop files between folders with unsaved-changes prompt
- Find References panel — right-click any symbol to see all occurrences
- VS Code-style inline Find & Replace bar (case, whole word, and regex toggles)

### Split Editor
- Side-by-side editing — drag a tab past the midpoint or use Ctrl+\\ / right-click menu
- Scroll lock — ⇕ button syncs both panes to the same scroll position
- Unsaved changes check when closing the split pane

### Git Integration
- Branch name in status bar with live 30s polling
- M/A/U/D badges on tabs and file explorer entries
- Gutter diff strips showing added/modified/deleted lines
- Source Control panel — staged/unstaged file lists, stage/unstage/discard, commit, push/pull
- Diff view with color-coded +/- lines
- Smart warning detection — automatically identifies venv files, secrets, build artifacts, and OS metadata in untracked files
- Git Health panel — scannable checklist (`.gitignore` exists, no venv tracked, no secrets staged) with one-click fixes
- Inline file explanations — hover any file in the Source Control list for a tooltip explaining what it is and why git cares
- Guided Fix Wizard — step-by-step: what happened → why it matters → how to fix it, with an action button

### Terminal & Output
- Integrated terminal — full PTY shell (PowerShell/bash) with ANSI color support, direct keyboard input
- Run / Output panel with stdout/stderr coloring
- OUTPUT and TERMINAL tabs share the bottom panel

### Project Wizard
- **File → New Project…** launches a guided 4-step project setup wizard
  - Step 1: Project name and location (with live path preview)
  - Step 2: Python interpreter selection (auto-detects all installed versions) + virtual environment creation
  - Step 3: Optional git init and starter files (main.py, requirements.txt, .gitignore)
  - Step 4: Summary — review settings before creating
- Animated progress bar during venv creation so the UI stays responsive
- Integrated learning guide — "? Learn about virtual environments" opens a 5-page interactive guide covering: what a venv is, why to use one, choosing an interpreter, creating and activating, and best practices

### Workspace
- Session persistence — restores open tabs, layout, and explorer root on relaunch
- Save / Open Workspace for named sessions
- Status bar: line/column, cursor count, lexer name, indent cycle (spaces ↔ tabs)

## Requirements

```
pip install -r requirements.txt
```

For LSP features (diagnostics, hover, go-to-definition, autocomplete):
```
pip install python-lsp-server pyflakes
```

## Usage

```
python main.py
```

## Keyboard Shortcuts

| Action | Shortcut |
|---|---|
| New tab | Ctrl+N |
| Open file | Ctrl+O |
| Save | Ctrl+S |
| Save As | Ctrl+Shift+S |
| Close tab | Ctrl+W |
| Find & Replace | Ctrl+F |
| Command palette | Ctrl+Shift+P |
| Run file | F5 |
| Go to Definition | F12 |
| Split editor | Ctrl+\\ |
| Source control | Ctrl+Shift+G |
| New terminal | Ctrl+` |
| Change font | Ctrl+L |
| Add cursor | Alt+Click |
| Clear cursors | Escape / Click |
| Toggle overwrite | Insert |
