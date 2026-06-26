// Cache du QR (data-URI). Le QR encode une URL+token quasi-fixe : inutile de
// refetch /qr.svg pour chaque onglet à chaque tick du watchdog. TTL 10 min pour
// tolérer un éventuel changement de token au redémarrage du serveur.
let _qrCache = null, _qrCacheAt = 0;
async function getQrDataUri(httpPort) {
  if (_qrCache && Date.now() - _qrCacheAt < 600000) return _qrCache;
  try {
    const resp = await fetch(`http://localhost:${httpPort}/qr.svg`);
    if (resp.ok) {
      const svg = await resp.text();
      _qrCache = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      _qrCacheAt = Date.now();
    }
  } catch {}
  return _qrCache;
}

// injectOverlay: qrSrc is a pre-fetched data-URI (or null to fetch via cache)
async function injectOverlay(tabId, info, qrSrc = null) {
  const controlUrl = info.control_url || `http://${info.ip}:${info.http_port}/`;
  if (qrSrc === null) qrSrc = await getQrDataUri(info.http_port);
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: (qrSrc, ctrlUrl) => {
        document.getElementById('wt-qr')?.remove();
        const el = document.createElement('div');
        el.id = 'wt-qr';
        el.style.cssText = [
          'position:fixed', 'bottom:14px', 'right:14px',
          'z-index:2147483647', 'background:#fff',
          'border-radius:12px', 'padding:8px',
          'box-shadow:0 4px 20px rgba(0,0,0,.22)',
          'cursor:pointer', 'text-align:center',
          'font-family:-apple-system,sans-serif',
          'transition:opacity .2s'
        ].join('!important;') + '!important';
        // Pas d'innerHTML : ctrlUrl/qrSrc viennent du serveur local via l'ack
        // WebSocket. On construit les nœuds et on pose les valeurs en texte/src
        // (jamais en HTML) pour qu'aucune chaîne ne puisse injecter de balise
        // dans la page du kiosque.
        const cap = document.createElement('div');
        cap.textContent = 'REMOTE';
        if (qrSrc) {
          const img = document.createElement('img');
          img.src = qrSrc; img.width = 86; img.height = 86;
          img.style.cssText = 'display:block;border-radius:4px';
          cap.style.cssText = 'font-size:9px;color:#555;margin-top:4px;font-weight:700;letter-spacing:.5px';
          el.append(img, cap);
        } else {
          const u = document.createElement('div');
          u.style.cssText = 'font-size:9px;color:#333;padding:4px 6px;max-width:90px;word-break:break-all;font-weight:600';
          u.textContent = ctrlUrl;
          cap.style.cssText = 'font-size:9px;color:#555;font-weight:700';
          el.append(u, cap);
        }
        el.addEventListener('mouseenter', () => el.style.opacity = '.6');
        el.addEventListener('mouseleave', () => el.style.opacity = '1');
        // N'ouvre que des URL http(s) : empêche un javascript:/data: éventuel
        el.addEventListener('click', () => {
          if (/^https?:\/\//i.test(ctrlUrl)) window.open(ctrlUrl, '_blank');
        });
        document.body?.appendChild(el);
      },
      args: [qrSrc, controlUrl]
    });
  } catch {}
}

// Fetch QR once (cached), then inject into every kiosk tab
async function injectOverlayAll() {
  const data = await chrome.storage.local.get(['config', 'remoteInfo']);
  const config = migrateConfig(data.config);
  const info = data.remoteInfo;
  if (!info?.ip || !config.tabIds.length) return;
  const qrSrc = await getQrDataUri(info.http_port);
  for (const tabId of config.tabIds) {
    await injectOverlay(tabId, info, qrSrc);
  }
}

async function injectYouTubeMaximize(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        if (!document.getElementById('wt-yt-style')) {
          const s = document.createElement('style');
          s.id = 'wt-yt-style';
          s.textContent = [
            'html,body{overflow:hidden!important}',
            'ytd-app,#page-manager{overflow:hidden!important;height:100vh!important}',
            '#masthead-container,ytd-miniguide-renderer{display:none!important}',
            'ytd-page-manager{margin-top:0!important;padding-top:0!important}',
            '#secondary,ytd-watch-next-secondary-results-renderer{display:none!important}',
            '.ytp-chrome-top,.ytp-title,.ytp-gradient-top{opacity:0!important;pointer-events:none!important}',
            'ytd-watch-metadata,#above-the-fold,ytd-above-the-fold-renderer,#actions,#owner,ytd-video-owner-renderer{display:none!important}',
            '.ytp-chrome-bottom,.ytp-gradient-bottom,.ytp-ce-element,.ytp-endscreen-element,.ytp-cards-teaser{display:none!important}',
            '#panels,ytd-engagement-panel-section-list-renderer{display:none!important}',
            'ytd-comments,#comments,#comment-teaser,#below{display:none!important}',
          ].join('');
          document.head.appendChild(s);
        }

        function maximize() {
          const player = document.querySelector('.html5-video-player') ||
                         document.getElementById('movie_player');
          if (!player) return false;
          let el = player.parentElement;
          while (el && el !== document.documentElement) {
            el.style.setProperty('transform',   'none', 'important');
            el.style.setProperty('filter',      'none', 'important');
            el.style.setProperty('contain',     'none', 'important');
            el.style.setProperty('perspective', 'none', 'important');
            el = el.parentElement;
          }
          [['position','fixed'],['top','0'],['left','0'],
           ['width','100vw'],['height','100vh'],
           ['z-index','2147483647'],['background','#000'],['overflow','hidden']
          ].forEach(([p, v]) => player.style.setProperty(p, v, 'important'));
          player.querySelectorAll('.html5-video-container, video').forEach(el => {
            [['position','absolute'],['top','0'],['left','0'],
             ['width','100%'],['height','100%'],
             ['max-width','none'],['max-height','none'],
             ['object-fit','contain'],['margin','0'],['padding','0']
            ].forEach(([p, v]) => el.style.setProperty(p, v, 'important'));
            el.removeAttribute('width'); el.removeAttribute('height');
          });
          return true;
        }

        let t = 0;
        const run = () => { if (!maximize() && ++t < 15) setTimeout(run, 400); };
        run();
        // Une seule boucle de ré-application à la fois : YouTube refire l'event
        // « complete » à chaque navigation SPA ; sans ce garde, les intervalles
        // s'empilaient (plusieurs maximize() toutes les 3 s au lieu d'un seul).
        if (window.__wtYtReapply) clearInterval(window.__wtYtReapply);
        if (window.__wtYtStop)    clearTimeout(window.__wtYtStop);
        window.__wtYtReapply = setInterval(maximize, 3000);
        window.__wtYtStop = setTimeout(() => {
          clearInterval(window.__wtYtReapply);
          window.__wtYtReapply = null;
        }, 120000);
      }
    });
  } catch {}
}
