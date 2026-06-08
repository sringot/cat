#!/usr/bin/env python3
"""Generate wt-rotate extension icons — bold rotation arrows, black on transparent."""
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


def draw(x, y, size):
    s  = float(size)
    cx = cy = s / 2.0
    px = x + 0.5
    py = y + 0.5
    dx = px - cx
    dy = py - cy
    dist      = math.sqrt(dx * dx + dy * dy)
    angle_deg = math.degrees(math.atan2(dy, dx)) % 360  # 0-360, 0=right, CW

    R_OUT = s * 0.44
    R_IN  = s * 0.24
    R_MID = (R_OUT + R_IN) / 2.0
    AA_W  = max(0.8, s * 0.016)

    # Two arcs — gaps at 0° (3 o'clock) and 180° (9 o'clock), ±10° each
    # ARC1 (top half): 190° → 350°, going CW through 270° (12 o'clock)
    # ARC2 (bottom half): 10° → 170°, going CW through 90° (6 o'clock)
    ARC1_S, ARC1_E = 190.0, 350.0
    ARC2_S, ARC2_E = 10.0,  170.0

    def in_arc(deg, a, b):
        return a <= deg <= b

    in_arc1 = in_arc(angle_deg, ARC1_S, ARC1_E)
    in_arc2 = in_arc(angle_deg, ARC2_S, ARC2_E)

    # Ring alpha with smooth AA at inner/outer edges
    ring_alpha = 0
    if in_arc1 or in_arc2:
        if R_IN <= dist <= R_OUT:
            ring_alpha = 255
        elif dist < R_IN:
            ring_alpha = int(255 * max(0.0, (dist - (R_IN - AA_W)) / AA_W))
        else:
            ring_alpha = int(255 * max(0.0, (R_OUT + AA_W - dist) / AA_W))

    # Arrowhead triangles at each arc end (CW tangent direction)
    def in_triangle(v1, v2, v3):
        def cross2d(ax, ay, bx, by):
            return (px - bx) * (ay - by) - (ax - bx) * (py - by)
        d1 = cross2d(v1[0], v1[1], v2[0], v2[1])
        d2 = cross2d(v2[0], v2[1], v3[0], v3[1])
        d3 = cross2d(v3[0], v3[1], v1[0], v1[1])
        neg = d1 < 0 or d2 < 0 or d3 < 0
        pos = d1 > 0 or d2 > 0 or d3 > 0
        return not (neg and pos)

    def arrow_fill(end_deg):
        tr   = math.radians(end_deg)
        tang = tr + math.pi / 2         # CW tangent
        ARR  = (R_OUT - R_IN) * 1.15   # arrowhead length
        v1 = (cx + R_OUT * math.cos(tr), cy + R_OUT * math.sin(tr))
        v2 = (cx + R_IN  * math.cos(tr), cy + R_IN  * math.sin(tr))
        v3 = (cx + R_MID * math.cos(tr) + ARR * math.cos(tang),
              cy + R_MID * math.sin(tr) + ARR * math.sin(tang))
        return 255 if in_triangle(v1, v2, v3) else 0

    final_alpha = max(ring_alpha, arrow_fill(ARC1_E), arrow_fill(ARC2_E))
    return [0, 0, 0, final_alpha]


os.makedirs('icons', exist_ok=True)
for sz in [16, 48, 128]:
    data = make_png(sz, draw)
    path = f'icons/icon{sz}.png'
    with open(path, 'wb') as f:
        f.write(data)
    print(f'  {path}  ({len(data)} bytes)')
