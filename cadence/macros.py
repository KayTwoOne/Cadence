"""Controller-triggered macros: hold a pad button, get a stream of clicks or keys.

The engine runs on its own thread and never blocks on a press. Each rule is a small
state machine holding "when is my next press due" and "when is the current one due to
be released", so several rules at different rates interleave cleanly and one slow duty
cycle cannot stall another rule.

Every rule can stop itself: a click budget, a time budget, and the mouse being shoved
into the edge of the screen. That last one matters most - it means a runaway macro is
always recoverable by moving the mouse, without needing the keyboard or the window.
"""

import time
import random
import threading

from . import synth

RATE_UNITS = {"second": 1.0, "minute": 60.0, "hour": 3600.0, "day": 86400.0}
ACTIONS = ("mouse", "key", "double")
MIN_INTERVAL = 0.001        # 1000 per second is past anything useful and stays safe
MIN_DOWN_S = 0.001


class Rule:
    """One macro. Defaults are the simple mode; the rest only matter in advanced."""

    _next_id = 1

    def __init__(self, trigger="RB", slot=None):
        self.id = Rule._next_id
        Rule._next_id += 1
        self.name = f"Macro {self.id}"
        self.enabled = True
        self.trigger = trigger       # controller button key, e.g. "RB"
        self.slot = slot             # None = any controller, else that slot only
        self.mode = "hold"           # "hold" while pressed, or "toggle" on/off
        self.action = "mouse"        # mouse | key | double
        self.button = "left"         # left | right | middle
        self.key_text = "a"          # literal character, case honoured, or a name
        # rate
        self.rate_value = 10.0
        self.rate_unit = "second"
        self.random_rate = False
        self.rate_min = 8.0
        self.rate_max = 14.0
        self.duty = 0.25             # share of the interval the button stays down
        # limits and safety
        self.limit_clicks = 0        # 0 = no limit
        self.limit_seconds = 0.0     # 0 = no limit
        self.edge_stop = True
        self.edge_margin = 2
        self.corners_only = True
        # position clicking
        self.fixed_position = False
        self.pos_x = 0
        self.pos_y = 0

        # live state, owned by the engine thread
        self.armed = False
        self.fired = 0
        self.session_fired = 0
        self.started_at = 0.0
        self.next_at = 0.0
        self.release_at = 0.0
        self.down = False
        self.stopped_reason = ""

    # ---- derived
    def base_interval(self):
        """Seconds between presses, from whichever rate control is in use."""
        if self.random_rate:
            lo, hi = sorted((max(0.01, self.rate_min), max(0.01, self.rate_max)))
            per_second = random.uniform(lo, hi)
            return max(MIN_INTERVAL, 1.0 / per_second)
        unit = RATE_UNITS.get(self.rate_unit, 1.0)
        value = max(0.000001, self.rate_value)
        return max(MIN_INTERVAL, unit / value)

    def describe_rate(self):
        if self.random_rate:
            lo, hi = sorted((self.rate_min, self.rate_max))
            return f"{lo:g}-{hi:g} per second, random"
        return f"{self.rate_value:g} per {self.rate_unit}"

    def describe_action(self):
        if self.action == "key":
            return f"key '{self.key_text}'"
        if self.action == "double":
            return f"double {self.button} click"
        return f"{self.button} click"

    def summary(self):
        where = "any pad" if self.slot is None else f"pad {self.slot + 1}"
        return (f"{self.trigger} on {where} · {self.mode} · {self.describe_action()} · "
                f"{self.describe_rate()}")

    def to_dict(self):
        skip = {"armed", "fired", "session_fired", "started_at", "next_at",
                "release_at", "down", "stopped_reason", "id"}
        return {k: v for k, v in self.__dict__.items() if k not in skip}

    def load(self, data):
        for k, v in data.items():
            if hasattr(self, k) and k != "id":
                setattr(self, k, v)


