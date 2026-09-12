"""Reading controllers through XInput, and knowing how much to trust the readings.

XInput hands back the last report the *controller* sent, not the live state of the
buttons. Controllers report on their own schedule - typically every 4 to 8 ms - so
reading faster than that just re-reads the same packet. The controller's report rate,
not the read rate, sets the real limit on precision, and this module measures it.
"""

import sys
import time
import math
import queue
import ctypes
import statistics
import threading
from collections import deque

# ---------------------------------------------------------------- settings
TRIGGER_PRESS = 30          # 0-255: trigger counts as pressed at/above this
TRIGGER_RELEASE = 20        # ...and released below this (stops flicker)
POLL_SLEEP = 0.0004         # seconds between controller reads
SCAN_INTERVAL = 1.0         # seconds between checks for newly plugged-in controllers
REPORT_SAMPLES = 240        # packet-change intervals kept to estimate the report rate
REPORT_MIN_SAMPLES = 24     # ...and how many are needed before the estimate is shown
ASSUMED_REPORT_MS = 4.0     # what to assume a pad does until its real rate is known
ANALOG_STICK_MIN = 3000     # raw stick units: past this the pad is definitely moving
ANALOG_TRIGGER_MIN = 5

LT_BIT, RT_BIT = 0x10000, 0x20000

# bit, key, label, colour-key
BUTTONS = [
    (0x1000, "A", "A"), (0x2000, "B", "B"), (0x4000, "X", "X"), (0x8000, "Y", "Y"),
    (0x0100, "LB", "LB"), (0x0200, "RB", "RB"),
    (LT_BIT, "LT", "LT"), (RT_BIT, "RT", "RT"),
    (0x0040, "LS", "LS"), (0x0080, "RS", "RS"),
    (0x0001, "UP", "D↑"), (0x0002, "DOWN", "D↓"),
    (0x0004, "LEFT", "D←"), (0x0008, "RIGHT", "D→"),
    (0x0020, "BACK", "View"), (0x0010, "START", "Menu"),
]
BIT = {k: b for b, k, _ in BUTTONS}
LABEL = {k: l for _, k, l in BUTTONS}
KEYS = [k for _, k, _ in BUTTONS]

SUBTYPE = {0: "unknown", 1: "gamepad", 2: "wheel", 3: "arcade stick", 4: "flight stick",
           5: "dance pad", 6: "guitar", 7: "guitar alt", 8: "drum kit", 11: "guitar bass",
           19: "arcade pad"}
BATT_TYPE = {0: "no battery", 1: "wired", 2: "alkaline", 3: "rechargeable"}
BATT_LEVEL = {0: "empty", 1: "low", 2: "medium", 3: "full"}


# ---------------------------------------------------------------- ctypes plumbing
class XInputGamepad(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_uint16),
                ("bLeftTrigger", ctypes.c_uint8), ("bRightTrigger", ctypes.c_uint8),
                ("sThumbLX", ctypes.c_int16), ("sThumbLY", ctypes.c_int16),
                ("sThumbRX", ctypes.c_int16), ("sThumbRY", ctypes.c_int16)]


class XInputState(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("Gamepad", XInputGamepad)]


class XInputCaps(ctypes.Structure):
    _fields_ = [("Type", ctypes.c_uint8), ("SubType", ctypes.c_uint8),
                ("Flags", ctypes.c_uint16), ("Gamepad", XInputGamepad),
                ("Vibration", ctypes.c_uint16 * 2)]


class XInputBattery(ctypes.Structure):
    _fields_ = [("BatteryType", ctypes.c_uint8), ("BatteryLevel", ctypes.c_uint8)]


class XInputReader:
    def __init__(self):
        dll = None
        for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                dll = ctypes.WinDLL(name)
                break
            except (OSError, AttributeError):
                continue
        if dll is None:
            raise RuntimeError("XInput could not be loaded. This tool needs Windows.")
        self.dll = dll
        self.fn = dll.XInputGetState
        self.fn.argtypes = [ctypes.c_uint32, ctypes.POINTER(XInputState)]
        self.fn.restype = ctypes.c_uint32

    def read(self, slot, buf):
        """buf is an XInputState owned by the calling thread."""
        if self.fn(slot, ctypes.byref(buf)) != 0:
            return None
        g = buf.Gamepad
        return (buf.dwPacketNumber, g.wButtons, g.bLeftTrigger, g.bRightTrigger,
                g.sThumbLX, g.sThumbLY, g.sThumbRX, g.sThumbRY)

    def describe(self, slot):
        """What kind of device this is, and how it is powered.

        Wireless pads report less often than wired ones, so this is not trivia - it
        is the first thing to check when the measured resolution looks poor."""
        out = {}
        try:
            caps = XInputCaps()
            if self.dll.XInputGetCapabilities(slot, 0, ctypes.byref(caps)) == 0:
                out["subtype"] = SUBTYPE.get(caps.SubType, f"type {caps.SubType}")
                out["wireless"] = bool(caps.Flags & 0x0004)
        except Exception:
            pass
        try:
            b = XInputBattery()
            if self.dll.XInputGetBatteryInformation(slot, 0, ctypes.byref(b)) == 0:
                out["power"] = BATT_TYPE.get(b.BatteryType, "?")
                if b.BatteryType in (2, 3):
                    out["battery"] = BATT_LEVEL.get(b.BatteryLevel, "?")
        except Exception:
            pass
        return out


