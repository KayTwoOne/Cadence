"""Drawing a controller that looks like the controller you are actually holding.

Two silhouettes cover the field: the offset-stick body shared by Xbox and Switch Pro
pads, and the symmetric-stick body of a DualShock. Within each, the face glyphs,
shoulder names, centre buttons and touchpad come from the scheme.

The outline is built from a half profile that is then mirrored, so the body is exactly
symmetrical and the grips are real grips rather than a rounded rectangle. Tk's spline
pulls a curve inside its control points, which is why the profile carries enough
points to hold the shape instead of relying on smoothing to invent it.
"""

import math

from .theme import BG, PANEL, PANEL_2, RAISED, LINE, EDGE, TEXT, MUTED, DIM, TINT

# The shell needs to separate from the panel behind it, so it gets its own pair of
# values rather than reusing a surface token that happens to sit at the same level.
SHELL = "#1a2620"
SHELL_EDGE = "#3d564a"

W_BODY = 2.0        # the shell
W_PART = 1.4        # buttons, sticks, d-pad
W_FINE = 0.9        # inner detail and highlights

CANVAS_W, CANVAS_H = 440, 252
MID = 220           # the mirror line


def rounded_points(x0, y0, x1, y1, r):
    r = max(1, min(r, abs(x1 - x0) / 2, abs(y1 - y0) / 2))
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0),
                       (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(6):
            a = math.radians(a0 + i * 18)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


def round_rect(c, x0, y0, x1, y1, r, **kw):
    return c.create_polygon(*rounded_points(x0, y0, x1, y1, r), smooth=True, **kw)


def ink_for(bg):
    """Black or white on a lit button, whichever is actually readable.

    One fixed ink colour leaves some buttons - a red Circle, say - with a glyph that
    barely separates from its own background."""
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))

    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#0a1410" if lum > 0.32 else "#ffffff"


# Right half of the shell, top centre round to bottom centre. Mirrored for the left.
# Grips are the wide sweep from x~300 outward and down; the waist is the climb back in.
HALF_OFFSET = [(220, 44), (288, 45), (324, 51), (350, 64), (366, 86), (374, 112),
               (372, 142), (363, 174), (346, 202), (322, 216), (300, 211),
               (286, 192), (273, 172), (256, 162), (234, 159), (220, 159)]

HALF_SYMMETRIC = [(220, 48), (286, 49), (322, 55), (348, 68), (363, 90), (370, 116),
                  (368, 146), (358, 176), (341, 200), (318, 212), (297, 206),
                  (284, 188), (272, 170), (256, 160), (234, 157), (220, 157)]


def mirror(half):
    pts = list(half)
    for x, y in reversed(half[1:-1]):
        pts.append((2 * MID - x, y))
    return pts


def spline_through(pts):
    """Flatten a point list so Tk's spline passes through every point.

    Tk smooths with a quadratic B-spline, which normally pulls the curve well inside
    its control polygon - that is what flattened the shell's top edge and let the
    buttons spill outside it. Repeating a control point forces the curve onto it, so
    the profile is followed exactly while the joins stay rounded."""
    flat = []
    for x, y in pts:
        flat += [x, y, x, y]
    return flat


