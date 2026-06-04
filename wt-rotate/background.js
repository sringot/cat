const DEFAULT_CONFIG = {
  urls: [],
  interval: 30,
  currentIndex: 0,
  active: false,
  tabId: null,
  windowId: null
};

// Top-level listeners required by MV3 service worker
chrome.runtime.onInstalled.addListener(onInstalled);
chrome.runtime.onStartup.addListener(onStartup);
chrome.tabs.onRemoved.addListener(onTabRemoved);
chrome.runtime.onMessage.addListener(onMessage);

async function onInstalled() {
  const data = await chrome.storage.local.get('config');
  if (!data.config) {
    await chrome.storage.local.set({ config: DEFAULT_CONFIG });
  }
  // Watchdog: recreate offscreen timer if service worker was killed
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
}

async function onStartup() {
  chrome.alarms.create('wt-watchdog', { periodInMinutes: 1 });
  const data = await chrome.storage.local.get('config');
  if (data.config?.active) {
    await ensureOffscreenTimer(data.config.interval);
  }
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== 'wt-watchdog') return;
  const data = await chrome.storage.local.get('config');
  if (data.config?.active) {
    await ensureOffscreenTimer(data.config.interval);
  }
});

async function onTabRemoved(tabId) {
  const data = await chrome.storage.local.get('config');
  const config = data.config;
  if (config?.tabId === tabId) {
    config.active = false;
    config.tabId = null;
    config.windowId = null;
    await closeOffscreenTimer();
    await chrome.storage.local.set({ config });
  }
}

function onMessage(message, sender, sendResponse) {
  // Rotation tick from offscreen document
  if (message.action === 'rotate' && message.source === 'offscreen') {
    rotateToNext();
    return false;
  }
  handleMessage(message)
    .then(sendResponse)
    .catch(err => sendResponse({ success: false, error: err.message }));
  return true;
}

// ── Offscreen document management ──────────────────────────────────────────

async function ensureOffscreenTimer(interval) {
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
  } catch (e) {
    console.error('[wt-rotate] offscreen error:', e);
  }
}

async function closeOffscreenTimer() {
  try {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT']
    });
    if (contexts.length > 0) {
      chrome.runtime.sendMessage({
        target: 'offscreen',
        action: 'stop-timer'
      }).catch(() => {});
      await chrome.offscreen.closeDocument();
    }
  } catch (e) {}
}

// ── Rotation logic ──────────────────────────────────────────────────────────

async function rotateToNext() {
  const data = await chrome.storage.local.get('config');
  const config = data.config || DEFAULT_CONFIG;
  if (!config.active) return;

  const activeUrls = config.urls.filter(u => u?.trim());
  if (activeUrls.length === 0) return;

  const nextIndex = (config.currentIndex + 1) % activeUrls.length;

  try {
    await chrome.tabs.update(config.tabId, { url: activeUrls[nextIndex] });
    config.currentIndex = nextIndex;
    await chrome.storage.local.set({ config });
  } catch {
    config.active = false;
    config.tabId = null;
    config.windowId = null;
    await closeOffscreenTimer();
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

      let tabExists = false;
      if (config.tabId) {
        try { await chrome.tabs.get(config.tabId); tabExists = true; } catch {}
      }

      if (!tabExists) {
        const win = await chrome.windows.create({
          url: activeUrls[0],
          state: message.fullscreen ? 'fullscreen' : 'maximized'
        });
        config.tabId = win.tabs[0].id;
        config.windowId = win.id;
      } else {
        await chrome.tabs.update(config.tabId, { url: activeUrls[0], active: true });
        if (message.fullscreen && config.windowId) {
          await chrome.windows.update(config.windowId, { state: 'fullscreen' });
        }
      }

      config.currentIndex = 0;
      config.active = true;
      await chrome.storage.local.set({ config });
      await ensureOffscreenTimer(config.interval);
      return { success: true };
    }

    case 'stop': {
      config.active = false;
      await chrome.storage.local.set({ config });
      await closeOffscreenTimer();
      return { success: true };
    }

    case 'next': {
      await rotateToNext();
      const fresh = await chrome.storage.local.get('config');
      return { success: true, config: fresh.config };
    }

    case 'getConfig':
      return { config };

    case 'setConfig': {
      const prevInterval = config.interval;
      config = { ...config, ...message.config };
      await chrome.storage.local.set({ config });
      if (config.active && message.config.interval && message.config.interval !== prevInterval) {
        await ensureOffscreenTimer(config.interval);
      }
      return { success: true };
    }

    default:
      return { success: false, error: 'Action inconnue' };
  }
}
