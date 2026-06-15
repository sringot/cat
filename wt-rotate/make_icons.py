#!/usr/bin/env python3
"""
Génère les icônes wee rotate — design Wee Technology.
Fond noir charbon (#1A1A1A), texte « wee » blanc en Poppins SemiBold,
point teal (#3DD9F5) en exposant.

Usage :
  python make_icons.py

Nécessite : pip install pillow
La police Poppins-SemiBold.ttf doit être dans le même dossier que ce script,
ou dans /tmp/Poppins-SemiBold.ttf (téléchargée automatiquement si absent).
"""
from PIL import Image, ImageDraw, ImageFont
import os, pathlib, urllib.request

BG_COLOR   = (0x1A, 0x1A, 0x1A)
TEXT_COLOR = (0xFF, 0xFF, 0xFF)
DOT_COLOR  = (0x3D, 0xD9, 0xF5)   # teal #3DD9F5

SCRIPT_DIR = pathlib.Path(__file__).parent
FONT_PATHS = [
    SCRIPT_DIR / 'Poppins-SemiBold.ttf',
    pathlib.Path('/tmp/Poppins-SemiBold.ttf'),
]
FONT_URL = (
    'https://fonts.gstatic.com/s/poppins/v21/'
    'pxiByp8kv8JHgFVrLGT9Z1xlFQ.woff2'
)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    # Téléchargement automatique (woff2 → subset latin, lisible par Pillow)
    dst = pathlib.Path('/tmp/Poppins-SemiBold.woff2')
    ttf = pathlib.Path('/tmp/Poppins-SemiBold.ttf')
    print('  → téléchargement de Poppins-SemiBold…')
    urllib.request.urlretrieve(FONT_URL, dst)
    # Conversion woff2 → ttf
    import sys, io
    sys.path.insert(0, '/usr/local/lib/python3.11/dist-packages')
    from fontTools.ttLib.woff2 import decompress
    buf = io.BytesIO(dst.read_bytes())
    out = io.BytesIO()
    decompress(buf, out)
    out.seek(0)
    ttf.write_bytes(out.read())
    return ImageFont.truetype(str(ttf), size)


def _draw_icon(draw, S: int, rounded_bg: bool):
    """Dessine l'icône sur `draw` (canvas S×S)."""
    radius = int(S * 0.215)
    if rounded_bg:
        img_tmp = draw._image  # accès direct pour rounded_rectangle
        draw.rounded_rectangle(
            [(0, 0), (S - 1, S - 1)], radius=radius, fill=BG_COLOR + (255,)
        )
    else:
        draw.rectangle([(0, 0), (S - 1, S - 1)], fill=BG_COLOR)

    # Texte « wee » occupant ~57 % de la largeur
    target_w = S * 0.57
    font_size = int(S * 0.38)
    font = _get_font(font_size)
    for _ in range(20):
        bbox = draw.textbbox((0, 0), 'wee', font=font)
        if abs(bbox[2] - bbox[0] - target_w) < S * 0.005:
            break
        font_size = int(font_size * target_w / (bbox[2] - bbox[0]))
        font = _get_font(font_size)

    bbox = draw.textbbox((0, 0), 'wee', font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (S - tw) // 2 - bbox[0]
    ty = (S - th) // 2 - bbox[1] - int(S * 0.015)
    draw.text((tx, ty), 'wee', font=font, fill=TEXT_COLOR + (255,))

    # Point teal en exposant
    dot_r  = int(S * 0.032)
    dot_cx = tx + tw + int(S * 0.018)
    dot_cy = ty - int(dot_r * 0.5)
    draw.ellipse(
        [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
        fill=DOT_COLOR + (255,),
    )


def make_icon(output_size: int, out_path: str, rgba: bool = True):
    """Génère un PNG avec fond arrondi transparent (pour iOS PWA, splash…)."""
    S = output_size * 4
    mode = 'RGBA' if rgba else 'RGB'
    img  = Image.new(mode, (S, S), (0, 0, 0, 0) if rgba else BG_COLOR)
    draw = ImageDraw.Draw(img)
    _draw_icon(draw, S, rounded_bg=True)
    final = img.resize((output_size, output_size), Image.LANCZOS)
    final.save(out_path, optimize=True)
    print(f'  {out_path} ({output_size}px)')


def make_ext_icon(output_size: int, out_path: str):
    """Icône pour l'extension Chrome (fond plein, pas de transparence)."""
    S = output_size * 4
    img  = Image.new('RGB', (S, S), BG_COLOR)
    draw = ImageDraw.Draw(img)
    _draw_icon(draw, S, rounded_bg=False)
    final = img.resize((output_size, output_size), Image.LANCZOS)
    final.save(out_path, optimize=True)
    print(f'  {out_path} ({output_size}px, ext)')


if __name__ == '__main__':
    out = SCRIPT_DIR / 'icons'
    out.mkdir(exist_ok=True)

    print('Génération des icônes wee rotate…')
    make_icon    (1024, str(out / 'icon-source.png'))   # master
    make_icon    (512,  str(out / 'icon512.png'))
    make_icon    (180,  str(out / 'icon180.png'))        # apple-touch-icon
    make_ext_icon(128,  str(out / 'icon128.png'))        # Chrome ext
    make_ext_icon(48,   str(out / 'icon48.png'))
    make_ext_icon(16,   str(out / 'icon16.png'))
    print('Terminé.')
