"""Reading controllers on Linux, where there is no XInput.

The kernel joystick interface exposes each pad as /dev/input/jsN and emits fixed
8-byte events. That is enough to drive everything Cadence does, and it needs no
packages: the struct has been stable for decades.

Two things differ from the Windows path and are handled here rather than leaking out:

  * Buttons arrive as an index, not a bitmask, so the index is mapped onto the same
    names the rest of the app already uses.
  * There is no packet counter. Every event carries a kernel timestamp instead, and a
    counter is synthesised so the report-rate estimator sees what it expects.

Button order follows the Linux gamepad spec that SDL, Steam and the kernel's own
xpad driver all follow, so an Xbox-style pad lands on the right names. Anything
stranger can be corrected from the Controllers tab like any other layout.
"""

import os
import glob
import struct
import threading
from collections import defaultdict

EVENT = struct.Struct("IhBB")        # time (ms), value, type, number
EVENT_SIZE = EVENT.size              # 8
BUTTON, AXIS, INIT = 0x01, 0x02, 0x80

# Index order from the kernel gamepad spec, mapped onto our XInput names.
BUTTON_MAP = {0: "A", 1: "B", 2: "X", 3: "Y", 4: "LB", 5: "RB",
              6: "BACK", 7: "START", 8: "GUIDE", 9: "LS", 10: "RS",
              11: "LEFT", 12: "RIGHT", 13: "UP", 14: "DOWN"}
BIT_FOR = {}          # filled on import from hardware, kept local to avoid a cycle

AXIS_LX, AXIS_LY, AXIS_LT, AXIS_RX, AXIS_RY, AXIS_RT = 0, 1, 2, 3, 4, 5
DPAD_X, DPAD_Y = 6, 7


def _bits():
    global BIT_FOR
    if not BIT_FOR:
        from .hardware import BIT
        BIT_FOR = BIT
    return BIT_FOR


class LinuxJoystickReader:
    """Same shape as XInputReader, so the poller cannot tell the difference.

    Each device gets a thread doing a blocking read, because the joystick interface
    has no way to poll several devices at once without select, and the state those
    threads maintain is what read() returns."""

    def __init__(self):
        self.devices = {}            # slot -> dict of live state
        self.threads = {}
        self.running = True
        self.lock = threading.Lock()
        self.scan()

    # ---- discovery
    def scan(self):
        """Pick up any device node that has appeared since the last look.

        Called on a timer by the poller's scanner thread, so plugging a pad in while
        Cadence is running works the same way it does on Windows."""
        for path in sorted(glob.glob("/dev/input/js*")):
            slot = int(path.rsplit("js", 1)[-1])
            if slot > 3 or slot in self.devices:
                continue
            try:
                fd = os.open(path, os.O_RDONLY)
            except OSError:
                continue
            state = {"fd": fd, "path": path, "buttons": 0, "packet": 0,
                     "axes": defaultdict(int), "name": self._name(slot)}
            with self.lock:
                self.devices[slot] = state
            t = threading.Thread(target=self._pump, args=(slot,), daemon=True)
            self.threads[slot] = t
            t.start()

    @staticmethod
    def _name(slot):
        try:
            with open(f"/sys/class/input/js{slot}/device/name") as fh:
                return fh.read().strip()
        except OSError:
            return "gamepad"

    # ---- per-device reader
    def _pump(self, slot):
        state = self.devices.get(slot)
        if not state:
            return
        bits = _bits()
        while self.running:
            try:
                data = os.read(state["fd"], EVENT_SIZE)
            except OSError:
                break
            if len(data) != EVENT_SIZE:
                break
            _t, value, etype, number = EVENT.unpack(data)
            kind = etype & ~INIT
            if kind == BUTTON:
                name = BUTTON_MAP.get(number)
                if name and name in bits:
                    if value:
                        state["buttons"] |= bits[name]
                    else:
                        state["buttons"] &= ~bits[name]
            elif kind == AXIS:
                state["axes"][number] = value
                # The d-pad usually arrives as two axes rather than buttons.
                if number == DPAD_X:
                    state["buttons"] &= ~(bits["LEFT"] | bits["RIGHT"])
                    if value < -16000:
                        state["buttons"] |= bits["LEFT"]
                    elif value > 16000:
                        state["buttons"] |= bits["RIGHT"]
                elif number == DPAD_Y:
                    state["buttons"] &= ~(bits["UP"] | bits["DOWN"])
                    if value < -16000:
                        state["buttons"] |= bits["UP"]
                    elif value > 16000:
                        state["buttons"] |= bits["DOWN"]
            state["packet"] += 1
        self._drop(slot)

    def _drop(self, slot):
        with self.lock:
            state = self.devices.pop(slot, None)
        if state:
            try:
                os.close(state["fd"])
            except OSError:
                pass

    # ---- the interface the poller uses
    def read(self, slot, buf=None):
        state = self.devices.get(slot)
        if state is None:
            return None
        ax = state["axes"]
        # Triggers rest at -32767 and travel to 32767; XInput wants 0..255.
        def trig(v):
            return max(0, min(255, int((v + 32767) * 255 / 65534)))
        return (state["packet"], state["buttons"],
                trig(ax[AXIS_LT]), trig(ax[AXIS_RT]),
                ax[AXIS_LX], -ax[AXIS_LY], ax[AXIS_RX], -ax[AXIS_RY])

    def describe(self, slot):
        state = self.devices.get(slot)
        if not state:
            return {}
        return {"subtype": state["name"][:32], "wireless": False, "power": "unknown"}

    def close(self):
        self.running = False
        for slot in list(self.devices):
            self._drop(slot)


def available():
    return bool(glob.glob("/dev/input/js*"))
