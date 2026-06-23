// Tests de la logique pure du module remote (bg/remote.js).
//  - activeIndices : traduit les index de la liste FILTRÉE (vue mobile) vers
//    les index réels de config.urls — toute erreur ici édite la mauvaise page.
//  - transformUrl  : normalise les URLs YouTube avant ouverture en spotlight.
const test = require('node:test');
const assert = require('node:assert');
const { activeIndices, transformUrl } = require('../bg/remote.js');

test('activeIndices: ignore les entrées vides ou blanches', () => {
  const config = { urls: [
    { url: 'https://a.test' },  // 0 ✓
    { url: '   ' },             // 1 ✗ (blanc)
    { url: 'https://b.test' },  // 2 ✓
    { url: '' },                // 3 ✗ (vide)
    {},                         // 4 ✗ (pas d'url)
    { url: 'https://c.test' },  // 5 ✓
  ] };
  assert.deepStrictEqual(activeIndices(config), [0, 2, 5]);
});

test('activeIndices: toutes valides → identité', () => {
  const config = { urls: [{ url: 'a' }, { url: 'b' }, { url: 'c' }] };
  assert.deepStrictEqual(activeIndices(config), [0, 1, 2]);
});

test('activeIndices: liste vide → []', () => {
  assert.deepStrictEqual(activeIndices({ urls: [] }), []);
});

test('transformUrl: youtu.be → watch', () => {
  assert.strictEqual(transformUrl('https://youtu.be/abc123'),
    'https://www.youtube.com/watch?v=abc123');
});

test('transformUrl: m.youtube /watch → www /watch', () => {
  assert.strictEqual(transformUrl('https://m.youtube.com/watch?v=xyz789'),
    'https://www.youtube.com/watch?v=xyz789');
});

test('transformUrl: /shorts/ → watch', () => {
  assert.strictEqual(transformUrl('https://www.youtube.com/shorts/SHORT01'),
    'https://www.youtube.com/watch?v=SHORT01');
});

test('transformUrl: /embed/ → watch', () => {
  assert.strictEqual(transformUrl('https://www.youtube.com/embed/EMB01'),
    'https://www.youtube.com/watch?v=EMB01');
});

test('transformUrl: URL non-YouTube inchangée', () => {
  assert.strictEqual(transformUrl('https://example.com/page?x=1'),
    'https://example.com/page?x=1');
});

test('transformUrl: chaîne non-URL renvoyée telle quelle', () => {
  assert.strictEqual(transformUrl('pas une url'), 'pas une url');
});
