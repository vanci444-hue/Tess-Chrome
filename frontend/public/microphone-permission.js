// This extension-origin page only establishes permission; it never opens ASR or stores audio.
const button = document.getElementById("allow");
const status = document.getElementById("status");
let leaving = false;
window.addEventListener("pagehide", () => { leaving = true; });
button.addEventListener("click", async () => {
  button.disabled = true;
  status.textContent = "请在 Chrome 提示中允许麦克风。";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    stream.getTracks().forEach((track) => track.stop());
    if (!leaving) status.textContent = "麦克风授权成功，已停止采音。请返回 Tess 侧栏，重新点击实时转写。";
  } catch (error) {
    if (leaving) return;
    status.textContent = error.name === "NotAllowedError"
      ? "麦克风权限未获允许。请检查 Chrome 的麦克风网站设置，以及 macOS 系统设置 → 隐私与安全性 → 麦克风中 Google Chrome 的权限，然后重试。"
      : error.name === "NotFoundError"
        ? "未找到麦克风，请连接设备后重试。"
        : "麦克风无法启动，请检查设备是否被占用及系统权限，然后重试。";
  } finally {
    if (!leaving) button.disabled = false;
  }
});
