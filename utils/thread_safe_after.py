"""thread_safe_after — queue-backed tkinter.after wrapper for background threads.

tkinter's after() calls tk.createcommand() internally, which must run on the
main thread.  On macOS Python 3.14+ this is strictly enforced and raises:
  RuntimeError: main thread is not in main loop

Usage:
    safe_after = make_thread_safe_after(some_tk_widget)
    # Pass safe_after as after_fn to any manager that runs on daemon threads.
"""
from __future__ import annotations

import queue
from typing import Callable


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
                widget.after(delay, cb, *args) if args else widget.after(delay, cb)
        except queue.Empty:
            pass
        widget.after(16, _pump)

    widget.after(16, _pump)
    return _safe_after
