"""FileExplorer — a dark-themed file system tree for the sidebar."""
from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import Menu, simpledialog, messagebox, ttk
from typing import Callable

from utils import bind_right_click


class FileExplorer(ttk.Frame):
    """Lazy-loading file system tree. Double-click or Enter opens a file."""

    _LOADING = "__loading__"

    def __init__(self, parent, on_open_file: Callable[[str], None],
                 on_file_move: Callable[[str, str], bool] | None = None,
                 on_root_change: Callable[[str], None] | None = None) -> None:
        super().__init__(parent, style="Explorer.TFrame")
        self._on_open = on_open_file
        self._on_file_move = on_file_move  # (old_path, new_path) -> bool (False = cancel)
        self._on_root_change = on_root_change
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
        self._tree.bind("<Delete>",            self._on_delete_key)
        bind_right_click(self._tree, self._on_right_click)

        # Drag/drop state
        self._drag_item:    str  = ""
        self._drag_start_y: int  = 0
        self._drag_active:  bool = False
        # Indicator line — child of self (Frame), placed over the treeview
        self._drag_line = tk.Frame(self, height=2, bg="#569cd6")
        self._tree.bind("<ButtonPress-1>",   self._on_drag_start)
        self._tree.bind("<B1-Motion>",       self._on_drag_motion)
        self._tree.bind("<ButtonRelease-1>", self._on_drag_release)

        self._menu = Menu(self._tree, tearoff=0)
        self._menu.add_command(label="Open File",             command=self._open_selected)
        self._menu.add_command(label="Set as Root Directory", command=self._set_selected_as_root)
        self._menu.add_separator()
        self._menu.add_command(label="New File",              command=self._new_file)
        self._menu.add_command(label="New Folder",            command=self._new_folder)
        self._menu.add_separator()
        self._menu.add_command(label="Rename",                command=self._rename_selected)
        self._menu.add_command(label="Delete",                command=self._delete_selected)
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
        if self._on_root_change:
            self._on_root_change(str(root))

    def apply_git_status(self, status_map: dict[str, str]) -> None:
        """Recolour and badge visible tree items to reflect git status.

        *status_map* maps absolute path → 'M' | 'A' | 'U' | 'D'.
        Uses both tag colours (where the theme supports it) and a text suffix
        so the status is always visible regardless of platform/theme.
        """
        norm_map = {os.path.normcase(k): v for k, v in status_map.items()}

        def _update(item: str) -> None:
            item_tags = self._tree.item(item, "tags")
            if "parent_dir" in item_tags:
                for child in self._tree.get_children(item):
                    _update(child)
                return
            values = self._tree.item(item, "values")
            if values and values[0] != self._LOADING:
                norm   = os.path.normcase(str(values[0]))
                status = norm_map.get(norm)
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
        # Allow right-click on blank space (e.g. empty directory)
        if item:
            self._tree.selection_set(item)
        self._menu_item = item
        values    = self._tree.item(item, "values") if item else []
        is_parent = bool(item and "parent_dir" in self._tree.item(item, "tags"))
        is_file   = bool(values and values[0] != self._LOADING
                         and Path(values[0]).is_file())
        is_item   = bool(values and values[0] != self._LOADING and not is_parent)
        self._menu.entryconfigure("Open File",
                                  state="normal" if is_file else "disabled")
        self._menu.entryconfigure("Set as Root Directory",
                                  state="normal" if not is_file and not is_parent and item else "disabled")
        self._menu.entryconfigure("Rename",
                                  state="normal" if is_item else "disabled")
        self._menu.entryconfigure("Delete",
                                  state="normal" if is_item else "disabled")
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

    def _rename_selected(self) -> None:
        if not self._menu_item:
            return
        values = self._tree.item(self._menu_item, "values")
        if not values or values[0] == self._LOADING:
            return
        old_path = Path(values[0])
        new_name = simpledialog.askstring(
            "Rename", f"Rename '{old_path.name}' to:",
            initialvalue=old_path.name,
            parent=self._tree,
        )
        if not new_name or new_name == old_path.name:
            return
        new_path = old_path.parent / new_name
        try:
            old_path.rename(new_path)
        except Exception as e:
            messagebox.showerror("Rename failed", str(e), parent=self._tree)
            return
        # Refresh the parent folder in the tree
        parent_item = self._tree.parent(self._menu_item)
        self._refresh_node(parent_item, old_path.parent)

    def _on_delete_key(self, event=None) -> None:
        """Delete key handler — sets _menu_item from tree selection first."""
        sel = self._tree.selection()
        if sel:
            self._menu_item = sel[0]
        self._delete_selected()

    def _delete_selected(self) -> None:
        if not self._menu_item:
            return
        values = self._tree.item(self._menu_item, "values")
        if not values or values[0] == self._LOADING:
            return
        path = Path(values[0])
        kind = "folder" if path.is_dir() else "file"
        if not messagebox.askyesno(
            "Delete", f"Delete {kind} '{path.name}'? This cannot be undone.",
            parent=self._tree,
        ):
            return
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except Exception as e:
            messagebox.showerror("Delete failed", str(e), parent=self._tree)
            return
        self._tree.delete(self._menu_item)
        self._menu_item = ""

    def _new_file(self) -> None:
        parent_item, parent_dir = self._new_item_context()
        if parent_dir is None:
            return
        self._start_inline_entry(parent_item, parent_dir, is_folder=False)

    def _new_folder(self) -> None:
        parent_item, parent_dir = self._new_item_context()
        if parent_dir is None:
            return
        self._start_inline_entry(parent_item, parent_dir, is_folder=True)

    def _start_inline_entry(self, parent_item: str, parent_dir: Path, is_folder: bool) -> None:
        """Show an inline Entry overlaid on a treeview placeholder item."""
        # If the parent folder isn't open yet, expand it and load its children.
        if parent_item and not self._tree.item(parent_item, "open"):
            self._tree.item(parent_item, open=True)
            # Fire the expand handler manually to populate lazy children
            class _FakeEvent:
                pass
            e = _FakeEvent()
            e.widget = self._tree  # type: ignore[attr-defined]
            self._on_node_expand(e)
            self._tree.update_idletasks()

        tmp_id = self._tree.insert(
            parent_item, "end",
            text="  📁 " if is_folder else "  ",
            tags=("_new_placeholder",),
        )
        self._tree.see(tmp_id)

        _attempts = [0]

        def _place():
            self._tree.update_idletasks()
            bbox = self._tree.bbox(tmp_id, "#0")
            if not bbox:
                _attempts[0] += 1
                if _attempts[0] < 5:
                    # Retry up to 5 times at 50ms intervals
                    self._tree.after(50, _place)
                else:
                    # Give up and fall back to dialog
                    try:
                        self._tree.delete(tmp_id)
                    except Exception:
                        pass
                    kind = "Folder" if is_folder else "File"
                    name = simpledialog.askstring(f"New {kind}", "Name:", parent=self._tree)
                    if name:
                        self._commit_new_item(parent_item, parent_dir, name, is_folder)
                return

            x, y, w, h = bbox
            entry_w = max(w, self._tree.winfo_width() - x - 4)

            entry = tk.Entry(
                self._tree,
                bg="#2d2d30", fg="#f8f8f2",
                insertbackground="#f8f8f2",
                relief="flat",
                font=("Segoe UI", 9),
                highlightthickness=1,
                highlightcolor="#007acc",
                highlightbackground="#007acc",
            )
            entry.place(x=x, y=y, width=entry_w, height=h)
            entry.focus_set()

            _done = [False]

            def _commit(event=None):
                if _done[0]:
                    return
                _done[0] = True
                name = entry.get().strip()
                entry.destroy()
                try:
                    self._tree.delete(tmp_id)
                except Exception:
                    pass
                if name:
                    self._commit_new_item(parent_item, parent_dir, name, is_folder)

            def _cancel(event=None):
                if _done[0]:
                    return
                _done[0] = True
                entry.destroy()
                try:
                    self._tree.delete(tmp_id)
                except Exception:
                    pass

            entry.bind("<Return>", _commit)
            entry.bind("<Escape>", _cancel)
            entry.bind("<FocusOut>", _cancel)

        self._tree.after(30, _place)

    def _commit_new_item(self, parent_item: str, parent_dir: Path, name: str, is_folder: bool) -> None:
        """Create the file/folder after inline name entry confirms."""
        new_path = parent_dir / name
        kind = "Folder" if is_folder else "File"
        if new_path.exists():
            messagebox.showwarning(
                f"{kind} exists", f"'{name}' already exists in this folder.",
                parent=self._tree,
            )
            return
        try:
            if is_folder:
                new_path.mkdir(parents=False)
            else:
                new_path.touch()
        except Exception as e:
            messagebox.showerror(f"New {kind} failed", str(e), parent=self._tree)
            return
        self._soft_refresh_node(parent_item, parent_dir)
        if not is_folder:
            self._on_open(str(new_path))

    def _new_item_context(self) -> tuple[str, Path | None]:
        """Return (parent_tree_item, parent_dir) for a new file/folder action."""
        if not self._menu_item:
            # Nothing selected — create in root
            return ("", self._root)
        values = self._tree.item(self._menu_item, "values")
        tags   = self._tree.item(self._menu_item, "tags")
        if not values or values[0] == self._LOADING or "parent_dir" in tags:
            return ("", self._root)
        path = Path(values[0])
        if path.is_dir():
            return (self._menu_item, path)
        # File selected — create alongside it
        return (self._tree.parent(self._menu_item), path.parent)

    def _refresh_node(self, parent_item: str, directory: Path) -> None:
        """Remove and re-populate a node's children."""
        for child in self._tree.get_children(parent_item):
            self._tree.delete(child)
        if parent_item == "":
            # Root level — re-add the .. entry if needed
            if self._root and self._root.parent != self._root:
                self._tree.insert(
                    "", 0, text="  ..",
                    values=[str(self._root.parent)],
                    tags=("parent_dir",),
                )
            self._populate("", directory)
        else:
            self._populate(parent_item, directory)

    def soft_refresh(self) -> None:
        """Refresh the visible tree without resetting expanded/collapsed state.

        Adds new files/dirs that appeared on disk, removes items that no longer
        exist, and leaves everything else (expansion, selection) untouched.
        Collapsed folders are skipped — they'll lazy-load correctly on open.
        """
        if self._root is None:
            return
        self._soft_refresh_node("", self._root)

    def _soft_refresh_node(self, parent_item: str, directory: Path) -> None:
        """Recursively sync one level of the tree with the filesystem."""
        try:
            entries = sorted(directory.iterdir(),
                             key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return

        visible = {str(p) for p in entries if not p.name.startswith(".")}

        # Remove items that no longer exist on disk
        for child in list(self._tree.get_children(parent_item)):
            vals = self._tree.item(child, "values")
            if not vals or vals[0] == self._LOADING:
                continue
            if vals[0] not in visible and self._tree.item(child, "text").strip() != "..":
                self._tree.delete(child)

        # Build a set of paths already in the tree at this level
        existing = {}
        for child in self._tree.get_children(parent_item):
            vals = self._tree.item(child, "values")
            if vals and vals[0] != self._LOADING:
                existing[vals[0]] = child

        # Add new entries that aren't in the tree yet
        for entry in entries:
            if entry.name.startswith("."):
                continue
            key = str(entry)
            if key in existing:
                # Already present — if it's an expanded folder, recurse into it
                if entry.is_dir():
                    node = existing[key]
                    children = self._tree.get_children(node)
                    is_expanded = self._tree.item(node, "open")
                    has_real_children = (
                        children and
                        self._tree.item(children[0], "values") != (self._LOADING,)
                    )
                    if is_expanded or has_real_children:
                        self._soft_refresh_node(node, entry)
            else:
                # New entry — insert it
                if entry.is_dir():
                    node = self._tree.insert(
                        parent_item, "end",
                        text=f"  {entry.name}",
                        values=[key],
                        tags=("folder",),
                        open=False,
                    )
                    self._tree.insert(node, "end", values=[self._LOADING])
                else:
                    self._tree.insert(
                        parent_item, "end",
                        text=f"  {entry.name}",
                        values=[key],
                        tags=("file",),
                    )

    # ── Drag / drop ───────────────────────────────────────────────────────────

    _DRAG_THRESHOLD = 6  # pixels before drag activates

    def _on_drag_start(self, event) -> None:
        item = self._tree.identify_row(event.y)
        if not item:
            self._drag_item = ""
            return
        tags   = self._tree.item(item, "tags")
        values = self._tree.item(item, "values")
        if "parent_dir" in tags or not values or values[0] == self._LOADING:
            self._drag_item = ""
            return
        self._drag_item    = item
        self._drag_start_y = event.y
        self._drag_active  = False

    def _on_drag_motion(self, event) -> None:
        if not self._drag_item:
            return
        # Only activate drag after threshold to avoid false triggers on clicks
        if not self._drag_active:
            if abs(event.y - self._drag_start_y) < self._DRAG_THRESHOLD:
                return
            self._drag_active = True

        target = self._tree.identify_row(event.y)
        if target and target != self._drag_item:
            bbox = self._tree.bbox(target)
            if bbox:
                # bbox is relative to treeview; offset by treeview position in self
                tree_y = self._tree.winfo_y()
                y = tree_y + bbox[1] + bbox[3]
                self._drag_line.place(x=0, y=y, width=self.winfo_width(), height=2)
                self._drag_line.lift()
                return
        self._drag_line.place_forget()

    def _on_drag_release(self, event) -> None:
        self._drag_line.place_forget()
        if not self._drag_item or not self._drag_active:
            self._drag_item   = ""
            self._drag_active = False
            return

        src_values = self._tree.item(self._drag_item, "values")
        src_item   = self._drag_item
        self._drag_item   = ""
        self._drag_active = False

        if not src_values or src_values[0] == self._LOADING:
            return
        src_path = Path(src_values[0])

        target_item = self._tree.identify_row(event.y)
        if not target_item or target_item == src_item:
            return

        tgt_tags   = self._tree.item(target_item, "tags")
        # ".." is a navigation shortcut, not a valid drop target
        if "parent_dir" in tgt_tags:
            return
        tgt_values = self._tree.item(target_item, "values")
        if not tgt_values or tgt_values[0] == self._LOADING:
            return
        tgt_path = Path(tgt_values[0])

        dest_dir = tgt_path if tgt_path.is_dir() else tgt_path.parent
        dest_path = dest_dir / src_path.name

        if dest_path == src_path or dest_dir == src_path.parent:
            return

        if dest_path.exists():
            if not messagebox.askyesno(
                "Overwrite?",
                f"'{dest_path.name}' already exists in '{dest_dir.name}'. Overwrite?",
                parent=self._tree,
            ):
                return

        # Let the app check for unsaved changes and update open tabs
        if self._on_file_move and not self._on_file_move(str(src_path), str(dest_path)):
            return

        try:
            shutil.move(str(src_path), str(dest_path))
        except Exception as e:
            messagebox.showerror("Move failed", str(e), parent=self._tree)
            return

        src_parent_item = self._find_item(str(src_path.parent))
        dst_parent_item = self._find_item(str(dest_dir))

        def _is_parent_dir(item: str) -> bool:
            if not item:
                return False
            if not (item == "" or self._tree.exists(item)):
                return False
            return "parent_dir" in self._tree.item(item, "tags")

        if src_parent_item is not None and not _is_parent_dir(src_parent_item):
            if src_parent_item == "" or self._tree.exists(src_parent_item):
                self._refresh_node(src_parent_item, src_path.parent)
        if dst_parent_item is not None and dst_parent_item != src_parent_item:
            if not _is_parent_dir(dst_parent_item):
                if dst_parent_item == "" or self._tree.exists(dst_parent_item):
                    self._refresh_node(dst_parent_item, dest_dir)

    def _find_item(self, path_str: str) -> str | None:
        """Find the tree item whose value matches path_str."""
        def _search(parent: str) -> str | None:
            for item in self._tree.get_children(parent):
                values = self._tree.item(item, "values")
                if values and values[0] == path_str:
                    return item
                found = _search(item)
                if found:
                    return found
            return None
        # Check root level first (including "" parent)
        if self._root and str(self._root) == path_str:
            return ""
        return _search("")

    def _activate(self, item: str) -> None:
        values = self._tree.item(item, "values")
        if not values or values[0] == self._LOADING:
            return
        path = Path(values[0])
        if path.is_file():
            self._on_open(str(path))
        elif "parent_dir" in self._tree.item(item, "tags"):
            self.set_root(str(path))
        else:
            self._tree.item(item, open=not self._tree.item(item, "open"))
