const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabId: null, windowId: null,
  scheduleEnabled: false, scheduleStart: '08:00', scheduleEnd: '18:00',
  scheduleDays: [1, 2, 3, 4, 5], lastScheduleState: false
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

function isInSchedule(config) {
  if (!config.scheduleEnabled) return true;
  const now = new Date();
  const day = now.getDay();
  if (!(config.scheduleDays || []).includes(day)) return false;
  const cur = now.getHours() * 60 + now.getMinutes();
  const [sh, sm] = (config.scheduleStart || '08:00').split(':').map(Number);
  const [eh, em] = (config.scheduleEnd   || '18:00').split(':').map(Number);
  return cur >= sh * 60 + sm && cur < eh * 60 + em;
}

// ── Listeners ─────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
  const data = await chrome.storage.local.get('config');
  if (!data.config) await chrome.storage.local.set({ config: DEFAULT_CONFIG });
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
  await log('onInstalled');
});

chrome.runtime.onStartup.addListener(async () => {
  await log('onStartup');
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (config.active) {
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    const cur = activeUrls[config.currentIndex % Math.max(activeUrls.length, 1)];
    await setNextAlarm(cur?.interval || config.interval);
    await log('onStartup — relance alarme');
  }
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'wt-rotate')   await rotateToNext();
  if (alarm.name === 'wt-watchdog') await checkSchedule();
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

// ── Schedule ──────────────────────────────────────────────────────────────────

async function checkSchedule() {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (!config.scheduleEnabled) return;

  const wasIn = config.lastScheduleState ?? false;
  const nowIn = isInSchedule(config);
  config.lastScheduleState = nowIn;

  if (nowIn && !wasIn) {
    // Vient d'entrer dans la plage → démarrage auto
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    if (activeUrls.length > 0 && !config.active) {
      await autoStartRotation(config);
      await log('schedule — démarrage auto');
      return;
    }
  } else if (!nowIn && wasIn && config.active) {
    // Vient de sortir de la plage → arrêt auto
    config.active = false;
    chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config });
    await log('schedule — arrêt auto');
    return;
  }

  await chrome.storage.local.set({ config });
}

async function autoStartRotation(config) {
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  let winExists = false;
  if (config.windowId) {
    try { await chrome.windows.get(config.windowId); winExists = true; } catch {}
  }
  try {
    if (!winExists) {
      const win = await chrome.windows.create({ url: activeUrls[0].url, state: 'fullscreen' });
      config.tabId    = win.tabs[0].id;
      config.windowId = win.id;
    } else {
      if (config.tabId) {
        try { await chrome.tabs.update(config.tabId, { url: activeUrls[0].url }); } catch {}
      }
      await chrome.windows.update(config.windowId, { state: 'fullscreen' });
    }
    config.currentIndex    = 0;
    config.active          = true;
    config.lastAlarmTime   = Date.now();
    config.currentAlarmSec = activeUrls[0].interval || config.interval;
    await chrome.storage.local.set({ config });
    await setNextAlarm(config.currentAlarmSec);
  } catch (e) {
    await log('autoStart ERR: ' + e.message);
    await chrome.storage.local.set({ config });
  }
}

// ── Alarme (one-shot) ─────────────────────────────────────────────────────────

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

  if (config.scheduleEnabled && !isInSchedule(config)) {
    await log('hors plage horaire — arrêt');
    config.active = false;
    chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config });
    return;
  }

  const activeUrls = config.urls.filter(u => u?.url?.trim());
  if (activeUrls.length < 2) { await log('moins de 2 URLs — abandon'); return; }

  const next     = (config.currentIndex + 1) % activeUrls.length;
  const entry    = activeUrls[next];
  const interval = entry.interval || config.interval;

  try {
    await chrome.tabs.update(config.tabId, { url: entry.url });
    config.currentIndex    = next;
    config.lastAlarmTime   = Date.now();
    config.currentAlarmSec = interval;
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
