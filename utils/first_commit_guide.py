"""First commit guide content — GuidePage objects for GuideWindow."""
from __future__ import annotations

from utils.guide_types import GuidePage


def get_pages() -> list[GuidePage]:
    return [
        GuidePage(
            title="What Just Happened",
            subtitle="Page 1 of 4",
            sections=[
                (
                    "YOUR PROJECT IS READY",
                    "IDOL just created your project folder, set up a virtual environment, "
                    "and ran 'git init' — so git is already tracking this folder. "
                    "Right now git knows the folder exists but hasn't saved any of your "
                    "files yet. That's what a commit does.",
                    "#73c991",
                ),
                (
                    "WHAT IS A COMMIT?",
                    "A commit is a saved snapshot of your project at a point in time. "
                    "Think of it like a save point in a game — you can always come back "
                    "to it. Every commit has a message describing what changed, and git "
                    "keeps the full history so nothing is ever lost.",
                    "#569cd6",
                ),
            ],
        ),
        GuidePage(
            title="Stage Your Files",
            subtitle="Page 2 of 4",
            sections=[
                (
                    "OPEN SOURCE CONTROL",
                    "Click the Source Control icon in the left sidebar "
                    "(or press Ctrl+Shift+G). You'll see your new files listed "
                    "under CHANGES — these are files git knows about but hasn't "
                    "saved in a commit yet.",
                    "#e2c08d",
                ),
                (
                    "STAGE YOUR FILES",
                    "Right-click a file and choose 'Stage Changes', or right-click "
                    "the CHANGES header to stage everything at once. "
                    "Staged files move to STAGED CHANGES — they're now queued up "
                    "and ready to be included in your next commit.",
                    "#73c991",
                ),
                (
                    "WHY STAGE?",
                    "Staging lets you choose exactly which changes go into each commit. "
                    "For your first commit you'll typically stage everything, "
                    "but as your project grows you'll often commit one feature at a time.",
                    "#569cd6",
                ),
            ],
        ),
        GuidePage(
            title="Make Your First Commit",
            subtitle="Page 3 of 4",
            sections=[
                (
                    "WRITE A COMMIT MESSAGE",
                    "At the top of the Source Control panel there's a text box — "
                    "type a short message describing what this commit contains. "
                    "For your first commit something like 'Initial commit' or "
                    "'Project setup' is perfect.",
                    "#e2c08d",
                ),
                (
                    "COMMIT",
                    "Click the '✓ Commit' button. Git saves a permanent snapshot "
                    "of all your staged files. You'll see the STAGED CHANGES section "
                    "clear out — that means it worked.",
                    "#73c991",
                ),
            ],
        ),
        GuidePage(
            title="Push to GitHub",
            subtitle="Page 4 of 4",
            sections=[
                (
                    "CREATE A REPO ON GITHUB",
                    "Go to github.com, click the '+' menu → 'New repository'. "
                    "Give it the same name as your project. Leave it empty "
                    "(no README, no .gitignore) — your project already has those. "
                    "Copy the repository URL shown on the next page.",
                    "#e2c08d",
                ),
                (
                    "ADD THE REMOTE AND PUSH",
                    "Open the terminal in IDOL (Ctrl+`) and run:\n\n"
                    "    git remote add origin <your-repo-url>\n"
                    "    git push -u origin main\n\n"
                    "After that, the '↑ Push' button in the Source Control panel "
                    "will push future commits with one click.",
                    "#73c991",
                ),
                (
                    "YOU'RE DONE",
                    "Your project is now on GitHub. Every time you make changes, "
                    "stage them → commit → push. That's the whole workflow.",
                    "#569cd6",
                ),
            ],
        ),
    ]
