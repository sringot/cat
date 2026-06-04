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

const DEFAULT_CONFIG = {
  urls: [], interval: 30, currentIndex: 0, active: false, tabIds: [], windowId: null
};

async function refresh() {
  try {
    const res = await msg({ action: 'getConfig' });
    config = res?.config || DEFAULT_CONFIG;
  } catch {
    config = config || DEFAULT_CONFIG;
  }
  renderAll();
}

function renderAll() {
  renderUrls();
  slider.value    = Math.min(config.interval, 300);
  intervalN.value = config.interval;
  updateStatusUI();
}

// ── URL list rendering ────────────────────────────────────────────────────

function renderUrls() {
  urlList.innerHTML = '';

  if (config.urls.length === 0) {
    urlList.innerHTML = '<div class="empty-hint">Aucune URL — cliquez sur + pour commencer</div>';
    return;
  }

  const activeUrls = config.urls.filter(u => u?.trim());
  const activeIdx  = config.active ? config.currentIndex % Math.max(activeUrls.length, 1) : -1;

  config.urls.forEach((url, i) => {
    const row = document.createElement('div');
    row.className = 'url-row' + (config.active && i === activeIdx ? ' active-url' : '');
    row.draggable = true;
    row.dataset.i = i;

    row.innerHTML = `
      <span class="drag-handle" title="Glisser pour réordonner">⠿</span>
      <span class="url-num">${i + 1}</span>
      <input class="url-input" type="text" value="${esc(url)}" placeholder="https://exemple.com" spellcheck="false">
      <button class="btn-del" data-i="${i}" title="Supprimer">✕</button>
    `;

    const input = row.querySelector('.url-input');
    // Save on every keystroke so nothing is lost if the popup closes without blur
    input.addEventListener('input', () => {
      config.urls[i] = input.value;
      saveConfig();
    });
    // On blur/Enter, trim whitespace and do a final save
    input.addEventListener('blur', () => {
      const trimmed = input.value.trim();
      input.value = trimmed;
      config.urls[i] = trimmed;
      saveConfig();
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') input.blur();
    });

    row.querySelector('.btn-del').addEventListener('click', () => {
      config.urls.splice(i, 1);
      if (config.currentIndex >= config.urls.filter(u => u?.trim()).length) {
        config.currentIndex = 0;
      }
      saveConfig();
      renderUrls();
    });

    // Drag & drop reordering
    row.addEventListener('dragstart', e => {
      dragSrcIndex = i;
      e.dataTransfer.effectAllowed = 'move';
    });
    row.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      row.classList.add('drag-over');
    });
    row.addEventListener('dragleave', () => row.classList.remove('drag-over'));
    row.addEventListener('drop', e => {
      e.preventDefault();
      row.classList.remove('drag-over');
      if (dragSrcIndex === null || dragSrcIndex === i) return;
      const moved = config.urls.splice(dragSrcIndex, 1)[0];
      config.urls.splice(i, 0, moved);
      dragSrcIndex = null;
      saveConfig();
      renderUrls();
    });
    row.addEventListener('dragend', () => {
      dragSrcIndex = null;
      urlList.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    });

    urlList.appendChild(row);
  });
}

// ── Status UI ─────────────────────────────────────────────────────────────

function updateStatusUI() {
  const on = config.active;

  badge.className   = 'badge ' + (on ? 'badge-active' : 'badge-stopped');
  badge.textContent = on ? 'Actif' : 'Arrêté';

  btnStart.classList.toggle('hidden', on);
  btnStop.classList.toggle('hidden', !on);
  btnNext.classList.toggle('hidden', !on);
  statusBar.classList.toggle('visible', on);

  if (on) {
    const activeUrls = config.urls.filter(u => u?.trim());
    const cur = activeUrls[config.currentIndex % Math.max(activeUrls.length, 1)] || '';
    statusCur.textContent = '▶ ' + cur;
    statusCnt.textContent = `⏱ Prochain dans ${countdownSec}s`;
  }
}

// ── Local countdown (visual only) ────────────────────────────────────────

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
        const res = await msg({ action: 'getConfig' });
        if (res?.config) config = res.config;
      } catch {}
      renderUrls();
      updateStatusUI();
    }
  }, 1000);
}

// ── Event handlers ────────────────────────────────────────────────────────

btnAdd.addEventListener('click', () => {
  if (!config) config = DEFAULT_CONFIG;
  config.urls.push('');
  saveConfig();
  renderUrls();
  const inputs = urlList.querySelectorAll('.url-input');
  if (inputs.length) inputs[inputs.length - 1].focus();
});

slider.addEventListener('input', () => {
  const v = parseInt(slider.value);
  intervalN.value = v;
  config.interval = v;
  countdownSec = v;
  saveConfig();
});

intervalN.addEventListener('change', () => {
  const v = Math.max(5, Math.min(86400, parseInt(intervalN.value) || 30));
  intervalN.value = v;
  slider.value    = Math.min(v, 300);
  config.interval = v;
  countdownSec    = v;
  saveConfig();
});

btnStart.addEventListener('click', async () => {
  flushInputs();
  await saveConfig();
  const res = await msg({ action: 'start', fullscreen: false });
  if (!res?.success) { alert(res?.error || 'Erreur de démarrage'); return; }
  await refresh();
  countdownSec = config.interval;
  startLocalCountdown();
});

btnStop.addEventListener('click', async () => {
  await msg({ action: 'stop' });
  await refresh();
});

btnFs.addEventListener('click', async () => {
  flushInputs();
  await saveConfig();
  const res = await msg({ action: 'start', fullscreen: true });
  if (!res?.success) { alert(res?.error || 'Erreur de démarrage'); return; }
  await refresh();
  countdownSec = config.interval;
  startLocalCountdown();
});

btnNext.addEventListener('click', async () => {
  const res = await msg({ action: 'next' });
  if (res.config) config = res.config;
  countdownSec = config.interval;
  renderUrls();
  updateStatusUI();
});

// ── Helpers ───────────────────────────────────────────────────────────────

function msg(payload) {
  return chrome.runtime.sendMessage(payload);
}

function saveConfig() {
  return msg({ action: 'setConfig', config });
}

function flushInputs() {
  urlList.querySelectorAll('.url-input').forEach((inp, i) => {
    if (config.urls[i] !== undefined) config.urls[i] = inp.value.trim();
  });
}

function esc(s) {
  return (s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
