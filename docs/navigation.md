# Navigation & Search

## Command Palette

Open with `Ctrl+Shift+P`. Fuzzy-searches all commands.

- **`@` prefix** — search symbols by name across the current file
- **`!pip` prefix** — install packages without opening the Package Manager; type `!pip requests` to install directly from the palette with package-name autocomplete
- **Designer commands** — Generate Code, Fold All, Unfold All appear when a designer project is open

## File Explorer

- Lazy loading with directory navigation and drag-to-resize sash
- **Right-click menu** — New File, New Folder, Rename, Delete, Set as Root Directory, Add to .gitignore
- New File / New Folder uses an **inline text field** directly in the tree (no dialog)
- Drag and drop files between folders with unsaved-changes prompt
- M/A/U/D badges on files showing git status

## Outline Panel

AST-based view of the current file showing classes, functions, methods, parameters, instance attributes, local variables, and nested definitions — all in a collapsible tree.

## Find References

Right-click any symbol to open the References panel showing all occurrences across the project. Clicking a result opens the correct file tab (if the reference is in a different file) and positions the caret at the exact column where the symbol appears.

## Find & Replace

`Ctrl+F` opens a VS Code-style inline bar with case-sensitive, whole-word, and regex toggles. When there is no active selection, the search field is pre-populated with the identifier under the caret.

## Navigation History

**‹ ›** buttons in the nav toolbar navigate backward/forward through edit history — same as browser back/forward for your cursor positions.
