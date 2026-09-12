"""Shared UI pieces: surfaces with real edges, controls that answer the pointer."""

import tkinter as tk

from .theme import (BG, PANEL, PANEL_2, RAISED, RAISED_HI, EDGE, LINE, TEXT, MUTED,
                    DIM, BRAND, BRAND_HI, TINT, ACCENT, ACCENT_HI, INK_ON_LIGHT,
                    SELECTED, SELECTED_HI)


class UIKit:
    """Widget helpers bound to one root, so scale and type are resolved once."""

    def __init__(self, root, type_):
        self.root = root
        self.t = type_
        self.S = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.tip = None

    # ---- geometry
    def s(self, *v):
        return [x * self.S for x in v]

    def px(self, v):
        return int(v * self.S)

    # ---- type passthrough
    def f(self, size, weight="normal"):
        return self.t.f(size, weight)

    def d(self, size, weight="normal"):
        return self.t.d(size, weight)

    # ---- surfaces
    def panel(self, parent, **kw):
        """A panel is a surface with a lit top edge, not a flat rectangle.

        One pixel of lighter colour along the top reads as a raised slab catching light
        from above, which is what stops the window looking like a stack of dark boxes."""
        wrap = tk.Frame(parent, bg=EDGE)
        inner = tk.Frame(wrap, bg=PANEL, **kw)
        inner.pack(fill="both", expand=True, pady=(1, 0))
        wrap.inner = inner
        return wrap

    def grad(self, canvas, w, h, top, bottom, bands=40, tag="grad"):
        """A shallow vertical wash across a canvas, drawn as a handful of bands.

        The contrast is only a few levels, enough to stop a large dark area reading as
        a flat cut-out and not enough to band visibly."""
        canvas.delete(tag)
        if w <= 1 or h <= 1:
            return
        a = tuple(int(top[i:i + 2], 16) for i in (1, 3, 5))
        b = tuple(int(bottom[i:i + 2], 16) for i in (1, 3, 5))
        step = h / bands
        for i in range(bands):
            f = i / (bands - 1)
            col = "#%02x%02x%02x" % tuple(round(a[c] + (b[c] - a[c]) * f) for c in range(3))
            canvas.create_rectangle(0, i * step, w, (i + 1) * step + 1,
                                    fill=col, width=0, tags=tag)
        canvas.create_line(0, 0, w, 0, fill=EDGE, tags=tag)
        canvas.tag_lower(tag)

    # ---- controls
    def hover(self, widget, rest, hot, children=()):
        targets = (widget,) + tuple(children)

        def paint(colour):
            for t in targets:
                try:
                    t.configure(bg=colour)
                except tk.TclError:
                    pass
        widget.bind("<Enter>", lambda e: paint(hot), add="+")
        widget.bind("<Leave>", lambda e: paint(rest), add="+")

    def button(self, parent, text, cmd, kind="plain", pad=(14, 7), radius=7, bg=None):
        rest, hot, fg = {
            "plain": (RAISED, RAISED_HI, TEXT),
            "brand": (BRAND, BRAND_HI, TEXT),
            "accent": (ACCENT, ACCENT_HI, INK_ON_LIGHT),
        }[kind]
        return RoundButton(parent, self, text, cmd, rest, hot, fg, pad, radius,
                           self.f(10, "semi"), bg)

    def restyle(self, b, rest, hot, fg=TEXT):
        """Re-set a toggle control's resting colour. Works for either a rounded
        button or a plain Label, because both still exist in the app."""
        if isinstance(b, RoundButton):
            b.set_colours(rest, hot, fg)
            return
        b.rest = rest
        b.configure(bg=rest, fg=fg)
        b.bind("<Enter>", lambda e: b.configure(bg=hot))
        b.bind("<Leave>", lambda e: b.configure(bg=b.rest))

    def entry(self, parent, var, width=6, on_change=None, data=True, accent=ACCENT):
        e = tk.Entry(parent, textvariable=var, width=width, bg=BG, fg=TEXT, bd=0,
                     insertbackground=accent, justify="right",
                     font=self.d(10) if data else self.f(10),
                     highlightthickness=1, highlightbackground=LINE, highlightcolor=accent)
        if on_change:
            e.bind("<KeyRelease>", lambda ev: on_change())
        return e

    def heading(self, parent, text, bg=PANEL, colour=BRAND_HI, pady=(14, 1)):
        """A section label with a short mark beside it, so sections are findable
        without reading a word."""
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=pady)
        tk.Frame(row, bg=colour, width=3, height=self.px(11)).pack(side="left", padx=(0, 8))
        tk.Label(row, text=text, bg=bg, fg=TEXT, font=self.f(11, "semi"),
                 anchor="w").pack(side="left")
        return row

    def metric(self, parent, label, bg=BG):
        """A named reading: a quiet condensed caption over a bright value."""
        col = tk.Frame(parent, bg=bg)
        cap = tk.Label(col, text=label.upper(), bg=bg, fg=MUTED, font=self.f(8, "tight"),
                       anchor="e")
        cap.pack(fill="x")
        val = tk.Label(col, text="—", bg=bg, fg=TEXT, font=self.d(11), anchor="e")
        val.pack(fill="x")
        col.value, col.caption = val, cap
        return col

    def field(self, parent, label, bg=PANEL):
        """A labelled control slot for the macro editor: caption above, widget below."""
        col = tk.Frame(parent, bg=bg)
        tk.Label(col, text=label.upper(), bg=bg, fg=DIM, font=self.f(8, "tight"),
                 anchor="w").pack(fill="x")
        body = tk.Frame(col, bg=bg)
        body.pack(fill="x")
        col.body = body
        return col

    def choice(self, parent, options, get, set_, bg=PANEL, width=None):
        """A row of segmented buttons. Better than a dropdown here because every option
        stays visible, which matters when the options are the whole vocabulary of the
        feature and the user is still learning it."""
        row = tk.Frame(parent, bg=bg)
        chips = {}

        def paint():
            cur = get()
            for value, chip in chips.items():
                on = value == cur
                self.restyle(chip, SELECTED if on else RAISED,
                             SELECTED_HI if on else RAISED_HI, TINT if on else MUTED)

        for value, text in options:
            c = RoundButton(row, self, text, None, RAISED, RAISED_HI, MUTED,
                            (9, 5), 6, self.f(9, "semi"), bg)
            c.command = (lambda v=value: (set_(v), paint()))
            c.pack(side="left", padx=(0, 3))
            chips[value] = c
        row.paint = paint
        paint()
        return row

    def switch(self, parent, text, get, set_, bg=PANEL, on_colour=BRAND):
        """A checkbox that looks like the rest of the app rather than like Windows 95."""
        row = tk.Frame(parent, bg=bg, cursor="hand2")
        box = tk.Canvas(row, width=self.px(15), height=self.px(15), bg=bg,
                        highlightthickness=0)
        box.pack(side="left", padx=(0, 7))
        rect = box.create_rectangle(*self.s(1, 1, 14, 14), outline=LINE, fill=PANEL_2,
                                    width=1)
        mark = box.create_line(*self.s(4, 8, 6.5, 11, 11, 4), fill=TEXT,
                               width=2 * self.S, state="hidden", capstyle="round",
                               joinstyle="round")
        lab = tk.Label(row, text=text, bg=bg, fg=MUTED, font=self.f(9), anchor="w")
        lab.pack(side="left")

        def paint():
            on = bool(get())
            box.itemconfigure(rect, fill=on_colour if on else PANEL_2,
                              outline=on_colour if on else LINE)
            box.itemconfigure(mark, state="normal" if on else "hidden")
            lab.configure(fg=TEXT if on else MUTED)

        def toggle(_=None):
            set_(not get())
            paint()
        for w in (row, box, lab):
            w.bind("<Button-1>", toggle)
        row.paint = paint
        paint()
        return row

    # ---- tooltips
    def tooltip(self, widget, text):
        widget.bind("<Enter>", lambda e, t=text: self.show_tip(t, e.x_root, e.y_root),
                    add="+")
        widget.bind("<Leave>", lambda e: self.hide_tip(), add="+")

    def show_tip(self, text, x, y):
        self.hide_tip()
        self.tip = tk.Toplevel(self.root)
        self.tip.wm_overrideredirect(True)
        self.tip.configure(bg=LINE)
        tk.Label(self.tip, text=text, bg=PANEL_2, fg=TEXT, font=self.f(9), justify="left",
                 wraplength=self.px(300), padx=9, pady=6).pack(padx=1, pady=1)
        self.tip.wm_geometry(f"+{int(x) + 14}+{int(y) + 18}")

    def hide_tip(self):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


