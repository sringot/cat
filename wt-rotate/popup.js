const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabId: null, windowId: null
};

let config = null;
let countdownSec = 0;
let countdownTimer = null;
let dragSrcIndex = null;

const $ = id => document.getElementById(id);
const badge     = $('badge');
const statusBar = $('status-bar');
const statusCur = $('status-current');
const statusCnt = $('status-countdown');
const urlList   = $('url-list');
const btnAdd    = $('btn-add');
const slider    = $('slider');
const intervalN = $('interval');
const btnStart  = $('btn-start');
const btnStop   = $('btn-stop');
const btnFs     = $('btn-fs');
const btnNext   = $('btn-next');

document.addEventListener('DOMContentLoaded', async () => {
  await refresh();
  startLocalCountdown();
});

async function refresh() {
  try {
    const data = await chrome.storage.local.get('config');
    config = data?.config || { ...DEFAULT_CONFIG };
  } catch {
    config = config || { ...DEFAULT_CONFIG };
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
  updateStatusUI();
}

// ── URL list ──────────────────────────────────────────────────────────────

function renderUrls() {
  urlList.innerHTML = '';
  if (!config.urls.length) {
    urlList.innerHTML = '<div class="empty-hint">Aucune URL — cliquez sur + pour commencer</div>';
    return;
  }
  config.urls.forEach((url, i) => {
    const row = document.createElement('div');
    row.className = 'url-row' + (config.active && i === config.currentIndex ? ' active-url' : '');
    row.draggable = true;
    row.innerHTML = `
      <span class="drag-handle">⠿</span>
      <span class="url-num">${i + 1}</span>
      <input class="url-input" type="text" value="${esc(url)}" placeholder="https://exemple.com" spellcheck="false">
      <button class="btn-del" title="Supprimer">✕</button>
    `;
    const input = row.querySelector('.url-input');
    input.addEventListener('input', () => { config.urls[i] = input.value; saveConfig(); });
    input.addEventListener('blur',  () => { input.value = input.value.trim(); config.urls[i] = input.value; saveConfig(); });
    input.addEventListener('keydown', e => { if (e.key === 'Enter') input.blur(); });
    row.querySelector('.btn-del').addEventListener('click', () => {
      config.urls.splice(i, 1);
      if (config.currentIndex >= config.urls.filter(u => u?.trim()).length) config.currentIndex = 0;
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

// ── Status ────────────────────────────────────────────────────────────────

function updateStatusUI() {
  const on = config.active;
  badge.className   = 'badge ' + (on ? 'badge-active' : 'badge-stopped');
  badge.textContent = on ? 'Actif' : 'Arrêté';
  btnStart.classList.toggle('hidden', on);
  btnStop.classList.toggle('hidden', !on);
  btnNext.classList.toggle('hidden', !on);
  statusBar.classList.toggle('visible', on);
  if (on) {
    const urls = config.urls.filter(u => u?.trim());
    statusCur.textContent = '▶ ' + (urls[config.currentIndex % Math.max(urls.length, 1)] || '');
    statusCnt.textContent = `⏱ Prochain dans ${countdownSec}s`;
  }
}

// ── Countdown ─────────────────────────────────────────────────────────────

function startLocalCountdown() {
  if (countdownTimer) clearInterval(countdownTimer);
  countdownSec = config?.interval || 30;
  countdownTimer = setInterval(async () => {
    if (!config?.active) return;
    countdownSec = Math.max(0, countdownSec - 1);
    statusCnt.textContent = `⏱ Prochain dans ${countdownSec}s`;
    if (countdownSec === 0) {
      countdownSec = config.interval;
      try { const d = await chrome.storage.local.get('config'); if (d?.config) config = d.config; } catch {}
      renderUrls(); updateStatusUI();
    }
  }, 1000);
}

// ── Démarrage — 1 onglet, navigation par URL ──────────────────────────────

async function startRotation(fullscreen) {
  try {
    flushInputs();
    await saveConfig();

    const activeUrls = config.urls.filter(u => u?.trim());
    if (!activeUrls.length) {
      alert('Ajoutez au moins une URL avant de démarrer.');
      return;
    }

    // Vérifier si la fenêtre existe encore
    let winExists = false;
    if (config.windowId) {
      try { await chrome.windows.get(config.windowId); winExists = true; } catch {}
    }

    if (!winExists) {
      // Ouvrir 1 seul onglet
      const win = await chrome.windows.create({
        url: activeUrls[0],
        state: fullscreen ? 'fullscreen' : 'maximized'
      });
      if (!win?.tabs?.[0]?.id) {
        alert('Impossible d\'ouvrir la fenêtre de rotation.');
        return;
      }
      config.tabId    = win.tabs[0].id;
      config.windowId = win.id;
    } else {
      // Réutiliser l'onglet existant, recharger la 1re URL
      if (config.tabId) {
        try { await chrome.tabs.update(config.tabId, { url: activeUrls[0] }); } catch {}
      }
      if (fullscreen) await chrome.windows.update(config.windowId, { state: 'fullscreen' });
    }

    config.currentIndex = 0;
    config.active = true;
    await saveConfig();

    // Démarrer le timer dans le background
    chrome.runtime.sendMessage({ action: 'startTimer', interval: config.interval }).catch(() => {});

    await refresh();
    countdownSec = config.interval;
    startLocalCountdown();

  } catch (err) {
    alert('Erreur : ' + (err?.message || String(err)));
  }
}

btnStart.addEventListener('click', () => startRotation(false));
btnFs.addEventListener('click',    () => startRotation(true));

btnStop.addEventListener('click', async () => {
  config.active = false;
  await saveConfig();
  chrome.runtime.sendMessage({ action: 'stopTimer' }).catch(() => {});
  await refresh();
});

btnNext.addEventListener('click', async () => {
  const activeUrls = config.urls.filter(u => u?.trim());
  if (!config.tabId || !activeUrls.length) return;
  const next = (config.currentIndex + 1) % activeUrls.length;
  try { await chrome.tabs.update(config.tabId, { url: activeUrls[next] }); } catch {}
  config.currentIndex = next;
  await saveConfig();
  countdownSec = config.interval;
  renderUrls(); updateStatusUI();
});

btnAdd.addEventListener('click', () => {
  if (!config) config = { ...DEFAULT_CONFIG };
  config.urls.push('');
  saveConfig(); renderUrls();
  const inputs = urlList.querySelectorAll('.url-input');
  if (inputs.length) inputs[inputs.length - 1].focus();
});

slider.addEventListener('input', () => {
  config.interval = parseInt(slider.value);
  intervalN.value = config.interval;
  countdownSec    = config.interval;
  saveConfig();
});

intervalN.addEventListener('change', () => {
  config.interval = Math.max(5, Math.min(86400, parseInt(intervalN.value) || 30));
  intervalN.value = config.interval;
  slider.value    = Math.min(config.interval, 300);
  countdownSec    = config.interval;
  saveConfig();
});

function flushInputs() {
  urlList.querySelectorAll('.url-input').forEach((inp, i) => {
    if (config.urls[i] !== undefined) config.urls[i] = inp.value.trim();
  });
}

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
