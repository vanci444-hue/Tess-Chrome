import type { CaptureInput, Issue, CapturedField } from "../types/api";
interface BridgeResult {
  source_url: string;
  captured_at: string;
  adapter_version: string;
  page_fingerprint: string;
  readiness: CaptureInput["readiness"];
  fields: CapturedField[];
  issues: (Partial<Issue> & {
    severity?: string;
    code: string;
    message: string;
  })[];
}
/** The diagnostic spike contains more data than the API accepts. Explicitly whitelist it. */
export function projectCapture(raw: BridgeResult): CaptureInput {
  return {
    source_url: raw.source_url,
    captured_at: raw.captured_at,
    adapter_version: raw.adapter_version,
    page_fingerprint: raw.page_fingerprint,
    readiness: raw.readiness,
    fields: raw.fields.map((f) => ({
      key: f.key,
      value: f.value,
      unit: f.unit,
      raw_text: f.raw_text,
      evidence: {
        kind: f.evidence.kind,
        selector_hint: f.evidence.selector_hint,
      },
      observed_at: f.observed_at,
    })),
    issues: raw.issues.map((issue) => ({
      code: issue.code,
      field: issue.field || null,
      blocking: issue.blocking ?? issue.severity === "error",
      message: issue.message,
    })),
  };
}
