"""Press history and the statistics drawn from it."""

import math
import statistics
from collections import deque, OrderedDict

from .hardware import LABEL

# Game engines sample input once per tick, so a gap only matters to the engine in
# whole ticks. 120 Hz is a common rate and the default here; set_tick_rate changes it
# for engines that run at 60, 64, 128 or anything else.
TICK_HZ = 120.0
TICK_MS = 1000 / TICK_HZ


def set_tick_rate(hz):
    """Point the tick column at whatever rate you are actually playing at."""
    global TICK_HZ, TICK_MS
    TICK_HZ = max(1.0, min(1000.0, float(hz)))
    TICK_MS = 1000 / TICK_HZ
    return TICK_HZ


STICK_DEADZONE = 0.35       # 0-1: below this the stick counts as centred
SPLIT_MIN_MS = 25           # two groups of a button pair must differ by at least this
TARGET_WINDOW = 25          # hit rate is measured over the last this many attempts
PAIR_WINDOW = 25            # attempts kept per button pair

ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]


def stick_arrow(x, y):
    if math.hypot(x, y) < STICK_DEADZONE:
        return "centred"
    ang = math.degrees(math.atan2(y, x))           # 0 = right, 90 = up
    idx = int(round(((90 - ang) % 360) / 45)) % 8  # 0 = up, clockwise
    return ARROWS[idx]


def fmt_ms(value, resolution):
    """Print a millisecond figure to the precision the hardware can actually support.

    A controller that reports every 4 ms cannot tell you a gap was 301.7 ms rather
    than 302 ms, so printing that decimal invents confidence that isn't there."""
    if value is None:
        return ""
    if resolution >= 2.5:
        return f"{value:.0f} ms"
    if resolution >= 0.8:
        return f"{value:.1f} ms"
    return f"{value:.2f} ms"


def fmt_ticks(gap):
    """A gap in whole engine ticks, because fractions of a tick are never sampled.

    The fractional part lands somewhere inside a tick and the engine never sees it,
    which is why this reads 36 rather than 36.2."""
    if gap is None:
        return ""
    return f"{gap / TICK_MS:.0f}"


class TimingModel:
    """Press history for one controller."""

    def __init__(self, ignored, gap_ref):
        self.ignored = ignored      # shared set of ignored buttons
        self.gap_ref = gap_ref      # shared [sequence_gap_ms]
        self.reset()

    def reset(self):
        self.presses = []
        self.open = {}
        self.last = None
        self.sequence = []
        self.seq_no = 0
        self.pairs = OrderedDict()
        self.recent_gaps = deque(maxlen=TARGET_WINDOW)

    def press(self, key, t, payload):
        if key in self.ignored:
            return None
        stick, window, trig = payload if payload else ((0.0, 0.0), 0.0, None)
        gap = None
        if self.last is not None:
            g = (t - self.last["t"]) * 1000
            if g <= self.gap_ref[0]:
                gap = g
        if gap is None:
            self.seq_no += 1
            self.sequence = []
        rec = {"n": (self.presses[-1]["n"] + 1) if self.presses else 1, "key": key, "t": t,
               "gap": gap, "held": None, "stick": stick or (0.0, 0.0), "seq": self.seq_no,
               "win": window, "trig": trig,
               "prev": self.last["key"] if gap is not None else None}
        if gap is not None:
            self.recent_gaps.append(gap)
            pk = (rec["prev"], key)
            d = self.pairs.pop(pk, None) or deque(maxlen=PAIR_WINDOW)
            d.append(gap)
            self.pairs[pk] = d
        self.presses.append(rec)
        if len(self.presses) > 20000:
            self.presses = self.presses[-10000:]
        self.sequence.append(rec)
        self.open[key] = rec
        self.last = rec
        return rec

    def release(self, key, t):
        rec = self.open.pop(key, None)
        if rec is not None:
            rec["held"] = (t - rec["t"]) * 1000
        return rec

    @staticmethod
    def _split(vals):
        """The same two buttons often get used for two different things, so A -> A can
        be a fast repeat and a slow one at once. Split when the times fall into two
        clearly separate groups, so one average doesn't blend them together."""
        if len(vals) < 6:
            return None
        v = sorted(vals)
        cut = max(range(1, len(v)), key=lambda i: v[i] - v[i - 1])
        lo, hi = v[:cut], v[cut:]
        sep = v[cut] - v[cut - 1]
        if len(lo) < 3 or len(hi) < 3 or sep < SPLIT_MIN_MS or sep < 0.35 * (v[-1] - v[0]):
            return None
        return lo, hi

    @staticmethod
    def _row(a, b, vals, note=""):
        """Median leads because button timing is skewed: one fumbled press drags a mean
        around far more than it reflects how you actually play. Spread is the sample
        standard deviation, which is what you want from a sample of attempts."""
        return (f"{LABEL[a]} → {LABEL[b]}" + (f"  {note}" if note else ""),
                statistics.median(vals),
                statistics.stdev(vals) if len(vals) > 1 else 0.0,
                min(vals), len(vals))

    def pair_stats(self, limit=6):
        out = []
        for (a, b), d in reversed(self.pairs.items()):
            vals = list(d)
            groups = self._split(vals)
            if groups and len(out) + 2 <= limit:
                lo, hi = groups
                out.append(self._row(a, b, lo, "quick"))
                out.append(self._row(a, b, hi, "delayed"))
            else:
                out.append(self._row(a, b, vals))
            if len(out) >= limit:
                break
        return out[:limit]

    def target_hits(self, target, tol):
        """How many of the recent gaps landed inside the practice window."""
        vals = list(self.recent_gaps)
        if not vals:
            return 0, 0
        return sum(1 for v in vals if abs(v - target) <= tol), len(vals)
