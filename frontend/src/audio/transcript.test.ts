import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  TranscriptBuffer,
  canSendPcm,
  isServerDrain,
  acceptsPcm,
} from "./transcript.ts";
import { Pcm16Encoder } from "./pcm.ts";
test("partials replace by item, final replaces preview; wrong session and old generation are ignored", () => {
  const b = new TranscriptBuffer("s", "a", 1, "已有文字");
  assert.equal(
    b.apply(
      {
        type: "partial",
        asr_session_id: "a",
        seq: 1,
        item_id: "i1",
        text: "月供",
        stash: "四",
      },
      1,
    ),
    "已有文字\n月供四",
  );
  assert.equal(
    b.apply(
      {
        type: "partial",
        asr_session_id: "a",
        seq: 2,
        item_id: "i1",
        text: "月供四千",
        stash: "",
      },
      1,
    ),
    "已有文字\n月供四千",
  );
  assert.equal(
    b.apply(
      {
        type: "final",
        asr_session_id: "a",
        seq: 3,
        item_id: "i1",
        transcript: "月供4000元。",
      },
      1,
    ),
    "已有文字\n月供4000元。",
  );
  assert.equal(
    b.apply(
      {
        type: "final",
        asr_session_id: "other",
        seq: 4,
        item_id: "i2",
        transcript: "串客",
      },
      1,
    ),
    null,
  );
  assert.equal(
    b.apply(
      {
        type: "final",
        asr_session_id: "a",
        seq: 4,
        item_id: "i2",
        transcript: "旧段",
      },
      2,
    ),
    null,
  );
  assert.equal(b.value, "已有文字\n月供4000元。");
});
test("edit/send freeze blocks late final; discard restores pre-recording text", () => {
  const b = new TranscriptBuffer("s", "a", 3, "手工底稿");
  b.apply(
    {
      type: "partial",
      asr_session_id: "a",
      seq: 1,
      item_id: "i",
      text: "八千",
      stash: "",
    },
    3,
  );
  b.edit("销售纠正为四千");
  assert.equal(
    b.apply(
      {
        type: "final",
        asr_session_id: "a",
        seq: 2,
        item_id: "i",
        transcript: "八千元",
      },
      3,
    ),
    null,
  );
  assert.equal(b.value, "销售纠正为四千");
  assert.equal(b.lateTail, "八千元");
  assert.equal(b.freeze(), "销售纠正为四千");
  assert.equal(b.discard(), "销售纠正为四千");
  const untouched = new TranscriptBuffer("s", "b", 4, "原手工底稿");
  untouched.apply(
    {
      type: "partial",
      asr_session_id: "b",
      seq: 1,
      item_id: "i",
      text: "录音段",
      stash: "",
    },
    4,
  );
  assert.equal(untouched.discard(), "原手工底稿");
});
test("PCM is 16k mono signed little-endian at both 48k and 44.1k, carried across quanta", () => {
  for (const rate of [48000, 44100]) {
    const encoder = new Pcm16Encoder(rate),
      chunks: ArrayBuffer[] = [];
    const input = new Float32Array(rate).fill(0.5);
    for (let i = 0; i < input.length; i += 128)
      chunks.push(...encoder.push(input.slice(i, i + 128)));
    const tail = encoder.flush();
    if (tail) chunks.push(tail);
    assert.equal(
      chunks.reduce((sum, b) => sum + b.byteLength, 0),
      32000,
    );
    assert.equal(chunks.length, 10);
    assert.equal(new DataView(chunks[0]).getInt16(0, true), 16384);
    assert.equal(chunks[0].byteLength, 3200);
  }
});
test("backpressure bounded to two seconds, no unlimited buffering", () => {
  assert.equal(canSendPcm(60800, 3200), true);
  assert.equal(canSendPcm(64000, 3200), false);
});

test("server duration limit drains final text while real errors fail", () => {
  const event = {
    type: "error" as const,
    asr_session_id: "a",
    seq: 2,
    code: "ASR_DURATION_LIMIT",
    message: "达到上限",
    incomplete: false,
  };
  assert.equal(isServerDrain(event), true);
  assert.equal(
    isServerDrain({ ...event, code: "ASR_DISCONNECTED", incomplete: true }),
    false,
  );
  const b = new TranscriptBuffer("s", "a", 1, "");
  b.apply(event, 1);
  assert.equal(
    b.apply(
      {
        type: "final",
        asr_session_id: "a",
        seq: 3,
        item_id: "last",
        transcript: "完整尾句",
      },
      1,
    ),
    "完整尾句",
  );
});

test("PCM gate waits for ready/recording and never sends beyond finish or failure", () => {
  assert.equal(acceptsPcm("connecting", 1, false), false);
  assert.equal(acceptsPcm("recording", 0, false), false);
  assert.equal(acceptsPcm("recording", 1, false), true);
  assert.equal(acceptsPcm("finishing", 1, false), true);
  assert.equal(acceptsPcm("finishing", 1, true), false);
  assert.equal(acceptsPcm("failed", 1, false), false);
});