# ---------------------------------------------------------------- rounded controls
class RoundButton:
    """A button drawn on a canvas so it can actually have rounded corners.

    Tk's Label is a rectangle and always will be, so every control in the app used to
    end in a hard 90-degree corner. This keeps the same small API the rest of the code
    already calls - configure(text=/fg=/cursor=), bind, pack, grid - so it can stand in
    for a Label button without touching call sites."""

    def __init__(self, parent, ui, text, command=None, rest=RAISED, hot=RAISED_HI,
                 fg=TEXT, pad=(14, 7), radius=7, font=None, bg=None):
        self.ui = ui
        self.command = command
        self._text = text
        self._rest, self._hot, self._fg = rest, hot, fg
        self._pad, self._radius = pad, radius
        self._font = font or ui.f(10, "semi")
        self._enabled = True
        try:
            surface = bg or parent.cget("bg")
        except tk.TclError:
            surface = bg or PANEL
        self.canvas = tk.Canvas(parent, highlightthickness=0, bd=0, bg=surface,
                                cursor="hand2")
        self.shape = self.canvas.create_polygon(0, 0, 0, 0, smooth=True,
                                                splinesteps=16, fill=rest, outline="")
        self.label = self.canvas.create_text(0, 0, text=text, fill=fg, font=self._font)
        self._measure()
        for ev, fn in (("<Enter>", self._enter), ("<Leave>", self._leave),
                       ("<Button-1>", self._click)):
            self.canvas.bind(ev, fn)

    # ---- geometry
    def _measure(self):
        from tkinter import font as tkfont
        f = tkfont.Font(font=self._font)
        w = f.measure(self._text) + self.ui.px(self._pad[0]) * 2
        h = f.metrics("linespace") + self.ui.px(self._pad[1]) * 2
        self._w, self._h = w, h
        self.canvas.configure(width=w, height=h)
        self._draw()

    def _draw(self):
        r = self.ui.px(self._radius)
        pts = rounded_points(1, 1, self._w - 1, self._h - 1, r)
        self.canvas.coords(self.shape, *pts)
        self.canvas.coords(self.label, self._w / 2, self._h / 2)

    # ---- behaviour
    def _enter(self, _=None):
        if self._enabled:
            self.canvas.itemconfigure(self.shape, fill=self._hot)

    def _leave(self, _=None):
        self.canvas.itemconfigure(self.shape, fill=self._rest)

    def _click(self, _=None):
        if self._enabled and self.command:
            self.command()

    # ---- Label-compatible surface
    def configure(self, **kw):
        if "text" in kw:
            self._text = kw.pop("text")
            self.canvas.itemconfigure(self.label, text=self._text)
            self._measure()
        if "fg" in kw:
            self._fg = kw.pop("fg")
            self.canvas.itemconfigure(self.label, fill=self._fg)
        if "bg" in kw:
            self._rest = kw.pop("bg")
            self.canvas.itemconfigure(self.shape, fill=self._rest)
        if "cursor" in kw:
            self.canvas.configure(cursor=kw.pop("cursor"))
        if "state" in kw:
            self._enabled = kw.pop("state") != "disabled"
        for k, v in kw.items():
            try:
                self.canvas.configure(**{k: v})
            except tk.TclError:
                pass
    config = configure

    def cget(self, key):
        # dict.get would evaluate the canvas lookup even on a hit, and the canvas has
        # no "text" option, so it has to be an explicit branch.
        mine = {"text": self._text, "bg": self._rest, "fg": self._fg}
        if key in mine:
            return mine[key]
        return self.canvas.cget(key)

    def set_colours(self, rest, hot, fg):
        self._rest, self._hot, self._fg = rest, hot, fg
        self.canvas.itemconfigure(self.shape, fill=rest)
        self.canvas.itemconfigure(self.label, fill=fg)

    def bind(self, *a, **kw):
        return self.canvas.bind(*a, **kw)

    def pack(self, **kw):
        self.canvas.pack(**kw)
        return self

    def grid(self, **kw):
        self.canvas.grid(**kw)
        return self

    def place(self, **kw):
        self.canvas.place(**kw)
        return self

    def pack_forget(self):
        self.canvas.pack_forget()

    def grid_forget(self):
        self.canvas.grid_forget()

    def winfo_ismapped(self):
        return self.canvas.winfo_ismapped()

    def winfo_children(self):
        return []

    def destroy(self):
        self.canvas.destroy()


