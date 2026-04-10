# Notepad IDE

A full-featured Python IDE built with tkinter, designed to be what IDLE could have been — a powerful development environment with a built-in learning platform.

The goal is to make Python development and education feel native: real editor features (LSP, git, terminal, split view) alongside guided learning tools (project wizards, interactive guides, and eventually an AI-powered learning mode). Built for beginners who want to grow and developers who want a distraction-free environment — all in pure Python.

Runs natively on **Windows**, **macOS**, and **Linux** from a single codebase.

![Editor Screenshot](screenshots/editor.png)
![Editor Screenshot](screenshots/editor-osx.png)

## Features

### Editor
- Multi-tab editor with drag reorder, hover close button, and right-click tab menu
- Syntax highlighting via [Pygments](https://pygments.org/) with multiple color schemes (Dracula, Monokai, Ayu, Material, and more)
- Line numbers with code folding (click ⊟/⊞ markers to collapse/expand blocks)
- Sticky scroll — enclosing scope pins to the top while you scroll, fully syntax highlighted with correct line numbers
- Minimap — live scaled-down view with hover zoom preview and mouse wheel scrolling
- Multi-cursor editing — Alt+Click to place additional cursors; all cursors edit in sync
- Insert key mode — toggles overwrite mode with block cursor and OVR status bar indicator
- Bracket matching, auto-indent, auto-close pairs, wrap selection in brackets/quotes

### Breadcrumb Bar
- Thin bar between the tab row and editor showing the full file path and current symbol scope
- Path crumbs — each folder segment is clickable to set it as the explorer root
- Symbol crumbs — updates live as the cursor moves; shows class › method hierarchy in the active file's color scheme
- **Sibling picker** — click any symbol crumb to see all peer symbols at that scope level and jump to one
- **Locals drill-down** — a `›` appears after the innermost crumb when locals exist; clicking it opens a picker showing all local variables, loop targets, and nested definitions inside that function
- **Syntax-highlighted footer** — hover any local to see its source line rendered with the active theme's token colors
- **Marquee scroll** — when the source preview overflows the footer width it smoothly ping-pongs left and right so the full line is always readable
- Keyboard navigation (↑↓ Enter Escape) in both pickers; scrollable for large symbol lists

### Intelligence (LSP)
- Diagnostics — error and warning squiggles powered by [pylsp](https://github.com/python-lsp/python-lsp-server)
- Hover documentation — rest the mouse over any symbol for inline docs
- Go to Definition — F12 or right-click menu
- Autocomplete — dropdown with kind labels, keyboard navigation (↑↓ to move, Tab/Enter to accept, Escape to dismiss)

### Navigation & Search
- Command palette — Ctrl+Shift+P; fuzzy search all commands, type @ to search symbols by name
- AST-based Outline panel — classes, functions, methods, parameters, instance attributes, local variables, and nested definitions; all shown in a collapsible tree
- File Explorer with lazy loading, directory navigation, and drag-to-resize sash
  - Right-click menu: New File, New Folder, Rename, Delete, Set as Root Directory, Add to .gitignore
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
- **Commit History panel** — scrollable HISTORY section inside Source Control showing the last 50 commits with colored ref/branch badges, author, and relative timestamps
  - Click any commit to expand an inline list of changed files
  - Click a file to open a syntax-highlighted diff tab scoped to that commit
  - Hover a commit row for a popup showing the full hash, author, absolute date, subject, and all refs
  - Filter bar to search commits by message, author, short hash, or branch name
  - "Load 50 more" button for repos with deep history

### Terminal & Output
- Integrated terminal — full PTY shell (PowerShell/bash) with ANSI color support, direct keyboard input
- Run / Output panel with stdout/stderr coloring
- OUTPUT and TERMINAL tabs share the bottom panel

### Project Wizard
- **File → New Project…** launches a guided 4-step project setup wizard
  - Step 1: Project name and location (with live path preview)
  - Step 2: Python interpreter selection (auto-detects all installed versions, with venv/system filters) + virtual environment creation
  - Step 3: Optional git init and starter files (main.py, requirements.txt, .gitignore)
  - Step 4: Summary — review settings before creating
- Animated progress bar during venv creation so the UI stays responsive
- Integrated learning guides — paginated, scrollable guides with plain-English analogies covering:
  - Virtual environments: what they are, why to use them, choosing an interpreter, creating/activating, best practices
  - Git remotes: repositories, remotes, creating a repo on GitHub, connecting and pushing, authentication

### Workspace
- Session persistence — restores open tabs, layout, and explorer root on relaunch
- Save / Open Workspace for named sessions
- Status bar: line/column, cursor count, lexer name, indent cycle (spaces ↔ tabs)
- Zen mode — F11 hides the sidebar, output panel, and status bar for distraction-free editing; toast notification on entry

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
| Zen mode | F11 |
| Change font | Ctrl+L |
| Add cursor | Alt+Click |
| Clear cursors | Escape / Click |
| Toggle overwrite | Insert |
