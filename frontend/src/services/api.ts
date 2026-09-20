import axios from "axios";
import type { Envelope } from "../types/api";
export const isExtension = location.protocol === "chrome-extension:";
export const contractMock =
  import.meta.env.VITE_CONTRACT_MOCK === "true" ||
  (!isExtension && new URLSearchParams(location.search).get("mock") === "1");
export const apiBase = isExtension
  ? `${import.meta.env.VITE_EXTENSION_API_ORIGIN}/api`
  : import.meta.env.VITE_API_BASE_URL || "/api";
export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public metadata: Record<string, unknown> = {},
  ) {
    super(message);
  }
}
export const api = axios.create({
  baseURL: apiBase,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});
api.interceptors.response.use(
  (response) => {
    const e = response.data as Envelope<unknown>;
    if (e.success === false)
      throw new ApiError(
        e.error || "操作未完成",
        e.error_code || "UNKNOWN",
        e.metadata,
      );
    return response;
  },
  (error) => {
    const e = error.response?.data as Envelope<unknown> | undefined;
    return Promise.reject(
      new ApiError(
        e?.error ||
          (error.response?.status === 401
            ? "本机服务拒绝访问，请检查允许的插件来源。"
            : "无法连接本机服务，请检查启动状态后重试。"),
        e?.error_code || "NETWORK_ERROR",
        e?.metadata,
      ),
    );
  },
);
export async function request<T>(
  method: string,
  url: string,
  data?: unknown,
  key?: string,
  timeoutMs?: number,
): Promise<T> {
  if (contractMock) {
    const { mockRequest } = await import("../mocks/transport");
    return (await mockRequest<T>(method, url, data, key)).data;
  }
  const response = await api.request<Envelope<T>>({
    method,
    url,
    data,
    timeout: timeoutMs,
    headers: key ? { "Idempotency-Key": key } : undefined,
  });
  return response.data.data;
}
export function reportUrl(id: string) {
  return isExtension
    ? `${import.meta.env.VITE_EXTENSION_API_ORIGIN}/reports/${encodeURIComponent(id)}`
    : `/reports/${encodeURIComponent(id)}`;
}
export const newKey = () => crypto.randomUUID();