class DemoReader:
    """Two fake controllers: slot 1 does flip + cancel, slot 2 does double jumps."""

    DEMO_REPORT_MS = 4.0    # a real pad only sends state every few ms, so this does too

    def __init__(self):
        import random
        self.random = random
        self.t0 = time.perf_counter()
        self.packet = {0: 0, 1: 0}
        self.last = {0: None, 1: None}
        self.cycle = {0: -1, 1: -1}
        self.j = {0: [0] * 6, 1: [0] * 6}

    def describe(self, slot):
        return {"subtype": "gamepad (demo)", "wireless": False, "power": "wired"}

    def _jitter(self, slot, cycle):
        if cycle != self.cycle[slot]:
            self.cycle[slot] = cycle
            self.j[slot] = [self.random.uniform(-12, 12) for _ in range(6)]
        return self.j[slot]

    def read(self, slot, buf=None):
        if slot not in (0, 1):
            return None
        elapsed = (time.perf_counter() - self.t0) * 1000
        bucket = math.floor(elapsed / self.DEMO_REPORT_MS)
        elapsed = bucket * self.DEMO_REPORT_MS
        btn, lt, rt, ly = 0, 0, 0, 0
        if slot == 0:
            cycle, ms = divmod(elapsed, 2400)
            j = self._jitter(0, cycle)
            if ms < 70 + j[0] or 120 + j[1] <= ms < 150 + j[2]:
                btn |= BIT["A"]
            if 220 + j[3] <= ms < 640:
                btn |= BIT["B"]
            if 180 + j[4] <= ms < 260 + j[5]:
                btn |= BIT["X"]
            rt = 255 if ms < 900 or ms >= 1650 else 0
            if 100 <= ms < 170 + j[2]:
                ly = 32767
            elif 170 + j[2] <= ms < 420:
                ly = -32768
        else:
            cycle, ms = divmod(elapsed + 700, 1900)
            j = self._jitter(1, cycle)
            if ms < 55 + j[0] or 95 + j[1] <= ms < 140 + j[2]:
                btn |= BIT["A"]
            if 60 + j[3] <= ms < 500:
                btn |= BIT["LB"]
            lt = 200 if 300 <= ms < 700 else 0
        # Noise derived from the report number, not per read, so every read inside one
        # report window returns byte-identical state exactly as a real pad does.
        noise = (bucket * 2654435761) % 5 - 2
        st = (btn, lt, rt, noise, ly + noise, 0, 0)
        if st != self.last[slot]:
            self.last[slot] = st
            self.packet[slot] += 1
        return (self.packet[slot],) + st


# ---------------------------------------------------------------- timing helpers
def percentile(sorted_vals, frac):
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, int(round(frac * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


class PrecisionSleeper:
    """Sleeps for well under a millisecond.

    time.sleep() on Windows rounds up to the system timer tick, so asking for 0.4 ms
    really sleeps 1-1.5 ms. A high-resolution waitable timer (Windows 10 1803+) gets
    close to what was asked for; anything older falls back to plain sleep."""

    def __init__(self):
        self.handle = None
        self.kernel = None
        if sys.platform != "win32":
            return
        try:
            k = ctypes.windll.kernel32
            k.CreateWaitableTimerExW.restype = ctypes.c_void_p
            k.CreateWaitableTimerExW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                                 ctypes.c_uint32, ctypes.c_uint32]
            # 0x2 = CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, 0x1F0003 = TIMER_ALL_ACCESS
            h = k.CreateWaitableTimerExW(None, None, 0x2, 0x1F0003)
            if not h:
                return
            k.SetWaitableTimer.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64),
                                           ctypes.c_int32, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_int32]
            k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            self.handle, self.kernel = h, k
        except (AttributeError, OSError):
            self.handle = None

    @property
    def precise(self):
        return self.handle is not None

    def sleep(self, seconds):
        if self.handle is None:
            time.sleep(seconds)
            return
        due = ctypes.c_int64(int(-seconds * 1e7))   # negative = relative, 100 ns units
        if not self.kernel.SetWaitableTimer(self.handle, ctypes.byref(due), 0, None, None, 0):
            time.sleep(seconds)
            return
        self.kernel.WaitForSingleObject(self.handle, 0xFFFFFFFF)

    def close(self):
        if self.handle is not None:
            try:
                ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            except Exception:
                pass
            self.handle = None


