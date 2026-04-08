import platform as _platform


def bind_right_click(widget, callback) -> None:
    """Bind a right-click handler cross-platform.

    On macOS, Ctrl+Click fires <Control-Button-1> rather than <Button-3>,
    so we bind both events to the same callback.
    """
    widget.bind("<Button-3>", callback)
    if _platform.system() == "Darwin":
        widget.bind("<Control-Button-1>", callback)
