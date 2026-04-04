"""LspClient — JSON-RPC 2.0 transport over a language-server subprocess.

Spawns the server, writes requests to its stdin, and reads responses/
notifications from stdout in a background thread.  All callbacks are
dispatched on the main thread via the *after_fn* hook (tkinter's `after`).
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Callable, Optional


class LspClient:
    def __init__(
        self,
        cmd: list[str],
        on_notification: Callable[[str, dict], None],
        after_fn: Callable,
        cwd: str = "",
    ) -> None:
        self._on_notification = on_notification
        self._after_fn        = after_fn
        self._pending: dict[int, Callable] = {}
        self._lock    = threading.Lock()
        self._next_id = 1
        self._running = False

        env = os.environ.copy()
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=cwd or None,
            env=env,
        )
        self._running = True
        threading.Thread(target=self._reader, daemon=True).start()

    # ── Public API ────────────────────────────────────────────────────────────

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def request(self, method: str, params: dict,
                callback: Callable | None = None) -> int:
        with self._lock:
            msg_id = self._next_id
            self._next_id += 1
            if callback:
                self._pending[msg_id] = callback
        self._send({"jsonrpc": "2.0", "id": msg_id,
                    "method": method, "params": params})
        return msg_id

    def notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def shutdown(self) -> None:
        self._running = False
        try:
            self.request("shutdown", {})
            self.notify("exit", {})
            self._proc.terminate()
        except Exception:
            pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _send(self, msg: dict) -> None:
        body   = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        try:
            self._proc.stdin.write(header + body)
            self._proc.stdin.flush()
        except Exception:
            pass

    def _reader(self) -> None:
        while self._running and self.is_alive():
            try:
                # Read headers until blank line
                headers: dict[str, str] = {}
                while True:
                    raw = self._proc.stdout.readline()
                    if not raw:
                        return
                    line = raw.decode("utf-8").strip()
                    if not line:
                        break
                    key, _, value = line.partition(":")
                    headers[key.strip()] = value.strip()

                length = int(headers.get("Content-Length", 0))
                if length == 0:
                    continue
                body = self._proc.stdout.read(length).decode("utf-8")
                msg  = json.loads(body)
                # Schedule dispatch on the main thread
                self._after_fn(0, lambda m=msg: self._dispatch(m))
            except Exception:
                break

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg and "method" not in msg:
            # Response to a request we sent
            with self._lock:
                cb = self._pending.pop(msg["id"], None)
            if cb:
                cb(msg.get("result"), msg.get("error"))
        elif "method" in msg:
            # Notification or server-initiated request
            self._on_notification(msg["method"], msg.get("params") or {})
