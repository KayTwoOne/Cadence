"""Tab 2 - Controllers. Every slot at once: what it is, what it is doing, how well
it can be measured.

This is also where a pad gets calibrated. Some controllers snap their sticks to dead
zero while idle and send nothing at all, so the report rate cannot be measured from a
pad sitting on a desk. Wiggling a stick for a couple of seconds gives the estimator
the continuous stream it needs.
"""

import tkinter as tk

from .theme import (BG, PANEL, PANEL_2, RAISED, RAISED_HI, LINE, TEXT, MUTED, DIM,
                    BRAND, BRAND_HI, TINT, ACCENT, MISS, XBOX_A, XBOX_B, XBOX_X, XBOX_Y)
from .hardware import BUTTONS, BIT, LABEL, ASSUMED_REPORT_MS, REPORT_MIN_SAMPLES
from .controllers import SCHEMES, SCHEME_ORDER
from .padart import lit_pair

CAL_SECONDS = 4.0

COLOUR = {"A": XBOX_A, "B": XBOX_B, "X": XBOX_X, "Y": XBOX_Y,
          "LB": "#d6d6d6", "RB": "#d6d6d6", "LT": TINT, "RT": TINT,
          "LS": "#b7e07a", "RS": "#b7e07a", "UP": "#a8a8a8", "DOWN": "#a8a8a8",
          "LEFT": "#a8a8a8", "RIGHT": "#a8a8a8", "BACK": "#7a7a7a", "START": "#7a7a7a"}


