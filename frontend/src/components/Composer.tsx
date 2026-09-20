import type { RecordingPhase } from "../hooks/useRealtimeAsr";
interface Props {
  text: string;
  onChange: (text: string) => void;
  onSend: () => void;
  busy: boolean;
  audio: {
    phase: RecordingPhase;
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
  const timer = `${Math.floor(audio.elapsed / 60)}:${String(audio.elapsed % 60).padStart(2, "0")}`;
  return (
    <footer className="composer">
      <div className={`input-shell ${audio.active ? "recording" : ""}`}>
        <textarea
          aria-label="本次试驾复盘"
          placeholder="记录本次试驾，或继续问 Tess…"
          rows={3}
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
        <div className="row between">
          <div className="row">
            {audio.active ? (
              <>
                <button
                  className="text-button"
                  type="button"
                  disabled={audio.phase === "finishing"}
                  onClick={audio.finish}
                >
                  {audio.phase === "connecting"
                    ? "取消连接"
                    : audio.phase === "finishing"
                      ? "收尾中…"
                      : `■ 停止 ${timer}`}
                </button>
                <button
                  className="text-button"
                  type="button"
                  onClick={audio.discard}
                >
                  放弃本段
                </button>
              </>
            ) : (
              <button
                className="text-button"
                type="button"
                disabled={busy}
                onClick={() => void audio.start()}
              >
                ◉ 实时转写
              </button>
            )}
          </div>
          <button
            className="send-button primary"
            disabled={busy || audio.active || !text.trim()}
            onClick={onSend}
            aria-label="发送"
          >
            ↑
          </button>
        </div>
      </div>
      <p
        className={`micro ${audio.phase === "failed" ? "text-error" : "muted"}`}
        role="status"
      >
        {audio.notice || "文字手动发送后才交给 Tess · ⌘ / Ctrl + Enter 发送"}
      </p>
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
