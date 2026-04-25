"""Git install guide content — returned as GuidePage objects for GuideWindow."""
from __future__ import annotations

from utils.guide_types import GuidePage


def get_pages() -> list[GuidePage]:
    return [
        GuidePage(
            title="Install Git — Windows",
            subtitle="Page 1 of 3",
            sections=[
                (
                    "OPTION A — winget (recommended)",
                    "Open a terminal and run:\n\n    winget install --id Git.Git -e --source winget\n\n"
                    "winget is built into Windows 10 (1809+) and Windows 11. "
                    "After install, restart any open terminals so git appears on PATH.",
                    "#73c991",
                ),
                (
                    "OPTION B — installer",
                    "Download the official installer from git-scm.com/download/win and run it. "
                    "The default options work well — leave 'Git from the command line and also from '3rd-party software' "
                    "selected so git is on your PATH.",
                    "#569cd6",
                ),
                (
                    "VERIFY",
                    "Open a new terminal and run:\n\n    git --version\n\n"
                    "You should see something like:  git version 2.x.x",
                    "#e2c08d",
                ),
            ],
        ),
        GuidePage(
            title="Install Git — macOS",
            subtitle="Page 2 of 3",
            sections=[
                (
                    "OPTION A — Xcode Command Line Tools",
                    "Run this in Terminal:\n\n    xcode-select --install\n\n"
                    "A dialog will appear asking to install the developer tools. "
                    "This is the simplest option and installs git maintained by Apple.",
                    "#73c991",
                ),
                (
                    "OPTION B — Homebrew",
                    "If you have Homebrew installed, run:\n\n    brew install git\n\n"
                    "This gives you the latest upstream git version. "
                    "If you don't have Homebrew yet, visit brew.sh for the one-line install command.",
                    "#569cd6",
                ),
                (
                    "VERIFY",
                    "Open a new terminal tab and run:\n\n    git --version\n\n"
                    "You should see something like:  git version 2.x.x",
                    "#e2c08d",
                ),
            ],
        ),
        GuidePage(
            title="Install Git — Linux",
            subtitle="Page 3 of 3",
            sections=[
                (
                    "DEBIAN / UBUNTU",
                    "    sudo apt update && sudo apt install git",
                    "#73c991",
                ),
                (
                    "FEDORA / RHEL / CENTOS",
                    "    sudo dnf install git\n\n"
                    "Or on older systems:  sudo yum install git",
                    "#569cd6",
                ),
                (
                    "ARCH LINUX",
                    "    sudo pacman -S git",
                    "#c586c0",
                ),
                (
                    "VERIFY",
                    "Open a new terminal and run:\n\n    git --version\n\n"
                    "You should see something like:  git version 2.x.x",
                    "#e2c08d",
                ),
            ],
        ),
    ]
