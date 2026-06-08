const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabIds: [], windowId: null,
  scheduleEnabled: false, scheduleStart: '08:00', scheduleEnd: '18:00',
  scheduleDays: [1, 2, 3, 4, 5], lastScheduleState: false,
  canvaRefreshMin: 5
};

let config        = null;
let progressTimer = null;
let dragSrcIndex  = null;

const $ = id => document.getElementById(id);

const badge          = $('badge');
const progressWrap   = $('progress-wrap');
const progressBar    = $('progress-bar');
const urlList        = $('url-list');
const btnAdd         = $('btn-add');
const slider         = $('slider');
const intervalN      = $('interval');
const btnStart       = $('btn-start');
const btnStop        = $('btn-stop');
const btnNext        = $('btn-next');
const scheduleEnabledCb = $('schedule-enabled');
const scheduleDetails   = $('schedule-details');
const scheduleStart     = $('schedule-start');
const scheduleEnd       = $('schedule-end');
const canvaRefreshInput = $('canva-refresh');
const debugToggle    = $('debug-toggle');
const debugBox       = $('debug-box');
const debugLog       = $('debug-log');
const debugClear     = $('debug-clear');

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  initTabs();
  initDayButtons();
  await refresh();
});

function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      $('tab-' + btn.dataset.tab).classList.add('active');
    });
  });
}

function initDayButtons() {
  document.querySelectorAll('.day-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const day  = parseInt(btn.dataset.day);
      const days = config.scheduleDays || [1, 2, 3, 4, 5];
      const idx  = days.indexOf(day);
      if (idx >= 0) days.splice(idx, 1); else days.push(day);
      config.scheduleDays = days;
      btn.classList.toggle('on', days.includes(day));
      saveConfig();
    });
  });
}

function migrateConfig(raw) {
  if (!raw) return { ...DEFAULT_CONFIG };
  const c = { ...DEFAULT_CONFIG, ...raw };
  c.urls = (c.urls || []).map(u =>
    typeof u === 'string' ? { url: u, name: '', interval: null } : u
  );
  // Migrate from old single tabId to tabIds array
  if (c.tabId !== undefined) {
    if (!c.tabIds?.length && c.tabId) c.tabIds = [c.tabId];
    delete c.tabId;
  }
  if (!Array.isArray(c.tabIds)) c.tabIds = [];
  return c;
}

async function refresh() {
  try {
    const data = await chrome.storage.local.get('config');
    config = migrateConfig(data?.config);
  } catch {
    config = config || migrateConfig(null);
  }
  renderAll();
}

function saveConfig() {
  return chrome.storage.local.set({ config });
}

function renderAll() {
  renderUrls();
  slider.value    = Math.min(config.interval, 300);
  intervalN.value = config.interval;
  canvaRefreshInput.value = config.canvaRefreshMin || 5;
  renderSchedule();
  updateStatusUI();
  refreshRemoteInfo();
}

// ── URL list ──────────────────────────────────────────────────────────────────

