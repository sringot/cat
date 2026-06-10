let remoteWs             = null;
let remoteReconnectTimer = null;

const SAFE_URL_SCHEMES = ['http:', 'https:'];

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
    if (videoId) return `https://www.youtube.com/watch?v=${videoId}`;
  } catch {}
  return url;
}

function connectRemote() {
  if (remoteWs?.readyState === WebSocket.OPEN    ||
      remoteWs?.readyState === WebSocket.CONNECTING ||
      remoteWs?.readyState === WebSocket.CLOSING) return;
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
          remoteInfo: { ip: msg.ip, http_port: msg.http_port, control_url: msg.control_url, connected: true }
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

function sendCmdAck(action, ok, reason) {
  if (remoteWs?.readyState !== WebSocket.OPEN) return;
  remoteWs.send(JSON.stringify({ type: 'cmd_ack', action, ok, reason: reason || null }));
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
    hasTabs: config.tabIds.length > 0,
    currentIndex: config.currentIndex,
    urls: activeUrls.map(u => ({ name: u.name || '', url: u.url })),
    interval: config.interval
  }));
}

async function handleRemoteCommand(cmd) {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  let ok = true, reason = null;

  switch (cmd.action) {
    case 'pause':
      if (!config.active) { ok = false; reason = 'not_running'; break; }
      config.active = false; config.remotePaused = true;
      chrome.alarms.clear('wt-rotate');
      await chrome.storage.local.set({ config });
      await log('remote — pause'); break;

    // start / resume / release : ferment l'onglet externe éventuel puis
    // reprennent la rotation — ou la (re)démarrent si les onglets ont disparu
    case 'start': case 'resume': case 'release': {
      const tabToRemove = config.remoteTabId;
      config.remoteTabId = null;
      if (tabToRemove) try { await chrome.tabs.remove(tabToRemove); } catch {}
      if (config.active) { await chrome.storage.local.set({ config }); break; }

      let tabsValid = config.tabIds.length > 0;
      for (const tid of config.tabIds) {
        try { await chrome.tabs.get(tid); } catch { tabsValid = false; break; }
      }
      if (!tabsValid) {
        const activeUrls = config.urls.filter(u => u?.url?.trim());
        if (!activeUrls.length) {
          await chrome.storage.local.set({ config });
          ok = false; reason = 'no_urls'; break;
        }
        await autoStartRotation(config);
        await log('remote — démarrage rotation');
      } else {
        config.active = true; config.remotePaused = false;
        config.lastAlarmTime = Date.now();
        await chrome.storage.local.set({ config });
        try { await chrome.tabs.update(config.tabIds[config.currentIndex % config.tabIds.length], { active: true }); } catch {}
        await setNextAlarm(config.currentAlarmSec || config.interval);
        await log('remote — reprise');
      }
      break;
    }

    case 'open_url': {
      if (!cmd.url) { ok = false; reason = 'invalid_url'; break; }
      if (!config.windowId) { ok = false; reason = 'no_window'; break; }
      let safeUrl;
      try {
        const parsed = new URL(cmd.url);
        if (!SAFE_URL_SCHEMES.includes(parsed.protocol)) {
          await log('remote open_url rejeté — schéma interdit: ' + parsed.protocol);
          ok = false; reason = 'blocked_scheme'; break;
        }
        safeUrl = transformUrl(cmd.url);
      } catch { ok = false; reason = 'invalid_url'; break; }
      try {
        if (config.remoteTabId) { try { await chrome.tabs.remove(config.remoteTabId); } catch {} }
        const tab = await chrome.tabs.create({ windowId: config.windowId, url: safeUrl, active: true });
        config.remoteTabId = tab.id; config.active = false; config.remotePaused = true;
        chrome.alarms.clear('wt-rotate');
        await chrome.storage.local.set({ config });
        await log('remote — open_url: ' + cmd.url.slice(0, 60));
      } catch (e) {
        await log('remote open_url ERR: ' + e.message);
        ok = false; reason = 'no_window';
      }
      break;
    }

    case 'next': case 'prev': {
      const urls = config.urls.filter(u => u?.url?.trim());
      if (!urls.length || !config.tabIds.length) { ok = false; reason = 'rotation_stopped'; break; }
      const n = cmd.action === 'next'
        ? (config.currentIndex + 1) % urls.length
        : (config.currentIndex - 1 + urls.length) % urls.length;
      if (n >= config.tabIds.length) { ok = false; reason = 'rotation_stopped'; break; }
      try { await chrome.tabs.update(config.tabIds[n], { active: true }); }
      catch { ok = false; reason = 'rotation_stopped'; break; }
      config.currentIndex = n; config.lastAlarmTime = Date.now();
      await chrome.storage.local.set({ config });
      if (config.active) await setNextAlarm(config.currentAlarmSec || config.interval);
      await log('remote — ' + cmd.action);
      break;
    }

    case 'goto': {
      const idx = Number.isInteger(cmd.index) ? cmd.index : -1;
      const urls = config.urls.filter(u => u?.url?.trim());
      if (!urls.length || !config.tabIds.length) { ok = false; reason = 'rotation_stopped'; break; }
      if (idx < 0 || idx >= urls.length || idx >= config.tabIds.length) { ok = false; reason = 'bad_index'; break; }
      try { await chrome.tabs.update(config.tabIds[idx], { active: true }); }
      catch { ok = false; reason = 'rotation_stopped'; break; }
      config.currentIndex = idx; config.lastAlarmTime = Date.now();
      await chrome.storage.local.set({ config });
      if (config.active) await setNextAlarm(config.currentAlarmSec || config.interval);
      await log('remote — goto ' + idx);
      break;
    }

    default:
      ok = false; reason = 'unknown_action';
  }

  sendCmdAck(cmd.action, ok, reason);
  await sendStateToRemote();
}
