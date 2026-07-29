"""Conda channels guide content — GuidePage objects for GuideWindow.

Deliberately curated rather than generated from `conda config --describe`:
that text is written for people who already know conda's model, and the one
thing beginners actually get wrong (which end of the list wins) it never says
plainly.
"""
from __future__ import annotations

from utils.guide_types import GuidePage


def get_pages() -> list[GuidePage]:
    return [
        GuidePage(
            title="What a Channel Is",
            subtitle="Page 1 of 3",
            sections=[
                (
                    "THE IDEA",
                    "A channel is a place conda downloads packages from. PyPI is "
                    "one big shared index; conda instead has several independent "
                    "channels, each built and maintained by different people.\n\n"
                    "conda-forge is the large community channel. defaults is "
                    "Anaconda's own. bioconda, pytorch and nvidia are "
                    "specialist channels for one field or one vendor's software.",
                    "#569cd6",
                ),
                (
                    "ORDER IS THE CONFIGURATION",
                    "The channel list is ordered, and the order is not cosmetic — "
                    "it decides which copy of a package you get when two channels "
                    "both offer it. The CHANNELS bar numbers them for exactly "
                    "this reason: 1 is searched first.\n\n"
                    "Reordering your channels can change which build of numpy you "
                    "install. It is a real configuration change, not a display "
                    "preference.",
                    "#73c991",
                ),
                (
                    "EACH ONE COSTS SOMETHING",
                    "Every active channel is another index conda downloads and "
                    "another set of candidates the solver considers. Two to four "
                    "channels is normal. A dozen makes every install slow and "
                    "makes conflicts much harder to resolve.",
                    "#e2c08d",
                ),
            ],
            plain_english=(
                "Channels are separate app stores. The order is which store you "
                "walk into first — and if the same app is in two of them, the "
                "first one wins."
            ),
        ),
        GuidePage(
            title="Priority and the Direction Trap",
            subtitle="Page 2 of 3",
            sections=[
                (
                    "WHY TUTORIALS LOOK BACKWARDS",
                    "conda's command line disagrees with itself about direction, "
                    "which is why copied setup instructions so often produce the "
                    "wrong order:\n\n"
                    "    conda config --add channels X      → X becomes FIRST\n"
                    "    conda config --append channels X   → X becomes LAST\n"
                    "    conda install -c A -c B            → A ranks above B\n\n"
                    "Because --add prepends, guides that want [conda-forge, "
                    "bioconda] tell you to add them in the opposite order. Read "
                    "any such instructions carefully, then check the numbers in "
                    "the CHANNELS bar — those are the truth.",
                    "#e2c08d",
                ),
                (
                    "WHAT PRIORITY MODE MEANS",
                    "The bar also shows conda's channel_priority setting, which "
                    "changes what the order does:\n\n"
                    "strict — a package found in a higher channel hides every "
                    "lower one for that name. Fastest, and the safest against "
                    "mixing incompatible builds, but it can make an environment "
                    "impossible to solve.\n\n"
                    "flexible — conda's default. The solver may drop to a lower "
                    "channel to satisfy a dependency. Slower, and more likely to "
                    "leave you with a mixed-channel environment.\n\n"
                    "disabled — the version number wins and channel order is only "
                    "a tiebreaker.",
                    "#569cd6",
                ),
                (
                    "CHANGING PRIORITY MODE",
                    "IDOL shows this value but does not edit it: it is a setting "
                    "for your whole conda installation, stored in ~/.condarc, "
                    "and IDOL does not write to a file conda also owns. To change "
                    "it, run one of these in the terminal (Ctrl+`):\n\n"
                    "    conda config --set channel_priority strict\n"
                    "    conda config --set channel_priority flexible\n\n"
                    "The bar picks the new value up next time it refreshes.",
                    "#cccccc",
                ),
            ],
            plain_english=(
                "\"First in the list\" and \"top of the file\" and \"--add\" all "
                "mean the same thing, and \"--append\" means the opposite. Trust "
                "the numbers, not the words."
            ),
        ),
        GuidePage(
            title="Where IDOL Reads It From",
            subtitle="Page 3 of 3",
            sections=[
                (
                    "YOUR PROJECT'S FILE COMES FIRST",
                    "If your project has an environment.yml, its channels: block "
                    "is what IDOL shows and uses. That file is the store — it "
                    "goes into git, so a teammate who runs "
                    "`conda env create -f environment.yml` resolves packages "
                    "exactly the way you do.\n\n"
                    "IDOL will not keep a second copy of your channel list in its "
                    "own settings. Two sources of truth for the same "
                    "configuration is how they end up disagreeing.",
                    "#569cd6",
                ),
                (
                    "OTHERWISE, YOUR CONDA'S OWN SETTINGS",
                    "With no environment.yml, IDOL asks conda directly and shows "
                    "which location the answer came from. There are several: a "
                    "system-wide file, your ~/.condarc, one inside the "
                    "environment itself, the CONDARC variable and the "
                    "CONDA_CHANNELS variable — and environment variables beat "
                    "files.\n\n"
                    "That is why the bar names its source. If it says "
                    "\"environment variables\", editing ~/.condarc will appear to "
                    "do nothing, and now you know why.\n\n"
                    "When you create a project, ~/.condarc seeds the new "
                    "environment.yml. After that the project's file is what "
                    "matters and the two can differ.",
                    "#73c991",
                ),
                (
                    "ABOUT defaults",
                    "Anaconda's Terms of Service require a paid Business plan for "
                    "organisations with 200 or more employees or contractors to "
                    "use Anaconda-maintained channels — that is what defaults "
                    "points at. Community channels such as conda-forge and "
                    "bioconda are exempt. Large nonprofits, academic "
                    "institutions and government bodies are not automatically "
                    "exempt.\n\n"
                    "Mixing defaults and conda-forge in one environment is also a "
                    "common source of breakage: they are built against different "
                    "compiler, BLAS and OpenSSL stacks. Current conda guidance is "
                    "to configure one or the other.\n\n"
                    "These are the facts, not legal advice — check with whoever "
                    "owns that decision where you work.",
                    "#e2c08d",
                ),
            ],
            plain_english=(
                "The project's environment.yml is the recipe that travels with "
                "the code. Your ~/.condarc is just the default IDOL starts a new "
                "recipe from."
            ),
        ),
    ]
