importScripts(
  'bg/logger.js',
  'bg/config.js',
  'bg/tabs.js',
  'bg/overlay.js',
  'bg/remote.js'
);

// ── Listeners ─────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(async () => {
  const data = await chrome.storage.local.get('config');
  if (!data.config) await chrome.storage.local.set({ config: DEFAULT_CONFIG });
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
  await log('onInstalled');
  connectRemote();
});

chrome.runtime.onStartup.addListener(async () => {
  await log('onStartup');
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (config.active) {
    let allTabsValid = config.tabIds.length > 0;
    for (const tid of config.tabIds) {
      try { await chrome.tabs.get(tid); } catch { allTabsValid = false; break; }
    }
    if (allTabsValid) {
      const activeUrls = config.urls.filter(u => u?.url?.trim());
      const cur = activeUrls[config.currentIndex % Math.max(activeUrls.length, 1)];
      await setNextAlarm(cur?.interval || config.interval);
      await log('onStartup — relance alarme');
    } else {
      config.active = false; config.tabIds = []; config.windowId = null;
      await chrome.storage.local.set({ config });
      await log('onStartup — onglets perdus, arrêt');
    }
  }
  connectRemote();
});

chrome.alarms.onAlarm.addListener(async alarm => {
  if (alarm.name === 'wt-rotate')   await rotateToNext();
  if (alarm.name === 'wt-watchdog') {
    await checkSchedule();
    connectRemote();
    await injectOverlayAll();
    await refreshCanvaTabsIfNeeded();
    await refreshStaleTabsIfNeeded();
  }
});

chrome.tabs.onRemoved.addListener(async tabId => {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (config.remoteTabId === tabId) config.remoteTabId = null;
  if (config.tabIds.includes(tabId)) {
    await log('onglet fermé — arrêt');
    config.active = false; config.tabIds = []; config.windowId = null; config.remoteTabId = null;
    chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config });
    await sendStateToRemote();
  } else {
    await chrome.storage.local.set({ config });
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (changeInfo.status !== 'complete') return;
  const data = await chrome.storage.local.get(['config', 'remoteInfo']);
  const config = migrateConfig(data.config);
  const info = data.remoteInfo;
  const isKiosk  = config.tabIds.includes(tabId);
  const isRemote = config.remoteTabId === tabId;
  if (!isKiosk && !isRemote) return;
  if (isKiosk && info?.ip) await injectOverlay(tabId, info);
  try {
    const tab = await chrome.tabs.get(tabId);
    if (/youtube\.com\/watch/.test(tab.url || '')) await injectYouTubeMaximize(tabId);
  } catch {}
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  // ── Popup actions (run in SW so popup closing doesn't interrupt them) ─────
  if (msg.action === 'startRotation') {
    (async () => {
      try {
        const data = await chrome.storage.local.get('config');
        const config = migrateConfig(data.config);
        if (!config.urls.filter(u => u?.url?.trim()).length) {
          reply({ ok: false, error: 'no_urls' }); return;
        }
        await autoStartRotation(config);
        reply({ ok: true });
      } catch (e) {
        await log('startRotation ERR: ' + e.message);
        reply({ ok: false, error: e.message });
      }
    })();
    return true;
  }
  if (msg.action === 'stopRotation') {
    (async () => {
      const data = await chrome.storage.local.get('config');
      const config = migrateConfig(data.config);
      config.active = false; config.remotePaused = false;
      chrome.alarms.clear('wt-rotate');
      await chrome.storage.local.set({ config });
      await log('popup — arrêt');
      await sendStateToRemote();
      reply({ ok: true });
    })();
    return true;
  }
  if (msg.action === 'nextUrl') {
    (async () => {
      const data = await chrome.storage.local.get('config');
      const config = migrateConfig(data.config);
      const urls = config.urls.filter(u => u?.url?.trim());
      if (!urls.length || !config.tabIds.length) { reply({ ok: false, error: 'not_running' }); return; }
      const next = (config.currentIndex + 1) % urls.length;
      if (next >= config.tabIds.length) { reply({ ok: false, error: 'sync_error' }); return; }
      try {
        await chrome.tabs.update(config.tabIds[next], { active: true });
        config.currentIndex = next; config.lastAlarmTime = Date.now();
        await chrome.storage.local.set({ config });
        if (config.active) await setNextAlarm(config.currentAlarmSec || config.interval);
        await sendStateToRemote();
        reply({ ok: true });
      } catch (e) { reply({ ok: false, error: e.message }); }
    })();
    return true;
  }
  if (msg.action === 'prevUrl') {
    (async () => {
      const data = await chrome.storage.local.get('config');
      const config = migrateConfig(data.config);
      const urls = config.urls.filter(u => u?.url?.trim());
      if (!urls.length || !config.tabIds.length) { reply({ ok: false, error: 'not_running' }); return; }
      const prev = (config.currentIndex - 1 + urls.length) % urls.length;
      if (prev >= config.tabIds.length) { reply({ ok: false, error: 'sync_error' }); return; }
      try {
        await chrome.tabs.update(config.tabIds[prev], { active: true });
        config.currentIndex = prev; config.lastAlarmTime = Date.now();
        await chrome.storage.local.set({ config });
        if (config.active) await setNextAlarm(config.currentAlarmSec || config.interval);
        await sendStateToRemote();
        reply({ ok: true });
      } catch (e) { reply({ ok: false, error: e.message }); }
    })();
    return true;
  }
  // ── Legacy timer messages ─────────────────────────────────────────────────
  if (msg.action === 'startTimer') {
    log('startTimer interval=' + msg.interval);
    setNextAlarm(msg.interval);
    sendStateToRemote();
    reply({ success: true });
    return false;
  }
  if (msg.action === 'stopTimer') {
    log('stopTimer');
    chrome.alarms.clear('wt-rotate');
    sendStateToRemote();
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

connectRemote();

// Empêche Chrome de tuer le service worker entre les alarmes (astuce MV3)
try {
  navigator.locks.request('wt-rotate-sw-alive', { mode: 'exclusive' }, () => new Promise(() => {}));
} catch {}
