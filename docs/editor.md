# Editor

## Multi-Tab Editor

- Multi-tab editing with drag reorder, hover close button, and right-click tab menu
- Hover any tab to see its full file path as a tooltip
- Canvas-rendered regex-rule syntax highlighting; themes are JSON files in `themes/` — no Pygments dependency
- Line numbers with code folding — click **▼**/**▶** markers to collapse/expand blocks; `# ── Name ───` section-marker comments fold from that header to the next section header at the same indent; IDOL designer markers (`# ── IDOL:BEGIN`, `# ── IDOL:IMPORTS:BEGIN`, etc.) fold their entire BEGIN…END block; **Up/Down arrow keys skip folded blocks**; pressing **Enter** on a folded section header unfolds the section first, then inserts a newline after the header line
- Bracket matching, auto-indent, auto-close pairs, wrap selection in brackets/quotes. When the cursor touches a bracket or quote, its matching partner is highlighted as you move — quotes are matched within the same line by counting quotes to tell openers from closers, and escaped quotes (`\"`) are skipped
- Insert key toggles overwrite mode — block cursor and OVR status bar indicator

## Font

**Settings → Editor → Font** (Ctrl+, ) sets the editor font family, size and style. **Ctrl+L** opens the same chooser directly. The chooser is IDOL's own — it opens scoped to the font you are currently using, and its preview renders inside a fixed box, so a 72pt sample scrolls rather than stretching the dialog.

The selection is a preference: it follows you across every project rather than being stored per project.

## Colour Picker

Hovering an inline colour swatch — the small square IDOL draws before a hex literal like `"#0d1117"` — opens a colour picker. Drag inside the saturation/value square or the hue strip, or type a hex value directly.

The literal updates live as you drag, and the whole picking session is a single undo step, so Ctrl+Z puts the original colour back in one press. Your quote style and hex case are preserved: `'#ff00aa'` stays lowercase and single-quoted. `#rgb` shorthand expands to six digits.

The picker stays open while the pointer is over either the swatch or the picker itself, with a short grace period so you can move between them. It closes on leave, on scroll, and when you switch tabs.

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

Live scaled-down view of the full file with hover zoom preview and mouse wheel scrolling. Toggle with the **MAP** button in the nav toolbar, or **Settings → Editor → Show minimap**. The minimap is fold-aware — folded lines are hidden in the minimap too.

## Breadcrumb Bar

A thin bar between the tab row and the editor showing the full file path and current symbol scope.

- **Path crumbs** — the folder segments leading to the file, shown dimmed. They are display-only: re-rooting the Explorer is Explorer → **Set as Root Directory**, deliberately not a stray click on a breadcrumb
- **File picker** — click the **filename** crumb to list the folder the file lives in: subfolders first, then files, both alphabetical. The current file is pre-selected and scrolled into view when the list opens. Picking a file opens it in a new tab (in the pane whose breadcrumb you clicked, so a split-pane pick stays in the split). Clicking a folder drills into it; a `‹ ..` row appears once you have drilled below the starting folder
- **Git status in the picker** — each file row carries a right-aligned `M` / `A` / `U` / `D` letter and takes that status's colour; each folder row carries a coloured `●` standing for the highest-priority status anywhere beneath it (see [Git status decorations](git.md#status-decorations)). A deleted file is gone from disk and so can never appear as a row — the red folder dot is how a deletion surfaces here. `.git` is not listed
- **Symbol crumbs** — updates live as the cursor moves; shows class › method hierarchy in the active color scheme
- **Sibling picker** — click any symbol crumb to see all peer symbols at that scope level and jump to one
- **Locals drill-down** — a `›` appears after the innermost crumb when locals exist; click to open a picker showing all local variables, loop targets, and nested definitions inside that function
- **Syntax-highlighted footer** — hover any local to see its source line rendered with the active theme's token colors
- **Marquee scroll** — when the source preview overflows the footer width it smoothly ping-pongs left and right
- Keyboard navigation (↑↓ Enter Escape) in all three pickers; scrollable for large lists

## Split Editor

### Opening and closing

| Action | Result |
|---|---|
| **SPLIT button** (nav bar) or `Ctrl+\` | First open with multiple tabs — moves the active tab to the split. First open with one tab — opens a fresh Untitled in the split. Subsequent clicks toggle visibility without destroying tabs. |
| **Drag a tab** past the midpoint of the main editor | **Moves** the tab to the split pane (removes it from main) |
| **Right-click → Open in Split Editor** | **Copies** the tab — it stays open in both panes. (A panel tab is *moved*; see below.) |
| **Drag a split tab** left past the split edge | **Moves** the tab back to the main pane; blue drop zone confirms the drop target |
| **Right-click a split tab → Open in Main Editor** | **Copies** to main — stays open in both panes |
| **Split pane × button** | True close — prompts for any unsaved changes, then destroys the pane |
| **Individual tab ×** in split | Closes that tab. The pane stays open even when it was the last one. |

The split closes only when **you** close it — the pane's × or the toggle. Closing its last tab, dragging that tab back to the main pane, or switching to the Designer all leave the pane where it is, ready for another tab. An empty split keeps its header, so you can drag one straight back in.

The split belongs to the project: it is saved and restored per project, and closing a project disposes of it so one project's split files never carry into the next.

### Panel tabs in the split

Welcome, Packages, Learning Mode and Settings can live in either pane. There is only ever one of each, so **Open in Split Editor** *moves* one rather than copying it, and dragging works the same as with a file tab. Note that these have no saved buffer — moving one rebuilds its panel, so anything you had typed into the Settings search box or a package filter starts fresh on the other side.

This is also where they open while the **Designer** has the main editor area, since a tab added there would be behind the canvas. See [GUI Designer → Layout](designer.md#layout).

### Caret and current-line highlight

Only the **focused** pane draws a blinking caret. Two carets blinking at once reads as two live insertion points when only one of them can take your typing.

Both panes keep their **current-line highlight** at all times, including when neither has focus (you clicked into the terminal, the explorer, the AI panel). The highlight is a "you were here" marker, so losing it on every focus change means losing your place in the pane you are about to come back to.

### Hide / show

The SPLIT button hides and re-shows the split pane **without closing or discarding any tabs**. All open split tabs survive behind the scenes. Click SPLIT again (or `Ctrl+\`) to restore them exactly as you left them.

Switching to **Designer mode** leaves the split exactly as you had it. The designer occupies the left half, so an open split puts the canvas and your code side by side.

### Session persistence

Split tabs are saved and restored across app restarts — including dirty/unsaved files (stored in `~/.idol/tmp/` just like main-pane tabs). The split state, sash position, and active tab index all survive a restart.

**Split tabs belong to the project they were opened in.** Closing a project closes the split pane along with its tabs, and opening a project restores that project's split — never the previous one's. Unsaved work in a split tab raises the same save prompt as unsaved work in the main pane.

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

History is **saved per project** and restored when you reopen it, so what you copied while working on one project does not turn up while working on another. With no project open you get a separate scratch history of the last 20 entries, also kept between sessions. Both live under `~/.idol/clipboard/` — never inside the project folder, so copied text cannot end up committed.

> The rows are rendered as Canvas primitives (not widget trees) — hover effects are sub-millisecond
> `itemconfigure` calls with no full redraws.

## Multi-Cursor

**Alt+Click** adds a secondary cursor at the clicked position. Alt+Click an existing secondary cursor removes it. A regular click clears all secondary cursors and returns to single-cursor mode.

- All cursors use the same blinking `|` caret — they all blink in sync with the primary
- Typing, Backspace, Delete, Enter, Tab, and Shift+Tab apply to every cursor simultaneously (edits are processed bottom-to-top so earlier positions are not shifted by earlier edits)
- Movement keys (arrows, Home, End, Page Up/Down) move every cursor; holding **Shift** extends each cursor's own selection — including **Shift+Home** (to first non-whitespace, then column 0) and **Shift+End**
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

**Settings → Editor → Highlight active line** toggles a subtle background band on the line the cursor is on, and **Active line colour** overrides the theme's own highlight. Both apply immediately to every open tab. Reset the colour to go back to following whichever theme is active.

## Themes

JSON files in the `themes/` directory. Change the active theme via **View → Theme**. Add a new theme by dropping a `.json` file into the `themes/` directory — it appears in the menu on next launch with no code changes needed. Seven themes are bundled: `monokai-bright`, `dark-plus`, `dracula`, `nord`, `github-light`, `solarized-light`, `dainty`.
