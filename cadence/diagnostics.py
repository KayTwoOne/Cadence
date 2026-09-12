"""Checks that answer "why did my macro do nothing?" before the user has to ask.

Synthetic input on Windows fails silently more often than it errors. The three common
causes, in the order new users hit them:

  1. UIPI. A process cannot send input to a window owned by a higher integrity level.
     If the game or app runs as administrator and Cadence does not, every click is
     dropped with no error anywhere.
  2. Exclusive full-screen. Some games read the device directly and ignore injected
     input entirely; borderless windowed almost always works.
  3. The panic key already being owned by another application, so the escape hatch the
     user is relying on was never registered.

None of these can be fixed silently, so each one is detected and stated plainly.
"""

import sys
import ctypes
from ctypes import wintypes


def is_elevated():
    """True if Cadence is running as administrator."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def foreground_is_elevated():
    """Whether the window the user is looking at outranks us.

    This is the check that matters: input is blocked per target window, not globally,
    so an unelevated Cadence works fine everywhere except against elevated apps."""
    if sys.platform != "win32":
        return False
    try:
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return False
        # PROCESS_QUERY_LIMITED_INFORMATION. Being refused this is itself the signal:
        # an unelevated process cannot open a more privileged one.
        h = k.OpenProcess(0x1000, False, pid.value)
        if not h:
            return True
        k.CloseHandle(h)
        return False
    except Exception:
        return False


def foreground_is_ours():
    """Whether the window that will receive synthetic input belongs to this process.

    SendInput goes to whatever is focused, not to a window you name. Without this
    check the self-test would happily type its phrase into whatever the user alt-tabbed
    to, which is both confusing and rude."""
    if sys.platform != "win32":
        return True
    try:
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == k.GetCurrentProcessId()
    except Exception:
        return False


def take_foreground(root):
    """Bring our own window forward so the test types where it says it will."""
    if sys.platform != "win32":
        root.lift()
        return
    try:
        root.update_idletasks()
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = u.GetParent(root.winfo_id()) or root.winfo_id()
        u.ShowWindow(hwnd, 9)          # SW_RESTORE
        # Windows refuses SetForegroundWindow from a process that does not already own
        # the foreground. Briefly attaching to the current foreground thread's input
        # queue is the documented way to raise your own window regardless.
        fg = u.GetForegroundWindow()
        tid_fg = u.GetWindowThreadProcessId(fg, None) if fg else 0
        tid_me = k.GetCurrentThreadId()
        attached = bool(tid_fg) and tid_fg != tid_me and             u.AttachThreadInput(tid_me, tid_fg, True)
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        if attached:
            u.AttachThreadInput(tid_me, tid_fg, False)
    except Exception:
        root.lift()


def window_title(hwnd=None):
    if sys.platform != "win32":
        return ""
    try:
        u = ctypes.windll.user32
        hwnd = hwnd or u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(hwnd)
        if not n:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


class OutputSelfTest:
    """Proves end to end that synthetic input reaches a window on this machine.

    A macro that silently does nothing is the worst first experience the app can give,
    and every cause of it is invisible. Typing into a field the user can see removes
    the guesswork: either the characters appear or they do not."""

    PHRASE = "cadence"

    def __init__(self, synth, entry_widget, root):
        self.synth = synth
        self.entry = entry_widget
        self.root = root
        self.index = 0
        self.running = False
        self.aborted = ""
        self.on_update = None

    def start(self, on_update=None):
        self.on_update = on_update
        self.index = 0
        self.running = True
        self.aborted = ""
        self.entry.delete(0, "end")
        take_foreground(self.root)
        self.entry.focus_force()
        self.root.after(260, self._step)

    def _step(self):
        if not self.running:
            return
        if self.index >= len(self.PHRASE):
            self.running = False
            self._finish()
            return
        if not foreground_is_ours():
            # Another window took focus. Stop rather than type into it.
            self.running = False
            self.aborted = "focus moved to another window"
            self._finish()
            return
        ch = self.PHRASE[self.index]
        self.index += 1
        self.synth.key(ch, True)
        self.synth.key(ch, False)
        self.root.after(70, self._step)

    def _finish(self):
        got = self.entry.get()
        ok = (not self.aborted) and got.strip().lower() == self.PHRASE
        if self.on_update:
            self.on_update(ok, self.aborted or got)

    def cancel(self):
        self.running = False


def summarise(synth_live, hotkey_ok, panic_key):
    """One line per condition worth telling the user about, worst first."""
    notes = []
    if not synth_live:
        notes.append(("info", "Output is disabled for this run - macros will count "
                              "but send nothing."))
    if not hotkey_ok:
        notes.append(("warn", f"The {panic_key} panic key is not registered, probably "
                              f"because another app owns it. Pick a different key."))
    if is_elevated():
        notes.append(("info", "Running as administrator, so input reaches elevated "
                              "windows too."))
    else:
        notes.append(("info", "Not running as administrator. Input works everywhere "
                              "except apps that run elevated - restart Cadence as "
                              "admin if a game ignores it."))
    return notes
