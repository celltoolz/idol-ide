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
      view_active_line_color, view_toggle_output, view_show_panel,
      view_clipboard_history, view_canvas_editor_sandbox
      debug_file, _nav_run, run_line, run_selection, run_stop, run_clear
      help_about
      theme_var, highlight_line_var, output_visible_var, panel_tab_var, _run_target_var
    """
    menubar = Menu(app)

    # ── File ─────────────────────────────────────────────────────────────────
    file_menu = Menu(menubar, tearoff=0)
    file_menu.add_command(label="New",      command=app.file_new,  accelerator="Ctrl+N")
    file_menu.add_command(label="Open...",  command=app.file_open, accelerator="Ctrl+O")
    file_menu.add_command(label="Save",     command=app.file_save, accelerator="Ctrl+S")
    file_menu.add_command(
        label="Save As...", command=app.file_save_as, accelerator="Ctrl+Shift+S"
    )
    file_menu.add_separator()
    file_menu.add_command(label="New Project...",  command=app.file_new_project)
    file_menu.add_command(label="Open Project...", command=app.workspace_open)
    file_menu.add_command(label="Save Project",    command=app.workspace_save)
    file_menu.add_command(label="Close Project",   command=app.workspace_close)
    file_menu.add_separator()
    file_menu.add_command(
        label="Close Tab", command=app.file_close, accelerator="Ctrl+W"
    )
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=app.file_exit, accelerator="Ctrl+Q")
    menubar.add_cascade(label="File", menu=file_menu)

    # ── Edit ─────────────────────────────────────────────────────────────────
    edit_menu = Menu(menubar, tearoff=0, postcommand=app._update_edit_menu_state)
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
    app._edit_menu = edit_menu
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
    panels_menu = Menu(view_menu, tearoff=0)
    for _label, _key, _accel in [
        ("Output",   "output",   "Ctrl+Shift+U"),
        ("Terminal", "terminal", "Ctrl+`"),
        ("Problems", "problems", "Ctrl+Shift+M"),
        ("Debug",    "debug",    "Ctrl+Shift+Y"),
    ]:
        panels_menu.add_radiobutton(
            label=_label,
            variable=app.panel_tab_var,
            value=_key,
            accelerator=_accel,
            command=lambda k=_key: app.view_show_panel(k),
        )
    view_menu.add_cascade(label="Panels", menu=panels_menu)
    view_menu.add_checkbutton(
        label="Show Panels",
        variable=app.output_visible_var,
        command=app.view_toggle_output,
    )
    view_menu.add_checkbutton(
        label="Show Minimap",
        variable=app.minimap_visible_var,
        command=app.view_toggle_minimap,
    )
    view_menu.add_checkbutton(
        label="Show Sidebar",
        variable=app.sidebar_visible_var,
        command=app.view_toggle_sidebar,
        accelerator="Ctrl+B",
    )
    view_menu.add_separator()
    view_menu.add_command(
        label="Split Editor",
        command=app.view_split_editor,
        accelerator="Ctrl+\\",
    )
    view_menu.add_checkbutton(
        label="Zen Mode",
        variable=app.zen_mode_var,
        command=app.view_zen_mode,
        accelerator="F10",
    )
    view_menu.add_command(
        label="Source Control",
        command=app.view_source_control,
        accelerator="Ctrl+Shift+G",
    )
    view_menu.add_command(
        label="Clipboard History",
        command=app.view_clipboard_history,
        accelerator="Ctrl+Shift+H",
    )
    view_menu.add_command(
        label="Canvas Editor (Preview)",
        command=app.view_canvas_editor_sandbox,
    )
    menubar.add_cascade(label="View", menu=view_menu)

    # ── Run ──────────────────────────────────────────────────────────────────
    run_menu = Menu(menubar, tearoff=0)
    run_menu.add_command(label="Debug",         command=app.debug_file,    accelerator="F5")
    run_menu.add_command(label="Run",           command=app._nav_run,      accelerator="Ctrl+F5")
    run_menu.add_separator()
    run_menu.add_radiobutton(label="  \u2192 Output",   variable=app._run_target_var, value="output")
    run_menu.add_radiobutton(label="  \u2192 Terminal", variable=app._run_target_var, value="terminal")
    run_menu.add_separator()
    run_menu.add_command(label="Run Line",      command=app.run_line)
    run_menu.add_command(label="Run Selection", command=app.run_selection)
    run_menu.add_separator()
    run_menu.add_command(label="Stop",          command=app.run_stop,      accelerator="Shift+F5")
    run_menu.add_command(label="Clear Output",  command=app.run_clear)
    menubar.add_cascade(label="Run", menu=run_menu)

    # ── Designer ──────────────────────────────────────────────────────────────
    designer_menu = Menu(menubar, tearoff=0)
    designer_menu.add_command(label="New Form...",
                              command=app.designer_new_form)
    designer_menu.add_command(label="Open Form...",
                              command=app.designer_open_form)
    designer_menu.add_command(label="Save Form",
                              command=app.designer_save_form,
                              state="disabled")
    designer_menu.add_command(label="Close Form",
                              command=app.designer_close_form)
    designer_menu.add_separator()
    designer_menu.add_command(label="Generate Code",
                              command=app.designer_generate_code,
                              accelerator="Ctrl+Shift+G",
                              state="disabled")
    app._designer_menu = designer_menu
    menubar.add_cascade(label="Designer", menu=designer_menu)

    # ── Help ─────────────────────────────────────────────────────────────────
    help_menu = Menu(menubar, tearoff=0)
    help_menu.add_command(
        label="Learning Mode",
        command=app.view_learning_mode,
        accelerator="F1",
    )
    help_menu.add_command(
        label="Ask AI",
        command=app.view_ai_chat,
        accelerator="F2",
    )
    help_menu.add_command(
        label="Package Manager",
        command=app.view_package_manager,
        accelerator="F3",
    )
    help_menu.add_separator()
    help_menu.add_command(
        label="Command Palette...",
        command=app.open_command_palette,
        accelerator="Ctrl+Shift+P",
    )
    help_menu.add_separator()
    help_menu.add_command(label="About", command=app.help_about)
    menubar.add_cascade(label="Help", menu=help_menu)

    app.configure(menu=menubar)
    return menubar
