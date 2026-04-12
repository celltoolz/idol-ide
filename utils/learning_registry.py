"""Learning Mode registry — content payloads and widget registration manager."""
from __future__ import annotations

from typing import Callable


# ── Content ───────────────────────────────────────────────────────────────────
# Each entry: title, what, how, example

REGISTRY: dict[str, dict[str, str]] = {

    # ── Editor ────────────────────────────────────────────────────────────────
    "editor": {
        "title": "Code Editor",
        "what": "The main editing area where you write Python code. It's the heart of IDOL.",
        "how": (
            "The editor provides syntax highlighting (colors for keywords, strings, functions), "
            "line numbers, auto-indentation, bracket matching, and auto-close pairs. "
            "It supports multiple cursors, code folding, undo/redo, and a minimap on the right side."
        ),
        "example": (
            "Try typing 'def greet(name):' and pressing Enter — the editor automatically "
            "indents the next line for you. Type 'print(' and notice the closing ) appears automatically."
        ),
    },

    # ── Tabs ──────────────────────────────────────────────────────────────────
    "notebook_tab": {
        "title": "Editor Tabs",
        "what": "Each tab holds one open file. You can have many files open at once.",
        "how": (
            "Ctrl+N opens a new tab, Ctrl+W closes the current one, Ctrl+O opens a file. "
            "Tabs show a dot (●) when there are unsaved changes. "
            "Right-click a tab for more options. Drag tabs to reorder them. "
            "Drag a tab past the midpoint of the editor to open a split view."
        ),
        "example": (
            "Open app.py and main.py at the same time — each gets its own tab. "
            "Edit app.py and notice the ● dot appears in the tab title until you save with Ctrl+S."
        ),
    },

    # ── Sidebar sections ──────────────────────────────────────────────────────
    "outline_panel": {
        "title": "Outline Panel",
        "what": "A live tree showing the structure of your current file — classes, functions, and variables.",
        "how": (
            "IDOL parses your code using Python's AST (Abstract Syntax Tree) every time you pause typing. "
            "It shows classes, methods, functions, parameters, instance attributes (self.x), "
            "local variables, and nested definitions. Click any item to jump to it."
        ),
        "example": (
            "If you define 'class Dog:' with a method 'def bark(self):' inside it, "
            "the Outline will show Dog as a parent node with bark() nested underneath. "
            "Click bark() to jump your cursor directly to that line."
        ),
    },

    "references_panel": {
        "title": "References Panel",
        "what": "Shows every place a symbol (variable, function, class) is used in the current file.",
        "how": (
            "Right-click any word in the editor and choose 'Find References'. "
            "The panel lists every line where that name appears, with the line number and a preview. "
            "Click any result to jump to that location."
        ),
        "example": (
            "Right-click the variable 'count' in your code → Find References. "
            "You'll see every assignment, read, and function call that uses 'count' listed here."
        ),
    },

    "source_control_panel": {
        "title": "Source Control Panel",
        "what": "Git integration — track changes, stage files, commit, push, and pull without leaving the IDE.",
        "how": (
            "CHANGES shows files you've modified but not yet staged. "
            "STAGED CHANGES shows files ready to be committed. "
            "Click a file to see a diff. Right-click for stage/unstage/discard options. "
            "Type a commit message and click Commit, then Push to send to GitHub."
        ),
        "example": (
            "Edit a file → it appears under CHANGES with an M badge. "
            "Click the + to stage it → it moves to STAGED CHANGES. "
            "Type 'Fix typo in greeting' in the message box → click Commit → Push."
        ),
    },

    "explorer_panel": {
        "title": "File Explorer",
        "what": "A tree view of your project folder — browse, open, rename, and organize files.",
        "how": (
            "Click any file to open it in a new tab. "
            "Right-click for options: New File, New Folder, Rename, Delete, Set as Root Directory, Add to .gitignore. "
            "Drag files between folders to move them. "
            "Click a folder path in the breadcrumb bar to set it as the explorer root."
        ),
        "example": (
            "Right-click the explorer panel → New File → type 'utils.py' → it opens ready to edit. "
            "Drag it into a subfolder to reorganize your project."
        ),
    },

    # ── Source Control actions ─────────────────────────────────────────────────
    "sc_commit_btn": {
        "title": "Commit Button",
        "what": "Saves a snapshot of your staged changes to your local git history.",
        "how": (
            "A commit is like a save point in a video game — it records exactly what your code "
            "looked like at this moment. Type a short message describing what you changed, "
            "then click Commit. The commit is saved locally until you Push."
        ),
        "example": (
            "Stage your changes, type 'Add user login feature' in the message box, click Commit. "
            "That snapshot is now permanently in your git history — you can always go back to it."
        ),
    },

    "sc_push_btn": {
        "title": "Push Button",
        "what": "Uploads your local commits to the remote repository (e.g. GitHub).",
        "how": (
            "Push sends all commits you've made locally to the remote server. "
            "This is how your teammates see your changes, and how your code gets backed up online. "
            "Click once to arm (button turns amber), click again to confirm and push."
        ),
        "example": (
            "After committing your work, click Push → the button turns amber showing 'Confirm?' "
            "→ click again to send. Your commits are now on GitHub."
        ),
    },

    "sc_pull_btn": {
        "title": "Pull Button",
        "what": "Downloads the latest commits from the remote repository to your local machine.",
        "how": (
            "Pull fetches changes your teammates pushed (or changes you made on another machine) "
            "and merges them into your current branch. "
            "Click once to arm (button turns amber), click again to confirm and pull."
        ),
        "example": (
            "Your teammate fixed a bug and pushed it. Click Pull → Confirm → "
            "their fix is now in your local code."
        ),
    },

    "sc_stage_btn": {
        "title": "Stage / Unstage",
        "what": "Staging marks a file as 'ready to be included in the next commit'.",
        "how": (
            "Think of staging like packing a box before shipping — you choose exactly what goes in. "
            "Right-click a file in CHANGES → Stage, or click the + icon. "
            "Staged files move to STAGED CHANGES. Unstage to take them back out."
        ),
        "example": (
            "You edited 3 files but only want to commit 2 of them. "
            "Stage just those 2 — the third stays in CHANGES and won't be included in the commit."
        ),
    },

    "sc_discard_btn": {
        "title": "Discard Changes",
        "what": "Throws away all edits to a file and restores it to the last committed version.",
        "how": (
            "Right-click a file in CHANGES → Discard. This runs 'git restore' on that file. "
            "Warning: this permanently removes your unsaved edits to that file — "
            "there is no undo for a discard."
        ),
        "example": (
            "You were experimenting and the file is a mess. Right-click → Discard → "
            "the file snaps back to exactly how it was after your last commit."
        ),
    },

    "git_health_panel": {
        "title": "Git Health Panel",
        "what": "A checklist that scans your repo for common git mistakes before they become problems.",
        "how": (
            "IDOL automatically checks for: missing .gitignore, virtual environment files "
            "that shouldn't be committed, potential secrets (API keys, .env files), "
            "and build artifacts. Each issue shows a one-click fix button."
        ),
        "example": (
            "You accidentally have your .venv folder showing as untracked. "
            "Git Health flags it as high severity → click 'Add to .gitignore' → "
            "IDOL adds .venv/ to your .gitignore automatically."
        ),
    },

    "commit_history": {
        "title": "Commit History",
        "what": "A scrollable log of every commit in the repository, newest first.",
        "how": (
            "Each row shows the commit message, author, and how long ago it was made. "
            "Branch and tag badges are color-coded. Click any commit to expand the list of changed files. "
            "Click a file to open a syntax-highlighted diff showing exactly what changed. "
            "Use the filter bar to search by message, author, or branch name."
        ),
        "example": (
            "You want to see what changed last Tuesday. Scroll to that date in HISTORY, "
            "click the commit → click a file → a diff tab opens showing + added lines in green "
            "and - removed lines in red."
        ),
    },

    # ── Status bar ────────────────────────────────────────────────────────────
    "statusbar_position": {
        "title": "Cursor Position",
        "what": "Shows the current line number and column of your text cursor.",
        "how": (
            "Ln = line number (1-based from the top of the file). "
            "Col = column (1-based from the left of the line). "
            "Useful for navigating to a specific line mentioned in an error message."
        ),
        "example": (
            "Python says 'SyntaxError on line 42'. Look at the status bar — "
            "navigate until it reads 'Ln 42' and you're exactly on the error."
        ),
    },

    "statusbar_branch": {
        "title": "Git Branch",
        "what": "Shows which git branch you are currently working on.",
        "how": (
            "A branch is an independent line of development. The main branch is usually called 'main' or 'master'. "
            "Feature branches let you build something new without affecting the stable code. "
            "The ⎇ symbol is the standard branch indicator."
        ),
        "example": (
            "Status bar shows '⎇ master' — you're on the main branch. "
            "If it showed '⎇ feature/login', you'd be on a separate branch for login work."
        ),
    },

    "statusbar_lexer": {
        "title": "Language / Syntax Mode",
        "what": "Shows which programming language the editor is using for syntax highlighting.",
        "how": (
            "IDOL detects the language automatically from the file extension (.py → Python, .js → JavaScript, etc.). "
            "The lexer controls what colors get applied to keywords, strings, comments, and functions."
        ),
        "example": (
            "Open a .py file → status bar shows 'Python'. "
            "Open a .json file → shows 'JSON' with different highlight colors."
        ),
    },

    "statusbar_indent": {
        "title": "Indentation Setting",
        "what": "Shows and controls how many spaces are inserted when you press Tab.",
        "how": (
            "Click to cycle through indent sizes: 2, 4, 8 spaces, or a real Tab character. "
            "Python convention is 4 spaces. "
            "This setting is per-editor-session and affects new indentation as you type."
        ),
        "example": (
            "Click 'Spaces: 4' → cycles to 'Spaces: 2' → useful when editing JavaScript "
            "or projects with a 2-space convention."
        ),
    },

    # ── Breadcrumb bar ─────────────────────────────────────────────────────────
    "breadcrumb_bar": {
        "title": "Breadcrumb Bar",
        "what": "Shows your current location — the file path and the code scope your cursor is inside.",
        "how": (
            "The left side shows folder path segments — click any to set that folder as the explorer root. "
            "The right side shows your current code scope (e.g. MyClass › my_method). "
            "Click a scope crumb to see all sibling symbols at that level. "
            "A › appears when locals are available — click it to see all local variables in scope."
        ),
        "example": (
            "Your cursor is inside Dog.bark(). The breadcrumb shows 'src / models / Dog › bark'. "
            "Click 'Dog' to see all methods in the class. Click › to see local variables inside bark()."
        ),
    },

    # ── Find & Replace ─────────────────────────────────────────────────────────
    "find_replace_bar": {
        "title": "Find & Replace Bar",
        "what": "Search for text in the current file and optionally replace it.",
        "how": (
            "Open with Ctrl+F. Type in the search box — matches highlight instantly. "
            "Toggle buttons: Aa (case sensitive), \\b (whole word), .* (regex mode). "
            "Press Enter or click arrows to jump between matches. "
            "Type in the Replace box and click Replace or Replace All."
        ),
        "example": (
            "Press Ctrl+F, type 'username' → all occurrences highlight in the editor. "
            "Type 'user_name' in Replace, click Replace All → every instance updates at once."
        ),
    },

    # ── Output / Terminal ─────────────────────────────────────────────────────
    "output_panel": {
        "title": "Output Panel",
        "what": "Shows the result of running your Python file — print statements, errors, and program output.",
        "how": (
            "Press F5 to run the current file. Output appears here in real time. "
            "Errors print in red, normal output in white, info messages in blue. "
            "Click Stop to kill a running program. Right-click any line in the editor to run just that line."
        ),
        "example": (
            "Write 'print(\"Hello World\")' and press F5. "
            "The output panel shows '$ python yourfile.py' then 'Hello World' beneath it."
        ),
    },

    "terminal_panel": {
        "title": "Integrated Terminal",
        "what": "A full shell (PowerShell on Windows, bash/zsh on macOS/Linux) running inside the IDE.",
        "how": (
            "Open with Ctrl+` (backtick). Type any shell command — cd, pip install, git, etc. "
            "Supports ANSI colors, arrow-key history, and direct keyboard input just like a real terminal. "
            "Useful for installing packages, running git commands, or any task needing a shell."
        ),
        "example": (
            "Ctrl+` → type 'pip install requests' → the package installs right inside the IDE. "
            "No need to switch to a separate terminal window."
        ),
    },

    # ── Command Palette ────────────────────────────────────────────────────────
    "command_palette": {
        "title": "Command Palette",
        "what": "A fuzzy-search launcher for every command in IDOL — the fastest way to do anything.",
        "how": (
            "Open with Ctrl+Shift+P. Start typing to filter all available commands. "
            "Type @ to switch to symbol search — find any class or function in the current file by name. "
            "Use arrow keys to navigate, Enter to execute, Escape to dismiss."
        ),
        "example": (
            "Press Ctrl+Shift+P, type 'zen' → 'Toggle Zen Mode' appears → press Enter. "
            "Or type '@greet' to jump directly to the greet() function in the current file."
        ),
    },

    # ── Split editor ──────────────────────────────────────────────────────────
    "split_editor": {
        "title": "Split Editor",
        "what": "View and edit two files (or two parts of one file) side by side.",
        "how": (
            "Drag a tab past the midpoint of the editor, or press Ctrl+\\. "
            "The ⇕ button toggles Scroll Lock — when on, both panes scroll together in sync. "
            "The ✕ button closes the right pane. Drag the sash between panes to resize."
        ),
        "example": (
            "Open app.py on the left and utils.py on the right. "
            "Toggle Scroll Lock to compare functions at the same position in both files."
        ),
    },
}


# ── Manager ───────────────────────────────────────────────────────────────────

class LearningManager:
    """Singleton that connects widget hover events to the Learning panel.

    Usage:
        # At app startup:
        LearningManager.set_handler(my_show_fn)

        # When building any widget:
        LearningManager.register(some_widget, "outline_panel")
    """

    _handler: Callable[[str], None] | None = None
    _registrations: list = []   # list of (widget, lid, overlay)

    @classmethod
    def set_handler(cls, fn: Callable[[str], None]) -> None:
        cls._handler = fn

    @classmethod
    def register(cls, widget, lid: str, overlay: bool = True) -> None:
        """Bind <Enter> on *widget* to fire the handler.

        overlay=True  → widget also gets a visual selection box in Learning Mode
        overlay=False → hover still works, but no overlay box (used for large panels)
        """
        if lid not in REGISTRY:
            return

        cls._registrations.append((widget, lid, overlay))

        def _fire(event=None):
            if cls._handler:
                cls._handler(lid)

        widget.bind("<Enter>", _fire, add="+")

    @classmethod
    def overlay_registrations(cls) -> list:
        """Return [(widget, lid)] for widgets that should get visual overlay boxes."""
        return [(w, l) for w, l, o in cls._registrations if o]
