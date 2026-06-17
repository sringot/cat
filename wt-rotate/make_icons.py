#!/usr/bin/env python3
"""
Génère les icônes wee rotate à partir du logo de marque « goodone.png ».

Identité : logo noir sur tuile blanche (fidèle au PNG fourni). Le logo source
est recadré sur sa marque visible puis recentré avec une marge constante, pour
des icônes nettes et homogènes à toutes les tailles (extension, PWA, apple-touch).

Usage :
  python make_icons.py

Nécessite : pip install pillow
Le fichier goodone.png doit être à côté de ce script.
"""
import sys
import pathlib
from PIL import Image

SCRIPT_DIR = pathlib.Path(__file__).parent
LOGO_PATHS = [SCRIPT_DIR / 'goodone.png',
              SCRIPT_DIR / 'icons' / 'goodone.png']

BG = (255, 255, 255)     # fond clair de la tuile
CONTENT = 0.78           # largeur de la marque en fraction de la tuile (zone sûre maskable)


def _logo_path() -> str:
    for p in LOGO_PATHS:
        if p.exists():
            return str(p)
    sys.exit('goodone.png introuvable à côté du script.')


def _art() -> Image.Image:
    """Charge le logo et le recadre au plus près de l'artwork (pixels non blancs)."""
    src = Image.open(_logo_path()).convert('RGB')
    gray = src.convert('L')
    mask = gray.point(lambda p: 255 if p < 250 else 0)   # tout ce qui n'est pas blanc
    bbox = mask.getbbox()
    if bbox is None:
        sys.exit('goodone.png est entièrement blanc — aucune marque à rendre.')
    return src.crop(bbox)


def render(size: int, art: Image.Image) -> Image.Image:
    """Tuile blanche `size`×`size` avec la marque centrée à CONTENT %."""
    canvas = Image.new('RGB', (size, size), BG)
    aw, ah = art.size
    scale = (CONTENT * size) / max(aw, ah)
    nw, nh = max(1, round(aw * scale)), max(1, round(ah * scale))
    mark = art.resize((nw, nh), Image.LANCZOS)
    canvas.paste(mark, ((size - nw) // 2, (size - nh) // 2))
    return canvas


if __name__ == '__main__':
    out = SCRIPT_DIR / 'icons'
    out.mkdir(exist_ok=True)
    art = _art()

    print('Génération des icônes wee (logo noir sur blanc)…')
    render(1024, art).save(out / 'icon-source.png', optimize=True)
    print('  icon-source.png (1024)')
    for sz in (512, 180, 128, 48, 16):
        render(sz, art).save(out / f'icon{sz}.png', optimize=True)
        print(f'  icon{sz}.png')
    print('Terminé.')
