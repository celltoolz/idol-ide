# Notepad IDE

A lightweight Python IDE built with tkinter.

![Editor Screenshot](screenshots/editor.png)

## Features

### Editor
- Multi-tab editor with drag reorder, hover close button, and right-click tab menu
- Syntax highlighting via [Pygments](https://pygments.org/) with multiple color schemes (Dracula, Monokai, Ayu, Material, and more)
- Line numbers with code folding (click ⊖/⊕ markers to collapse/expand blocks)
- Sticky scroll — enclosing scope pins to the top while you scroll, fully syntax highlighted
- Minimap — live scaled-down view of the file with hover preview
- Multi-cursor editing — Alt+Click to place additional cursors; all cursors edit in sync
- Bracket matching, auto-indent, auto-close pairs, wrap selection in brackets/quotes

### Intelligence (LSP)
- Diagnostics — error and warning squiggles powered by [pylsp](https://github.com/python-lsp/python-lsp-server)
- Hover documentation — rest the mouse over any symbol for inline docs
- Go to Definition — F12 or right-click menu
- Autocomplete — dropdown with kind labels, keyboard navigation (↑↓ to move, Tab/Enter to accept, Escape to dismiss)

### Navigation & Search
- AST-based Outline panel (classes, functions, parameters, attributes, variables)
- File Explorer with lazy loading, directory navigation, and drag-to-resize sash
- Find References panel — right-click any symbol to see all occurrences
- VS Code-style inline Find & Replace bar (case, whole word, and regex toggles)

### Terminal & Output
- Integrated terminal — full PTY shell (PowerShell/bash) with ANSI color support, direct keyboard input
- Run / Output panel with stdout/stderr coloring
- OUTPUT and TERMINAL tabs share the bottom panel

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
pip install python-lsp-server
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
| Run file | F5 |
| Go to Definition | F12 |
| New terminal | Ctrl+` |
| Add cursor | Alt+Click |
| Clear cursors | Escape / Click |
