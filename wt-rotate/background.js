const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabId: null, windowId: null
};

const MAX_LOGS = 60;

function migrateConfig(raw) {
  if (!raw) return { ...DEFAULT_CONFIG };
  const c = { ...DEFAULT_CONFIG, ...raw };
  c.urls = (c.urls || []).map(u =>
    typeof u === 'string' ? { url: u, name: '', interval: null } : u
  );
  return c;
}

// ── Listeners ────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
  const data = await chrome.storage.local.get('config');
  if (!data.config) await chrome.storage.local.set({ config: DEFAULT_CONFIG });
  await log('onInstalled');
});

chrome.runtime.onStartup.addListener(async () => {
  await log('onStartup');
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (config.active) {
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    const cur = activeUrls[config.currentIndex % Math.max(activeUrls.length, 1)];
    const interval = cur?.interval || config.interval;
    await log('onStartup — relance alarme ' + interval + 's');
    await setNextAlarm(interval);
  }
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  await log('alarm: ' + alarm.name);
  if (alarm.name === 'wt-rotate') await rotateToNext();
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (config.tabId === tabId) {
    await log('onglet fermé — arrêt');
    config.active = false;
    config.tabId = null;
    config.windowId = null;
    chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config });
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg.action === 'startTimer') {
    log('startTimer interval=' + msg.interval);
    setNextAlarm(msg.interval);
    reply({ success: true });
    return false;
  }
  if (msg.action === 'stopTimer') {
    log('stopTimer');
    chrome.alarms.clear('wt-rotate');
    reply({ success: true });
    return false;
  }
  if (msg.action === 'getLogs') {
    chrome.storage.local.get('debugLogs').then(d => reply({ logs: d.debugLogs || [] }));
    return true;
  }
  reply({ success: false, error: 'action inconnue' });
  return false;
});

// ── Alarme (one-shot, recrée après chaque rotation) ───────────────────────────

function setNextAlarm(interval) {
  return new Promise(resolve => {
    const mins = Math.max(interval / 60, 0.1667);
    chrome.alarms.clear('wt-rotate', () => {
      chrome.alarms.create('wt-rotate', { delayInMinutes: mins });
      resolve();
    });
  });
}

// ── Rotation ──────────────────────────────────────────────────────────────────

async function rotateToNext() {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);

  if (!config.active) { await log('inactif — abandon'); return; }
  if (!config.tabId)  { await log('tabId null — abandon'); return; }

  const activeUrls = config.urls.filter(u => u?.url?.trim());
  if (activeUrls.length < 2) {
    await log('moins de 2 URLs — abandon');
    return;
  }

  const next  = (config.currentIndex + 1) % activeUrls.length;
  const entry = activeUrls[next];
  const interval = entry.interval || config.interval;

  try {
    await chrome.tabs.update(config.tabId, { url: entry.url });
    config.currentIndex     = next;
    config.lastAlarmTime    = Date.now();
    config.currentAlarmSec  = interval;
    await chrome.storage.local.set({ config });
    await setNextAlarm(interval);
    await log('OK → ' + (entry.name || entry.url.slice(0, 50)));
  } catch (err) {
    await log('tabs.update ERR: ' + err.message);
    config.active = false;
    config.tabId = null;
    config.windowId = null;
    chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config });
  }
}

// ── Log ───────────────────────────────────────────────────────────────────────

async function log(msg) {
  try {
    const entry = `[${new Date().toLocaleTimeString('fr-FR')}] ${msg}`;
    const data  = await chrome.storage.local.get('debugLogs');
    const logs  = data.debugLogs || [];
    logs.push(entry);
    if (logs.length > MAX_LOGS) logs.splice(0, logs.length - MAX_LOGS);
    await chrome.storage.local.set({ debugLogs: logs });
  } catch {}
}
