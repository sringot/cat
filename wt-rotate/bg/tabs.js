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
    // Refresh preview 1.5 s after the switch (let the page load first)
    setTimeout(autoScreenshot, 3000);
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
  // Spotlight en cours : on ne démarre/arrête rien par-dessus une URL envoyée
  // explicitement. lastScheduleState n'est pas mis à jour, la transition
  // sera appliquée au tick suivant la fin du spotlight.
  if (config.remoteTabId) return;
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

// Empêche Memory Saver de décharger un onglet kiosque : un onglet déchargé
// ne poll plus son API → la session expire côté serveur (WithSecure, NinjaOne…)
async function keepTabAlive(tabId) {
  try { await chrome.tabs.update(tabId, { autoDiscardable: false }); } catch {}
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
      await keepTabAlive(win.tabs[0].id);
      for (let i = 1; i < activeUrls.length; i++) {
        const tab = await chrome.tabs.create({ windowId: win.id, url: activeUrls[i].url, active: false });
        config.tabIds.push(tab.id);
        await keepTabAlive(tab.id);
      }
    } else {
      // tabIds vidés en storage AVANT la fermeture des anciens onglets :
      // le listener onRemoved les prendrait pour une fermeture manuelle
      const oldTabs = config.tabIds;
      config.tabIds = [];
      await chrome.storage.local.set({ config });
      for (const tid of oldTabs) { try { await chrome.tabs.remove(tid); } catch {} }
      for (let i = 0; i < activeUrls.length; i++) {
        const tab = await chrome.tabs.create({ windowId: config.windowId, url: activeUrls[i].url, active: i === 0 });
        config.tabIds.push(tab.id);
        await keepTabAlive(tab.id);
      }
      await chrome.windows.update(config.windowId, { state: 'fullscreen' });
    }
    config.currentIndex = 0; config.active = true; config.remotePaused = false;
    config.lastAlarmTime = Date.now();
    config.currentAlarmSec = activeUrls[0].interval || config.interval;
    config.tabsDirty = false;   // onglets fraîchement alignés sur la playlist
    await chrome.storage.local.set({ config });
    await setNextAlarm(config.currentAlarmSec);
    await sendStateToRemote();
  } catch (e) {
    await log('autoStart ERR: ' + e.message);
    // Échec en cours de (re)construction des onglets : on ne laisse pas tourner
    // une rotation sur un jeu d'onglets incomplet (sinon currentIndex pointe
    // dans le vide). Retour à un état arrêté propre ; le prochain démarrage
    // (popup, horaire, resync) repart de zéro.
    config.active = false; config.tabIds = []; config.windowId = null;
    await chrome.storage.local.set({ config });
  }
}

// Le popup peut éditer config.urls sans toucher tabIds : l'alignement
// tabIds[i] ↔ activeUrls[i] — sur lequel reposent la rotation, la détection de
// session et le refresh Canva — se rompt alors. Deux cas, tous deux rattrapés :
//   - ajout/suppression                → les longueurs diffèrent ;
//   - réordonnancement / URL changée en place (mêmes longueurs) → le popup pose
//     config.tabsDirty quand il édite pendant une rotation active.
// On reconstruit alors les onglets sur la playlist courante, comme le fait une
// édition mobile (qui, elle, passe par le SW : tabIds maintenu, drapeau jamais levé).
function needsResync(config, activeUrls) {
  if (!config.active || !config.windowId || config.remoteTabId) return false;
  if (!activeUrls.length) return false;
  return config.tabIds.length !== activeUrls.length || !!config.tabsDirty;
}

async function resyncTabsIfNeeded() {
  const data = await chrome.storage.local.get('config');
  const config = migrateConfig(data.config);
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  if (!needsResync(config, activeUrls)) return;
  await log('resync — playlist modifiée pendant la rotation, reconstruction des onglets');
  await autoStartRotation(config);
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
    if (!(tabId in times)) {
      // First time we see this tab — seed the clock so it isn't reloaded immediately
      times[tabId] = now;
      changed = true;
      continue;
    }
    if (now - times[tabId] >= intervalMs) {
      // Re-read currentIndex only when about to reload (rare) : it may have
      // changed during the awaits, and we must never reload the active tab.
      const fresh = await chrome.storage.local.get('config');
      if (i === migrateConfig(fresh.config).currentIndex) continue;
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

// ── Détection de sessions expirées (page de login affichée) ──────────────────
// Quand un onglet kiosque atterrit sur une page de login (session expirée),
// on le re-navigue vers son URL configurée : si le SSO est encore valide la
// reconnexion est silencieuse et le dashboard revient seul. Sinon l'entrée
// reste dans sessionWarn et le téléphone affiche un avertissement.

const LOGIN_RX = /(login\.microsoftonline\.com|b2clogin\.com|okta\.com|auth0\.com|accounts\.google\.com|onelogin\.com|duosecurity\.com)|[\/.](login|log-?in|sign-?in|sso|authenticate|authentication)([\/?#.]|$)/i;
const LOGIN_RETRY_MS = 10 * 60 * 1000; // re-navigation au plus toutes les 10 min

async function checkSessions() {
  const data = await chrome.storage.local.get(['config', 'sessionWarn']);
  const config = migrateConfig(data.config);
  if (!config.tabIds.length) {
    if (Object.keys(data.sessionWarn || {}).length)
      await chrome.storage.local.set({ sessionWarn: {} });
    return;
  }
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  const warn = data.sessionWarn || {};
  const now = Date.now();
  let changed = false;

  for (let i = 0; i < config.tabIds.length; i++) {
    const tabId = config.tabIds[i];
    const entry = activeUrls[i];
    if (!entry) continue;
    let tab;
    try { tab = await chrome.tabs.get(tabId); } catch { continue; }

    if (tab.autoDiscardable !== false) await keepTabAlive(tabId);
    if (tab.status === 'loading') continue;          // redirection SSO en cours

    // Si l'URL configurée ressemble elle-même à une page de login, indétectable
    const onLogin = !LOGIN_RX.test(entry.url) && LOGIN_RX.test(tab.url || '');

    if (onLogin) {
      if (!warn[tabId]) {
        warn[tabId] = { name: entry.name || entry.url.slice(0, 40), since: now, lastRetry: 0 };
        changed = true;
        await log('session expirée détectée: ' + warn[tabId].name);
      }
      if (now - warn[tabId].lastRetry >= LOGIN_RETRY_MS) {
        warn[tabId].lastRetry = now;
        changed = true;
        try {
          await chrome.tabs.update(tabId, { url: entry.url });
          await log('re-navigation (tentative SSO): ' + warn[tabId].name);
        } catch {}
      }
    } else if (warn[tabId]) {
      await log('session restaurée: ' + warn[tabId].name);
      delete warn[tabId];
      changed = true;
    }
  }

  for (const tid of Object.keys(warn)) {
    if (!config.tabIds.includes(Number(tid))) { delete warn[tid]; changed = true; }
  }
  if (changed) {
    await chrome.storage.local.set({ sessionWarn: warn });
    await sendStateToRemote();
  }
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
    if (!(tabId in times)) {
      times[tabId] = now;
      changed = true;
      continue;
    }
    if (now - times[tabId] >= minMs) {
      // Re-read currentIndex only when about to reload (rare) to avoid the active tab
      const fresh = await chrome.storage.local.get('config');
      if (i === migrateConfig(fresh.config).currentIndex) continue;
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

// Export pour les tests Node (`module` est undefined dans le service worker
// MV3 : ce bloc y est ignoré et n'affecte pas le runtime de l'extension).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { needsResync };
}
