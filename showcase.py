#!/usr/bin/env python3
"""Runs Cadence through its own features so you can record a demo.

Start it, put ScreenToGif over the window, hit record. The script drives the app on a
timer with a caption strip along the bottom saying what is happening, so the recording
explains itself without narration.

It uses the two fake controllers, so nothing needs plugging in, and macro output is
switched off, so the clicks it demonstrates never reach your desktop.

    python showcase.py              full run, about 95 seconds
    python showcase.py --fast       same beats, roughly half the time
    python showcase.py --loop       start again when it reaches the end
"""

import sys
import time
import tkinter as tk

from cadence import app as A
from cadence.theme import (BG, PANEL, PANEL_2, EDGE, TEXT, MUTED, DIM, TINT,
                           BRAND, BRAND_HI, ACCENT)
from cadence.macros import Rule

FAST = "--fast" in sys.argv
LOOP = "--loop" in sys.argv


def beats():
    """Every step: (seconds to hold, heading, sub-line, what to do).

    Kept as data so the pacing can be retimed without touching the actions."""
    return [
        (5, "Cadence", "Controller timing, pad testing and macros in one window.", None),
        (5, "The big number is the gap",
         "Time between the start of one press and the start of the next.",
         lambda a: a.show_tab("timing")),
        (6, "Every press lands in the log",
         "Gap, whole Rocket League ticks, how long you held it, stick direction.", None),
        (6, "The strip draws it to scale",
         "One row per button. Bar width is hold time, the bracket above is the gap.",
         None),
        (5, "Nothing finer than the hardware",
         "Pads report every 4 to 8 ms, so gaps are rounded to what can be measured.",
         None),
        (4, "Set a target to practise against",
         "Pick a gap and how close counts as a hit.", target_on),
        (7, "Hits and misses tint the log",
         "Amber landed inside the window, red did not. The rate tracks your last 25.",
         None),
        (5, "Every slot, live", "All four XInput slots read at once, on any tab.",
         lambda a: a.show_tab("pads")),
        (6, "Press anything to prove it works",
         "Buttons light up as they arrive. Sticks and triggers move with them.", None),
        (6, "XInput hides the brand",
         "Names come from the USB vendor id. When that is a guess, Cadence says so.",
         None),
        (5, "Pick the layout yourself",
         "PlayStation names and glyphs, drawn as a DualShock.",
         lambda a: set_scheme(a, "playstation")),
        (5, "Or a Switch pad",
         "Nintendo mirrors A/B and X/Y, which is where mislabelling usually starts.",
         lambda a: set_scheme(a, "nintendo")),
        (4, "Back to Xbox", "The bits underneath never changed. Only the names did.",
         lambda a: set_scheme(a, "xbox")),
        (5, "Measure your own pad",
         "Some pads send nothing while idle, so the rate is read while a stick moves.",
         calibrate),
        (5, "Bind a pad button to a macro",
         "Hold or toggle, mouse or keyboard, at whatever rate you set.",
         lambda a: a.show_tab("macros")),
        (5, "Press the button you want",
         "No list of sixteen names to scroll. Cadence listens for the next press.",
         capture_trigger),
        (5, "Arm it", "The mark in the title bar lights while macros are live.",
         arm),
        (7, "Holding RB fires clicks",
         "Ten a second here. The counter climbs while the button is down.",
         fire),
        (6, "Advanced adds the rest",
         "Duty cycle, random rate, click and time limits, fixed-position clicking.",
         advanced),
        (7, "Three ways to stop it",
         "The arm switch, a panic key that works unfocused, or the mouse in a corner.",
         None),
        (5, "Check output works first",
         "It types a known word into a box so you know before you point it at a game.",
         None),
        (4, "Disarmed", "Nothing fires until you say so.", disarm),
        (6, "Cadence", "github.com/KayTwoOne/Cadence", lambda a: a.show_tab("timing")),
    ]


# ---------------------------------------------------------------- actions
def target_on(a):
    t = a.tabs["timing"]
    if not t.target_on:
        t.toggle_target()
    t.target_var.set("60")
    t.tol_var.set("25")
    t.read_target()


def set_scheme(a, key):
    for slot in range(4):
        a.schemes.set_override(slot, key)
    for tab in a.tabs.values():
        if hasattr(tab, "on_scheme_change"):
            tab.on_scheme_change()


def calibrate(a):
    a.show_tab("pads")
    a.tabs["pads"].cards[0].calibrate()


def capture_trigger(a):
    mt = a.tabs["macros"]
    if not mt.capturing:
        mt.capture_trigger()
    mt.offer_button(0, "RB")


def arm(a):
    if not a.engine.armed_master:
        a.tabs["macros"].toggle_master()


