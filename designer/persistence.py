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

def extract_user_imports(py_path: Path) -> str:
    """Return user import lines between IDOL:IMPORTS markers, or ''."""
    try:
        lines = py_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    begins = [i for i, l in enumerate(lines) if _IDOL_IMPORT_BEGIN in l]
    ends   = [i for i, l in enumerate(lines) if _IDOL_IMPORT_END   in l]
    if not begins or not ends:
        return ""
    return "\n".join(lines[begins[0] + 1 : ends[0]]).strip()


def extract_event_signatures(py_path: Path) -> dict[str, tuple[str, str]]:
    """Return {method_name: (params, return_ann)} for event methods.

    params     — everything after 'self' in the signature, e.g. 'event' or 'event: tk.Event'
    return_ann — return annotation string without '->', e.g. 'None', or '' if absent

    Only methods whose signature differs from the default '(self, *args)' are included,
    so callers can use .get(name, ("*args", "")) to fall back cleanly.
    """
    _, tree, _ = _parse(py_path)
    if tree is None:
        return {}

    sigs: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            name = item.name
            if name in ("__init__", "_build_ui", "_apply_anchor_layout") or not name.startswith("_"):
                continue
            params = _extract_params(item)
            ret    = ast.unparse(item.returns) if item.returns else ""
            if params != "*args" or ret:
                sigs[name] = (params, ret)
    return sigs


def _extract_params(fn: ast.FunctionDef) -> str:
    """Reconstruct the parameter string after 'self' from the AST."""
    args  = fn.args
    parts: list[str] = []
    for arg in args.args[1:]:   # skip self
        p = arg.arg
        if arg.annotation:
            p += f": {ast.unparse(arg.annotation)}"
        parts.append(p)
    if args.vararg:
        va = f"*{args.vararg.arg}"
        if args.vararg.annotation:
            va += f": {ast.unparse(args.vararg.annotation)}"
        parts.append(va)
    if args.kwarg:
        kw = f"**{args.kwarg.arg}"
        if args.kwarg.annotation:
            kw += f": {ast.unparse(args.kwarg.annotation)}"
        parts.append(kw)
    return ", ".join(parts)


def extract_event_bodies(py_path: Path) -> dict[str, str]:
    """Return {method_name: dedented_body_str} for event methods in the generated class.

    Skips __init__ and _build_ui.  All other underscore-prefixed methods are
    treated as event stubs and their bodies are extracted for regen splicing.
    """
    src, tree, lines = _parse(py_path)
    if tree is None:
        return {}

    bodies: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            name = item.name
            if name in ("__init__", "_build_ui", "_apply_anchor_layout") or not name.startswith("_"):
                continue
            body = _extract_body(item, lines)
            if body is not None:
                bodies[name] = body

    return bodies


# Tokens used to identify IDOL-generated blocks inside __init__
_IDOL_BEGIN = "IDOL:BEGIN"
_IDOL_END   = "IDOL:END"

# Tokens for the module-level user imports block
_IDOL_IMPORT_BEGIN = "IDOL:IMPORTS:BEGIN"
_IDOL_IMPORT_END   = "IDOL:IMPORTS:END"

# Token for the component initialization block (inside second IDOL:BEGIN block)
_IDOL_COMP_BEGIN = "IDOL:COMPONENTS:BEGIN"
_IDOL_COMP_END   = "IDOL:COMPONENTS:END"


