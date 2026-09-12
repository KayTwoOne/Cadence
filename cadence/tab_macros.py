"""Tab 3 - Macros. Bind a pad button to a stream of clicks or keypresses.

Simple mode is the top half: what triggers it, what it sends, how fast, hold or
toggle. Advanced adds the controls you only want once the basic thing works - duty
cycle, random rates, limits, fixed positions and the edge stop.

The safety story matters more here than anywhere else in the app, because the output
lands in whatever window you are actually looking at. Three independent ways to stop:
the master switch, a global panic key that works unfocused, and shoving the mouse into
a screen corner.
"""

import time
import tkinter as tk

from .theme import (BG, PANEL, PANEL_2, RAISED, RAISED_HI, LINE, TEXT, MUTED, DIM,
                    BRAND, BRAND_HI, TINT, ACCENT, ACCENT_HI, MISS, INK_ON_LIGHT)
from .hardware import KEYS, LABEL
from .macros import Rule, RATE_UNITS
from .synth import PANIC_KEYS, cursor_pos
from . import diagnostics


class MacroTab:
    def __init__(self, parent, app):
        self.app = app
        self.ui = app.ui
        self.engine = app.engine
        self.advanced = False
        self.selected = None
        self.capturing = False          # waiting for a pad button to bind
        self.picking = False            # waiting for the position pick countdown
        self.pick_until = 0.0
        self.rows = {}
        self._hotkey_seen = None
        self.frame = tk.Frame(parent, bg=BG)
        self._build()
        if not self.engine.rules:
            self.select(self.engine.add(Rule("RB")))
        else:
            self.select(self.engine.rules[0])

    # ---------------------------------------------------------------- layout
    def _build(self):
        ui, r = self.ui, self.frame
        r.grid_columnconfigure(1, weight=1)
        r.grid_rowconfigure(1, weight=1)

        # ---- control strip
        strip = tk.Frame(r, bg=BG)
        strip.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.master_btn = tk.Label(strip, text="", font=ui.f(13, "semi"), padx=20, pady=10,
                                   cursor="hand2")
        self.master_btn.pack(side="left")
        self.master_btn.bind("<Button-1>", lambda e: self.toggle_master())

        stat = tk.Frame(strip, bg=BG)
        stat.pack(side="left", padx=(16, 0))
        self.state_line = tk.Label(stat, text="", bg=BG, fg=TEXT, font=ui.f(12), anchor="w")
        self.state_line.pack(fill="x")
        self.state_note = tk.Label(stat, text="", bg=BG, fg=MUTED, font=ui.f(9), anchor="w")
        self.state_note.pack(fill="x")

        self.m_sent = ui.metric(strip, "sent this run")
        self.m_sent.pack(side="right", padx=(18, 0))
        panic = tk.Frame(strip, bg=BG)
        panic.pack(side="right", padx=(18, 0))
        tk.Label(panic, text="PANIC KEY", bg=BG, fg=MUTED, font=ui.f(8, "tight"),
                 anchor="e").pack(fill="x")
        prow = tk.Frame(panic, bg=BG)
        prow.pack()
        self.panic_chips = ui.choice(
            prow, [(k, k) for k in PANIC_KEYS], lambda: self.app.panic_key,
            self.app.set_panic_key, bg=BG)
        self.panic_chips.pack()
        ui.tooltip(panic, "Stops every macro instantly, even when Cadence is not the "
                          "window you are looking at.")

        # ---- rule list
        listwrap = ui.panel(r, padx=12, pady=10)
        listwrap.grid(row=1, column=0, sticky="ns", padx=(0, 10))
        side = listwrap.inner
        ui.heading(side, "MACROS", pady=(0, 6))
        self.list_frame = tk.Frame(side, bg=PANEL)
        self.list_frame.pack(fill="both", expand=True)
        btns = tk.Frame(side, bg=PANEL)
        btns.pack(fill="x", pady=(10, 0))
        ui.button(btns, "＋ ADD", self.add_rule, pad=(12, 6)).pack(side="left")
        self.del_btn = ui.button(btns, "REMOVE", self.remove_rule, pad=(12, 6))
        self.del_btn.pack(side="right")

        # ---- editor
        editwrap = ui.panel(r, padx=16, pady=14)
        editwrap.grid(row=1, column=1, sticky="nsew")
        ed = editwrap.inner
        self.editor = ed

        title = tk.Frame(ed, bg=PANEL)
        title.pack(fill="x")
        self.rule_title = tk.Label(title, text="", bg=PANEL, fg=TEXT,
                                   font=ui.f(14, "semi"), anchor="w")
        self.rule_title.pack(side="left")
        self.mode_btn = tk.Label(title, text="", font=ui.f(9, "semi"), padx=10, pady=4,
                                 cursor="hand2")
        self.mode_btn.pack(side="right")
        self.mode_btn.bind("<Button-1>", lambda e: self.toggle_advanced())

        # --- simple block
        simple = tk.Frame(ed, bg=PANEL)
        simple.pack(fill="x", pady=(12, 0))

        trig = ui.field(simple, "trigger  ·  the pad button that starts it")
        trig.pack(fill="x")
        self.trigger_btn = ui.button(trig.body, "", self.capture_trigger, pad=(14, 6))
        self.trigger_btn.pack(side="left")
        self.slot_choice = ui.choice(
            trig.body, [(None, "ANY PAD")] + [(i, f"PAD {i + 1}") for i in range(4)],
            lambda: self.cur.slot if self.cur else None, self.set_slot)
        self.slot_choice.pack(side="left", padx=(10, 0))

        act = ui.field(simple, "sends")
        act.pack(fill="x", pady=(12, 0))
        self.action_choice = ui.choice(
            act.body, [("mouse", "MOUSE CLICK"), ("double", "DOUBLE CLICK"),
                       ("key", "KEYBOARD KEY")],
            lambda: self.cur.action if self.cur else "mouse", self.set_action)
        self.action_choice.pack(side="left")

        detail = tk.Frame(simple, bg=PANEL)
        detail.pack(fill="x", pady=(8, 0))
        self.button_choice = ui.choice(
            detail, [("left", "LEFT"), ("right", "RIGHT"), ("middle", "MIDDLE")],
            lambda: self.cur.button if self.cur else "left", self.set_button)
        self.key_row = tk.Frame(detail, bg=PANEL)
        self.key_var = tk.StringVar()
        tk.Label(self.key_row, text="key", bg=PANEL, fg=MUTED,
                 font=self.ui.f(9)).pack(side="left", padx=(0, 6))
        ui.entry(self.key_row, self.key_var, 10, self.read_key,
                 data=False).pack(side="left", ipady=3)
        tk.Label(self.key_row, text="one character, case as typed — or a name like "
                                    "space, enter, f5",
                 bg=PANEL, fg=DIM, font=ui.f(8)).pack(side="left", padx=(8, 0))

        hold = ui.field(simple, "activation")
        hold.pack(fill="x", pady=(12, 0))
        self.mode_choice = ui.choice(
            hold.body, [("hold", "HOLD  ·  runs while the button is down"),
                        ("toggle", "TOGGLE  ·  press once on, once off")],
            lambda: self.cur.mode if self.cur else "hold", self.set_mode)
        self.mode_choice.pack(side="left")

        rate = ui.field(simple, "rate")
        rate.pack(fill="x", pady=(12, 0))
        self.rate_var = tk.StringVar()
        ui.entry(rate.body, self.rate_var, 7, self.read_rate).pack(side="left", ipady=3)
        tk.Label(rate.body, text="per", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left", padx=8)
        self.unit_choice = ui.choice(
            rate.body, [(u, u.upper()) for u in RATE_UNITS],
            lambda: self.cur.rate_unit if self.cur else "second", self.set_unit)
        self.unit_choice.pack(side="left")
        self.rate_note = tk.Label(rate.body, text="", bg=PANEL, fg=TINT, font=ui.d(9))
        self.rate_note.pack(side="left", padx=(12, 0))

        # --- advanced block
        self.adv = tk.Frame(ed, bg=PANEL)
        ui.heading(self.adv, "ADVANCED", pady=(16, 4))

        timing = ui.field(self.adv, "duty cycle  ·  how much of each interval is spent "
                                    "holding the button down")
        timing.pack(fill="x")
        self.duty_scale = tk.Scale(timing.body, from_=5, to=95, resolution=5,
                                   orient="horizontal", showvalue=False, bg=BRAND_HI,
                                   troughcolor=BG, fg=TEXT, activebackground=TINT,
                                   highlightthickness=0, bd=0, width=ui.px(10),
                                   sliderlength=ui.px(22), sliderrelief="flat",
                                   length=ui.px(260), cursor="hand2",
                                   command=self.set_duty)
        self.duty_scale.pack(side="left")
        self.duty_note = tk.Label(timing.body, text="", bg=PANEL, fg=MUTED, font=ui.d(9))
        self.duty_note.pack(side="left", padx=(12, 0))

        rnd = ui.field(self.adv, "random rate  ·  varies the speed so it is not a "
                                 "metronome")
        rnd.pack(fill="x", pady=(12, 0))
        self.random_switch = ui.switch(rnd.body, "random between", self.get_random,
                                       self.set_random)
        self.random_switch.pack(side="left")
        self.rmin_var, self.rmax_var = tk.StringVar(), tk.StringVar()
        ui.entry(rnd.body, self.rmin_var, 5, self.read_rate).pack(side="left", padx=(8, 4),
                                                                 ipady=3)
        tk.Label(rnd.body, text="and", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left", padx=2)
        ui.entry(rnd.body, self.rmax_var, 5, self.read_rate).pack(side="left", padx=(4, 6),
                                                                 ipady=3)
        tk.Label(rnd.body, text="per second", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left")

        lim = ui.field(self.adv, "limits  ·  stop on their own. 0 means no limit")
        lim.pack(fill="x", pady=(12, 0))
        self.climit_var, self.tlimit_var = tk.StringVar(), tk.StringVar()
        ui.entry(lim.body, self.climit_var, 7, self.read_limits).pack(side="left", ipady=3)
        tk.Label(lim.body, text="clicks", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left", padx=(6, 16))
        ui.entry(lim.body, self.tlimit_var, 7, self.read_limits).pack(side="left", ipady=3)
        tk.Label(lim.body, text="seconds", bg=PANEL, fg=MUTED,
                 font=ui.f(9)).pack(side="left", padx=(6, 0))

        edge = ui.field(self.adv, "screen edge stop  ·  your way out of a runaway macro")
        edge.pack(fill="x", pady=(12, 0))
        self.edge_switch = ui.switch(edge.body, "stop when the mouse reaches",
                                     self.get_edge, self.set_edge)
        self.edge_switch.pack(side="left")
        self.corner_choice = ui.choice(
            edge.body, [(True, "A CORNER"), (False, "ANY EDGE")],
            lambda: self.cur.corners_only if self.cur else True, self.set_corners)
        self.corner_choice.pack(side="left", padx=(8, 0))

        pos = ui.field(self.adv, "position  ·  click a fixed spot instead of wherever "
                                 "the pointer is")
        pos.pack(fill="x", pady=(12, 0))
        self.pos_switch = ui.switch(pos.body, "click at", self.get_pos, self.set_pos)
        self.pos_switch.pack(side="left")
        self.pos_label = tk.Label(pos.body, text="", bg=PANEL, fg=TEXT, font=ui.d(10))
        self.pos_label.pack(side="left", padx=(8, 8))
        self.pick_btn = ui.button(pos.body, "PICK A SPOT", self.pick_position, pad=(10, 4))
        self.pick_btn.pack(side="left")

        # ---- setup check, above the footer so new users meet it first
        self.setup = tk.Frame(ed, bg=PANEL)
        self.setup.pack(fill="x", pady=(16, 0))
        ui.heading(self.setup, "DOES OUTPUT WORK HERE?", pady=(0, 4))
        row = tk.Frame(self.setup, bg=PANEL)
        row.pack(fill="x")
        self.test_btn = ui.button(row, "RUN TEST", self.run_self_test, pad=(12, 6))
        self.test_btn.pack(side="left")
        self.test_entry = ui.entry(row, tk.StringVar(), 18, None, data=True)
        self.test_entry.configure(justify="left")
        self.test_entry.pack(side="left", padx=(10, 0), ipady=4)
        self.test_note = tk.Label(self.setup, text="", bg=PANEL, fg=MUTED,
                                  font=ui.f(9), anchor="w", justify="left",
                                  wraplength=ui.px(620))
        self.test_note.pack(fill="x", pady=(6, 0))
        self.env_note = tk.Label(self.setup, text="", bg=PANEL, fg=MUTED,
                                 font=ui.f(9), anchor="w", justify="left",
                                 wraplength=ui.px(620))
        self.env_note.pack(fill="x", pady=(2, 0))
        self.selftest = diagnostics.OutputSelfTest(self.engine.synth,
                                                   self.test_entry, self.app.root)
        self.refresh_env()

        # ---- live footer
        foot = tk.Frame(ed, bg=PANEL)
        foot.pack(side="bottom", fill="x", pady=(14, 0))
        self.summary = tk.Label(foot, text="", bg=PANEL, fg=MUTED, font=ui.f(9),
                                anchor="w", justify="left", wraplength=ui.px(620))
        self.summary.pack(fill="x")

        self.simple_block = simple
        self.paint_master()
        self.paint_mode_btn()

    # ---------------------------------------------------------------- helpers
    @property
    def cur(self):
        return self.selected

    def add_rule(self):
        self.select(self.engine.add(Rule("RB")))
        self.rebuild_list()

    def remove_rule(self):
        if not self.cur or len(self.engine.rules) <= 1:
            return
        self.engine.remove(self.cur)
        self.select(self.engine.rules[0])
        self.rebuild_list()

    def select(self, rule):
        self.selected = rule
        self.load_rule()
        self.rebuild_list()

    # ---------------------------------------------------------------- list
    def rebuild_list(self):
        ui = self.ui
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.rows = {}
        for rule in self.engine.rules:
            sel = rule is self.selected
            row = tk.Frame(self.list_frame, bg=BRAND if sel else PANEL_2, cursor="hand2")
            row.pack(fill="x", pady=(0, 4))
            inner = tk.Frame(row, bg=row["bg"], padx=10, pady=7)
            inner.pack(fill="x")
            top = tk.Frame(inner, bg=row["bg"])
            top.pack(fill="x")
            lamp = tk.Canvas(top, width=ui.px(8), height=ui.px(8), bg=row["bg"],
                             highlightthickness=0)
            lamp_id = lamp.create_oval(*ui.s(0, 0, 8, 8), fill=DIM, outline="")
            lamp.pack(side="left", padx=(0, 7), pady=(0, 1))
            nm = tk.Label(top, text=f"{rule.trigger} → {rule.describe_action()}",
                          bg=row["bg"], fg=TEXT, font=ui.f(10, "semi"), anchor="w")
            nm.pack(side="left")
            sub = tk.Label(inner, text=rule.describe_rate(), bg=row["bg"],
                           fg="#cfe8dc" if sel else MUTED, font=ui.f(8), anchor="w")
            sub.pack(fill="x")
            for w in (row, inner, top, lamp, nm, sub):
                w.bind("<Button-1>", lambda e, rr=rule: self.select(rr))
            self.rows[rule.id] = (row, inner, top, lamp, lamp_id, nm, sub)
        self.del_btn.configure(fg=TEXT if len(self.engine.rules) > 1 else DIM)

    # ---------------------------------------------------------------- load / save
    def load_rule(self):
        r = self.cur
        if not r:
            return
        self.rule_title.configure(text=r.name)
        self.trigger_btn.configure(text=f"  {LABEL.get(r.trigger, r.trigger)}  ")
        self.key_var.set(r.key_text)
        self.rate_var.set(f"{r.rate_value:g}")
        self.rmin_var.set(f"{r.rate_min:g}")
        self.rmax_var.set(f"{r.rate_max:g}")
        self.climit_var.set(f"{r.limit_clicks:g}")
        self.tlimit_var.set(f"{r.limit_seconds:g}")
        self.duty_scale.set(int(r.duty * 100))
        for chips in (self.slot_choice, self.action_choice, self.button_choice,
                      self.mode_choice, self.unit_choice, self.corner_choice):
            chips.paint()
        for sw in (self.random_switch, self.edge_switch, self.pos_switch):
            sw.paint()
        self.sync_detail_row()
        self.paint_notes()

    def sync_detail_row(self):
        """Only one of the two output detail controls can be relevant at a time."""
        r = self.cur
        self.button_choice.pack_forget()
        self.key_row.pack_forget()
        if r and r.action == "key":
            self.key_row.pack(side="left")
        else:
            self.button_choice.pack(side="left")

    def paint_notes(self):
        r = self.cur
        if not r:
            return
        interval = r.base_interval()
        per_s = 1.0 / interval if interval else 0
        self.rate_note.configure(text=f"≈ {per_s:,.1f} per second"
                                      f"   ·   one every {interval * 1000:,.0f} ms")
        down = interval * r.duty
        self.duty_note.configure(text=f"{r.duty * 100:.0f}%  ·  down {down * 1000:.0f} ms, "
                                      f"up {(interval - down) * 1000:.0f} ms")
        self.pos_label.configure(text=f"{r.pos_x}, {r.pos_y}" if r.fixed_position
                                 else "wherever the pointer is",
                                 fg=TEXT if r.fixed_position else DIM)
        self.summary.configure(text=r.summary())

    # ---- setters
    def set_slot(self, v):
        if self.cur:
            self.cur.slot = v
            self.paint_notes()

    def set_action(self, v):
        if self.cur:
            self.cur.action = v
            self.sync_detail_row()
            self.paint_notes()
            self.rebuild_list()

    def set_button(self, v):
        if self.cur:
            self.cur.button = v
            self.paint_notes()
            self.rebuild_list()

    def set_mode(self, v):
        if self.cur:
            self.cur.mode = v
            self.paint_notes()

    def set_unit(self, v):
        if self.cur:
            self.cur.rate_unit = v
            self.paint_notes()
            self.rebuild_list()

    def set_duty(self, v):
        if self.cur:
            self.cur.duty = max(0.05, min(0.95, float(v) / 100))
            self.paint_notes()

    def set_corners(self, v):
        if self.cur:
            self.cur.corners_only = v

    def get_random(self):
        return self.cur.random_rate if self.cur else False

    def set_random(self, v):
        if self.cur:
            self.cur.random_rate = v
            self.paint_notes()
            self.rebuild_list()

    def get_edge(self):
        return self.cur.edge_stop if self.cur else True

    def set_edge(self, v):
        if self.cur:
            self.cur.edge_stop = v

    def get_pos(self):
        return self.cur.fixed_position if self.cur else False

    def set_pos(self, v):
        if self.cur:
            self.cur.fixed_position = v
            self.paint_notes()

    def _num(self, var, fallback, lo, hi):
        try:
            return min(hi, max(lo, float(var.get())))
        except ValueError:
            return fallback

    def read_rate(self):
        r = self.cur
        if not r:
            return
        r.rate_value = self._num(self.rate_var, r.rate_value, 0.0001, 1000)
        r.rate_min = self._num(self.rmin_var, r.rate_min, 0.01, 1000)
        r.rate_max = self._num(self.rmax_var, r.rate_max, 0.01, 1000)
        self.paint_notes()
        self.rebuild_list()

    def read_key(self):
        if self.cur:
            self.cur.key_text = self.key_var.get()[:12] or "a"
            self.paint_notes()
            self.rebuild_list()

    def read_limits(self):
        r = self.cur
        if not r:
            return
        r.limit_clicks = int(self._num(self.climit_var, r.limit_clicks, 0, 10_000_000))
        r.limit_seconds = self._num(self.tlimit_var, r.limit_seconds, 0, 86400)

    # ---------------------------------------------------------------- trigger capture
    def capture_trigger(self):
        """Rather than a list of sixteen button names, just listen for the next press.

        Binding a pad button by pressing it is both faster and impossible to get wrong,
        and it needs no explanation."""
        self.capturing = not self.capturing
        self.paint_capture()

    def paint_capture(self):
        r = self.cur
        if self.capturing:
            self.trigger_btn.configure(text="  PRESS ANY PAD BUTTON  ")
            self.ui.restyle(self.trigger_btn, ACCENT, ACCENT_HI, INK_ON_LIGHT)
        else:
            self.trigger_btn.configure(
                text=f"  {LABEL.get(r.trigger, r.trigger) if r else '—'}  ")
            self.ui.restyle(self.trigger_btn, RAISED, RAISED_HI, TEXT)

    def offer_button(self, slot, key):
        """Called by the app when any pad button goes down."""
        if not self.capturing or not self.cur:
            return False
        self.cur.trigger = key
        self.capturing = False
        self.paint_capture()
        self.rebuild_list()
        self.paint_notes()
        return True

    # ---------------------------------------------------------------- position pick
    def pick_position(self):
        """Give the user three seconds to park the pointer, then read it.

        Clicking a button to record a position cannot work, because the click has to
        happen on the button. A countdown is the simplest thing that does."""
        self.picking = True
        self.pick_until = time.perf_counter() + 3.0

    def tick_pick(self, now):
        if not self.picking:
            return
        left = self.pick_until - now
        if left <= 0:
            self.picking = False
            x, y = cursor_pos()
            if self.cur:
                self.cur.pos_x, self.cur.pos_y = x, y
                self.cur.fixed_position = True
                self.pos_switch.paint()
            self.pick_btn.configure(text="PICK A SPOT")
            self.paint_notes()
        else:
            self.pick_btn.configure(text=f"HOLD STILL… {left:.1f}")

    # ---------------------------------------------------------------- setup check
    def run_self_test(self):
        """Type a known word into the box using the same path a macro uses.

        If the characters appear, synthetic input works on this machine and every
        later failure is about the target window rather than the setup."""
        self.test_note.configure(text="Typing into the box…", fg=MUTED)
        self.test_btn.configure(text="TESTING…")
        self.selftest.start(self.finish_self_test)

    def finish_self_test(self, ok, got):
        self.test_btn.configure(text="RUN TEST")
        if ok:
            self.test_note.configure(
                text="Output works. Cadence can drive the keyboard and mouse on this "
                     "machine.", fg=BRAND_HI)
        elif not self.engine.synth.live:
            self.test_note.configure(
                text="Output is switched off for this run, so nothing was sent. "
                     "That is the --no-output flag, not a fault.", fg=ACCENT)
        else:
            self.test_note.configure(
                text=f"Nothing arrived (box reads '{got}'). Something is intercepting "
                     f"synthetic input - antivirus, an overlay, or the window losing "
                     f"focus mid-test. Try again with this window in front.", fg=MISS)

    def refresh_env(self):
        notes = diagnostics.summarise(self.engine.synth.live, self.app.hotkey_ok(),
                                      self.app.panic_key)
        worst = "warn" if any(k == "warn" for k, _ in notes) else "info"
        text = "  ·  ".join(t for _, t in notes)
        self.env_note.configure(text=text, fg=ACCENT if worst == "warn" else MUTED)

    # ---------------------------------------------------------------- master
    def toggle_master(self):
        self.engine.set_master(not self.engine.armed_master)
        self.paint_master()

    def paint_master(self):
        on = self.engine.armed_master
        self.master_btn.configure(text="ARMED" if on else "DISARMED")
        self.ui.restyle(self.master_btn, BRAND if on else RAISED,
                        BRAND_HI if on else RAISED_HI, TEXT)
        if on:
            self.state_line.configure(text="Macros are live", fg=TEXT)
            if self.app.hotkey_ok():
                self.state_note.configure(
                    text=f"Hold or toggle a bound button to fire. {self.app.panic_key} "
                         f"stops everything, so does putting the mouse in a screen "
                         f"corner.", fg=MUTED)
            else:
                self.state_note.configure(
                    text=f"Hold or toggle a bound button to fire. {self.app.panic_key} "
                         f"could not be registered - another app owns it. Use a "
                         f"different panic key, or stop with a screen corner.", fg=ACCENT)
        else:
            self.state_line.configure(text="Nothing will fire", fg=MUTED)
            last = self.engine.last_stop
            self.state_note.configure(
                text=f"Last stop: {last}." if last else
                     "Arm this to let pad buttons drive the mouse and keyboard.")

    def toggle_advanced(self):
        self.advanced = not self.advanced
        self.paint_mode_btn()

    def paint_mode_btn(self):
        on = self.advanced
        self.mode_btn.configure(text="ADVANCED" if on else "SIMPLE")
        self.ui.restyle(self.mode_btn, BRAND if on else RAISED,
                        BRAND_HI if on else RAISED_HI, TEXT)
        if on:
            self.adv.pack(fill="x", after=self.simple_block)
        else:
            self.adv.pack_forget()

    # ---------------------------------------------------------------- app hooks
    def refresh_all(self):
        self.rebuild_list()
        self.load_rule()

    def tick(self, latest, connected, dirty):
        now = time.perf_counter()
        self.tick_pick(now)
        self.m_sent.value.configure(
            text=f"{self.engine.total_fired:,}",
            fg=BRAND_HI if self.engine.armed_master else MUTED)
        ok = self.app.hotkey_ok()
        if self._hotkey_seen != ok:
            self._hotkey_seen = ok
            self.paint_master()
            self.refresh_env()
        for rule in self.engine.rules:
            item = self.rows.get(rule.id)
            if not item:
                continue
            lamp, lamp_id = item[3], item[4]
            colour = (ACCENT if rule.armed else
                      (BRAND_HI if self.engine.armed_master and rule.enabled else DIM))
            lamp.itemconfigure(lamp_id, fill=colour)
