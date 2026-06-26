// Service worker — installabilité PWA + copies hors-ligne (Centre d'aide + app).
//
// Deux pages sont gardées en cache pour rester accessibles serveur coupé :
//   • /support — le Centre d'aide (lien « Support & aide » de la page d'erreur).
//   • /app     — la coquille de la télécommande. Sans ça, ouvrir le PWA serveur
//                éteint affiche l'écran d'erreur natif de Chrome. Avec, on sert la
//                dernière copie de control.html : elle boote, ne joint pas le
//                WebSocket, et affiche sa propre page « Serveur injoignable ·
//                Erreur 105 » (qui propose à son tour le Centre d'aide caché).
// Tout le reste (WebSocket, /info, /qr.svg…) passe direct au réseau.
//
// Limite inhérente aux PWA : le cache se remplit à la 1re visite réussie (serveur
// allumé). Le tout premier lancement serveur déjà éteint reste donc une erreur
// navigateur — il n'y a encore rien en mémoire.

const CACHE  = 'wt-shell-v2';
const HELP   = '/support';
const SHELL  = '/app';
const ASSETS = [HELP, SHELL];

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    // add() individuel : si une page échoue (serveur lent, 404…), l'autre est
    // quand même mise en cache.
    caches.open(CACHE)
      .then(c => Promise.all(ASSETS.map(p => c.add(p).catch(() => {}))))
      .catch(() => {})
  );
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    // Purge des anciennes versions de cache (ex. wt-help-v1).
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  let url;
  try { url = new URL(e.request.url); } catch { return; }
  if (url.origin !== self.location.origin) return;

  // On normalise sur le chemin : la clé de cache ignore le ?token=… éventuel
  // (le PWA lance /app et lit le token dans localStorage).
  const key = (url.pathname === '/support' || url.pathname === '/aide') ? HELP
            : (url.pathname === '/app')                                 ? SHELL
            : null;
  if (!key) return;

  // Network-first : version fraîche si le serveur répond (et on rafraîchit la
  // copie hors-ligne au passage) ; sinon on bascule sur le cache.
  e.respondWith(
    fetch(e.request).then(resp => {
      const copy = resp.clone();
      caches.open(CACHE).then(c => c.put(key, copy)).catch(() => {});
      return resp;
    }).catch(() =>
      caches.match(key).then(r => r || offlineFallback(key))
    )
  );
});

// Dernier recours : rien en cache pour cette page (serveur jamais atteint sur ce
// téléphone). On rend au moins une page on-brand plutôt qu'une erreur réseau.
function offlineFallback(key) {
  if (key === SHELL) {
    return new Response(
      '<!doctype html><meta charset=utf-8>' +
      '<meta name=viewport content="width=device-width,initial-scale=1">' +
      '<title>Serveur injoignable</title>' +
      '<body style="font-family:-apple-system,system-ui,sans-serif;background:#1F241B;' +
      'color:#eee;min-height:100vh;margin:0;display:flex;flex-direction:column;' +
      'align-items:center;justify-content:center;text-align:center;padding:32px">' +
      '<h2 style="margin:0 0 8px">Serveur injoignable</h2>' +
      '<p style="opacity:.7;max-width:320px;line-height:1.5">Le PC remote ne répond pas. ' +
      'Vérifiez qu\'il est allumé, sur le même réseau, et que le serveur est lancé.</p>' +
      '<p style="font-size:13px;opacity:.5">Erreur 105 · connexion impossible</p>' +
      '<p style="margin-top:24px"><a href="/support" style="color:#9cc">Support &amp; aide</a></p>',
      { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
  }
  return new Response(
    '<!doctype html><meta charset=utf-8><title>Hors ligne</title>' +
    '<body style="font-family:-apple-system,sans-serif;padding:40px;text-align:center">' +
    '<h2>Centre d\'aide indisponible hors ligne</h2>' +
    '<p>Reconnectez-vous au serveur puis réessayez.</p>',
    { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}