function renderUrls() {
  urlList.innerHTML = '';
  if (!config.urls.length) {
    urlList.innerHTML = '<div class="empty-hint">Aucune URL — cliquez sur + pour commencer</div>';
    return;
  }
  config.urls.forEach((entry, i) => {
    const isActive = config.active && i === config.currentIndex;
    const row = document.createElement('div');
    row.className = 'url-row' + (isActive ? ' active-url' : '');
    row.draggable = true;
    row.innerHTML = `
      <span class="drag-handle">⠿</span>
      <div class="url-fields">
        <input class="name-input" type="text" value="${esc(entry.name || '')}"
               placeholder="Nom affiché" autocomplete="off">
        <input class="url-input" type="text" value="${esc(entry.url || '')}"
               placeholder="https://..." spellcheck="false" autocomplete="off">
      </div>
      <div class="url-actions">
        <button class="btn-del" title="Supprimer">✕</button>
        <div class="url-interval-wrap">
          <button class="url-dur-toggle${entry.interval ? ' on' : ''}" title="Durée personnalisée">⏱</button>
          <input class="url-interval" type="number"
                 value="${entry.interval || config.interval}"
                 min="5" max="86400"
                 style="display:${entry.interval ? '' : 'none'}">
          <span class="interval-s" style="display:${entry.interval ? '' : 'none'}">s</span>
        </div>
      </div>
    `;
    const nameInp   = row.querySelector('.name-input');
    const urlInp    = row.querySelector('.url-input');
    const toggleBtn = row.querySelector('.url-dur-toggle');
    const intInp    = row.querySelector('.url-interval');
    const intS      = row.querySelector('.interval-s');

    nameInp.addEventListener('input', () => { config.urls[i].name = nameInp.value; saveConfig(); });
    nameInp.addEventListener('blur',  () => { config.urls[i].name = nameInp.value.trim(); nameInp.value = config.urls[i].name; saveConfig(); });
    nameInp.addEventListener('keydown', e => { if (e.key === 'Enter') urlInp.focus(); });

    urlInp.addEventListener('input', () => { config.urls[i].url = urlInp.value; saveConfig(); });
    urlInp.addEventListener('blur',  () => { config.urls[i].url = urlInp.value.trim(); urlInp.value = config.urls[i].url; saveConfig(); });
    urlInp.addEventListener('keydown', e => { if (e.key === 'Enter') urlInp.blur(); });

    toggleBtn.addEventListener('click', () => {
      if (config.urls[i].interval) {
        config.urls[i].interval = null;
        toggleBtn.classList.remove('on');
        intInp.style.display = 'none'; intS.style.display = 'none';
      } else {
        config.urls[i].interval = config.interval;
        intInp.value = config.interval;
        toggleBtn.classList.add('on');
        intInp.style.display = ''; intS.style.display = '';
      }
      saveConfig();
    });

    intInp.addEventListener('change', () => {
      const val = parseInt(intInp.value);
      config.urls[i].interval = val >= 5 ? val : null;
      intInp.value = config.urls[i].interval || config.interval;
      saveConfig();
    });

    row.querySelector('.btn-del').addEventListener('click', () => {
      config.urls.splice(i, 1);
      const valid = config.urls.filter(u => u?.url?.trim());
      if (config.currentIndex >= valid.length) config.currentIndex = 0;
      saveConfig(); renderUrls();
    });

    row.addEventListener('dragstart', e => { dragSrcIndex = i; e.dataTransfer.effectAllowed = 'move'; });
    row.addEventListener('dragover',  e => { e.preventDefault(); row.classList.add('drag-over'); });
    row.addEventListener('dragleave', () => row.classList.remove('drag-over'));
    row.addEventListener('drop', e => {
      e.preventDefault(); row.classList.remove('drag-over');
      if (dragSrcIndex === null || dragSrcIndex === i) return;
      const moved = config.urls.splice(dragSrcIndex, 1)[0];
      config.urls.splice(i, 0, moved);
      dragSrcIndex = null; saveConfig(); renderUrls();
    });
    row.addEventListener('dragend', () => {
      dragSrcIndex = null;
      urlList.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    });
    urlList.appendChild(row);
  });
}

// ── Status ────────────────────────────────────────────────────────────────────

