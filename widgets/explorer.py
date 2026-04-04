"""FileExplorer — a dark-themed file system tree for the sidebar."""
from __future__ import annotations

import os
from pathlib import Path
from tkinter import Menu, ttk
from typing import Callable


class FileExplorer(ttk.Frame):
    """Lazy-loading file system tree. Double-click or Enter opens a file."""

    _LOADING = "__loading__"

    def __init__(self, parent, on_open_file: Callable[[str], None]) -> None:
        super().__init__(parent, style="Explorer.TFrame")
        self._on_open = on_open_file
        self._root: Path | None = None

        self._tree = ttk.Treeview(
            self,
            show="tree",
            selectmode="browse",
            style="FileTree.Treeview",
        )
        vs = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vs.set)

        self._tree.grid(row=0, column=0, sticky="nswe")
        vs.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._tree.tag_configure("folder",     foreground="#8be9fd")
        self._tree.tag_configure("file",       foreground="#f8f8f2")
        self._tree.tag_configure("parent_dir", foreground="#6272a4")
        # Git status tags
        self._tree.tag_configure("git_M", foreground="#e2c08d")
        self._tree.tag_configure("git_A", foreground="#73c991")
        self._tree.tag_configure("git_U", foreground="#cccccc")
        self._tree.tag_configure("git_D", foreground="#f14c4c")

        self._tree.bind("<<TreeviewOpen>>",    self._on_node_expand)
        self._tree.bind("<Double-Button-1>",   self._on_double_click)
        self._tree.bind("<Return>",            self._on_enter)
        self._tree.bind("<Button-3>",          self._on_right_click)

        self._menu = Menu(self._tree, tearoff=0)
        self._menu.add_command(label="Set as Root Directory", command=self._set_selected_as_root)
        self._menu.add_command(label="Open File",             command=self._open_selected)
        self._menu_item: str = ""

    # ── Public API ────────────────────────────────────────────────────────────

    def set_root(self, path: str) -> None:
        """Populate the tree starting at *path* (a directory)."""
        root = Path(path)
        if not root.is_dir():
            root = root.parent
        self._root = root
        self._tree.delete(*self._tree.get_children())
        # ".." entry to navigate up — hidden at the filesystem root
        if root.parent != root:
            self._tree.insert(
                "", 0,
                text="  ..",
                values=[str(root.parent)],
                tags=("parent_dir",),
            )
        self._populate("", root)

    def apply_git_status(self, status_map: dict[str, str]) -> None:
        """Recolour and badge visible tree items to reflect git status.

        *status_map* maps normcase absolute path → 'M' | 'A' | 'U' | 'D'.
        Uses both tag colours (where the theme supports it) and a text suffix
        so the status is always visible regardless of platform/theme.
        """
        def _update(item: str) -> None:
            item_tags = self._tree.item(item, "tags")
            if "parent_dir" in item_tags:
                for child in self._tree.get_children(item):
                    _update(child)
                return
            values = self._tree.item(item, "values")
            if values and values[0] != self._LOADING:
                norm   = os.path.normcase(str(values[0]))
                status = status_map.get(norm)
                # Tag colours (put git tag first for priority)
                base_tags = [t for t in item_tags if not t.startswith("git_")]
                new_tags  = ([f"git_{status}"] + base_tags) if status else base_tags
                self._tree.item(item, tags=new_tags)
                # Text badge — works on every platform/theme
                name     = Path(values[0]).name
                prefix   = "  "
                new_text = f"{prefix}{name} {status}" if status else f"{prefix}{name}"
                self._tree.item(item, text=new_text)
            for child in self._tree.get_children(item):
                _update(child)

        for root_item in self._tree.get_children():
            _update(root_item)

    def apply_theme(self, bg: str, fg: str, select_bg: str) -> None:
        style = ttk.Style()
        # No global `foreground` here — item colours come from per-item tags
        # so that git status tags can override without being blocked by the style.
        style.configure("FileTree.Treeview",
                         background=bg, fieldbackground=bg, borderwidth=0)
        style.configure("FileTree.Treeview.Item", padding=(2, 1))
        style.map("FileTree.Treeview",
                  background=[("selected", select_bg)],
                  foreground=[("selected", fg)])
        style.configure("Explorer.TFrame", background=bg)
        # Ensure base tag colours reflect the current theme
        self._tree.tag_configure("file",       foreground=fg)
        self._tree.tag_configure("parent_dir", foreground="#6272a4")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _populate(self, parent_id: str, directory: Path) -> None:
        """Add immediate children of *directory* to the tree."""
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except PermissionError:
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                node = self._tree.insert(
                    parent_id, "end",
                    text=f"  {entry.name}",
                    values=[str(entry)],
                    tags=("folder",),
                    open=False,
                )
                # Dummy child makes the expand arrow appear
                self._tree.insert(node, "end", values=[self._LOADING])
            else:
                self._tree.insert(
                    parent_id, "end",
                    text=f"  {entry.name}",
                    values=[str(entry)],
                    tags=("file",),
                )

    def _on_node_expand(self, _) -> None:
        """Lazy-load a directory's contents the first time it is expanded."""
        node = self._tree.focus()
        children = self._tree.get_children(node)
        if len(children) == 1:
            placeholder = children[0]
            if self._tree.item(placeholder, "values") == (self._LOADING,):
                self._tree.delete(placeholder)
                path = Path(self._tree.item(node, "values")[0])
                self._populate(node, path)

    def _on_double_click(self, event) -> None:
        item = self._tree.identify_row(event.y)
        if not item:
            return
        tags = self._tree.item(item, "tags")
        values = self._tree.item(item, "values")
        # Let the Treeview's built-in behaviour expand/collapse regular folders.
        # Only intercept for files (open in editor) and ".." (navigate up).
        if "parent_dir" in tags:
            self._activate(item)
        elif values and values[0] != self._LOADING:
            path = Path(values[0])
            if path.is_file():
                self._activate(item)

    def _on_enter(self, _) -> None:
        item = self._tree.focus()
        if item:
            self._activate(item)

    def _on_right_click(self, event) -> None:
        item = self._tree.identify_row(event.y)
        if not item:
            return
        self._tree.selection_set(item)
        self._menu_item = item
        tags = self._tree.item(item, "tags")
        values = self._tree.item(item, "values")
        is_file = values and values[0] != self._LOADING and Path(values[0]).is_file()
        # Show/hide entries based on what was right-clicked
        self._menu.entryconfigure("Set as Root Directory",
                                  state="normal" if not is_file else "disabled")
        self._menu.entryconfigure("Open File",
                                  state="normal" if is_file else "disabled")
        self._menu.tk_popup(event.x_root, event.y_root)

    def _set_selected_as_root(self) -> None:
        if not self._menu_item:
            return
        values = self._tree.item(self._menu_item, "values")
        if values:
            path = Path(values[0])
            if not path.is_dir():
                path = path.parent
            self.set_root(str(path))

    def _open_selected(self) -> None:
        if self._menu_item:
            self._activate(self._menu_item)

    def _activate(self, item: str) -> None:
        values = self._tree.item(item, "values")
        if not values or values[0] == self._LOADING:
            return
        path = Path(values[0])
        if path.is_file():
            self._on_open(str(path))
        elif "parent_dir" in self._tree.item(item, "tags"):
            # ".." — navigate up to the parent directory
            self.set_root(str(path))
        else:
            # Any other folder — expand/collapse in place
            self._tree.item(item, open=not self._tree.item(item, "open"))
