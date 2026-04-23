"""Guide pages for the 'input() & Debug' guide window."""
from __future__ import annotations

from typing import Callable

from utils.guide_types import GuidePage

_ORANGE = "#ce9178"
_BLUE   = "#569cd6"
_GREEN  = "#4ec9b0"
_DIM    = "#919191"


def make_pages(switch_fn: Callable) -> list[GuidePage]:
    return [
        GuidePage(
            title="input() in Debug Mode",
            subtitle="Why your script is waiting",
            sections=[
                (
                    "The problem",
                    "Your script called input(), but in Output debug mode the subprocess "
                    "stdin isn't wired to the inline › bar — it's managed by debugpy, which "
                    "doesn't forward keyboard input to your script.",
                    _ORANGE,
                ),
                (
                    "What you see",
                    "The script appears to hang. The › input bar has no effect while the "
                    "debugger is active in Output mode.",
                    _BLUE,
                ),
            ],
            plain_english=(
                "Think of debugpy as a middleman sitting between IDOL and your script. "
                "The middleman handles step-by-step control, but it doesn't pass along "
                "what you type — so your script waits for input that never arrives."
            ),
        ),
        GuidePage(
            title="Terminal Debug Mode",
            subtitle="input() works natively here",
            sections=[
                (
                    "How it works",
                    "In Terminal mode, debugpy launches your script inside the integrated "
                    "terminal — a real PTY shell. input() works exactly like running the "
                    "script from a command line.",
                    _GREEN,
                ),
                (
                    "Full debugger + stdin",
                    "You keep all debugger features: breakpoints, step over/into, locals "
                    "panel. When your script calls input(), just type your response directly "
                    "in the terminal.",
                    _BLUE,
                ),
            ],
            plain_english=(
                "Terminal debug mode is like handing your script a real keyboard. "
                "Everything works — including input()."
            ),
        ),
        GuidePage(
            title="Switch to Terminal Debug",
            subtitle="One click to fix it",
            sections=[
                (
                    "What happens next",
                    "Clicking the button below stops the current session, switches the run "
                    "target to Terminal, and restarts the debugger automatically.",
                    _BLUE,
                ),
                (
                    "Change it anytime",
                    "The chevron (›) next to the Run button in the nav toolbar lets you "
                    "switch between Output and Terminal debug mode at any time.",
                    _DIM,
                ),
            ],
            action_label="↺  Switch to Terminal Debug",
            action_fn=switch_fn,
        ),
    ]