class ReportRate:
    """Works out how often a controller actually sends a new report.

    XInput bumps dwPacketNumber only when the device sends *different* state, which is
    the catch. A pad whose driver snaps the sticks to dead zero while idle sends
    nothing at all, and then the only packet changes are your own button presses -
    measuring those would report how fast you were pressing buttons and call it the
    pad's report rate, which is nonsense.

    So intervals are only collected while an analogue input is genuinely in motion: a
    stick off centre, or a trigger part way down. In that state the raw values wobble
    every report and the intervals really are the report period. In Rocket League this
    is continuous, because you are always holding a trigger and steering.
    """

    def __init__(self):
        self.gaps = deque(maxlen=REPORT_SAMPLES)
        self.last_change = None
        self.prev_active = False
        self.period_ms = 0.0
        self.samples_seen = 0

    def reset(self):
        self.gaps.clear()
        self.last_change = None
        self.prev_active = False
        self.period_ms = 0.0
        self.samples_seen = 0

    def saw_change(self, t, analog_active):
        # Both ends of an interval must fall inside a stretch of analogue motion,
        # otherwise the gap spans a period of silence and means nothing.
        if analog_active and self.prev_active and self.last_change is not None:
            g = (t - self.last_change) * 1000
            if 0.05 < g < 60:
                self.gaps.append(g)
                self.samples_seen += 1
        self.last_change = t
        self.prev_active = analog_active
        if len(self.gaps) >= REPORT_MIN_SAMPLES:
            self.period_ms = self._estimate()

    def _estimate(self):
        """Find one report period from intervals that are whole multiples of it.

        A low percentile picks out the single-period cluster rather than the doubles
        and triples that appear whenever the pad had nothing new to send. But that
        percentile sits on the fast edge of the cluster, because a late read only ever
        lengthens the interval it ends and shortens the next. Averaging the whole
        cluster around it puts the estimate back in the middle where it belongs."""
        base = percentile(sorted(self.gaps), 0.15)
        if base <= 0:
            return 0.0
        cluster = [g for g in self.gaps if 0.6 * base <= g <= 1.6 * base]
        return statistics.fmean(cluster) if len(cluster) >= 5 else base

    @property
    def measured(self):
        return self.period_ms > 0

    @property
    def resolution_ms(self):
        """Worst-case error from not knowing where inside a report the press landed.

        Until enough samples arrive this assumes a slow-ish pad rather than a fast one.
        Guessing pessimistically can only make the app look less precise than it is,
        which is the safe direction to be wrong in."""
        period = self.period_ms if self.period_ms else ASSUMED_REPORT_MS
        return period / 2


def boost_thread_priority(level=2):
    if sys.platform != "win32":
        return
    try:
        k = ctypes.windll.kernel32
        k.GetCurrentThread.restype = ctypes.c_void_p
        k.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        k.SetThreadPriority(k.GetCurrentThread(), level)  # 2 = THREAD_PRIORITY_HIGHEST
    except Exception:
        pass