class PadArt:
    """Draws one controller and keeps the item ids needed to light it up live."""

    def __init__(self, canvas, ui, scheme):
        self.c = canvas
        self.ui = ui
        self.scheme = scheme
        self.items = {}       # key -> (shape id, glyph id, lit colour, resting colour)
        self.triggers = {}
        self.sticks = {}
        self.cache = {}
        self.build()

    def s(self, *v):
        return self.ui.s(*v)

    # ---------------------------------------------------------------- build
    def build(self):
        self.c.delete("pad")
        self.items, self.triggers, self.sticks, self.cache = {}, {}, {}, {}
        sym = self.scheme.sticks == "symmetric"
        self.body(sym)
        self.shoulders()
        if sym:
            # DualShock: d-pad and faces high and wide apart, touchpad between them,
            # both sticks low and level.
            self.dpad(128, 108)
            self.faces(312, 108)
            self.touchpad(MID, 94)
            self.stick("LS", 172, 168)
            self.stick("RS", 268, 168)
            self.centre_pair(166, 72, 274, 72, side=True)
            self.guide(MID, 142, 8)
        else:
            # Xbox / Switch Pro: left stick high-left, d-pad low-left, faces high-right,
            # right stick low-right.
            self.stick("LS", 128, 104)
            self.dpad(170, 164)
            self.faces(312, 104)
            self.stick("RS", 258, 164)
            self.centre_pair(194, 96, 246, 96)
            self.guide(MID, 64, 10)

    def body(self, sym):
        """The shell, plus a highlight along the top where light would catch it."""
        c, s = self.c, self.s
        pts = mirror(HALF_SYMMETRIC if sym else HALF_OFFSET)
        flat = spline_through(pts)
        c.create_polygon(*s(*flat), smooth=True, splinesteps=14, fill=SHELL,
                         outline=SHELL_EDGE, width=W_BODY * self.ui.S, tags="pad")
        y = 54 if not sym else 58
        c.create_line(*s(128, y + 4, MID, y, 312, y + 4), smooth=True, fill=SHELL_EDGE,
                      width=W_FINE * self.ui.S, capstyle="round", tags="pad")

    def shoulders(self):
        """Triggers read as meters because they are analogue; bumpers are plain caps.

        Both sit across the top edge of the shell so they look mounted on it rather
        than floating above it."""
        c, s, sch = self.c, self.s, self.scheme
        for key, x0, x1 in (("LT", 64, 170), ("RT", 270, 376)):
            round_rect(c, *s(x0, 6, x1, 26), self.ui.S * 9, fill=BG, outline=LINE,
                       width=W_FINE * self.ui.S, tags="pad")
            fill = c.create_rectangle(*s(x0 + 3, 9, x0 + 3, 23), fill=TINT, width=0,
                                      tags="pad")
            c.create_text(*s((x0 + x1) / 2, 16), text=sch.label(key), fill=TEXT,
                          font=self.ui.f(9, "semi"), tags="pad")
            self.triggers[key] = (fill, x0, x1)
        for key, x0, x1 in (("LB", 78, 184), ("RB", 256, 362)):
            iid = round_rect(c, *s(x0, 33, x1, 57), self.ui.S * 10, fill=BG,
                             outline=LINE, width=W_PART * self.ui.S, tags="pad")
            tid = c.create_text(*s((x0 + x1) / 2, 44), text=sch.label(key), fill=TEXT,
                                font=self.ui.f(9, "semi"), tags="pad")
            self.items[key] = (iid, tid, TEXT, BG)

    def faces(self, cx, cy):
        """Four buttons in a diamond, sized and spaced like the real cluster."""
        c, s, sch = self.c, self.s, self.scheme
        r, gap = 14, 29
        for key, (x, y) in {"Y": (cx, cy - gap), "A": (cx, cy + gap),
                            "X": (cx - gap, cy), "B": (cx + gap, cy)}.items():
            col = sch.faces[key]
            iid = c.create_oval(*s(x - r, y - r, x + r, y + r), fill=BG, outline=LINE,
                                width=W_PART * self.ui.S, tags="pad")
            gid = (self.ps_glyph(key, x, y, col) if sch.glyphs == "symbol"
                   else c.create_text(*s(x, y), text=sch.label(key), fill=col,
                                      font=self.ui.f(12, "semi"), tags="pad"))
            self.items[key] = (iid, gid, col, BG)

    def ps_glyph(self, key, x, y, col):
        """PlayStation marks drawn as shapes. The text glyphs live in fonts that may
        not be installed, and a missing-glyph box on the face of the pad would be the
        most obviously wrong thing the app could show."""
        c, s, S = self.c, self.s, self.ui.S
        w = 1.8 * S
        if key == "Y":
            return c.create_polygon(*s(x, y - 8, x + 7.5, y + 5.5, x - 7.5, y + 5.5),
                                    fill="", outline=col, width=w, joinstyle="round",
                                    tags="pad")
        if key == "A":
            return c.create_line(*s(x - 6, y - 6, x + 6, y + 6, x, y, x + 6, y - 6,
                                    x - 6, y + 6), fill=col, width=w, capstyle="round",
                                 tags="pad")
        if key == "B":
            return c.create_oval(*s(x - 7, y - 7, x + 7, y + 7), outline=col, fill="",
                                 width=w, tags="pad")
        return round_rect(c, *s(x - 6.5, y - 6.5, x + 6.5, y + 6.5), 1.6 * S,
                          fill="", outline=col, width=w, tags="pad")

    def dpad(self, cx, cy):
        """One moulded cross, with each arm lighting inside the outline rather than
        as a tile sitting on top of it."""
        c, s, S = self.c, self.s, self.ui.S
        a, b = 9, 24
        pts = (cx - a, cy - b, cx + a, cy - b, cx + a, cy - a, cx + b, cy - a,
               cx + b, cy + a, cx + a, cy + a, cx + a, cy + b, cx - a, cy + b,
               cx - a, cy + a, cx - b, cy + a, cx - b, cy - a, cx - a, cy - a)
        c.create_polygon(*s(*pts), fill=BG, outline=LINE, width=W_PART * S,
                         joinstyle="round", tags="pad")
        k = 3
        for key, box in {"UP": (cx - a + k, cy - b + k, cx + a - k, cy - a + k),
                         "DOWN": (cx - a + k, cy + a - k, cx + a - k, cy + b - k),
                         "LEFT": (cx - b + k, cy - a + k, cx - a + k, cy + a - k),
                         "RIGHT": (cx + a - k, cy - a + k, cx + b - k, cy + a - k)}.items():
            iid = round_rect(c, *s(*box), 2 * S, fill=BG, outline="", tags="pad")
            self.items[key] = (iid, None, MUTED, BG)

    def stick(self, key, cx, cy):
        c, s, S = self.c, self.s, self.ui.S
        ring, cap = 29, 14
        c.create_oval(*s(cx - ring, cy - ring, cx + ring, cy + ring), fill=BG,
                      outline=LINE, width=W_PART * S, tags="pad")
        c.create_oval(*s(cx - ring + 5, cy - ring + 5, cx + ring - 5, cy + ring - 5),
                      outline=EDGE, width=W_FINE * S, tags="pad")
        d = c.create_oval(*s(cx - cap, cy - cap, cx + cap, cy + cap), fill=RAISED,
                          outline=MUTED, width=W_PART * S, tags="pad")
        self.items[key] = (d, None, TINT, RAISED)
        self.sticks[key] = (cx, cy, ring - cap - 2, cap, d)

    def centre_pair(self, lx, ly, rx, ry, side=False):
        """Small centre buttons with their names next to them.

        On a DualShock these flank the touchpad, so the name goes outboard - putting it
        above would land on the bumpers and below would land on the pad surface."""
        c, s, sch = self.c, self.s, self.scheme
        for key, x, y, name, out in (("BACK", lx, ly, sch.centre[0], -1),
                                     ("START", rx, ry, sch.centre[1], 1)):
            iid = c.create_oval(*s(x - 7, y - 7, x + 7, y + 7), fill=BG, outline=LINE,
                                width=W_FINE * self.ui.S, tags="pad")
            if side:
                c.create_text(*s(x + out * 12, y), text=name, fill=MUTED,
                              anchor="w" if out > 0 else "e",
                              font=self.ui.f(9, "tight"), tags="pad")
            else:
                c.create_text(*s(x, y + 18), text=name, fill=MUTED,
                              font=self.ui.f(9, "tight"), tags="pad")
            self.items[key] = (iid, None, MUTED, BG)

    def touchpad(self, cx, cy):
        round_rect(self.c, *self.s(cx - 44, cy - 19, cx + 44, cy + 19),
                   self.ui.S * 6, fill=BG, outline=LINE,
                   width=W_FINE * self.ui.S, tags="pad")

    def guide(self, cx, cy, r):
        self.guide_id = self.c.create_oval(*self.s(cx - r, cy - r, cx + r, cy + r),
                                           fill=DIM, outline=LINE,
                                           width=W_FINE * self.ui.S, tags="pad")

    # ---------------------------------------------------------------- live state
    def update(self, latest, connected):
        from .hardware import BIT
        c = self.c
        mask, lt, rt, lx, ly, rx, ry = latest if latest else (0, 0, 0, 0, 0, 0, 0)
        if self.cache.get("guide") != connected:
            self.cache["guide"] = connected
            c.itemconfigure(self.guide_id, fill=TINT if connected else DIM)
        symbols = self.scheme.glyphs == "symbol"
        for key, (iid, gid, col, rest) in self.items.items():
            on = bool(mask & BIT[key])
            if self.cache.get(key) == on:
                continue
            self.cache[key] = on
            c.itemconfigure(iid, fill=col if on else rest)
            if gid is None:
                continue
            lit = ink_for(col)
            if symbols and key in ("A", "B", "X", "Y"):
                # outline shapes carry their colour on the stroke, the cross on fill
                if key == "A":
                    c.itemconfigure(gid, fill=lit if on else col)
                else:
                    c.itemconfigure(gid, outline=lit if on else col)
            else:
                c.itemconfigure(gid, fill=lit if on else col)
        for key, (fid, x0, x1) in self.triggers.items():
            val = lt if key == "LT" else rt
            span = (x1 - x0 - 6) * val / 255
            if key == "LT":
                c.coords(fid, *self.s(x0 + 3, 9, x0 + 3 + span, 23))
            else:
                c.coords(fid, *self.s(x1 - 3 - span, 9, x1 - 3, 23))
        for key, (vx, vy) in (("LS", (lx, ly)), ("RS", (rx, ry))):
            if key not in self.sticks:
                continue
            cx, cy, travel, cap, d = self.sticks[key]
            px = cx + travel * max(-1, vx / 32767)
            py = cy - travel * max(-1, vy / 32767)
            c.coords(d, *self.s(px - cap, py - cap, px + cap, py + cap))
