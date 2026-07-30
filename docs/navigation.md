# Navigation & Search

## Command Palette

Open with `Ctrl+Shift+P`. Fuzzy-searches all commands.

- **`@` prefix** — search symbols by name across the current file
- **`!pip` prefix** — install packages without opening the Package Manager; type `!pip requests` to install directly from the palette with package-name autocomplete
- **Designer commands** — Generate Code, Fold All, Unfold All appear when a designer project is open

## File Explorer

- Lazy loading with directory navigation and drag-to-resize sash
- **Right-click menu** — Open File, Open in Designer, Set as Root Directory, Open in Terminal, New File, New Folder, Rename, Delete. (**Add to .gitignore** lives on the Source Control panel's file rows, not here — see [Git Integration](git.md#source-control-panel))
- **The root only moves when you ask it to** — opening a project or **Set as Root Directory**. `File → Open` opens the file in a tab and leaves the tree exactly where it was, and breadcrumb crumbs never move it
- **Set as Root Directory** re-roots the tree only. It does not `cd` a running terminal — a shell you already have open stays where you left it
- **Open in Terminal** is the opposite half: it `cd`s the terminal to the selected folder (a file resolves to its containing folder) and brings the terminal panel up. If no shell is running yet, the new one starts there
- New File / New Folder uses an **inline text field** directly in the tree (no dialog)
- Drag and drop files between folders with unsaved-changes prompt
- **Git status decorations** — files carry an `M` / `A` / `U` / `D` badge and take that status's colour; folders carry a coloured `●` for the highest-priority status anywhere beneath them, so a collapsed folder still tells you there is something inside to deal with. Colours and the folder roll-up rule are shared with the breadcrumb file picker — see [Git status decorations](git.md#status-decorations). The badge letter is kept alongside the colour on purpose: it is the cue that survives a colour-blind reader and any theme where tag foregrounds misbehave

## Outline Panel

AST-based view of the current file showing classes, functions, methods, parameters, instance attributes, local variables, and nested definitions — all in a collapsible tree.

## Find References

Right-click any symbol to open the References panel showing all occurrences across the project. Clicking a result opens the correct file tab (if the reference is in a different file) and positions the caret at the exact column where the symbol appears.

## Find & Replace

`Ctrl+F` opens a VS Code-style inline bar with case-sensitive, whole-word, and regex toggles. When there is no active selection, the search field is pre-populated with the identifier under the caret.

## Navigation History

**‹ ›** buttons in the nav toolbar navigate backward/forward through edit history — same as browser back/forward for your cursor positions.
