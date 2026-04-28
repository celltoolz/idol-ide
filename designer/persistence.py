from __future__ import annotations

"""
.form.json save/load and event body extraction.

File format:
  {
    "version": 1,
    "codegen_checksum": "sha256:<hex>",   // SHA-256 of the last generated .py
    "form": { ...FormModel fields... }
  }

The checksum lets app.py detect manual edits before re-entering Designer mode.
"""

import ast
import hashlib
import json
import textwrap
from pathlib import Path

from .model import FormModel


_VERSION = 1


# ── Save / load ───────────────────────────────────────────────────────────────

def save(form: FormModel, json_path: Path, py_checksum: str = "") -> None:
    """Write *form* to *json_path* as a .form.json file."""
    payload = {
        "version": _VERSION,
        "codegen_checksum": py_checksum,
        "form": form.to_dict(),
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load(json_path: Path) -> tuple[FormModel, str]:
    """Load a .form.json and return (FormModel, stored_checksum).

    Returns a blank FormModel and empty checksum if the file is missing or corrupt.
    """
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        form = FormModel.from_dict(payload.get("form", {}))
        checksum = payload.get("codegen_checksum", "")
        return form, checksum
    except Exception:
        return FormModel(), ""


# ── Checksum helpers ──────────────────────────────────────────────────────────

def compute_checksum(py_path: Path) -> str:
    """Return 'sha256:<hex>' for the contents of *py_path*, or '' if missing."""
    try:
        data = py_path.read_bytes()
        return "sha256:" + hashlib.sha256(data).hexdigest()
    except FileNotFoundError:
        return ""


def was_modified(py_path: Path, stored_checksum: str) -> bool:
    """True when *py_path* has been edited since the last codegen save."""
    if not stored_checksum:
        return False
    return compute_checksum(py_path) != stored_checksum


# ── Event body extraction ─────────────────────────────────────────────────────

def extract_event_bodies(py_path: Path) -> dict[str, str]:
    """Return {method_name: dedented_body_str} for event methods in the generated class.

    Skips __init__ and _build_ui.  All other underscore-prefixed methods are
    treated as event stubs and their bodies are extracted for regen splicing.
    """
    try:
        source = py_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    lines = source.splitlines()
    bodies: dict[str, str] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            name = item.name
            if name in ("__init__", "_build_ui") or not name.startswith("_"):
                continue
            body = _extract_body(item, lines)
            if body is not None:
                bodies[name] = body

    return bodies


def _extract_body(fn: ast.FunctionDef, lines: list[str]) -> str | None:
    """Return the dedented body string for *fn*, or None on failure."""
    if not fn.body:
        return None
    # fn.body[0].lineno is 1-indexed; fn.end_lineno is 1-indexed inclusive
    start = fn.body[0].lineno - 1   # 0-indexed
    end = fn.end_lineno             # exclusive upper bound for slice
    body_lines = lines[start:end]
    return textwrap.dedent("\n".join(body_lines))
