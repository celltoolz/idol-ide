#!/usr/bin/env python3
import os
import sys
import tkinter as tk
from pathlib import Path


_SPLASH_MS  = 2500   # how long the splash stays up
_LOGO_WIDTH = 520    # display width of the logo image


def _show_splash(app: tk.Tk) -> None:
    """Display a frameless splash screen; reveal *app* when it closes."""
    logo_path = Path(__file__).parent / "images" / "gitPIDE.png"

    splash = tk.Toplevel(app)
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)
    splash.configure(bg="#0d1117")

    try:
        from PIL import Image, ImageTk
        img = Image.open(logo_path)
        ratio = _LOGO_WIDTH / img.width
        img = img.resize((_LOGO_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        splash._photo = photo
        lbl = tk.Label(splash, image=photo, bg="#0d1117", bd=0)
    except Exception:
        lbl = tk.Label(
            splash,
            text="IDOL\nIntegrated Development and Objective Learning\n\ncreated by gitPIDE",
            bg="#0d1117", fg="#cccccc",
            font=("Segoe UI", 18, "bold"),
            padx=60, pady=40,
        )
    lbl.pack()

    # Center on screen
    splash.update_idletasks()
    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    w  = splash.winfo_width()
    h  = splash.winfo_height()
    splash.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _dismiss():
        try:
            splash.destroy()
        except Exception:
            pass

    # Delay click-to-dismiss by 500ms — on macOS the launch click can fire
    # <Button-1> on the splash immediately and dismiss it before it's seen.
    splash.after(500, lambda: splash.bind("<Button-1>", lambda _: _dismiss()))
    splash.after(_SPLASH_MS, _dismiss)


if __name__ == "__main__":
    file_path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None

    from app import IDOL
    app = IDOL(file_path)
    _show_splash(app)
    app.mainloop()
