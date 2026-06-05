// Injecté sur canva.com — masque l'overlay vidéo pour afficher le design en statique

const CSS = `
  [class*="playerWrapper"],
  [class*="PlayerWrapper"],
  [class*="videoPlayer"],
  [class*="VideoPlayer"],
  [class*="playButton"],
  [class*="PlayButton"],
  [class*="playOverlay"],
  [class*="PlayOverlay"],
  [class*="videoControls"],
  [class*="VideoControls"],
  [data-testid*="play"],
  [aria-label="Lire"],
  [aria-label="Read"],
  [aria-label="Play"] {
    display: none !important;
    opacity: 0 !important;
    pointer-events: none !important;
  }
`;

function inject() {
  if (document.getElementById('wee-rotate-fix')) return;
  const s = document.createElement('style');
  s.id = 'wee-rotate-fix';
  s.textContent = CSS;
  (document.head || document.documentElement).appendChild(s);
}

inject();
new MutationObserver(inject).observe(document.documentElement, { childList: true, subtree: true });