function updateStatusUI() {
  const on = config.active;
  badge.className   = 'badge ' + (on ? 'badge-active' : 'badge-stopped');
  badge.textContent = on ? 'Actif' : 'Arrêté';
  btnStart.classList.toggle('hidden', on);
  btnStop.classList.toggle('hidden', !on);
  btnNext.classList.toggle('hidden', !on);
  progressWrap.classList.toggle('hidden', !on);

  if (on) {
    const activeUrls  = config.urls.filter(u => u?.url?.trim());
    const cur         = activeUrls[config.currentIndex % Math.max(activeUrls.length, 1)];
    const totalSec    = config.currentAlarmSec || cur?.interval || config.interval;
    let   remainSec   = totalSec;
    if (config.lastAlarmTime) {
      remainSec = Math.max(1, totalSec - (Date.now() - config.lastAlarmTime) / 1000);
    }
    startProgressBar(remainSec, totalSec);
  } else {
    stopProgressBar();
  }
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function startProgressBar(remainSec, totalSec) {
  stopProgressBar();
  const pct = (remainSec / totalSec) * 100;
  progressBar.style.transition = 'none';
  progressBar.style.width = pct + '%';
  progressBar.offsetWidth;
  progressBar.style.transition = `width ${remainSec}s linear`;
  progressBar.style.width = '0%';
  progressTimer = setTimeout(async () => {
    try {
      const d = await chrome.storage.local.get('config');
      if (d?.config) { config = migrateConfig(d.config); renderAll(); }
    } catch {}
  }, remainSec * 1000);
}

function stopProgressBar() {
  if (progressTimer) { clearTimeout(progressTimer); progressTimer = null; }
  progressBar.style.transition = 'none';
  progressBar.style.width = '0%';
}

// ── Start / Stop / Next ───────────────────────────────────────────────────────

async function startRotation() {
  try {
    flushInputs();
    await saveConfig();
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    if (!activeUrls.length) { alert('Ajoutez au moins une URL avant de démarrer.'); return; }

    let winExists = false;
    if (config.windowId) {
      try { await chrome.windows.get(config.windowId); winExists = true; } catch {}
    }

    if (!winExists) {
      const win = await chrome.windows.create({ url: activeUrls[0].url, state: 'fullscreen' });
      if (!win?.tabs?.[0]?.id) { alert("Impossible d'ouvrir la fenêtre."); return; }
      config.tabIds   = [win.tabs[0].id];
      config.windowId = win.id;
      for (let i = 1; i < activeUrls.length; i++) {
        const tab = await chrome.tabs.create({ windowId: win.id, url: activeUrls[i].url, active: false });
        config.tabIds.push(tab.id);
      }
    } else {
      // Window exists — close stale tabs and recreate for the current URL list
      for (const tid of config.tabIds || []) { try { await chrome.tabs.remove(tid); } catch {} }
      config.tabIds = [];
      for (let i = 0; i < activeUrls.length; i++) {
        const tab = await chrome.tabs.create({ windowId: config.windowId, url: activeUrls[i].url, active: i === 0 });
        config.tabIds.push(tab.id);
      }
      await chrome.windows.update(config.windowId, { state: 'fullscreen' });
    }

    config.currentIndex    = 0;
    config.active          = true;
    config.lastAlarmTime   = Date.now();
    config.currentAlarmSec = activeUrls[0].interval || config.interval;
    await saveConfig();
    chrome.runtime.sendMessage({ action: 'startTimer', interval: config.currentAlarmSec }).catch(() => {});
    await refresh();
  } catch (err) {
    alert('Erreur : ' + (err?.message || String(err)));
  }
}

btnStart.addEventListener('click', startRotation);

btnStop.addEventListener('click', async () => {
  config.active = false;
  await saveConfig();
  chrome.runtime.sendMessage({ action: 'stopTimer' }).catch(() => {});
  await refresh();
});

btnNext.addEventListener('click', async () => {
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  if (!config.tabIds?.length || !activeUrls.length) return;
  const next = (config.currentIndex + 1) % activeUrls.length;
  if (next < config.tabIds.length) {
    try { await chrome.tabs.update(config.tabIds[next], { active: true }); } catch {}
  }
  config.currentIndex    = next;
  config.lastAlarmTime   = Date.now();
  config.currentAlarmSec = activeUrls[next].interval || config.interval;
  await saveConfig();
  renderUrls(); updateStatusUI();
});

// ── Add URL ───────────────────────────────────────────────────────────────────

btnAdd.addEventListener('click', () => {
  if (!config) config = migrateConfig(null);
  config.urls.push({ url: '', name: '', interval: null });
  saveConfig(); renderUrls();
  const inputs = urlList.querySelectorAll('.url-input');
  if (inputs.length) inputs[inputs.length - 1].focus();
});

// ── Interval ──────────────────────────────────────────────────────────────────

slider.addEventListener('input', () => {
  config.interval = parseInt(slider.value);
  intervalN.value = config.interval;
  saveConfig(); renderUrls();
});

intervalN.addEventListener('change', () => {
  config.interval = Math.max(5, Math.min(86400, parseInt(intervalN.value) || 30));
  intervalN.value = config.interval;
  slider.value    = Math.min(config.interval, 300);
  saveConfig(); renderUrls();
});

// ── Schedule ──────────────────────────────────────────────────────────────────

function renderSchedule() {
  scheduleEnabledCb.checked = !!config.scheduleEnabled;
  scheduleDetails.classList.toggle('hidden', !config.scheduleEnabled);
  scheduleStart.value = config.scheduleStart || '08:00';
  scheduleEnd.value   = config.scheduleEnd   || '18:00';
  const days = config.scheduleDays || [1, 2, 3, 4, 5];
  document.querySelectorAll('.day-btn').forEach(btn => {
    btn.classList.toggle('on', days.includes(parseInt(btn.dataset.day)));
  });
}

scheduleEnabledCb.addEventListener('change', () => {
  config.scheduleEnabled = scheduleEnabledCb.checked;
  scheduleDetails.classList.toggle('hidden', !config.scheduleEnabled);
  saveConfig();
});

scheduleStart.addEventListener('change', () => { config.scheduleStart = scheduleStart.value; saveConfig(); });
scheduleEnd.addEventListener('change',   () => { config.scheduleEnd   = scheduleEnd.value;   saveConfig(); });

canvaRefreshInput.addEventListener('change', () => {
  config.canvaRefreshMin = Math.max(1, Math.min(60, parseInt(canvaRefreshInput.value) || 5));
  canvaRefreshInput.value = config.canvaRefreshMin;
  saveConfig();
});

// ── Import / Export ───────────────────────────────────────────────────────────

$('btn-export').addEventListener('click', async () => {
  const data = await chrome.storage.local.get('config');
  const json = JSON.stringify(data.config, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = 'wee-rotate-config.json';
  a.click(); URL.revokeObjectURL(url);
});

$('btn-import').addEventListener('click', () => $('import-file').click());

$('import-file').addEventListener('change', async e => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const raw = JSON.parse(await file.text());
    if (!Array.isArray(raw.urls)) throw new Error('Format invalide');
    config = migrateConfig(raw);
    await saveConfig();
    await refresh();
    alert('Configuration importée avec succès.');
  } catch (err) {
    alert('Erreur import : ' + err.message);
  }
  e.target.value = '';
});

