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
        self._symbol_ranges: list[tuple[str, str, int, int]] = []
        self._locals: dict[int, list[tuple[str, str, int]]] = {}  # start_line → [(tag, name, lineno)]
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
        self.tree.tag_configure("local",    foreground="#abb2bf")  # soft grey

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
        self._symbol_ranges = []
        self._locals = {}

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

    @staticmethod
    def _local_vars(func_node) -> list[tuple[str, str, int]]:
        """Return (tag, name, lineno) for symbols in the immediate body of *func_node*.

        Covers: local assignments, annotated assignments, for-loop targets,
        with-statement targets, and nested function/class definitions.
        Only the direct body is scanned — nested function bodies are skipped.
        """
        # Collect param names so we don't re-list them as locals
        param_names: set[str] = set()
        for arg in (
            func_node.args.posonlyargs
            + func_node.args.args
            + func_node.args.kwonlyargs
        ):
            param_names.add(arg.arg)
        if func_node.args.vararg:
            param_names.add(func_node.args.vararg.arg)
        if func_node.args.kwarg:
            param_names.add(func_node.args.kwarg.arg)

        seen: set[str] = set()
        results: list[tuple[str, str, int]] = []

        def _add(name: str, lineno: int, tag: str = "local") -> None:
            if name not in seen and name not in param_names:
                seen.add(name)
                results.append((tag, name, lineno))

        for stmt in func_node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async " if isinstance(stmt, ast.AsyncFunctionDef) else ""
                seen.add(stmt.name)
                results.append(("nested_fn", prefix + stmt.name, stmt.lineno))
            elif isinstance(stmt, ast.ClassDef):
                seen.add(stmt.name)
                results.append(("nested_class", stmt.name, stmt.lineno))
            elif isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        _add(t.id, stmt.lineno)
                    elif isinstance(t, ast.Tuple):
                        for elt in t.elts:
                            if isinstance(elt, ast.Name):
                                _add(elt.id, stmt.lineno)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                _add(stmt.target.id, stmt.lineno)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                if isinstance(stmt.target, ast.Name):
                    _add(stmt.target.id, stmt.lineno)
                elif isinstance(stmt.target, ast.Tuple):
                    for elt in stmt.target.elts:
                        if isinstance(elt, ast.Name):
                            _add(elt.id, stmt.lineno)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                        _add(item.optional_vars.id, stmt.lineno)

        return results

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh(self, code: str) -> None:
        self._after_id = None
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return  # Keep existing content until the code is valid again

        self.clear()
        ranges: list[tuple[str, str, int, int]] = []

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
                c_end = getattr(node, "end_lineno", node.lineno + 500)
                ranges.append(("class", node.name, node.lineno, c_end))
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
                        m_end = getattr(child, "end_lineno", child.lineno + 100)
                        ranges.append(("method", prefix + child.name, child.lineno, m_end))
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
                        locals_ = self._local_vars(child)
                        self._locals[child.lineno] = locals_
                        for ltag, lname, lline in locals_:
                            icon = "◈" if ltag in ("nested_fn", "nested_class") else "◦"
                            tv_tag = "method" if ltag == "nested_fn" else (
                                "class" if ltag == "nested_class" else "local"
                            )
                            self.tree.insert(method_node, "end",
                                             text=f"{icon}  {lname}",
                                             values=(lline,),
                                             tags=(tv_tag,))

            # ── Top-level function ────────────────────────────────────────────
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                f_end = getattr(node, "end_lineno", node.lineno + 100)
                ranges.append(("function", prefix + node.name, node.lineno, f_end))
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
                locals_ = self._local_vars(node)
                self._locals[node.lineno] = locals_
                for ltag, lname, lline in locals_:
                    icon = "◈" if ltag in ("nested_fn", "nested_class") else "◦"
                    tv_tag = "function" if ltag == "nested_fn" else (
                        "class" if ltag == "nested_class" else "local"
                    )
                    self.tree.insert(func_node, "end",
                                     text=f"{icon}  {lname}",
                                     values=(lline,),
                                     tags=(tv_tag,))

        self._symbol_ranges = ranges

    def get_symbols(self) -> list[tuple[str, int]]:
        """Return a flat list of (display_label, lineno) for all symbols in the tree."""
        results = []
        def _walk(parent):
            for iid in self.tree.get_children(parent):
                item = self.tree.item(iid)
                text = item["text"].strip()
                values = item["values"]
                tags = item["tags"]
                # Only include top-level items (classes, functions, vars) — skip params/attrs
                if tags and tags[0] in ("class", "function", "method", "var"):
                    if values:
                        results.append((text, int(values[0])))
                _walk(iid)
        _walk("")
        return results

    def get_scope_at(self, lineno: int) -> list[tuple[str, str, int]]:
        """Return the enclosing scope chain (outermost→innermost) for *lineno*.

        Each entry is (tag, name, start_line).  Only classes, methods and
        functions are included; variables are not scopes.
        """
        chain = [
            (tag, name, start)
            for tag, name, start, end in self._symbol_ranges
            if start <= lineno <= end
        ]
        chain.sort(key=lambda x: x[2])
        return chain

    def get_module_symbols(self) -> list[tuple[str, str, int]]:
        """Return all module-level classes and functions as (tag, name, lineno)."""
        return [
            (tag, name, start)
            for tag, name, start, _end in self._symbol_ranges
            if tag in ("class", "function")
        ]

    def get_class_methods(self, class_start: int) -> list[tuple[str, str, int]]:
        """Return methods of the class whose start line is *class_start*."""
        entry = next(
            (r for r in self._symbol_ranges if r[0] == "class" and r[2] == class_start),
            None,
        )
        if entry is None:
            return []
        _, _, c_start, c_end = entry
        return [
            (tag, name, start)
            for tag, name, start, _end in self._symbol_ranges
            if tag == "method" and c_start <= start <= c_end
        ]

    def get_local_symbols(self, func_start: int) -> list[tuple[str, str, int]]:
        """Return local symbols inside the function/method that starts at *func_start*."""
        return self._locals.get(func_start, [])

    def _on_select(self, _) -> None:
        selected = self.tree.selection()
        if selected and self._on_navigate:
            values = self.tree.item(selected[0], "values")
            if values:
                self._on_navigate(int(values[0]))
