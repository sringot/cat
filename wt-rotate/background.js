// Background — gère uniquement le timer et la navigation entre URLs.
// 1 seul onglet qui charge chaque URL à tour de rôle.

const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabId: null, windowId: null
};

chrome.runtime.onInstalled.addListener(async () => {
  const data = await chrome.storage.local.get('config');
  if (!data.config) await chrome.storage.local.set({ config: DEFAULT_CONFIG });
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
});

chrome.runtime.onStartup.addListener(async () => {
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
  const data = await chrome.storage.local.get('config');
  if (data.config?.active) await startTimer(data.config.interval);
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'wt-watchdog') {
    const data = await chrome.storage.local.get('config');
    if (data.config?.active) await startTimer(data.config.interval);
  } else if (alarm.name === 'wt-rotate') {
    await rotateToNext();
  }
});

// Si l'onglet de rotation est fermé → on arrête
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const data = await chrome.storage.local.get('config');
  const config = data.config;
  if (config?.tabId === tabId) {
    config.active = false;
    config.tabId = null;
    config.windowId = null;
    await stopTimer();
    await chrome.storage.local.set({ config });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'rotate' && message.source === 'offscreen') {
    rotateToNext();
    return false;
  }
  if (message.action === 'startTimer') {
    startTimer(message.interval)
      .then(() => sendResponse({ success: true }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
  if (message.action === 'stopTimer') {
    stopTimer()
      .then(() => sendResponse({ success: true }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
  sendResponse({ success: false, error: 'Action inconnue' });
  return false;
});

// ── Timer ─────────────────────────────────────────────────────────────────

async function startTimer(interval) {
  if (typeof chrome.offscreen !== 'undefined') {
    try {
      const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
      if (contexts.length === 0) {
        await chrome.offscreen.createDocument({
          url: 'offscreen.html',
          reasons: ['BLOBS'],
          justification: 'Interval timer for URL rotation'
        });
        await new Promise(r => setTimeout(r, 300));
      }
      chrome.runtime.sendMessage({ target: 'offscreen', action: 'start-timer', interval }).catch(() => {});
      return;
    } catch (e) {
      console.warn('[wt-rotate] offscreen indisponible, fallback alarms');
    }
  }
  chrome.alarms.clear('wt-rotate');
  chrome.alarms.create('wt-rotate', { periodInMinutes: Math.max(interval / 60, 0.5) });
}

async function stopTimer() {
  chrome.alarms.clear('wt-rotate');
  if (typeof chrome.offscreen === 'undefined') return;
  try {
    const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
    if (contexts.length > 0) {
      chrome.runtime.sendMessage({ target: 'offscreen', action: 'stop-timer' }).catch(() => {});
      await chrome.offscreen.closeDocument();
    }
  } catch {}
}

// ── Rotation — 1 onglet, navigation par URL ───────────────────────────────

async function rotateToNext() {
  const data = await chrome.storage.local.get('config');
  const config = data.config || DEFAULT_CONFIG;

  if (!config.active || !config.tabId) return;

  const activeUrls = config.urls.filter(u => u?.trim());
  if (activeUrls.length < 2) return;

  const next = (config.currentIndex + 1) % activeUrls.length;

  try {
    // Naviguer vers la prochaine URL dans le même onglet (reload automatique)
    await chrome.tabs.update(config.tabId, { url: activeUrls[next] });
    config.currentIndex = next;
    await chrome.storage.local.set({ config });
  } catch {
    // L'onglet a été fermé
    config.active = false;
    config.tabId = null;
    config.windowId = null;
    await stopTimer();
    await chrome.storage.local.set({ config });
  }
}
