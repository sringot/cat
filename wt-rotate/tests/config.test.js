// Tests de la logique pure du service worker (bg/config.js).
// Lancés avec le runner natif : `node --test tests/`
const test = require('node:test');
const assert = require('node:assert');
const { DEFAULT_CONFIG, migrateConfig, isInSchedule } = require('../bg/config.js');

test('migrateConfig(null) renvoie une config par défaut saine', () => {
  const c = migrateConfig(null);
  assert.deepStrictEqual(c.urls, []);
  assert.deepStrictEqual(c.tabIds, []);
  assert.deepStrictEqual(c.scheduleDays, [1, 2, 3, 4, 5]);
});

test('migrateConfig convertit les URLs string en objets', () => {
  const c = migrateConfig({ urls: ['https://a.test'] });
  assert.deepStrictEqual(c.urls[0], { url: 'https://a.test', name: '', interval: null });
});

test('migrateConfig isole les tableaux de DEFAULT_CONFIG (copie profonde)', () => {
  const c = migrateConfig(null);
  c.urls.push({ url: 'x' });
  c.tabIds.push(42);
  c.scheduleDays.push(9);
  // DEFAULT_CONFIG ne doit jamais être pollué par une mutation du résultat
  assert.strictEqual(DEFAULT_CONFIG.urls.length, 0);
  assert.strictEqual(DEFAULT_CONFIG.tabIds.length, 0);
  assert.deepStrictEqual(DEFAULT_CONFIG.scheduleDays, [1, 2, 3, 4, 5]);
  // Et deux appels successifs sont indépendants
  assert.strictEqual(migrateConfig(null).urls.length, 0);
});

test('migrateConfig migre l\'ancien champ tabId → tabIds', () => {
  const c = migrateConfig({ tabId: 7 });
  assert.deepStrictEqual(c.tabIds, [7]);
  assert.strictEqual(c.tabId, undefined);
});

test('migrateConfig ignore tabId si tabIds déjà présent', () => {
  const c = migrateConfig({ tabId: 7, tabIds: [1, 2] });
  assert.deepStrictEqual(c.tabIds, [1, 2]);
});

test('migrateConfig répare un scheduleDays non-tableau', () => {
  const c = migrateConfig({ scheduleDays: 'lundi' });
  assert.deepStrictEqual(c.scheduleDays, [1, 2, 3, 4, 5]);
});

test('isInSchedule: désactivé → toujours vrai', () => {
  assert.strictEqual(isInSchedule({ scheduleEnabled: false }), true);
});

test('isInSchedule: fenêtre pleine journée, jour courant → vrai', () => {
  const today = new Date().getDay();
  assert.strictEqual(isInSchedule({
    scheduleEnabled: true, scheduleDays: [today],
    scheduleStart: '00:00', scheduleEnd: '24:00',
  }), true);
});

test('isInSchedule: fin <= début (fenêtre nulle) → faux', () => {
  const today = new Date().getDay();
  assert.strictEqual(isInSchedule({
    scheduleEnabled: true, scheduleDays: [today],
    scheduleStart: '00:00', scheduleEnd: '00:00',
  }), false);
});

test('isInSchedule: mauvais jour → faux', () => {
  const wrongDay = (new Date().getDay() + 1) % 7;
  assert.strictEqual(isInSchedule({
    scheduleEnabled: true, scheduleDays: [wrongDay],
    scheduleStart: '00:00', scheduleEnd: '24:00',
  }), false);
});
