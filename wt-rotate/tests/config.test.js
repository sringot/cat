// Tests de la logique pure du service worker (bg/config.js).
// Lancés avec le runner natif : `node --test tests/`
const test = require('node:test');
const assert = require('node:assert');
const {
  DEFAULT_CONFIG, migrateConfig, isInSchedule,
  nextIndex, prevIndex, isValidIndex,
  ROTATE_FLOOR_SEC, clampInterval,
} = require('../bg/config.js');

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

// ── Plancher d'intervalle (chrome.alarms : 30 s mini sur extension installée) ─

test('ROTATE_FLOOR_SEC vaut 30 s', () => {
  assert.strictEqual(ROTATE_FLOOR_SEC, 30);
});

test('clampInterval: borne basse à 30, 0/invalide → null', () => {
  assert.strictEqual(clampInterval(5), 30);
  assert.strictEqual(clampInterval(30), 30);
  assert.strictEqual(clampInterval(90), 90);
  assert.strictEqual(clampInterval('45'), 45);
  assert.strictEqual(clampInterval(0), null);
  assert.strictEqual(clampInterval(null), null);
  assert.strictEqual(clampInterval('abc'), null);
});

test('migrateConfig: durée par page < 30 s remontée au plancher', () => {
  const c = migrateConfig({ urls: [{ url: 'a', name: '', interval: 10 }] });
  assert.strictEqual(c.urls[0].interval, 30);
});

test('migrateConfig: durée par page nulle/absente reste null', () => {
  const c = migrateConfig({ urls: [{ url: 'a', interval: null }, { url: 'b' }] });
  assert.strictEqual(c.urls[0].interval, null);
  assert.strictEqual(c.urls[1].interval, null);
});

test('migrateConfig: durée par page >= 30 s inchangée', () => {
  assert.strictEqual(migrateConfig({ urls: [{ url: 'a', interval: 45 }] }).urls[0].interval, 45);
});

test('migrateConfig: intervalle global < 30 s remonté, défaut = 30', () => {
  assert.strictEqual(migrateConfig({ interval: 5 }).interval, 30);
  assert.strictEqual(migrateConfig({ interval: 120 }).interval, 120);
  assert.strictEqual(migrateConfig(null).interval, 30);
});

// ── Arithmétique d'index (next / prev / goto) ────────────────────────────────

test('nextIndex: avance et boucle sur la fin', () => {
  assert.strictEqual(nextIndex(0, 3), 1);
  assert.strictEqual(nextIndex(1, 3), 2);
  assert.strictEqual(nextIndex(2, 3), 0);       // wrap
  assert.strictEqual(nextIndex(0, 1), 0);       // une seule page
});

test('prevIndex: recule et boucle sur le début', () => {
  assert.strictEqual(prevIndex(2, 3), 1);
  assert.strictEqual(prevIndex(1, 3), 0);
  assert.strictEqual(prevIndex(0, 3), 2);       // wrap
  assert.strictEqual(prevIndex(0, 1), 0);
});

test('next/prevIndex: longueur 0 → 0 (pas de NaN)', () => {
  assert.strictEqual(nextIndex(0, 0), 0);
  assert.strictEqual(prevIndex(0, 0), 0);
});

test('isValidIndex: bornes et type', () => {
  assert.strictEqual(isValidIndex(0, 3), true);
  assert.strictEqual(isValidIndex(2, 3), true);
  assert.strictEqual(isValidIndex(3, 3), false);   // hors borne haute
  assert.strictEqual(isValidIndex(-1, 3), false);  // négatif
  assert.strictEqual(isValidIndex(1.5, 3), false); // non entier
  assert.strictEqual(isValidIndex('1', 3), false); // non entier (string)
  assert.strictEqual(isValidIndex(0, 0), false);   // playlist vide
});
