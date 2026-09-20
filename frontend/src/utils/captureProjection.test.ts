import { strict as assert } from "node:assert";
import { test } from "node:test";
import { projectCapture } from "./captureProjection.ts";
test("Capture bridge strips diagnostics and maps severity without changing original snapshot", () => {
  const input = {
    source_url: "https://www.tesla.cn/modely/design#overview",
    captured_at: "2026-09-20T00:00:00Z",
    adapter_version: "0.1.1",
    page_fingerprint: "proof",
    readiness: "ready" as const,
    fields: [
      {
        key: "vehicle_price",
        value: 31350000,
        unit: "CNY_fen",
        raw_text: "¥313,500",
        evidence: { kind: "dom_text", selector_hint: "footer" },
        observed_at: "2026-09-20T00:00:00Z",
      },
    ],
    issues: [
      {
        code: "FINANCE_NOT_VISIBLE",
        severity: "warning",
        message: "金融待获取",
      },
      {
        code: "FINANCE_PRICE_CONFLICT",
        severity: "error",
        message: "金额冲突",
      },
    ],
    diagnostics: { page_text: "must not upload" },
    completeness: "complete",
  };
  const original = JSON.stringify(input),
    result = projectCapture(input);
  assert.deepEqual(
    Object.keys(result).sort(),
    [
      "source_url",
      "captured_at",
      "adapter_version",
      "page_fingerprint",
      "readiness",
      "fields",
      "issues",
    ].sort(),
  );
  assert.equal(result.fields[0].value, 31350000);
  assert.equal(result.issues[0].blocking, false);
  assert.equal(result.issues[1].blocking, true);
  assert.equal(JSON.stringify(input), original);
});
