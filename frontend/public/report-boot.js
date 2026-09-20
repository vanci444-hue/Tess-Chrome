(() => {
  const stage = document.getElementById("report-stage");
  const root = document.getElementById("report-root");
  const tabs = document.querySelectorAll(".view-tabs button");

  const params = new URLSearchParams(location.search);
  const sessionId =
    (location.hash || "").replace(/^#/, "").trim() ||
    params.get("id") ||
    localStorage.getItem("tess.demo.report.html.latest") ||
    "";

  function fail(message) {
    if (root) {
      root.innerHTML = `<div class="error"><h1>无法打开报告</h1><p>${message}</p></div>`;
    }
  }

  function setView(view) {
    const next = view === "phone" ? "phone" : "web";
    if (stage) {
      stage.classList.remove("layout-web", "layout-phone");
      stage.classList.add(next === "phone" ? "layout-phone" : "layout-web");
    }
    tabs.forEach((button) => {
      const active = button.getAttribute("data-view") === next;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    try {
      localStorage.setItem("tess.demo.report.view", next);
    } catch {
      /* ignore */
    }
  }

  tabs.forEach((button) => {
    button.addEventListener("click", () => {
      setView(button.getAttribute("data-view") || "web");
    });
  });

  let preferred = "web";
  try {
    preferred = localStorage.getItem("tess.demo.report.view") || "web";
  } catch {
    preferred = "web";
  }
  setView(preferred === "phone" ? "phone" : "web");

  if (!sessionId) {
    fail("链接缺少会话信息。请从 Tess 侧栏重新打开「查看报告」。");
    return;
  }

  let html = null;
  try {
    html = localStorage.getItem(`tess.demo.report.html.v1.${sessionId}`);
  } catch {
    fail("无法读取本机报告内容。");
    return;
  }

  if (!html) {
    fail(
      "本机还没有这份报告的静态稿。请在 Tess 中再次点击「生成试驾报告」，再打开链接。",
    );
    return;
  }

  const parsed = new DOMParser().parseFromString(html, "text/html");
  const reportStyle = document.createElement("style");
  reportStyle.setAttribute("data-report", "1");
  reportStyle.textContent = [...parsed.querySelectorAll("style")]
    .map((node) => node.textContent || "")
    .join("\n");
  document.head.appendChild(reportStyle);

  const sheet = parsed.querySelector("main");
  if (!sheet || !root) {
    fail("报告内容格式异常，请重新生成试驾报告。");
    return;
  }
  sheet.classList.remove("phone");
  sheet.classList.add("report-sheet");
  root.replaceChildren(sheet);
})();