def rounded_points(x0, y0, x1, y1, r):
    """Corner points dense enough that smooth=True reads as a true radius."""
    import math
    r = max(1, min(r, abs(x1 - x0) / 2, abs(y1 - y0) / 2))
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0),
                       (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(5):
            a = math.radians(a0 + i * 22.5)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


def _attach_key_badge(kit, btn, key):
    """Draw the shortcut letter inside a rounded button as a small keycap.

    The old form buried the hint in the label as "PAUSE  (P)", where the brackets read
    as punctuation and the letter read as part of the word. A keycap is recognisably a
    key, so it is skimmable and never mistaken for the button's name."""
    import tkinter.font as tkfont
    ui = kit
    f = tkfont.Font(font=ui.f(8, "semi"))
    kw = f.measure(key) + ui.px(9)
    kh = f.metrics("linespace") + ui.px(3)
    btn._pad = (btn._pad[0] + (kw + ui.px(5)) / 2 / ui.S, btn._pad[1])
    btn._measure()
    pad_r = ui.px(9)
    x1 = btn._w - pad_r
    x0 = x1 - kw
    y0 = (btn._h - kh) / 2
    btn._badge = (
        btn.canvas.create_polygon(*rounded_points(x0, y0, x1, y0 + kh, ui.px(3)),
                                  smooth=True, splinesteps=8, fill=BG, outline=""),
        btn.canvas.create_text((x0 + x1) / 2, y0 + kh / 2, text=key, fill=MUTED,
                               font=ui.f(8, "semi")))
    # the word shifts left so the cap does not sit on top of it
    btn.canvas.coords(btn.label, (btn._w - kw - ui.px(5)) / 2, btn._h / 2)
    return btn


def _kit_action(self, parent, text, key, cmd, kind="plain", bg=None):
    b = self.button(parent, text, cmd, kind=kind, bg=bg)
    _attach_key_badge(self, b, key)
    self.tooltip(b.canvas, f"{text.title()}  ·  shortcut: {key}")
    return b


UIKit.action = _kit_action
