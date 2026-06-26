// File d'exécution mutuellement exclusive pour les sections qui
// lisent-modifient-écrivent chrome.storage.local (config).
//
// Le service worker MV3 est mono-thread mais coopératif : deux gestionnaires
// (alarme wt-rotate vs watchdog, commande téléphone, message popup…) qui
// s'entrelacent sur leurs `await` peuvent relire une config périmée et écraser
// la mutation de l'autre — « lost update ». Conséquences observées : rotation
// stoppée si rotateToNext réécrit d'anciens tabIds par-dessus une resync en
// cours, horodatages de rafraîchissement perdus, etc.
//
// runExclusive sérialise ces gestionnaires : un seul s'exécute de bout en bout,
// le suivant attend la fin du précédent. Comme tout est mono-thread, c'est une
// simple file de promesses — aucun vrai verrou OS.
//
// À n'utiliser QU'AUX FRONTIÈRES d'événements (onAlarm, onStartup, onMessage,
// onRemoved, commande WebSocket). Les fonctions internes (rotateToNext,
// autoStartRotation, checkSchedule, resumeRotation…) ne doivent PAS l'acquérir
// elles-mêmes : une frontière en appelle souvent une autre, et une ré-entrance
// sur la même file se bloquerait elle-même (interblocage).
let _exclusiveChain = Promise.resolve();

function runExclusive(fn) {
  // On enchaîne sur la file courante (toujours « apaisée » : voir plus bas),
  // donc fn part dès que la tâche précédente est terminée.
  const run = _exclusiveChain.then(() => fn());
  // La file ne doit jamais rester en rejet, sinon une tâche qui throw bloquerait
  // toutes les suivantes. On la remplace par une version neutralisée ; l'erreur
  // reste visible pour l'appelant via la promesse `run` renvoyée.
  _exclusiveChain = run.then(() => {}, () => {});
  return run;
}

// Export pour les tests Node (`module` est undefined dans le service worker
// MV3 : ce bloc y est ignoré et n'affecte pas le runtime de l'extension).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { runExclusive };
}
