// Tests de la décision de resynchronisation des onglets (bg/tabs.js).
// `needsResync` est la logique pure derrière le watchdog resyncTabsIfNeeded.
// `pruneTimes` retire les onglets disparus des maps d'horodatages (anti-fuite).
const test = require('node:test');
const assert = require('node:assert');
const { needsResync, pruneTimes } = require('../bg/tabs.js');

const base = { active: true, windowId: 10, remoteTabId: null, tabIds: [1, 2, 3], tabsDirty: false };
const three = [{ url: 'a' }, { url: 'b' }, { url: 'c' }];

test('aligné (mêmes longueurs, pas de drapeau) → pas de resync', () => {
  assert.strictEqual(needsResync(base, three), false);
});

test('rotation inactive → pas de resync', () => {
  assert.strictEqual(needsResync({ ...base, active: false }, three), false);
});

test('pas de fenêtre kiosque → pas de resync', () => {
  assert.strictEqual(needsResync({ ...base, windowId: null }, three), false);
});

test('spotlight (remoteTabId) → pas de resync', () => {
  assert.strictEqual(needsResync({ ...base, remoteTabId: 99 }, three), false);
});

test('playlist vide → pas de resync', () => {
  assert.strictEqual(needsResync(base, []), false);
});

test('longueurs différentes (ajout/suppression) → resync', () => {
  assert.strictEqual(needsResync(base, [{ url: 'a' }, { url: 'b' }]), true);
});

test('mêmes longueurs mais tabsDirty (réordonnancement / URL changée) → resync', () => {
  assert.strictEqual(needsResync({ ...base, tabsDirty: true }, three), true);
});

// ── pruneTimes : anti-fuite des maps d'horodatages ───────────────────────────

test('pruneTimes: retire les onglets disparus, garde les vivants', () => {
  // clés strings (comme en storage JSON), tabIds nombres (comme chrome.tabs)
  const times = { '1': 100, '2': 200, '999': 300 };
  assert.deepStrictEqual(pruneTimes(times, [1, 2]), { '1': 100, '2': 200 });
});

test('pruneTimes: aucun onglet valide → map vide', () => {
  assert.deepStrictEqual(pruneTimes({ '5': 1, '6': 2 }, []), {});
});

test('pruneTimes: tous valides → inchangé', () => {
  const times = { '1': 10, '2': 20, '3': 30 };
  assert.deepStrictEqual(pruneTimes(times, [1, 2, 3]), times);
});

test('pruneTimes: map vide ou absente → {}', () => {
  assert.deepStrictEqual(pruneTimes({}, [1, 2]), {});
  assert.deepStrictEqual(pruneTimes(undefined, [1, 2]), {});
});
