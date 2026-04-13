#!/usr/bin/env python3
import os
import sys

from app import IDOL


if __name__ == "__main__":
    file_path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    app = IDOL(file_path)
    app.mainloop()
