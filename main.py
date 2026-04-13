#!/usr/bin/env python3
import os
import sys
import tkinter as tk
from pathlib import Path


_SPLASH_MS   = 2500   # how long the splash stays up
_LOGO_WIDTH  = 520    # display width of the logo image


def _show_splash(root: tk.Tk) -> None:
    """Display a frameless splash screen centered on the primary monitor."""
    logo_path = Path(__file__).parent / "images" / "gitPIDE.png"

    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)
    splash.configure(bg="#0d1117")

    # Load and scale the logo
    try:
        from PIL import Image, ImageTk
        img = Image.open(logo_path)
        ratio = _LOGO_WIDTH / img.width
        img = img.resize((_LOGO_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        splash._photo = photo   # keep reference
        lbl = tk.Label(splash, image=photo, bg="#0d1117", bd=0)
    except Exception:
        # PIL not available — text-only fallback
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

    # Dismiss on click or after timer
    splash.bind("<Button-1>", lambda _: splash.destroy())
    splash.after(_SPLASH_MS, splash.destroy)


if __name__ == "__main__":
    file_path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None

    # Create a hidden root first so Toplevel (splash) has a parent,
    # then import and build the real app while the splash is visible.
    root = tk.Tk()
    root.withdraw()

    _show_splash(root)

    # Build the main app (imports are the slow part — this happens during splash)
    from app import IDOL
    app = IDOL(file_path)

    # Destroy the temporary root now that the real window exists
    root.destroy()

    app.mainloop()
