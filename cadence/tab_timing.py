"""Tab 1 - Timing. One controller, every press, and the gaps between them."""

import time
import tkinter as tk
from tkinter import ttk

from .theme import (BG, PANEL_2, PANEL, RAISED_HI, RAISED, LINE, TEXT, MUTED, DIM,
                    BRAND_HI, TINT, ACCENT, MISS, XBOX_A, XBOX_B, XBOX_X, XBOX_Y)

from .hardware import BUTTONS
from . import timing as T
from .timing import fmt_ms, fmt_ticks, stick_arrow
from .padart import PadArt

MAX_LOG_ROWS = 500
TIMELINE_MAX_PRESSES = 26
DEFAULT_SEQUENCE_GAP = 600
DEFAULT_TARGET_MS = 150
DEFAULT_TOLERANCE_MS = 15

COLOUR = {"A": XBOX_A, "B": XBOX_B, "X": XBOX_X, "Y": XBOX_Y,
          "LB": "#d6d6d6", "RB": "#d6d6d6", "LT": TINT, "RT": TINT,
          "LS": "#b7e07a", "RS": "#b7e07a", "UP": "#a8a8a8", "DOWN": "#a8a8a8",
          "LEFT": "#a8a8a8", "RIGHT": "#a8a8a8", "BACK": "#7a7a7a", "START": "#7a7a7a"}


