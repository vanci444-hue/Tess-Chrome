/* The action opens Chrome's native side panel. No remote scripts or API calls. */
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);

async function teslaDesignTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = new URL(tab?.url || "about:blank");
  if (url.protocol !== "https:" || url.hostname !== "www.tesla.cn" || url.pathname !== "/modely/design") {
    throw new Error("仅支持 https://www.tesla.cn/modely/design。请切回该官网标签页。");
  }
  return tab;
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return false;
  if (message?.type === "CAPTURE_CURRENT_CONFIGURATION") {
    (async () => {
      const tab = await teslaDesignTab();
      await chrome.scripting.executeScript({ target: { tabId: tab.id, frameIds: [0] }, files: ["capture.js"] });
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id, frameIds: [0] },
        func: async () => globalThis.TessCapture.capture(),
      });
      return { ok: true, tab_id: tab.id, capture: results[0]?.result };
    })().then(respond).catch((error) => respond({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "OPEN_TESLA_FINANCE") {
    (async () => {
      const tab = await teslaDesignTab();
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id, frameIds: [0] },
        func: () => {
          const el = [...document.querySelectorAll("a,button,[role='button']")].find((node) =>
            /查看金融方案/.test(node.innerText || node.textContent || ""),
          );
          if (!el) throw new Error("当前页没有「查看金融方案」，请先打开 Model Y 配置器。");
          el.click();
          return true;
        },
      });
      if (!results[0]?.result) throw new Error(results[0]?.error || "无法打开官网金融方案。");
      return { ok: true };
    })().then(respond).catch((error) => respond({ ok: false, error: error.message }));
    return true;
  }
  return false;
});
