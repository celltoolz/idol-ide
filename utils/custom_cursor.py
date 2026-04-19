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

# Arrow + question mark cursor, 32x32.
# 'X' = set pixel, '.' = transparent.  Each row is exactly 32 chars.
# All column indices are 0-based.
#
# Arrow tip at row 2, col 2 (hotspot declared as 0,0 — 2px above-left of tip).
# Arrow grows 1px/row from 1px at row 2 to peak 8px (cols 2-9) at row 9,
# then the left edge tapers inward rows 10-16 forming the tail.
#
# ?-mark: rows 10-19, positioned clear of the arrow body
#   row 10: top arc        cols 15-17
#   row 11: arc sides      cols 14, 18
#   row 12: right side     col 18
#   row 13: bend           col 18
#   rows 14-16: stem       cols 16-17 tapering to col 16
#   rows 17, 19: dot       col 16  (two-pixel dot with gap at row 18)
_GRID = [
    "................................",  #  0  blank
    "................................",  #  1  blank
    "..X.............................",  #  2  arrow tip 1px       col 2
    "..XX............................",  #  3  arrow 2px           cols 2-3
    "..XXX...........................",  #  4  arrow 3px           cols 2-4
    "..XXXX..........................",  #  5  arrow 4px           cols 2-5
    "..XXXXX.........................",  #  6  arrow 5px           cols 2-6
    "..XXXXXX........................",  #  7  arrow 6px           cols 2-7
    "..XXXXXXX.......................",  #  8  arrow 7px           cols 2-8
    "..XXXXXXXX......................",  #  9  arrow peak 8px      cols 2-9
    "..XXXXX........XXX..............",  # 10  arrow 5px cols 2-6  | ? top arc   cols 15-17
    "..XX.XX.......X...X.............",  # 11  arrow diagonal 2-3,5-6 | ? arc sides cols 14,18
    "..X...XX..........X.............",  # 12  arrow col 2, cols 6-7  | ? right     col 18
    "......XX..........X.............",  # 13  arrow cols 6-7      | ? bend      col 18
    ".......XX.......XX..............",  # 14  arrow tail cols 7-8 | ? stem      cols 16-17
    "........XX......X...............",  # 15  arrow tail cols 8-9 | ? stem      col 16
    "........XX......X...............",  # 16  arrow tail cols 8-9 | ? bottom    col 16
    "................X...............",  # 17  (arrow done)        | ? dot       col 16
    "................................",  # 18  blank gap
    "................X...............",  # 19  ? dot (second row)  col 16
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
    return ["".join("X" if out[r][c] else "." for c in range(_W)) for r in range(_H)]


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
    mask_path = os.path.join(_tmpdir, "mask.xbm")

    with open(cursor_path, "w") as f:
        f.write(_xbm(_to_bits(_GRID), "cur"))
    with open(mask_path, "w") as f:
        f.write(_xbm(_to_bits(_dilate(_GRID)), "mask"))

    _cursor_str = f"@{cursor_path} {mask_path} black white"
    return _cursor_str
