"""What to install when a run dies on `No module named 'X'`.

Pure lookup and parsing — no subprocess, no widgets. Two facts this module
exists to carry:

**The name you import is not the name you install.** `import PIL` comes from
`pillow`, `import cv2` from `opencv-python`, `import yaml` from `PyYAML`. Telling
a beginner to `pip install PIL` sends them to a dead end (there is no such
package), and `pip install sklearn` is worse — it installs a stub whose only
purpose is to tell you that you wanted `scikit-learn`. Offering an install
without this table would misfire on precisely the packages beginners hit first.

**conda and PyPI do not always agree either.** `opencv-python` on PyPI is
`opencv` on conda; `PyMuPDF` is `pymupdf`. Offering a conda user a name only
PyPI has fails at the exact moment the offer was meant to help.

Modules that are part of Python itself are deliberately *not* installable here —
see `is_stdlib`. A missing `tkinter` means the interpreter was built without it,
and `pip install tkinter` cannot fix that.
"""
from __future__ import annotations

import re
import sys

#: import name → (PyPI name, conda name). Only entries where the import name
#: differs from the package name, or where the two ecosystems disagree — a
#: module whose package shares its name needs no row and gets the fallback.
#: Dotted keys are matched longest-prefix-first, so `google.protobuf` wins over
#: a bare `google` entry if one is ever added.
_PACKAGES: dict[str, tuple[str, str]] = {
    "PIL":          ("pillow", "pillow"),
    "cv2":          ("opencv-python", "opencv"),
    "sklearn":      ("scikit-learn", "scikit-learn"),
    "skimage":      ("scikit-image", "scikit-image"),
    "yaml":         ("PyYAML", "pyyaml"),
    "bs4":          ("beautifulsoup4", "beautifulsoup4"),
    "dateutil":     ("python-dateutil", "python-dateutil"),
    "serial":       ("pyserial", "pyserial"),
    "Crypto":       ("pycryptodome", "pycryptodome"),
    "Cryptodome":   ("pycryptodomex", "pycryptodomex"),
    "docx":         ("python-docx", "python-docx"),
    "pptx":         ("python-pptx", "python-pptx"),
    "fitz":         ("PyMuPDF", "pymupdf"),
    "OpenGL":       ("PyOpenGL", "pyopengl"),
    "google.protobuf": ("protobuf", "protobuf"),
    "grpc":         ("grpcio", "grpcio"),
    "attr":         ("attrs", "attrs"),
    "jwt":          ("PyJWT", "pyjwt"),
    "dotenv":       ("python-dotenv", "python-dotenv"),
    "magic":        ("python-magic", "python-magic"),
    "usb":          ("pyusb", "pyusb"),
    "gi":           ("PyGObject", "pygobject"),
    "cairo":        ("pycairo", "pycairo"),
    "Xlib":         ("python-xlib", "python-xlib"),
    "zmq":          ("pyzmq", "pyzmq"),
    "nacl":         ("PyNaCl", "pynacl"),
    "OpenSSL":      ("pyOpenSSL", "pyopenssl"),
    "psycopg2":     ("psycopg2-binary", "psycopg2"),
    "MySQLdb":      ("mysqlclient", "mysqlclient"),
    "pkg_resources": ("setuptools", "setuptools"),
    "win32api":     ("pywin32", "pywin32"),
    "win32com":     ("pywin32", "pywin32"),
    "win32con":     ("pywin32", "pywin32"),
    "win32gui":     ("pywin32", "pywin32"),
    "pythoncom":    ("pywin32", "pywin32"),
    "pywintypes":   ("pywin32", "pywin32"),
}

_MISSING_RE = re.compile(r"No module named '([^']+)'")


def parse(text: str) -> str | None:
    """The module name from the last `No module named '...'` in *text*.

    The last, not the first: a run can print several tracebacks, and the one
    that ended it is the one worth offering to fix. Returns None when the text
    holds no such error.
    """
    found = _MISSING_RE.findall(text)
    return found[-1] if found else None


def is_stdlib(module: str) -> bool:
    """Is *module* part of Python itself?

    Then no package manager can supply it, and offering an install would send
    the user somewhere that cannot help. This is how a Linux `tkinter` or
    `sqlite3` failure gets explained instead of mis-offered — the interpreter
    was built without the module, which is a system-package or pyenv problem.

    Read from the running interpreter's `sys.stdlib_module_names`, not a table:
    it is authoritative and free. IDOL's interpreter and the user's may differ,
    but the stdlib name set barely moves between versions.
    """
    return module.split(".")[0] in sys.stdlib_module_names


def distribution_for(module: str, conda: bool = False) -> str:
    """The package name to install so that `import module` works.

    Falls back to the module's own top-level name, which is right for the large
    majority — `requests`, `numpy`, `flask` and friends all match.
    """
    parts = module.split(".")
    for i in range(len(parts), 0, -1):
        entry = _PACKAGES.get(".".join(parts[:i]))
        if entry:
            return entry[1] if conda else entry[0]
    return parts[0]
