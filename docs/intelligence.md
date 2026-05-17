# Intelligence (LSP & Diagnostics)

## Diagnostics

IDOL uses a two-source diagnostic pipeline:

1. **ruff** — runs on every keystroke (debounced), reading from stdin so unsaved buffers work
2. **compile()** fallback — catches syntax errors when ruff isn't available

### Three-Tier Severity

| Indicator | Meaning |
|---|---|
| Red squiggle | Crash-level — syntax errors, undefined names |
| Yellow squiggle | Likely bug |
| Blue squiggle | Style issue, unused import |

**Cascade suppression** — diagnostics within 3 lines of a root syntax error are hidden so one bad line doesn't flood the list.

## Problems Panel

The **PROBLEMS** tab in the bottom panel lists every diagnostic with colored severity dots (✕ error, ⚠ warning, · info).

- Click any entry to jump directly to that line and column
- **Hover tooltips** — rest the mouse over any problem for 600ms to see the rule code, a beginner-friendly plain-English description (covers ~40 common ruff rules), and a hint to double-click for AI help
- **Double-click → Ask AI** — opens the AI Chat panel and asks for a plain-English explanation, a minimal broken example, and the fixed version
- **✦ Ask AI button** — appears in the tab bar whenever there are errors or warnings; sends the full file with all problems to AI Chat

Open the panel: `Ctrl+Shift+M` or click the diagnostic badge in the status bar.

## Flashing Tab

When a script crashes and the Problems panel isn't open, the PROBLEMS tab pulses amber until you click it or start typing.

## Runtime Error Indicators

When a script crashes, IDOL:
1. Jumps to the offending line
2. Applies an amber highlight to that line
3. Draws a right-pointing amber triangle (▶) in the gutter
4. Flashes the PROBLEMS tab

All indicators clear on the next keystroke.

## Diagnostic Statusbar Badge

Live ✕N ⚠N count on the left of the status bar. Click it to open the Problems panel instantly.

## LSP Features (pylsp)

Backed by `python-lsp-server`, which ships with `requirements.txt`.

- **Hover documentation** — rest the mouse over any symbol for inline docs
- **Go to Definition** — `F12` or right-click menu. IDOL first scans the current buffer for a matching `def` or `class` statement (instant, no LSP round-trip); if that fails and the LSP is ready, it falls through to a full LSP request. The right-click menu item is disabled until the LSP is connected. Both `Location` and `LocationLink` response formats are accepted (forward-compatible with any LSP server)
- **Autocomplete** — dropdown with kind labels (function, class, variable, etc.); ↑↓ to navigate, Tab/Enter to accept, Escape to dismiss
