#!/usr/bin/env python3
import os
import sys

from app import Notepad

if __name__ == "__main__":
    file_path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    app = Notepad(file_path)
    app.mainloop()
