#!/usr/bin/env python3
"""Generate wt-rotate icons — Wee Technology style: blue circle, white bold w."""
from PIL import Image, ImageDraw
import os

BLUE  = (27, 81, 165)
WHITE = (255, 255, 255)


def rrect(draw, x0, y0, x1, y1, r, fill):
    r = max(0, min(r, (x1-x0)//2, (y1-y0)//2))
    draw.rectangle([x0+r, y0, x1-r, y1], fill=fill)
    draw.rectangle([x0, y0+r, x1, y1-r], fill=fill)
    draw.ellipse([x0,       y0,       x0+2*r, y0+2*r], fill=fill)
    draw.ellipse([x1-2*r,   y0,       x1,     y0+2*r], fill=fill)
    draw.ellipse([x0,       y1-2*r,   x0+2*r, y1    ], fill=fill)
    draw.ellipse([x1-2*r,   y1-2*r,   x1,     y1    ], fill=fill)


def make_icon(size):
    s = size
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Blue circle ───────────────────────────────────────────────────────────
    draw.ellipse([0, 0, s-1, s-1], fill=BLUE)

    # ── White "w" body ────────────────────────────────────────────────────────
    # bounds of the w inside the circle
    mx = s * 0.105
    mt = s * 0.135
    mb = s * 0.140

    x0, y0 = mx, mt
    x1, y1 = s - mx, s - mb
    ww = x1 - x0
    wh = y1 - y0

    # main rounded body
    rrect(draw, int(x0), int(y0), int(x1), int(y1), int(ww * 0.135), WHITE)

    # ── Two inner notches cut from top (draw blue on top of white) ────────────
    nw = ww * 0.188   # notch width
    nh = wh * 0.530   # notch depth
    nr = int(nw * 0.50)

    for frac in (0.272, 0.728):
        ncx = x0 + ww * frac
        rrect(draw, int(ncx - nw/2), int(y0 - 2),
              int(ncx + nw/2), int(y0 + nh), nr, BLUE)

    # ── Subtle bottom valley (center dip) ─────────────────────────────────────
    vw = ww * 0.100
    vh = wh * 0.115
    vcx = s / 2
    draw.ellipse([int(vcx-vw/2), int(y1-vh),
                  int(vcx+vw/2), int(y1+vh*0.3)], fill=BLUE)

    # ── Clip to circle (for corners of w that stick out) ─────────────────────
    mask = Image.new('L', (s, s), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, s-1, s-1], fill=255)
    out = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out


os.makedirs('icons', exist_ok=True)
master = make_icon(512)
master.save('icons/icon512.png')

for sz in [16, 48, 128, 180]:
    master.resize((sz, sz), Image.LANCZOS).save(f'icons/icon{sz}.png')
    print(f'  icons/icon{sz}.png')
