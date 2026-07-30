# Learning Mode

Press **F1** (or **Help → Learning Mode**) to open a dedicated Learning tab in the editor area.

It opens as a tab in whichever editor pane is on screen — while the [GUI Designer](designer.md) has the main area, that means the split pane, so the panel sits beside your form instead of behind it. Drag the tab between panes at any time.

## How It Works

While Learning Mode is active, **click** any IDE element — panels, buttons, the editor, status bar, breadcrumb bar — and the Learning tab populates with:

- **What it is** — plain-English description
- **How it works** — the mechanics behind it
- **Real-world example** — how you'd actually use it

The click is intercepted, so it explains the thing instead of activating it: you can click Commit, or the run button, or a tab's ×, and read about it without anything happening. Click the same element again and nothing is lost — press **F1** (or the Learning nav button) to leave and get your normal clicks back.

Zero overhead when the tab is closed — the interception is installed on F1 and removed when you leave.

## Coverage

Covers 20+ IDE elements: editor, tabs, outline, references, source control, explorer, commit/push/pull/stage/discard, git health, commit history, status bar segments, breadcrumb bar, find & replace, output, terminal, and more.

## AI Explanations

Each explained element gets an **Ask AI** button that streams a beginner-friendly explanation in real time via [Ollama](https://ollama.com) (no API key, fully offline). The same offline install card as AI Chat appears when Ollama isn't running.

Recommended model: `qwen2.5-coder` — install with `ollama pull qwen2.5-coder`.

## Learning Cursor

While Learning Mode is active, a custom cursor (arrow + question mark) indicates which elements are registered — i.e. which ones have an explanation waiting behind a click. Uses the system cursor on Windows and macOS; generates an XBM bitmap on Linux.
