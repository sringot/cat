#!/usr/bin/env python3
"""
Génère les icônes wee rotate — effet « glass » glossy façon icônes Apple.

Identité : tuile noir charbon, « wee » blanc lustré en Poppins SemiBold,
point teal (#3DD9F5) en bille glossy. Reliefs : dégradé, reflet supérieur,
rim light, ombre interne, ombre portée et halo central — pour le look
dimensionnel/tactile des icônes iOS récentes.

Usage :
  python make_icons.py            # variante 'dark' (défaut)
  python make_icons.py light      # variante claire (fond blanc, wee bleu)

Nécessite : pip install pillow numpy
La police Poppins-SemiBold.ttf doit être à côté de ce script (sinon elle est
téléchargée automatiquement dans /tmp).
"""
import sys, io, pathlib, urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

SCRIPT_DIR = pathlib.Path(__file__).parent
FONT_PATHS = [SCRIPT_DIR / 'Poppins-SemiBold.ttf',
              pathlib.Path('/tmp/Poppins-SemiBold.ttf')]
FONT_URL = ('https://fonts.gstatic.com/s/poppins/v21/'
            'pxiByp8kv8JHgFVrLGT9Z1xlFQ.woff2')

DOT_COLOR = (61, 217, 245)   # teal #3DD9F5


def _font_path() -> str:
    for p in FONT_PATHS:
        if p.exists():
            return str(p)
    dst = pathlib.Path('/tmp/Poppins-SemiBold.woff2')
    ttf = pathlib.Path('/tmp/Poppins-SemiBold.ttf')
    print('  → téléchargement de Poppins-SemiBold…')
    urllib.request.urlretrieve(FONT_URL, dst)
    sys.path.insert(0, '/usr/local/lib/python3.11/dist-packages')
    from fontTools.ttLib.woff2 import decompress
    out = io.BytesIO()
    decompress(io.BytesIO(dst.read_bytes()), out)
    out.seek(0)
    ttf.write_bytes(out.read())
    return str(ttf)


FONT = _font_path()


# ── petits helpers graphiques ──────────────────────────────────────────────────
def _vgrad(w, h, top, bot):
    t = np.linspace(0, 1, h)[:, None]
    a = np.zeros((h, w, 4), np.uint8)
    for i in range(3):
        a[:, :, i] = (top[i] * (1 - t) + bot[i] * t).astype(np.uint8)
    a[:, :, 3] = 255
    return Image.fromarray(a, 'RGBA')


def _radial(w, h, cx, cy, r, inner, outer):
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r, 0, 1)
    a = np.zeros((h, w, 4), np.uint8)
    for i in range(4):
        a[:, :, i] = (inner[i] * (1 - d) + outer[i] * d).astype(np.uint8)
    return Image.fromarray(a, 'RGBA')


def _rmask(S, rad):
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle([(0, 0), (S - 1, S - 1)], radius=rad, fill=255)
    return m


def _tmask(S, text, frac, dy=0.0):
    fs = int(S * 0.4)
    f = ImageFont.truetype(FONT, fs)
    d = ImageDraw.Draw(Image.new('L', (S, S)))
    for _ in range(24):
        b = d.textbbox((0, 0), text, font=f)
        w = b[2] - b[0]
        if abs(w - frac * S) < S * 0.004:
            break
        fs = int(fs * frac * S / w)
        f = ImageFont.truetype(FONT, fs)
    b = d.textbbox((0, 0), text, font=f)
    tw, th = b[2] - b[0], b[3] - b[1]
    tx = (S - tw) // 2 - b[0]
    ty = (S - th) // 2 - b[1] + int(S * dy)
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).text((tx, ty), text, font=f, fill=255)
    return m, (tx, ty, tw, th)


def _clip(layer, mask):
    layer.putalpha(Image.composite(layer.split()[3], Image.new('L', layer.size, 0), mask))
    return layer


def _pc(S, col, mask, off=(0, 0)):
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    im.paste(Image.new('RGBA', (S, S), col), off, mask)
    return im