def fire(a):
    rule = a.tabs["macros"].cur
    if rule:
        rule.rate_value, rule.rate_unit = 10, "second"
    a.engine.handle(0, "RB", True)


def advanced(a):
    a.engine.handle(0, "RB", False)
    mt = a.tabs["macros"]
    if not mt.advanced:
        mt.toggle_advanced()


def disarm(a):
    a.engine.handle(0, "RB", False)
    if a.engine.armed_master:
        a.tabs["macros"].toggle_master()


# ---------------------------------------------------------------- caption strip
class Caption:
    """A band across the bottom of the window carrying the current beat."""

    def __init__(self, app):
        self.app = app
        ui = app.ui
        self.frame = tk.Frame(app.shell, bg=PANEL_2, height=ui.px(76))
        self.frame.pack_propagate(False)
        self.frame.grid(row=9, column=0, sticky="ew")
        tk.Frame(app.shell, bg=EDGE, height=1).grid(row=8, column=0, sticky="ew")

        inner = tk.Frame(self.frame, bg=PANEL_2)
        inner.pack(fill="both", expand=True, padx=22, pady=12)

        self.dot = tk.Canvas(inner, width=ui.px(10), height=ui.px(10), bg=PANEL_2,
                             highlightthickness=0)
        self.dot_id = self.dot.create_oval(*ui.s(0, 0, 10, 10), fill=BRAND_HI,
                                           outline="")
        self.dot.pack(side="left", padx=(0, 12), pady=(6, 0), anchor="n")

        text = tk.Frame(inner, bg=PANEL_2)
        text.pack(side="left", fill="both", expand=True)
        self.head = tk.Label(text, text="", bg=PANEL_2, fg=TEXT,
                             font=ui.f(15, "semi"), anchor="w")
        self.head.pack(fill="x")
        self.sub = tk.Label(text, text="", bg=PANEL_2, fg=MUTED, font=ui.f(11),
                            anchor="w")
        self.sub.pack(fill="x")

        self.count = tk.Label(inner, text="", bg=PANEL_2, fg=DIM, font=ui.d(9))
        self.count.pack(side="right", anchor="s")

        self.bar = tk.Canvas(self.frame, height=ui.px(3), bg=PANEL, highlightthickness=0)
        self.bar.pack(side="bottom", fill="x")
        self.bar_id = self.bar.create_rectangle(0, 0, 0, ui.px(3), fill=BRAND_HI,
                                                width=0)

    def show(self, index, total, head, sub):
        self.head.configure(text=head)
        self.sub.configure(text=sub)
        self.count.configure(text=f"{index + 1} / {total}")

    def progress(self, fraction):
        self.bar.coords(self.bar_id, 0, 0, self.bar.winfo_width() * fraction,
                        self.app.ui.px(3))


# ---------------------------------------------------------------- driver
class Showcase:
    def __init__(self, app):
        self.app = app
        self.caption = Caption(app)
        self.steps = beats()
        self.index = -1
        self.speed = 0.55 if FAST else 1.0
        self.started = 0.0
        self.hold = 0.0
        app.root.after(900, self.next_step)
        app.root.after(60, self.tick)

    def next_step(self):
        self.index += 1
        if self.index >= len(self.steps):
            if LOOP:
                self.index = 0
                reset(self.app)
            else:
                self.caption.show(len(self.steps) - 1, len(self.steps),
                                  "Done", "Stop your recording whenever you like.")
                self.caption.progress(1.0)
                return
        secs, head, sub, action = self.steps[self.index]
        self.caption.show(self.index, len(self.steps), head, sub)
        if action:
            try:
                action(self.app)
            except Exception as exc:
                print(f"step {self.index} ({head}) raised: {exc}")
        self.hold = secs * self.speed
        self.started = time.perf_counter()
        self.app.root.after(int(self.hold * 1000), self.next_step)

    def tick(self):
        if self.hold:
            self.caption.progress(
                min(1.0, (time.perf_counter() - self.started) / self.hold))
        self.app.root.after(60, self.tick)


def reset(app):
    app.engine.set_master(False)
    set_scheme(app, "xbox")
    t = app.tabs["timing"]
    if t.target_on:
        t.toggle_target()
    if app.tabs["macros"].advanced:
        app.tabs["macros"].toggle_advanced()
    app.show_tab("timing")


def main():
    root = tk.Tk()
    # Demo pads, and output off so the macro beats never touch the real mouse.
    app = A.App(root, A.DemoReader(), demo=True, live_output=False)
    app.shell.grid_rowconfigure(9, weight=0)
    Showcase(app)
    root.mainloop()


if __name__ == "__main__":
    main()
