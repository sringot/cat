// Masque l'interface vidéo Canva — class names extraits via DevTools

const CSS = `
  /* Bouton play central — class .BDjDQQ confirmée */
  .BDjDQQ,
  .Flujtg,
  button[aria-label="Lire"],
  button[aria-label="Play"],
  button[aria-label="Read"] {
    display: none !important;
  }

  /* Barre de contrôles vidéo en bas — class .rURnAQ confirmée */
  .rURnAQ {
    display: none !important;
  }
`;

function injectCSS() {
  if (document.getElementById('wr-canva-fix')) return;
  const s = document.createElement('style');
  s.id = 'wr-canva-fix';
  s.textContent = CSS;
  (document.head || document.documentElement).appendChild(s);
}

function hideTopBar() {
  // h1 confirmé via DevTools : h1._5Gynyg.snQKTg (titre "Trame canva Présence")
  const h1 = document.querySelector(
    'h1.snQKTg, h1._5Gynyg, h1[class*="snQKTg"], h1[class*="5Gynyg"]'
  );
  if (!h1) return;

  // Remonte jusqu'au conteneur de la barre du haut (pleine largeur, hauteur < 80px, positionné en haut)
  let el = h1.parentElement;
  for (let i = 0; i < 5 && el; i++) {
    const r = el.getBoundingClientRect();
    if (r.top < 10 && r.width > window.innerWidth * 0.5 && r.height < 100) {
      el.style.setProperty('display', 'none', 'important');
      return;
    }
    el = el.parentElement;
  }
}

injectCSS();

function run() {
  injectCSS();
  hideTopBar();
}

if (document.body) {
  run();
  new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
} else {
  document.addEventListener('DOMContentLoaded', () => {
    run();
    new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
  });
}
