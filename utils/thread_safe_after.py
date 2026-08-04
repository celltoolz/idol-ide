"""thread_safe_after — queue-backed tkinter.after wrapper for background threads.

tkinter's after() calls tk.createcommand() internally, which must run on the
main thread.  On macOS Python 3.14+ this is strictly enforced and raises:
  RuntimeError: main thread is not in main loop

Usage:
    safe_after = make_thread_safe_after(some_tk_widget)
    # Pass safe_after as after_fn to any manager that runs on daemon threads.

Also home to rearm_after(), the guard every self-re-arming after() loop needs.

This module imports tkinter, which no other utils/ module does.  That is not a
crack in the import rule: the rule forbids utils/ from reaching into IDOL's own
widgets/ layer, and this file is a tkinter lifecycle shim by definition — it
already takes a Tk widget and calls .after() on it.  Naming (tk.TclError,
RuntimeError) exactly beats a blanket except Exception in a helper that every
poll loop in the app depends on.
"""
from __future__ import annotations

import queue
import tkinter as tk
from typing import Callable


def rearm_after(widget, delay_ms: int, callback: Callable) -> str | None:
    """Re-schedule *callback* on *widget*, unless the widget is gone.

    Returns the after-id when the next tick was scheduled, None when the widget
    has been destroyed and the loop should stop. An id rather than a bool
    because several of these loops also store their id to after_cancel() it on
    an explicit stop — a bool would have forced those sites to keep calling
    widget.after directly, which is the bug.

    **Every self-re-arming after() loop must go through this instead of calling
    widget.after directly.**  Tk registers after() callbacks on the interpreter,
    not on the widget, so destroying the widget does not cancel a pending tick:
    the tick still fires, re-arms against a destroyed widget, and raises —
    TclError for a destroyed widget, RuntimeError once the interpreter itself is
    gone.  In the running app Tk's background-error handler swallows that and it
    is invisible; under pytest it surfaces as a PytestUnraisableExceptionWarning
    reported against whichever test happened to be running, which is what made
    panels effectively untestable at the widget level.

    Both the winfo_exists() check and the after() call sit inside the try, since
    the widget can be destroyed between the two.

    The alternative pattern — cancelling a stored after-id in destroy() — is
    equally correct and is what widgets/welcome.py does; this helper is for the
    loops that have no id to store.
    """
    try:
        if not widget.winfo_exists():
            return None
        return widget.after(delay_ms, callback)
    except (tk.TclError, RuntimeError):
        return None


def make_thread_safe_after(widget) -> Callable:
    """Return an after_fn callable that is safe to call from any thread.

    The returned function has the same signature as tkinter's after():
        safe_after(delay_ms, callback, *args)

    A background polling loop (started immediately) drains the queue on the
    main thread so tkinter.after() is always invoked on the main thread.
    """
    q: queue.Queue = queue.Queue()

    def _safe_after(delay_ms: int, callback: Callable, *args) -> None:
        q.put((delay_ms, callback, args))

    def _pump() -> None:
        try:
            while True:
                delay, cb, args = q.get_nowait()
                try:
                    widget.after(delay, cb, *args) if args else widget.after(delay, cb)
                except (tk.TclError, RuntimeError):
                    # Widget gone mid-drain. Stop the loop rather than re-arming;
                    # anything still queued has nothing left to run on.
                    return
        except queue.Empty:
            pass
        rearm_after(widget, 16, _pump)

    rearm_after(widget, 16, _pump)
    return _safe_after
