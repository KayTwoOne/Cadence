"""Generates the Cadence mark, icon set and repo banner.

Everything is drawn from one glyph so the icon and the banner can never drift apart.
The glyph is four bars of different heights with round caps, read as a level meter or
a bar of music depending on which you saw first. Stroke-only, one weight, no fill, in
the spirit of the M3 Expressive marks on the other repos.

Run:  python assets/make_brand.py
"""

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = HERE
SS = 4                      # supersample factor, everything is drawn big then resized

INK = (238, 245, 241)
MINT = (86, 201, 163)
PHTHALO = (14, 174, 116)
DEEP = (0, 121, 74)
BG_TOP = (10, 20, 17)
BG_BOTTOM = (5, 11, 9)
SAGE = (157, 191, 168)
DIM = (125, 154, 137)

# Bar heights as a fraction of the glyph box, left to right. Uneven on purpose: an
# even set reads as a logo for a battery, this reads as something being measured.
BARS = (0.42, 0.86, 0.62, 0.30)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vignette_bg(w, h, top=BG_TOP, bottom=BG_BOTTOM, glow=None):
    """Dark ground with a vertical fade and an optional off-centre glow."""
    img = Image.new("RGB", (w, h), bottom)
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / max(1, h - 1)))
    if glow:
        gx, gy, gr, gcol, gstrength = glow
        layer = Image.new("RGB", (w, h), (0, 0, 0))
        gd = ImageDraw.Draw(layer)
        steps = 60
        for i in range(steps, 0, -1):
            t = i / steps
            r = gr * t
            gd.ellipse([gx - r, gy - r, gx + r, gy + r],
                       fill=tuple(round(c * (1 - t) * gstrength) for c in gcol))
        layer = layer.filter(ImageFilter.GaussianBlur(gr * 0.18))
        img = Image.blend(img, Image.blend(img, layer, 0.0), 0.0)
        img = Image.fromarray(
            __import__("numpy").clip(
                __import__("numpy").asarray(img, dtype=int)
                + __import__("numpy").asarray(layer, dtype=int), 0, 255).astype("uint8")
        ) if "numpy" in sys.modules else _add(img, layer)
    return img


def _add(base, layer):
    """Additive blend without numpy, so the script has no extra dependency."""
    out = base.copy()
    bp, lp, op = base.load(), layer.load(), out.load()
    w, h = base.size
    for y in range(h):
        for x in range(w):
            b, l = bp[x, y], lp[x, y]
            op[x, y] = (min(255, b[0] + l[0]), min(255, b[1] + l[1]),
                        min(255, b[2] + l[2]))
    return out


def draw_glyph(d, cx, cy, size, colour, weight=0.16, gap=0.085):
    """Four round-capped bars centred on (cx, cy) inside a box `size` across."""
    w = size * weight
    step = size * (weight + gap)
    total = step * (len(BARS) - 1)
    x0 = cx - total / 2
    for i, frac in enumerate(BARS):
        x = x0 + i * step
        half = size * frac / 2
        d.rounded_rectangle([x - w / 2, cy - half, x + w / 2, cy + half],
                            radius=w / 2, fill=colour)


def draw_ring(d, cx, cy, r, colour, weight):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=colour, width=round(weight))


# ---------------------------------------------------------------- icon
def build_icon(px=1024):
    """App icon, drawn for the size it will be shown at.

    Shrinking one master works down to about 32px and then stops: the ring and the
    bars close up on each other and the mark turns into a smudge. Below that the ring
    is dropped and the bars drawn heavier, which keeps it readable in a taskbar and an
    alt-tab strip, where it matters most."""
    n = px * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = n / 2
    if px >= 32:
        draw_ring(d, cx, cy, n * 0.435, MINT + (255,), n * 0.075)
        draw_glyph(d, cx, cy, n * 0.56, MINT + (255,), weight=0.155, gap=0.085)
    else:
        draw_glyph(d, cx, cy, n * 0.94, MINT + (255,), weight=0.2, gap=0.095)
    return img.resize((px, px), Image.LANCZOS)


def build_icon_solid(px=1024):
    """Filled variant for places that put the icon on a light ground."""
    n = px * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, n, n], radius=n * 0.22, fill=(9, 18, 15, 255))
    draw_glyph(d, n / 2, n / 2, n * 0.56, MINT + (255,))
    return img.resize((px, px), Image.LANCZOS)


# ---------------------------------------------------------------- type
def load_font(names, size):
    for name in names:
        for path in (fr"C:\Windows\Fonts\{name}", f"/usr/share/fonts/truetype/{name}"):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


BOLD = ["bahnschrift.ttf", "seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"]
REG = ["bahnschrift.ttf", "segoeui.ttf", "arial.ttf"]
MONO = ["CascadiaMono.ttf", "consola.ttf", "cour.ttf"]