class TimingTab:
    def __init__(self, parent, app):
        self.app = app
        self.ui = app.ui
        self.root = app.root
        self.res = 0.0
        self.target = DEFAULT_TARGET_MS
        self.tol = DEFAULT_TOLERANCE_MS
        self.target_on = False
        self.hint_on = True
        self.pulse_job = None
        self.hover_row = None
        self.gap_zones = []
        self._scheme_key = None
        self.frame = tk.Frame(parent, bg=BG)
        self._build()

    # ---------------------------------------------------------------- layout
    def _build(self):
        ui, r = self.ui, self.frame
        r.grid_columnconfigure(1, weight=1)
        r.grid_rowconfigure(0, weight=1)

        left_wrap = ui.panel(r, padx=16, pady=14)
        left_wrap.grid(row=0, column=0, sticky="ns", padx=(0, 10), pady=(0, 0))
        left = left_wrap.inner

        self.pad = tk.Canvas(left, width=ui.px(420), height=ui.px(258), bg=PANEL,
                             highlightthickness=0)
        self.pad.pack()
        ui.grad(self.pad, ui.px(420), ui.px(258), PANEL_2, PANEL)
        self.art = PadArt(self.pad, ui, self.app.schemes.scheme(0))
        self.scheme_line = tk.Label(left, text="", bg=PANEL, fg=MUTED, font=ui.f(9),
                                    anchor="w", justify="left", wraplength=ui.px(400))
        self.scheme_line.pack(fill="x", pady=(4, 0))

        ui.heading(left, "YOUR CONSISTENCY", pady=(12, 1))
        tk.Label(left, text="Last 25 of each pair. Typical is the middle attempt, so one "
                            "fumble doesn't skew it. A full Steadiness bar means you "
                            "repeat it tightly.",
                 bg=PANEL, fg=MUTED, wraplength=ui.px(400), justify="left",
                 font=ui.f(9), anchor="w").pack(fill="x")
        grid = tk.Frame(left, bg=PANEL)
        grid.pack(fill="x", pady=(6, 0))
        heads = ["Pair", "Typical", "± Spread", "Fastest", "n", "Steadiness"]
        tips = ["Which button followed which",
                "Middle value of your recent attempts",
                "How far your attempts stray from typical. Smaller is better.",
                "Your quickest attempt of the recent batch",
                "How many attempts this row is based on",
                "Spread as a share of the typical gap. Full bar means very repeatable."]
        for i, (h, tip) in enumerate(zip(heads, tips)):
            lab = tk.Label(grid, text=h, bg=PANEL, fg=MUTED, font=ui.f(9, "semi"),
                           anchor="w" if i == 0 else "e")
            lab.grid(row=0, column=i, sticky="ew", padx=4)
            grid.grid_columnconfigure(i, weight=2 if i == 0 else 1)
            ui.tooltip(lab, tip)
        self.stat_cells, self.stat_bars = [], []
        for row in range(6):
            cells = []
            for i in range(5):
                lab = tk.Label(grid, text="", bg=PANEL, fg=TEXT,
                               font=ui.f(10) if i == 0 else ui.d(9),
                               anchor="w" if i == 0 else "e")
                lab.grid(row=row + 1, column=i, sticky="ew", padx=4, pady=1)
                cells.append(lab)
            bar = tk.Canvas(grid, width=ui.px(54), height=ui.px(8), bg=PANEL,
                            highlightthickness=0)
            bar.grid(row=row + 1, column=5, sticky="e", padx=4)
            self.stat_cells.append(cells)
            self.stat_bars.append(bar)

        ui.heading(left, "BUTTONS TO COUNT", pady=(12, 1))
        tk.Label(left, text="Click to ignore held inputs like throttle", bg=PANEL,
                 fg=MUTED, font=ui.f(9), anchor="w").pack(fill="x")
        chips = tk.Frame(left, bg=PANEL)
        chips.pack(fill="x", pady=(6, 0))
        self.chips = {}
        for i, (_, key, label) in enumerate(BUTTONS):
            c = tk.Label(chips, text=label, font=ui.f(9, "semi"), width=5, pady=4,
                         cursor="hand2")
            c.grid(row=i // 8, column=i % 8, padx=2, pady=2, sticky="ew")
            c.bind("<Button-1>", lambda e, k=key: self.toggle_key(k))
            c.bind("<Enter>", lambda e, w=c: w.configure(bg=RAISED_HI), add="+")
            c.bind("<Leave>", lambda e, k=key: self._paint_chip(k), add="+")
            self.chips[key] = c
            self._paint_chip(key)

        gapf = tk.Frame(left, bg=PANEL)
        gapf.pack(fill="x", pady=(12, 2))
        tk.Label(gapf, text="New sequence after", bg=PANEL, fg=TEXT,
                 font=ui.f(10)).pack(side="left")
        self.gap_label = tk.Label(gapf, text="", bg=PANEL, fg=TINT, font=ui.f(10, "semi"))
        self.gap_label.pack(side="right")
        self.gap_scale = tk.Scale(left, from_=150, to=2000, resolution=50,
                                  orient="horizontal", showvalue=False, bg=BRAND_HI,
                                  troughcolor=BG, fg=TEXT, activebackground=TINT,
                                  highlightthickness=0, bd=0, width=ui.px(10),
                                  sliderlength=ui.px(22), sliderrelief="flat",
                                  cursor="hand2", command=self.set_gap)
        self.gap_scale.set(DEFAULT_SEQUENCE_GAP)
        self.gap_scale.pack(fill="x")

        tickf = tk.Frame(left, bg=PANEL)
        tickf.pack(fill="x", pady=(10, 0))
        tk.Label(tickf, text="Engine tick rate", bg=PANEL, fg=TEXT,
                 font=ui.f(10)).pack(side="left")
        self.tick_var = tk.StringVar(value=f"{T.TICK_HZ:.0f}")
        ui.entry(tickf, self.tick_var, 5, self.read_tick_rate).pack(side="left",
                                                                   padx=(8, 4), ipady=2)
        tk.Label(tickf, text="Hz", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left")
        self.tick_note = tk.Label(left, text="", bg=PANEL, fg=MUTED, font=ui.f(9),
                                  anchor="w", wraplength=ui.px(400), justify="left")
        self.tick_note.pack(fill="x", pady=(2, 0))
        self.paint_tick_note()

        tgt = tk.Frame(left, bg=PANEL)
        tgt.pack(fill="x", pady=(12, 0))
        self.target_btn = tk.Label(tgt, text="", font=ui.f(10, "semi"), padx=11, pady=5,
                                   cursor="hand2")
        self.target_btn.pack(side="left")
        self.target_btn.bind("<Button-1>", lambda e: self.toggle_target())
        tk.Label(tgt, text="Aim for", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left", padx=(10, 4))
        self.target_var = tk.StringVar(value=str(DEFAULT_TARGET_MS))
        self.tol_var = tk.StringVar(value=str(DEFAULT_TOLERANCE_MS))
        ui.entry(tgt, self.target_var, 5, self.read_target).pack(side="left", ipady=2)
        tk.Label(tgt, text="ms", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left", padx=(3, 8))
        tk.Label(tgt, text="±", bg=PANEL, fg=MUTED, font=ui.f(10)).pack(side="left",
                                                                       padx=(0, 4))
        ui.entry(tgt, self.tol_var, 4, self.read_target).pack(side="left", ipady=2)
        tk.Label(tgt, text="ms", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left", padx=(3, 0))
        self.target_hits = tk.Label(left, text="", bg=PANEL, fg=MUTED, font=ui.f(9),
                                    anchor="w", justify="left", wraplength=ui.px(400))
        self.target_hits.pack(fill="x", pady=(4, 0))
        self._paint_target()

        # ---- right column
        right = tk.Frame(r, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        read = tk.Frame(right, bg=BG)
        read.grid(row=0, column=0, sticky="ew")
        self.sub1 = tk.Label(read, text="GAP BETWEEN YOUR LAST TWO PRESSES", bg=BG,
                             fg=DIM, font=ui.f(8, "tight"), anchor="w")
        self.sub1.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 1))
        self.big = tk.Label(read, text="—", bg=BG, fg=DIM, font=ui.d(44), anchor="w")
        self.big.grid(row=1, column=0, sticky="w")
        unit = tk.Frame(read, bg=BG)
        unit.grid(row=1, column=1, sticky="sw", padx=(8, 0), pady=(0, 11))
        tk.Label(unit, text="ms", bg=BG, fg=MUTED, font=ui.f(15, "thin"),
                 anchor="w").pack(fill="x")
        self.plus = tk.Label(unit, text="", bg=BG, fg=DIM, font=ui.d(8), anchor="w")
        self.plus.pack(fill="x")
        sub = tk.Frame(read, bg=BG)
        sub.grid(row=1, column=2, sticky="sw", padx=(24, 0), pady=(0, 10))
        self.sub2 = tk.Label(sub, text="Press a button to start", bg=BG, fg=TEXT,
                             font=ui.f(13), anchor="w")
        self.sub2.pack(fill="x")
        read.grid_columnconfigure(3, weight=1)
        self.seq_label = tk.Label(read, text="", bg=BG, fg=MUTED, font=ui.f(9),
                                  justify="right", anchor="se")
        self.seq_label.grid(row=0, column=4, rowspan=2, sticky="se", pady=(0, 10))
        self.sub3 = tk.Label(read, text="", bg=BG, fg=MUTED, font=ui.f(9), anchor="w")
        self.sub3.grid(row=2, column=0, columnspan=5, sticky="w", pady=(2, 0))

        self.tl = tk.Canvas(right, height=ui.px(230), bg=PANEL, highlightthickness=0)
        self.tl.grid(row=1, column=0, sticky="ew", pady=(6, 12))
        self._redraw_job = None
        self._last_draw = 0.0
        self.tl.bind("<Configure>", lambda e: self.queue_redraw())
        self.tl.bind("<Motion>", self.timeline_hover)
        self.tl.bind("<Leave>", lambda e: self.ui.hide_tip())
        self.tl.bind("<Button-1>", lambda e: self.dismiss_hint())

        log_wrap = ui.panel(right)
        log_wrap.grid(row=2, column=0, sticky="nsew")
        logf = log_wrap.inner
        cols = ("n", "time", "button", "gap", "ticks", "held", "stick")
        heads = ("#", "TIME", "BUTTON", "GAP FROM LAST", "TICKS", "HELD FOR", "STICK")
        widths = (44, 78, 68, 122, 62, 96, 74)
        self.tree = ttk.Treeview(logf, columns=cols, show="headings", style="Log.Treeview")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h, anchor="w" if c == "button" else "e")
            self.tree.column(c, width=ui.px(w), anchor="w" if c == "button" else "e",
                             stretch=c in ("gap", "held"))
        self.tree.tag_configure("sa", background=PANEL)
        self.tree.tag_configure("sb", background=PANEL_2)
        self.tree.tag_configure("hit", background="#3a2a08", foreground="#ffe0a3")
        self.tree.tag_configure("miss", background="#301513", foreground="#f7c9c6")
        self.tree.tag_configure("hover", background=RAISED)
        self.tree.bind("<Motion>", self.row_hover)
        self.tree.bind("<Leave>", lambda e: self.row_hover(None))
        sb = ttk.Scrollbar(logf, orient="vertical", command=self.tree.yview,
                           style="Log.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ---------------------------------------------------------------- timeline
    def queue_redraw(self):
        """Collapse a burst of resize events into one redraw."""
        if self._redraw_job is not None:
            try:
                self.root.after_cancel(self._redraw_job)
            except Exception:
                pass
        self._redraw_job = self.root.after(60, self._do_redraw)

    def _do_redraw(self):
        self._redraw_job = None
        self.draw_timeline()

    def draw_timeline(self):
        self._last_draw = time.perf_counter()
        c, ui = self.tl, self.ui
        S = ui.S
        c.delete("strip")
        self.gap_zones = []
        w, h = c.winfo_width(), c.winfo_height()
        ui.grad(c, w, h, PANEL_2, PANEL)
        m = self.app.cur
        full = m.sequence if m else []
        seq = full[-TIMELINE_MAX_PRESSES:]
        if not seq:
            title = ("Press buttons on your controller" if self.app.selected is not None
                     else "Plug in a controller")
            c.create_text(w / 2, h / 2 - 36 * S, text=title, fill=TEXT, font=ui.f(14, "semi"), tags="strip")
            for i, line in enumerate([
                    "This strip draws your presses to scale, left to right, as they happen.",
                    "One row per button. A bar is how long you held it; the bracket above "
                    "is the gap between presses.",
                    f"Faint vertical lines are engine ticks at {T.TICK_HZ:.0f} Hz, "
                    f"one every {T.TICK_MS:.2f} ms."]):
                c.create_text(w / 2, h / 2 + (i * 18 - 4) * S, text=line, fill=MUTED,
                              font=ui.f(10 if i == 0 else 9), tags="strip")
            return
        now = time.perf_counter()
        t0 = seq[0]["t"]
        ends = [r["t"] + r["held"] / 1000 if r["held"] is not None else now for r in seq]
        span = max(200.0, (max(ends) - t0) * 1000 * 1.06)
        lanes = []
        for r in seq:
            if r["key"] not in lanes:
                lanes.append(r["key"])
        left, right = 64 * S, w - 22 * S
        top, bottom = 58 * S, h - 26 * S
        lane_h = min(36 * S, (bottom - top) / len(lanes))
        ppm = (right - left) / span

        def X(t):
            return left + (t - t0) * 1000 * ppm

        for i, key in enumerate(lanes):
            y = top + i * lane_h
            if i % 2 == 0:
                c.create_rectangle(left, y, right, y + lane_h, fill=PANEL_2, width=0, tags="strip")
            lane_col = self.app.scheme().faces.get(key, COLOUR.get(key, MUTED))
            c.create_text(left - 10 * S, y + lane_h / 2, text=self.app.label(key),
                          anchor="e", fill=lane_col, font=ui.f(10, "bold"), tags="strip")
        lanes_end = top + len(lanes) * lane_h

        if T.TICK_MS * ppm >= 6 * S:
            k = 0
            while k * T.TICK_MS <= span:
                c.create_line(left + k * T.TICK_MS * ppm, top,
                              left + k * T.TICK_MS * ppm, lanes_end, fill="#1a2822", tags="strip")
                k += 1
        step = next((st for st in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000)
                     if st * ppm >= 70 * S), 5000)
        mm = 0
        while mm <= span:
            x = left + mm * ppm
            c.create_line(x, top, x, lanes_end, fill=LINE, tags="strip")
            c.create_text(x, lanes_end + 12 * S, text=f"{mm} ms" if mm else "0",
                          fill=MUTED, font=ui.f(8), tags="strip")
            mm += step

        for r, end in zip(seq, ends):
            i = lanes.index(r["key"])
            y = top + i * lane_h
            x0, x1 = X(r["t"]), max(X(end), X(r["t"]) + 3 * S)
            bar_col = self.app.scheme().faces.get(r["key"],
                                                  COLOUR.get(r["key"], MUTED))
            c.create_rectangle(x0, y + 5 * S, x1, y + lane_h - 5 * S, fill=bar_col,
                               outline=TEXT if r["held"] is None else "", width=1.5 * S, tags="strip")

        taken = {0: [], 1: []}
        for n in range(1, len(seq)):
            a, b = seq[n - 1], seq[n]
            if b["gap"] is None:
                continue
            xa, xb = X(a["t"]), X(b["t"])
            lvl = n % 2
            yl = (38 if lvl else 18) * S
            text = ("together" if b["gap"] < 0.05
                    else fmt_ms(b["gap"], self.res).replace(" ms", ""))
            half = len(text) * 3.4 * S + 4 * S
            mid = (xa + xb) / 2
            x0, x1 = mid - half, mid + half
            if any(x0 < o1 and x1 > o0 for o0, o1 in taken[lvl]):
                continue
            taken[lvl].append((x0, x1))
            hit = self.on_target(b["gap"])
            col = TINT if hit is None else (ACCENT if hit else MISS)
            for coords in ((xa, yl, xb, yl), (xa, yl - 4 * S, xa, yl + 4 * S),
                           (xb, yl - 4 * S, xb, yl + 4 * S)):
                c.create_line(*coords, fill=col, width=1.5 * S, tags="strip")
            c.create_line(xb, yl + 4 * S, xb, top, fill=col, dash=(2, 3), tags="strip")
            c.create_text(mid, yl - 9 * S, text=text, fill=TEXT, font=ui.f(9, "semi"), tags="strip")
            self.gap_zones.append((x0, x1, yl - 18 * S, yl + 6 * S, self.gap_detail(a, b)))

        if len(full) > len(seq):
            c.create_text(left, lanes_end + 30 * S, anchor="w",
                          text=f"showing the last {len(seq)} of {len(full)} presses",
                          fill=MUTED, font=ui.f(8), tags="strip")
        if self.hint_on:
            y = h - 11 * S
            if y >= lanes_end + 16 * S:
                c.create_text(64 * S, y, anchor="w", fill=DIM, font=ui.f(8),
                              text="bars are presses, width is how long you held  ·  "
                                   "hover a bracket for detail  ·  click to hide this", tags="strip")

    def gap_detail(self, a, b):
        gap = b["gap"]
        L = self.app.label
        lines = [f"{L(a['key'])} → {L(b['key'])}",
                 f"{fmt_ms(gap, self.res)}" + (f"  ± {self.res:.1f}" if self.res else ""),
                 f"{fmt_ticks(gap)} ticks at {T.TICK_HZ:.0f} Hz ({T.TICK_MS:.2f} ms each)"]
        if a["held"] is not None:
            lines.append(f"{L(a['key'])} was held {fmt_ms(a['held'], self.res)}")
        hit = self.on_target(gap)
        if hit is not None:
            lines.append(("Inside" if hit else "Outside")
                         + f" your ±{self.tol:.0f} ms target of {self.target:.0f} ms")
        return "\n".join(lines)

    def timeline_hover(self, ev):
        for x0, x1, y0, y1, text in self.gap_zones:
            if x0 <= ev.x <= x1 and y0 <= ev.y <= y1:
                if self.ui.tip is None:
                    self.ui.show_tip(text, ev.x_root, ev.y_root)
                return
        self.ui.hide_tip()

    def dismiss_hint(self):
        if self.hint_on:
            self.hint_on = False
            self.draw_timeline()

    # ---------------------------------------------------------------- rows
    def row_tags(self, r):
        hit = self.on_target(r["gap"])
        if hit is True:
            return ("hit",)
        if hit is False:
            return ("miss",)
        return ("sa" if r["seq"] % 2 else "sb",)

    def row_hover(self, ev):
        row = self.tree.identify_row(ev.y) if ev is not None else None
        if row == self.hover_row:
            return
        if self.hover_row and self.tree.exists(self.hover_row):
            tags = tuple(t for t in self.tree.item(self.hover_row, "tags") if t != "hover")
            self.tree.item(self.hover_row, tags=tags)
        self.hover_row = row
        if row:
            self.tree.item(row, tags=("hover",) + tuple(self.tree.item(row, "tags")))

    def row_values(self, r):
        gap = fmt_ms(r["gap"], self.res) if r["gap"] is not None else "start"
        held = fmt_ms(r["held"], self.res) if r["held"] is not None else "holding"
        return (r["n"], f"{r['t'] - self.app.t_start:.3f}s", self.app.label(r["key"]), gap,
                fmt_ticks(r["gap"]), held, stick_arrow(*r["stick"]))

    # ---------------------------------------------------------------- readout
    def show_readout(self, r):
        if r["gap"] is not None:
            hit = self.on_target(r["gap"])
            colour = TINT if hit is None else (ACCENT if hit else MISS)
            self.big.configure(text=fmt_ms(r["gap"], self.res).replace(" ms", ""), fg=colour)
            self.plus.configure(text=f"±{self.res:.1f}" if self.res else "")
            self.sub1.configure(text="GAP BETWEEN YOUR LAST TWO PRESSES", fg=DIM)
            ticks = fmt_ticks(r["gap"])
            self.sub2.configure(text=f"{self.app.label(r['prev'])}  →  "
                                     f"{self.app.label(r['key'])}"
                                     f"        {ticks} tick{'' if ticks == '1' else 's'}")
            note = (f"an engine at {T.TICK_HZ:.0f} Hz reads your pad every "
                    f"{T.TICK_MS:.2f} ms, so anything finer never reaches it")
            if hit is True:
                note = (f"hit · inside ±{self.tol:.0f} ms of {self.target:.0f} ms"
                        f"   ·   ") + note
            elif hit is False:
                off = r["gap"] - self.target
                note = (f"miss · {abs(off):.0f} ms {'late' if off > 0 else 'early'}"
                        f" of {self.target:.0f} ms   ·   ") + note
            self.sub3.configure(text=note, fg=colour if hit is not None else MUTED)
            self.pulse(colour)
        else:
            self.big.configure(text="—", fg=DIM)
            self.plus.configure(text="")
            self.sub1.configure(text="NEW SEQUENCE STARTED", fg=DIM)
            self.sub2.configure(text=f"First press: {self.app.label(r['key'])}")
            self.sub3.configure(text="nothing before it to measure against", fg=MUTED)
        seq = self.app.cur.sequence
        if seq:
            total = (seq[-1]["t"] - seq[0]["t"]) * 1000
            self.seq_label.configure(
                text=f"Sequence {seq[-1]['seq']}\n{len(seq)} press"
                     f"{'' if len(seq) == 1 else 'es'} in {total:.0f} ms")

    def pulse(self, colour):
        """One short flash when a fresh reading lands.

        It answers a real question - did that press register? - on a screen where an
        unchanged number and a new identical number look the same."""
        if self.pulse_job is not None:
            self.root.after_cancel(self.pulse_job)
        self.big.configure(fg=TEXT)

        def settle():
            self.pulse_job = None
            try:
                self.big.configure(fg=colour)
            except tk.TclError:
                pass
        self.pulse_job = self.root.after(110, settle)

    def clear_readout(self):
        self.big.configure(text="—", fg=DIM)
        self.plus.configure(text="")
        self.sub1.configure(text="GAP BETWEEN YOUR LAST TWO PRESSES", fg=DIM)
        self.sub2.configure(text="Press a button to start")
        self.sub3.configure(text="")
        self.seq_label.configure(text="")

    # ---------------------------------------------------------------- stats
    def update_stats(self):
        m = self.app.cur
        stats = m.pair_stats(len(self.stat_cells)) if m else []
        for row, cells in enumerate(self.stat_cells):
            bar = self.stat_bars[row]
            bar.delete("all")
            if row < len(stats):
                name, mid, sd, mn, n = stats[row]
                vals = (name, fmt_ms(mid, self.res), f"±{sd:.1f}",
                        fmt_ms(mn, self.res).replace(" ms", ""), str(n))
                self._draw_steadiness(bar, mid, sd, n)
                fg = TEXT
            else:
                vals = ("press two buttons in a row" if row == 0 and not stats else "",
                        "", "", "", "")
                fg = DIM
            for cell, v in zip(cells, vals):
                cell.configure(text=v, fg=fg)

    def _draw_steadiness(self, bar, mid, sd, n):
        """Spread as a share of the gap itself, so a 10 ms wobble on a 60 ms flip reads
        as much worse than the same 10 ms on a 600 ms wait."""
        ui = self.ui
        w, h = ui.px(54), ui.px(8)
        bar.create_rectangle(0, 0, w, h, fill=BG, outline="")
        if n < 3 or mid <= 0:
            bar.create_text(w / 2, h / 2, text="need more", fill=DIM, font=ui.f(7))
            return
        frac = 1.0 - min(1.0, sd / mid / 0.25)
        col = BRAND_HI if frac > 0.66 else (ACCENT if frac > 0.33 else MISS)
        bar.create_rectangle(0, 0, max(2 * ui.S, w * frac), h, fill=col, outline="")

    # ---------------------------------------------------------------- controls
    def relabel_chips(self):
        sch = self.app.schemes.scheme(0 if self.app.selected is None
                                      else self.app.selected)
        for key, chip in self.chips.items():
            chip.configure(text=sch.label(key))
            self._paint_chip(key)

    def _paint_chip(self, key):
        off = key in self.app.ignored
        sch = self.app.schemes.scheme(0 if self.app.selected is None
                                      else self.app.selected)
        col = sch.faces.get(key, COLOUR.get(key, MUTED))
        self.chips[key].configure(bg=BG if off else RAISED, fg=DIM if off else col)

    def toggle_key(self, key):
        if key in self.app.ignored:
            self.app.ignored.discard(key)
        else:
            self.app.ignored.add(key)
        self._paint_chip(key)

    def set_gap(self, v):
        self.app.gap_ref[0] = float(v)
        self.gap_label.configure(text=f"{int(float(v))} ms of no presses")

    def read_tick_rate(self):
        """Recount every gap against the new rate. Nothing is re-measured, only
        re-divided, so the whole log can just be redrawn."""
        try:
            T.set_tick_rate(float(self.tick_var.get()))
        except ValueError:
            return
        self.paint_tick_note()
        self.refresh_all()

    def paint_tick_note(self):
        self.tick_note.configure(
            text=f"One tick is {T.TICK_MS:.2f} ms. Gaps closer together than that "
                 f"land on the same tick and play out identically.")

    def toggle_target(self):
        self.target_on = not self.target_on
        self._paint_target()
        self.update_target()

    def read_target(self):
        def num(var, fallback, lo, hi):
            try:
                return min(hi, max(lo, float(var.get())))
            except ValueError:
                return fallback
        self.target = num(self.target_var, self.target, 1, 5000)
        self.tol = num(self.tol_var, self.tol, 1, 500)
        self.update_target()

    def _paint_target(self):
        on = self.target_on
        self.target_btn.configure(text="TARGET ON " if on else "TARGET OFF")
        self.ui.restyle(self.target_btn, ACCENT if on else RAISED,
                        "#ffc866" if on else RAISED_HI,
                        "#231800" if on else TEXT)

    def update_target(self):
        if not self.target_on:
            self.target_hits.configure(
                text="Turn this on to practise hitting one gap over and over.", fg=MUTED)
            return
        m = self.app.cur
        hits, total = m.target_hits(self.target, self.tol) if m else (0, 0)
        if not total:
            self.target_hits.configure(
                text=f"Aiming for {self.target:.0f} ms. No attempts yet.", fg=MUTED)
            return
        pct = 100 * hits / total
        colour = BRAND_HI if pct >= 70 else (ACCENT if pct >= 40 else MISS)
        self.target_hits.configure(
            text=f"{hits} of the last {total} landed within ±{self.tol:.0f} ms "
                 f"of {self.target:.0f} ms  ({pct:.0f}%)", fg=colour)

    def on_target(self, gap):
        """True / False if the target is on and this gap hit it, otherwise None."""
        if not self.target_on or gap is None:
            return None
        return abs(gap - self.target) <= self.tol

    # ---------------------------------------------------------------- app hooks
    def refresh_all(self):
        self.tree.delete(*self.tree.get_children())
        self.relabel_chips()
        m = self.app.cur
        if m:
            for r in m.presses[-MAX_LOG_ROWS:]:
                self.tree.insert("", 0, iid=str(r["n"]), values=self.row_values(r),
                                 tags=self.row_tags(r))
        if m and m.presses:
            self.show_readout(m.presses[-1])
        else:
            self.clear_readout()
        if hasattr(self, 'art'):
            self.art.cache.clear()
        self.update_stats()
        self.update_target()
        self.draw_timeline()

    def on_press(self, r):
        self.tree.insert("", 0, iid=str(r["n"]), values=self.row_values(r),
                         tags=self.row_tags(r))
        kids = self.tree.get_children()
        if len(kids) > MAX_LOG_ROWS:
            self.tree.delete(*kids[MAX_LOG_ROWS:])
        self.show_readout(r)
        self.update_stats()
        self.update_target()

    def on_release(self, rec):
        if self.tree.exists(str(rec["n"])):
            self.tree.item(str(rec["n"]), values=self.row_values(rec))

    def on_scheme_change(self):
        """Redraw the pad in the layout of whichever controller is selected."""
        slot = self.app.selected
        sch = self.app.schemes.scheme(0 if slot is None else slot)
        if getattr(self, "_scheme_key", None) != sch.key:
            self._scheme_key = sch.key
            self.ui.grad(self.pad, self.ui.px(420), self.ui.px(258), PANEL_2, PANEL)
            self.art = PadArt(self.pad, self.ui, sch)
        if slot is not None and self.app.schemes.is_guess(slot):
            self.scheme_line.configure(
                text=f"Drawn as a {sch.name} pad - {self.app.schemes.explain(slot)}. "
                     f"Change it on the Controllers tab if that is wrong.", fg=ACCENT)
        else:
            self.scheme_line.configure(text=f"{sch.name} layout"
                                            + (f" · {sch.note}" if sch.note else ""),
                                       fg=MUTED)
        self.refresh_all()

    def tick(self, latest, connected, dirty):
        self.res = self.app.res
        self.art.update(latest, connected)
        m = self.app.cur
        live = bool(m) and any(r["held"] is None for r in m.sequence)
        if not (dirty or live):
            return
        # A held button makes the strip live, but redrawing it at the tick rate means
        # rebuilding the whole canvas a hundred and twenty times a second. Twenty-five
        # is smooth to look at and leaves the main thread free for everything else.
        now = time.perf_counter()
        if not dirty and now - self._last_draw < 0.04:
            return
        self._last_draw = now
        self.draw_timeline()
