"""Working out what kind of controller is plugged in, and what its buttons are called.

XInput deliberately hides the device behind one standard gamepad shape: whatever you
plug in, the bottom face button arrives as "A". That is useful for reading input and
useless for labelling it, because on a PlayStation pad that button is Cross and on a
Nintendo pad it is B.

So the brand is recovered separately, through RawInput, which does report the USB
vendor and product id. Two honest limits come with that:

  * XInput gives no way to tie a slot number back to a USB device. With one pad
    attached the mapping is unambiguous; with several it is a guess.
  * A pad running through DS4Windows, Steam Input or any other remapper presents as a
    virtual Microsoft pad, so the vendor id really is Microsoft's.

Both of those are why the scheme can always be set by hand, and why auto-detection
reports how confident it is instead of just asserting an answer.
"""

import sys
import ctypes
from ctypes import wintypes

# XInput key -> what that physical button is called on each brand of pad.
XINPUT_FACE = ("A", "B", "X", "Y")

# Vendor ids that are safe to name. Anything absent stays "unknown" on purpose:
# a wrong label is worse than an honest prompt.
VENDORS = {
    0x045E: ("Microsoft", "xbox", "certain"),
    0x054C: ("Sony", "playstation", "certain"),
    0x057E: ("Nintendo", "nintendo", "certain"),
    0x28DE: ("Valve", "xbox", "certain"),
    0x2DC8: ("8BitDo", "xbox", "likely"),
    0x0F0D: ("HORI", "xbox", "likely"),
    0x24C6: ("PowerA", "xbox", "likely"),
    0x0E6F: ("PDP", "xbox", "likely"),
    0x1532: ("Razer", "xbox", "likely"),
    0x046D: ("Logitech", "xbox", "likely"),
    0x20D6: ("BDA / PowerA", "xbox", "likely"),
    0x0079: ("DragonRise", "generic", "likely"),
    0x2563: ("ShanWan", "generic", "likely"),
}


class Scheme:
    """Everything that changes between one brand of pad and another.

    Only the names and the artwork change. The bits underneath are XInput's, identical
    for every device, which is why a scheme can be swapped at any time with no effect
    on what was recorded."""

    def __init__(self, key, name, labels, faces, glyphs, sticks, centre, note=""):
        self.key = key
        self.name = name
        self.labels = labels        # xinput key -> display label
        self.faces = faces          # A/B/X/Y -> colour
        self.glyphs = glyphs        # "letter" or "symbol"
        self.sticks = sticks        # "offset" (Xbox/Switch) or "symmetric" (PlayStation)
        self.centre = centre        # (left button name, right button name)
        self.note = note

    def label(self, key):
        return self.labels.get(key, key)


_DPAD = {"UP": "D↑", "DOWN": "D↓", "LEFT": "D←", "RIGHT": "D→"}
_STICKS = {"LS": "LS", "RS": "RS"}

# Xbox face colours are the real ones moulded into the pad.
XBOX = Scheme(
    "xbox", "Xbox",
    {**_DPAD, **_STICKS, "A": "A", "B": "B", "X": "X", "Y": "Y",
     "LB": "LB", "RB": "RB", "LT": "LT", "RT": "RT",
     "BACK": "View", "START": "Menu"},
    {"A": "#55b83a", "B": "#e2322f", "X": "#2a8ae0", "Y": "#f1b21a"},
    "letter", "offset", ("View", "Menu"))

# PlayStation swaps nothing positionally, but every name and glyph differs.
PLAYSTATION = Scheme(
    "playstation", "PlayStation",
    {**_DPAD, "LS": "L3", "RS": "R3",
     "A": "Cross", "B": "Circle", "X": "Square", "Y": "Triangle",
     "LB": "L1", "RB": "R1", "LT": "L2", "RT": "R2",
     "BACK": "Create", "START": "Options"},
    {"A": "#7b8cde", "B": "#e2555f", "X": "#d56ab0", "Y": "#4fc3a1"},
    "symbol", "symmetric", ("Create", "Options"))

# Nintendo mirrors both face pairs, which is the single most common source of a
# mislabelled prompt when a Switch pad is used on a PC.
NINTENDO = Scheme(
    "nintendo", "Nintendo",
    {**_DPAD, **_STICKS,
     "A": "B", "B": "A", "X": "Y", "Y": "X",
     "LB": "L", "RB": "R", "LT": "ZL", "RT": "ZR",
     "BACK": "−", "START": "+"},
    {"A": "#d8dde0", "B": "#d8dde0", "X": "#d8dde0", "Y": "#d8dde0"},
    "letter", "offset", ("Minus", "Plus"),
    "A/B and X/Y sit opposite to an Xbox pad")

GENERIC = Scheme(
    "generic", "Generic",
    {**_DPAD, **_STICKS,
     "A": "1", "B": "2", "X": "3", "Y": "4",
     "LB": "L1", "RB": "R1", "LT": "L2", "RT": "R2",
     "BACK": "Select", "START": "Start"},
    {"A": "#9dbfa8", "B": "#9dbfa8", "X": "#9dbfa8", "Y": "#9dbfa8"},
    "letter", "offset", ("Select", "Start"))

SCHEMES = {s.key: s for s in (XBOX, PLAYSTATION, NINTENDO, GENERIC)}
SCHEME_ORDER = ["xbox", "playstation", "nintendo", "generic"]


# ---------------------------------------------------------------- RawInput lookup
class _RIDL(ctypes.Structure):
    _fields_ = [("hDevice", wintypes.HANDLE), ("dwType", wintypes.DWORD)]


