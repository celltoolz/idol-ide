"""UI_FONT — cross-platform font family for all IDE widgets.

Segoe UI on Windows, Helvetica Neue on macOS, DejaVu Sans on Linux.
Import as: from utils.ui_font import UI_FONT
"""
import sys

if sys.platform == "win32":
    UI_FONT = "Segoe UI"
elif sys.platform == "darwin":
    UI_FONT = "Helvetica Neue"
else:
    UI_FONT = "DejaVu Sans"
