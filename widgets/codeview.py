from __future__ import annotations

import inspect
from contextlib import suppress
from pathlib import Path
import tkinter as tk
from tkinter import BaseWidget, Event, Frame, Menu, Misc, TclError, Text, ttk
from tkinter.font import Font
from typing import Any, Callable, Type, Union

import pygments
import pygments.lexer
import pygments.lexers
import toml
from pyperclip import copy

from .linenums import TkLineNumbers
from .minimap import Minimap
from .sticky_scroll import StickyScroll
from utils.schemeparser import _parse_scheme

color_schemes_dir = Path(__file__).parent.parent / "colorschemes"

LexerType = Union[Type[pygments.lexer.Lexer], pygments.lexer.Lexer]


class Scrollbar(ttk.Scrollbar):
    def __init__(self, master: ttk.Frame, autohide: bool, *args, **kwargs) -> None:
        super().__init__(master, *args, **kwargs)
        self.autohide = autohide

    def set(self, low: float, high: float) -> None:
        if self.autohide:
            if float(low) <= 0.0 and float(high) >= 1.0:
                self.grid_remove()
            else:
                self.grid()
        super().set(low, high)


class CodeView(Text):
    _w: str
    builtin_color_schemes = [
        "ayu-dark",
        "ayu-light",
        "dracula",
        "mariana",
        "monokai",
        "material",
        "rrt",
        "test",
    ]

    def __init__(
        self,
        master: Misc | None = None,
        lexer: LexerType = pygments.lexers.TextLexer,
        color_scheme: dict[str, dict[str, str | int]] | str | None = None,
        tab_width: int = 4,
        linenums_theme: Callable[[], tuple[str, str]] | tuple[str, str] | None = None,
        autohide_scrollbar: bool = True,
        linenums_border: int = 0,
        default_context_menu: bool = False,
        **kwargs,
    ) -> None:
        # Plain tk.Frame so we can set bg directly — ttk.Frame ignores bg on Windows
        self._frame = Frame(master, bg="#000000")
        self._frame.grid_rowconfigure(0, weight=1)
        self._frame.grid_columnconfigure(1, weight=1)

        kwargs.setdefault("wrap", "none")
        kwargs.setdefault("font", ("Fira Mono", 10))

        super().__init__(self._frame, **kwargs)
        super().grid(row=0, column=1, sticky="nswe")

        self._line_numbers = TkLineNumbers(
            self._frame,
            self,
            justify=kwargs.get("justify", "left"),
            colors=linenums_theme,
            borderwidth=kwargs.get("borderwidth", linenums_border),
        )
        self._vs = Scrollbar(
            self._frame,
            autohide=autohide_scrollbar,
            orient="vertical",
            command=self.yview,
        )
        self._hs = Scrollbar(
            self._frame,
            autohide=autohide_scrollbar,
            orient="horizontal",
            command=self.xview,
        )

        self._line_numbers.grid(row=0, column=0, sticky="ns")
        self._vs.grid(row=0, column=2, sticky="ns")
        self._hs.grid(row=1, column=1, sticky="we")

        super().configure(
            yscrollcommand=self.vertical_scroll,
            xscrollcommand=self.horizontal_scroll,
            tabs=Font(font=kwargs["font"]).measure(" " * tab_width),
        )

        self._context_menu = None
        self._default_context_menu = default_context_menu
        if default_context_menu:
            self.context_menu

        contmand = "Command" if self._windowingsystem == "aqua" else "Control"
        super().bind(f"<{contmand}-c>", self._copy, add=True)
        super().bind(f"<{contmand}-v>", self._paste, add=True)
        super().bind(f"<{contmand}-a>", self._select_all, add=True)
        super().bind(f"<{contmand}-Shift-Z>", self.redo, add=True)
        super().bind("<<ContentChanged>>", self.scroll_line_update, add=True)
        super().bind("<Button-1>", self._line_numbers.redraw, add=True)
        super().bind("<Double-Button-1>", self._on_double_click, add=True)

        # _orig must be set before Minimap so the peer can use it
        self._orig = f"{self._w}_widget"
        self.tk.call("rename", self._w, self._orig)
        self.tk.createcommand(self._w, self._cmd_proxy)

        self._sticky = StickyScroll(self._frame, self, self._line_numbers)
        # Minimap.grid() also places its border widget in column 3;
        # the peer widget itself goes in column 4.
        self._minimap = Minimap(self._frame, self)
        self._minimap.grid()

        self._set_lexer(lexer)
        self.set_color_scheme(color_scheme)


    @property
    def context_menu(self) -> Menu:
        if self._context_menu is None:
            self._context_menu = self._create_context_menu()
        return self._context_menu

    def _create_context_menu(self) -> Menu:
        context_menu = Menu(self, tearoff=0)
        popup_cb = lambda e: context_menu.tk_popup(e.x_root + 5, e.y_root + 5)

        if self._windowingsystem == "aqua":
            super().bind("<Button-2>", popup_cb)
            super().bind("<Control-Button-1>", popup_cb)
        else:
            super().bind("<Button-3>", popup_cb)

        if self._default_context_menu:
            mod = "⌘" if self._windowingsystem == "aqua" else "Ctrl"
            context_menu.add_command(
                label="Undo",
                accelerator=f"{mod}+Z",
                command=lambda: self.event_generate("<<Undo>>"),
            )
            context_menu.add_command(
                label="Redo",
                accelerator=f"{mod}+Y",
                command=lambda: self.event_generate("<<Redo>>"),
            )
            context_menu.add_separator()
            context_menu.add_command(
                label="Cut",
                accelerator=f"{mod}+X",
                command=lambda: self.event_generate("<<Cut>>"),
            )
            context_menu.add_command(
                label="Copy", accelerator=f"{mod}+C", command=self._copy
            )
            context_menu.add_command(
                label="Paste", accelerator=f"{mod}+V", command=self._paste
            )
            context_menu.add_command(
                label="Select all", accelerator=f"{mod}+A", command=self._select_all
            )
        return context_menu

    def _on_double_click(self, event) -> str:
        """Select the word under the cursor, stopping at punctuation and whitespace."""
        idx = self.index(f"@{event.x},{event.y}")
        line, col = map(int, idx.split("."))
        line_text = self.get(f"{line}.0", f"{line}.end")
        if col >= len(line_text):
            return "break"
        # Expand left while char is a word character
        start = col
        while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] == "_"):
            start -= 1
        # Expand right while char is a word character
        end = col
        while end < len(line_text) and (line_text[end].isalnum() or line_text[end] == "_"):
            end += 1
        self.tag_remove("sel", "1.0", "end")
        self.tag_add("sel", f"{line}.{start}", f"{line}.{end}")
        self.mark_set("insert", f"{line}.{end}")
        return "break"

    def _select_all(self, *_) -> str:
        self.tag_add("sel", "1.0", "end")
        self.mark_set("insert", "end")
        return "break"

    def redo(self, event: Event | None = None) -> None:
        try:
            self.edit_redo()
        except TclError:
            pass

    def _paste(self, *_):
        insert = self.index(f"@0,0 + {self.cget('height') // 2} lines")
        with suppress(TclError):
            self.delete("sel.first", "sel.last")
            self.tag_remove("sel", "1.0", "end")
            self.insert("insert", self.clipboard_get())
        self.see(insert)
        return "break"

    def _copy(self, *_):
        text = self.get("sel.first", "sel.last")
        if not text:
            text = self.get("insert linestart", "insert lineend")
        copy(text)
        return "break"

    def _cmd_proxy(self, command: str, *args) -> Any:
        try:
            if command in {"insert", "delete", "replace"}:
                start_line = int(
                    str(self.tk.call(self._orig, "index", args[0])).split(".")[0]
                )
                end_line = start_line
                if len(args) == 3:
                    end_line = (
                        int(
                            str(self.tk.call(self._orig, "index", args[1])).split(".")[
                                0
                            ]
                        )
                        - 1
                    )
            result = self.tk.call(self._orig, command, *args)
        except TclError as e:
            error = str(e)
            if (
                'tagged with "sel"' in error
                or "nothing to" in error
                or "bad text index" in error
            ):
                return ""
            raise e from None

        if command == "insert":
            if args[0] != "insert":
                start_line -= 1
            lines = args[1].count("\n")
            if lines == 1:
                self.highlight_line(f"{start_line}.0")
            else:
                self.highlight_area(start_line, start_line + lines)
            self.event_generate("<<ContentChanged>>")
        elif command in {"replace", "delete"}:
            if start_line == end_line:
                self.highlight_line(f"{start_line}.0")
            else:
                self.highlight_area(start_line, end_line)
            self.event_generate("<<ContentChanged>>")

        return result

    def _setup_tags(self, tags: dict[str, str]) -> None:
        for key, value in tags.items():
            if isinstance(value, str):
                self.tag_configure(f"Token.{key}", foreground=value)

    def highlight_line(self, index: str) -> None:
        line_num = int(self.index(index).split(".")[0])
        for tag in self.tag_names(index=None):
            if tag.startswith("Token"):
                self.tag_remove(tag, f"{line_num}.0", f"{line_num}.end")
        # Use rstrip('\n') so pygments' trailing newline token doesn't shift columns
        line_text = self.get(f"{line_num}.0", f"{line_num}.end").rstrip("\n")
        start_col = 0
        for token, text in pygments.lex(line_text, self._lexer):
            token = str(token)
            end_col = start_col + len(text)
            # Skip the synthetic trailing newline pygments always appends
            if text == "\n":
                break
            if token not in {"Token.Text.Whitespace", "Token.Text", "active_line"}:
                self.tag_add(token, f"{line_num}.{start_col}", f"{line_num}.{end_col}")
            start_col = end_col

    def highlight_all(self) -> None:
        for tag in self.tag_names(index=None):
            if tag.startswith("Token"):
                self.tag_remove(tag, "1.0", "end")
        lines = self.get("1.0", "end")
        line_offset = lines.count("\n") - lines.lstrip().count("\n")
        start_index = str(
            self.tk.call(self._orig, "index", f"1.0 + {line_offset} lines")
        )
        for token, text in pygments.lex(lines, self._lexer):
            token = str(token)
            end_index = self.index(f"{start_index} + {len(text)} chars")
            if token not in {"Token.Text.Whitespace", "Token.Text"}:
                self.tag_add(token, start_index, end_index)
            start_index = end_index

    def highlight_area(
        self, start_line: int | None = None, end_line: int | None = None
    ) -> None:
        for tag in self.tag_names(index=None):
            if tag.startswith("Token"):
                self.tag_remove(tag, f"{start_line}.0", f"{end_line}.end")
        text = self.get(f"{start_line}.0", f"{end_line}.end")
        line_offset = text.count("\n") - text.lstrip().count("\n")
        start_index = str(
            self.tk.call(self._orig, "index", f"{start_line}.0 + {line_offset} lines")
        )
        for token, text in pygments.lex(text, self._lexer):
            token = str(token)
            end_index = self.index(f"{start_index} + {len(text)} indices")
            if token not in {"Token.Text.Whitespace", "Token.Text"}:
                self.tag_add(token, start_index, end_index)
            start_index = end_index

    def set_color_scheme(
        self, color_scheme: dict[str, dict[str, str | int]] | str | None
    ) -> None:
        if isinstance(color_scheme, str) and color_scheme in self.builtin_color_schemes:
            color_scheme = toml.load(color_schemes_dir / f"{color_scheme}.toml")
        elif color_scheme is None:
            color_scheme = toml.load(color_schemes_dir / "dracula.toml")
        assert isinstance(color_scheme, dict), (
            "Must be a dictionary or a built-in color scheme"
        )
        config, tags = _parse_scheme(color_scheme)
        self.configure(**config)
        self._setup_tags(tags)
        self.highlight_all()
        # Keep the outer frame background in sync so no fringe shows between columns.
        self._frame.configure(bg=self["background"])
        self._sticky.apply_colors(
            bg=self["background"],
            fg=self["foreground"],
            sep="#44475a",
            font=self.cget("font"),
        )
        self._minimap.apply_colors(
            bg=self["background"],
            fg=self["foreground"],
        )

    def _set_lexer(self, lexer: LexerType) -> None:
        self._lexer = lexer() if inspect.isclass(lexer) else lexer
        self.highlight_all()
        if hasattr(self, "_sticky"):
            self._sticky._sync_tags()

    def __setitem__(self, key: str, value) -> None:
        self.configure(**{key: value})

    def __getitem__(self, key: str) -> Any:
        return self.cget(key)

    def configure(self, **kwargs) -> None:
        lexer = kwargs.pop("lexer", None)
        color_scheme = kwargs.pop("color_scheme", None)
        if lexer is not None:
            self._set_lexer(lexer)
        if color_scheme is not None:
            self.set_color_scheme(color_scheme)
        super().configure(**kwargs)
        # Re-sync minimap font if font changed
        if "font" in kwargs and hasattr(self, "_minimap"):
            self._minimap.apply_colors(self["background"], self["foreground"])

    config = configure

    def pack(self, *args, **kwargs) -> None:
        self._frame.pack(*args, **kwargs)

    def grid(self, *args, **kwargs) -> None:
        self._frame.grid(*args, **kwargs)

    def place(self, *args, **kwargs) -> None:
        self._frame.place(*args, **kwargs)

    def pack_forget(self) -> None:
        self._frame.pack_forget()

    def grid_forget(self) -> None:
        self._frame.grid_forget()

    def place_forget(self) -> None:
        self._frame.place_forget()

    def destroy(self) -> None:
        for widget in self._frame.winfo_children():
            BaseWidget.destroy(widget)
        BaseWidget.destroy(self._frame)

    def horizontal_scroll(self, first: str | float, last: str | float) -> None:
        self._hs.set(first, last)

    def show_minimap(self) -> None:
        self._minimap.grid()  # also re-shows the border widget

    def hide_minimap(self) -> None:
        self._minimap.grid_remove()  # also hides the border widget

    def vertical_scroll(self, first: str | float, last: str | float) -> None:
        self._vs.set(first, last)
        self._line_numbers.redraw()
        self._sticky.refresh()

    def scroll_line_update(self, event: Event | None = None) -> None:
        self.horizontal_scroll(*self.xview())
        self.vertical_scroll(*self.yview())