class _HID(ctypes.Structure):
    _fields_ = [("dwVendorId", wintypes.DWORD), ("dwProductId", wintypes.DWORD),
                ("dwVersionNumber", wintypes.DWORD), ("usUsagePage", wintypes.USHORT),
                ("usUsage", wintypes.USHORT)]


class _MOUSE(ctypes.Structure):
    _fields_ = [("dwId", wintypes.DWORD), ("dwNumberOfButtons", wintypes.DWORD),
                ("dwSampleRate", wintypes.DWORD), ("fHasHorizontalWheel", wintypes.BOOL)]


class _KBD(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSubType", wintypes.DWORD),
                ("dwKeyboardMode", wintypes.DWORD),
                ("dwNumberOfFunctionKeys", wintypes.DWORD),
                ("dwNumberOfIndicators", wintypes.DWORD),
                ("dwNumberOfKeysTotal", wintypes.DWORD)]


class _RIDU(ctypes.Union):
    _fields_ = [("mouse", _MOUSE), ("keyboard", _KBD), ("hid", _HID)]


class _RID(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("cbSize", wintypes.DWORD), ("dwType", wintypes.DWORD), ("u", _RIDU)]


def enumerate_xinput_devices():
    """Every HID gamepad Windows also exposes through XInput.

    The "IG_" marker in the device path is how Windows itself distinguishes an
    XInput-capable device, and it is the only reliable way to filter out the dozen
    unrelated HIDs on a typical machine."""
    if sys.platform != "win32":
        return []
    try:
        u = ctypes.windll.user32
        n = wintypes.UINT(0)
        if u.GetRawInputDeviceList(None, ctypes.byref(n), ctypes.sizeof(_RIDL)) == -1:
            return []
        arr = (_RIDL * max(1, n.value))()
        if u.GetRawInputDeviceList(arr, ctypes.byref(n), ctypes.sizeof(_RIDL)) == -1:
            return []
        found = []
        for d in list(arr)[:n.value]:
            if d.dwType != 2:                     # RIM_TYPEHID
                continue
            size = wintypes.UINT(0)
            u.GetRawInputDeviceInfoW(d.hDevice, 0x20000007, None, ctypes.byref(size))
            if not size.value:
                continue
            buf = ctypes.create_unicode_buffer(size.value)
            u.GetRawInputDeviceInfoW(d.hDevice, 0x20000007, buf, ctypes.byref(size))
            info = _RID()
            info.cbSize = ctypes.sizeof(_RID)
            cb = wintypes.UINT(ctypes.sizeof(_RID))
            if u.GetRawInputDeviceInfoW(d.hDevice, 0x2000000b,
                                        ctypes.byref(info), ctypes.byref(cb)) == -1:
                continue
            h = info.hid
            if h.usUsagePage != 0x01 or h.usUsage not in (0x04, 0x05):
                continue
            if "IG_" not in buf.value:
                continue
            found.append({"vid": h.dwVendorId, "pid": h.dwProductId,
                          "path": buf.value})
        return found
    except Exception:
        return []


def identify(devices, connected_count):
    """Turn a device list into a scheme guess plus an honest confidence.

    Returns (scheme_key, vendor_name, confidence, detail). Confidence is one of
    'certain', 'likely', 'ambiguous' or 'unknown', and only 'certain' should ever be
    applied without telling the user what happened."""
    if not devices:
        return None, None, "unknown", "no XInput device visible to RawInput"
    if connected_count > 1 and len(devices) > 1:
        # XInput exposes no way to tie a slot to a USB device, so with several pads
        # attached any mapping would be a guess dressed up as a fact.
        return (None, None, "ambiguous",
                f"{len(devices)} XInput devices attached - Windows does not say which "
                f"slot is which, so pick the scheme yourself")
    dev = devices[0]
    vid, pid = dev["vid"], dev["pid"]
    hit = VENDORS.get(vid)
    if not hit:
        return (None, None, "unknown",
                f"VID 0x{vid:04X} PID 0x{pid:04X} is not a vendor Cadence recognises")
    vendor, scheme, confidence = hit
    detail = f"{vendor} (VID 0x{vid:04X} PID 0x{pid:04X})"
    if vid == 0x045E:
        detail += " - note that remappers such as DS4Windows and Steam Input also " \
                  "present as Microsoft"
    return scheme, vendor, confidence, detail


class SchemeResolver:
    """Holds the detected scheme per slot and whatever the user has overridden."""

    def __init__(self):
        self.detected = {}      # slot -> (scheme_key, vendor, confidence, detail)
        self.override = {}      # slot -> scheme_key chosen by hand
        self.scanned = False

    def scan(self, connected):
        devices = enumerate_xinput_devices()
        for slot in connected:
            self.detected[slot] = identify(devices, len(connected))
        self.scanned = True
        return devices

    def scheme_key(self, slot):
        if slot in self.override:
            return self.override[slot]
        got = self.detected.get(slot)
        if got and got[0] and got[2] in ("certain", "likely"):
            return got[0]
        return "xbox"           # the XInput default, and what the bits literally are

    def scheme(self, slot):
        return SCHEMES[self.scheme_key(slot)]

    def is_guess(self, slot):
        """True when the user has not chosen and detection was not confident."""
        if slot in self.override:
            return False
        got = self.detected.get(slot)
        return not (got and got[0] and got[2] == "certain")

    def explain(self, slot):
        if slot in self.override:
            return f"set by you: {SCHEMES[self.override[slot]].name}"
        got = self.detected.get(slot)
        if not got:
            return "not checked yet"
        key, vendor, confidence, detail = got
        if confidence == "certain":
            return f"detected: {detail}"
        if confidence == "likely":
            return f"probably {vendor} - {detail}"
        return detail

    def set_override(self, slot, key):
        if key in SCHEMES:
            self.override[slot] = key
