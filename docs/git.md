# Git Integration

## Status & Gutter

- Branch name in the status bar with live 30-second polling
- M/A/U/D badges on tabs and file explorer entries (Modified, Added, Untracked, Deleted)
- Gutter diff strips showing added/modified/deleted lines inline in the editor

## Source Control Panel

Open with `Ctrl+Shift+G`. Shows staged/unstaged file lists with full workflow:

- Stage / unstage / discard individual files
- Commit with message
- Push / pull
- Diff view with color-coded +/- lines

### Inline File Explanations
Hover any file in the Source Control list for a tooltip explaining what it is and why git cares about it.

## Git Health Panel

Scannable checklist of common git hygiene issues:

- `.gitignore` exists
- No venv files tracked
- No secrets staged
- No large build artifacts committed

Each issue has a **one-click fix** button. Smart warning detection automatically identifies venv files, secrets, build artifacts, and OS metadata in untracked files.

When git is not installed, the health panel shows a guide for installing git on Windows, macOS, or Linux.

## Guided Fix Wizard

Step-by-step resolution flow for git problems:
1. What happened
2. Why it matters
3. How to fix it (with an action button)

## Commit History Panel

Scrollable HISTORY section inside the Source Control panel showing the last 50 commits.

- Colored ref/branch badges, author, and relative timestamps
- Click any commit to expand an inline list of changed files
- Click a file to open a syntax-highlighted diff tab scoped to that commit
- Hover a commit row for a popup showing the full hash, author, absolute date, subject, and all refs
- **Filter bar** to search commits by message, author, short hash, or branch name
- **Load 50 more** button for repos with deep history

## Git Identity Guide

When git user.name/email isn't configured, IDOL opens a 4-page guide covering:
- Setting `user.name` and `user.email`
- Creating a GitHub account
- Authenticating via GitHub CLI (`gh auth login`)

## First Commit Guide

After the Project Wizard creates a git-enabled project, a 4-page guide covers making a first commit and pushing to GitHub.
