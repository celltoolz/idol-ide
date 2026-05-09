from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class HandlerDef:
    id:              str            # method name, e.g. "_on_close"
    label:           str            # display label
    description:     str            # hint bar text on hover
    applies_to:      tuple[str, ...]  # "main", "dialog"
    default_checked: bool
    wiring:          str            # line to emit in __init__ block; "" if none
    params:          str            # params after self in method sig
    default_body:    str            # default stub body


HANDLER_CATALOG: list[HandlerDef] = [
    HandlerDef(
        id="_on_close",
        label="on_close",
        description=(
            "Called when the user clicks the × button. Default hides the window "
            "(self.withdraw()) so the parent's self.dlg_X reference stays valid for reuse."
        ),
        applies_to=("dialog",),
        default_checked=True,
        wiring='self.protocol("WM_DELETE_WINDOW", self._on_close)',
        params="",
        default_body="self.withdraw()",
    ),
    HandlerDef(
        id="_on_escape",
        label="on_escape",
        description=(
            "Called when Escape is pressed anywhere in the window. "
            "Useful for closing dialogs, cancelling actions, or clearing selections."
        ),
        applies_to=("main", "dialog"),
        default_checked=False,
        wiring='self.bind("<Escape>", self._on_escape)',
        params="event=None",
        default_body="pass  # TODO",
    ),
    HandlerDef(
        id="_on_return",
        label="on_return",
        description=(
            "Called when Enter/Return is pressed anywhere in the window. "
            "Useful for confirming dialogs or submitting forms."
        ),
        applies_to=("main", "dialog"),
        default_checked=False,
        wiring='self.bind("<Return>", self._on_return)',
        params="event=None",
        default_body="pass  # TODO",
    ),
    HandlerDef(
        id="_on_focus_in",
        label="on_focus_in",
        description=(
            "Called when this window gains focus. "
            "Note: also fires when a child widget gains focus inside the window."
        ),
        applies_to=("main", "dialog"),
        default_checked=False,
        wiring='self.bind("<FocusIn>", self._on_focus_in)',
        params="event=None",
        default_body="pass  # TODO",
    ),
    HandlerDef(
        id="_on_focus_out",
        label="on_focus_out",
        description=(
            "Called when this window loses focus. "
            "Note: also fires when a child widget loses focus inside the window."
        ),
        applies_to=("main", "dialog"),
        default_checked=False,
        wiring='self.bind("<FocusOut>", self._on_focus_out)',
        params="event=None",
        default_body="pass  # TODO",
    ),
]


def handlers_for(form_type: str) -> list[HandlerDef]:
    """Return all handlers applicable to the given form type."""
    return [h for h in HANDLER_CATALOG if form_type in h.applies_to]


def default_enabled_for(form_type: str) -> list[str]:
    """Return IDs of handlers that are on by default for the given form type."""
    return [h.id for h in handlers_for(form_type) if h.default_checked]
