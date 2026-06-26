// Plancher RÉEL d'une rotation. chrome.alarms ramène silencieusement toute
// alarme à 30 s minimum sur une extension installée (publiée/empaquetée) :
// demander 5 ou 10 s, Chrome sert quand même 30 s. On borne donc partout à
// cette valeur pour que l'UI ne promette jamais un défilement que le navigateur
// ne tient pas (le compte à rebours du remote afficherait 10 s, l'écran
// changerait à 30 s). Tout passe par migrateConfig : une seule source de vérité.
const ROTATE_FLOOR_SEC = 30;

// Normalise une durée par page : >0 → bornée au plancher ; 0/invalide → null
// (= « utilise l'intervalle par défaut »).
function clampInterval(v) {
  const n = Math.round(Number(v) || 0);
  return n > 0 ? Math.max(n, ROTATE_FLOOR_SEC) : null;
}

const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabIds: [], windowId: null,
  scheduleEnabled: false, scheduleStart: '08:00', scheduleEnd: '18:00',
  scheduleDays: [1, 2, 3, 4, 5], lastScheduleState: false,
  remotePaused: false, remoteTabId: null, remoteUntil: null,
  canvaRefreshMin: 5,
  tabRefreshHours: 4
};

function migrateConfig(raw) {
  // Copie profonde des tableaux : une mutation sur config.urls / tabIds ne
  // doit jamais polluer DEFAULT_CONFIG (partagé par référence sinon)
  const c = { ...DEFAULT_CONFIG, ...(raw || {}) };
  c.urls = (c.urls || []).map(u => {
    const o = typeof u === 'string' ? { url: u, name: '', interval: null } : { ...u };
    o.interval = clampInterval(o.interval);   // remonte d'anciennes durées < 30 s
    return o;
  });
  c.interval = Math.max(Math.round(Number(c.interval) || 30), ROTATE_FLOOR_SEC);
  if (c.tabId !== undefined) {
    if (!c.tabIds?.length && c.tabId) c.tabIds = [c.tabId];
    delete c.tabId;
  }
  c.tabIds = Array.isArray(c.tabIds) ? [...c.tabIds] : [];
  c.scheduleDays = Array.isArray(c.scheduleDays) ? [...c.scheduleDays] : [1, 2, 3, 4, 5];
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

// ── Arithmétique d'index de la playlist (pure, partagée rotate/next/prev/goto) ─
// len peut valoir 0 (playlist vide) : on renvoie 0 plutôt que NaN. Les appelants
// garantissent toujours len > 0 avant de tourner, mais ce garde-fou empêche
// qu'une régression amont ne propage un NaN dans currentIndex.
function nextIndex(current, len) { return len > 0 ? (current + 1) % len : 0; }
function prevIndex(current, len) { return len > 0 ? (current - 1 + len) % len : 0; }
function isValidIndex(idx, len) { return Number.isInteger(idx) && idx >= 0 && idx < len; }

// Export pour les tests Node (`module` est undefined dans le service worker
// MV3 : ce bloc y est donc ignoré et n'affecte pas le runtime de l'extension).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { DEFAULT_CONFIG, migrateConfig, isInSchedule,
                     nextIndex, prevIndex, isValidIndex,
                     ROTATE_FLOOR_SEC, clampInterval };
}
