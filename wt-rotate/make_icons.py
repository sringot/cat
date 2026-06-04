#!/usr/bin/env python3
"""Generate wt-rotate extension icons (no external dependencies)."""
import struct, zlib, math, os

def make_png(size, pixel_fn):
    raw = b''
    for y in range(size):
        raw += b'\x00'
        for x in range(size):
            raw += bytes(pixel_fn(x, y, size))

    def chunk(t, d):
        payload = t + d
        return struct.pack('>I', len(d)) + payload + struct.pack('>I', zlib.crc32(payload) & 0xffffffff)

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>II', size, size) + b'\x08\x06\x00\x00\x00')
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))


def lerp(a, b, t):
    return int(a + (b - a) * t)

def aa_circle(dist, r, width=1.4):
    """Return alpha [0-255] for an anti-aliased circle edge."""
    d = dist - r
    if d < -width / 2:
        return 255
    if d > width / 2:
        return 0
    return int(255 * (0.5 - d / width))


def draw(x, y, size):
    s  = float(size)
    cx = cy = s / 2.0
    px = x + 0.5
    py = y + 0.5
    dx = px - cx
    dy = py - cy
    dist   = math.sqrt(dx * dx + dy * dy)
    angle  = math.atan2(dy, dx)   # -π … π

    # --- geometry (relative to size) ---
    R_BG   = s * 0.48   # background circle radius
    R_OUT  = s * 0.375  # ring outer
    R_IN   = s * 0.215  # ring inner
    R_MID  = (R_OUT + R_IN) / 2.0

    BG = [15, 52, 96]      # #0f3460
    FG = [255, 255, 255]   # white

    # Outside the icon → transparent
    bg_alpha = aa_circle(dist, R_BG)
    if bg_alpha == 0:
        return [0, 0, 0, 0]

    # --- arc: 300° ring, gap at the top (clockwise arrow) ---
    # Gap: from -π/2 - 30° to -π/2 + 30°  (i.e. top ± 30°)
    GAP_CENTER = -math.pi / 2.0
    GAP_HALF   = math.pi / 6.0    # 30°

    def angle_diff(a, b):
        d = abs(a - b) % (2 * math.pi)
        return d if d <= math.pi else 2 * math.pi - d

    in_ring  = R_IN <= dist <= R_OUT
    in_gap   = angle_diff(angle, GAP_CENTER) < GAP_HALF

    ring_alpha = 0
    if in_ring and not in_gap:
        ring_alpha = 255

    # Anti-alias the ring edges (outer & inner)
    if not in_gap:
        ring_alpha = max(ring_alpha, aa_circle(dist, R_OUT) - aa_circle(dist, R_OUT))
        outer_aa = aa_circle(dist, R_OUT, 1.8)
        inner_aa = aa_circle(dist, R_IN,  1.8)
        ring_alpha = max(0, min(255, outer_aa - (255 - inner_aa) if dist < R_MID else outer_aa))
        if R_IN < dist < R_OUT and not in_gap:
            ring_alpha = 255

    # --- arrowhead ---
    # Clockwise end of the arc = GAP_CENTER - GAP_HALF (left side of gap)
    arrow_tip_a = GAP_CENTER - GAP_HALF     # ≈ -120° → bottom-left area
    TANG = arrow_tip_a - math.pi / 2.0      # tangent at that point, pointing "into" the gap

    v1x = cx + R_OUT * math.cos(arrow_tip_a)
    v1y = cy + R_OUT * math.sin(arrow_tip_a)
    v2x = cx + R_IN  * math.cos(arrow_tip_a)
    v2y = cy + R_IN  * math.sin(arrow_tip_a)
    ARR = s * 0.19
    v3x = cx + R_MID * math.cos(arrow_tip_a) + ARR * math.cos(TANG)
    v3y = cy + R_MID * math.sin(arrow_tip_a) + ARR * math.sin(TANG)

    def sign(ax, ay, bx, by):
        return (px - bx) * (ay - by) - (ax - bx) * (py - by)

    d1 = sign(v1x, v1y, v2x, v2y)
    d2 = sign(v2x, v2y, v3x, v3y)
    d3 = sign(v3x, v3y, v1x, v1y)
    in_arrow = not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))

    if in_arrow:
        ring_alpha = 255

    # --- compose: BG + FG (ring/arrow) ---
    if ring_alpha == 0:
        # pure background color
        r = lerp(0, BG[0], bg_alpha / 255.0)
        g = lerp(0, BG[1], bg_alpha / 255.0)
        b = lerp(0, BG[2], bg_alpha / 255.0)
        return [r, g, b, bg_alpha]
    else:
        # blend FG over BG, then blend over transparent
        t = ring_alpha / 255.0
        rgb = [lerp(BG[i], FG[i], t) for i in range(3)]
        r2 = lerp(0, rgb[0], bg_alpha / 255.0)
        g2 = lerp(0, rgb[1], bg_alpha / 255.0)
        b2 = lerp(0, rgb[2], bg_alpha / 255.0)
        return [r2, g2, b2, bg_alpha]


os.makedirs('icons', exist_ok=True)
for sz in [16, 48, 128]:
    data = make_png(sz, draw)
    path = f'icons/icon{sz}.png'
    with open(path, 'wb') as f:
        f.write(data)
    print(f'  {path}  ({len(data)} bytes)')
