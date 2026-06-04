const DEFAULT_CONFIG = {
  urls: [],
  interval: 30,
  currentIndex: 0,
  active: false,
  tabIds: [],
  windowId: null
};

// Top-level listeners required by MV3 service worker
chrome.runtime.onInstalled.addListener(onInstalled);
chrome.runtime.onStartup.addListener(onStartup);
chrome.tabs.onRemoved.addListener(onTabRemoved);
chrome.runtime.onMessage.addListener(onMessage);
chrome.alarms.onAlarm.addListener(onAlarm);

async function onInstalled() {
  const data = await chrome.storage.local.get('config');
  if (!data.config) {
    await chrome.storage.local.set({ config: DEFAULT_CONFIG });
  }
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
}

async function onStartup() {
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
  const data = await chrome.storage.local.get('config');
  if (data.config?.active) await startTimer(data.config.interval);
}

async function onAlarm(alarm) {
  if (alarm.name === 'wt-watchdog') {
    const data = await chrome.storage.local.get('config');
    if (data.config?.active) await startTimer(data.config.interval);
  } else if (alarm.name === 'wt-rotate') {
    // Alarm fallback for Edge versions that don't support offscreen API
    await rotateToNext();
  }
}

async function onTabRemoved(tabId) {
  const data = await chrome.storage.local.get('config');
  const config = data.config;
  if (config?.tabIds?.includes(tabId)) {
    config.active = false;
    config.tabIds = [];
    config.windowId = null;
    await stopTimer();
    await chrome.storage.local.set({ config });
  }
}

function onMessage(message, sender, sendResponse) {
  if (message.action === 'rotate' && message.source === 'offscreen') {
    rotateToNext();
    return false;
  }
  handleMessage(message)
    .then(sendResponse)
    .catch(err => sendResponse({ success: false, error: err.message }));
  return true;
}

// ── Timer — offscreen preferred, alarm API as fallback ──────────────────────

async function startTimer(interval) {
  if (typeof chrome.offscreen !== 'undefined') {
    try {
      const contexts = await chrome.runtime.getContexts({
        contextTypes: ['OFFSCREEN_DOCUMENT']
      });
      if (contexts.length === 0) {
        await chrome.offscreen.createDocument({
          url: 'offscreen.html',
          reasons: ['BLOBS'],
          justification: 'Interval timer for URL rotation'
        });
      }
      chrome.runtime.sendMessage({
        target: 'offscreen',
        action: 'start-timer',
        interval
      }).catch(() => {});
      return;
    } catch (e) {
      console.warn('[wt-rotate] offscreen unavailable, using alarms:', e);
    }
  }
  // Alarm fallback (30s minimum for packed extensions, ~1 min for unpacked)
  chrome.alarms.clear('wt-rotate');
  chrome.alarms.create('wt-rotate', {
    periodInMinutes: Math.max(interval / 60, 0.5)
  });
}

async function stopTimer() {
  chrome.alarms.clear('wt-rotate');
  if (typeof chrome.offscreen === 'undefined') return;
  try {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT']
    });
    if (contexts.length > 0) {
      chrome.runtime.sendMessage({ target: 'offscreen', action: 'stop-timer' }).catch(() => {});
      await chrome.offscreen.closeDocument();
    }
  } catch (e) {}
}

// ── Rotation — switches active tab, does NOT navigate ──────────────────────

async function rotateToNext() {
  const data = await chrome.storage.local.get('config');
  const config = data.config || DEFAULT_CONFIG;
  if (!config.active || !config.tabIds?.length) return;

  const nextIndex = (config.currentIndex + 1) % config.tabIds.length;

  try {
    await chrome.tabs.update(config.tabIds[nextIndex], { active: true });
    config.currentIndex = nextIndex;
    await chrome.storage.local.set({ config });
  } catch {
    // A rotation tab was closed externally
    config.active = false;
    config.tabIds = [];
    config.windowId = null;
    await stopTimer();
    await chrome.storage.local.set({ config });
  }
}

// ── Message handler ─────────────────────────────────────────────────────────

async function handleMessage(message) {
  const data = await chrome.storage.local.get('config');
  let config = data.config || { ...DEFAULT_CONFIG };

  switch (message.action) {

    case 'start': {
      const activeUrls = config.urls.filter(u => u?.trim());
      if (activeUrls.length === 0) {
        return { success: false, error: 'Aucune URL configurée' };
      }

      // Check if the rotation window still exists
      let winExists = false;
      if (config.windowId) {
        try { await chrome.windows.get(config.windowId); winExists = true; } catch {}
      }

      if (!winExists) {
        // Open first URL in a new window
        const win = await chrome.windows.create({
          url: activeUrls[0],
          state: message.fullscreen ? 'fullscreen' : 'maximized'
        });
        const tabIds = [win.tabs[0].id];

        // Open remaining URLs as additional tabs in the same window
        for (let i = 1; i < activeUrls.length; i++) {
          const tab = await chrome.tabs.create({
            windowId: win.id,
            url: activeUrls[i],
            active: false   // don't steal focus while opening
          });
          tabIds.push(tab.id);
        }

        config.tabIds = tabIds;
        config.windowId = win.id;
      } else {
        // Window already open — reuse existing tabs
        if (config.tabIds?.length > 0) {
          try { await chrome.tabs.update(config.tabIds[0], { active: true }); } catch {}
        }
        if (message.fullscreen) {
          await chrome.windows.update(config.windowId, { state: 'fullscreen' });
        }
      }

      config.currentIndex = 0;
      config.active = true;
      await chrome.storage.local.set({ config });
      await startTimer(config.interval);
      return { success: true };
    }

    case 'stop': {
      config.active = false;
      await chrome.storage.local.set({ config });
      await stopTimer();
      return { success: true };
    }

    case 'next': {
      await rotateToNext();
      const fresh = await chrome.storage.local.get('config');
      return { success: true, config: fresh.config };
    }

    case 'getConfig':
      return { config };

    default:
      return { success: false, error: 'Action inconnue' };
  }
}
