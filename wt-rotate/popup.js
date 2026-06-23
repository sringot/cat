const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabIds: [], windowId: null,
  scheduleEnabled: false, scheduleStart: '08:00', scheduleEnd: '18:00',
  scheduleDays: [1, 2, 3, 4, 5], lastScheduleState: false,
  remotePaused: false, remoteTabId: null, remoteUntil: null,
  canvaRefreshMin: 5,
  tabRefreshHours: 4
};

let config        = null;
let progressTimer = null;
let dragSrcIndex  = null;
let toastTimer    = null;

const $ = id => document.getElementById(id);

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  initTabs();
  initDayButtons();
  wireButtons();
  await refresh();
});

function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.page').forEach(p => p.classList.remove('show'));
      btn.classList.add('active');
      $('tab-' + btn.dataset.tab).classList.add('show');
    });
  });
}

function initDayButtons() {
  document.querySelectorAll('.day-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (!config) return;
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

function wireButtons() {
  $('b-main').addEventListener('click', onMainButton);
  $('b-prev').addEventListener('click', onPrev);
  $('b-next-t').addEventListener('click', onNext);

  $('btn-add').addEventListener('click', () => {
    if (!config) config = migrateConfig(null);
    config.urls.push({ url: '', name: '', interval: null });
    saveConfig(); renderUrls();
    const inputs = $('url-list').querySelectorAll('.url-input');
    if (inputs.length) inputs[inputs.length - 1].focus();
  });

  $('slider').addEventListener('input', () => {
    config.interval = parseInt($('slider').value);
    $('interval').value = config.interval;
    saveConfig(); renderUrls();
  });
  $('interval').addEventListener('change', () => {
    config.interval = Math.max(5, Math.min(86400, parseInt($('interval').value) || 30));
    $('interval').value = config.interval;
    $('slider').value   = Math.min(config.interval, 300);
    saveConfig(); renderUrls();
  });

  $('tab-refresh').addEventListener('change', () => {
    config.tabRefreshHours = Math.max(0, Math.min(24, parseInt($('tab-refresh').value) || 0));
    $('tab-refresh').value = config.tabRefreshHours;
    saveConfig();
  });

  $('canva-refresh').addEventListener('change', () => {
    config.canvaRefreshMin = Math.max(1, Math.min(60, parseInt($('canva-refresh').value) || 5));
    $('canva-refresh').value = config.canvaRefreshMin;
    saveConfig();
  });

  $('schedule-enabled').addEventListener('change', () => {
    config.scheduleEnabled = $('schedule-enabled').checked;
    $('schedule-details').classList.toggle('show', config.scheduleEnabled);
    saveConfig();
  });
  $('schedule-start').addEventListener('change', () => { config.scheduleStart = $('schedule-start').value; saveConfig(); });
  $('schedule-end').addEventListener('change',   () => { config.scheduleEnd   = $('schedule-end').value;   saveConfig(); });

  $('btn-export').addEventListener('click', exportConfig);
  $('btn-import').addEventListener('click', () => $('import-file').click());
  $('import-file').addEventListener('change', importConfig);
  $('btn-reset').addEventListener('click', resetConfig);

  $('debug-toggle').addEventListener('click', async () => {
    const open = $('debug-box').classList.toggle('open');
    if (open) await refreshDebugLogs();
  });
  $('debug-clear').addEventListener('click', async () => {
    await chrome.storage.local.set({ debugLogs: [] });
    $('debug-log').textContent = '(logs effacés)';
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (changes.remoteInfo) {
      const qrDiv = $('remote-qr');
      if (qrDiv) qrDiv.dataset.loaded = '';
      refreshRemoteInfo();
    }
  });
}

// ── Config ────────────────────────────────────────────────────────────────────

function migrateConfig(raw) {
  // Copie profonde des tableaux : un push sur config.urls ne doit jamais
  // polluer DEFAULT_CONFIG (sinon « Réinit. » restaure une config sale)
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
  $('slider').value        = Math.min(config.interval, 300);
  $('interval').value      = config.interval;
  $('tab-refresh').value   = config.tabRefreshHours ?? 4;
  $('canva-refresh').value = config.canvaRefreshMin  || 5;
  renderSchedule();
  updateStatusUI();
  refreshRemoteInfo();
}

// ── URL list ──────────────────────────────────────────────────────────────────

function renderUrls() {
  const urlList = $('url-list');
  urlList.innerHTML = '';

  if (!config.urls.length) {
    urlList.innerHTML = '<div class="empty-hint">Aucune page — cliquez sur + pour commencer</div>';
    $('pl-count').textContent = '';
    return;
  }

  updatePlCount();

  config.urls.forEach((entry, i) => {
    const isActive    = config.active && i === config.currentIndex;
    const hasCustomInt = entry.interval != null;
    const origUrl     = entry.url || '';   // URL au rendu — pour détecter une édition en place
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
        <div class="url-dur-wrap">
          <button class="url-dur-btn${hasCustomInt ? ' on' : ''}" title="Durée personnalisée">⏱</button>
          <input class="url-int" type="number"
                 value="${parseInt(entry.interval) || parseInt(config.interval) || 30}"
                 min="5" max="86400" style="display:${hasCustomInt ? '' : 'none'}">
          <span class="url-int-s" style="display:${hasCustomInt ? '' : 'none'}">s</span>
        </div>
      </div>`;

    const nameInp = row.querySelector('.name-input');
    const urlInp  = row.querySelector('.url-input');
    const durBtn  = row.querySelector('.url-dur-btn');
    const intInp  = row.querySelector('.url-int');
    const intS    = row.querySelector('.url-int-s');

    nameInp.addEventListener('input', () => { config.urls[i].name = nameInp.value; saveConfig(); });
    nameInp.addEventListener('blur',  () => { config.urls[i].name = nameInp.value.trim(); nameInp.value = config.urls[i].name; saveConfig(); });
    nameInp.addEventListener('keydown', e => { if (e.key === 'Enter') urlInp.focus(); });

    urlInp.addEventListener('input', () => { config.urls[i].url = urlInp.value; saveConfig(); updatePlCount(); });
    urlInp.addEventListener('blur',  () => {
      const v = urlInp.value.trim();
      // URL changée en place pendant une rotation active : tabIds pointe encore
      // sur l'ancienne page → on demande au watchdog de réaligner les onglets.
      if (config.active && v !== origUrl) config.tabsDirty = true;
      config.urls[i].url = v; urlInp.value = v; saveConfig();
    });
    urlInp.addEventListener('keydown', e => { if (e.key === 'Enter') urlInp.blur(); });

    durBtn.addEventListener('click', () => {
      if (config.urls[i].interval != null) {
        config.urls[i].interval = null;
        durBtn.classList.remove('on');
        intInp.style.display = 'none'; intS.style.display = 'none';
      } else {
        config.urls[i].interval = config.interval;
        intInp.value = config.interval;
        durBtn.classList.add('on');
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
      // Réordonnancement en pleine rotation : tabIds n'est pas touché ici (c'est
      // le SW qui les gère) → on signale au watchdog de reconstruire l'alignement.
      if (config.active) config.tabsDirty = true;
      dragSrcIndex = null; saveConfig(); renderUrls();
    });
    row.addEventListener('dragend', () => {
      dragSrcIndex = null;
      urlList.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    });

    urlList.appendChild(row);
  });
}

function updatePlCount() {
  const n = config.urls.filter(u => u?.url?.trim()).length;
  $('pl-count').textContent = config.urls.length ? n + ' page' + (n > 1 ? 's' : '') : '';
}

// ── Status UI ─────────────────────────────────────────────────────────────────

function updateStatusUI() {
  const on     = config.active;
  const paused = config.remotePaused;

  $('chip').classList.toggle('on', on);
  $('chip-txt').textContent = on ? (paused ? 'En pause' : 'Actif') : 'Arrêté';

  $('prog-wrap').classList.toggle('hidden', !on || paused);

  $('ic-play').style.display = on ? 'none' : '';
  $('ic-stop').style.display = on ? ''     : 'none';

  const nowLbl = $('now-lbl');
  if (on) {
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    const cur = activeUrls[config.currentIndex % Math.max(activeUrls.length, 1)];
    const name = cur?.name || cur?.url || '—';
    nowLbl.classList.toggle('live', !paused);
    $('now-lbl-txt').textContent = paused ? 'En pause' : 'En cours';
    $('now-name').textContent    = name;
    $('now-url').textContent     = cur?.url || '';
    setArt(name);
    if (!paused) {
      const totalSec  = config.currentAlarmSec || cur?.interval || config.interval;
      let   remainSec = totalSec;
      if (config.lastAlarmTime)
        remainSec = Math.max(1, totalSec - (Date.now() - config.lastAlarmTime) / 1000);
      startProgressBar(remainSec, totalSec);
    } else {
      stopProgressBar();
    }
  } else {
    nowLbl.classList.remove('live');
    $('now-lbl-txt').textContent = 'Arrêté';
    $('now-name').textContent    = '—';
    $('now-url').textContent     = '';
    setArt(null);
    stopProgressBar();
  }

  renderHomeCards();
}

function renderHomeCards() {
  const on         = config.active;
  const activeUrls = config.urls.filter(u => u?.url?.trim());
  const nextCard   = $('card-next');
  const stopCard   = $('card-stopped');

  if (on && activeUrls.length >= 2) {
    const nextIdx = (config.currentIndex + 1) % activeUrls.length;
    const next    = activeUrls[nextIdx];
    const name    = next?.name || next?.url || '—';
    const art     = $('next-art');
    art.textContent = name.trim().charAt(0).toUpperCase() || '—';
    let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
    art.style.background = `linear-gradient(140deg,hsl(${h},34%,72%),hsl(${h},40%,52%))`;
    $('next-name').textContent = name;
    $('next-url').textContent  = next?.url || '';
    nextCard.style.display = '';
    stopCard.style.display = 'none';
  } else if (!on) {
    nextCard.style.display = 'none';
    const n = activeUrls.length;
    if (n > 0) {
      $('stopped-title').textContent = n + ' page' + (n > 1 ? 's' : '') + ' configurée' + (n > 1 ? 's' : '');
      $('stopped-sub').textContent   = 'Appuyez sur ▶ pour démarrer la rotation';
    } else {
      $('stopped-title').textContent = 'Aucune page configurée';
      $('stopped-sub').textContent   = 'Allez dans Playlist pour ajouter des pages';
    }
    stopCard.style.display = '';
  } else {
    nextCard.style.display = 'none';
    stopCard.style.display = 'none';
  }
}

// « pochette » : teinte stable dérivée du nom de l'écran
function setArt(name) {
  const a = $('art');
  if (!name) {
    a.textContent = '—';
    a.style.background = 'linear-gradient(140deg,#C9C7C2,#8B8A86)';
    return;
  }
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  a.textContent = name.trim().charAt(0).toUpperCase() || '—';
  a.style.background = `linear-gradient(140deg, hsl(${h},34%,72%), hsl(${h},40%,52%))`;
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function startProgressBar(remainSec, totalSec) {
  stopProgressBar();
  const bar = $('prog-bar');
  const pct = (remainSec / totalSec) * 100;
  bar.style.transition = 'none';
  bar.style.width = pct + '%';
  bar.offsetWidth; // force reflow
  bar.style.transition = `width ${remainSec}s linear`;
  bar.style.width = '0%';
  progressTimer = setTimeout(async () => {
    try {
      const d = await chrome.storage.local.get('config');
      if (d?.config) { config = migrateConfig(d.config); renderAll(); }
    } catch {}
  }, remainSec * 1000);
}

function stopProgressBar() {
  if (progressTimer) { clearTimeout(progressTimer); progressTimer = null; }
  const bar = $('prog-bar');
  bar.style.transition = 'none';
  bar.style.width = '0%';
}

// ── Transport ─────────────────────────────────────────────────────────────────

async function onMainButton() {
  if (config.active) {
    const res = await chrome.runtime.sendMessage({ action: 'stopRotation' });
    if (res?.ok) await refresh();
  } else {
    flushInputs();
    await saveConfig();
    const activeUrls = config.urls.filter(u => u?.url?.trim());
    if (!activeUrls.length) { showToast('Ajoutez au moins une URL.'); return; }
    $('b-main').disabled = true;
    try {
      const res = await chrome.runtime.sendMessage({ action: 'startRotation' });
      if (res?.ok) {
        await refresh();
      } else {
        const msg = res?.error === 'no_urls' ? 'Ajoutez au moins une URL.' : (res?.error || 'Erreur');
        showToast(msg);
      }
    } finally {
      $('b-main').disabled = false;
    }
  }
}

async function onNext() {
  const res = await chrome.runtime.sendMessage({ action: 'nextUrl' });
  if (res?.ok) await refresh();
  else if (res?.error === 'not_running') showToast('La rotation n\'est pas active.');
}

async function onPrev() {
  const res = await chrome.runtime.sendMessage({ action: 'prevUrl' });
  if (res?.ok) await refresh();
  else if (res?.error === 'not_running') showToast('La rotation n\'est pas active.');
}

// ── Schedule ──────────────────────────────────────────────────────────────────

function renderSchedule() {
  $('schedule-enabled').checked = !!config.scheduleEnabled;
  $('schedule-details').classList.toggle('show', !!config.scheduleEnabled);
  $('schedule-start').value = config.scheduleStart || '08:00';
  $('schedule-end').value   = config.scheduleEnd   || '18:00';
  const days = config.scheduleDays || [1, 2, 3, 4, 5];
  document.querySelectorAll('.day-btn').forEach(btn => {
    btn.classList.toggle('on', days.includes(parseInt(btn.dataset.day)));
  });
}

// ── Import / Export ───────────────────────────────────────────────────────────

async function exportConfig() {
  const data = await chrome.storage.local.get('config');
  const json = JSON.stringify(data.config, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = 'wee-rotate-config.json';
  a.click(); URL.revokeObjectURL(url);
}

async function importConfig(e) {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const raw = JSON.parse(await file.text());
    if (!Array.isArray(raw.urls)) throw new Error('Format invalide');
    config = migrateConfig(raw);
    await saveConfig();
    await refresh();
    showToast('Configuration importée.');
  } catch (err) {
    showToast('Erreur import : ' + err.message);
  }
  e.target.value = '';
}

async function resetConfig() {
  if (!confirm('Réinitialiser toute la configuration ?')) return;
  config = migrateConfig(null);
  await saveConfig();
  chrome.runtime.sendMessage({ action: 'stopRotation' }).catch(() => {});
  await refresh();
}

// ── Debug ─────────────────────────────────────────────────────────────────────

async function refreshDebugLogs() {
  try {
    const data = await chrome.storage.local.get('debugLogs');
    $('debug-log').textContent = (data.debugLogs || []).join('\n') || '(aucun log)';
    $('debug-box').scrollTop = $('debug-box').scrollHeight;
  } catch { $('debug-log').textContent = '(erreur)'; }
}

// ── Remote info ───────────────────────────────────────────────────────────────

async function refreshRemoteInfo() {
  try {
    const data = await chrome.storage.local.get('remoteInfo');
    const info = data?.remoteInfo;

    if (info?.connected && info?.ip) {
      const url = info.control_url || `http://${info.ip}:${info.http_port}/`;
      $('remote-dot').classList.add('on');
      $('remote-status-txt').textContent = 'Serveur connecté';
      $('remote-status-txt').style.color = 'var(--green)';
      $('remote-online').classList.remove('hidden');
      $('remote-offline-hint').classList.add('hidden');
      const qrDiv = $('remote-qr');
      if (qrDiv && !qrDiv.dataset.loaded) {
        try {
          const resp = await fetch(`http://localhost:${info.http_port}/qr.svg`);
          if (resp.ok) {
            qrDiv.innerHTML = await resp.text();
            const svgEl = qrDiv.querySelector('svg');
            if (svgEl) {
              const w = svgEl.getAttribute('width'), h = svgEl.getAttribute('height');
              if (w && h && !svgEl.getAttribute('viewBox'))
                svgEl.setAttribute('viewBox', `0 0 ${w} ${h}`);
              svgEl.removeAttribute('width'); svgEl.removeAttribute('height');
            }
          } else {
            qrDiv.innerHTML = '<div style="font-size:10px;color:#aaa;padding:12px;text-align:center">pip install qrcode</div>';
          }
          qrDiv.dataset.loaded = '1';
        } catch {
          qrDiv.innerHTML = '<div style="font-size:10px;color:#aaa;padding:12px;text-align:center">QR indisponible</div>';
          qrDiv.dataset.loaded = '1';
        }
      }
    } else {
      $('remote-dot').classList.remove('on');
      $('remote-status-txt').textContent = 'Non détecté';
      $('remote-status-txt').style.color = '';
      $('remote-online').classList.add('hidden');
      $('remote-offline-hint').classList.remove('hidden');
    }
  } catch {}
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(msg) {
  let t = $('__toast');
  if (!t) {
    t = document.createElement('div');
    t.id = '__toast';
    Object.assign(t.style, {
      position: 'fixed', bottom: '14px', left: '50%', transform: 'translateX(-50%)',
      background: 'rgba(0,0,0,.82)', color: '#fff', borderRadius: '20px',
      padding: '7px 16px', fontSize: '12px', fontWeight: '500',
      zIndex: '9999', pointerEvents: 'none', transition: 'opacity .2s', opacity: '0',
    });
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity = '1';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.opacity = '0'; }, 2500);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function flushInputs() {
  $('url-list').querySelectorAll('.url-row').forEach((row, i) => {
    if (!config.urls[i]) return;
    const n = row.querySelector('.name-input');
    const u = row.querySelector('.url-input');
    if (n) config.urls[i].name = n.value.trim();
    if (u) config.urls[i].url  = u.value.trim();
  });
}

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
