const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabIds: [], windowId: null,
  scheduleEnabled: false, scheduleStart: '08:00', scheduleEnd: '18:00',
  scheduleDays: [1, 2, 3, 4, 5], lastScheduleState: false,
  remotePaused: false, remoteTabId: null,
  canvaRefreshMin: 5,
  tabRefreshHours: 4
};

const MAX_LOGS = 60;

function migrateConfig(raw) {
  if (!raw) return { ...DEFAULT_CONFIG };
  const c = { ...DEFAULT_CONFIG, ...raw };
  c.urls = (c.urls || []).map(u =>
    typeof u === 'string' ? { url: u, name: '', interval: null } : u
  );
  if (c.tabId !== undefined) {
    if (!c.tabIds?.length && c.tabId) c.tabIds = [c.tabId];
    delete c.tabId;
  }
  if (!Array.isArray(c.tabIds)) c.tabIds = [];
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
  if (alarm.name === 'wt-watchdog') { await checkSchedule(); connectRemote(); await injectOverlayAll(); await refreshCanvaTabsIfNeeded(); await refreshStaleTabsIfNeeded(); }
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

// ── Schedule ──────────────────────────────────────────────────────────────────

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

// ── Alarm ─────────────────────────────────────────────────────────────────────

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

// ── QR Overlay injection ──────────────────────────────────────────────────────

async function injectOverlay(tabId, info) {
  const controlUrl = `http://${info.ip}:${info.http_port}/`;
  let qrSrc = null;
  try {
    const resp = await fetch(`http://localhost:${info.http_port}/qr.svg`);
    if (resp.ok) {
      const svg = await resp.text();
      qrSrc = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    }
  } catch {}
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: (qrSrc, ctrlUrl) => {
        document.getElementById('wt-qr')?.remove();
        const el = document.createElement('div');
        el.id = 'wt-qr';
        el.style.cssText = [
          'position:fixed', 'bottom:14px', 'right:14px',
          'z-index:2147483647', 'background:#fff',
          'border-radius:12px', 'padding:8px',
          'box-shadow:0 4px 20px rgba(0,0,0,.22)',
          'cursor:pointer', 'text-align:center',
          'font-family:-apple-system,sans-serif',
          'transition:opacity .2s'
        ].join('!important;') + '!important';
        el.innerHTML = qrSrc
          ? `<img src="${qrSrc}" width="86" height="86" style="display:block;border-radius:4px">
             <div style="font-size:9px;color:#555;margin-top:4px;font-weight:700;letter-spacing:.5px">📱 REMOTE</div>`
          : `<div style="font-size:9px;color:#333;padding:4px 6px;max-width:90px;word-break:break-all;font-weight:600">${ctrlUrl}</div>
             <div style="font-size:9px;color:#555;font-weight:700">📱 REMOTE</div>`;
        el.addEventListener('mouseenter', () => el.style.opacity = '.6');
        el.addEventListener('mouseleave', () => el.style.opacity = '1');
        el.addEventListener('click', () => window.open(ctrlUrl, '_blank'));
        document.body?.appendChild(el);
      },
      args: [qrSrc, controlUrl]
    });
  } catch {}
}

async function injectOverlayAll() {
  const data = await chrome.storage.local.get(['config', 'remoteInfo']);
  const config = migrateConfig(data.config);
  const info = data.remoteInfo;
  if (!info?.ip || !config.tabIds.length) return;
  for (const tabId of config.tabIds) {
    await injectOverlay(tabId, info);
  }
}

// ── Remote WebSocket client ───────────────────────────────────────────────────

let remoteWs             = null;
let remoteReconnectTimer = null;

function connectRemote() {
  if (remoteWs?.readyState === WebSocket.OPEN ||
      remoteWs?.readyState === WebSocket.CONNECTING) return;
  clearTimeout(remoteReconnectTimer);
  try { remoteWs = new WebSocket('ws://localhost:8765'); } catch { scheduleReconnect(); return; }

  remoteWs.onopen = () => remoteWs.send(JSON.stringify({ type: 'extension' }));

  remoteWs.onmessage = async evt => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'ping') {
        remoteWs.send(JSON.stringify({ type: 'pong' }));
      } else if (msg.type === 'ack') {
        await chrome.storage.local.set({
          remoteInfo: { ip: msg.ip, http_port: msg.http_port, connected: true }
        });
        await sendStateToRemote();
        await injectOverlayAll();
      } else if (msg.type === 'command') {
        await handleRemoteCommand(msg);
      }
    } catch {}
  };

  remoteWs.onclose = async () => {
    const d = await chrome.storage.local.get('remoteInfo');
    await chrome.storage.local.set({ remoteInfo: { ...(d.remoteInfo || {}), connected: false } });
    scheduleReconnect();
  };
  remoteWs.onerror = () => scheduleReconnect();
}

