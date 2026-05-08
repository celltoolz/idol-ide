"""Learning Mode registry — content payloads keyed by widget ID."""
from __future__ import annotations


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
            'Try it now — type this into the editor:\n\n'
            '    print("Hello, IDOL!")\n\n'
            "Then right-click that line → Run Line → the Output panel shows: Hello, IDOL!\n\n"
            "Also try typing 'def greet(name):' and pressing Enter — the editor automatically "
            "indents the next line. Type 'print(' and notice the closing ) appears automatically."
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

    "run_entry_selector": {
        "title": "Entry File Selector",
        "what": "Pins a specific Python file as the run/debug target regardless of which tab is active.",
        "how": (
            "Click ▶ in the status bar to open the picker. "
            "Choose 'Active Tab' to run whichever file is open (default), "
            "pick a .py file from your project, or click Browse to locate any file. "
            "The pinned file is saved with the project and restored on next open."
        ),
        "example": (
            "Your project has main.py as the entry point but you're editing utils.py. "
            "Pin main.py — now Ctrl+F5 and F5 always launch main.py no matter which tab is focused."
        ),
    },
    "interpreter_selector": {
        "title": "Python Interpreter",
        "what": "Shows the active Python interpreter — the version (and venv, if one is active) used to run and debug your code.",
        "how": (
            "Click to open the interpreter picker. Choose any detected Python installation or virtual environment. "
            "When a .venv is active it shows as '(.venv) Python x.x.x'. "
            "The selection is saved per project so each project remembers its own interpreter."
        ),
        "example": (
            "Your project needs Python 3.11 but the statusbar shows 3.9 — click it, pick 3.11, "
            "and all subsequent runs and debugger sessions use the correct version."
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
            "Use the ▶ button (or Ctrl+F5) to run the current file. Output appears here in real time. "
            "Errors print in red, normal output in white, info messages in blue. "
            "Press Shift+F5 or click ■ to stop a running program. "
            "Right-click any line in the editor to run just that line."
        ),
        "example": (
            "Write 'print(\"Hello World\")' and press Ctrl+F5. "
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

    "problems_panel": {
        "title": "Problems Panel",
        "what": "Lists all syntax errors, warnings, and type issues in your open files, detected by the language server in real time.",
        "how": (
            "Click the PROBLEMS tab to open it. Errors show a ✕ count and warnings a ⚠ count on the tab badge. "
            "Click any entry to jump directly to that line in the editor. "
            "Errors are shown in red, warnings in yellow."
        ),
        "example": (
            "You forget a closing parenthesis — a red ✕1 badge appears on PROBLEMS immediately. "
            "Click the entry to jump straight to the offending line."
        ),
    },
    "debug_panel": {
        "title": "Debug Panel",
        "what": "Shows the active debug session — current breakpoints, variable state, and call stack.",
        "how": (
            "Click the DEBUG tab or press F5 to start a debug session. "
            "Set breakpoints by clicking the gutter (line number area) in the editor. "
            "Use the debug toolbar buttons to Continue, Step Over (F10), and Step Into (F11)."
        ),
        "example": (
            "Set a breakpoint on line 10, press F5 — execution pauses there. "
            "The Debug panel shows all local variables and the call stack at that moment."
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

    # ── Debug toolbar (shown in nav bar during a session or learning mode) ────
    "dbg_continue": {
        "title": "Continue (▶)",
        "what": "Resumes execution after the debugger has paused at a breakpoint.",
        "how": "Click ▶ or press F5. The program runs until it hits the next breakpoint or finishes.",
        "example": "Paused at line 12 inspecting a variable — click ▶ to continue to the next breakpoint.",
    },
    "dbg_step_over": {
        "title": "Step Over (↷)",
        "what": "Executes the current line and moves to the next, without stepping into any function calls.",
        "how": "Click ↷ or press F10. Use this to advance line by line while skipping over the internals of called functions.",
        "example": "Line 15 calls 'process_data()'. Step Over runs that whole function and lands on line 16.",
    },
    "dbg_step_in": {
        "title": "Step Into (↓)",
        "what": "Steps inside the function being called on the current line so you can debug it directly.",
        "how": "Click ↓ or press F11. The debugger jumps into the first line of the called function.",
        "example": "Line 15 calls 'process_data()'. Step Into takes you inside 'process_data' to debug it line by line.",
    },
    "dbg_step_out": {
        "title": "Step Out (↑)",
        "what": "Finishes executing the current function and pauses back at the caller.",
        "how": "Click ↑ when you're inside a function you've stepped into and want to return to the calling code.",
        "example": "You stepped into 'process_data()' and inspected what you needed — click ↑ to return to the caller.",
    },
    "dbg_stop": {
        "title": "Stop Debug (■)",
        "what": "Terminates the active debug session immediately.",
        "how": "Click the red ■ to kill the debugger and return to normal editing. Shift+F5 does the same.",
        "example": "You've found the bug and don't need to keep the session running — click ■ to stop cleanly.",
    },

    # ── Nav toolbar ──────────────────────────────────────────────────────────
    "nav_run": {
        "title": "Run / Debug Button (▶ / ⬡)",
        "what": "Executes the current file in whichever mode was last selected — Run (▶) or Debug (⬡).",
        "how": (
            "Click ▶ to run, or click ▾ next to it to pick a mode from the dropdown. "
            "The button icon and color change to show the active mode: green ▶ for Run, yellow ⬡ for Debug. "
            "Keyboard: Ctrl+F5 to run, F5 to debug."
        ),
        "example": "Click ▾, choose Debug — the button turns yellow ⬡. Now every click or F5 launches the debugger until you switch back.",
    },
    "nav_chevron": {
        "title": "Run Mode Selector (▾)",
        "what": "Opens a dropdown to choose what happens when you click the run button.",
        "how": (
            "Click ▾ to open the menu. Choose Run (Ctrl+F5) to execute normally, "
            "or Debug (F5) to launch with the debugger. "
            "You can also choose Run Line, Run Selection, or switch output to Terminal. "
            "The choice is remembered until you change it."
        ),
        "example": "Click ▾ → select 'Run Selection' to execute only the highlighted code block.",
    },
    "nav_stop": {
        "title": "Stop Button (■)",
        "what": "Terminates whatever is currently running — a script, debug session, or long-running process.",
        "how": "Click ■ or press Shift+F5. The button is dim when nothing is running and turns red when something is active.",
        "example": "Your script is stuck in an infinite loop — click ■ to kill it instantly.",
    },
    "nav_split": {
        "title": "Split Editor (SPLIT)",
        "what": "Opens two editors side by side so you can view and edit two files at once.",
        "how": "Click SPLIT (or press Ctrl+\\) to open a second editor pane. Drag the sash to resize. Click again to close. Drag any tab past the midpoint to open it in the split.",
        "example": "Open app.py on the left and utils.py on the right to cross-reference while coding.",
    },
    "nav_map": {
        "title": "Minimap (MAP)",
        "what": "A scaled-down bird's-eye view of your entire file on the right edge of the editor.",
        "how": "Click MAP to toggle it. Hover over the minimap for a zoom preview of that section. Drag or click to scroll the editor.",
        "example": "Your file is 500 lines. The minimap shows the whole thing at once — click near the bottom to jump there instantly.",
    },
    "nav_sidebar": {
        "title": "Sidebar Toggle (☰)",
        "what": "Hides or shows the entire left sidebar (Outline, Explorer, Source Control).",
        "how": "Click ☰ or press Ctrl+B. Hiding the sidebar gives your editor more horizontal space when you need to focus.",
        "example": "You're on a laptop with a small screen — hide the sidebar to get 220 more pixels of editor width.",
    },
    "nav_zen": {
        "title": "Zen Mode (ZEN)",
        "what": "Distraction-free mode — hides the sidebar, output panel, and status bar.",
        "how": "Click ZEN or press F10. Press F10 again or Escape to exit. A small toast appears when you enter.",
        "example": "You're writing a tricky algorithm and want zero visual noise. Hit ZEN — just you and the code.",
    },
    "nav_ai": {
        "title": "AI Chat (AI)",
        "what": "Toggles the AI Chat panel on the right side of the editor.",
        "how": "Click AI or press F2. The panel slides in alongside your code — drag the sash to resize. Click again to close.",
        "example": "Stuck on an error? Press F2, paste the traceback, ask 'what does this mean?' — without leaving the IDE.",
    },
    "nav_pkg": {
        "title": "Package Manager (📦)",
        "what": "Opens the Package Manager tab — browse, search, install, and uninstall Python packages.",
        "how": "Click 📦 or press F3. Click again to close. All installed packages are shown grouped by topic.",
        "example": "Need the 'requests' library? Open Package Manager, search 'requests', click Install.",
    },
    "nav_learn": {
        "title": "Learning Mode (📖)",
        "what": "Opens Learning Mode — hover over any IDE element to get an explanation of what it does.",
        "how": "Click 📖 or press F1. Blue boxes appear on every element. Hover or click one to learn about it. Click 📖 again to close.",
        "example": "Not sure what the breadcrumb bar does? Open Learning Mode and hover over it — you're reading the result right now!",
    },
    "nav_terminal": {
        "title": "New Terminal (>_)",
        "what": "Opens a new integrated terminal tab in the bottom panel.",
        "how": "Click >_ or press Ctrl+` (backtick). Each click opens a fresh shell. You can have multiple terminal tabs.",
        "example": "Click >_ and type 'pip install flask' to install a package right inside the IDE.",
    },

    # ── Package Manager ───────────────────────────────────────────────────────
    "pkg_search": {
        "title": "Package Search",
        "what": "Search your installed packages or find new ones on PyPI.",
        "how": (
            "Type to instantly filter your installed packages by name or topic. "
            "Press Enter or click PyPI ↗ to search the full Python Package Index for new packages. "
            "Results are ranked by relevance with well-known packages at the top."
        ),
        "example": "Type 'web' to see all networking packages you have installed. Press Enter to search PyPI for web frameworks.",
    },
    "pkg_list": {
        "title": "Installed Packages",
        "what": "All Python packages currently installed in your environment, grouped by topic.",
        "how": (
            "Packages are grouped automatically by category (Web, Data Science, CLI Tools, etc.) "
            "using PyPI classifier data. Click any package to see its details on the right. "
            "The list updates after every install or uninstall."
        ),
        "example": "You see 'Data Science (4)' — click it to expand and find numpy, pandas, matplotlib, and scipy.",
    },
    "pkg_install": {
        "title": "Install Button",
        "what": "Installs the selected package into your Python environment using pip.",
        "how": (
            "Select a package from the list or PyPI search results, then click ⬇ Install. "
            "pip runs in the background and output streams to the Output panel. "
            "The installed list refreshes automatically when done."
        ),
        "example": "Search for 'flask', click it, click Install → pip installs Flask and all its dependencies.",
    },
    "pkg_uninstall": {
        "title": "Uninstall Button",
        "what": "Removes the selected package from your Python environment using pip.",
        "how": (
            "Select an installed package and click ✕ Uninstall. "
            "pip removes it in the background with output in the Output panel. "
            "Use carefully — other packages may depend on what you're removing."
        ),
        "example": "You no longer need 'colorama'. Select it, click Uninstall → pip removes it cleanly.",
    },

    # ── AI Chat ───────────────────────────────────────────────────────────────
    "ai_chat": {
        "title": "AI Chat Input",
        "what": "Type a message here to talk to the AI assistant powered by Ollama running locally on your machine.",
        "how": (
            "Type your question or paste code, then press Enter (or Shift+Enter for a new line). "
            "The AI keeps the full conversation in memory so you can ask follow-up questions. "
            "Use 📄 Send File to attach your open file, or ✂ Selection to attach highlighted code."
        ),
        "example": (
            "Type 'What does a decorator do in Python?' and press Enter. "
            "Then follow up with 'Can you show me a simple example?' — "
            "the AI remembers the context of the whole conversation."
        ),
    },

    # ── AI Chat buttons ───────────────────────────────────────────────────────
    "ai_settings_btn": {
        "title": "AI Settings (⚙)",
        "what": "Configure which Ollama server IDOL connects to for AI responses.",
        "how": (
            "Click ⚙ to reveal the URL field. Change the address if Ollama is running on a "
            "different machine or port. Click Apply to connect and verify instantly. "
            "The default (localhost) works if Ollama is running on your own computer."
        ),
        "example": (
            "Your Ollama is on a home server at 192.168.1.10. "
            "Click ⚙ → type 'http://192.168.1.10:11434' → Apply → IDOL connects remotely."
        ),
    },

    "ai_clear_btn": {
        "title": "Clear Conversation (🗑)",
        "what": "Wipes the entire chat history — messages, memory, and the saved history file.",
        "how": (
            "Click 🗑 Clear to erase everything and start fresh. "
            "The AI has no memory of previous messages after a clear. "
            "Useful when switching topics or when the token counter is nearly full."
        ),
        "example": (
            "You've been debugging one file for a while and want to ask about something new. "
            "Click Clear — the AI starts with a blank slate, no context confusion."
        ),
    },

    "ai_load_btn": {
        "title": "Load Conversation (📂)",
        "what": "Loads a previously saved conversation from a JSON file.",
        "how": (
            "Click 📂 Load and pick a .json file you exported earlier. "
            "The full conversation restores — the AI picks up right where you left off, "
            "with all prior context intact."
        ),
        "example": (
            "You saved a useful debugging session last week. "
            "Load it now to continue from where you stopped, or refer back to the AI's suggestions."
        ),
    },

    "ai_save_btn": {
        "title": "Save Conversation (💾)",
        "what": "Exports the full chat history to a JSON file you can reload later.",
        "how": (
            "Click 💾 Save and choose where to save the file. "
            "The file stores every message in the conversation. "
            "Conversations also auto-save on exit and restore on next launch automatically."
        ),
        "example": (
            "You've had a really useful chat solving a tricky bug. "
            "Save it so you can reload it on any machine or share it with a teammate."
        ),
    },

    "ai_send_file_btn": {
        "title": "Send File (📄)",
        "what": "Attaches the code from your currently open file to your next AI message.",
        "how": (
            "Click 📄 Send File — a label confirms the file is attached. "
            "Then type your question and send. The AI sees your full file contents "
            "and can answer specifically about your code. The attachment clears after sending."
        ),
        "example": (
            "You have app.py open. Click Send File, type 'What does _apply_layout do?' — "
            "the AI reads your actual code and gives you a precise answer."
        ),
    },

    "ai_selection_btn": {
        "title": "Send Selection (✂)",
        "what": "Attaches only the highlighted text from the editor to your next AI message.",
        "how": (
            "Select code in the editor first, then click ✂ Selection. "
            "The snippet is attached — useful when you want to ask about a specific function "
            "without sending the whole file. The attachment clears after sending."
        ),
        "example": (
            "Select a confusing 10-line function, click Selection, "
            "type 'Explain this to me like I'm 5.' — the AI explains just that snippet."
        ),
    },

    "ai_token_label": {
        "title": "Token Counter",
        "what": "Shows how much of the AI's memory (context window) the conversation is using.",
        "how": (
            "Each token is roughly 3–4 characters. Most models have a limit (e.g. 32,000 tokens). "
            "The counter turns amber when you're approaching the limit. "
            "If the AI seems forgetful or starts ignoring earlier messages, the context is full — "
            "click 🗑 Clear to start fresh."
        ),
        "example": (
            "'~1,200 / 32,000 tokens (4%)' means you have plenty of room. "
            "At 80%+, consider clearing the conversation before asking new questions."
        ),
    },
}
