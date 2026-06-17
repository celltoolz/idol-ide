# Editor

## Multi-Tab Editor

- Multi-tab editing with drag reorder, hover close button, and right-click tab menu
- Hover any tab to see its full file path as a tooltip
- Canvas-rendered regex-rule syntax highlighting; themes are JSON files in `themes/` — no Pygments dependency
- Line numbers with code folding — click **▼**/**▶** markers to collapse/expand blocks; `# ── Name ───` section-marker comments fold from that header to the next section header at the same indent; IDOL designer markers (`# ── IDOL:BEGIN`, `# ── IDOL:IMPORTS:BEGIN`, etc.) fold their entire BEGIN…END block; **Up/Down arrow keys skip folded blocks**; pressing **Enter** on a folded section header unfolds the section first, then inserts a newline after the header line
- Bracket matching, auto-indent, auto-close pairs, wrap selection in brackets/quotes. When the cursor touches a bracket or quote, its matching partner is highlighted as you move — quotes are matched within the same line by counting quotes to tell openers from closers, and escaped quotes (`\"`) are skipped
- Insert key toggles overwrite mode — block cursor and OVR status bar indicator

## Font

**View → Change Font** opens a font chooser dialog where you can set the editor font family, size, and bold/italic style. The selection persists across restarts.

## Line Move & Duplicate

| Action | Shortcut |
|---|---|
| Move line up / down | Alt+Up / Alt+Down |
| Duplicate line below (cursor follows) | Shift+Alt+Down |
| Duplicate line below (cursor stays on original) | Shift+Alt+Up |

Works on the current line or a selected block.

## Sticky Scroll

Enclosing scope pins to the top of the editor while you scroll — fully syntax-highlighted with correct line numbers.

## Minimap

Live scaled-down view of the full file with hover zoom preview and mouse wheel scrolling. Toggle with the **MAP** button in the nav toolbar. The minimap is fold-aware — folded lines are hidden in the minimap too.

## Breadcrumb Bar

A thin bar between the tab row and the editor showing the full file path and current symbol scope.

- **Path crumbs** — each folder segment is clickable to set it as the Explorer root
- **Symbol crumbs** — updates live as the cursor moves; shows class › method hierarchy in the active color scheme
- **Sibling picker** — click any symbol crumb to see all peer symbols at that scope level and jump to one
- **Locals drill-down** — a `›` appears after the innermost crumb when locals exist; click to open a picker showing all local variables, loop targets, and nested definitions inside that function
- **Syntax-highlighted footer** — hover any local to see its source line rendered with the active theme's token colors
- **Marquee scroll** — when the source preview overflows the footer width it smoothly ping-pongs left and right
- Keyboard navigation (↑↓ Enter Escape) in both pickers; scrollable for large symbol lists

## Split Editor

### Opening and closing

| Action | Result |
|---|---|
| **SPLIT button** (nav bar) or `Ctrl+\` | First open with multiple tabs — moves the active tab to the split. First open with one tab — opens a fresh Untitled in the split. Subsequent clicks toggle visibility without destroying tabs. |
| **Drag a tab** past the midpoint of the main editor | **Moves** the tab to the split pane (removes it from main) |
| **Right-click → Open in Split Editor** | **Copies** the tab — it stays open in both panes |
| **Drag a split tab** left past the split edge | **Moves** the tab back to the main pane; blue drop zone confirms the drop target |
| **Right-click a split tab → Open in Main Editor** | **Copies** to main — stays open in both panes |
| **Split pane × button** | True close — prompts for any unsaved changes, then destroys the pane |
| **Individual tab ×** in split | Closes that tab; if it was the last, the split pane closes |

### Hide / show

The SPLIT button hides and re-shows the split pane **without closing or discarding any tabs**. All open split tabs survive behind the scenes. Click SPLIT again (or `Ctrl+\`) to restore them exactly as you left them.

Entering **Designer mode** also hides the split automatically; returning to Editor mode restores it.

### Session persistence

Split tabs are saved and restored across app restarts — including dirty/unsaved files (stored in `~/.idol/tmp/` just like main-pane tabs). The split state, sash position, and active tab index all survive a restart.

### Scroll lock

The ⇕ button (in the split header) syncs both panes to the same scroll position. The hardware **Scroll Lock key** also toggles it — IDOL reads the key state on startup.

## Syntax Highlighting

- **Canvas-rendered regex-rule engine** — themes are JSON files in `themes/`; no Pygments dependency
- **Multiline string highlighting** — triple-quoted strings (`"""..."""` and `'''...'''`) are highlighted as strings across all lines; typing `"""` or `'''` auto-inserts the matching closing triple-quote (auto-pair)

## Code Editing Helpers

- **Ctrl+/** — toggle comment on the current line or selection; `#` characters are aligned at the **minimum indentation level** of the selected lines (VS Code style), not at column 0
- **Tab / Shift+Tab** — indent or unindent the current line or selected block by the configured tab size (spaces only)
- **Smart Home** — first press jumps to the first non-whitespace character; second press jumps to column 0 (position-based, no state needed)
- **Word occurrence highlights** — when the cursor rests on a word, all other occurrences in the file highlight automatically; updates on arrow-key navigation too
- **Selection collapse** — pressing Left or Right arrow with a selection collapses to the start/end of the selection (VS Code behavior)

## Undo / Redo

The canvas editor has a full undo/redo stack (200-entry limit). Every edit operation — character insert, newline, backspace, forward-delete, cut, paste, comment toggle, line move, line duplicate, indent, and unindent — pushes a snapshot before it runs. Consecutive same-type operations (e.g. several character inserts in a row) coalesce into a single undo step.

`Ctrl+Z` undoes; `Ctrl+Y` redoes. Both are also wired as `<<Undo>>`/`<<Redo>>` virtual events so the **Edit** menu items (and their macOS equivalents) work too. The Edit menu items dim automatically when there is nothing to undo or redo.

## Non-ASCII Paste Detection

When you paste text that contains non-ASCII characters (curly quotes, em-dashes, zero-width spaces, etc.) an amber **Fix Encoding** pill appears in the nav bar.

- Click **Fix Encoding** to replace all detected non-ASCII characters with a space (zero-width characters are stripped entirely)
- Useful when copying from Word, web pages, or PDF — invisible characters that cause `SyntaxError` or `IndentationError` at runtime are caught before they cause problems
- The pill disappears once the file is clean

## CRC Dirty Tracking

The tab's modified dot (`•`) clears automatically when you undo back to the exact saved state — no manual save needed to clean the indicator. CRC32 is computed on each save and compared on every change.

## Clipboard History

Open with **Ctrl+Shift+H** — a floating panel that records every copy and cut from the editor.

- Ring buffer of the **last 50 entries**; deduplication by content (most-recent wins)
- **Search / filter bar** at the top — type to narrow entries by content or source filename
- **Click** any row to paste it into the editor at the current cursor position
- **Right-click** a row to toggle its **📌 pin** — pinned entries survive "Clear All" (🗑 toolbar button)
- **Keyboard navigation** — Up/Down to move selection, Enter or Ctrl+C to paste the highlighted entry
- **Pin-to-top** — 📌 toolbar button keeps the panel floating above all other windows
- The panel is a persistent hidden window; closing it with the × just hides it, history is preserved

> The rows are rendered as Canvas primitives (not widget trees) — hover effects are sub-millisecond
> `itemconfigure` calls with no full redraws.

## Multi-Cursor

**Alt+Click** adds a secondary cursor at the clicked position. Alt+Click an existing secondary cursor removes it. A regular click clears all secondary cursors and returns to single-cursor mode.

- All cursors use the same blinking `|` caret — they all blink in sync with the primary
- Typing, Backspace, Delete, Enter, Tab, and Shift+Tab apply to every cursor simultaneously (edits are processed bottom-to-top so earlier positions are not shifted by earlier edits)
- Secondary text selections render in the active theme's selection color
- The status bar shows a live `N cursors` count while multiple cursors are active
- **Escape** clears all secondary cursors

## Find & Replace

VS Code-style inline bar with case, whole word, and regex toggles. Open with `Ctrl+F`. When there is no active selection, the search field is pre-populated with the identifier under the caret (if one exists).

## Navigation

**Go to Definition** (`F12`, or right-click → Go to Definition) — jumps to the definition of the symbol under the caret using the LSP. When navigating to a handler from the designer (double-click widget or event row) or via Go to Definition, the editor **vertically centers the target line** in the viewport so the destination is not hidden near the top or bottom edge.

## Right-Click Context Menu

The editor's right-click menu is an IDOL-style dark overlay (not a native OS menu). It shows each action with its keyboard shortcut in a two-column layout. Available actions: Cut, Copy, Paste, Select All, Go to Definition, Find & Replace. Go to Definition is disabled if the LSP is not yet connected.

## Active Line Highlight

**View → Highlight Active Line** toggles a subtle background band on the line the cursor is on. **View → Active Line Color** opens a color picker to customize the highlight color. Both settings apply immediately to all open editor tabs.

## Themes

JSON files in the `themes/` directory. Change the active theme via **View → Theme**. Add a new theme by dropping a `.json` file into the `themes/` directory — it appears in the menu on next launch with no code changes needed. Seven themes are bundled: `monokai-bright`, `dark-plus`, `dracula`, `nord`, `github-light`, `solarized-light`, `dainty`.
