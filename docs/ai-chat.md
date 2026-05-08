# AI Chat

Press **F2** (or **Help → Ask AI**) to toggle a persistent right-side chat panel — stays open alongside your code.

## Requirements

AI Chat requires [Ollama](https://ollama.com) running locally. No API key needed — fully offline.

```
ollama pull qwen2.5-coder
```

Recommended model: `qwen2.5-coder` (~4GB). The panel shows platform-specific install instructions when Ollama isn't running.

## Features

- **Conversational interface** to a local Ollama LLM
- **Streaming responses** appear word-by-word in real time; animated **Thinking...** dots while waiting
- **Draggable sash** to resize the panel; width and visibility are saved across sessions
- **📄 Send File** — attaches your currently open file as context for the next message
- **✂ Selection** — attaches highlighted code from the editor; clears after sending
- **Code blocks** are syntax-highlighted with a **⎘ Copy** button that strips the language hint automatically
- **💾 Save / 📂 Load** — export and reload full conversation history as JSON
- **🗑 Clear** — wipes conversation history from the UI, memory, and disk in one click
- **Conversation auto-saves** on exit and restores the last 20 messages on next launch
- **Live token counter** shows approximate context usage (e.g. `~1,200 / 32,000 tokens`) — turns amber near the limit

## Remote Host

Click **⚙** to toggle a URL field for pointing IDOL at a different Ollama host (e.g. a remote machine on your network). Hit **Apply** to connect and verify instantly.

## Integration with Problems Panel

- **Double-click any problem** in the Problems panel → AI Chat opens and asks for a plain-English explanation, a minimal broken example, and the fixed version
- **✦ Ask AI button** in the Problems tab bar → sends the full file with all problems and asks for explanations and a corrected version
