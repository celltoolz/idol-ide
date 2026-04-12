"""Ollama local LLM client — health check, one-shot generate, streaming generate."""
from __future__ import annotations

import sys
import threading
from typing import Callable

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

_BASE_URL  = "http://127.0.0.1:11434"
_DEFAULT_MODEL = "qwen2.5-coder"
_TIMEOUT_HEALTH  = 5    # seconds — allow for IPv4/IPv6 fallback on tunnels
_TIMEOUT_GENERATE = 60  # seconds — give the model time to respond


def _dbg(msg: str) -> None:
    print(f"[ollama_client] {msg}", file=sys.stderr, flush=True)


def set_base_url(url: str) -> None:
    """Override the Ollama server URL (e.g. to tunnel through to a remote host)."""
    global _BASE_URL
    _BASE_URL = url.rstrip("/")
    _dbg(f"set_base_url → {_BASE_URL!r}")


def get_base_url() -> str:
    return _BASE_URL


# ── Health check ──────────────────────────────────────────────────────────────

def is_available() -> bool:
    """Return True if the Ollama server is reachable (blocking, fast)."""
    if not _REQUESTS_OK:
        _dbg("is_available: requests not installed")
        return False
    url = f"{_BASE_URL}/api/tags"
    _dbg(f"is_available: GET {url!r} timeout={_TIMEOUT_HEALTH}s")
    try:
        r = _requests.get(url, timeout=_TIMEOUT_HEALTH)
        _dbg(f"is_available: status={r.status_code}")
        return r.status_code == 200
    except Exception as exc:
        _dbg(f"is_available: FAILED — {type(exc).__name__}: {exc}")
        return False


def check_async(callback: Callable[[bool], None]) -> None:
    """Non-blocking health check — calls callback(True/False) on a daemon thread."""
    def _run():
        result = is_available()
        _dbg(f"check_async → {result}")
        callback(result)
    threading.Thread(target=_run, daemon=True).start()


def list_models() -> list[str]:
    """Return list of locally available model names. Empty list if offline."""
    if not _REQUESTS_OK:
        return []
    try:
        r = _requests.get(f"{_BASE_URL}/api/tags", timeout=_TIMEOUT_HEALTH)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


# ── Generate ──────────────────────────────────────────────────────────────────

def generate(
    prompt: str,
    model: str = _DEFAULT_MODEL,
    on_chunk: Callable[[str], None] | None = None,
    on_done: Callable[[str], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    """Stream a response from Ollama in a background thread.

    on_chunk(text)  — called for each streamed token as it arrives
    on_done(full)   — called once with the complete response when finished
    on_error(msg)   — called if the request fails
    """
    def _run():
        if not _REQUESTS_OK:
            _dbg("generate: requests not installed")
            if on_error:
                on_error("requests library not available")
            return
        url = f"{_BASE_URL}/api/generate"
        _dbg(f"generate: POST {url!r} model={model!r}")
        try:
            r = _requests.post(
                url,
                json={"model": model, "prompt": prompt, "stream": True},
                stream=True,
                timeout=_TIMEOUT_GENERATE,
            )
            _dbg(f"generate: status={r.status_code}")
            r.raise_for_status()
        except Exception as exc:
            _dbg(f"generate: FAILED — {type(exc).__name__}: {exc}")
            if on_error:
                on_error(str(exc))
            return

        import json
        full = []
        try:
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                token = data.get("response", "")
                if token and on_chunk:
                    on_chunk(token)
                full.append(token)
                if data.get("done"):
                    break
        except Exception as exc:
            if on_error:
                on_error(str(exc))
            return

        if on_done:
            on_done("".join(full))

    threading.Thread(target=_run, daemon=True).start()


# ── Prompt builders ───────────────────────────────────────────────────────────

def prompt_for_element(title: str, what: str) -> str:
    """Build a learning-mode prompt for an IDE element."""
    return (
        f"You are a friendly Python tutor inside a beginner IDE called IDOL.\n"
        f"The user is hovering over '{title}': {what}\n\n"
        f"Give a short, encouraging explanation for a complete beginner (under 120 words). "
        f"Include one tiny concrete code example if relevant. "
        f"No markdown headers, no bullet points — just plain conversational text."
    )


def prompt_for_package(package_name: str) -> str:
    """Build a prompt for pip package usage examples."""
    return (
        f"You are a friendly Python tutor inside a beginner IDE.\n"
        f"Show 2 short, practical beginner-friendly code examples for the Python package '{package_name}'.\n"
        f"Use realistic, simple scenarios. Add a one-line comment above each example. "
        f"Keep the total response under 150 words. No markdown headers."
    )
