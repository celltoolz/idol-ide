"""Turning `No module named 'X'` into something the user can act on.

Nothing else in IDOL can catch a missing dependency — ruff never resolves
imports, `compile()` never executes them — so the run output is the only place
it is visible. The offer is only useful if it names a package that exists:
`pip install PIL` fails outright, and `pip install sklearn` installs a stub
whose whole purpose is to tell you that you wanted scikit-learn.
"""
from __future__ import annotations

import sys

import pytest

from utils import missing_module as mm
from widgets.output import OutputPanel

_offer = OutputPanel._offer_missing_module


# ── Parsing ──────────────────────────────────────────────────────────────────

def test_parses_the_module_name():
    text = ("Traceback (most recent call last):\n"
            '  File "main.py", line 3, in <module>\n'
            "    from PIL import Image\n"
            "ModuleNotFoundError: No module named 'PIL'\n")
    assert mm.parse(text) == "PIL"


def test_takes_the_last_error_not_the_first():
    """A run can print several tracebacks; the one that ended it is the one
    worth offering to fix."""
    text = ("No module named 'first'\n"
            "...caught and carried on...\n"
            "No module named 'second'\n")
    assert mm.parse(text) == "second"


def test_dotted_submodule_is_kept_whole():
    assert mm.parse("No module named 'google.protobuf'") == "google.protobuf"


def test_no_error_is_none():
    assert mm.parse("all fine\nProcess finished with exit code 0\n") is None


# ── Name mapping ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module,pypi", [
    ("PIL", "pillow"),
    ("cv2", "opencv-python"),
    ("sklearn", "scikit-learn"),
    ("yaml", "PyYAML"),
    ("bs4", "beautifulsoup4"),
    ("win32com", "pywin32"),
])
def test_import_name_maps_to_the_package_that_provides_it(module, pypi):
    assert mm.distribution_for(module) == pypi


@pytest.mark.parametrize("module,conda_name", [
    ("cv2", "opencv"),          # opencv-python on PyPI
    ("fitz", "pymupdf"),        # PyMuPDF on PyPI
    ("yaml", "pyyaml"),
    ("psycopg2", "psycopg2"),   # psycopg2-binary on PyPI
])
def test_conda_names_differ_where_conda_differs(module, conda_name):
    """Offering a conda user a PyPI-only name fails at the moment the offer
    was supposed to help."""
    assert mm.distribution_for(module, conda=True) == conda_name


def test_unknown_module_falls_back_to_its_own_name():
    assert mm.distribution_for("requests") == "requests"
    assert mm.distribution_for("some_private_thing") == "some_private_thing"


def test_dotted_module_resolves_by_longest_prefix():
    assert mm.distribution_for("google.protobuf") == "protobuf"
    # No entry for the parent alone — fall back to the top-level name.
    assert mm.distribution_for("google.cloud.storage") == "google"


def test_submodule_of_a_mapped_package_uses_the_package():
    assert mm.distribution_for("PIL.Image") == "pillow"


# ── Standard library ─────────────────────────────────────────────────────────

def test_stdlib_modules_are_recognised():
    assert mm.is_stdlib("tkinter")
    assert mm.is_stdlib("sqlite3")
    assert mm.is_stdlib("os.path")


def test_third_party_modules_are_not_stdlib():
    assert not mm.is_stdlib("PIL")
    assert not mm.is_stdlib("requests")


def test_stdlib_check_uses_the_real_name_set():
    """Guards against the table-shaped version of this that would rot."""
    assert "tkinter" in sys.stdlib_module_names


# ── The offer itself ─────────────────────────────────────────────────────────

class _Runner:
    def __init__(self, returncode=1):
        self.returncode = returncode


class _Panel:
    """Only what _offer_missing_module touches."""

    def __init__(self, text: str, returncode: int = 1, resolve=True):
        self._text_value = text
        self._runner = _Runner(returncode)
        self.written: list[tuple[str, str]] = []
        self.offers: list[tuple[str, str, str]] = []
        self.resolve_missing_module = (
            (lambda m: ("pillow", "conda")) if resolve else None)
        self.on_install_module = (lambda p: None) if resolve else None

    @property
    def _text(self):
        outer = self

        class _T:
            def get(self, *_a):
                return outer._text_value
        return _T()

    def write(self, text, tag=None):
        self.written.append((text, tag))

    def _write_install_offer(self, module, package, backend):
        self.offers.append((module, package, backend))


def test_offers_an_install_for_a_third_party_module():
    p = _Panel("ModuleNotFoundError: No module named 'PIL'\n")
    _offer(p)
    assert p.offers == [("PIL", "pillow", "conda")]


def test_stdlib_module_is_explained_not_offered():
    """`pip install tkinter` cannot fix an interpreter built without it."""
    p = _Panel("ModuleNotFoundError: No module named 'tkinter'\n")
    _offer(p)
    assert p.offers == []
    assert any("standard library" in t for t, _ in p.written)


def test_successful_run_offers_nothing():
    p = _Panel("No module named 'PIL'\n", returncode=0)
    _offer(p)
    assert p.offers == []
    assert p.written == []


def test_no_offer_without_a_host_to_perform_it():
    p = _Panel("No module named 'PIL'\n", resolve=False)
    _offer(p)
    assert p.offers == []


def test_host_declining_suppresses_the_offer():
    p = _Panel("No module named 'PIL'\n")
    p.resolve_missing_module = lambda _m: None
    _offer(p)
    assert p.offers == []
