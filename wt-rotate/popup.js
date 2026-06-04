const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabIds: [], windowId: null
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

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  await refresh();
  startLocalCountdown();
});

// Read directly from storage — no message passing
async function refresh() {
  try {
    const data = await chrome.storage.local.get('config');
    config = data?.config || { ...DEFAULT_CONFIG };
  } catch {
    config = config || { ...DEFAULT_CONFIG };
  }
  renderAll();
}

// Write directly to storage — reliable, no service worker needed
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

    // Save on every keystroke — nothing lost if popup closes
    input.addEventListener('input', () => {
      config.urls[i] = input.value;
      saveConfig();
    });
    // Trim final value on blur / Enter
    input.addEventListener('blur', () => {
      input.value = input.value.trim();
      config.urls[i] = input.value;
      saveConfig();
    });
    input.addEventListener('keydown', e => { if (e.key === 'Enter') input.blur(); });

    row.querySelector('.btn-del').addEventListener('click', () => {
      config.urls.splice(i, 1);
      if (config.currentIndex >= config.urls.filter(u => u?.trim()).length) config.currentIndex = 0;
      saveConfig();
      renderUrls();
    });

    // Drag-to-reorder
    row.addEventListener('dragstart', e => { dragSrcIndex = i; e.dataTransfer.effectAllowed = 'move'; });
    row.addEventListener('dragover',  e => { e.preventDefault(); row.classList.add('drag-over'); });
    row.addEventListener('dragleave', () => row.classList.remove('drag-over'));
    row.addEventListener('drop', e => {
      e.preventDefault(); row.classList.remove('drag-over');
      if (dragSrcIndex === null || dragSrcIndex === i) return;
      const moved = config.urls.splice(dragSrcIndex, 1)[0];
      config.urls.splice(i, 0, moved);
      dragSrcIndex = null;
      saveConfig(); renderUrls();
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

// ── Countdown (visual only) ───────────────────────────────────────────────

function startLocalCountdown() {
  if (countdownTimer) clearInterval(countdownTimer);
  countdownSec = config?.interval || 30;
  countdownTimer = setInterval(async () => {
    if (!config?.active) return;
    countdownSec = Math.max(0, countdownSec - 1);
    statusCnt.textContent = `⏱ Prochain dans ${countdownSec}s`;
    if (countdownSec === 0) {
      countdownSec = config.interval;
      try {
        const data = await chrome.storage.local.get('config');
        if (data?.config) config = data.config;
      } catch {}
      renderUrls();
      updateStatusUI();
    }
  }, 1000);
}

// ── Button handlers ───────────────────────────────────────────────────────

btnAdd.addEventListener('click', () => {
  if (!config) config = { ...DEFAULT_CONFIG };
  config.urls.push('');
  saveConfig();
  renderUrls();
  const inputs = urlList.querySelectorAll('.url-input');
  if (inputs.length) inputs[inputs.length - 1].focus();
});

slider.addEventListener('input', () => {
  config.interval = parseInt(slider.value);
  intervalN.value = config.interval;
  countdownSec = config.interval;
  saveConfig();
});

intervalN.addEventListener('change', () => {
  config.interval = Math.max(5, Math.min(86400, parseInt(intervalN.value) || 30));
  intervalN.value = config.interval;
  slider.value    = Math.min(config.interval, 300);
  countdownSec    = config.interval;
  saveConfig();
});

btnStart.addEventListener('click', async () => {
  flushInputs();
  await saveConfig();   // wait for write before background reads it
  const res = await chrome.runtime.sendMessage({ action: 'start', fullscreen: false });
  if (!res?.success) { alert(res?.error || 'Erreur de démarrage'); return; }
  await refresh();
  countdownSec = config.interval;
  startLocalCountdown();
});

btnStop.addEventListener('click', async () => {
  await chrome.runtime.sendMessage({ action: 'stop' });
  await refresh();
});

btnFs.addEventListener('click', async () => {
  flushInputs();
  await saveConfig();   // wait for write before background reads it
  const res = await chrome.runtime.sendMessage({ action: 'start', fullscreen: true });
  if (!res?.success) { alert(res?.error || 'Erreur de démarrage'); return; }
  await refresh();
  countdownSec = config.interval;
  startLocalCountdown();
});

btnNext.addEventListener('click', async () => {
  const res = await chrome.runtime.sendMessage({ action: 'next' });
  if (res?.config) config = res.config;
  countdownSec = config.interval;
  renderUrls();
  updateStatusUI();
});

// ── Helpers ───────────────────────────────────────────────────────────────

function flushInputs() {
  urlList.querySelectorAll('.url-input').forEach((inp, i) => {
    if (config.urls[i] !== undefined) config.urls[i] = inp.value.trim();
  });
}

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
