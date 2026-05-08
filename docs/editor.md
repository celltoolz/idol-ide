# Editor

## Multi-Tab Editor

- Multi-tab editing with drag reorder, hover close button, and right-click tab menu
- Hover any tab to see its full file path as a tooltip
- Syntax highlighting via [Pygments](https://pygments.org/) — Dracula, Monokai, Ayu, Material, and more
- Line numbers with code folding — click ⊟/⊞ markers to collapse/expand blocks; `# ── Name ───` section-marker comments are also foldable regions
- Bracket matching, auto-indent, auto-close pairs, wrap selection in brackets/quotes
- Insert key toggles overwrite mode — block cursor and OVR status bar indicator

## Multi-Cursor Editing

- **Alt+Click** to add a cursor; Alt+Click an existing cursor to remove it
- All cursors type, delete, and navigate in sync
- **Shift+Arrow** extends an independent selection at each cursor
- **Ctrl+C** copies all selections at once
- Smart pairs (brackets, quotes) auto-close and skip-over correctly at every cursor
- Click placement aligned to nearest character boundary

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

Live scaled-down view of the full file with hover zoom preview and mouse wheel scrolling. Toggle with the **MAP** button in the nav toolbar.

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

- **Side-by-side editing** — drag a tab past the midpoint or use `Ctrl+\` / right-click menu
- **Scroll lock** — ⇕ button syncs both panes to the same scroll position; Scroll Lock key toggles it
- Unsaved-changes check when closing the split pane

## Code Editing Helpers

- **Ctrl+/** — toggle comment on the current line or selection (adds/removes `#`)
- **Smart Home** — first press jumps to the first non-whitespace character; second press jumps to column 0 (position-based, no state needed)
- **Word occurrence highlights** — when the cursor rests on a word, all other occurrences in the file highlight automatically; updates on arrow-key navigation too
- **Selection collapse** — pressing Left or Right arrow with a selection collapses to the start/end of the selection (VS Code behavior)

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
> `itemconfigure` calls with no full redraws. This is the pilot for the canvas-renderer pattern
> that will eventually back the Outline, References, Source Control, and Explorer panels.

## Find & Replace

VS Code-style inline bar with case, whole word, and regex toggles. Open with `Ctrl+F`.

## Color Schemes

`.toml` files in the `colorschemes/` directory. Change via `Edit → Color Scheme` or `Ctrl+L` (font/scheme chooser). Add new themes by dropping a `.toml` file in that directory.