def extract_init_user_zones(py_path: Path) -> tuple[str, str]:
    """Return (pre_build_ui, post_build_ui) user code from __init__.

    If IDOL:BEGIN/END markers are present uses string scanning; otherwise
    falls back to AST to extract the post-build zone only (legacy files).
    Both strings are stripped and dedented.
    """
    _, tree, lines = _parse(py_path)
    if tree is None:
        return "", ""

    # Find __init__ line bounds.
    # Use the *next sibling method's* start line as the end boundary rather than
    # item.end_lineno — AST end_lineno stops at the last statement and excludes
    # trailing comments (e.g. the closing IDOL:END marker after self._build_ui()).
    init_start = init_end = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        siblings = node.body
        for i, item in enumerate(siblings):
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                init_start = item.lineno - 1   # 0-indexed inclusive
                if i + 1 < len(siblings):
                    init_end = siblings[i + 1].lineno - 1   # 0-indexed exclusive
                else:
                    init_end = len(lines)

    if init_start is None:
        return "", ""

    init_lines = lines[init_start:init_end]
    begins = [i for i, l in enumerate(init_lines) if _IDOL_BEGIN in l]
    ends   = [i for i, l in enumerate(init_lines) if _IDOL_END   in l]

    if len(begins) >= 2 and len(ends) >= 2:
        pre_lines  = init_lines[ends[0] + 1 : begins[1]]
        post_lines = init_lines[ends[1] + 1 :]
        pre  = textwrap.dedent("\n".join(pre_lines)).strip()
        post = textwrap.dedent("\n".join(post_lines)).strip()
        return pre, post

    # Legacy fallback: AST extraction of post-build zone only
    return "", _extract_post_build_ast(tree, lines)


def _extract_post_build_ast(tree: ast.Module, lines: list[str]) -> str:
    """AST fallback for files without IDOL markers — extracts post-_build_ui lines."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
                continue
            for child in ast.walk(item):
                if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
                    func = child.value.func
                    if isinstance(func, ast.Attribute) and func.attr == "_build_ui":
                        start = child.lineno   # 0-indexed = line after _build_ui()
                        end   = item.end_lineno
                        if start >= end:
                            return ""
                        return textwrap.dedent("\n".join(lines[start:end])).strip()
    return ""


def extract_helper_methods(py_path: Path) -> str:
    """Return full source of class methods that are not __init__, _build_ui, or event stubs.

    These are public helper methods the user wrote that should survive regeneration.
    """
    _, tree, lines = _parse(py_path)
    if tree is None:
        return ""

    parts: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name in ("__init__", "_build_ui") or item.name.startswith("_"):
                continue
            # Include decorator lines (@property, @name.setter, @staticmethod, etc.)
            if item.decorator_list:
                start = item.decorator_list[0].lineno - 1
            else:
                start = item.lineno - 1
            end = item.end_lineno   # exclusive
            parts.append(textwrap.dedent("\n".join(lines[start:end])))

    return "\n\n".join(parts)


def _parse(py_path: Path) -> tuple[str, ast.Module | None, list[str]]:
    try:
        source = py_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "", None, []
    try:
        return source, ast.parse(source), source.splitlines()
    except SyntaxError:
        return source, None, source.splitlines()


def _extract_body(fn: ast.FunctionDef, lines: list[str]) -> str | None:
    """Return the dedented body string for *fn*, or None on failure."""
    if not fn.body:
        return None
    # fn.body[0].lineno is 1-indexed; fn.end_lineno is 1-indexed inclusive
    first_stmt = fn.body[0].lineno - 1  # 0-indexed line of first AST statement
    end = fn.end_lineno                 # exclusive upper bound for slice
    # AST skips comment lines, so fn.body[0].lineno misses comments that appear
    # between the def line and the first real statement.  Walk back to include them.
    body_indent = fn.col_offset + 4
    start = first_stmt
    for i in range(first_stmt - 1, fn.lineno - 1, -1):
        line = lines[i]
        stripped = line.strip()
        leading = len(line) - len(line.lstrip())
        if stripped == "" or (stripped.startswith("#") and leading >= body_indent):
            start = i
        else:
            break
    # Walk forward to include trailing comment lines at body indentation
    # (AST end_lineno stops at the last statement and excludes trailing comments)
    while end < len(lines):
        line = lines[end]
        stripped = line.strip()
        leading = len(line) - len(line.lstrip())
        if stripped.startswith("#") and leading >= body_indent:
            end += 1
        else:
            break
    body_lines = lines[start:end]
    return textwrap.dedent("\n".join(body_lines))
