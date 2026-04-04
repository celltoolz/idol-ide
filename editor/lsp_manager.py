"""LspManager — LSP protocol layer on top of LspClient.

Handles initialize handshake, file lifecycle (open/change/close),
and routes diagnostics / hover / definition responses.
"""
from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path
from typing import Callable, Optional

from .lsp_client import LspClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def path_to_uri(path: str) -> str:
    resolved = Path(path).resolve().as_posix()
    if not resolved.startswith("/"):
        resolved = "/" + resolved
    return f"file://{resolved}"


def uri_to_path(uri: str) -> str:
    path = uri.removeprefix("file:///").removeprefix("file://")
    # On Windows the URI looks like file:///C:/... → C:/...
    if len(path) > 1 and path[1] == ":":
        pass  # already looks like C:/...
    return path


def detect_server() -> list[str] | None:
    """Return a command to launch an available Python LSP server, or None."""
    # Prefer a server in the same Python environment as the running app
    scripts = os.path.dirname(sys.executable)
    for exe in ("pylsp", "pylsp.exe",
                "jedi-language-server", "jedi-language-server.exe"):
        candidate = os.path.join(scripts, exe)
        if os.path.isfile(candidate):
            return [candidate]
    # Fall back to PATH
    for name in ("pylsp", "pyright-langserver", "jedi-language-server"):
        found = shutil.which(name)
        if found:
            cmd = [found]
            if name == "pyright-langserver":
                cmd.append("--stdio")
            return cmd
    return None


# ── Severity constants ────────────────────────────────────────────────────────

SEV_ERROR   = 1
SEV_WARNING = 2
SEV_INFO    = 3
SEV_HINT    = 4


class LspManager:
    """High-level LSP client for one workspace / language server."""

    def __init__(self, root_path: str, after_fn: Callable) -> None:
        self._root      = root_path
        self._after_fn  = after_fn
        self._client: Optional[LspClient] = None
        self._ready     = False
        self._versions: dict[str, int] = {}   # uri → version counter

        # Callbacks set by the app
        self.on_diagnostics: Optional[Callable[[str, list], None]] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        return self._ready and bool(self._client) and self._client.is_alive()

    def start(self, cmd: list[str]) -> None:
        self._client = LspClient(
            cmd,
            on_notification=self._handle_notification,
            after_fn=self._after_fn,
            cwd=self._root,
        )
        self._initialize()

    def stop(self) -> None:
        if self._client:
            self._client.shutdown()
            self._client = None
        self._ready = False

    # ── File lifecycle ────────────────────────────────────────────────────────

    def open_file(self, path: str, text: str,
                  language_id: str = "python") -> None:
        if not self.ready:
            return
        uri = path_to_uri(path)
        self._versions[uri] = 1
        self._client.notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": 1,
                "text": text,
            }
        })

    def change_file(self, path: str, text: str) -> None:
        if not self.ready:
            return
        uri = path_to_uri(path)
        v   = self._versions.get(uri, 0) + 1
        self._versions[uri] = v
        self._client.notify("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": v},
            "contentChanges": [{"text": text}],
        })

    def close_file(self, path: str) -> None:
        if not self.ready:
            return
        uri = path_to_uri(path)
        self._versions.pop(uri, None)
        self._client.notify("textDocument/didClose", {
            "textDocument": {"uri": uri}
        })

    def save_file(self, path: str) -> None:
        if not self.ready:
            return
        self._client.notify("textDocument/didSave", {
            "textDocument": {"uri": path_to_uri(path)}
        })

    # ── Requests ──────────────────────────────────────────────────────────────

    def hover(self, path: str, line: int, col: int,
              callback: Callable[[dict | None], None]) -> None:
        if not self.ready:
            return
        self._client.request("textDocument/hover", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": {"line": line, "character": col},
        }, lambda result, _err: callback(result))

    def definition(self, path: str, line: int, col: int,
                   callback: Callable[[list | None], None]) -> None:
        if not self.ready:
            return
        self._client.request("textDocument/definition", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": {"line": line, "character": col},
        }, lambda result, _err: callback(result))

    def completion(self, path: str, line: int, col: int,
                   callback: Callable[[list], None]) -> None:
        if not self.ready:
            return
        def _cb(result, _err):
            if result is None:
                callback([])
                return
            # result may be a list or a CompletionList object
            items = result if isinstance(result, list) else result.get("items", [])
            callback(items)
        self._client.request("textDocument/completion", {
            "textDocument": {"uri": path_to_uri(path)},
            "position":     {"line": line, "character": col},
            "context":      {"triggerKind": 1},   # Invoked
        }, _cb)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _initialize(self) -> None:
        root_uri = path_to_uri(self._root) if self._root else ""
        self._client.request("initialize", {
            "processId": os.getpid(),
            "rootUri":   root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": False,
                        "didSave": True,
                    },
                    "publishDiagnostics": {"relatedInformation": False},
                    "hover":      {"contentFormat": ["plaintext", "markdown"]},
                    "definition": {"linkSupport": False},
                    "completion": {
                        "completionItem": {
                            "snippetSupport": False,
                            "documentationFormat": ["plaintext"],
                        }
                    },
                }
            },
            "workspaceFolders": None,
        }, self._on_init_response)

    def _on_init_response(self, result, error) -> None:
        if error:
            return
        self._client.notify("initialized", {})
        self._ready = True

    def _handle_notification(self, method: str, params: dict) -> None:
        if method == "textDocument/publishDiagnostics":
            uri   = params.get("uri", "")
            diags = params.get("diagnostics", [])
            if self.on_diagnostics:
                self.on_diagnostics(uri, diags)
