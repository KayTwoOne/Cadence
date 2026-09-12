"""Palette and type for Cadence.

The colours are pulled off a Phthalo Green pigment chart: a near-black masstone, a
deep emerald glaze, a mint tint and a sage tone. Phthalo is a blue-green, which is
what keeps the dark surfaces reading as cool and deep rather than muddy.

Two colours carry meaning and nothing else competes with them:
    green  - the hardware. Your pads, your presses, what was actually read.
    amber  - your intent. Practice targets, armed macros, anything you set up.
Amber is the complement of the greens, so it stays legible against every surface and
stops the window turning into one monotone wash. Xbox face buttons keep their factory
colours, because those are labels on a physical object rather than app chrome.
"""

# ---------------------------------------------------------------- surfaces
# A ramp from the pigment's Shade through its masstone. The green tint is heavy in
# hue but almost absent in saturation, so it reads as depth, not as colour.
BG = "#070d0b"          # the ground everything sits on
PANEL = "#0e1613"       # surface 1: panels
PANEL_2 = "#141f1a"     # surface 2: rows, wells, insets
RAISED = "#1d2b25"      # surface 3: controls at rest
RAISED_HI = "#27392f"   # surface 3 under the pointer
EDGE = "#2a3d33"        # the lit top edge that lifts a panel off the ground
LINE = "#2b3f36"        # hairline rules and outlines

# ---------------------------------------------------------------- ink
TEXT = "#eef5f1"
MUTED = "#9dbfa8"       # the chart's Tone swatch, which is exactly a muted body colour
DIM = "#7d9a89"        # lifted to clear 4.5:1 on every surface; small captions use it
INK_ON_LIGHT = "#08211a"   # for text sitting on a bright green or amber fill

# ---------------------------------------------------------------- meaning
BRAND = "#00794a"       # the Glaze: fills, selected states
BRAND_HI = "#0eae74"    # phthalo at full strength: hover, live indicator
TINT = "#56c9a3"        # the Tint swatch: values and highlights on dark
SELECTED = "#123a2b"    # a chosen segment: deep green ground under mint text
SELECTED_HI = "#18513a"
ACCENT = "#ffb020"      # the single sharp accent: targets and armed macros
ACCENT_HI = "#ffc866"
MISS = "#e2554f"
WARN = "#ffb020"

# Factory colours of the physical buttons. Not part of the palette, deliberately.
XBOX_A = "#55b83a"
XBOX_B = "#e2322f"
XBOX_X = "#2a8ae0"
XBOX_Y = "#f1b21a"


class Type:
    """Two families, each doing the job it is actually good at.

    Numbers go in Cascadia Mono because its digits are all one width, so a reading
    that changes from 111 to 888 does not shuffle sideways on every press. Chrome goes
    in Bahnschrift, a DIN-derived technical face whose digits are handsome but
    proportional, which is fine for text that never redraws itself.
    """

    def __init__(self, root):
        from tkinter import font as tkfont
        fams = set(tkfont.families(root))

        def pick(*names):
            return next((n for n in names if n in fams), None)

        self.ui = pick("Bahnschrift", "Segoe UI", "DejaVu Sans") or "TkDefaultFont"
        self.thin = pick("Bahnschrift Light", "Segoe UI Light", "Segoe UI") or self.ui
        self.bold = pick("Bahnschrift SemiBold", "Segoe UI Semibold") or self.ui
        self.tight = pick("Bahnschrift Condensed", "Bahnschrift", "Segoe UI") or self.ui
        self.data = pick("Cascadia Mono", "Consolas", "DejaVu Sans Mono") or self.ui
        self.bold_is_real = self.bold != self.ui

    def f(self, size, weight="normal"):
        """Chrome type. 'semi' is the heavy end, 'thin' the light end, 'tight' the
        condensed face used for the small captions that name a value."""
        if weight == "semi":
            return (self.bold, size) if self.bold_is_real else (self.ui, size, "bold")
        if weight == "thin":
            return (self.thin, size)
        if weight == "tight":
            return (self.tight, size)
        return (self.ui, size, weight)

    def d(self, size, weight="normal"):
        """Data type: anything the user reads as a measurement."""
        return (self.data, size) if weight == "normal" else (self.data, size, weight)
