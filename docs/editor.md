# Editor

## Multi-Tab Editor

- Multi-tab editing with drag reorder, hover close button, and right-click tab menu
- Hover any tab to see its full file path as a tooltip
- Syntax highlighting via [Pygments](https://pygments.org/) — Dracula, Monokai, Ayu, Material, and more
- Line numbers with code folding — click ⊟/⊞ markers to collapse/expand blocks
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

## Find & Replace

VS Code-style inline bar with case, whole word, and regex toggles. Open with `Ctrl+F`.

## Color Schemes

`.toml` files in the `colorschemes/` directory. Change via `Edit → Color Scheme` or `Ctrl+L` (font/scheme chooser). Add new themes by dropping a `.toml` file in that directory.
