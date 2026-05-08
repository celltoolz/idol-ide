# Learning Mode

Press **F1** (or **Help → Learning Mode**) to open a dedicated Learning tab in the editor area.

## How It Works

While Learning Mode is active, hover over any IDE element — panels, buttons, the editor, status bar, breadcrumb bar — and the Learning tab populates instantly with:

- **What it is** — plain-English description
- **How it works** — the mechanics behind it
- **Real-world example** — how you'd actually use it

Zero overhead when the tab is closed — hover bindings are no-ops until F1 is active.

## Coverage

Covers 20+ IDE elements: editor, tabs, outline, references, source control, explorer, commit/push/pull/stage/discard, git health, commit history, status bar segments, breadcrumb bar, find & replace, output, terminal, and more.

## AI Explanations

Each hovered element gets an **Ask AI** button that streams a beginner-friendly explanation in real time via [Ollama](https://ollama.com) (no API key, fully offline). The same offline install card as AI Chat appears when Ollama isn't running.

Recommended model: `qwen2.5-coder` — install with `ollama pull qwen2.5-coder`.

## Learning Cursor

While Learning Mode is active, a custom cursor (arrow + question mark) indicates which elements are registered. Uses the system cursor on Windows and macOS; generates an XBM bitmap on Linux.
