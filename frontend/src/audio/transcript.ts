export type AsrEvent =
  | { type: "ready"; asr_session_id: string }
  | {
      type: "partial";
      asr_session_id: string;
      seq: number;
      item_id: string;
      text: string;
      stash: string;
    }
  | {
      type: "final";
      asr_session_id: string;
      seq: number;
      item_id: string;
      transcript: string;
    }
  | { type: "finished"; asr_session_id: string; seq: number; complete: boolean }
  | {
      type: "error";
      asr_session_id: string;
      seq: number;
      code: string;
      message: string;
      incomplete: boolean;
    };
/** A generation owns one immutable base text. Editing freezes it against all late packets. */
export class TranscriptBuffer {
  readonly items = new Map<string, { text: string; final: boolean }>();
  private lastSeq = -1;
  private locked = false;
  private edited = false;
  private current: string;
  lateTail = "";
  readonly sessionId: string;
  readonly asrSessionId: string;
  readonly generation: number;
  readonly baseText: string;
  constructor(
    sessionId: string,
    asrSessionId: string,
    generation: number,
    baseText: string,
  ) {
    this.sessionId = sessionId;
    this.asrSessionId = asrSessionId;
    this.generation = generation;
    this.baseText = baseText;
    this.current = baseText;
  }
  private compose() {
    const transcript = [...this.items.values()].map((i) => i.text).join("");
    return (
      this.baseText + (this.baseText && transcript ? "\n" : "") + transcript
    );
  }
  apply(event: AsrEvent, generation: number): string | null {
    if (
      generation !== this.generation ||
      event.asr_session_id !== this.asrSessionId
    )
      return null;
    if (!("seq" in event) || event.seq <= this.lastSeq) return null;
    this.lastSeq = event.seq;
    if (event.type !== "partial" && event.type !== "final") return null;
    const prior = this.items.get(event.item_id);
    if (prior?.final && event.type === "partial") return null;
    this.items.set(event.item_id, {
      text:
        event.type === "final" ? event.transcript : event.text + event.stash,
      final: event.type === "final",
    });
    if (this.locked) {
      this.lateTail = [...this.items.values()].map((i) => i.text).join("");
      return null;
    }
    this.current = this.compose();
    return this.current;
  }
  edit(text: string) {
    this.edited = true;
    this.locked = true;
    this.current = text;
  }
  freeze() {
    this.locked = true;
    return this.current;
  }
  discard() {
    this.locked = true;
    return this.edited ? this.current : this.baseText;
  }
  get value() {
    return this.current;
  }
}
export const ASR_MAX_BUFFER_BYTES = 16000 * 2 * 2;
export function canSendPcm(bufferedAmount: number, nextBytes: number) {
  return bufferedAmount + nextBytes <= ASR_MAX_BUFFER_BYTES;
}

export function isServerDrain(event: AsrEvent) {
  return (
    event.type === "error" &&
    event.code === "ASR_DURATION_LIMIT" &&
    !event.incomplete
  );
}

export function acceptsPcm(
  phase: string,
  readyState: number,
  finishSent: boolean,
) {
  return (
    readyState === 1 &&
    !finishSent &&
    (phase === "recording" || phase === "finishing")
  );
}
