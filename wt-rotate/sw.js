// Service worker minimal — présent uniquement pour l'installabilité de la PWA
// (Android / Chrome). Pas de cache hors-ligne, pas de notifications push.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
