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
4. Adds the crash to the PROBLEMS panel and flashes the tab

The line highlight and gutter triangle clear on the next keystroke. The PROBLEMS
entry is more persistent — it stays until you run again, open a different
project, or install the package that was missing.

**The crash is listed above any lint warnings**, with the exception's own message
(`ModuleNotFoundError: No module named 'PIL'`), because something you just
watched fail matters more than an unused import. It sits alongside the linter's
findings rather than replacing them, and a lint pass triggered by your next
keystroke won't sweep it away.

This is the only way a crash reaches PROBLEMS. Linting is static — it reads your
code without running it — so a failure that only happens at runtime is invisible
to it. Before this, the tab flashed for a crash and the panel it pointed at held
whatever the linter had last found, which for a missing import was nothing.

## Diagnostic Statusbar Badge

Live ✕N ⚠N count on the left of the status bar. Click it to open the Problems panel instantly.

## LSP Features (pylsp)

Backed by `python-lsp-server`, which ships with `requirements.txt`.

**Completions and hovers follow the active interpreter.** The server itself always runs
from IDOL's own environment (no per-project install needed — like the bundled debugger),
but its jedi backend is pointed at the interpreter shown in the status bar
(`pylsp.plugins.jedi.environment`), so imports resolve against the packages of the
selected venv or conda env. Switching interpreters re-points the live server instantly —
no restart. (The ruff diagnostics track doesn't resolve imports, so it needs no
interpreter awareness.)

- **Hover documentation** — rest the mouse over any symbol for inline docs
- **Go to Definition** — `F12` or right-click menu. IDOL first scans the current buffer for a matching `def` or `class` statement (instant, no LSP round-trip); if that fails and the LSP is ready, it falls through to a full LSP request. The right-click menu item is disabled until the LSP is connected. Both `Location` and `LocationLink` response formats are accepted (forward-compatible with any LSP server)
- **Autocomplete** — dropdown of completion candidates (the LSP item labels); ↑↓ to navigate, Tab/Enter to accept, Escape to dismiss. The popup is themed from the active color scheme (background, text, and selection colors follow the current theme)