class MacroEngine(threading.Thread):
    """Owns every rule's timing. The UI only ever hands it events and reads counters."""

    def __init__(self, sender=None, on_change=None):
        super().__init__(daemon=True)
        self.synth = sender or synth.Synth()
        self.on_change = on_change or (lambda: None)
        self.rules = []
        self.running = True
        self.armed_master = False     # the big on/off; nothing fires while this is off
        self.lock = threading.Lock()
        self.last_stop = ""
        self.total_fired = 0

    # ---- rule bookkeeping
    def add(self, rule=None):
        rule = rule or Rule()
        with self.lock:
            self.rules.append(rule)
        return rule

    def remove(self, rule):
        with self.lock:
            self._disarm(rule, "removed")
            if rule in self.rules:
                self.rules.remove(rule)

    def set_master(self, on):
        """The master switch. Turning it off releases anything held down, so a macro
        can never leave a mouse button stuck after being stopped."""
        with self.lock:
            self.armed_master = bool(on)
            if not on:
                for r in self.rules:
                    self._disarm(r, "master off")
        self.on_change()

    def panic(self, reason="panic key"):
        self.last_stop = reason
        self.set_master(False)

    # ---- events in from the controller
    def handle(self, slot, key, down):
        """A controller button changed. Arms or disarms whatever is bound to it."""
        if not self.armed_master:
            return
        changed = False
        with self.lock:
            for r in self.rules:
                if not r.enabled or r.trigger != key:
                    continue
                if r.slot is not None and r.slot != slot:
                    continue
                if r.mode == "hold":
                    if down and not r.armed:
                        self._arm(r)
                        changed = True
                    elif not down and r.armed:
                        self._disarm(r, "released")
                        changed = True
                elif down:                      # toggle acts on the press only
                    if r.armed:
                        self._disarm(r, "toggled off")
                    else:
                        self._arm(r)
                    changed = True
        if changed:
            self.on_change()

    def _arm(self, r):
        r.armed = True
        r.session_fired = 0
        r.started_at = time.perf_counter()
        r.next_at = r.started_at            # first press goes out immediately
        r.release_at = 0.0
        r.down = False
        r.stopped_reason = ""

    def _disarm(self, r, reason=""):
        if r.down:
            self._release(r)
        r.armed = False
        r.stopped_reason = reason

    # ---- output
    def _press(self, r):
        if r.fixed_position:
            self.synth.move_to(r.pos_x, r.pos_y)
        if r.action == "key":
            self.synth.key(r.key_text, True)
        else:
            self.synth.mouse(r.button, True)
        r.down = True

    def _release(self, r):
        if r.action == "key":
            self.synth.key(r.key_text, False)
        else:
            self.synth.mouse(r.button, False)
        r.down = False
        if r.action == "double":
            # The second click of a double has to land inside the system's double-click
            # time, so it goes out immediately rather than waiting for the next tick.
            self.synth.mouse(r.button, True)
            self.synth.mouse(r.button, False)

    def _limits_hit(self, r, now):
        if r.limit_clicks and r.session_fired >= r.limit_clicks:
            return f"limit {r.limit_clicks} reached"
        if r.limit_seconds and now - r.started_at >= r.limit_seconds:
            return f"{r.limit_seconds:g}s elapsed"
        if r.edge_stop and synth.near_edge(r.edge_margin, r.corners_only):
            return "mouse at screen edge"
        return ""

    # ---- the loop
    def run(self):
        sleeper = None
        try:
            from .hardware import PrecisionSleeper
            sleeper = PrecisionSleeper()
        except Exception:
            pass
        while self.running:
            now = time.perf_counter()
            busy = False
            stops = []
            with self.lock:
                for r in self.rules:
                    if not r.armed:
                        continue
                    busy = True
                    if r.down:
                        if now >= r.release_at:
                            self._release(r)
                        continue
                    reason = self._limits_hit(r, now)
                    if reason:
                        self._disarm(r, reason)
                        stops.append(reason)
                        continue
                    if now >= r.next_at:
                        interval = r.base_interval()
                        down_s = max(MIN_DOWN_S,
                                     min(interval * max(0.02, min(0.95, r.duty)),
                                         interval - MIN_DOWN_S))
                        self._press(r)
                        r.release_at = now + down_s
                        r.next_at = now + interval
                        r.fired += 1
                        r.session_fired += 1
                        self.total_fired += 1
            if stops:
                self.last_stop = stops[-1]
                self.on_change()
            if busy:
                if sleeper:
                    sleeper.sleep(0.0005)
                else:
                    time.sleep(0.0005)
            else:
                time.sleep(0.01)
        if sleeper:
            sleeper.close()

    def stop(self):
        self.set_master(False)
        self.running = False


class GlobalHotkey(threading.Thread):
    """A panic key that works even when Cadence is not the focused window.

    An auto-clicker that can only be stopped from its own window is a trap, because
    the clicks it is sending are landing in whatever app you are actually looking at.
    """

    def __init__(self, vk, callback):
        super().__init__(daemon=True)
        self.vk = vk
        self.callback = callback
        self.thread_id = None
        self.ok = False

    def run(self):
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        self.thread_id = k.GetCurrentThreadId()
        if not u.RegisterHotKey(None, 1, 0x4000, self.vk):   # 0x4000 = MOD_NOREPEAT
            return
        self.ok = True
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:            # WM_HOTKEY
                try:
                    self.callback()
                except Exception:
                    pass
        u.UnregisterHotKey(None, 1)

    def stop(self):
        if self.thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)  # WM_QUIT
