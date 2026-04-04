from __future__ import annotations

import ast
from tkinter import ttk
from typing import Callable, Optional


class OutlinePanel(ttk.Frame):
    """Treeview panel showing classes and functions parsed from the current file.

    Refreshes 500 ms after the last edit (debounced).
    Clicking a symbol navigates the editor to that line.
    """

    def __init__(
        self,
        master,
        on_navigate: Optional[Callable[[int], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._on_navigate = on_navigate
        self._after_id: Optional[str] = None
        self._build_ui()

    def _build_ui(self) -> None:
        # Register a custom style so we can theme the treeview independently
        style = ttk.Style()
        style.configure("Outline.TFrame",   background="#272822")
        style.configure("Outline.TLabel",   background="#272822", foreground="#75715e")
        style.configure(
            "Outline.Treeview",
            background="#272822",
            foreground="#f8f8f2",
            fieldbackground="#272822",
            borderwidth=0,
            rowheight=22,
        )
        style.map(
            "Outline.Treeview",
            background=[("selected", "#3e3d32")],
            foreground=[("selected", "#f8f8f2")],
        )

        self.configure(style="Outline.TFrame")

        frame = ttk.Frame(self, style="Outline.TFrame")
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(frame, show="tree", selectmode="browse", style="Outline.Treeview")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nswe")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Symbol type colours (readable on dark background)
        self.tree.tag_configure("class",    foreground="#8be9fd")  # cyan
        self.tree.tag_configure("method",   foreground="#50fa7b")  # green
        self.tree.tag_configure("function", foreground="#ffb86c")  # orange
        self.tree.tag_configure("param",    foreground="#bd93f9")  # purple
        self.tree.tag_configure("attr",     foreground="#ff79c6")  # pink
        self.tree.tag_configure("var",      foreground="#f1fa8c")  # yellow

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def apply_theme(self, bg: str, fg: str, select_bg: str) -> None:
        """Update outline colours to match the active editor theme."""
        style = ttk.Style()
        style.configure("Outline.TFrame",    background=bg)
        style.configure("Outline.TLabel",    background=bg)
        style.configure(
            "Outline.Treeview",
            background=bg,
            foreground=fg,
            fieldbackground=bg,
        )
        style.map(
            "Outline.Treeview",
            background=[("selected", select_bg)],
            foreground=[("selected", fg)],
        )
        self.configure(style="Outline.TFrame")

    # ── Public API ────────────────────────────────────────────────────────────

    def schedule_refresh(self, code: str) -> None:
        """Call this on every keystroke; the actual parse runs 500 ms later."""
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(500, self._refresh, code)

    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())

    # ── Internals ─────────────────────────────────────────────────────────────

    # ── AST helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _params(func_node) -> list[tuple[str, int]]:
        """Return (name, lineno) for every parameter of a function."""
        args = []
        for arg in func_node.args.posonlyargs + func_node.args.args:
            args.append((arg.arg, arg.lineno if hasattr(arg, "lineno") else func_node.lineno))
        if func_node.args.vararg:
            v = func_node.args.vararg
            args.append((f"*{v.arg}", v.lineno if hasattr(v, "lineno") else func_node.lineno))
        for arg in func_node.args.kwonlyargs:
            args.append((arg.arg, arg.lineno if hasattr(arg, "lineno") else func_node.lineno))
        if func_node.args.kwarg:
            k = func_node.args.kwarg
            args.append((f"**{k.arg}", k.lineno if hasattr(k, "lineno") else func_node.lineno))
        # drop bare 'self' / 'cls'
        return [(n, l) for n, l in args if n not in ("self", "cls")]

    @staticmethod
    def _instance_attrs(func_node) -> list[tuple[str, int]]:
        """Return (name, lineno) for each unique self.xxx assignment in *func_node*."""
        seen: dict[str, int] = {}
        for node in ast.walk(func_node):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if (
                        isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "self"
                        and t.attr not in seen
                    ):
                        seen[t.attr] = node.lineno
        return list(seen.items())

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh(self, code: str) -> None:
        self._after_id = None
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return  # Keep existing content until the code is valid again

        self.clear()

        for node in ast.iter_child_nodes(tree):

            # ── Module-level variable / constant ─────────────────────────────
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        self.tree.insert("", "end",
                                         text=f"◦  {t.id}",
                                         values=(node.lineno,),
                                         tags=("var",))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                self.tree.insert("", "end",
                                 text=f"◦  {node.target.id}",
                                 values=(node.lineno,),
                                 tags=("var",))

            # ── Class ─────────────────────────────────────────────────────────
            elif isinstance(node, ast.ClassDef):
                class_node = self.tree.insert(
                    "", "end",
                    text=f"◉  {node.name}",
                    values=(node.lineno,),
                    tags=("class",),
                    open=True,
                )
                # Methods — params then instance attrs, all nested under the method
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        prefix = "async " if isinstance(child, ast.AsyncFunctionDef) else ""
                        method_node = self.tree.insert(
                            class_node, "end",
                            text=f"◈  {prefix}{child.name}",
                            values=(child.lineno,),
                            tags=("method",),
                        )
                        for pname, pline in self._params(child):
                            self.tree.insert(method_node, "end",
                                             text=f"◦  {pname}",
                                             values=(pline,),
                                             tags=("param",))
                        for aname, aline in self._instance_attrs(child):
                            self.tree.insert(method_node, "end",
                                             text=f"◦  {aname}",
                                             values=(aline,),
                                             tags=("attr",))

            # ── Top-level function ────────────────────────────────────────────
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                func_node = self.tree.insert(
                    "", "end",
                    text=f"◈  {prefix}{node.name}",
                    values=(node.lineno,),
                    tags=("function",),
                    open=True,
                )
                for pname, pline in self._params(node):
                    self.tree.insert(func_node, "end",
                                     text=f"◦  {pname}",
                                     values=(pline,),
                                     tags=("param",))

    def _on_select(self, _) -> None:
        selected = self.tree.selection()
        if selected and self._on_navigate:
            values = self.tree.item(selected[0], "values")
            if values:
                self._on_navigate(int(values[0]))
