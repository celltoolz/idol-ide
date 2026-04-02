"""ReferencesPanel — shows all occurrences of a word in the current file."""
from __future__ import annotations

import re
from tkinter import Frame, Label, ttk
from typing import Callable


class ReferencesPanel(ttk.Frame):
    """Collapsible panel that lists every occurrence of a word.

    Lives in the sidebar between Outline and Explorer.
    Call show(word, codeview) to populate, hide() to dismiss.
    Clicking a result navigates the editor to that line.
    """

    def __init__(self, parent, on_navigate: Callable[[int], None]) -> None:
        super().__init__(parent, style="Sidebar.TFrame")
        self._on_navigate = on_navigate
        self._bg  = "#1e1e1e"
        self._fg  = "#cccccc"
        self._sel = "#094771"
        self._build_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def show(self, word: str, codeview) -> None:
        """Populate the list with every occurrence of *word* in *codeview*."""
        self._tree.delete(*self._tree.get_children())
        self._word_lbl.config(text=f'References: "{word}"')

        text = codeview.get("1.0", "end-1c")
        pattern = re.compile(r"\b" + re.escape(word) + r"\b")
        results = []
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                col = m.start()
                preview = line.strip()
                if len(preview) > 60:
                    preview = preview[:60] + "…"
                results.append((lineno, col, preview))

        for lineno, col, preview in results:
            self._tree.insert("", "end",
                              text=f"  {lineno}:{col+1}  {preview}",
                              values=(lineno,),
                              tags=("result",))

        count = len(results)
        self._count_lbl.config(
            text=f"{count} reference{'s' if count != 1 else ''}"
        )
        self._tree.tag_configure("result", foreground=self._fg)

    def apply_theme(self, bg: str, fg: str, select_bg: str) -> None:
        self._bg  = bg
        self._fg  = fg
        self._sel = select_bg
        style = ttk.Style()
        style.configure("Refs.Treeview",
                        background=bg, foreground=fg,
                        fieldbackground=bg, borderwidth=0, rowheight=20)
        style.map("Refs.Treeview",
                  background=[("selected", select_bg)],
                  foreground=[("selected", fg)])
        self._header.config(bg=bg)
        self._word_lbl.config(bg=bg, fg="#858585")
        self._count_lbl.config(bg=bg, fg="#858585")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._header = Frame(self, bg=self._bg)
        self._header.pack(fill="x", side="top")

        self._word_lbl = Label(
            self._header, text="References",
            bg=self._bg, fg="#858585",
            font=("Segoe UI", 8), anchor="w", padx=6,
        )
        self._word_lbl.pack(side="left", fill="x", expand=True)

        self._count_lbl = Label(
            self._header, text="",
            bg=self._bg, fg="#858585",
            font=("Segoe UI", 8), padx=6,
        )
        self._count_lbl.pack(side="right")

        frame = ttk.Frame(self, style="Sidebar.TFrame")
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            frame, show="tree", selectmode="browse", style="Refs.Treeview"
        )
        vs = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vs.set)
        self._tree.grid(row=0, column=0, sticky="nswe")
        vs.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<ButtonRelease-1>", self._on_click)
        self._tree.bind("<Return>",          self._on_enter)

    def _on_click(self, _) -> None:
        item = self._tree.focus()
        if item:
            lineno = self._tree.item(item, "values")
            if lineno:
                self._on_navigate(int(lineno[0]))

    def _on_enter(self, _) -> None:
        self._on_click(None)
