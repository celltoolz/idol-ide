"""Custom learning-mode cursor — arrow + question mark.

On Windows/macOS the built-in 'question_arrow' system cursor looks great.
On Linux/X11 we generate a 32x32 XBM bitmap pair (cursor + mask) because
the system question_arrow is theme-dependent and often renders poorly.

The cursor is written once to a temp dir on first call and cached.
The temp dir is removed automatically on process exit via atexit.
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile

_W, _H = 32, 32

# Arrow (solid right-triangle, hotspot at 0,0) + question mark to its right.
# Exactly 32 characters per row.  'X' = set pixel, '.' = transparent.
#
# Arrow:  rows 0-11, width grows 1px per row (1..12)
# ?-mark: rows 9-16, positioned clear of the arrow tip
#   row  9: top arc    cols 15-17
#   row 10: arc sides  cols 14, 18
#   row 11: right side col 18
#   row 12: bend       col 17
#   rows 13-14: stem   col 16
#   row 15: gap
#   row 16: dot        col 16
_GRID = [
    "X...............................",  #  0
    "XX..............................",  #  1
    "XXX.............................",  #  2
    "XXXX............................",  #  3
    "XXXXX...........................",  #  4
    "XXXXXX..........................",  #  5
    "XXXXXXX.........................",  #  6
    "XXXXXXXX........................",  #  7
    "XXXXXXXXX.......................",  #  8
    "XXXXXXXXXX.....XXX..............",  #  9
    "XXXXXXXXXXX...X...X.............",  # 10
    "XXXXXXXXXXXX......X.............",  # 11
    ".................X..............",  # 12
    "................X...............",  # 13
    "................X...............",  # 14
    "................................",  # 15
    "................X...............",  # 16
    "................................",  # 17
    "................................",  # 18
    "................................",  # 19
    "................................",  # 20
    "................................",  # 21
    "................................",  # 22
    "................................",  # 23
    "................................",  # 24
    "................................",  # 25
    "................................",  # 26
    "................................",  # 27
    "................................",  # 28
    "................................",  # 29
    "................................",  # 30
    "................................",  # 31
]


def _to_bits(grid: list[str]) -> list[int]:
    """Grid → XBM byte list.  XBM stores bits LSB-first within each byte."""
    result = []
    for row in grid:
        row = row.ljust(_W, ".")
        for byte_idx in range(_W // 8):
            byte = 0
            for bit in range(8):
                if row[byte_idx * 8 + bit] == "X":
                    byte |= 1 << bit
            result.append(byte)
    return result


def _dilate(grid: list[str]) -> list[str]:
    """Expand every set pixel by 1 in all 8 directions to build the mask."""
    src = [[c == "X" for c in row.ljust(_W, ".")] for row in grid]
    out = [[False] * _W for _ in range(_H)]
    for r in range(_H):
        for c in range(_W):
            if src[r][c]:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < _H and 0 <= nc < _W:
                            out[nr][nc] = True
    return [
        "".join("X" if out[r][c] else "." for c in range(_W))
        for r in range(_H)
    ]


def _xbm(bits: list[int], name: str = "cur") -> str:
    hex_str = ", ".join(f"0x{b:02x}" for b in bits)
    return (
        f"#define {name}_width {_W}\n"
        f"#define {name}_height {_H}\n"
        f"#define {name}_x_hot 0\n"
        f"#define {name}_y_hot 0\n"
        f"static unsigned char {name}_bits[] = {{\n"
        f"   {hex_str}}};\n"
    )


_tmpdir: str | None = None
_cursor_str: str | None = None


def get_learn_cursor() -> str:
    """Return the tkinter cursor string for learning mode.

    Windows / macOS : 'question_arrow'  (native, looks perfect)
    Linux / X11     : '@cursor.xbm mask.xbm black white'  (custom XBM)
    """
    if sys.platform in ("win32", "darwin"):
        return "question_arrow"

    global _tmpdir, _cursor_str
    if _cursor_str is not None:
        return _cursor_str

    _tmpdir = tempfile.mkdtemp(prefix="idol_cur_")
    atexit.register(shutil.rmtree, _tmpdir, ignore_errors=True)

    cursor_path = os.path.join(_tmpdir, "cur.xbm")
    mask_path   = os.path.join(_tmpdir, "mask.xbm")

    with open(cursor_path, "w") as f:
        f.write(_xbm(_to_bits(_GRID), "cur"))
    with open(mask_path, "w") as f:
        f.write(_xbm(_to_bits(_dilate(_GRID)), "mask"))

    _cursor_str = f"@{cursor_path} {mask_path} black white"
    return _cursor_str
