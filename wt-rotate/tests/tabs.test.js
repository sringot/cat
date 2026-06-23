// Tests de la décision de resynchronisation des onglets (bg/tabs.js).
// `needsResync` est la logique pure derrière le watchdog resyncTabsIfNeeded.
const test = require('node:test');
const assert = require('node:assert');
const { needsResync } = require('../bg/tabs.js');

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
