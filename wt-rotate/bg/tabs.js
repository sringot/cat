function setNextAlarm(interval) {
  return new Promise(resolve => {
    const mins = Math.max(interval / 60, 0.1667);
    chrome.alarms.clear('wt-rotate', () => {
      chrome.alarms.create('wt-rotate', { delayInMinutes: mins });
      resolve();
    });
  });
}

async function rotateToNext() {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (!config.active)        { await log('inactif — abandon'); return; }
  if (!config.tabIds.length) { await log('tabIds vide — abandon'); return; }
  if (config.remotePaused)   { await log('remote pause — abandon'); return; }
  if (config.scheduleEnabled && !isInSchedule(config)) {
    await log('hors plage — arrêt');
    config.active = false; chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config }); await sendStateToRemote(); return;
  }
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  if (activeUrls.length < 2) { await log('moins de 2 URLs — abandon'); return; }
  const next = (config.currentIndex + 1) % activeUrls.length;
  if (next >= config.tabIds.length) {
    await log('tabIds désynchronisé — arrêt');
    config.active = false; config.tabIds = []; config.windowId = null;
    chrome.alarms.clear('wt-rotate'); await chrome.storage.local.set({ config }); return;
  }
  const entry = activeUrls[next];
  const interval = entry.interval || config.interval;
  try {
    await chrome.tabs.update(config.tabIds[next], { active: true });
    config.currentIndex = next; config.lastAlarmTime = Date.now();
    config.currentAlarmSec = interval;
    await chrome.storage.local.set({ config });
    await setNextAlarm(interval);
    await log('OK → ' + (entry.name || entry.url.slice(0, 50)));
    await sendStateToRemote();
  } catch (err) {
    await log('tabs.update ERR: ' + err.message);
    config.active = false; config.tabIds = []; config.windowId = null;
    chrome.alarms.clear('wt-rotate'); await chrome.storage.local.set({ config });
  }
}

async function checkSchedule() {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (!config.scheduleEnabled) return;
  const wasIn = config.lastScheduleState ?? false;
  const nowIn = isInSchedule(config);
  config.lastScheduleState = nowIn;
  if (nowIn && !wasIn) {
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    if (activeUrls.length > 0 && !config.active) {
      await autoStartRotation(config);
      await log('schedule — démarrage auto');
      return;
    }
  } else if (!nowIn && wasIn && config.active) {
    config.active = false;
    chrome.alarms.clear('wt-rotate');
    await chrome.storage.local.set({ config });
    await log('schedule — arrêt auto');
    await sendStateToRemote();
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
      config.tabIds = [win.tabs[0].id]; config.windowId = win.id;
      for (let i = 1; i < activeUrls.length; i++) {
        const tab = await chrome.tabs.create({ windowId: win.id, url: activeUrls[i].url, active: false });
        config.tabIds.push(tab.id);
      }
    } else {
      for (const tid of config.tabIds) { try { await chrome.tabs.remove(tid); } catch {} }
      config.tabIds = [];
      for (let i = 0; i < activeUrls.length; i++) {
        const tab = await chrome.tabs.create({ windowId: config.windowId, url: activeUrls[i].url, active: i === 0 });
        config.tabIds.push(tab.id);
      }
      await chrome.windows.update(config.windowId, { state: 'fullscreen' });
    }
    config.currentIndex = 0; config.active = true; config.remotePaused = false;
    config.lastAlarmTime = Date.now();
    config.currentAlarmSec = activeUrls[0].interval || config.interval;
    await chrome.storage.local.set({ config });
    await setNextAlarm(config.currentAlarmSec);
    await sendStateToRemote();
  } catch (e) {
    await log('autoStart ERR: ' + e.message);
    await chrome.storage.local.set({ config });
  }
}

// ── Auto-refresh des onglets kiosque (sessions expirantes type WithSecure) ─────

async function refreshStaleTabsIfNeeded() {
  const data = await chrome.storage.local.get(['config', 'tabRefreshTimes']);
  const config = migrateConfig(data.config);
  if (!config.active || !config.tabIds.length) return;
  const hours = config.tabRefreshHours ?? 4;
  if (hours <= 0) return;
  const intervalMs = hours * 3600 * 1000;
  const times = data.tabRefreshTimes || {};
  const now = Date.now();
  let changed = false;
  for (let i = 0; i < config.tabIds.length; i++) {
    const tabId = config.tabIds[i];
    // Re-read currentIndex before each reload to avoid reloading a tab that just became active
    const fresh = await chrome.storage.local.get('config');
    if (i === migrateConfig(fresh.config).currentIndex) continue;
    if (!(tabId in times)) {
      // First time we see this tab — seed the clock so it isn't reloaded immediately
      times[tabId] = now;
      changed = true;
      continue;
    }
    if (now - times[tabId] >= intervalMs) {
      try {
        await chrome.tabs.reload(tabId);
        times[tabId] = now;
        changed = true;
        await log('session-refresh tab ' + tabId + ' (intervalle ' + hours + 'h)');
      } catch {}
    }
  }
  if (changed) await chrome.storage.local.set({ tabRefreshTimes: times });
}

// ── Auto-refresh des onglets Canva ────────────────────────────────────────────

async function refreshCanvaTabsIfNeeded() {
  const data = await chrome.storage.local.get(['config', 'canvaRefreshTimes']);
  const config = migrateConfig(data.config);
  if (!config.active || !config.tabIds.length) return;
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  const times  = data.canvaRefreshTimes || {};
  const minMs  = (config.canvaRefreshMin || 5) * 60 * 1000;
  const now    = Date.now();
  let changed  = false;
  for (let i = 0; i < config.tabIds.length; i++) {
    if (!activeUrls[i]?.url?.includes('canva.com')) continue;
    const tabId = config.tabIds[i];
    // Re-read currentIndex to avoid reloading the active tab
    const fresh = await chrome.storage.local.get('config');
    if (i === migrateConfig(fresh.config).currentIndex) continue;
    if (!(tabId in times)) {
      times[tabId] = now;
      changed = true;
      continue;
    }
    if (now - times[tabId] >= minMs) {
      try {
        await chrome.tabs.reload(tabId);
        times[tabId] = now;
        changed = true;
        await log('canva refresh — tab ' + tabId);
      } catch {}
    }
  }
  if (changed) await chrome.storage.local.set({ canvaRefreshTimes: times });
}
