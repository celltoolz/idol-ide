"""Venv learning guide pages for use with GuideWindow."""
from __future__ import annotations

from widgets.guide_window import GuidePage


def get_pages() -> list[GuidePage]:
    """Return the virtual environment learning guide as a list of GuidePage objects."""
    return [
        GuidePage(
            title="What is a Virtual Environment?",
            sections=[
                (
                    "THE IDEA",
                    "A virtual environment is an isolated copy of Python and its packages "
                    "that belongs only to your project. Think of it as a clean room — "
                    "whatever you install inside stays inside and doesn't affect anything else on your computer.",
                    "#569cd6",
                ),
                (
                    "WHAT IT CONTAINS",
                    "• A copy of the Python interpreter\n"
                    "• Its own pip\n"
                    "• An isolated site-packages folder where libraries are installed\n"
                    "• Activation scripts (activate, activate.bat, Activate.ps1)",
                    "#cccccc",
                ),
                (
                    "WHERE IT LIVES",
                    "Usually in a folder called venv/ or .venv/ at the root of your project. "
                    "This folder should always be listed in your .gitignore — it can contain "
                    "hundreds of files and is specific to your machine.",
                    "#e2c08d",
                ),
            ],
            plain_english=(
                "Imagine every project gets its own toolbox. Whatever tools (packages) "
                "you put in that toolbox stay there and don't mix with anyone else's. "
                "If you break something in the toolbox, you just throw it away and "
                "make a new one — your other projects are completely untouched."
            ),
        ),
        GuidePage(
            title="Why Use a Virtual Environment?",
            sections=[
                (
                    "DEPENDENCY ISOLATION",
                    "Different projects often need different versions of the same library. "
                    "Without venvs, installing a new package for one project could break another. "
                    "Each venv has its own independent set of packages.",
                    "#73c991",
                ),
                (
                    "REPRODUCIBILITY",
                    "When you freeze your dependencies with 'pip freeze > requirements.txt', "
                    "anyone who clones your project can run 'pip install -r requirements.txt' "
                    "inside their own venv and get an identical environment.",
                    "#569cd6",
                ),
                (
                    "KEEPS YOUR SYSTEM CLEAN",
                    "Installing packages globally (without a venv) pollutes your system Python "
                    "and can conflict with system tools. A venv keeps everything contained "
                    "and easy to throw away if something goes wrong.",
                    "#cccccc",
                ),
            ],
            plain_english=(
                "Without venvs, installing a package for one project is like putting "
                "a tool on your kitchen counter — eventually there's no space and "
                "things start getting in each other's way. A venv gives each project "
                "its own drawer. Need to start fresh? Just empty the drawer."
            ),
        ),
        GuidePage(
            title="Choosing a Python Interpreter",
            sections=[
                (
                    "WHY ARE THERE MULTIPLE?",
                    "It's common to have several Python installations on one machine — "
                    "the system Python that came with your OS, one you installed from python.org, "
                    "one inside a virtual environment, maybe one from Homebrew or pyenv. "
                    "They are completely independent and may have different versions and packages.",
                    "#569cd6",
                ),
                (
                    "WHICH ONE SHOULD I PICK?",
                    "For a new project, pick the newest stable Python you have installed "
                    "(e.g. 3.12 over 3.9). Avoid the one labelled '.venv' or 'venv' — "
                    "that's the interpreter inside an existing virtual environment and should "
                    "not be used to create another one inside it.",
                    "#73c991",
                ),
                (
                    "AVOID THE SYSTEM PYTHON",
                    "On macOS and Linux there is often a system Python at /usr/bin/python3. "
                    "Avoid using it for your projects — it belongs to the OS, may be outdated, "
                    "and some systems restrict what you can install into it. "
                    "Use a Python you installed yourself instead.",
                    "#e2c08d",
                ),
                (
                    "THE VENV WILL USE YOUR CHOICE",
                    "When you create a virtual environment, it copies the interpreter you selected. "
                    "After activation, 'python' and 'pip' inside the project always refer to "
                    "that version — no matter what else is installed on your system.",
                    "#cccccc",
                ),
            ],
            plain_english=(
                "Think of Python versions like different models of a car. You might "
                "have a 2019 and a 2023 sitting in your garage. When you start a "
                "project, you pick which one to drive — and that project always uses "
                "that car, even if you buy a newer model later. The system Python "
                "is like a car the house came with: it's there, but it's not really yours to modify."
            ),
        ),
        GuidePage(
            title="Creating a Virtual Environment",
            sections=[
                (
                    "CREATE",
                    "python -m venv venv\n\n"
                    "This creates a venv/ folder in your current directory. "
                    "You only need to do this once per project.",
                    "#569cd6",
                ),
                (
                    "ACTIVATE",
                    "Windows (PowerShell):   venv\\Scripts\\Activate.ps1\n"
                    "Windows (CMD):          venv\\Scripts\\activate.bat\n"
                    "macOS / Linux:          source venv/bin/activate\n\n"
                    "Your terminal prompt will show (venv) when active.",
                    "#73c991",
                ),
                (
                    "INSTALL PACKAGES",
                    "pip install requests numpy pandas\n\n"
                    "Packages are installed into the venv only. "
                    "When you're done working, run 'deactivate' to leave the environment.",
                    "#cccccc",
                ),
            ],
        ),
        GuidePage(
            title="Best Practices",
            sections=[
                (
                    "ALWAYS ADD TO .GITIGNORE",
                    "Add venv/ (or whatever you named it) to your .gitignore before your first commit. "
                    "The venv folder can have thousands of files and must never be committed to git.",
                    "#f14c4c",
                ),
                (
                    "TRACK DEPENDENCIES INSTEAD",
                    "pip freeze > requirements.txt\n\n"
                    "Commit requirements.txt — not the venv. This is a small text file that "
                    "lets anyone recreate your exact environment with one command.",
                    "#73c991",
                ),
                (
                    "ONE VENV PER PROJECT",
                    "Don't share venvs between projects. Create a fresh one for each project "
                    "so dependencies stay clean and isolated. Name it venv/ or .venv/ by convention.",
                    "#cccccc",
                ),
            ],
            plain_english=(
                "The venv folder can have thousands of files but requirements.txt is "
                "just a shopping list. Don't commit the whole supermarket — just the "
                "list. Anyone who needs to restock can read the list and buy exactly "
                "what's needed. It also means your git history stays fast and clean."
            ),
        ),
    ]
