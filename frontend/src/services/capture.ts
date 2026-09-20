import { ApiError, contractMock, isExtension } from "./api";
import type { CaptureInput } from "../types/api";
import { mockCapture } from "../mocks/fixtures";
import { projectCapture } from "../utils/captureProjection";
export async function captureCurrent(): Promise<CaptureInput> {
  if (contractMock) {
    return mockCapture();
  }
  if (!isExtension)
    throw new ApiError(
      "真实 Capture 需要在 Chrome 插件侧栏中使用。请加载 frontend/dist，再切到 Tesla 中国 Model Y 官网。",
      "EXTENSION_REQUIRED",
    );
  const result = await chrome.runtime.sendMessage({
    type: "CAPTURE_CURRENT_CONFIGURATION",
  });
  if (!result?.ok)
    throw new ApiError(
      result?.error || "未获取到官网数据，请重试。",
      "CAPTURE_FAILED",
    );
  const raw = result.capture;
  if (raw.readiness !== "ready")
    throw new ApiError(
      "官网选配尚未稳定，请等待价格更新后再次 Capture。",
      "PAGE_UNSTABLE",
    );
  // Only transport the approved capture whitelist; do not send page diagnostics/whole DOM.
  return projectCapture(raw);
}