function scheduleReconnect() {
  clearTimeout(remoteReconnectTimer);
  remoteReconnectTimer = setTimeout(connectRemote, 500);
}

async function sendStateToRemote() {
  if (remoteWs?.readyState !== WebSocket.OPEN) return;
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  let remoteUrl = null;
  if (config.remoteTabId) {
    try { const tab = await chrome.tabs.get(config.remoteTabId); remoteUrl = tab.url || null; } catch {}
  }
  remoteWs.send(JSON.stringify({
    type: 'state', active: config.active,
    remotePaused: config.remotePaused || false,
    remoteUrl,
    currentIndex: config.currentIndex,
    urls: activeUrls.map(u => ({ name: u.name || '', url: u.url })),
    interval: config.interval
  }));
}

function transformUrl(url) {
  try {
    const u = new URL(url);
    const h = u.hostname.replace(/^m\./, '').replace(/^www\./, '');
    let videoId = null;
    if (h === 'youtu.be') {
      videoId = u.pathname.slice(1).split('/')[0];
    } else if (h === 'youtube.com') {
      if (u.pathname === '/watch') videoId = u.searchParams.get('v');
      else if (u.pathname.startsWith('/shorts/')) videoId = u.pathname.split('/')[2];
      else if (u.pathname.startsWith('/embed/')) videoId = u.pathname.split('/')[2];
    }
    // Use regular watch URL — embed fails with error 153 for many videos
    if (videoId) return `https://www.youtube.com/watch?v=${videoId}`;
  } catch {}
  return url;
}

async function injectYouTubeMaximize(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        if (!document.getElementById('wt-yt-style')) {
          const s = document.createElement('style');
          s.id = 'wt-yt-style';
          s.textContent = [
            'html,body{overflow:hidden!important}',
            'ytd-app,#page-manager{overflow:hidden!important;height:100vh!important}',
            '#masthead-container,ytd-miniguide-renderer{display:none!important}',
            'ytd-page-manager{margin-top:0!important;padding-top:0!important}',
            '#secondary,ytd-watch-next-secondary-results-renderer{display:none!important}',
            '.ytp-chrome-top,.ytp-title,.ytp-gradient-top{opacity:0!important;pointer-events:none!important}',
            'ytd-watch-metadata,#above-the-fold,ytd-above-the-fold-renderer,#actions,#owner,ytd-video-owner-renderer{display:none!important}',
            '.ytp-chrome-bottom,.ytp-gradient-bottom,.ytp-ce-element,.ytp-endscreen-element,.ytp-cards-teaser{display:none!important}',
            '#panels,ytd-engagement-panel-section-list-renderer{display:none!important}',
            'ytd-comments,#comments,#comment-teaser,#below{display:none!important}',
          ].join('');
          document.head.appendChild(s);
        }

        function maximize() {
          // Target the YouTube player container directly (same element YouTube uses for its own fullscreen)
          const player = document.querySelector('.html5-video-player') ||
                         document.getElementById('movie_player');
          if (!player) return false;

          // Clear stacking context blockers on every ancestor — transform/filter/contain/perspective
          // prevent position:fixed from being viewport-relative
          let el = player.parentElement;
          while (el && el !== document.documentElement) {
            el.style.setProperty('transform',   'none', 'important');
            el.style.setProperty('filter',      'none', 'important');
            el.style.setProperty('contain',     'none', 'important');
            el.style.setProperty('perspective', 'none', 'important');
            el = el.parentElement;
          }

          // Make the player fill the entire viewport
          [['position','fixed'],['top','0'],['left','0'],
           ['width','100vw'],['height','100vh'],
           ['z-index','2147483647'],['background','#000'],['overflow','hidden']
          ].forEach(([p, v]) => player.style.setProperty(p, v, 'important'));

          // Make the inner video container + video element fill the player
          player.querySelectorAll('.html5-video-container, video').forEach(el => {
            [['position','absolute'],['top','0'],['left','0'],
             ['width','100%'],['height','100%'],
             ['max-width','none'],['max-height','none'],
             ['object-fit','contain'],['margin','0'],['padding','0']
            ].forEach(([p, v]) => el.style.setProperty(p, v, 'important'));
            el.removeAttribute('width'); el.removeAttribute('height');
          });

          return true;
        }

        // Initial attempts with backoff
        let t = 0;
        const run = () => { if (!maximize() && ++t < 15) setTimeout(run, 400); };
        run();

        // Re-apply for 2 minutes in case YouTube resets styles dynamically
        const reapply = setInterval(maximize, 3000);
        setTimeout(() => clearInterval(reapply), 120000);
      }
    });
  } catch {}
}

