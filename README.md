# IDOL
### Integrated Development and Objective Learning

<p align="center">
  <img src="images/gitPIDE.png" width="65%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-blueviolet?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/UI-Tkinter-blue?style=flat-square" alt="Tkinter">
  <img src="https://img.shields.io/badge/LSP-pylsp%20%2B%20ruff-orange?style=flat-square" alt="LSP">
  <img src="https://img.shields.io/badge/Debugger-debugpy-red?style=flat-square" alt="Debugger">
  <img src="https://img.shields.io/badge/AI-Ollama%20powered-8b5cf6?style=flat-square" alt="Ollama AI">
  <img src="https://img.shields.io/badge/Designer-GUI%20Builder-ff6b35?style=flat-square" alt="GUI Designer">
  <img src="https://img.shields.io/badge/Status-Active%20Development-brightgreen?style=flat-square" alt="Active Development">
</p>

IDOL is what IDLE could have been — a full Python IDE with professional-grade tools (LSP, git, terminal, split editor) and a built-in learning platform designed to grow with you. Beginner-friendly without being beginner-limited. Pure Python, no Electron, no dependencies beyond pip.

Runs natively on **Windows**, **macOS**, and **Linux** from a single codebase.

> **What's coming next?** See the [ROADMAP](ROADMAP.md) for in-progress work, the planned backlog, and long-term ideas.

<p align="center">
  <img src="screenshots/editor-main.png" width="100%">
</p>

---

## Quick Start

```
pip install -r requirements.txt
python main.py
```

For LSP (hover, autocomplete, go-to-definition): `pip install python-lsp-server`  
For diagnostics: `pip install ruff`  
For AI features: install [Ollama](https://ollama.com) and run `ollama pull qwen2.5-coder`

→ **[Full setup guide](docs/getting-started.md)**

---

## Features

### GUI Designer

<img src="screenshots/designer-canvas-palette-properties.png" width="100%">
<p align="center">
  <img src="screenshots/designer-calculator-running-history.png" width="50%">
  <img src="screenshots/designer-calculator-running.png" width="30%">
</p>

The only Python IDE with a **VB6-style visual form designer** built in. Drag-and-drop canvas, 14 widget types, live property editing, variable binding, menu builder, and clean class-based code generation — all in a Tkinter project.

→ **[Full designer docs](docs/designer.md)**

### Editor

<img src="screenshots/editor-stickyscroll-tabs-syntax_highlighting-line_numbers_folding-minimap.png" width="100%">

Multi-tab editing with Pygments syntax highlighting, code folding, sticky scroll, minimap, multi-cursor (`Alt+Click`), line move/duplicate, smart pairs, split editor with scroll sync, and VS Code-style find & replace.

→ **[Full editor docs](docs/editor.md)**

### Intelligence (LSP & Diagnostics)

<img src="screenshots/intelligence-multi_error-hover_tooltip-autocomplete-problems_hover.gif" width="100%">

ruff diagnostics on every keystroke (three severity tiers, cascade suppression), Problems panel with hover tooltips and AI double-click, pylsp hover docs, autocomplete, and go-to-definition.

→ **[Full intelligence docs](docs/intelligence.md)**

### Navigation & Search

<img src="screenshots/navigation_search-outline-explorer-references.gif" width="100%">

Command palette (`Ctrl+Shift+P`), AST-based Outline panel, File Explorer with inline new-file/rename, Find References, and breadcrumb bar with locals drill-down and sibling picker.

→ **[Full navigation docs](docs/navigation.md)**

### Git Integration

<img src="screenshots/git_integration-statusbar-badge-gutter_diff-health-history-staging-changes.png" width="100%">

Staging/unstaging, commit, push/pull, gutter diff strips, Git Health panel with one-click fixes, commit history with inline diffs, inline file explanations, and a guided Fix Wizard.

→ **[Full git docs](docs/git.md)**

### Terminal & Output

<img src="screenshots/terminal-powershell-activate_venv-colors-tui.gif" width="100%">

Full VT100 PTY terminal (PowerShell/bash/zsh), venv detection toolbar, Run/Output panel with inline stdin bar, Run Line, Run Selection, and runtime error indicators.

→ **[Full terminal docs](docs/terminal.md)**

### Debugger

<img src="screenshots/debugger-step_controls-breakpoints-locals-current_line.png" width="100%">

debugpy over DAP — breakpoints with VS Code-style gutter, step controls (F5/F10/F11), LOCALS + BREAKPOINTS panel, floating debug panel, two debug targets (Output or Terminal). No per-project install needed.

→ **[Full debugger docs](docs/debugger.md)**

### AI Chat (F2)

<table><tr>
<td valign="top">

Local Ollama LLM — fully offline, no API key. Send File, Send Selection, streaming responses, syntax-highlighted code blocks, token counter, conversation save/load, and remote host support.

→ **[Full AI chat docs](docs/ai-chat.md)**

</td>
<td width="50%"><img src="screenshots/ai_chat-send-selection-tokens-chat_panel.png" width="100%"></td>
</tr></table>

### Package Manager (F3)

<img src="screenshots/package_manager-topics-details-install-uninstall.png" width="100%">

Installed packages grouped by topic, live filter, PyPI search, install/uninstall with live output, and AI examples — all tied to the active interpreter.

→ **[Full package manager docs](docs/package-manager.md)**

### Learning Mode (F1)

<p align="center">
  <img src="screenshots/learning-outline-debug-click_controls.gif" width="60%" align="top">
  <img src="screenshots/learning-guide_window.png" width="35%" align="top">
</p>

Hover any IDE element for a three-section explanation (what it is, how it works, real-world example). AI Ask button streams a beginner-friendly explanation via Ollama. Covers 20+ IDE elements.

→ **[Full learning mode docs](docs/learning-mode.md)**

### Project Wizard & Session

<p align="center">
  <img src="screenshots/project_wizard-details-envirornment-options-summary.gif" width="50%">
</p>

4-step project setup wizard, per-project interpreter selection, venv management, session persistence, `.idol-project` files, zen mode, and status bar with live git branch and diagnostic count.

→ **[Full project docs](docs/project.md)**

---

## Documentation

| | |
|---|---|
| [Getting Started](docs/getting-started.md) | Install, run, first steps |
| [Keyboard Shortcuts](docs/keyboard-shortcuts.md) | Full shortcut reference |
| [GUI Designer](docs/designer.md) | Canvas, properties, code generation |
| [Editor](docs/editor.md) | Editing, cursor, breadcrumb, split |
| [Intelligence](docs/intelligence.md) | Diagnostics, Problems panel, LSP |
| [Navigation](docs/navigation.md) | Palette, explorer, outline |
| [Git Integration](docs/git.md) | Staging, history, health panel |
| [Terminal & Output](docs/terminal.md) | PTY terminal, output, run |
| [Debugger](docs/debugger.md) | Breakpoints, step, locals |
| [AI Chat](docs/ai-chat.md) | Ollama, send file, token counter |
| [Package Manager](docs/package-manager.md) | Install, uninstall, PyPI search |
| [Learning Mode](docs/learning-mode.md) | Hover explanations, AI |
| [Project & Session](docs/project.md) | Wizard, interpreter, persistence |
| [ROADMAP](ROADMAP.md) | Planned features and backlog |
| [CONTRIBUTING](CONTRIBUTING.md) | Architecture and conventions |
