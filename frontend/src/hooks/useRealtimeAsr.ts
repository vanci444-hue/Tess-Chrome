import { useCallback, useEffect, useRef, useState } from "react";
import workletUrl from "../audio/pcm-worklet.ts?worker&url";
import {
  TranscriptBuffer,
  canSendPcm,
  isServerDrain,
  acceptsPcm,
  type AsrEvent,
} from "../audio/transcript";
import { createAudio, audioSocketUrl } from "../services/audio";
export type RecordingPhase =
  "idle" | "connecting" | "recording" | "finishing" | "finished" | "failed";
const activePhases = new Set<RecordingPhase>([
  "connecting",
  "recording",
  "finishing",
]);
interface Options {
  sessionId: string;
  revision: number;
  text: string;
  onText: (text: string) => void;
}
/** One hook instance belongs to one keyed route session. Audio never enters persistent storage. */
export function useRealtimeAsr({ sessionId, revision, text, onText }: Options) {
  const [phase, setPhase] = useState<RecordingPhase>("idle"),
    [notice, setNotice] = useState(""),
    [lateTail, setLateTail] = useState(""),
    [elapsed, setElapsed] = useState(0);
  const options = useRef({ sessionId, revision, text, onText });
  options.current = { sessionId, revision, text, onText };
  const generation = useRef(0),
    currentPhase = useRef<RecordingPhase>("idle"),
    buffer = useRef<TranscriptBuffer | null>(null),
    asrId = useRef<string | null>(null);
  const socket = useRef<WebSocket | null>(null),
    media = useRef<MediaStream | null>(null),
    context = useRef<AudioContext | null>(null),
    processor = useRef<AudioWorkletNode | null>(null),
    source = useRef<MediaStreamAudioSourceNode | null>(null);
  const timeouts = useRef<ReturnType<typeof setTimeout>[]>([]),
    ticker = useRef<ReturnType<typeof setInterval> | null>(null),
    finishSent = useRef(false);
  const changePhase = useCallback((next: RecordingPhase) => {
    currentPhase.current = next;
    setPhase(next);
  }, []);
  const clearAudio = useCallback(() => {
    source.current?.disconnect();
    processor.current?.disconnect();
    media.current?.getTracks().forEach((track) => track.stop());
    media.current = null;
    source.current = null;
    processor.current = null;
    if (context.current) {
      void context.current.close().catch(() => {});
      context.current = null;
    }
  }, []);
  const cleanup = useCallback(() => {
    clearAudio();
    timeouts.current.forEach(clearTimeout);
    timeouts.current = [];
    if (ticker.current) clearInterval(ticker.current);
    ticker.current = null;
    const ws = socket.current;
    socket.current = null;
    if (ws && ws.readyState < 2) ws.close(1000);
  }, [clearAudio]);
  const fail = useCallback(
    (message: string) => {
      if (!activePhases.has(currentPhase.current)) return;
      buffer.current?.freeze();
      changePhase("failed");
      setNotice(
        message + " 已收到的文字已保留，末句可能不完整；可手动纠正后发送。",
      );
      cleanup();
    },
    [changePhase, cleanup],
  );
  const finish = useCallback(() => {
    if (currentPhase.current === "connecting") {
      generation.current++;
      buffer.current?.freeze();
      changePhase("finished");
      setNotice("已停止连接；没有发送会话消息。");
      cleanup();
      return;
    }
    if (currentPhase.current !== "recording") return;
    changePhase("finishing");
    setNotice("正在处理最后一句，完成后仍需手动发送。");
    media.current?.getTracks().forEach((track) => track.stop());
    processor.current?.port.postMessage("finish");
    timeouts.current.push(
      setTimeout(() => {
        if (!finishSent.current && currentPhase.current === "finishing")
          fail("音频尾段未能及时结束。");
      }, 1000),
    );
  }, [changePhase, cleanup, fail]);
  const discard = useCallback(() => {
    const original = buffer.current?.discard();
    generation.current++;
    changePhase("finished");
    if (socket.current?.readyState === WebSocket.OPEN)
      socket.current.send(JSON.stringify({ type: "discard" }));
    cleanup();
    if (original !== undefined) options.current.onText(original);
    asrId.current = null;
    setLateTail("");
    setNotice("已放弃本段录音；原有手工文字与本次手动更正均已保留。");
  }, [changePhase, cleanup]);
  const start = useCallback(async () => {
    if (activePhases.has(currentPhase.current)) return;
    cleanup();
    const mine = ++generation.current;
    const owner = { ...options.current };
    const baseText = owner.text;
    changePhase("connecting");
    setNotice("连接实时转写。音频会发送至百炼，文字需手动发送给 Tess。");
    setLateTail("");
    setElapsed(0);
    finishSent.current = false;
    asrId.current = null;
    buffer.current = null;
    try {
      const created = await createAudio(owner.sessionId, owner.revision);
      if (mine !== generation.current) return;
      if (created.session_id !== owner.sessionId)
        throw new Error("实时转写归属不匹配");
      asrId.current = created.asr_session_id;
      buffer.current = new TranscriptBuffer(
        owner.sessionId,
        created.asr_session_id,
        mine,
        baseText,
      );
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error(
          "当前页面无法访问麦克风，请在 Chrome 插件或本机页面使用",
        );
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
        video: false,
      });
      if (mine !== generation.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      media.current = stream;
      const audio = new AudioContext();
      context.current = audio;
      await audio.audioWorklet.addModule(workletUrl);
      if (mine !== generation.current) return;
      const node = new AudioWorkletNode(audio, "tess-pcm-16k");
      processor.current = node;
      const silent = audio.createGain();
      silent.gain.value = 0;
      node.connect(silent);
      silent.connect(audio.destination);
      const ws = new WebSocket(audioSocketUrl(created.ws_path));
      socket.current = ws;
      node.port.onmessage = (event) => {
        if (
          mine !== generation.current ||
          socket.current !== ws ||
          ws.readyState !== WebSocket.OPEN
        )
          return;
        if (event.data === "flushed") {
          if (currentPhase.current !== "finishing" || finishSent.current)
            return;
          finishSent.current = true;
          ws.send(JSON.stringify({ type: "finish" }));
          clearAudio();
          timeouts.current.push(
            setTimeout(() => {
              if (
                mine === generation.current &&
                currentPhase.current === "finishing"
              )
                fail("实时转写收尾超时。");
            }, 10000),
          );
          return;
        }
        if (
          !(event.data instanceof ArrayBuffer) ||
          !acceptsPcm(currentPhase.current, ws.readyState, finishSent.current)
        )
          return;
        if (!canSendPcm(ws.bufferedAmount, event.data.byteLength)) {
          fail("网络发送积压超过两秒，已停止采音。");
          return;
        }
        ws.send(event.data);
      };
      ws.onmessage = (event) => {
        if (mine !== generation.current || socket.current !== ws) return;
        let received: AsrEvent;
        try {
          received = JSON.parse(String(event.data)) as AsrEvent;
        } catch {
          fail("实时转写返回了无法识别的数据。");
          return;
        }
        if (received.asr_session_id !== created.asr_session_id) return;
        if (received.type === "ready") {
          if (currentPhase.current !== "connecting") return;
          source.current = audio.createMediaStreamSource(stream);
          source.current.connect(node);
          void audio.resume().catch(() => fail("无法启动音频采集。"));
          changePhase("recording");
          setNotice("正在实时转写 · 停止后不会自动发送");
          const started = Date.now();
          ticker.current = setInterval(
            () => setElapsed(Math.floor((Date.now() - started) / 1000)),
            1000,
          );
          timeouts.current.push(
            setTimeout(() => {
              if (
                mine === generation.current &&
                currentPhase.current === "recording"
              ) {
                finish();
                setNotice(
                  "本段达到5分钟，已停止采音；文字保留，仍需手动发送。",
                );
              }
            }, 300000),
          );
          return;
        }
        const updated = buffer.current?.apply(received, mine);
        if (updated != null) owner.onText(updated);
        if (buffer.current?.lateTail) setLateTail(buffer.current.lateTail);
        if (received.type === "finished") {
          changePhase("finished");
          setNotice(
            received.complete
              ? "识别结束，请检查文字后手动发送。"
              : "本段识别不完整，请核对末句再发送。",
          );
          cleanup();
        }
        if (isServerDrain(received)) {
          // Server allows a 2s drain window; flush the local tail once, then wait for final.
          if (currentPhase.current === "recording") finish();
          setNotice("本段已达时长上限，正在等待最后一句；不会自动发送。");
        } else if (received.type === "error")
          fail(received.message || "识别连接中断。");
      };
      ws.onerror = () => {
        if (mine === generation.current) fail("无法连接实时转写服务。");
      };
      ws.onclose = () => {
        if (
          mine === generation.current &&
          activePhases.has(currentPhase.current)
        )
          fail("识别连接已断开。");
      };
      timeouts.current.push(
        setTimeout(() => {
          if (
            mine === generation.current &&
            currentPhase.current === "connecting"
          )
            fail("实时转写连接超时。");
        }, 10000),
      );
    } catch (error) {
      if (mine !== generation.current) return;
      const e = error as Error;
      fail(
        e.name === "NotAllowedError"
          ? "麦克风权限被拒，请允许麦克风后重试或改用文字。"
          : e.message,
      );
    }
  }, [changePhase, cleanup, clearAudio, fail, finish]);
  const edit = useCallback(
    (value: string) => {
      if (activePhases.has(currentPhase.current)) {
        buffer.current?.edit(value);
        if (currentPhase.current === "recording") finish();
        else if (currentPhase.current === "connecting") {
          generation.current++;
          changePhase("finished");
          cleanup();
        }
      }
      options.current.onText(value);
    },
    [finish, changePhase, cleanup],
  );
  const freezeForSend = useCallback(() => {
    buffer.current?.freeze();
    if (currentPhase.current === "recording") finish();
    return buffer.current?.items.size ? asrId.current : null;
  }, [finish]);
  const dispose = useCallback(() => {
    generation.current++;
    cleanup();
  }, [cleanup]);
  useEffect(() => dispose, [dispose]);
  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => {
      if (activePhases.has(currentPhase.current)) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, []);
  const markSent = useCallback(() => {
    buffer.current?.freeze();
    asrId.current = null;
    buffer.current = null;
    generation.current++;
    setLateTail("");
  }, []);
  return {
    markSent,
    phase,
    active: activePhases.has(phase),
    notice,
    lateTail,
    elapsed,
    start,
    finish,
    discard,
    edit,
    freezeForSend,
  };
}