def render(out, variant='dark'):
    """Rend une icône glossy `out`×`out` (supersampling ×3)."""
    SS = 3
    S = out * SS
    rad = int(S * 0.225)
    mask = _rmask(S, rad)

    if variant == 'dark':
        tt, tb = (74, 76, 84), (20, 20, 24)
        wt, wb = (255, 255, 255), (208, 214, 225)
        tile_glow = (120, 150, 195, 85); drop = (0, 0, 0, 165)
        halo_a = 45; sweep_v = 85; ish_a = 120
    else:  # light, fond blanc + wee bleu
        tt, tb = (255, 255, 255), (245, 248, 252)
        wt, wb = (84, 172, 252), (20, 76, 188)
        tile_glow = (210, 234, 255, 170); drop = (30, 64, 140, 60)
        halo_a = 0; sweep_v = 60; ish_a = 42

    # ── TUILE : dégradé + halo + reflet + ombre interne + rim light ───────────
    tile = _vgrad(S, S, tt, tb)
    tile = Image.alpha_composite(tile, _radial(S, S, S // 2, int(S * 0.4),
                                               int(S * 0.62), tile_glow, (0, 0, 0, 0)))
    sweep = Image.new('L', (S, S), 0)
    ImageDraw.Draw(sweep).ellipse([-int(S * 0.3), -int(S * 0.8),
                                   int(S * 1.3), int(S * 0.42)], fill=sweep_v)
    sweep = sweep.filter(ImageFilter.GaussianBlur(S * 0.035))
    tile = Image.alpha_composite(tile, _clip(Image.composite(
        Image.new('RGBA', (S, S), (255, 255, 255, 255)),
        Image.new('RGBA', (S, S), (0, 0, 0, 0)), sweep), mask))
    ish = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(ish).rounded_rectangle([(0, 0), (S - 1, S - 1)], radius=rad,
                                          outline=(0, 0, 0, ish_a), width=int(S * 0.02))
    ish = ish.filter(ImageFilter.GaussianBlur(S * 0.012))
    ia = np.array(ish.split()[3], float) * np.linspace(0.05, 1, S)[:, None]
    ish.putalpha(Image.fromarray(ia.astype(np.uint8)))
    tile = Image.alpha_composite(tile, _clip(ish, mask))
    ring = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle([(0, 0), (S - 1, S - 1)], radius=rad,
                                           outline=(255, 255, 255, 170),
                                           width=max(2, int(S * 0.005)))
    ring = ring.filter(ImageFilter.GaussianBlur(S * 0.003))
    ga = np.array(ring.split()[3], float) * np.linspace(1, 0.1, S)[:, None]
    ring.putalpha(Image.fromarray(ga.astype(np.uint8)))
    tile = Image.alpha_composite(tile, ring)
    tile.putalpha(mask)

    # ── « wee » lustré ────────────────────────────────────────────────────────
    gm, (tx, ty, tw, th) = _tmask(S, 'wee', 0.56, dy=-0.01)
    layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    layer = Image.alpha_composite(layer, _pc(S, drop, gm, (0, int(S * 0.013)))
                                  .filter(ImageFilter.GaussianBlur(S * 0.016)))
    if halo_a > 0:
        layer = Image.alpha_composite(layer, _clip(
            _pc(S, (150, 180, 215, halo_a), gm).filter(ImageFilter.GaussianBlur(S * 0.02)), mask))
    core = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    core.paste(_vgrad(S, S, wt, wb), (0, 0), gm)
    layer = Image.alpha_composite(layer, core)
    cg = _radial(S, S, S // 2, ty + th // 2, tw * 0.55, (255, 255, 255, 105), (255, 255, 255, 0))
    layer = Image.alpha_composite(layer, _clip(Image.composite(cg, Image.new('RGBA', (S, S), (0, 0, 0, 0)), gm), gm))
    half = Image.new('L', (S, S), 0)
    ImageDraw.Draw(half).rectangle([0, 0, S, int(ty + th * 0.46)], fill=255)
    glm = Image.composite(gm, Image.new('L', (S, S), 0), half).filter(ImageFilter.GaussianBlur(S * 0.005))
    layer = Image.alpha_composite(layer, _pc(S, (255, 255, 255, 120), glm))
    topm = Image.new('L', (S, S), 0)
    ImageDraw.Draw(topm).rectangle([0, 0, S, int(ty + th * 0.12)], fill=255)
    layer = Image.alpha_composite(layer, _pc(S, (255, 255, 255, 180),
                                  Image.composite(gm, Image.new('L', (S, S), 0), topm)))
    icon = Image.alpha_composite(tile, _clip(layer, mask))

    # ── point teal : bille glossy ──────────────────────────────────────────────
    dr = int(S * 0.034)
    dcx = tx + tw + int(S * 0.020)
    dcy = ty - int(dr * 0.4)
    L = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    g = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([dcx - dr * 2, dcy - dr * 2, dcx + dr * 2, dcy + dr * 2],
                              fill=(*DOT_COLOR, 85))
    L = Image.alpha_composite(L, g.filter(ImageFilter.GaussianBlur(S * 0.012)))
    bead = _radial(S, S, dcx - dr * 0.3, dcy - dr * 0.4, dr * 1.7,
                   (195, 249, 255, 255), (15, 146, 176, 255))
    bm = Image.new('L', (S, S), 0)
    ImageDraw.Draw(bm).ellipse([dcx - dr, dcy - dr, dcx + dr, dcy + dr], fill=255)
    bd = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    bd.paste(bead, (0, 0), bm)
    L = Image.alpha_composite(L, bd)
    sp = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sp).ellipse([dcx - dr * 0.55, dcy - dr * 0.65, dcx, dcy - dr * 0.1],
                               fill=(255, 255, 255, 225))
    L = Image.alpha_composite(L, sp.filter(ImageFilter.GaussianBlur(S * 0.0035)))
    icon = Image.alpha_composite(icon, _clip(L, mask))

    return icon.resize((out, out), Image.LANCZOS)


if __name__ == '__main__':
    variant = sys.argv[1] if len(sys.argv) > 1 else 'dark'
    out = SCRIPT_DIR / 'icons'
    out.mkdir(exist_ok=True)

    print(f'Génération des icônes wee (variante « {variant} »)…')
    # Un seul rendu haute résolution, puis downscale pour chaque taille.
    master = render(1024, variant)
    master.save(out / 'icon-source.png', optimize=True)
    print('  icon-source.png (1024)')
    for sz in (512, 180, 128, 48, 16):
        master.resize((sz, sz), Image.LANCZOS).save(out / f'icon{sz}.png', optimize=True)
        print(f'  icon{sz}.png')
    print('Terminé.')
