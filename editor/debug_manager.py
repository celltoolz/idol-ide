"""DebugManager — DAP (Debug Adapter Protocol) client for debugpy.

Launches debugpy as a subprocess, connects via TCP, and drives the
debug session.  All callbacks are dispatched on the main thread via
after_fn (tkinter's `after`).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from typing import Callable, Optional


def _find_free_port(start: int = 5678, end: int = 5720) -> int:
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start


class DebugManager:
    """Thin DAP client that wraps a debugpy process."""

    def __init__(self, after_fn: Callable) -> None:
        self._after_fn   = after_fn
        self._proc: Optional[subprocess.Popen]  = None
        self._sock: Optional[socket.socket]     = None
        self._seq        = 1
        self._pending: dict[int, Callable]      = {}
        self._lock       = threading.Lock()
        self._running    = False
        self._thread_id: Optional[int]          = None
        self._port: int  = 5678

        # Set these before calling launch()
        self.on_stopped:    Optional[Callable[[int, str, int, str], None]] = None
        self.on_continued:  Optional[Callable[[], None]]                  = None
        self.on_terminated: Optional[Callable[[], None]]                  = None
        self.on_output:     Optional[Callable[[str, str], None]]          = None

    @property
    def active(self) -> bool:
        return self._running

    # ── Public API ────────────────────────────────────────────────────────────

    def launch(
        self,
        filepath: str,
        python_path: str,
        breakpoints: dict[str, list[int]],
    ) -> None:
        """Start a debug session for *filepath* using *python_path*."""
        self._filepath            = filepath
        self._pending_breakpoints = breakpoints
        self._port                = _find_free_port()

        cmd = [
            python_path,
            "-m", "debugpy",
            "--listen", f"127.0.0.1:{self._port}",
            "--wait-for-client",
            filepath,
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(filepath) or None,
        )
        self._running = True
        threading.Thread(target=self._pipe_reader, args=(self._proc.stderr,), daemon=True).start()
        threading.Thread(target=self._pipe_reader, args=(self._proc.stdout,), daemon=True).start()
        # Give debugpy ~300 ms to start listening, then connect
        self._after_fn(300, self._connect)

    def continue_(self) -> None:
        if self._thread_id is not None:
            self._request("continue", {"threadId": self._thread_id})

    def next_(self) -> None:
        if self._thread_id is not None:
            self._request("next", {"threadId": self._thread_id})

    def step_in(self) -> None:
        if self._thread_id is not None:
            self._request("stepIn", {"threadId": self._thread_id})

    def step_out(self) -> None:
        if self._thread_id is not None:
            self._request("stepOut", {"threadId": self._thread_id})

    def disconnect(self) -> None:
        self._running = False
        try:
            self._request("disconnect", {"terminateDebuggee": True})
        except Exception:
            pass
        for obj in (self._sock, self._proc):
            try:
                if obj:
                    obj.close() if hasattr(obj, "close") else obj.terminate()
            except Exception:
                pass
        self._sock      = None
        self._proc      = None
        self._thread_id = None

    def get_locals(
        self,
        frame_id: int,
        callback: Callable[[list[dict]], None],
    ) -> None:
        """Fetch local variables for *frame_id* and deliver to *callback*."""
        def _on_scopes(result, _error):
            if not result:
                callback([])
                return
            locals_ref = None
            for scope in result.get("scopes", []):
                if scope.get("name") in ("Locals", "locals"):
                    locals_ref = scope["variablesReference"]
                    break
            if locals_ref is None:
                scopes = result.get("scopes", [])
                if scopes:
                    locals_ref = scopes[0]["variablesReference"]
            if not locals_ref:
                callback([])
                return
            self._request(
                "variables",
                {"variablesReference": locals_ref},
                lambda r, e: callback(r.get("variables", []) if r else []),
            )

        self._request("scopes", {"frameId": frame_id}, _on_scopes)

    # ── Transport ─────────────────────────────────────────────────────────────

    def _pipe_reader(self, pipe) -> None:
        """Forward subprocess stdout/stderr through on_output."""
        try:
            for raw in pipe:
                text = raw.decode("utf-8", errors="replace")
                if text and self.on_output:
                    self._after_fn(0, lambda t=text: self.on_output("stdout", t))
        except Exception:
            pass

    def _connect(self) -> None:
        """Connect TCP socket to debugpy; retry up to 15 times."""
        for attempt in range(15):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                sock.connect(("127.0.0.1", self._port))
                sock.settimeout(None)
                self._sock = sock
                threading.Thread(target=self._reader, daemon=True).start()
                self._request("initialize", {
                    "adapterID":            "python",
                    "clientName":           "IDOL",
                    "pathFormat":           "path",
                    "linesStartAt1":        True,
                    "columnsStartAt1":      True,
                    "supportsVariableType": True,
                }, self._on_initialize_response)
                return
            except (ConnectionRefusedError, OSError):
                time.sleep(0.2)
        # Could not connect — signal termination
        self._running = False
        if self.on_terminated:
            self._after_fn(0, self.on_terminated)

    def _request(
        self,
        command: str,
        args: dict,
        callback: Optional[Callable] = None,
    ) -> int:
        with self._lock:
            seq = self._seq
            self._seq += 1
            if callback:
                self._pending[seq] = callback
        self._send_msg({"seq": seq, "type": "request",
                        "command": command, "arguments": args})
        return seq

    def _send_msg(self, msg: dict) -> None:
        body   = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        try:
            self._sock.sendall(header + body)
        except Exception:
            pass

    def _reader(self) -> None:
        buf = b""
        while self._running:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while True:
                    sep = buf.find(b"\r\n\r\n")
                    if sep == -1:
                        break
                    header_raw = buf[:sep].decode("utf-8", errors="replace")
                    length = 0
                    for line in header_raw.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            length = int(line.split(":", 1)[1].strip())
                    body_start = sep + 4
                    if len(buf) < body_start + length:
                        break
                    body = buf[body_start : body_start + length]
                    buf  = buf[body_start + length :]
                    try:
                        msg = json.loads(body.decode("utf-8"))
                        self._after_fn(0, lambda m=msg: self._dispatch(m))
                    except Exception:
                        pass
            except Exception:
                break
        if self._running:
            self._running = False
            if self.on_terminated:
                self._after_fn(0, self.on_terminated)

    def _dispatch(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "response":
            with self._lock:
                cb = self._pending.pop(msg.get("request_seq", -1), None)
            if cb:
                if msg.get("success"):
                    cb(msg.get("body"), None)
                else:
                    cb(None, msg.get("message", ""))
        elif kind == "event":
            self._handle_event(msg.get("event", ""), msg.get("body") or {})

    def _handle_event(self, event: str, body: dict) -> None:
        if event == "initialized":
            self._on_initialized()
        elif event == "stopped":
            self._thread_id = body.get("threadId", 1)
            reason = body.get("reason", "")
            if reason == "entry":
                # debugpy pauses at script entry before our breakpoints — skip it
                self.continue_()
                return
            self._request(
                "stackTrace",
                {"threadId": self._thread_id, "startFrame": 0, "levels": 1},
                lambda r, e: self._on_stack(r, reason),
            )
        elif event == "continued":
            if self.on_continued:
                self.on_continued()
        elif event in ("terminated", "exited"):
            self._running = False
            if self.on_terminated:
                self.on_terminated()
        elif event == "output":
            category = body.get("category", "stdout")
            text     = body.get("output", "")
            if text and self.on_output and category not in ("telemetry",):
                self.on_output(category, text)

    def _on_initialize_response(self, _result, _error) -> None:
        """initialize responded — attach to the waiting debugpy process."""
        self._request("attach", {"justMyCode": True})

    def _on_initialized(self) -> None:
        """debugpy sent initialized event — set breakpoints and release the script."""
        self._request("setExceptionBreakpoints", {"filters": ["uncaught"]})
        for filepath, lines in self._pending_breakpoints.items():
            self._request("setBreakpoints", {
                "source":      {"path": filepath},
                "breakpoints": [{"line": ln} for ln in sorted(lines)],
            })
        self._request("configurationDone", {})

    def _on_stack(self, result: Optional[dict], reason: str) -> None:
        frames = (result or {}).get("stackFrames", [])
        if not frames:
            if self.on_stopped:
                self.on_stopped(0, "", 0, reason)
            return
        frame    = frames[0]
        frame_id = frame.get("id", 0)
        source   = frame.get("source") or {}
        filepath = source.get("path", "")
        line     = frame.get("line", 0)
        if self.on_stopped:
            self.on_stopped(frame_id, filepath, line, reason)
