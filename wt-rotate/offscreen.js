let timerId = null;

chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== 'offscreen') return;

  if (message.action === 'start-timer') {
    if (timerId) clearInterval(timerId);
    timerId = setInterval(() => {
      chrome.runtime.sendMessage({ action: 'rotate', source: 'offscreen' }).catch(() => {});
    }, message.interval * 1000);
  }

  if (message.action === 'stop-timer') {
    if (timerId) { clearInterval(timerId); timerId = null; }
  }
});
