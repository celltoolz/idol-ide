"""Generated form code must not flag itself in IDOL's own Problems panel.

This is the suite that closes the gap that cost several manual round-trips:
nothing lints generated projects, so defects in codegen output were only ever
found by opening a file and looking at it.

Real `generate()` output is run through real ruff with an explicit `--select`,
because `I` is not a default rule on the pinned version — asserting the block is
genuinely sorted rather than that this ruff happens to skip the check.
"""
from __future__ import annotations

import pytest

from designer.codegen import _sorted_import_lines, generate
from designer.model import ComponentDescriptor, FormModel, WidgetDescriptor

CHECKED_RULES = "I,E4,F"


# ── the ordering helper ──────────────────────────────────────────────────────

def test_bare_form_imports_only_tkinter():
    assert _sorted_import_lines([], False) == ["import tkinter as tk"]


def test_same_module_from_imports_merge_and_sort():
    assert _sorted_import_lines(
        ["from tkinter import ttk", "from tkinter import filedialog",
         "from tkinter import colorchooser"], False
    ) == ["import tkinter as tk",
          "from tkinter import colorchooser, filedialog, ttk"]


def test_comma_separated_import_splits():
    assert _sorted_import_lines(["import socket, threading"], False) == [
        "import socket", "import threading", "import tkinter as tk"]


def test_third_party_is_a_separate_section():
    assert _sorted_import_lines([], True) == [
        "import os", "import tkinter as tk", "", "from PIL import Image, ImageTk"]


def test_stdlib_sorts_alphabetically():
    assert _sorted_import_lines(
        ["import struct", "import socket", "import threading"], False
    ) == ["import socket", "import struct", "import threading",
          "import tkinter as tk"]


def test_unknown_module_is_classified_third_party():
    """Classification is via sys.stdlib_module_names, so a future component
    pulling in a third-party package groups itself with no code change here."""
    assert _sorted_import_lines(["import numpy"], False) == [
        "import tkinter as tk", "", "import numpy"]


# ── real forms, end to end ───────────────────────────────────────────────────

def _basic():
    f = FormModel(name="Basic", title="Basic")
    f.widgets = [WidgetDescriptor(id="b1", type="Button", x=5, y=5, width=80, height=24)]
    return f


def _ttk():
    f = FormModel(name="WithTtk", title="Ttk")
    f.widgets = [WidgetDescriptor(id="t1", type="Treeview", x=5, y=5, width=200, height=100)]
    return f


def _images():
    f = FormModel(name="WithImages", title="Images")
    f.widgets = [WidgetDescriptor(id="l1", type="Label", x=5, y=5, width=80, height=24,
                                  props={"image": "images/logo.png"})]
    return f


def _socket():
    """Socket imports only emit when a connectable handler is wired, and
    `_scaffold_pb_transfer` holds a Progressbar *widget id*, not a flag."""
    f = FormModel(name="WithSocket", title="Socket")
    btn = WidgetDescriptor(id="b1", type="Button", x=5, y=5, width=80, height=24)
    btn.events["click"] = "_sock1_toggle_connect"
    f.widgets = [btn, WidgetDescriptor(id="pb1", type="Progressbar",
                                       x=5, y=40, width=200, height=20)]
    c = ComponentDescriptor(id="sock1", type="Socket")
    c.props["_scaffold_pb_transfer"] = "pb1"
    f.components = [c]
    return f


def _socket_labelled():
    """The branch where `import os as _os` is actually used."""
    f = _socket()
    f.name = "SocketLabelled"
    f.widgets.append(WidgetDescriptor(id="lbl1", type="Label",
                                      x=5, y=70, width=200, height=20))
    f.components[0].props["_scaffold_lbl_file"] = "lbl1"
    return f


def _kitchen_sink():
    f = FormModel(name="Everything", title="Everything")
    f.widgets = [
        WidgetDescriptor(id="b1", type="Button", x=5, y=5, width=80, height=24),
        WidgetDescriptor(id="t1", type="Treeview", x=5, y=40, width=200, height=100),
        WidgetDescriptor(id="l1", type="Label", x=5, y=150, width=80, height=24,
                         props={"image": "images/logo.png"}),
        WidgetDescriptor(id="pb1", type="Progressbar", x=5, y=190, width=200, height=20),
    ]
    f.widgets[0].events["click"] = "_sock1_toggle_connect"
    f.widgets[1].events["treeselect"] = "_cd1_show_open"
    sock = ComponentDescriptor(id="sock1", type="Socket")
    sock.props["_scaffold_pb_transfer"] = "pb1"
    f.components = [ComponentDescriptor(id="cd1", type="CommonDialog"), sock]
    return f


ALL_FORMS = [_basic, _ttk, _images, _socket, _socket_labelled, _kitchen_sink]
FORM_IDS = [b().name for b in ALL_FORMS]


@pytest.mark.parametrize("builder", ALL_FORMS, ids=FORM_IDS)
def test_generated_form_is_lint_clean(builder, lint_source):
    f = builder()
    assert lint_source(generate(f), CHECKED_RULES, f"{f.name}.py") == []


@pytest.mark.parametrize("builder", ALL_FORMS, ids=FORM_IDS)
def test_generated_form_compiles(builder):
    f = builder()
    compile(generate(f), f"{f.name}.py", "exec")


@pytest.mark.parametrize("builder", ALL_FORMS, ids=FORM_IDS)
def test_regeneration_is_stable(builder):
    """Reordering churn would make every autogen run a spurious diff."""
    f = builder()
    assert generate(f) == generate(f)


def test_marker_block_is_separated_from_the_imports():
    """Without a blank line isort reads the marker comments as part of the
    import block — enough to trip I001 on a form whose only import is tkinter."""
    src = generate(_basic())
    lines = src.splitlines()
    marker = next(i for i, ln in enumerate(lines) if "IDOL:IMPORTS:BEGIN" in ln)
    assert lines[marker - 1] == ""


def test_unused_scaffold_import_is_omitted():
    """`_os` is only read by the label line; emitting it unconditionally left an
    unused import in generated code."""
    body = generate(_socket()).split("_pick_and_send_file")[1][:400]
    assert "import os as _os" not in body


def test_used_scaffold_import_is_emitted():
    src = generate(_socket_labelled())
    assert "import os as _os" in src and "_os.path.basename" in src


def test_user_imports_are_left_alone():
    """Imports inside the IDOL:IMPORTS markers are user-owned; a linter flagging
    a user's own unsorted imports is a linter doing its job."""
    src = generate(_basic(), user_imports="import zlib\nimport abc")
    zone = src.split("IDOL:IMPORTS:BEGIN")[1].split("IDOL:IMPORTS:END")[0]
    assert zone.index("import zlib") < zone.index("import abc")
