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
  c.urls = (c.urls || []).map(u =>
    typeof u === 'string' ? { url: u, name: '', interval: null } : { ...u }
  );
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

// Export pour les tests Node (`module` est undefined dans le service worker
// MV3 : ce bloc y est donc ignoré et n'affecte pas le runtime de l'extension).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { DEFAULT_CONFIG, migrateConfig, isInSchedule };
}