class PadCard:
    """One controller slot, drawn as a card. Empty slots stay visible but recede, so
    the number of pads you have is readable at a glance."""

    def __init__(self, parent, app, slot):
        self.app, self.slot, self.ui = app, slot, app.ui
        ui = self.ui
        self.cal_until = 0.0
        self.cache = {}

        wrap = ui.panel(parent)
        self.wrap = wrap
        body = wrap.inner
        body.configure(padx=14, pady=12)

        head = tk.Frame(body, bg=PANEL)
        head.pack(fill="x")
        self.dot = tk.Canvas(head, width=ui.px(10), height=ui.px(10), bg=PANEL,
                             highlightthickness=0)
        self.dot_id = self.dot.create_oval(*ui.s(0, 0, 10, 10), fill=DIM, outline="")
        self.dot.pack(side="left", pady=(0, 2), padx=(0, 8))
        self.name = tk.Label(head, text=app.names[slot], bg=PANEL, fg=TEXT,
                             font=ui.f(12, "semi"), anchor="w", cursor="hand2")
        self.name.pack(side="left")
        self.name.bind("<Double-Button-1>", lambda e: app.rename(slot))
        ui.tooltip(self.name, "Double-click to rename this controller")
        self.presses = tk.Label(head, text="", bg=PANEL, fg=MUTED, font=ui.d(9))
        self.presses.pack(side="right")

        self.kind = tk.Label(body, text="not connected", bg=PANEL, fg=MUTED,
                             font=ui.f(9, "tight"), anchor="w")
        self.kind.pack(fill="x", pady=(1, 6))

        # Which button names to print. Detection is a hint, never the last word.
        scheme_row = tk.Frame(body, bg=PANEL)
        scheme_row.pack(fill="x", pady=(0, 8))
        tk.Label(scheme_row, text="LAYOUT", bg=PANEL, fg=DIM, font=ui.f(9, "tight"),
                 anchor="w").pack(side="left", padx=(0, 8))
        self.scheme_chips = ui.choice(
            scheme_row, [(k, SCHEMES[k].name.upper()) for k in SCHEME_ORDER],
            lambda: app.schemes.scheme_key(self.slot), self.pick_scheme, bg=PANEL)
        self.scheme_chips.pack(side="left")
        self.scheme_note = tk.Label(body, text="", bg=PANEL, fg=MUTED, font=ui.f(9),
                                    anchor="w", justify="left", wraplength=ui.px(330))
        self.scheme_note.pack(fill="x", pady=(0, 8))

        # live button grid: the fastest way to prove a pad works at all
        grid = tk.Frame(body, bg=PANEL)
        grid.pack(fill="x")
        self.lamps = {}
        for i, (_, key, label) in enumerate(BUTTONS):
            lamp = tk.Label(grid, text=label, font=ui.f(9, "semi"), width=5, pady=4,
                            bg=PANEL_2, fg=MUTED)
            lamp.grid(row=i // 8, column=i % 8, padx=1, pady=1, sticky="ew")
            self.lamps[key] = lamp
        self.grid_frame = grid

        sticks = tk.Frame(body, bg=PANEL)
        sticks.pack(fill="x", pady=(8, 0))
        self.stick_canvas = tk.Canvas(sticks, width=ui.px(150), height=ui.px(74),
                                      bg=PANEL, highlightthickness=0)
        self.stick_canvas.pack(side="left")
        self._build_sticks()

        readings = tk.Frame(sticks, bg=PANEL)
        readings.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.m_report = ui.metric(readings, "reports every", bg=PANEL)
        self.m_report.pack(fill="x")
        self.m_report.caption.configure(anchor="w")
        self.m_report.value.configure(anchor="w")
        self.m_res = ui.metric(readings, "resolution", bg=PANEL)
        self.m_res.pack(fill="x", pady=(4, 0))
        self.m_res.caption.configure(anchor="w")
        self.m_res.value.configure(anchor="w")

        self.cal_btn = ui.button(body, "MEASURE THIS PAD", self.calibrate, pad=(10, 5))
        self.cal_btn.pack(fill="x", pady=(10, 0))
        self.cal_note = tk.Label(body, text="", bg=PANEL, fg=MUTED, font=ui.f(8),
                                 anchor="w", justify="left", wraplength=ui.px(300))
        self.cal_note.pack(fill="x", pady=(4, 0))

    def _build_sticks(self):
        c, ui = self.stick_canvas, self.ui
        self.dots = {}
        for key, cx in (("LS", 37), ("RS", 112)):
            c.create_oval(*ui.s(cx - 30, 7, cx + 30, 67), outline=LINE, fill=BG,
                          width=1.5 * ui.S)
            c.create_line(*ui.s(cx - 30, 37, cx + 30, 37), fill=PANEL_2)
            c.create_line(*ui.s(cx, 7, cx, 67), fill=PANEL_2)
            self.dots[key] = (cx, 37, 22,
                              c.create_oval(*ui.s(cx - 6, 31, cx + 6, 43),
                                            fill=RAISED, outline=MUTED, width=1.5 * ui.S))
        c.create_text(*ui.s(37, 71), text="LEFT", fill=DIM, font=ui.f(7, "tight"))
        c.create_text(*ui.s(112, 71), text="RIGHT", fill=DIM, font=ui.f(7, "tight"))

    def pick_scheme(self, key):
        self.app.schemes.set_override(self.slot, key)
        self.relabel()
        self.scheme_chips.paint()
        for tab in self.app.tabs.values():
            if hasattr(tab, "on_scheme_change"):
                tab.on_scheme_change()

    def relabel(self):
        """Repaint every button name from the active scheme."""
        sch = self.app.schemes.scheme(self.slot)
        for key, lamp in self.lamps.items():
            lamp.configure(text=sch.label(key))
        guess = self.app.schemes.is_guess(self.slot)
        note = self.app.schemes.explain(self.slot)
        if self.slot not in self.app.connected:
            self.scheme_note.configure(text="", fg=MUTED)
        elif guess:
            self.scheme_note.configure(
                text=f"{note}. Names above are a guess - if they do not match the "
                     f"buttons on your pad, pick the right layout.", fg=ACCENT)
        else:
            self.scheme_note.configure(text=note, fg=MUTED)

    def calibrate(self):
        """Clear the estimate and ask for a few seconds of stick movement."""
        import time
        if self.slot not in self.app.connected:
            return
        self.app.poller.recalibrate(self.slot)
        self.cal_until = time.perf_counter() + CAL_SECONDS
        self.cache.pop("cal", None)

    def refresh(self, now):
        ui = self.ui
        app = self.app
        connected = self.slot in app.connected
        latest = app.poller.latest.get(self.slot)

        if self.cache.get("conn") != connected:
            self.cache["conn"] = connected
            self.dot.itemconfigure(self.dot_id, fill=BRAND_HI if connected else DIM)
            self.name.configure(fg=TEXT if connected else DIM)
            info = app.poller.info.get(self.slot, {})
            if connected:
                bits = [info.get("subtype", "gamepad"),
                        "wireless" if info.get("wireless") else "wired"]
                if info.get("battery"):
                    bits.append(f"battery {info['battery']}")
                self.kind.configure(text=" · ".join(bits), fg=MUTED)
            else:
                self.kind.configure(text="not connected", fg=DIM)
            self.cal_btn.configure(cursor="hand2" if connected else "arrow",
                                   fg=TEXT if connected else DIM)
            self.relabel()
            self.scheme_chips.paint()

        self.name.configure(text=app.names[self.slot])
        model = app.models.get(self.slot)
        n = len(model.presses) if model else 0
        self.presses.configure(text=f"{n} press{'' if n == 1 else 'es'}" if connected else "")

        mask, lt, rt, lx, ly, rx, ry = latest if latest else (0, 0, 0, 0, 0, 0, 0)
        for key, lamp in self.lamps.items():
            on = bool(mask & BIT[key])
            if self.cache.get(("lamp", key)) == on:
                continue
            self.cache[("lamp", key)] = on
            face = self.app.schemes.scheme(self.slot).faces.get(key) or COLOUR[key]
            fill, ink = lit_pair(face)
            lamp.configure(bg=fill if on else PANEL_2,
                           fg=ink if on else (MUTED if connected else DIM))
        for key, (vx, vy) in (("LS", (lx, ly)), ("RS", (rx, ry))):
            cx, cy, travel, dot = self.dots[key]
            px = cx + travel * max(-1, vx / 32767)
            py = cy - travel * max(-1, vy / 32767)
            self.stick_canvas.coords(dot, *ui.s(px - 6, py - 6, px + 6, py + 6))
            self.stick_canvas.itemconfigure(
                dot, fill=TINT if abs(vx) > 8000 or abs(vy) > 8000 else RAISED)

        if not connected:
            self.m_report.value.configure(text="—", fg=DIM)
            self.m_res.value.configure(text="—", fg=DIM)
            self.cal_note.configure(text="")
            return

        rep = app.poller.report_ms(self.slot)
        res = app.poller.resolution_ms(self.slot)
        if rep:
            self.m_report.value.configure(text=f"{rep:.2f} ms", fg=TEXT)
            self.m_report.caption.configure(text=f"REPORTS EVERY · {1000 / rep:,.0f} HZ")
            self.m_res.value.configure(text=f"±{res:.2f} ms", fg=TINT)
            self.m_res.caption.configure(text="RESOLUTION · MEASURED")
        else:
            self.m_report.value.configure(text="not measured", fg=MUTED)
            self.m_report.caption.configure(text="REPORTS EVERY")
            self.m_res.value.configure(text=f"±{res:.2f} ms", fg=MUTED)
            self.m_res.caption.configure(text=f"RESOLUTION · ASSUMING {ASSUMED_REPORT_MS:g} MS")

        got = app.poller.analog_samples(self.slot)
        if now < self.cal_until:
            left = self.cal_until - now
            self.cal_note.configure(
                text=f"Move the left stick in circles… {left:.1f}s  "
                     f"({got}/{REPORT_MIN_SAMPLES} samples)",
                fg=ACCENT)
        elif self.cache.get("cal") != bool(rep):
            self.cache["cal"] = bool(rep)
            if rep:
                self.cal_note.configure(
                    text="Measured from your own pad. Nothing finer than the resolution "
                         "above is real.", fg=MUTED)
            else:
                self.cal_note.configure(
                    text="Your pad sends nothing while it sits still, so the rate can "
                         "only be read while a stick or trigger is moving. Press the "
                         "button above and circle the left stick.", fg=MUTED)


class PadsTab:
    def __init__(self, parent, app):
        self.app = app
        self.ui = app.ui
        self.frame = tk.Frame(parent, bg=BG)
        self._build()

    def _build(self):
        ui, r = self.ui, self.frame
        intro = tk.Frame(r, bg=BG)
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        tk.Label(intro, text="EVERY SLOT, LIVE", bg=BG, fg=DIM, font=ui.f(8, "tight"),
                 anchor="w").pack(fill="x")
        tk.Label(intro, text="All four XInput slots are read at once, whichever tab you "
                             "are on. Press anything on a pad to confirm it is being "
                             "seen, and measure each one so its timing figures mean "
                             "something.",
                 bg=BG, fg=MUTED, font=ui.f(10), anchor="w", justify="left",
                 wraplength=ui.px(900)).pack(fill="x")

        # Two columns of two. A four-across row would squeeze each card to uselessness
        # and a single column would waste the width the window already has.
        self.cards = []
        for slot in range(4):
            card = PadCard(r, self.app, slot)
            card.wrap.grid(row=1 + slot // 2, column=slot % 2, sticky="nsew",
                           padx=(0, 10) if slot % 2 == 0 else (0, 0),
                           pady=(0, 10))
            self.cards.append(card)
        r.grid_columnconfigure(0, weight=1, uniform="pads")
        r.grid_columnconfigure(1, weight=1, uniform="pads")
        # The cards are as tall as their contents. A spacer row soaks up the rest, so
        # four short cards do not stretch into four tall mostly-empty ones.
        r.grid_rowconfigure(3, weight=1)
        tk.Frame(r, bg=BG).grid(row=3, column=0, columnspan=2, sticky="nsew")

    def refresh_all(self):
        self.on_scheme_change()

    def on_scheme_change(self):
        for card in self.cards:
            card.relabel()
            card.scheme_chips.paint()

    def tick(self, latest, connected, dirty):
        import time
        now = time.perf_counter()
        for card in self.cards:
            card.refresh(now)
