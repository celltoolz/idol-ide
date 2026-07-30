"""CondaChannelsEditor — pick and order the conda channels a project searches.

Opened from the Package Manager's CHANNELS bar. Two panes, `ComponentConnector`
style: **Available** is the catalog (`data/idol_conda_channels.json`) plus
anything custom the user types, **Searched** is the project's ordered active
list. Reordering happens only on the right, because only the right-hand list is
configuration.

Two things this deliberately does not have:

* **No enable/disable.** The list is written to the project's `environment.yml`,
  and conda has no notion of a disabled channel — a portable, conda-native file
  can only express which channels are active. Removing a channel and re-adding
  it from Available is the same gesture with none of the round-trip loss.
* **No "don't use Anaconda defaults" switch.** Removing `defaults` from the list
  is that switch; `utils.conda_env.render_channels_block` emits `nodefaults`
  whenever `defaults` is absent, so the list says it on its own.

This dialog only collects the ordered list and hands it to `on_save`. Writing
the file is `utils.conda_env.write_project_channels`, and the caller owns it.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from utils.conda_channels import (CATALOG, catalog_entry, blocking,
                                  reorder_for_requirements, validate)
from utils.conda_env import mask_channel
from utils.ui_font import UI_FONT

_BG       = "#1e1e1e"
_PANEL    = "#252526"
_LIST     = "#1e1e1e"
_INPUT_BG = "#2d2d30"
_BORDER   = "#3c3c3c"
_FG       = "#cccccc"
_DIM      = "#858585"
_LINK     = "#569cd6"
_WARN     = "#e2c08d"
_SEL      = "#094771"
_ACCENT   = "#0e639c"
_ACCENT_H = "#1177bb"
_GREY     = "#3c3c3c"
_GREY_H   = "#4a4a4a"

_ERR      = "#f48771"

#: Issue severity → the colour it is drawn in.
_SEV_FG = {"error": _ERR, "warning": _WARN, "info": _DIM}


class CondaChannelsEditor(tk.Toplevel):
    """Modal channel picker. Calls on_save(channels) only on Save."""

    def __init__(self, parent, channels: list[str], target_label: str,
                 on_save: Callable[[list[str]], None],
                 priority: str = "",
                 missing: tuple[str, ...] = ()) -> None:
        super().__init__(parent)
        self._on_save = on_save
        # conda's channel_priority changes what a conflict means, and which
        # channels have no searchable index is something only the search layer
        # knows — both are passed in rather than re-derived here.
        self._priority = priority
        self._missing = tuple(missing)
        # Work on a copy: Cancel has to leave the caller's list untouched.
        self._active: list[str] = [c for c in channels if c]
        self._saved = False
        self._save_blocked = False
        self._sel: tuple[str, str] | None = None   # ("avail"|"active", spec)
        #: spec → the index it was removed from, for in-session restore. Order
        #: is the configuration here, so re-adding a channel at the bottom of
        #: the list is a silent misconfiguration rather than an inconvenience.
        #: Deliberately not persisted — it is an undo, not a preference.
        self._removed_at: dict[str, int] = {}

        self.title(f"Conda Channels — {target_label}")
        self.configure(bg=_BG)
        self.transient(parent.winfo_toplevel())
        self.minsize(660, 470)

        self._build(target_label)
        self._refresh()

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _: self.destroy())

        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{px + max((pw - w) // 2, 0)}+{py + max((ph - h) // 3, 0)}")
        self.grab_set()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self, target_label: str) -> None:
        tk.Label(self, text="Channels are searched in order — 1 first. "
                            "The order decides which channel's build of a "
                            "package you get.",
                 bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w",
                 padx=12, pady=(8)).pack(fill="x")

        cols = tk.Frame(self, bg=_BG)
        cols.pack(fill="both", expand=True, padx=12, pady=(2, 0))

        # ── Left: available ───────────────────────────────────────────────────
        left = tk.Frame(cols, bg=_BG)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="AVAILABLE", bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8, "bold"), anchor="w").pack(fill="x")

        self._filter_var = tk.StringVar()
        filt = tk.Entry(left, textvariable=self._filter_var, bg=_INPUT_BG,
                        fg=_FG, insertbackground=_FG, font=(UI_FONT, 9),
                        relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=_BORDER, highlightcolor=_ACCENT)
        filt.pack(fill="x", ipady=3, pady=(2, 4))
        filt.insert(0, "")
        # Return would otherwise submit nothing; make it add the top match.
        filt.bind("<Return>", lambda _: self._add_selected())
        self._filter_var.trace_add("write", lambda *_: self._refresh_avail())

        self._avail_lb = tk.Listbox(
            left, bg=_LIST, fg=_FG, selectbackground=_SEL, activestyle="none",
            font=(UI_FONT, 9), relief="flat", bd=0, height=11,
            exportselection=False, highlightthickness=0,
        )
        self._avail_lb.pack(fill="both", expand=True)
        self._avail_lb.bind("<<ListboxSelect>>", lambda _: self._on_avail_select())
        self._avail_lb.bind("<Double-Button-1>", lambda _: self._add_selected())

        custom = tk.Frame(left, bg=_BG)
        custom.pack(fill="x", pady=(6, 0))
        self._custom_var = tk.StringVar()
        cust_entry = tk.Entry(custom, textvariable=self._custom_var, bg=_INPUT_BG,
                              fg=_FG, insertbackground=_FG, font=(UI_FONT, 9),
                              relief="flat", bd=0, highlightthickness=1,
                              highlightbackground=_BORDER, highlightcolor=_ACCENT)
        cust_entry.pack(side="left", fill="x", expand=True, ipady=3)
        cust_entry.bind("<Return>", lambda _: self._add_custom())
        self._btn(custom, "＋ Add custom", _GREY, _GREY_H, _FG,
                  self._add_custom).pack(side="right", padx=(6, 0))
        tk.Label(left, text="a name, a full URL, owner/label, or file:///path",
                 bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w").pack(
            fill="x", pady=(2, 0))

        # ── Middle: add ───────────────────────────────────────────────────────
        mid = tk.Frame(cols, bg=_BG, width=90)
        mid.pack(side="left", fill="y", padx=8)
        mid.pack_propagate(False)
        self._add_btn = self._btn(mid, "Add  →", _ACCENT, _ACCENT_H, "white",
                                  self._add_selected)
        self._add_btn.pack(pady=(90, 6))
        self._rm_btn = self._btn(mid, "←  Remove", _GREY, _GREY_H, _FG,
                                 self._remove_selected)
        self._rm_btn.pack()

        # ── Right: searched ───────────────────────────────────────────────────
        right = tk.Frame(cols, bg=_BG)
        right.pack(side="left", fill="both", expand=True)
        hdr = tk.Frame(right, bg=_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="SEARCHED", bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8, "bold"), anchor="w").pack(side="left")
        tk.Label(hdr, text="1 is searched first", bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8)).pack(side="right")

        self._active_lb = tk.Listbox(
            right, bg=_LIST, fg=_FG, selectbackground=_SEL, activestyle="none",
            font=(UI_FONT, 9), relief="flat", bd=0, height=11,
            exportselection=False, highlightthickness=0,
        )
        self._active_lb.pack(fill="both", expand=True, pady=(2, 0))
        self._active_lb.bind("<<ListboxSelect>>",
                             lambda _: self._on_active_select())
        self._active_lb.bind("<Double-Button-1>",
                             lambda _: self._remove_selected())

        tools = tk.Frame(right, bg=_BG)
        tools.pack(fill="x", pady=(6, 0))
        self._btn(tools, "▲", _GREY, _GREY_H, _FG,
                  lambda: self._move(-1)).pack(side="left")
        self._btn(tools, "▼", _GREY, _GREY_H, _FG,
                  lambda: self._move(1)).pack(side="left", padx=(4, 0))
        self._btn(tools, "✕", _GREY, _GREY_H, _FG,
                  self._remove_selected).pack(side="left", padx=(4, 0))
        self._restore_btn = self._btn(tools, "↺ Restore", _GREY, _GREY_H, _LINK,
                                      self._restore_last)
        tk.Label(right, text="each channel adds work to every solve and search",
                 bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w").pack(
            fill="x", pady=(4, 0))

        # ── Description box ───────────────────────────────────────────────────
        self._desc = tk.Frame(self, bg=_PANEL, height=104)
        self._desc.pack(fill="x", padx=12, pady=(10, 0))
        self._desc.pack_propagate(False)
        self._desc_title = tk.Label(self._desc, text="", bg=_PANEL, fg=_LINK,
                                    font=(UI_FONT, 9, "bold"), anchor="w")
        self._desc_title.pack(fill="x", padx=10, pady=(8, 0))
        self._desc_body = tk.Label(self._desc, text="", bg=_PANEL, fg=_FG,
                                   font=(UI_FONT, 8), anchor="nw",
                                   justify="left", wraplength=600)
        self._desc_body.pack(fill="x", padx=10, pady=(3, 0))
        self._desc_note = tk.Label(self._desc, text="", bg=_PANEL, fg=_WARN,
                                   font=(UI_FONT, 8), anchor="nw",
                                   justify="left", wraplength=600)
        self._desc_note.pack(fill="x", padx=10, pady=(3, 0))

        # ── Issues strip ──────────────────────────────────────────────────────
        # Live, and above the footer rather than in a dialog on Save: an
        # ordering mistake is worth seeing while you are still making it.
        self._issues_frame = tk.Frame(self, bg=_BG)
        self._issue_rows: list[tk.Widget] = []

        # ── Footer ────────────────────────────────────────────────────────────
        foot = tk.Frame(self, bg=_BG)
        foot.pack(fill="x", padx=12, pady=(10, 12))
        self._foot = foot
        tk.Label(foot, text=f"Writes channels: to {target_label}", bg=_BG,
                 fg=_DIM, font=(UI_FONT, 8), anchor="w").pack(side="left")
        self._save_btn = self._btn(foot, "Save", _ACCENT, _ACCENT_H, "white",
                                   self._save)
        self._save_btn.pack(side="right")
        self._btn(foot, "Cancel", _GREY, _GREY_H, _FG,
                  self.destroy).pack(side="right", padx=(0, 8))

    def _btn(self, parent, text: str, bg: str, hover_bg: str, fg: str,
             command: Callable[[], None]) -> tk.Label:
        """A clickable label. IDOL uses labels, not tk.Button, for actions."""
        lbl = tk.Label(parent, text=text, bg=bg, fg=fg,
                       font=(UI_FONT, 9), padx=12, pady=4, cursor="hand2")
        lbl.bind("<Enter>", lambda _: lbl.config(bg=hover_bg))
        lbl.bind("<Leave>", lambda _: lbl.config(bg=bg))
        lbl.bind("<ButtonRelease-1>", lambda _: command())
        return lbl

    # ── Data ──────────────────────────────────────────────────────────────────

    def _available(self) -> list[str]:
        """Catalog specs not already active, plus previously-removed customs."""
        out = [e["spec"] for e in CATALOG if e["spec"] not in self._active]
        for spec in self._removed_at:
            if spec not in self._active and spec not in out:
                out.append(spec)
        query = self._filter_var.get().strip().lower()
        if query:
            out = [s for s in out
                   if query in s.lower()
                   or query in ((catalog_entry(s) or {}).get("description", "")
                                .lower())]
        return out

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._refresh_avail()
        self._refresh_active()
        self._sync_restore()
        self._refresh_issues()

    def _refresh_issues(self) -> None:
        """Re-render the issues strip for the current working list."""
        for row in self._issue_rows:
            row.destroy()
        self._issue_rows = []
        issues = validate(self._active, self._priority, self._missing)
        self._sync_save(bool(blocking(issues)))
        if not issues:
            self._issues_frame.pack_forget()
            return
        # Above the footer, below the description box.
        self._issues_frame.pack(fill="x", padx=12, pady=(8, 0),
                                before=self._foot)
        for issue in issues:
            row = tk.Frame(self._issues_frame, bg=_BG)
            row.pack(fill="x", pady=(2, 0))
            glyph = "✕" if issue.severity == "error" else (
                "⚠" if issue.severity == "warning" else "ⓘ")
            fg = _SEV_FG[issue.severity]
            tk.Label(row, text=glyph, bg=_BG, fg=fg,
                     font=(UI_FONT, 8, "bold")).pack(side="left", padx=(0, 6))
            # The fix button packs first so a long message wraps around it
            # instead of pushing it out of the window.
            if issue.fix == "reorder":
                self._btn(row, "Fix order", _GREY, _GREY_H, _LINK,
                          self._fix_order).pack(side="right", padx=(8, 0))
            tk.Label(row, text=issue.message, bg=_BG, fg=fg,
                     font=(UI_FONT, 8), anchor="w", justify="left",
                     wraplength=560).pack(side="left", fill="x", expand=True)
            self._issue_rows.append(row)

    def _sync_save(self, blocked: bool) -> None:
        """Make Save *look* unavailable when it is.

        The refusal used to be silent — Save simply did nothing on an empty
        list. The reason is now always on screen in the issues strip, and the
        button stops inviting the click.
        """
        self._save_blocked = blocked
        if blocked:
            self._save_btn.config(bg=_GREY, fg=_DIM, cursor="")
            self._save_btn.unbind("<Enter>")
            self._save_btn.unbind("<Leave>")
        else:
            self._save_btn.config(bg=_ACCENT, fg="white", cursor="hand2")
            self._save_btn.bind(
                "<Enter>", lambda _: self._save_btn.config(bg=_ACCENT_H))
            self._save_btn.bind(
                "<Leave>", lambda _: self._save_btn.config(bg=_ACCENT))

    def _fix_order(self) -> None:
        """Reorder the active list so every requires_order_below is satisfied."""
        fixed = reorder_for_requirements(self._active)
        if fixed == self._active:
            return
        self._active = fixed
        self._refresh()

    def _refresh_avail(self) -> None:
        self._avail_lb.delete(0, "end")
        for spec in self._available():
            entry = catalog_entry(spec)
            tier = f"   {entry['tier']}" if entry else "   custom"
            self._avail_lb.insert("end", f" {mask_channel(spec)}{tier}")

    def _refresh_active(self) -> None:
        self._active_lb.delete(0, "end")
        for i, spec in enumerate(self._active, 1):
            self._active_lb.insert("end", f" {i}   {mask_channel(spec)}")

    def _sync_restore(self) -> None:
        """Show the restore affordance only while there is something to restore."""
        if self._removable_restores():
            self._restore_btn.pack(side="right")
        else:
            self._restore_btn.pack_forget()

    def _removable_restores(self) -> list[str]:
        return [s for s in self._removed_at if s not in self._active]

    def _show_desc(self, spec: str) -> None:
        entry = catalog_entry(spec)
        if not entry:
            self._desc_title.config(text=mask_channel(spec))
            self._desc_body.config(
                text="Custom channel. IDOL has no description for this one — it "
                     "is passed to conda exactly as written.")
            self._desc_note.config(text="")
            return
        self._desc_title.config(text=entry.get("display_name") or spec)
        self._desc_body.config(text=entry.get("description") or "")
        notes = [entry["notes"]] if entry.get("notes") else []
        below = [c for c in entry.get("requires_order_below") or []]
        if below:
            notes.append("Needs " + ", ".join(below) + " searched before it.")
        self._desc_note.config(text="\n".join(f"⚠  {n}" for n in notes))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_avail_select(self) -> None:
        specs = self._available()
        idx = self._avail_lb.curselection()
        if idx and idx[0] < len(specs):
            self._sel = ("avail", specs[idx[0]])
            self._show_desc(specs[idx[0]])

    def _on_active_select(self) -> None:
        idx = self._active_lb.curselection()
        if idx and idx[0] < len(self._active):
            self._sel = ("active", self._active[idx[0]])
            self._show_desc(self._active[idx[0]])

    def _add_selected(self) -> None:
        """Add the highlighted available channel, or the only filter match."""
        specs = self._available()
        idx = self._avail_lb.curselection()
        spec = specs[idx[0]] if idx else (specs[0] if len(specs) == 1 else "")
        if spec:
            self._insert(spec)

    def _add_custom(self) -> None:
        spec = self._custom_var.get().strip()
        if not spec or spec in self._active:
            self._custom_var.set("")
            return
        self._custom_var.set("")
        self._insert(spec)

    def _insert(self, spec: str) -> None:
        """Add *spec*, at the position it was removed from when we know it."""
        if spec in self._active:
            return
        at = self._removed_at.pop(spec, None)
        if at is None or at > len(self._active):
            self._active.append(spec)
        else:
            self._active.insert(at, spec)
        self._refresh()
        self._select_active(spec)
        self._show_desc(spec)

    def _remove_selected(self) -> None:
        idx = self._active_lb.curselection()
        if not idx or idx[0] >= len(self._active):
            return
        at = idx[0]
        spec = self._active.pop(at)
        self._removed_at[spec] = at
        self._refresh()

    def _restore_last(self) -> None:
        pending = self._removable_restores()
        if pending:
            self._insert(pending[-1])

    def _move(self, delta: int) -> None:
        idx = self._active_lb.curselection()
        if not idx:
            return
        at = idx[0]
        to = at + delta
        if not (0 <= at < len(self._active) and 0 <= to < len(self._active)):
            return
        self._active[at], self._active[to] = self._active[to], self._active[at]
        self._refresh_active()
        self._active_lb.selection_set(to)
        self._sel = ("active", self._active[to])

    def _select_active(self, spec: str) -> None:
        if spec in self._active:
            at = self._active.index(spec)
            self._active_lb.selection_clear(0, "end")
            self._active_lb.selection_set(at)
            self._active_lb.see(at)
            self._sel = ("active", spec)

    def _save(self) -> None:
        # Blocked by an "error" issue — the strip says why and `_sync_save` has
        # already greyed the button, so there is nothing to report here.
        if self._saved or self._save_blocked:
            return
        self._saved = True
        channels = list(self._active)
        self.destroy()
        self._on_save(channels)
