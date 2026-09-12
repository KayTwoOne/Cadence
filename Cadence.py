#!/usr/bin/env python3
"""Cadence - Controller Input Suite.

Three tabs:
  Timing       one controller, every press, and the gaps between them
  Controllers  all four slots at once, with per-pad timing calibration
  Macros       bind a pad button to a stream of clicks or keypresses

Requirements : Windows 10/11 and Python 3.10+. No extra packages.
Run          : python Cadence.py
No controller: python Cadence.py --demo        two fake controllers
Dry run      : python Cadence.py --no-output   macros count but send nothing
"""

import sys
import traceback

from cadence.app import main

if __name__ == "__main__":
    try:
        main()
    except Exception:       # keep the error visible when launched by double-click
        traceback.print_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("Cadence crashed", traceback.format_exc())
        except Exception:
            input("Press Enter to close...")