def track(d, xy, text, font, fill, spacing=0):
    """Draw text with letter spacing, which PIL does not do on its own."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + spacing
    return x


# ---------------------------------------------------------------- banner
def build_banner(w=1280, h=640, scale=2):
    """Repo banner: eyebrow, name, one line of what it does, the URL, glyph on the right.

    Same skeleton as the other repo banners - text stack left, single oversized mark
    right, everything on a dark ground with one accent colour doing all the work."""
    W, H = w * scale, h * scale
    img = vignette_bg(W, H, BG_TOP, BG_BOTTOM,
                      glow=(W * 0.74, H * 0.5, H * 0.62, (10, 92, 62), 0.55))
    d = ImageDraw.Draw(img, "RGBA")

    # faint concentric arcs behind the mark, echoing the ring in the icon
    gx, gy = W * 0.745, H * 0.5
    for i, r in enumerate((H * 0.40, H * 0.50, H * 0.60)):
        d.ellipse([gx - r, gy - r, gx + r, gy + r],
                  outline=(20, 70, 52, 130 - i * 30), width=max(1, round(scale * 1.2)))

    # the mark
    draw_glyph(d, gx, gy, H * 0.50, MINT + (255,), weight=0.15, gap=0.09)
    draw_ring(d, gx, gy, H * 0.335, MINT + (90,), scale * 2.5)

    left = W * 0.085
    f_eyebrow = load_font(BOLD, round(15 * scale))
    f_name = load_font(BOLD, round(76 * scale))
    f_sub = load_font(REG, round(24 * scale))
    f_url = load_font(MONO, round(15 * scale))

    y = H * 0.27
    track(d, (left, y), "CONTROLLER UTILITY", f_eyebrow, MINT, spacing=3.2 * scale)

    y += 36 * scale
    d.text((left, y), "Cadence", font=f_name, fill=INK)
    # the full stop in accent, the way "At a glance." does it
    nw = d.textlength("Cadence", font=f_name)
    d.text((left + nw + 6 * scale, y), ".", font=f_name, fill=MINT)

    y += 116 * scale
    d.text((left, y), "Measure your controller timing, test every pad,",
           font=f_sub, fill=SAGE)
    d.text((left, y + 34 * scale), "and bind pad buttons to macros.",
           font=f_sub, fill=SAGE)

    y += 104 * scale
    d.line([(left, y), (left + 46 * scale, y)], fill=DEEP, width=round(3 * scale))
    d.text((left, y + 16 * scale), "github.com/KayTwoOne/Cadence", font=f_url, fill=DIM)

    return img.resize((w, h), Image.LANCZOS)


def build_social(w=1280, h=640):
    """GitHub's social preview card is 1280x640 and gets cropped to 1200x600."""
    return build_banner(w, h)


def build_wide(w=2000, h=618):
    """Wide strip for the top of the README, same proportions as the BMFinder one."""
    return build_banner(w, h)


def write_ico(path, images):
    """Write an .ico whose entries are the images given, not resamples of one."""
    import struct
    from io import BytesIO
    blobs = []
    for im in images:
        buf = BytesIO()
        im.save(buf, format="PNG")     # PNG-compressed entries, valid since Vista
        blobs.append(buf.getvalue())
    offset = 6 + 16 * len(blobs)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(blobs)))
        for im, blob in zip(images, blobs):
            w = 0 if im.width >= 256 else im.width
            h = 0 if im.height >= 256 else im.height
            fh.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset))
            offset += len(blob)
        for blob in blobs:
            fh.write(blob)


def main():
    os.makedirs(OUT, exist_ok=True)

    build_icon(1024).save(os.path.join(OUT, "icon.png"))
    build_icon_solid(1024).save(os.path.join(OUT, "icon-solid.png"))

    sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = {n: build_icon(n) for n in sizes}
    for n, im in frames.items():
        im.save(os.path.join(OUT, f"icon-{n}.png"))

    # Pillow builds a .ico by downscaling one image, which would throw away the
    # simplified small drawings. Writing the directory by hand keeps each as drawn.
    write_ico(os.path.join(os.path.dirname(HERE), "cadence.ico"),
              [frames[n] for n in sizes])

    build_wide(2000, 618).save(os.path.join(OUT, "banner.png"))
    build_social(1280, 640).save(os.path.join(OUT, "social-preview.png"))
    build_banner(1280, 400).save(os.path.join(OUT, "banner-compact.png"))

    print("wrote:")
    for f in sorted(os.listdir(OUT)):
        if f.endswith(".png"):
            p = os.path.join(OUT, f)
            print(f"  assets/{f:26} {os.path.getsize(p) // 1024:5d} KB")
    print("  cadence.ico (7 sizes)")


if __name__ == "__main__":
    main()
