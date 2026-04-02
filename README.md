# Notepad IDE

A lightweight Python IDE built with tkinter.

![Editor Screenshot](screenshots/editor.png)

## Features

- Multi-tab editor with drag reorder, hover close button, and right-click tab menu
- Syntax highlighting via [Pygments](https://pygments.org/) with multiple color schemes (Dracula, Monokai, Ayu, Material, and more)
- Line numbers with code folding (click ⊖/⊕ markers to collapse/expand blocks)
- Sticky scroll — enclosing scope pins to the top while you scroll, fully syntax highlighted
- AST-based Outline panel (classes, functions, parameters, attributes, variables)
- File Explorer with lazy loading, directory navigation, and drag-to-resize sash
- Find References panel — right-click any symbol to see all occurrences
- VS Code-style inline Find & Replace bar (case, whole word, and regex toggles)
- Integrated Run / Output panel with stdout/stderr coloring
- Session persistence — restores open tabs, layout, and explorer root on relaunch
- Save / Open Workspace for named sessions
- Status bar: line/column, lexer name, indent cycle (spaces ↔ tabs)
- Bracket matching, auto-indent, auto-close pairs

## Requirements

```
pip install pygments
```

## Usage

```
python main.py
```

## Keyboard Shortcuts

| Action | Shortcut |
|---|---|
| New tab | Ctrl+T |
| Open file | Ctrl+O |
| Save | Ctrl+S |
| Save As | Ctrl+Shift+S |
| Close tab | Ctrl+W |
| Find & Replace | Ctrl+H |
| Run file | F5 |
| Next tab | Ctrl+Tab |
| Previous tab | Ctrl+Shift+Tab |
