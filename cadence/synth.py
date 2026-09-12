"""Sending mouse and keyboard input to Windows, plus the screen facts macros need.

Everything goes through SendInput, which is the modern path and the one applications
actually listen to. Keyboard output is sent as Unicode rather than as virtual key
codes, so a capital letter is genuinely a capital letter without having to fake a
shift key and hope the timing lands.
"""

import sys
import ctypes
from ctypes import wintypes

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004

MOUSE_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

# Keys with no printable character have to go as virtual key codes instead.
NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "backspace": 0x08, "esc": 0x1B,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}

# Hotkey names offered for the global panic key, mapped to virtual key codes.
PANIC_KEYS = {"F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79,
              "Pause": 0x13, "ScrollLock": 0x91}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


class Synth:
    """All outbound input goes through one object so it can be disabled in one place.

    `live` exists so the whole app can be run and tested without it actually moving
    anything: the counters still tick, so behaviour is verifiable without a macro
    taking over the machine mid-test."""

    def __init__(self, live=True):
        self.live = live and sys.platform == "win32"
        self.sent = 0
        self.log = []            # recent (kind, detail) pairs, for tests and the UI
        self.log_limit = 200
        if sys.platform == "win32":
            self.user32 = ctypes.windll.user32
            self.user32.SendInput.argtypes = [wintypes.UINT,
                                              ctypes.POINTER(INPUT), ctypes.c_int]
            self.user32.SendInput.restype = wintypes.UINT
        else:
            self.user32 = None

    def _record(self, kind, detail):
        self.sent += 1
        self.log.append((kind, detail))
        if len(self.log) > self.log_limit:
            del self.log[:len(self.log) - self.log_limit]

    def _send(self, *inputs):
        if not self.live or not inputs:
            return
        n = len(inputs)
        arr = (INPUT * n)(*inputs)
        self.user32.SendInput(n, arr, ctypes.sizeof(INPUT))

    # ---- mouse
    def mouse(self, button, down):
        flags = MOUSE_FLAGS.get(button)
        if not flags:
            return
        flag = flags[0] if down else flags[1]
        self._record("mouse", f"{button} {'down' if down else 'up'}")
        self._send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, flag, 0, 0)))

    def move_to(self, x, y):
        """Absolute move. SendInput wants 0-65535 across the virtual desktop, and using
        it rather than SetCursorPos keeps the move in the same input stream as the
        click that follows, so nothing can slip between them."""
        self._record("move", f"{x},{y}")
        if not self.live:
            return
        w, h = screen_size()
        nx = int(x * 65535 / max(1, w - 1))
        ny = int(y * 65535 / max(1, h - 1))
        self._send(INPUT(type=INPUT_MOUSE,
                         mi=MOUSEINPUT(nx, ny, 0,
                                       MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, 0)))

    # ---- keyboard
    def key(self, text, down):
        """One key press. A named key goes as a virtual key code; anything else goes as
        the literal character, which is how case is honoured without a shift dance."""
        if not text:
            return
        name = text.strip().lower()
        self._record("key", f"{text} {'down' if down else 'up'}")
        flags = 0 if down else KEYEVENTF_KEYUP
        if name in NAMED_KEYS:
            ki = KEYBDINPUT(NAMED_KEYS[name], 0, flags, 0, 0)
        else:
            ki = KEYBDINPUT(0, ord(text[0]), flags | KEYEVENTF_UNICODE, 0, 0)
        self._send(INPUT(type=INPUT_KEYBOARD, ki=ki))


# ---------------------------------------------------------------- screen facts
def screen_size():
    if sys.platform != "win32":
        return 1920, 1080
    u = ctypes.windll.user32
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def cursor_pos():
    if sys.platform != "win32":
        return 0, 0
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def near_edge(margin, corners_only=False):
    """Is the pointer parked against the side of the screen?

    This is the escape hatch: shove the mouse into a corner and every running macro
    stops. It is the reason a runaway clicker is recoverable without the keyboard."""
    x, y = cursor_pos()
    w, h = screen_size()
    at_x = x <= margin or x >= w - 1 - margin
    at_y = y <= margin or y >= h - 1 - margin
    return (at_x and at_y) if corners_only else (at_x or at_y)
