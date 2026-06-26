// Tests du service worker (sw.js) : routage du cache hors-ligne.
//
// Le SW tourne normalement dans un contexte navigateur (self, caches, fetch,
// Response, URL). On le charge ici dans un bac à sable `vm` qui simule ces
// globales, on capture les gestionnaires d'événements enregistrés, puis on
// exerce le handler `fetch` pour vérifier :
//   • /app, /support, /aide sont interceptés et mis en cache (network-first) ;
//   • serveur coupé → on sert la copie en cache, ou une page de repli on-brand ;
//   • tout le reste (autre chemin, non-GET, cross-origin) passe au réseau.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SW_SRC = fs.readFileSync(path.join(__dirname, '..', 'sw.js'), 'utf8');
const flush = () => new Promise(r => setImmediate(r));   // vide les microtasks en attente

// Charge sw.js dans un faux environnement service worker et renvoie de quoi le piloter.
function loadSW() {
  const listeners = {};
  const store = new Map();                 // cache simulé : clé (chemin) → réponse
  const deleted = [];                      // clés de cache supprimées (purge)
  const net = { offline: false, fail: new Set() };  // contrôle réseau mutable

  const makeResp = (body, init = {}) => ({
    _body: body,
    status: init.status || 200,
    headers: init.headers || {},
    clone() { return makeResp(body, init); },
    async text() { return body; },
  });

  const cacheObj = {
    async add(p) {
      if (net.offline || net.fail.has(p)) throw new Error('add a échoué : ' + p);
      store.set(p, makeResp('cached:' + p));
    },
    async put(p, resp) { store.set(p, resp); },
    async match(p) { return store.get(p); },
  };
  const caches = {
    async open() { return cacheObj; },
    async keys() { return ['wt-help-v1', 'wt-shell-v2', 'autre-v0']; },
    async delete(k) { deleted.push(k); return true; },
    async match(p) { return store.get(p); },
  };

  const self = {
    location: { origin: 'http://kiosk.local' },
    addEventListener(type, fn) { listeners[type] = fn; },
    skipWaiting() {},
    clients: { claim() {} },
  };
  const fetchImpl = async req => {
    if (net.offline) throw new Error('réseau coupé');
    return makeResp('fresh:' + ((req && req.url) || req));
  };
  function Response(body, init) { return makeResp(body, init); }

  const sandbox = { self, caches, fetch: fetchImpl, Response, URL, console };
  vm.createContext(sandbox);
  vm.runInContext(SW_SRC, sandbox);
  return { listeners, store, deleted, net, makeResp };
}

// Déclenche un événement extensible (install/activate) et attend ses waitUntil.
async function fireLifecycle(fn) {
  const promises = [];
  fn({ waitUntil(p) { promises.push(p); } });
  await Promise.all(promises);
}

// Déclenche un fetch ; renvoie la réponse, ou {passthrough:true} si non intercepté.
async function doFetch(listeners, url, method = 'GET') {
  let responded = null;
  listeners.fetch({ request: { url, method }, respondWith(p) { responded = p; } });
  return responded ? await responded : { passthrough: true };
}

test('install : met /support et /app en cache', async () => {
  const { listeners, store } = loadSW();
  await fireLifecycle(listeners.install);
  assert.ok(store.has('/support'), '/support doit être en cache');
  assert.ok(store.has('/app'), '/app doit être en cache');
});

test('install : un add qui échoue ne bloque pas l\'autre', async () => {
  const { listeners, store, net } = loadSW();
  net.fail.add('/app');                      // la coquille échoue…
  await fireLifecycle(listeners.install);
  assert.ok(store.has('/support'), '…mais /support est quand même caché');
  assert.ok(!store.has('/app'));
});

test('activate : purge les caches d\'une autre version', async () => {
  const { listeners, deleted } = loadSW();
  await fireLifecycle(listeners.activate);
  assert.deepStrictEqual(deleted.sort(), ['autre-v0', 'wt-help-v1']);
  assert.ok(!deleted.includes('wt-shell-v2'), 'le cache courant est conservé');
});

test('fetch /app en ligne : sert le réseau et rafraîchit le cache', async () => {
  const { listeners, store } = loadSW();
  const r = await doFetch(listeners, 'http://kiosk.local/app');
  assert.match(r._body, /^fresh:/);
  await flush();                             // le put() est fire-and-forget
  assert.ok(store.has('/app'), 'la copie hors-ligne est rafraîchie au passage');
});

test('fetch /app hors-ligne : sert la coquille en cache', async () => {
  const { listeners, store, net, makeResp } = loadSW();
  store.set('/app', makeResp('coquille-en-cache'));
  net.offline = true;
  const r = await doFetch(listeners, 'http://kiosk.local/app');
  assert.strictEqual(r._body, 'coquille-en-cache');
});

test('fetch /app?token=… : routé malgré la query (clé normalisée sur le chemin)', async () => {
  const { listeners, store, net, makeResp } = loadSW();
  store.set('/app', makeResp('coquille-en-cache'));
  net.offline = true;
  const r = await doFetch(listeners, 'http://kiosk.local/app?token=abc123');
  assert.strictEqual(r._body, 'coquille-en-cache');
});

test('fetch /app hors-ligne sans cache : page de repli on-brand (503)', async () => {
  const { listeners, net } = loadSW();
  net.offline = true;
  const r = await doFetch(listeners, 'http://kiosk.local/app');
  assert.strictEqual(r.status, 503);
  assert.match(r._body, /Serveur injoignable/);
  assert.match(r._body, /\/support/);        // le repli pointe vers le Centre d'aide
});

test('fetch /support et /aide hors-ligne : repli Centre d\'aide', async () => {
  const { listeners, net } = loadSW();
  net.offline = true;
  const r1 = await doFetch(listeners, 'http://kiosk.local/support');
  const r2 = await doFetch(listeners, 'http://kiosk.local/aide');
  for (const r of [r1, r2]) {
    assert.strictEqual(r.status, 503);
    assert.match(r._body, /Centre d'aide indisponible/);
  }
});

test('fetch d\'un autre chemin : laissé au réseau (pas intercepté)', async () => {
  const { listeners } = loadSW();
  const r = await doFetch(listeners, 'http://kiosk.local/info');
  assert.deepStrictEqual(r, { passthrough: true });
});

test('requête non-GET : laissée au réseau', async () => {
  const { listeners } = loadSW();
  const r = await doFetch(listeners, 'http://kiosk.local/app', 'POST');
  assert.deepStrictEqual(r, { passthrough: true });
});

test('requête cross-origin : laissée au réseau', async () => {
  const { listeners } = loadSW();
  const r = await doFetch(listeners, 'http://evil.test/app');
  assert.deepStrictEqual(r, { passthrough: true });
});
