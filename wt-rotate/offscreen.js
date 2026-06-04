let timerId = null;

function tick() {
  chrome.runtime.sendMessage({ action: 'rotate', source: 'offscreen' }).catch(() => {});
}

function startMs(ms) {
  if (timerId) clearInterval(timerId);
  timerId = setInterval(tick, ms);
}

// Listener enregistré de façon synchrone AVANT toute opération async
chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== 'offscreen') return;
  if (message.action === 'start-timer') startMs(message.interval * 1000);
  if (message.action === 'stop-timer') { clearInterval(timerId); timerId = null; }
});

// Auto-démarrage : lit l'intervalle directement depuis le storage
// (fiable car le config est sauvé avant que ce document soit créé)
chrome.storage.local.get('config').then(data => {
  if (data?.config?.active && data.config.interval) {
    startMs(data.config.interval * 1000);
  }
});
