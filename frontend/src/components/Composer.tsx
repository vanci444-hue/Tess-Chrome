import { useLayoutEffect, useRef } from "react";
import { isExtension } from "../services/api";
import type { RecordingPhase } from "../hooks/useRealtimeAsr";
import { Icon } from "./Icon";

interface Props {
  text: string;
  onChange: (text: string) => void;
  onSend: () => void;
  busy: boolean;
  audio: {
    phase: RecordingPhase;
    permissionDenied?: boolean;
    active: boolean;
    notice: string;
    lateTail: string;
    elapsed: number;
    start: () => Promise<void>;
    finish: () => void;
    discard: () => void;
  };
}

export default function Composer({
  text,
  onChange,
  onSend,
  busy,
  audio,
}: Props) {
  const area = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);
  const timer = `${Math.floor(audio.elapsed / 60)}:${String(audio.elapsed % 60).padStart(2, "0")}`;
  return (
    <footer className="composer">
      <div className={`input-shell composer-bar ${audio.active ? "recording" : ""}`}>
        <textarea
          ref={area}
          aria-label="本次试驾复盘"
          placeholder="记录本次试驾，或继续问 Tess…"
          rows={1}
          value={text}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              (e.metaKey || e.ctrlKey) &&
              !busy &&
              !audio.active &&
              text.trim()
            )
              onSend();
          }}
        />
        <div className="composer-actions">
          {audio.active ? (
            <>
              <span className="composer-timer" aria-live="polite">
                {timer}
              </span>
              <button
                className="mic-button"
                type="button"
                aria-label="放弃本段语音"
                title="放弃"
                onClick={audio.discard}
              >
                <Icon name="close" size={18} />
              </button>
              <button
                className="send-button primary"
                type="button"
                disabled={audio.phase === "finishing"}
                aria-label="完成语音输入"
                title="完成"
                onClick={audio.finish}
              >
                <Icon name="check" size={18} />
              </button>
            </>
          ) : (
            <>
              <button
                className="mic-button"
                type="button"
                disabled={busy}
                aria-label="语音输入"
                onClick={() => void audio.start()}
              >
                <Icon name="microphone" size={20} />
              </button>
              <button
                className="send-button primary"
                disabled={busy || !text.trim()}
                onClick={onSend}
                aria-label="发送"
              >
                <Icon name="send" size={18} />
              </button>
            </>
          )}
        </div>
      </div>
      {audio.notice && (
        <p
          className={`micro ${audio.phase === "failed" ? "text-error" : "muted"}`}
          role="status"
        >
          {audio.notice}
        </p>
      )}
      {audio.permissionDenied && isExtension && (
        <p className="micro">
          <a
            href={chrome.runtime.getURL("microphone-permission.html")}
            target="_blank"
            rel="noopener noreferrer"
          >
            打开麦克风授权页
          </a>
          {" · 授权完成后返回此处，再点麦克风。"}
        </p>
      )}
      {audio.lateTail && (
        <details className="late-transcript">
          <summary>手动编辑后收到的识别尾段（未采用）</summary>
          <p>{audio.lateTail}</p>
          <small>输入框保留你的编辑。需要时可手动复制补充。</small>
        </details>
      )}
    </footer>
  );
}
