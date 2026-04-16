"""Git remote/push learning guide pages for use with GuideWindow."""

from __future__ import annotations

from utils.guide_types import GuidePage


def get_pages() -> list[GuidePage]:
    """Return the git remote setup guide as a list of GuidePage objects."""
    return [
        GuidePage(
            title="What is a Repository?",
            subtitle="The foundation of version control",
            sections=[
                (
                    "A PLACE FOR YOUR PROJECT",
                    "A repository (repo) is a folder that git has been asked to track. "
                    "It stores every version of every file you've ever saved — not just "
                    "the current state, but the entire history of how your project evolved.",
                    "#569cd6",
                ),
                (
                    "MORE THAN JUST FILES",
                    "Inside every repo is a hidden .git folder. That's where git stores "
                    "your commit history, branches, author information, and configuration. "
                    "You never need to touch it directly — git manages it for you.",
                    "#cccccc",
                ),
                (
                    "COMMITS ARE SNAPSHOTS",
                    "Each time you commit, git takes a snapshot of your project at that "
                    "moment. You can revisit any snapshot, compare changes between them, "
                    "or undo mistakes — even weeks or months later.",
                    "#73c991",
                ),
                (
                    "LOCAL ONLY — FOR NOW",
                    "A fresh repository lives entirely on your machine. Only you can see it. "
                    "To share your work or back it up online, you need a remote — "
                    "which is exactly what the next page covers.",
                    "#e2c08d",
                ),
            ],
            plain_english=(
                "Think of a repository like a project folder that secretly keeps a "
                "photograph of itself every time you say 'save a checkpoint'. "
                "You can always go back to any photograph, even if you've changed "
                "everything since. It's like an infinite undo button for your entire project."
            ),
        ),
        GuidePage(
            title="What is a Git Remote?",
            sections=[
                (
                    "THE IDEA",
                    "A remote is a copy of your repository hosted on a server — usually GitHub, "
                    "GitLab, or Bitbucket. While git tracks your changes locally, a remote lets "
                    "you back up your work online and share it with others.",
                    "#569cd6",
                ),
                (
                    "LOCAL vs REMOTE",
                    "Your local repository lives only on your computer. A remote repository "
                    "lives on a server. 'Push' sends your commits to the remote. 'Pull' brings "
                    "changes from the remote down to your machine.",
                    "#cccccc",
                ),
                (
                    "WHY YOU NEED ONE TO PUSH",
                    "Git doesn't know where to send your commits until you tell it. "
                    "A remote called 'origin' is the convention for your primary server. "
                    "Once it's configured, 'git push' knows exactly where to go.",
                    "#e2c08d",
                ),
            ],
            plain_english=(
                "Imagine your project folder is a notebook. A remote is like making "
                "a photocopy and storing it in a safe at the bank. Your original is "
                "still at home (local), but if your house burns down — or you just "
                "want to work from a different computer — the safe copy is there. "
                "Push = putting a new copy in the safe. Pull = grabbing the latest copy."
            ),
        ),
        GuidePage(
            title="Creating a Repository on GitHub",
            sections=[
                (
                    "STEP 1 — SIGN IN",
                    "Go to github.com and sign in to your account. "
                    "If you don't have one, creating an account is free.",
                    "#569cd6",
                ),
                (
                    "STEP 2 — NEW REPOSITORY",
                    "Click the '+' icon in the top right and select 'New repository'. "
                    "Give it a name that matches your project. Leave it empty — "
                    "don't add a README or .gitignore since your local project already has them.",
                    "#73c991",
                ),
                (
                    "STEP 3 — COPY THE URL",
                    "After creating the repo, GitHub shows you a URL like:\n"
                    "https://github.com/yourusername/yourproject.git\n\n"
                    "Copy this — you'll need it in the next step.",
                    "#cccccc",
                ),
            ],
        ),
        GuidePage(
            title="Connecting Your Local Repo to GitHub",
            sections=[
                (
                    "ADD THE REMOTE",
                    "In your terminal, run:\n\n"
                    "git remote add origin https://github.com/yourusername/yourproject.git\n\n"
                    "Replace the URL with the one you copied from GitHub. "
                    "'origin' is just a name — it's the standard convention for your main remote.",
                    "#569cd6",
                ),
                (
                    "PUSH FOR THE FIRST TIME",
                    "git push -u origin main\n\n"
                    "The -u flag sets 'origin main' as the default so future pushes "
                    "only need 'git push'. If your branch is called 'master' instead of 'main', "
                    "use that name instead.",
                    "#73c991",
                ),
                (
                    "VERIFY IT WORKED",
                    "Refresh your GitHub page — your files should now appear there. "
                    "From this point on, 'git push' in this project will send commits "
                    "to GitHub automatically.",
                    "#cccccc",
                ),
            ],
        ),
        GuidePage(
            title="Authentication",
            sections=[
                (
                    "GITHUB NOW USES TOKENS",
                    "GitHub no longer accepts your account password for git operations. "
                    "You need a Personal Access Token (PAT) or SSH key instead.",
                    "#e2c08d",
                ),
                (
                    "PERSONAL ACCESS TOKEN (easiest)",
                    "Go to GitHub → Settings → Developer Settings → Personal Access Tokens → "
                    "Tokens (classic) → Generate new token.\n\n"
                    "Select 'repo' scope and generate. When git asks for a password, "
                    "paste the token instead. Your OS credential manager will save it.",
                    "#569cd6",
                ),
                (
                    "SSH KEY (recommended for regular use)",
                    'Generate a key:  ssh-keygen -t ed25519 -C "you@email.com"\n'
                    "Add to GitHub:   Settings → SSH and GPG Keys → New SSH Key\n"
                    "Use SSH URL:     git remote add origin git@github.com:user/repo.git\n\n"
                    "SSH never asks for a password once set up.",
                    "#73c991",
                ),
            ],
            plain_english=(
                "GitHub used to let you log in with your password. They stopped that "
                "because passwords aren't safe enough for automated tools. Now you "
                "generate a special code (a token) that works like a temporary "
                "password just for git — you can revoke it any time without changing "
                "your actual account password. SSH keys work the same way but are "
                "even more secure and never ask you to type anything."
            ),
        ),
    ]
