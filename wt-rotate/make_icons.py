#!/usr/bin/env python3
"""
Génère les icônes wee rotate à partir du logo de marque « logoW_edited.png ».

Identité (v1.17) : tuile charbon profond façon Neumorphisme/Minimalisme,
marque « w » en vert néon (#19E57D) avec halo diffus, reflet supérieur glossy
et léger relief — pour un rendu dimensionnel/tactile type icône iOS.

Le logo source est monochrome sur fond transparent : on se sert de son canal
alpha comme masque de forme, puis on le recolore en dégradé vert néon.

Usage :
  python make_icons.py

Nécessite : pip install pillow numpy
Le fichier logoW_edited.png doit être à côté de ce script.
"""
import sys, pathlib
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

SCRIPT_DIR = pathlib.Path(__file__).parent
LOGO_PATHS = [SCRIPT_DIR / 'logoW_edited.png',
              SCRIPT_DIR / 'icons' / 'logoW_edited.png']

# Palette — accord avec l'UI (control.html) : vert néon profond sur charbon.
ACCENT      = (25, 229, 125)    # #19E57D vert néon
ACCENT_HI   = (104, 247, 173)   # reflet clair du dégradé de la marque
ACCENT_LO   = (12, 191, 104)    # base profonde du dégradé
TILE_TOP    = (42, 47, 60)      # haut de la tuile (lumière)
TILE_BOT    = (18, 20, 26)      # bas de la tuile (profondeur)


def _logo_path() -> str:
    for p in LOGO_PATHS:
        if p.exists():
            return str(p)
    sys.exit('logoW_edited.png introuvable à côté du script.')


# ── helpers graphiques ──────────────────────────────────────────────────────
def _vgrad(w, h, top, bot):
    """Dégradé vertical opaque."""
    t = np.linspace(0, 1, h)[:, None]
    a = np.zeros((h, w, 4), np.uint8)
    for i in range(3):
        a[:, :, i] = (top[i] * (1 - t) + bot[i] * t).astype(np.uint8)
    a[:, :, 3] = 255
    return Image.fromarray(a, 'RGBA')


def _radial(w, h, cx, cy, r, inner, outer):
    """Dégradé radial (inner→outer en RGBA)."""
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.clip(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r, 0, 1)
    a = np.zeros((h, w, 4), np.uint8)
    for i in range(4):
        a[:, :, i] = (inner[i] * (1 - d) + outer[i] * d).astype(np.uint8)
    return Image.fromarray(a, 'RGBA')


def _logo_mask(S, scale=0.60):
    """Charge le logo, recadre sur la marque et renvoie un masque L S×S centré.

    `scale` = largeur cible de la marque en fraction de S.
    """
    src = Image.open(_logo_path()).convert('RGBA')
    alpha = src.split()[3]
    bbox = alpha.getbbox()                     # recadre sur la marque visible
    if bbox is None:
        sys.exit('logoW_edited.png est entièrement transparent — aucune marque à rendre.')
    mark = alpha.crop(bbox)
    mw, mh = mark.size
    target_w = int(S * scale)
    target_h = int(target_w * mh / mw)
    mark = mark.resize((target_w, target_h), Image.LANCZOS)
    m = Image.new('L', (S, S), 0)
    m.paste(mark, ((S - target_w) // 2, (S - target_h) // 2))
    return m


def render(out):
    """Rend une icône glossy `out`×`out` (supersampling ×3)."""
    SS = 3
    S = out * SS

    # ── TUILE : dégradé charbon + halo vert + reflet supérieur ───────────────
    tile = _vgrad(S, S, TILE_TOP, TILE_BOT)

    # halo vert diffus, légèrement bas-centre, pour l'identité de marque
    glow = _radial(S, S, S // 2, int(S * 0.56), int(S * 0.52),
                   (*ACCENT, 70), (*ACCENT, 0))
    tile = Image.alpha_composite(tile, glow.filter(ImageFilter.GaussianBlur(S * 0.03)))

    # reflet glossy en haut (balayage elliptique blanc très doux)
    sweep = Image.new('L', (S, S), 0)
    ImageDraw.Draw(sweep).ellipse([-int(S * 0.3), -int(S * 0.85),
                                   int(S * 1.3), int(S * 0.40)], fill=70)
    sweep = sweep.filter(ImageFilter.GaussianBlur(S * 0.04))
    tile = Image.alpha_composite(tile, Image.composite(
        Image.new('RGBA', (S, S), (255, 255, 255, 255)),
        Image.new('RGBA', (S, S), (0, 0, 0, 0)), sweep))

    # liseré lumineux haut (rim light) qui s'estompe vers le bas
    ring = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(
        [(0, 0), (S - 1, S - 1)], radius=int(S * 0.235),
        outline=(255, 255, 255, 130), width=max(2, int(S * 0.004)))
    ga = np.array(ring.split()[3], float) * np.linspace(1, 0.05, S)[:, None]
    ring.putalpha(Image.fromarray(ga.astype(np.uint8)))
    tile = Image.alpha_composite(tile, ring)

    # ── MARQUE « w » : dégradé vert néon + halo + reflet ─────────────────────
    gm = _logo_mask(S, scale=0.60)

    layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))

    # halo vert serré derrière la marque
    halo = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    halo.paste(Image.new('RGBA', (S, S), (*ACCENT, 130)), (0, 0), gm)
    layer = Image.alpha_composite(layer, halo.filter(ImageFilter.GaussianBlur(S * 0.022)))

    # ombre portée douce (profondeur)
    drop = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    drop.paste(Image.new('RGBA', (S, S), (0, 0, 0, 150)), (0, int(S * 0.012)), gm)
    layer = Image.alpha_composite(layer, drop.filter(ImageFilter.GaussianBlur(S * 0.014)))

    # corps de la marque : dégradé vert clair (haut) → vert profond (bas)
    core = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    core.paste(_vgrad(S, S, ACCENT_HI, ACCENT_LO), (0, 0), gm)
    layer = Image.alpha_composite(layer, core)

    # reflet glossy sur la moitié haute de la marque
    bb = gm.getbbox()
    half = Image.new('L', (S, S), 0)
    ImageDraw.Draw(half).rectangle([0, 0, S, bb[1] + int((bb[3] - bb[1]) * 0.42)], fill=255)
    glm = Image.composite(gm, Image.new('L', (S, S), 0), half)
    sheen = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    sheen.paste(Image.new('RGBA', (S, S), (255, 255, 255, 95)), (0, 0), glm)
    layer = Image.alpha_composite(layer, sheen)

    icon = Image.alpha_composite(tile, layer)
    return icon.resize((out, out), Image.LANCZOS)


if __name__ == '__main__':
    out = SCRIPT_DIR / 'icons'
    out.mkdir(exist_ok=True)

    print('Génération des icônes wee (logo vert néon)…')
    master = render(1024)
    master.save(out / 'icon-source.png', optimize=True)
    print('  icon-source.png (1024)')
    for sz in (512, 180, 128, 48, 16):
        master.resize((sz, sz), Image.LANCZOS).save(out / f'icon{sz}.png', optimize=True)
        print(f'  icon{sz}.png')
    print('Terminé.')
