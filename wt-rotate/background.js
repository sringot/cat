const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabId: null, windowId: null
};

const MAX_LOGS = 60;

// ── Listeners (tous synchrones au top-level) ──────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
  const data = await chrome.storage.local.get('config');
  if (!data.config) await chrome.storage.local.set({ config: DEFAULT_CONFIG });
  await log('onInstalled — extension initialisée');
});

chrome.runtime.onStartup.addListener(async () => {
  await log('onStartup');
  const data = await chrome.storage.local.get('config');
  if (data.config?.active) {
    await log('onStartup — rotation active, relance alarme');
    setAlarm(data.config.interval);
  }
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  await log('alarm fired: ' + alarm.name);
  if (alarm.name === 'wt-rotate') await rotateToNext();
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const data = await chrome.storage.local.get('config');
  const config = data.config;
  if (config?.tabId === tabId) {
    await log('onglet de rotation fermé — arrêt');
    config.active = false;
    config.tabId = null;
    config.windowId = null;
    chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config });
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg.action === 'startTimer') {
    log('startTimer reçu, interval=' + msg.interval);
    setAlarm(msg.interval);
    reply({ success: true });
    return false;
  }
  if (msg.action === 'stopTimer') {
    log('stopTimer reçu');
    chrome.alarms.clear('wt-rotate');
    reply({ success: true });
    return false;
  }
  if (msg.action === 'getLogs') {
    chrome.storage.local.get('debugLogs').then(d => {
      reply({ logs: d.debugLogs || [] });
    });
    return true;
  }
  reply({ success: false, error: 'action inconnue' });
  return false;
});

// ── Alarme ────────────────────────────────────────────────────────────────

function setAlarm(interval) {
  const mins = Math.max(interval / 60, 0.1667); // min ~10s
  chrome.alarms.clear('wt-rotate', () => {
    chrome.alarms.create('wt-rotate', { delayInMinutes: mins, periodInMinutes: mins });
    log('alarme créée: délai=' + mins.toFixed(2) + 'min');
  });
}

// ── Rotation ──────────────────────────────────────────────────────────────

async function rotateToNext() {
  const data = await chrome.storage.local.get('config');
  const config = data.config || DEFAULT_CONFIG;

  if (!config.active) { await log('rotateToNext — inactif, abandon'); return; }
  if (!config.tabId)  { await log('rotateToNext — tabId null, abandon'); return; }

  const activeUrls = config.urls.filter(u => u?.trim());
  if (activeUrls.length < 2) {
    await log('rotateToNext — moins de 2 URLs (' + activeUrls.length + '), abandon');
    return;
  }

  const next = (config.currentIndex + 1) % activeUrls.length;
  const url  = activeUrls[next];
  await log(`rotateToNext — ${config.currentIndex} → ${next} : ${url}`);

  try {
    await chrome.tabs.update(config.tabId, { url });
    config.currentIndex = next;
    await chrome.storage.local.set({ config });
    await log('rotation OK');
  } catch (err) {
    await log('chrome.tabs.update ERREUR: ' + err.message);
    config.active = false;
    config.tabId = null;
    config.windowId = null;
    chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config });
  }
}

// ── Log ───────────────────────────────────────────────────────────────────

async function log(msg) {
  try {
    const now = new Date().toLocaleTimeString('fr-FR');
    const entry = `[${now}] ${msg}`;
    const data = await chrome.storage.local.get('debugLogs');
    const logs = data.debugLogs || [];
    logs.push(entry);
    if (logs.length > MAX_LOGS) logs.splice(0, logs.length - MAX_LOGS);
    await chrome.storage.local.set({ debugLogs: logs });
  } catch {}
}
