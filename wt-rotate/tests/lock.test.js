// Tests de la file d'exécution exclusive (bg/lock.js) : la sérialisation des
// gestionnaires d'événements évite les « lost update » sur chrome.storage.
const test = require('node:test');
const assert = require('node:assert');
const { runExclusive } = require('../bg/lock.js');

const sleep = ms => new Promise(r => setTimeout(r, ms));

test('runExclusive: sérialise — B ne démarre qu\'après la fin de A', async () => {
  const events = [];
  const task = id => async () => {
    events.push('start' + id);
    await sleep(15);
    events.push('end' + id);
  };
  // Lancées « en même temps » : sans verrou, A et B s'entrelaceraient
  // (startA, startB, endA, endB). Avec le verrou, A finit avant que B démarre.
  const a = runExclusive(task('A'));
  const b = runExclusive(task('B'));
  await Promise.all([a, b]);
  assert.deepStrictEqual(events, ['startA', 'endA', 'startB', 'endB']);
});

test('runExclusive: une tâche qui échoue ne bloque pas la file', async () => {
  const a = runExclusive(async () => { throw new Error('boom'); });
  await assert.rejects(a, /boom/);              // l'erreur remonte à l'appelant…
  const done = [];
  await runExclusive(async () => { done.push('suivante'); });
  assert.deepStrictEqual(done, ['suivante']);   // …et la suivante tourne quand même
});

test('runExclusive: renvoie la valeur de la tâche', async () => {
  assert.strictEqual(await runExclusive(async () => 42), 42);
});

test('runExclusive: respecte l\'ordre d\'arrivée (FIFO)', async () => {
  const order = [];
  const ps = [];
  for (const id of [1, 2, 3, 4]) {
    ps.push(runExclusive(async () => { await sleep(5); order.push(id); }));
  }
  await Promise.all(ps);
  assert.deepStrictEqual(order, [1, 2, 3, 4]);
});
