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
  const data = await chrome.storage.local.get(['config', 'sessionWarn']);
  const config = migrateConfig(data.config);
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  let remoteUrl = null;
  if (config.remoteTabId) {
    try { const tab = await chrome.tabs.get(config.remoteTabId); remoteUrl = tab.url || null; } catch {}
  }
  // Index (dans la playlist) des onglets bloqués sur une page de login
  const sessionWarn = data.sessionWarn || {};
  const warnings = config.tabIds
    .map((tid, i) => sessionWarn[tid] ? i : -1)
    .filter(i => i >= 0 && i < activeUrls.length);
  remoteWs.send(JSON.stringify({
    type: 'state', active: config.active,
    remotePaused: config.remotePaused || false,
    remoteUrl,
    remoteUntil: config.remoteUntil || null,
    hasTabs: config.tabIds.length > 0,
    currentIndex: config.currentIndex,
    urls: activeUrls.map(u => ({ name: u.name || '', url: u.url })),
    interval: config.interval,
    warnings
  }));
}

// Ferme l'onglet externe éventuel puis reprend la rotation — ou la
// (re)démarre si les onglets ont disparu. Partagé entre les commandes
// start/resume/release et la fin de spotlight (alarme wt-spotlight).
async function resumeRotation(config) {
  const tabToRemove = config.remoteTabId;
  config.remoteTabId = null;
  config.remoteUntil = null;
  chrome.alarms.clear('wt-spotlight');
  if (tabToRemove) try { await chrome.tabs.remove(tabToRemove); } catch {}
  if (config.active) { await chrome.storage.local.set({ config }); return { ok: true }; }

  let tabsValid = config.tabIds.length > 0;
  for (const tid of config.tabIds) {
    try { await chrome.tabs.get(tid); } catch { tabsValid = false; break; }
  }
  if (!tabsValid) {
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    if (!activeUrls.length) {
      await chrome.storage.local.set({ config });
      return { ok: false, reason: 'no_urls' };
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
  return { ok: true };
}

// Fin du spotlight : l'URL externe a fait son temps, retour à la rotation
async function endSpotlight() {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  if (!config.remoteTabId && !config.remoteUntil) return; // déjà relâché à la main
  await log('spotlight terminé — retour à la rotation');
  await resumeRotation(config);
  await sendStateToRemote();
}

// Indices réels (dans config.urls) des pages actives — le remote ne voit
// que la liste filtrée, ses indices doivent être traduits avant mutation
function activeIndices(config) {
  return config.urls.map((u, j) => u?.url?.trim() ? j : -1).filter(j => j >= 0);
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

    case 'start': case 'resume': case 'release': {
      const r = await resumeRotation(config);
      ok = r.ok; reason = r.reason || null;
      break;
    }

    case 'open_url': {
      if (!cmd.url) { ok = false; reason = 'invalid_url'; break; }
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
        if (config.remoteTabId) { try { await chrome.tabs.remove(config.remoteTabId); } catch {} config.remoteTabId = null; }
        let tab;
        if (config.windowId) {
          // Essai d'ajout dans la fenêtre kiosque existante
          try {
            tab = await chrome.tabs.create({ windowId: config.windowId, url: safeUrl, active: true });
            // ré-assert le plein écran (fenêtre potentiellement réduite à la main)
            try { await chrome.windows.update(config.windowId, { state: 'fullscreen', focused: true }); } catch {}
          } catch { config.windowId = null; }
        }
        if (!config.windowId) {
          // Pas de fenêtre kiosque : on ouvre une fenêtre plein écran dédiée
          const win = await chrome.windows.create({ url: safeUrl, state: 'fullscreen' });
          config.windowId = win.id;
          tab = win.tabs[0];
        }
        config.remoteTabId = tab.id; config.active = false; config.remotePaused = true;
        chrome.alarms.clear('wt-rotate');
        // Spotlight : retour automatique à la rotation après `duration` secondes
        chrome.alarms.clear('wt-spotlight');
        const dur = Number(cmd.duration) || 0;
        if (dur > 0) {
          config.remoteUntil = Date.now() + dur * 1000;
          chrome.alarms.create('wt-spotlight', { delayInMinutes: Math.max(dur / 60, 0.1) });
        } else {
          config.remoteUntil = null;
        }
        await chrome.storage.local.set({ config });
        await log('remote — open_url: ' + cmd.url.slice(0, 60) + (dur ? ` (${dur}s)` : ''));
        // Injection YouTube immédiate en cas de chargement rapide
        if (/youtube\.com\/watch|youtu\.be\//.test(safeUrl)) {
          setTimeout(() => injectYouTubeMaximize(tab.id).catch(() => {}), 1500);
        }
      } catch (e) {
        await log('remote open_url ERR: ' + e.message);
        ok = false; reason = 'create_failed';
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

    // Avance/recule dans la vidéo affichée (YouTube ou tout lecteur HTML5)
    case 'seek': {
      const delta = Number(cmd.delta);
      if (!delta || Math.abs(delta) > 600) { ok = false; reason = 'bad_index'; break; }
      let target = config.remoteTabId;
      if (!target && config.tabIds.length)
        target = config.tabIds[config.currentIndex % config.tabIds.length];
      if (!target) { ok = false; reason = 'no_video'; break; }
      try {
        const res = await chrome.scripting.executeScript({
          target: { tabId: target, allFrames: true },
          func: d => {
            const v = document.querySelector('video');
            if (!v) return false;
            v.currentTime = Math.max(0, v.currentTime + d);
            return true;
          },
          args: [delta]
        });
        if (!res?.some(r => r?.result)) { ok = false; reason = 'no_video'; }
      } catch { ok = false; reason = 'no_video'; }
      break;
    }

    // ── Édition de la playlist depuis le téléphone ───────────────────────────
    case 'pl_add': {
      const url = (cmd.url || '').trim();
      try {
        const parsed = new URL(url);
        if (!SAFE_URL_SCHEMES.includes(parsed.protocol)) throw 0;
      } catch { ok = false; reason = 'invalid_url'; break; }
      config.urls.push({ url, name: (cmd.name || '').trim(), interval: null });
      // Rotation en cours : on crée l'onglet à la volée, sans tout recharger
      if (config.tabIds.length && config.windowId) {
        try {
          const tab = await chrome.tabs.create({ windowId: config.windowId, url, active: false });
          config.tabIds.push(tab.id);
          await keepTabAlive(tab.id);
        } catch {} // fenêtre fermée : la prochaine lecture recréera tout
      }
      await chrome.storage.local.set({ config });
      await log('remote — page ajoutée: ' + url.slice(0, 50));
      break;
    }

    case 'pl_remove': {
      const act = activeIndices(config);
      const i = Number.isInteger(cmd.index) ? cmd.index : -1;
      if (i < 0 || i >= act.length) { ok = false; reason = 'bad_index'; break; }
      const name = config.urls[act[i]].name || config.urls[act[i]].url.slice(0, 40);
      config.urls.splice(act[i], 1);
      const removedTab = config.tabIds[i];
      if (removedTab !== undefined) {
        const wasCur = i === config.currentIndex;
        config.tabIds.splice(i, 1);
        if (!config.tabIds.length) {
          config.active = false; config.windowId = null;
          chrome.alarms.clear('wt-rotate');
        } else {
          if (i < config.currentIndex) config.currentIndex--;
          if (config.currentIndex >= config.tabIds.length) config.currentIndex = 0;
          if (wasCur) {
            try { await chrome.tabs.update(config.tabIds[config.currentIndex], { active: true }); } catch {}
            config.lastAlarmTime = Date.now();
            if (config.active) await setNextAlarm(config.currentAlarmSec || config.interval);
          }
        }
        // config sauvée AVANT tabs.remove : sinon le listener onRemoved croit
        // qu'un onglet kiosque a été fermé à la main et stoppe la rotation
        await chrome.storage.local.set({ config });
        try { await chrome.tabs.remove(removedTab); } catch {}
      } else {
        await chrome.storage.local.set({ config });
      }
      await log('remote — page supprimée: ' + name);
      break;
    }

    case 'pl_rename': {
      const act = activeIndices(config);
      const i = Number.isInteger(cmd.index) ? cmd.index : -1;
      if (i < 0 || i >= act.length) { ok = false; reason = 'bad_index'; break; }
      config.urls[act[i]].name = (cmd.name || '').trim();
      await chrome.storage.local.set({ config });
      break;
    }

    case 'pl_move': {
      const act = activeIndices(config);
      const from = Number.isInteger(cmd.from) ? cmd.from : -1;
      const to   = Number.isInteger(cmd.to)   ? cmd.to   : -1;
      if (from < 0 || from >= act.length || to < 0 || to >= act.length || from === to) {
        ok = false; reason = 'bad_index'; break;
      }
      const [moved] = config.urls.splice(act[from], 1);
      const act2 = activeIndices(config);
      const insertAt = to < act2.length ? act2[to] : config.urls.length;
      config.urls.splice(insertAt, 0, moved);
      // Les onglets suivent le même réordonnancement, la page affichée ne change pas
      if (config.tabIds.length === act.length) {
        const curTab = config.tabIds[config.currentIndex];
        const [t] = config.tabIds.splice(from, 1);
        config.tabIds.splice(to, 0, t);
        const ni = config.tabIds.indexOf(curTab);
        if (ni >= 0) config.currentIndex = ni;
      }
      await chrome.storage.local.set({ config });
      break;
    }

    default:
      ok = false; reason = 'unknown_action';
  }

  sendCmdAck(cmd.action, ok, reason);
  await sendStateToRemote();
}
