from __future__ import annotations

from tkinter import Menu

_THEMES = ["ayu-dark", "ayu-light", "dracula", "mariana", "material", "monokai", "rrt"]


def build_menubar(app) -> Menu:
    """Build and attach the menu bar to *app*.

    app must expose the following methods / attributes:
      file_new, file_open, file_save, file_save_as, file_close, file_exit
      edit_undo, edit_redo, edit_cut, edit_copy, edit_paste, edit_select_all,
      edit_find_replace
      view_change_theme, view_change_font, view_toggle_highlight,
      view_active_line_color, view_toggle_output, view_new_terminal
      run_file, run_stop, run_clear
      help_about
      theme_var, highlight_line_var, output_visible_var
    """
    menubar = Menu(app)

    # ── File ─────────────────────────────────────────────────────────────────
    file_menu = Menu(menubar, tearoff=0)
    file_menu.add_command(label="New", command=app.file_new, accelerator="Ctrl+N")
    file_menu.add_command(label="New Project...", command=app.file_new_project)
    file_menu.add_command(label="Open...", command=app.file_open, accelerator="Ctrl+O")
    file_menu.add_separator()
    file_menu.add_command(label="Save", command=app.file_save, accelerator="Ctrl+S")
    file_menu.add_command(
        label="Save As...", command=app.file_save_as, accelerator="Ctrl+Shift+S"
    )
    file_menu.add_separator()
    file_menu.add_command(label="New Workspace", command=app.workspace_new)
    file_menu.add_command(label="Close Workspace", command=app.workspace_close)
    file_menu.add_separator()
    file_menu.add_command(label="Save Workspace...", command=app.workspace_save)
    file_menu.add_command(label="Open Workspace...", command=app.workspace_open)
    file_menu.add_separator()
    file_menu.add_command(
        label="Close Tab", command=app.file_close, accelerator="Ctrl+W"
    )
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=app.file_exit, accelerator="Ctrl+Q")
    menubar.add_cascade(label="File", menu=file_menu)

    # ── Edit ─────────────────────────────────────────────────────────────────
    edit_menu = Menu(menubar, tearoff=0)
    edit_menu.add_command(label="Undo", command=app.edit_undo, accelerator="Ctrl+Z")
    edit_menu.add_command(label="Redo", command=app.edit_redo, accelerator="Ctrl+Y")
    edit_menu.add_separator()
    edit_menu.add_command(label="Cut", command=app.edit_cut, accelerator="Ctrl+X")
    edit_menu.add_command(label="Copy", command=app.edit_copy, accelerator="Ctrl+C")
    edit_menu.add_command(label="Paste", command=app.edit_paste, accelerator="Ctrl+V")
    edit_menu.add_command(
        label="Select All", command=app.edit_select_all, accelerator="Ctrl+A"
    )
    edit_menu.add_separator()
    edit_menu.add_command(
        label="Find & Replace...", command=app.edit_find_replace, accelerator="Ctrl+F"
    )
    menubar.add_cascade(label="Edit", menu=edit_menu)

    # ── View ─────────────────────────────────────────────────────────────────
    view_menu = Menu(menubar, tearoff=0)

    theme_menu = Menu(view_menu, tearoff=0)
    for theme in _THEMES:
        theme_menu.add_radiobutton(
            label=theme,
            variable=app.theme_var,
            value=theme,
            command=app.view_change_theme,
        )
    view_menu.add_cascade(label="Theme", menu=theme_menu)
    view_menu.add_command(
        label="Change Font...", command=app.view_change_font, accelerator="Ctrl+L"
    )
    view_menu.add_separator()
    view_menu.add_checkbutton(
        label="Highlight Active Line",
        variable=app.highlight_line_var,
        command=app.view_toggle_highlight,
    )
    view_menu.add_command(
        label="Active Line Color...", command=app.view_active_line_color
    )
    view_menu.add_separator()
    view_menu.add_checkbutton(
        label="Show Output Panel",
        variable=app.output_visible_var,
        command=app.view_toggle_output,
    )
    view_menu.add_command(
        label="New Terminal",
        command=app.view_new_terminal,
        accelerator="Ctrl+`",
    )
    view_menu.add_checkbutton(
        label="Show Minimap",
        variable=app.minimap_visible_var,
        command=app.view_toggle_minimap,
    )
    view_menu.add_separator()
    view_menu.add_command(
        label="Split Editor",
        command=app.view_split_editor,
        accelerator="Ctrl+\\",
    )
    view_menu.add_command(
        label="Zen Mode",
        command=app.view_zen_mode,
        accelerator="F11",
    )
    view_menu.add_command(
        label="Source Control",
        command=app.view_source_control,
        accelerator="Ctrl+Shift+G",
    )
    menubar.add_cascade(label="View", menu=view_menu)

    # ── Run ──────────────────────────────────────────────────────────────────
    run_menu = Menu(menubar, tearoff=0)
    run_menu.add_command(label="Run File", command=app.run_file, accelerator="F5")
    run_menu.add_command(label="Stop", command=app.run_stop)
    run_menu.add_separator()
    run_menu.add_command(label="Clear Output", command=app.run_clear)
    menubar.add_cascade(label="Run", menu=run_menu)

    # ── Help ─────────────────────────────────────────────────────────────────
    help_menu = Menu(menubar, tearoff=0)
    help_menu.add_command(
        label="Command Palette...",
        command=app.open_command_palette,
        accelerator="Ctrl+Shift+P",
    )
    help_menu.add_separator()
    help_menu.add_command(label="[DEBUG] Populate SC Lists", command=app._debug_populate_sc)
    help_menu.add_separator()
    help_menu.add_command(label="About", command=app.help_about)
    menubar.add_cascade(label="Help", menu=help_menu)

    app.configure(menu=menubar)
    return menubar
