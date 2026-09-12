"""Frameless window: our own title bar, our own resize, rounded corners.

The native Windows caption is a light strip of someone else's design sitting above a
dark app, and it cannot be styled. Replacing it costs three things that have to be
rebuilt by hand - dragging, resizing, and the minimise/maximise/close buttons - plus
one thing that is easy to lose by accident: the taskbar button. A frameless Tk window
defaults to a tool window, which Windows deliberately keeps off the taskbar, so the
extended style is corrected explicitly.

Everything here degrades: if any Win32 call fails the window keeps its native frame
and stays completely usable.
"""

import sys
import ctypes
from ctypes import wintypes
import tkinter as tk

from .theme import (BG, PANEL_2, RAISED_HI, RAISED, EDGE, TEXT, MUTED, DIM, BRAND_HI,
                    MISS)

from .widgets import rounded_points

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SW_MINIMIZE = 6
SW_RESTORE = 9
GRIP = 6                # pixels of window edge that start a resize
CORNER_RADIUS = 10


def _hwnd(root):
    root.update_idletasks()
    return ctypes.windll.user32.GetParent(root.winfo_id())


def keep_on_taskbar(root):
    """A frameless Tk window is a tool window to Windows, and tool windows get no
    taskbar button. Without this the app vanishes from Alt-Tab and the taskbar."""
    if sys.platform != "win32":
        return False
    try:
        u = ctypes.windll.user32
        h = _hwnd(root)
        get = getattr(u, "GetWindowLongPtrW", u.GetWindowLongW)
        setl = getattr(u, "SetWindowLongPtrW", u.SetWindowLongW)
        style = get(h, GWL_EXSTYLE)
        setl(h, GWL_EXSTYLE, (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
        return True
    except Exception:
        return False


def round_corners(root, radius=CORNER_RADIUS):
    """Soften the window's own outline to match the softened controls inside it.

    SetWindowRgn installs a fixed clipping region, so it has to be recomputed every
    time the window changes size. Leaving a stale one behind does not just look wrong:
    Windows clips the window to the old rectangle, and anything outside it is both
    invisible and unclickable until the region is replaced."""
    if sys.platform != "win32":
        return
    try:
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        h = _hwnd(root)
        w, ht = root.winfo_width(), root.winfo_height()
        if w <= 1 or ht <= 1:
            return
        rgn = g.CreateRoundRectRgn(0, 0, w + 1, ht + 1, radius * 2, radius * 2)
        # SetWindowRgn takes ownership of the region on success; deleting it here
        # would leave the window clipped to a freed handle.
        if not u.SetWindowRgn(h, rgn, True):
            g.DeleteObject(rgn)
    except Exception:
        pass


def clear_region(root):
    """Hand the window back to Windows unclipped."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetWindowRgn(_hwnd(root), None, True)
    except Exception:
        pass


def minimise(root):
    if sys.platform != "win32":
        root.iconify()
        return
    try:
        ctypes.windll.user32.ShowWindow(_hwnd(root), SW_MINIMIZE)
    except Exception:
        root.iconify()


def work_area():
    """The desktop minus the taskbar, so 'maximised' does not cover it."""
    if sys.platform != "win32":
        return 0, 0, 1920, 1080
    try:
        r = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
        return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        return 0, 0, 1920, 1080


def ease_out_expo(t):
    """The easing the design system calls for: fast departure, long settle.

    Motion here is not decoration - the window changing size is a big, potentially
    disorienting event, and easing it is what keeps it readable as one object moving
    rather than the layout being replaced."""
    return 1.0 if t >= 1 else 1 - pow(2, -10 * t)


class WindowAnimator:
    """Tweens window geometry. Only ever one tween in flight."""

    def __init__(self, root, ms=260, fps=90):
        self.root = root
        self.ms = ms
        self.step_ms = max(8, int(1000 / fps))
        self.job = None
        self.busy = False

    def stop(self):
        if self.job is not None:
            try:
                self.root.after_cancel(self.job)
            except Exception:
                pass
            self.job = None
        self.busy = False

    def to(self, x, y, w, h, on_done=None):
        import time
        self.stop()
        x0, y0 = self.root.winfo_x(), self.root.winfo_y()
        w0, h0 = self.root.winfo_width(), self.root.winfo_height()
        if (abs(x - x0) + abs(y - y0) + abs(w - w0) + abs(h - h0)) < 3:
            if on_done:
                on_done()
            return
        start = time.perf_counter()
        self.busy = True

        def frame():
            t = (time.perf_counter() - start) * 1000 / self.ms
            k = ease_out_expo(min(1.0, t))
            cx = round(x0 + (x - x0) * k)
            cy = round(y0 + (y - y0) * k)
            cw = round(w0 + (w - w0) * k)
            ch = round(h0 + (h - h0) * k)
            self.root.geometry(f"{cw}x{ch}+{cx}+{cy}")
            if t >= 1:
                self.job = None
                self.busy = False
                round_corners(self.root)
                if on_done:
                    on_done()
            else:
                self.job = self.root.after(self.step_ms, frame)
        frame()


class WindowButton:
    """One caption button: a rounded plate with its glyph drawn as strokes.

    Text glyphs for these vary in weight and baseline between fonts, so a minimise
    that looks centred on one machine sits low on another. Drawing them keeps all
    three optically aligned and lets the plate round off to match the window."""

    W, H, R = 30, 22, 7

    def __init__(self, parent, ui, kind, command, danger=False):
        self.ui = ui
        self.kind = kind
        self.command = command
        self.danger = danger
        self.canvas = tk.Canvas(parent, width=ui.px(self.W), height=ui.px(self.H),
                                bg=PANEL_2, highlightthickness=0, cursor="hand2")
        self.plate = self.canvas.create_polygon(
            *rounded_points(0, 0, ui.px(self.W), ui.px(self.H), ui.px(self.R)),
            smooth=True, splinesteps=10, fill=PANEL_2, outline="")
        self.marks = []
        self.set_kind(kind)
        self.canvas.bind("<Button-1>", lambda e: self.command())
        self.canvas.bind("<Enter>", lambda e: self._hover(True))
        self.canvas.bind("<Leave>", lambda e: self._hover(False))

    def set_kind(self, kind):
        ui, c = self.ui, self.canvas
        for m in self.marks:
            c.delete(m)
        self.marks = []
        self.kind = kind
        cx, cy = ui.px(self.W) / 2, ui.px(self.H) / 2
        w = max(1.0, 1.3 * ui.S)
        r = ui.px(4)
        if kind == "min":
            self.marks.append(c.create_line(cx - r, cy, cx + r, cy, fill=MUTED,
                                            width=w, capstyle="round"))
        elif kind == "max":
            self.marks.append(c.create_rectangle(cx - r, cy - r, cx + r, cy + r,
                                                 outline=MUTED, width=w))
        elif kind == "restore":
            self.marks.append(c.create_rectangle(cx - r, cy - r + ui.px(2),
                                                 cx + r - ui.px(2), cy + r,
                                                 outline=MUTED, width=w))
            self.marks.append(c.create_line(cx - r + ui.px(2), cy - r + ui.px(2),
                                            cx - r + ui.px(2), cy - r,
                                            cx + r, cy - r, cx + r, cy + r - ui.px(2),
                                            fill=MUTED, width=w))
        else:
            self.marks.append(c.create_line(cx - r, cy - r, cx + r, cy + r,
                                            fill=MUTED, width=w, capstyle="round"))
            self.marks.append(c.create_line(cx + r, cy - r, cx - r, cy + r,
                                            fill=MUTED, width=w, capstyle="round"))

    def _hover(self, on):
        fill = (MISS if self.danger else RAISED_HI) if on else PANEL_2
        ink = ("#ffffff" if self.danger else TEXT) if on else MUTED
        self.canvas.itemconfigure(self.plate, fill=fill)
        for m in self.marks:
            if self.canvas.type(m) == "rectangle":
                self.canvas.itemconfigure(m, outline=ink)
            else:
                self.canvas.itemconfigure(m, fill=ink)


class TitleBar:
    """Our caption strip: mark, name, version, window buttons.

    Blur puts its controls on one thin bar with the product name centred, and that
    shape is worth borrowing - it gives the app a face without spending a whole row of
    vertical space on decoration."""

    def __init__(self, parent, app, on_close, on_minimise, on_maximise):
        self.app = app
        self.ui = app.ui
        self.root = app.root
        ui = self.ui
        self.maximised = False
        self._drag = None

        self.frame = tk.Frame(parent, bg=PANEL_2, height=ui.px(34))
        self.frame.pack_propagate(False)

        # left: running indicator and the app mark
        left = tk.Frame(self.frame, bg=PANEL_2)
        left.pack(side="left", padx=(10, 0))
        self.lamp = tk.Canvas(left, width=ui.px(14), height=ui.px(14), bg=PANEL_2,
                              highlightthickness=0)
        self.lamp_id = self.lamp.create_oval(*ui.s(2, 2, 12, 12), fill=RAISED,
                                             outline="")
        self.lamp.pack(side="left", padx=(0, 8))
        ui.tooltip(self.lamp, "Lit while macros are armed")

        # centre: name and version, the way Blur centres its title
        centre = tk.Frame(self.frame, bg=PANEL_2)
        centre.place(relx=0.5, rely=0.5, anchor="center")
        from .version import __version__, APP_NAME
        tk.Label(centre, text=APP_NAME, bg=PANEL_2, fg=TEXT, font=ui.f(11, "semi")
                 ).pack(side="left")
        v = tk.Label(centre, text=f"v{__version__}", bg=PANEL_2, fg=DIM,
                     font=ui.d(8))
        v.pack(side="left", padx=(8, 0), pady=(3, 0))
        ui.tooltip(v, f"{APP_NAME} {__version__}")
        self.version_label = v

        # Hidden until a check finds something. Sitting next to the version number is
        # where someone already looks to find out what they are running.
        self.update_btn = tk.Label(centre, text="", bg=PANEL_2, fg=BRAND_HI,
                                   font=ui.f(9, "semi"), cursor="hand2", padx=8)
        self.update_btn.bind("<Button-1>", lambda e: app.run_update())
        self.update_btn.bind("<Enter>",
                             lambda e: self.update_btn.configure(fg=TEXT))
        self.update_btn.bind("<Leave>",
                             lambda e: self.update_btn.configure(fg=BRAND_HI))

        # right: window buttons, inset and rounded rather than full-height slabs
        right = tk.Frame(self.frame, bg=PANEL_2)
        right.pack(side="right", padx=(0, 7))
        self.buttons = []
        for kind, cmd, danger, tip in (("min", on_minimise, False, "Minimise"),
                                       ("max", on_maximise, False, "Maximise"),
                                       ("close", on_close, True, "Close")):
            b = WindowButton(right, ui, kind, cmd, danger)
            b.canvas.pack(side="left", padx=1)
            ui.tooltip(b.canvas, tip)
            self.buttons.append(b)

        # dragging: the bar itself and any inert label on it
        for w in (self.frame, left, centre, self.lamp):
            self._make_draggable(w)
        for child in centre.winfo_children():
            self._make_draggable(child)

        # a hairline under the bar so it reads as chrome, not as content
        self.rule = tk.Frame(parent, bg=EDGE, height=1)

    def pack(self, **kw):
        self.frame.pack(**kw)
        self.rule.pack(fill="x")

    def _make_draggable(self, w):
        w.bind("<Button-1>", self._press, add="+")
        w.bind("<B1-Motion>", self._move, add="+")
        w.bind("<Double-Button-1>", lambda e: self.app.toggle_maximise(), add="+")

    def _press(self, ev):
        self._drag = (ev.x_root - self.root.winfo_x(), ev.y_root - self.root.winfo_y())

    def _move(self, ev):
        if self._drag is None or self.maximised:
            return
        dx, dy = self._drag
        self.root.geometry(f"+{ev.x_root - dx}+{ev.y_root - dy}")

    def show_update(self, version):
        self.update_btn.configure(text=f"update to {version}")
        self.update_btn.pack(side="left", padx=(10, 0), pady=(2, 0))
        self.ui.tooltip(self.update_btn, f"Cadence {version} is available. "
                                         f"Click to download and install it.")

    def set_update_text(self, text):
        self.update_btn.configure(text=text)

    def set_lamp(self, on):
        self.lamp.itemconfigure(self.lamp_id, fill=BRAND_HI if on else RAISED)

    def set_maximised(self, on):
        self.maximised = on
        self.buttons[1].set_kind("restore" if on else "max")


class ResizeGrips:
    """Eight invisible strips around the window that start a drag-resize.

    A frameless window has no border for Windows to hit-test, so the border has to be
    rebuilt. Keeping them as real widgets rather than a global hook means they only
    ever fire when the pointer is genuinely on the edge."""

    CURSORS = {"n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
               "e": "sb_h_double_arrow", "w": "sb_h_double_arrow",
               "nw": "size_nw_se", "se": "size_nw_se",
               "ne": "size_ne_sw", "sw": "size_ne_sw"}

    def __init__(self, root, app, min_w=900, min_h=600):
        self.root, self.app = root, app
        self.min_w, self.min_h = min_w, min_h
        self.grips = {}
        self.state = None
        self._job = None
        for side in self.CURSORS:
            g = tk.Frame(root, bg=BG, cursor=self.CURSORS[side])
            g.bind("<Button-1>", lambda e, s=side: self._press(e, s))
            g.bind("<B1-Motion>", self._drag)
            self.grips[side] = g
        root.bind("<Configure>", self._queue, add="+")

    def _queue(self, _=None):
        """Repositioning eight frames on every Configure is eight relayouts per frame
        of a drag. Doing it once the drag settles is indistinguishable and far cheaper.

        The clipping region is refreshed here too, because it is tied to the window
        size and a stale one silently cuts off whatever grew outside it."""
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.root.after(50, self._settled)

    def _settled(self):
        self._job = None
        round_corners(self.root)
        self._place()

    def _place(self, _=None):
        if self.app.maximised:
            for g in self.grips.values():
                g.place_forget()
            return
        w, h, k = self.root.winfo_width(), self.root.winfo_height(), GRIP
        spots = {
            "n": (k, 0, w - 2 * k, k), "s": (k, h - k, w - 2 * k, k),
            "w": (0, k, k, h - 2 * k), "e": (w - k, k, k, h - 2 * k),
            "nw": (0, 0, k, k), "ne": (w - k, 0, k, k),
            "sw": (0, h - k, k, k), "se": (w - k, h - k, k, k)}
        for side, (x, y, cw, ch) in spots.items():
            self.grips[side].place(x=x, y=y, width=cw, height=ch)
            self.grips[side].lift()

    def _press(self, ev, side):
        self.state = (side, ev.x_root, ev.y_root, self.root.winfo_x(),
                      self.root.winfo_y(), self.root.winfo_width(),
                      self.root.winfo_height())

    def _drag(self, ev):
        if not self.state:
            return
        side, sx, sy, ox, oy, ow, oh = self.state
        dx, dy = ev.x_root - sx, ev.y_root - sy
        x, y, w, h = ox, oy, ow, oh
        if "e" in side:
            w = max(self.min_w, ow + dx)
        if "s" in side:
            h = max(self.min_h, oh + dy)
        if "w" in side:
            w = max(self.min_w, ow - dx)
            x = ox + (ow - w)
        if "n" in side:
            h = max(self.min_h, oh - dy)
            y = oy + (oh - h)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
