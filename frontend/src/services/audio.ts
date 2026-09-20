import { request, newKey, isExtension } from "./api";
export interface AudioCreated {
  asr_session_id: string;
  session_id: string;
  ws_path: string;
  state: "created";
  expires_in_seconds: number;
}
export function createAudio(sessionId: string, revision: number) {
  return request<AudioCreated>(
    "POST",
    `/sessions/${sessionId}/audio`,
    { expected_revision: revision, language: null },
    newKey(),
  );
}
export function audioSocketUrl(path: string) {
  if (!path.startsWith("/ws/sessions/") || path.includes("://"))
    throw new Error("转写连接地址无效");
  const base = isExtension
    ? import.meta.env.VITE_EXTENSION_API_ORIGIN
    : location.origin;
  const url = new URL(path, base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

/** Release only an unconnected reservation; the server refuses active streams. */
export function cancelAudioReservation(sessionId: string, asrId: string) {
  return request<{ asr_session_id: string; state: string }>(
    "DELETE",
    `/sessions/${sessionId}/audio/${asrId}`,
  );
}
