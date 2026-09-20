/* The action opens Chrome's native side panel. No remote scripts or API calls. */
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || message?.type !== 'CAPTURE_CURRENT_CONFIGURATION') return false;
  (async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = new URL(tab?.url || 'about:blank');
    if (url.protocol !== 'https:' || url.hostname !== 'www.tesla.cn' || url.pathname !== '/modely/design') {
      throw new Error('仅支持 https://www.tesla.cn/modely/design。请切回该官网标签页。');
    }
    // Injection is top-frame only, and capture.js validates scope again before reading DOM.
    await chrome.scripting.executeScript({ target: { tabId: tab.id, frameIds: [0] }, files: ['capture.js'] });
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, frameIds: [0] },
      func: async () => globalThis.TessCapture.capture(),
    });
    return { ok: true, tab_id: tab.id, capture: results[0]?.result };
  })().then(respond).catch(error => respond({ ok: false, error: error.message }));
  return true;
});
