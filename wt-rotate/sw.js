// Service worker — installabilité PWA + copie hors-ligne du Centre d'aide.
//
// Seule la page /support est mise en cache : elle doit rester consultable même
// quand le serveur est injoignable (c'est le lien « Support & aide » de la page
// d'erreur 105). Tout le reste du trafic (app, WebSocket, /info, /qr.svg…) passe
// directement au réseau — le SW ne l'intercepte pas.

const CACHE = 'wt-help-v1';
const HELP = '/support';

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(c => c.add(HELP)).catch(() => {})
  );
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    // Purge des anciennes versions de cache
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
  if (url.pathname !== '/support' && url.pathname !== '/aide') return;

  // Network-first : on sert la version fraîche si le serveur répond, et on
  // rafraîchit la copie hors-ligne au passage ; sinon on bascule sur le cache.
  e.respondWith(
    fetch(e.request).then(resp => {
      const copy = resp.clone();
      caches.open(CACHE).then(c => c.put(HELP, copy)).catch(() => {});
      return resp;
    }).catch(() =>
      caches.match(HELP).then(r => r || new Response(
        '<!doctype html><meta charset=utf-8><title>Hors ligne</title>' +
        '<body style="font-family:-apple-system,sans-serif;padding:40px;text-align:center">' +
        '<h2>Centre d\'aide indisponible hors ligne</h2>' +
        '<p>Reconnectez-vous au serveur puis réessayez.</p>',
        { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
      ))
    )
  );
});