$('btn-reset').addEventListener('click', async () => {
  if (!confirm('Réinitialiser toute la configuration ?')) return;
  config = migrateConfig(null);
  await saveConfig();
  chrome.runtime.sendMessage({ action: 'stopTimer' }).catch(() => {});
  await refresh();
});

// ── Debug ─────────────────────────────────────────────────────────────────────

debugToggle.addEventListener('click', async () => {
  const open = debugBox.classList.toggle('open');
  if (open) await refreshDebugLogs();
});
debugClear.addEventListener('click', async () => {
  await chrome.storage.local.set({ debugLogs: [] });
  debugLog.textContent = '(logs effacés)';
});
async function refreshDebugLogs() {
  try {
    const data = await chrome.storage.local.get('debugLogs');
    debugLog.textContent = (data.debugLogs || []).join('\n') || '(aucun log)';
    debugBox.scrollTop = debugBox.scrollHeight;
  } catch { debugLog.textContent = '(erreur)'; }
}

// ── Remote info ───────────────────────────────────────────────────────────────

async function refreshRemoteInfo() {
  try {
    const data = await chrome.storage.local.get('remoteInfo');
    const info = data?.remoteInfo;
    const dot    = $('remote-dot');
    const online = $('remote-online');
    const offlineHint = $('remote-offline-hint');
    const statusTxt   = $('remote-status-txt');

    if (info?.connected && info?.ip) {
      const url = `http://${info.ip}:${info.http_port}/`;
      dot.className = 'remote-dot remote-dot-on';
      statusTxt.textContent = 'Serveur connecté';
      statusTxt.style.color = 'var(--green-txt)';
      $('remote-url-box').textContent = url;
      online.classList.remove('hidden');
      offlineHint.classList.add('hidden');
      const qrDiv = $('remote-qr');
      if (qrDiv && !qrDiv.dataset.loaded) {
        try {
          const resp = await fetch(`http://localhost:${info.http_port}/qr.svg`);
          if (resp.ok) {
            const svgText = await resp.text();
            qrDiv.innerHTML = svgText;
            const svgEl = qrDiv.querySelector('svg');
            if (svgEl) {
              const w = svgEl.getAttribute('width'), h = svgEl.getAttribute('height');
              if (w && h && !svgEl.getAttribute('viewBox'))
                svgEl.setAttribute('viewBox', `0 0 ${w} ${h}`);
              svgEl.removeAttribute('width'); svgEl.removeAttribute('height');
              qrDiv.dataset.loaded = '1';
            }
          } else {
            qrDiv.innerHTML = '<div style="font-size:10px;color:#aaa;padding:12px;text-align:center">pip install qrcode</div>';
            qrDiv.dataset.loaded = '1';
          }
        } catch {
          qrDiv.innerHTML = '<div style="font-size:10px;color:#aaa;padding:12px;text-align:center">QR indisponible</div>';
          qrDiv.dataset.loaded = '1';
        }
      }
    } else {
      dot.className = 'remote-dot remote-dot-off';
      statusTxt.textContent = 'Serveur non détecté';
      statusTxt.style.color = '';
      online.classList.add('hidden');
      offlineHint.classList.remove('hidden');
    }
  } catch {}
}

$('btn-copy-remote').addEventListener('click', async () => {
  const url = $('remote-url-box').textContent;
  if (!url || url === '—') return;
  try {
    await navigator.clipboard.writeText(url);
    const btn = $('btn-copy-remote');
    btn.textContent = '✓ Copié !';
    setTimeout(() => { btn.textContent = '📋 Copier l\'URL'; }, 1500);
  } catch {}
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function flushInputs() {
  urlList.querySelectorAll('.url-row').forEach((row, i) => {
    if (!config.urls[i]) return;
    const n = row.querySelector('.name-input');
    const u = row.querySelector('.url-input');
    if (n) config.urls[i].name = n.value.trim();
    if (u) config.urls[i].url  = u.value.trim();
  });
}

function esc(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