class Poller(threading.Thread):
    """Reads every connected controller in a tight loop and emits press/release events.

    Checking empty XInput slots can be slow, so a separate scanner thread looks for
    newly connected controllers and hands them over. That keeps the timing loop fast.
    """

    def __init__(self, reader, out_q):
        super().__init__(daemon=True)
        self.reader = reader
        self.q = out_q
        self.running = True
        self.active = {}          # slot -> per-controller state (poller thread only)
        self.found = queue.Queue()
        self.latest = {}          # slot -> (mask, lt, rt, lx, ly, rx, ry) for drawing
        self.connected = set()    # read by the scanner thread
        self.info = {}            # slot -> device description
        self.sample_hz = 0.0
        self.worst_poll_ms = 0.0  # slowest single trip round the loop in the last window
        self.rates = {}           # slot -> ReportRate
        self.sleeper = PrecisionSleeper()
        self.scanner = threading.Thread(target=self._scan, daemon=True)

    # ---- what the UI asks about
    def report_ms(self, slot):
        r = self.rates.get(slot)
        return r.period_ms if r else 0.0

    def measured(self, slot):
        r = self.rates.get(slot)
        return bool(r and r.measured)

    def analog_samples(self, slot):
        r = self.rates.get(slot)
        return r.samples_seen if r else 0

    def recalibrate(self, slot):
        r = self.rates.get(slot)
        if r:
            r.reset()

    def resolution_ms(self, slot):
        """How far out a single measured gap could be, in ms.

        Two sources add up: the controller quantises the press to its own report (half
        a report period either way) and the reader can be late by however long a loop
        took. The report period is almost always the bigger of the two."""
        r = self.rates.get(slot)
        quant = r.resolution_ms if r else ASSUMED_REPORT_MS / 2
        return quant + min(self.worst_poll_ms, 4.0) / 2

    def _scan(self):
        buf = XInputState()
        while self.running:
            for slot in range(4):
                if slot not in self.connected and self.reader.read(slot, buf) is not None:
                    self.connected.add(slot)
                    self.found.put(slot)
            time.sleep(SCAN_INTERVAL)

    def run(self):
        boost_thread_priority()
        self.scanner.start()
        buf = XInputState()
        loops = 0
        t_rate = time.perf_counter()
        t_loop = t_rate
        worst = 0.0
        while self.running:
            while not self.found.empty():
                slot = self.found.get_nowait()
                self.active[slot] = {"held": 0, "packet": None, "seen": time.perf_counter()}
                self.rates[slot] = ReportRate()
                try:
                    self.info[slot] = self.reader.describe(slot)
                except Exception:
                    self.info[slot] = {}
                self.q.put(("connected", slot, None, time.perf_counter(), None))

            for slot in list(self.active):
                st = self.active[slot]
                # Bracket the read. The change happened somewhere between the previous
                # read of this slot and now, so the middle of the read is the least
                # biased single instant we can pin it to.
                t_before = time.perf_counter()
                s = self.reader.read(slot, buf)
                t_after = time.perf_counter()
                t = (t_before + t_after) / 2
                window = (t_after - st["seen"]) * 1000
                st["seen"] = t_after
                if s is None:
                    for bit, key, _ in BUTTONS:
                        if st["held"] & bit:
                            self.q.put(("up", slot, key, t, None))
                    del self.active[slot]
                    self.latest.pop(slot, None)
                    self.rates.pop(slot, None)
                    self.info.pop(slot, None)
                    self.connected.discard(slot)
                    self.q.put(("disconnected", slot, None, t, None))
                    continue
                packet, btn, lt, rt, lx, ly, rx, ry = s
                if packet == st["packet"]:
                    continue
                st["packet"] = packet
                analog = (max(abs(lx), abs(ly), abs(rx), abs(ry)) > ANALOG_STICK_MIN
                          or lt > ANALOG_TRIGGER_MIN or rt > ANALOG_TRIGGER_MIN)
                self.rates[slot].saw_change(t, analog)
                held = st["held"]
                mask = btn & 0xF3FF
                if lt >= TRIGGER_PRESS or (held & LT_BIT and lt >= TRIGGER_RELEASE):
                    mask |= LT_BIT
                if rt >= TRIGGER_PRESS or (held & RT_BIT and rt >= TRIGGER_RELEASE):
                    mask |= RT_BIT
                changed = mask ^ held
                if changed:
                    stick = (max(-1.0, lx / 32767), max(-1.0, ly / 32767))
                    for bit, key, _ in BUTTONS:
                        if changed & bit:
                            trig = lt if bit == LT_BIT else (rt if bit == RT_BIT else None)
                            self.q.put(("down" if mask & bit else "up", slot, key, t,
                                        (stick, window, trig)))
                    st["held"] = mask
                self.latest[slot] = (mask, lt, rt, lx, ly, rx, ry)

            loops += 1
            now = time.perf_counter()
            if self.active:
                worst = max(worst, (now - t_loop) * 1000)
            t_loop = now
            if now - t_rate >= 0.5:
                self.sample_hz = loops / (now - t_rate) if self.active else 0.0
                self.worst_poll_ms = worst if self.active else 0.0
                loops, worst, t_rate = 0, 0.0, now
            if self.active:
                self.sleeper.sleep(POLL_SLEEP)
            else:
                time.sleep(0.05)
        self.sleeper.close()
