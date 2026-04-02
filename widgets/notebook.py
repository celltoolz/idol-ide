from __future__ import annotations

from tkinter import Label, Menu, PhotoImage, ttk
from typing import Callable, Optional


class CustomNotebook(ttk.Notebook):
    """A ttk Notebook with a hover-only close button on each tab.

    The X appears when you mouse over a tab and disappears when you leave.
    Right-click a tab for Close / Close Others / Close All.
    """

    __initialized = False

    def __init__(
        self, *args, on_close: Optional[Callable[[int], None]] = None, **kwargs
    ):
        if not self.__class__.__initialized:
            self._initialize_style()
            self.__class__.__initialized = True

        kwargs["style"] = "CustomNotebook"
        super().__init__(*args, **kwargs)

        self._on_close = on_close
        self._hovered_tab: int | None = None

        # Hover X — placed over whichever tab is under the cursor
        self._hover_btn = Label(
            self,
            text="×",
            font=("Segoe UI", 9, "bold"),
            fg="#888888",
            bg=self.__class__._COLOR_LIGHT,
            cursor="hand2",
            padx=2,
            pady=0,
        )
        self._hover_btn.bind("<ButtonPress-1>", self._on_hover_close_click)
        self._hover_btn.bind("<Enter>", self._on_hover_btn_enter)
        self._hover_btn.bind("<Leave>", self._on_hover_btn_leave)

        # Right-click context menu
        self._tab_menu = Menu(self, tearoff=0)
        self._tab_menu.add_command(label="Close",            command=self._close_from_menu)
        self._tab_menu.add_command(label="Close Others",     command=self._close_others)
        self._tab_menu.add_command(label="Close to the Left",  command=self._close_left)
        self._tab_menu.add_command(label="Close to the Right", command=self._close_right)
        self._tab_menu.add_separator()
        self._tab_menu.add_command(label="Close All",        command=self._close_all)
        self._menu_index: int | None = None

        # Drag state
        self._drag_index: int | None = None
        self._drag_tab_id: str | None = None

        self.bind("<ButtonPress-1>",   self._on_drag_start)
        self.bind("<B1-Motion>",       self._on_drag_motion)
        self.bind("<ButtonRelease-1>", self._on_drag_release)
        self.bind("<Motion>",          self._on_tab_motion)
        self.bind("<Leave>",           self._on_notebook_leave)
        self.bind("<Button-3>",        self._on_right_click)
        self.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.bind("<MouseWheel>",      self._on_scroll)
        self.bind("<Button-4>",        self._on_scroll)
        self.bind("<Button-5>",        self._on_scroll)

    # ── Tab drag reorder ──────────────────────────────────────────────────────

    def _on_drag_start(self, event) -> None:
        try:
            idx = self.index(f"@{event.x},{event.y}")
        except Exception:
            return
        self._drag_index = idx
        self._drag_tab_id = self.tabs()[idx]
        self.configure(cursor="fleur")

    def _on_drag_motion(self, event) -> None:
        if self._drag_index is None:
            return
        try:
            target = self.index(f"@{event.x},{event.y}")
        except Exception:
            return
        if target == self._drag_index:
            return
        # Move the tab to the target position
        self.insert(target, self._drag_tab_id)
        self._drag_index = target

    def _on_drag_release(self, _) -> None:
        self._drag_index = None
        self._drag_tab_id = None
        self.configure(cursor="")

    # ── Hover X logic ─────────────────────────────────────────────────────────

    def _on_tab_motion(self, event) -> None:
        # self.identify() needs a subcommand in Tk so use index() instead
        try:
            idx = self.index(f"@{event.x},{event.y}")
        except Exception:
            if self._hovered_tab is not None:
                self._hovered_tab = None
                self._hide_hover_btn()
            return
        if idx != self._hovered_tab:
            self._hovered_tab = idx
            self._show_hover_btn(idx, event.x, event.y)

    def _on_notebook_leave(self, event) -> None:
        # Use winfo_containing to detect if cursor moved onto the hover button
        widget_under = self.winfo_containing(event.x_root, event.y_root)
        if widget_under is self._hover_btn:
            return
        self._hovered_tab = None
        self._hide_hover_btn()

    def _on_hover_btn_enter(self, _) -> None:
        self._hover_btn.config(fg="#ffffff")

    def _on_hover_btn_leave(self, event) -> None:
        self._hover_btn.config(fg="#888888")
        widget_under = self.winfo_containing(event.x_root, event.y_root)
        if widget_under is not self._hover_btn and widget_under is not self:
            self._hovered_tab = None
            self._hide_hover_btn()

    def _tab_bar_height(self) -> int:
        """Find the tab bar height by scanning downward — cached after first call."""
        if not hasattr(self, "_cached_tab_h"):
            for y in range(2, 60):
                try:
                    self.index(f"@5,{y}")
                except Exception:
                    self._cached_tab_h = y - 1
                    break
            else:
                self._cached_tab_h = 24
        return self._cached_tab_h

    def _show_hover_btn(self, idx: int, mx: int, my: int) -> None:
        tabs = self.tabs()
        if idx >= len(tabs):
            return
        # Scan rightward from mouse x to find the tab's right edge
        nb_w = self.winfo_width()
        right = mx
        while right < nb_w:
            try:
                if self.index(f"@{right},{my}") != idx:
                    break
            except Exception:
                break
            right += 1

        btn_w, btn_h = 14, 14
        tab_h = self._tab_bar_height()
        btn_x = right - btn_w - 2
        # +14: _tab_bar_height() scans from y=0 which is above the visible tab row.
        # The tab row itself starts partway down the notebook header area, so we
        # offset by 14px to land the button in the visual center of the tab.
        btn_y = (tab_h - btn_h) // 2 + 14
        selected = self.index(self.select()) if tabs else -1
        bg = (
            self.__class__._COLOR_DARK
            if idx == selected
            else self.__class__._COLOR_LIGHT
        )
        self._hover_btn.configure(bg=bg)
        self._hover_btn.place(x=btn_x, y=btn_y, width=btn_w, height=btn_h)
        self._hover_btn.lift()

    def _hide_hover_btn(self) -> None:
        self._hover_btn.place_forget()

    def _on_hover_close_click(self, _) -> None:
        idx = self._hovered_tab
        if idx is None:
            return
        self._hide_hover_btn()
        self._hovered_tab = None
        self._do_close(idx)

    def _do_close(self, index: int) -> None:
        if self._on_close:
            self._on_close(index)
        else:
            if len(self.tabs()) > 1:
                self.forget(index)
            else:
                self.quit()

    # ── Right-click menu ──────────────────────────────────────────────────────

    def _on_right_click(self, event) -> None:
        try:
            index = self.index(f"@{event.x},{event.y}")
        except Exception:
            return
        self._menu_index = index
        self.select(index)
        self._tab_menu.tk_popup(event.x_root, event.y_root)

    def _close_from_menu(self) -> None:
        if self._menu_index is not None:
            self._do_close(self._menu_index)
            self._menu_index = None

    def _close_others(self) -> None:
        if self._menu_index is None:
            return
        keep = self.tabs()[self._menu_index]
        for tab_id in [t for t in self.tabs() if t != keep]:
            idx = list(self.tabs()).index(tab_id)
            self._do_close(idx)

    def _close_left(self) -> None:
        if self._menu_index is None:
            return
        for _ in range(self._menu_index):
            self._do_close(0)

    def _close_right(self) -> None:
        if self._menu_index is None:
            return
        while len(self.tabs()) > self._menu_index + 1:
            self._do_close(self._menu_index + 1)

    def _close_all(self) -> None:
        for _ in range(len(self.tabs())):
            self._do_close(0)

    # ── Tab changed / scroll ──────────────────────────────────────────────────

    def _on_tab_changed(self, *_) -> None:
        selected = self.index(self.select())
        for i, tab_id in enumerate(self.tabs()):
            self.tab(tab_id, underline=0 if i == selected else -1)
        # Refresh hover button bg in case selected state changed
        if self._hovered_tab is not None:
            self._show_hover_btn(self._hovered_tab)

    def _on_scroll(self, event) -> None:
        tabs = self.tabs()
        if not tabs:
            return
        current = self.index(self.select())
        if event.num == 4 or event.delta > 0:
            self.select(tabs[max(0, current - 1)])
        else:
            self.select(tabs[min(len(tabs) - 1, current + 1)])

    def select_next(self) -> None:
        tabs = self.tabs()
        idx = self.index(self.select())
        if idx < len(tabs) - 1:
            self.select(tabs[idx + 1])

    def select_prev(self) -> None:
        tabs = self.tabs()
        idx = self.index(self.select())
        if idx > 0:
            self.select(tabs[idx - 1])

    # ── Style initialization ──────────────────────────────────────────────────

    @classmethod
    def _initialize_style(cls):
        style = ttk.Style()
        cls._COLOR_LIGHT = "#D3D3D3"
        cls._COLOR_DARK = "#C1C1C1"

        style.theme_create(
            "selectedtab",
            parent="alt",
            settings={
                "CustomNotebook": {"configure": {"tabmargins": [2, 5, 2, 0]}},
                "CustomNotebook.Tab": {
                    "configure": {"padding": [5, 1], "background": cls._COLOR_LIGHT},
                    "map": {
                        "background": [("selected", cls._COLOR_DARK)],
                        "expand": [("selected", [1, 1, 1, 0])],
                    },
                },
            },
        )
        style.theme_use("selectedtab")

        # 1×1 transparent image used to neutralise the overflow arrow slots
        cls._images = (PhotoImage("img_arrow_blank", width=1, height=1),)

        # Bind overflow arrows to a zero-size blank so they don't fall back
        # to any other image element and show phantom icons
        for arrow in ("CustomNotebook.leftarrow", "CustomNotebook.rightarrow"):
            style.element_create(
                arrow,
                "image",
                "img_arrow_blank",
                border=0,
                width=0,
                height=0,
                sticky="",
            )

        style.layout(
            "CustomNotebook",
            [
                ("CustomNotebook.client", {"sticky": "nswe"}),
            ],
        )

        # Tab layout: label only — no close element
        style.layout(
            "CustomNotebook.Tab",
            [
                (
                    "CustomNotebook.tab",
                    {
                        "sticky": "nswe",
                        "children": [
                            (
                                "CustomNotebook.padding",
                                {
                                    "side": "top",
                                    "sticky": "nswe",
                                    "children": [
                                        (
                                            "CustomNotebook.focus",
                                            {
                                                "side": "top",
                                                "sticky": "nswe",
                                                "children": [
                                                    (
                                                        "CustomNotebook.label",
                                                        {"side": "left", "sticky": ""},
                                                    ),
                                                ],
                                            },
                                        )
                                    ],
                                },
                            )
                        ],
                    },
                )
            ],
        )
