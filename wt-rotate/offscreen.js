// Offscreen document — manages the WebSocket connection persistently.
// Unlike service workers (killed after 30s idle), offscreen documents
// stay alive as long as the extension is running. This eliminates the
// connect/disconnect cycling caused by the MV3 service worker lifecycle.

let ws = null;
let reconnectTimer = null;

function connect() {
    clearTimeout(reconnectTimer);
    try {
        ws = new WebSocket('ws://localhost:8765');
    } catch {
        reconnectTimer = setTimeout(connect, 3000);
        return;
    }

    ws.onopen = () => ws.send(JSON.stringify({ type: 'extension' }));

    ws.onmessage = evt => {
        let msg;
        try { msg = JSON.parse(evt.data); } catch { return; }
        // Answer application-level pings locally (no need to wake the SW)
        if (msg.type === 'ping') { ws.send(JSON.stringify({ type: 'pong' })); return; }
        // Forward everything else to the background SW (wakes it up if sleeping)
        chrome.runtime.sendMessage({ target: 'background', ...msg }).catch(() => {});
    };

    ws.onclose = () => {
        chrome.runtime.sendMessage({ target: 'background', type: 'ws_disconnected' }).catch(() => {});
        reconnectTimer = setTimeout(connect, 3000);
    };

    ws.onerror = () => {};
}

// Receive outgoing messages from the background SW and forward to the server
chrome.runtime.onMessage.addListener(msg => {
    if (msg.target !== 'offscreen') return;
    if (msg.action === 'sendToServer' && ws?.readyState === WebSocket.OPEN) {
        ws.send(msg.data);
    }
});

connect();
