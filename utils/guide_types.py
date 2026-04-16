"""Shared dataclass for guide content pages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class GuidePage:
    """One page of a GuideWindow.

    sections: list of (label, body, color) tuples — label is the section
    heading, body is the paragraph text, color is the heading foreground.
    action_label / action_fn: optional button shown at the bottom of the page;
    clicking it runs action_fn then closes the window.
    """

    title: str
    subtitle: str = ""
    sections: list[tuple[str, str, str]] = field(default_factory=list)
    plain_english: str = ""
    action_label: str = ""
    action_fn: Callable | None = field(default=None, repr=False)
