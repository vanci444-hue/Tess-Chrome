/* The action opens Chrome's native side panel. No remote scripts or API calls. */
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);

async function teslaDesignTab() {
  const pattern = "https://www.tesla.cn/modely/design*";
  const matches = await chrome.tabs.query({ url: pattern });
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab =
    matches.find((t) => t.id === active?.id) ||
    matches.find((t) => t.active) ||
    matches[0] ||
    active;
  const url = new URL(tab?.url || "about:blank");
  const onDesign =
    url.protocol === "https:" &&
    url.hostname === "www.tesla.cn" &&
    url.pathname.startsWith("/modely/design");
  if (!onDesign || tab?.id == null) {
    throw new Error("仅支持 https://www.tesla.cn/modely/design。请切回该官网标签页。");
  }
  return tab;
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return false;
  if (message?.type === "CAPTURE_CURRENT_CONFIGURATION") {
    (async () => {
      const tab = await teslaDesignTab();
      await chrome.scripting.executeScript({
        target: { tabId: tab.id, frameIds: [0] },
        files: ["capture.js"],
      });
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id, frameIds: [0] },
        func: async () => globalThis.TessCapture.capture(),
      });
      return { ok: true, tab_id: tab.id, capture: results[0]?.result };
    })()
      .then(respond)
      .catch((error) => respond({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "OPEN_TESLA_FINANCE") {
    (async () => {
      const tab = await teslaDesignTab();
      await chrome.tabs.update(tab.id, { active: true }).catch(() => {});
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id, frameIds: [0] },
        func: () => {
          const textOf = (node) =>
            `${node.innerText || ""} ${node.textContent || ""} ${node.getAttribute?.("aria-label") || ""}`
              .replace(/\s+/g, " ")
              .trim();
          const footerTrigger = document.querySelector(
            ".aside-footer--container button.modal-trigger",
          );
          const nodes = [
            ...document.querySelectorAll("a,button,[role='button']"),
          ];
          const el =
            footerTrigger ||
            nodes.find((node) => /查看金融方案/.test(textOf(node))) ||
            nodes.find(
              (node) =>
                /¥[\d,]+\s*\/\s*月/.test(textOf(node)) &&
                /车辆价格/.test(textOf(node)),
            ) ||
            nodes.find((node) => /^金融方案$/.test(textOf(node)));
          if (!el) {
            throw new Error(
              "当前页没有金融方案入口。请打开 Model Y 配置器底部「¥…/月」价格按钮。",
            );
          }
          el.click();
          return true;
        },
      });
      if (!results[0]?.result) {
        throw new Error(results[0]?.error || "无法打开官网金融方案。");
      }
      return { ok: true };
    })()
      .then(respond)
      .catch((error) => respond({ ok: false, error: error.message }));
    return true;
  }
  return false;
});
