"""Git identity & GitHub login guide content — GuidePage objects for GuideWindow."""
from __future__ import annotations

from utils.guide_types import GuidePage


def get_pages() -> list[GuidePage]:
    return [
        GuidePage(
            title="Set Your Git Identity",
            subtitle="Page 1 of 4",
            sections=[
                (
                    "WHAT IS GIT IDENTITY?",
                    "Every commit you make is stamped with your name and email. "
                    "Without this configured, git will either refuse to commit or "
                    "use a generic placeholder that makes your history hard to read.",
                    "#e2c08d",
                ),
                (
                    "SET YOUR NAME AND EMAIL",
                    "Open the terminal in IDOL (Ctrl+`) and run these two commands "
                    "— replace the values with your own:\n\n"
                    "    git config --global user.name \"Your Name\"\n"
                    "    git config --global user.email \"you@example.com\"\n\n"
                    "The --global flag sets this for every repo on your machine, "
                    "so you only need to do this once.",
                    "#73c991",
                ),
                (
                    "VERIFY",
                    "    git config --global --list\n\n"
                    "You should see user.name and user.email in the output.",
                    "#569cd6",
                ),
            ],
        ),
        GuidePage(
            title="Create a GitHub Account",
            subtitle="Page 2 of 4",
            sections=[
                (
                    "WHAT IS GITHUB?",
                    "GitHub is a website where you store your git repositories online. "
                    "It acts as a remote backup, lets you share code, and is where "
                    "most open-source projects live. Git (the tool) and GitHub "
                    "(the website) are separate things — git works locally without "
                    "GitHub, but GitHub requires git.",
                    "#e2c08d",
                ),
                (
                    "SIGN UP",
                    "Visit github.com and create a free account. "
                    "Use the same email address you set in your git identity — "
                    "this links your commits to your GitHub profile.",
                    "#73c991",
                ),
            ],
        ),
        GuidePage(
            title="Authenticate with GitHub CLI",
            subtitle="Page 3 of 4",
            sections=[
                (
                    "INSTALL GITHUB CLI — WINDOWS",
                    "    winget install --id GitHub.cli -e --source winget\n\n"
                    "After install, close and reopen the terminal so gh is on your PATH.",
                    "#73c991",
                ),
                (
                    "INSTALL GITHUB CLI — macOS",
                    "    brew install gh",
                    "#4ec9b0",
                ),
                (
                    "INSTALL GITHUB CLI — LINUX",
                    "Install instructions vary by distro. See the official guide:\n\n"
                    "    github.com/cli/cli/blob/trunk/docs/install_linux.md",
                    "#c586c0",
                ),
                (
                    "LOG IN",
                    "    gh auth login\n\n"
                    "Select GitHub.com → HTTPS → Yes (authenticate git) → Login with a web browser. "
                    "A code will appear — copy it, press Enter, and paste it in the browser page "
                    "that opens. That's it — git is now authenticated.",
                    "#569cd6",
                ),
            ],
        ),
        GuidePage(
            title="Verify Everything is Working",
            subtitle="Page 4 of 4",
            sections=[
                (
                    "CHECK AUTH STATUS",
                    "    gh auth status\n\n"
                    "You should see: ✓ Logged in to github.com as <your-username>",
                    "#73c991",
                ),
                (
                    "CHECK GIT IDENTITY",
                    "    git config --global user.name\n"
                    "    git config --global user.email\n\n"
                    "Both should print your configured values.",
                    "#569cd6",
                ),
                (
                    "WHAT'S NEXT?",
                    "You're ready to use git with GitHub. Use the Project Wizard "
                    "(File → New Project...) to scaffold a new project with a git "
                    "repository, then use the Source Control panel to stage, commit, "
                    "and push your first changes.",
                    "#e2c08d",
                ),
            ],
        ),
    ]
