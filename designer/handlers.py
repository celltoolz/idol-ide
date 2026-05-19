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

    # ── New fields ────────────────────────────────────────────────────────────
    # True → opens Connector dialog to wire to a widget event
    connectable: bool = False
    # True → always shown in Connected section, never removable
    always_wired: bool = False
    # display string for the built-in connection target, e.g. "<Escape>"
    display_target: str = ""
    # selectable options shown in the [...] editor row
    options: tuple[str, ...] = ()
    # parallel to options: handler stub body for each option (overrides default_body)
    stub_option_bodies: tuple[str, ...] = ()
    # parallel to options: body emitted inside the wired widget event for each option
    wire_option_bodies: tuple[str, ...] = ()
    # widget types this handler can be wired to; empty = all widget types
    applies_to_widgets: tuple[str, ...] = ()
    # False → no "def _id(self):" stub emitted (wire body goes directly in widget event)
    generates_stub: bool = True
    # Template for the wire body when option is not in the static options list
    # Use {option} as a placeholder, e.g. "self._open_{option}()"
    dynamic_wire_body: str = ""
    # True → stays in Available even after wiring (can be wired to multiple targets)
    multi_wire: bool = False
    # Options shown in the mode-change editor on Connected rows (e.g. "hide (withdraw)")
    secondary_options: tuple[str, ...] = ()
    # "linked_dialogs" → connector pulls primary options from form.linked_dialogs at runtime
    connector_options_source: str = ""
    # Descriptions shown in HandlerOptionsEditor alongside secondary_options rows.
    # Parallel to secondary_options; if empty, falls back to wire_option_bodies.
    edit_bodies: tuple[str, ...] = ()
    # Side-effect tag applied after wiring or mode-change. Dispatched in app.py.
    # "sync_dialog_close_mode" → update linked dialog's _on_close handler_option
    wire_side_effects: str = ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_option(self, option: str) -> str:
        """Map option to a current option name, handling old short forms.

        Allows "destroy" to match "destroy (exit)" and "hide" to match
        "hide (withdraw)" so projects saved before the rename still work.
        """
        if not option:
            return option
        if option in self.options:
            return option
        for o in self.options:
            if o.startswith(option):
                return o
        return option

    def stub_body_for(self, option: str) -> str:
        """Return the handler stub body for the given option name."""
        opt = self._resolve_option(option)
        if opt and opt in self.options:
            idx = self.options.index(opt)
            if idx < len(self.stub_option_bodies):
                return self.stub_option_bodies[idx]
        return self.default_body

    def wire_body_for(self, option: str, handler_id: str) -> str:
        """Return the widget-event body for the given option name.

        Static options are checked first (with backward-compat normalization);
        dynamic_wire_body is used as a fallback template for dynamic values
        such as dialog names. Falls back to ``self.handler_id()`` when nothing matches.
        """
        opt = self._resolve_option(option)
        if opt and opt in self.options:
            idx = self.options.index(opt)
            if idx < len(self.wire_option_bodies):
                return self.wire_option_bodies[idx]
        if self.dynamic_wire_body and option:
            # Strip :secondary suffix (e.g. "Dialog1:destroy (exit)" → "Dialog1")
            base = option.split(":")[0]
            return self.dynamic_wire_body.replace("{option}", base)
        return f"self.{handler_id}()"


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
        always_wired=True,
        display_target="WM_DELETE_WINDOW",
        options=("hide (withdraw)", "destroy (exit)"),
        stub_option_bodies=(
            "self.withdraw()  — reuses instance on next open",
            "self.destroy()  — recreated fresh on next open",
        ),
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
        display_target="<Escape>",
        options=("hide (withdraw)", "destroy (exit)"),
        stub_option_bodies=("self.withdraw()", "self.destroy()"),
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
        display_target="<Return>",
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
        display_target="<FocusIn>",
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
        display_target="<FocusOut>",
    ),
    HandlerDef(
        id="_set_always_on_top",
        label="always_on_top",
        description=(
            "Wire to a button or menu item to control window pinning. "
            "Choose toggle, enable, or disable when connecting."
        ),
        applies_to=("main", "dialog"),
        default_checked=False,
        wiring="",
        params="event=None",
        default_body='self.attributes("-topmost", not self.attributes("-topmost"))',
        connectable=True,
        applies_to_widgets=("Button", "Label", "Checkbutton", "Radiobutton"),
        options=("toggle", "enable", "disable"),
        wire_option_bodies=(
            'self.attributes("-topmost", not self.attributes("-topmost"))',
            'self.attributes("-topmost", True)',
            'self.attributes("-topmost", False)',
        ),
    ),
    HandlerDef(
        id="_open_dialog",
        label="open_dialog",
        description=(
            "Wire to any widget event to open a linked dialog window. "
            "Pick the dialog and its close mode in the connector. "
            "Can be wired to multiple widget events — one per dialog."
        ),
        applies_to=("main",),
        default_checked=False,
        wiring="",
        params="event=None",
        default_body="pass  # TODO",
        connectable=True,
        generates_stub=False,
        multi_wire=True,
        dynamic_wire_body="self._open_{option}()",
        secondary_options=("hide (withdraw)", "destroy (exit)"),
        connector_options_source="linked_dialogs",
        edit_bodies=(
            "withdraw() — reuses instance on next open",
            "destroy() — recreated fresh on next open",
        ),
        wire_side_effects="sync_dialog_close_mode",
    ),
]


def handlers_for(form_type: str) -> list[HandlerDef]:
    """Return all handlers applicable to the given form type."""
    return [h for h in HANDLER_CATALOG if form_type in h.applies_to]


def default_enabled_for(form_type: str) -> list[str]:
    """Return IDs of handlers that are on by default for the given form type."""
    return [h.id for h in handlers_for(form_type) if h.default_checked]
