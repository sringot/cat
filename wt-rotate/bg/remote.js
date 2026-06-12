let remoteWs             = null;
let remoteReconnectTimer = null;
let remoteLastMsg        = 0;

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
  if (remoteWs) {
    const rs = remoteWs.readyState;
    if (rs === WebSocket.CONNECTING || rs === WebSocket.CLOSING) return;
    if (rs === WebSocket.OPEN) {
      // Le serveur ping toutes les 20 s : une socket « ouverte » mais muette
      // depuis 50 s est un zombie (serveur tué, veille…) — on la remplace.
      if (Date.now() - remoteLastMsg < 50000) return;
      remoteWs.onclose = remoteWs.onmessage = remoteWs.onerror = null;
      try { remoteWs.close(); } catch {}
    }
  }
  clearTimeout(remoteReconnectTimer);
  try { remoteWs = new WebSocket('ws://localhost:8765'); } catch { scheduleReconnect(); return; }

  remoteWs.onopen = () => { remoteLastMsg = Date.now(); remoteWs.send(JSON.stringify({ type: 'extension' })); };

  remoteWs.onmessage = async evt => {
    remoteLastMsg = Date.now();
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
  config.remotePaused = false;
  chrome.alarms.clear('wt-spotlight');
  // config sauvée AVANT tabs.remove : sinon le listener onRemoved relit
  // l'ancien remoteTabId et réécrit la config périmée par-dessus la nôtre
  await chrome.storage.local.set({ config });
  if (tabToRemove) try { await chrome.tabs.remove(tabToRemove); } catch {}
  if (config.active) return { ok: true };

  let tabsValid = config.tabIds.length > 0;
  for (const tid of config.tabIds) {
    try { await chrome.tabs.get(tid); } catch { tabsValid = false; break; }
  }
  if (!tabsValid) {
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    if (!activeUrls.length) return { ok: false, reason: 'no_urls' };
    await autoStartRotation(config);
    await log('remote — démarrage rotation');
  } else {
    config.active = true;
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
        if (config.remoteTabId) {
          // remoteTabId effacé en storage AVANT la fermeture, pour que le
          // listener onRemoved ne la prenne pas pour une fermeture manuelle
          const old = config.remoteTabId;
          config.remoteTabId = null;
          await chrome.storage.local.set({ config });
          try { await chrome.tabs.remove(old); } catch {}
        }
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
      // Pendant un spotlight, suivant/précédent ferme l'URL externe et reprend
      if (config.remoteTabId || config.remoteUntil) {
        const r = await resumeRotation(config);
        if (!r.ok) { ok = false; reason = r.reason || null; break; }
      }
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
      // Pendant un spotlight, choisir une page ferme l'URL externe et reprend
      if (config.remoteTabId || config.remoteUntil) {
        const r = await resumeRotation(config);
        if (!r.ok) { ok = false; reason = r.reason || null; break; }
      }
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

    // Capture l'onglet kiosque et renvoie un JPEG base64 aux mobiles
    case 'screenshot': {
      if (!config.windowId) return;
      try {
        const dataUrl = await chrome.tabs.captureVisibleTab(
          config.windowId, { format: 'jpeg', quality: 35 });
        if (remoteWs?.readyState === WebSocket.OPEN) {
          remoteWs.send(JSON.stringify({ type: 'screenshot', data: dataUrl }));
        }
      } catch {}
      return; // pas d'ack ni de state push
    }

    // Affiche un bandeau de message sur les onglets kiosque
    case 'announce': {
      const text = (cmd.text || '').trim().slice(0, 300);
      const duration = Math.min(300, Math.max(5, Number(cmd.duration) || 30));
      if (!text) { ok = false; reason = 'empty_text'; break; }
      // Injecté dans TOUS les onglets kiosque : la rotation peut changer de
      // page pendant l'affichage, le message doit rester visible
      const targets = [...config.tabIds];
      if (config.remoteTabId) targets.push(config.remoteTabId);
      if (!targets.length) { ok = false; reason = 'no_window'; break; }
      let done = 0;
      for (const tid of targets) {
        try {
          await chrome.scripting.executeScript({
            target: { tabId: tid },
            func: (text, duration) => {
              const prev = document.getElementById('__wt_announce');
              if (prev) prev.remove();
              const el = document.createElement('div');
              el.id = '__wt_announce';
              el.textContent = text;
              el.style.cssText = 'position:fixed;bottom:0;left:0;right:0;'
                + 'background:rgba(0,0,0,.84);color:#fff;'
                + 'font:700 2.2vw/1.4 system-ui,sans-serif;'
                + 'text-align:center;padding:2vh 3vw;'
                + 'z-index:2147483647;opacity:0;transition:opacity .35s';
              document.body.appendChild(el);
              setTimeout(() => { el.style.opacity = '1'; }, 16);
              setTimeout(() => {
                el.style.opacity = '0';
                setTimeout(() => el.remove(), 420);
              }, duration * 1000);
            },
            args: [text, duration]
          });
          done++;
        } catch {} // onglet en cours de chargement, page chrome:// …
      }
      if (!done) { ok = false; reason = 'create_failed'; }
      break;
    }

    // Réglage du volume — injecté dans tous les <video> de l'onglet actif
    case 'volume': {
      const level = Math.round(Math.min(100, Math.max(0, Number(cmd.level) || 0)));
      let target = config.remoteTabId;
      if (!target && config.tabIds.length)
        target = config.tabIds[config.currentIndex % config.tabIds.length];
      if (target) {
        try {
          const vol = level / 100;
          await chrome.scripting.executeScript({
            target: { tabId: target, allFrames: true },
            func: v => { document.querySelectorAll('video').forEach(el => { el.volume = v; el.muted = false; }); },
            args: [vol]
          });
        } catch {}
      }
      return; // contrôle continu — pas d'ack ni de push d'état
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

    case 'reload_all': {
      const tabs = [...config.tabIds];
      if (config.remoteTabId) tabs.push(config.remoteTabId);
      for (const tid of tabs) {
        try { await chrome.tabs.reload(tid); } catch {}
      }
      await log('remote — rechargement de toutes les pages');
      break;
    }

    case 'set_interval': {
      const secs = Math.round(Math.min(3600, Math.max(5, Number(cmd.seconds) || 30)));
      config.interval = secs;
      await chrome.storage.local.set({ config });
      if (config.active) await setNextAlarm(secs);
      await log('remote — intervalle → ' + secs + ' s');
      break;
    }

    default:
      ok = false; reason = 'unknown_action';
  }

  sendCmdAck(cmd.action, ok, reason);
  await sendStateToRemote();
}