async function handleRemoteCommand(cmd) {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);

  switch (cmd.action) {
    case 'pause':
      config.active = false; config.remotePaused = true;
      chrome.alarms.clear('wt-rotate');
      await chrome.storage.local.set({ config });
      await log('remote — pause'); break;

    case 'resume': {
      const tabToRemove = config.remoteTabId;
      config.remoteTabId = null;
      config.active = true; config.remotePaused = false;
      config.lastAlarmTime = Date.now();
      await chrome.storage.local.set({ config });          // sauvegarde avant remove
      if (tabToRemove) try { await chrome.tabs.remove(tabToRemove); } catch {}
      if (config.tabIds.length) {
        try { await chrome.tabs.update(config.tabIds[config.currentIndex % config.tabIds.length], { active: true }); } catch {}
      }
      await setNextAlarm(config.currentAlarmSec || config.interval);
      await log('remote — reprise'); break;
    }

    case 'open_url':
      if (cmd.url && config.windowId) {
        try {
          if (config.remoteTabId) { try { await chrome.tabs.remove(config.remoteTabId); } catch {} }
          const tab = await chrome.tabs.create({ windowId: config.windowId, url: transformUrl(cmd.url), active: true });
          config.remoteTabId = tab.id; config.active = false; config.remotePaused = true;
          chrome.alarms.clear('wt-rotate');
          await chrome.storage.local.set({ config });
          await log('remote — open_url: ' + cmd.url.slice(0, 60));
        } catch (e) { await log('remote open_url ERR: ' + e.message); }
      } break;

    case 'release': {
      const tabToRemove = config.remoteTabId;
      config.remoteTabId = null;
      config.active = true; config.remotePaused = false; config.lastAlarmTime = Date.now();
      await chrome.storage.local.set({ config });          // sauvegarde avant remove
      if (tabToRemove) try { await chrome.tabs.remove(tabToRemove); } catch {}
      if (config.tabIds.length) {
        try { await chrome.tabs.update(config.tabIds[config.currentIndex % config.tabIds.length], { active: true }); } catch {}
      }
      await setNextAlarm(config.currentAlarmSec || config.interval);
      await log('remote — libération'); break;
    }

    case 'next': case 'prev': {
      const urls = config.urls.filter(u => u?.url?.trim());
      if (urls.length && config.tabIds.length) {
        const n = cmd.action === 'next'
          ? (config.currentIndex + 1) % urls.length
          : (config.currentIndex - 1 + urls.length) % urls.length;
        if (n < config.tabIds.length) {
          try { await chrome.tabs.update(config.tabIds[n], { active: true }); } catch {}
          config.currentIndex = n; config.lastAlarmTime = Date.now();
          await chrome.storage.local.set({ config });
          if (config.active) await setNextAlarm(config.currentAlarmSec || config.interval);
          await log('remote — ' + cmd.action);
        }
      } break;
    }
  }
  await sendStateToRemote();
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
    if (i === config.currentIndex) continue; // ne jamais recharger l'onglet actif
    const tabId = config.tabIds[i];
    if (now - (times[tabId] || 0) >= intervalMs) {
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

// ── Canva auto-refresh ────────────────────────────────────────────────────────

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
    if (i === config.currentIndex) continue;
    if (!activeUrls[i]?.url?.includes('canva.com')) continue;
    const tabId = config.tabIds[i];
    if (now - (times[tabId] || 0) >= minMs) {
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

connectRemote();

// Empêche Chrome de tuer le service worker entre les alarmes (astuce MV3)
try {
  navigator.locks.request('wt-rotate-sw-alive', { mode: 'shared' }, () => new Promise(() => {}));
} catch {}
