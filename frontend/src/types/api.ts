/** Endpoint DTOs mirror tech-spec. All CNY values are integer fen, never yuan. */
export type Json =
  string | number | boolean | null | Json[] | { [key: string]: Json };
export interface Envelope<T> {
  success: boolean;
  data: T;
  error: string | null;
  error_code: string | null;
  message: string | null;
  timestamp: string;
  request_id: string;
  metadata: Record<string, unknown>;
}
export interface Issue {
  code: string;
  field: string | null;
  blocking: boolean;
  message: string;
}
export interface CustomerSummary {
  id: string;
  nickname: string;
  contact_mask: string;
  latest_session_id: string | null;
}
export interface Customer {
  id: string;
  nickname: string;
  phone: string | null;
  email: string | null;
  revision: number;
}
export interface CustomerList {
  items: CustomerSummary[];
  next_cursor: string | null;
}
export interface IdentityInput {
  nickname: string;
  phone: string | null;
  email: string | null;
  identity_confirmed: boolean;
  allow_duplicate: boolean;
  extraction_id?: string;
}
export interface Extraction {
  extraction_id: string;
  proposed: {
    nickname: string | null;
    phone: string | null;
    email: string | null;
  };
  historical_facts: Fact[];
  missing: string[];
}
export interface SessionSummary {
  id: string;
  title: string;
  status: string;
  created_at: string;
  latest_report_id: string | null;
}
export interface SessionCreated {
  id: string;
  customer_id: string;
  title: string;
  revision: number;
  status: string;
  created_at: string;
}
export interface SessionsList {
  items: SessionSummary[];
  next_cursor: string | null;
}
export interface ReportSummary {
  report_id: string;
  session_id: string;
  session_title: string;
  title: string;
  published_at: string;
  url: string;
}
export interface ReportsList {
  items: ReportSummary[];
  next_cursor: string | null;
}
export interface CapturedField {
  key: string;
  value: Json;
  unit: string | null;
  raw_text: string;
  evidence: { kind: string; selector_hint: string | null };
  observed_at: string;
}
export interface CaptureInput {
  source_url: string;
  captured_at: string;
  adapter_version: string;
  page_fingerprint: string;
  readiness: "ready" | "unstable" | "unsupported";
  fields: CapturedField[];
  issues: Issue[];
}
export interface Capture {
  id: string;
  session_id: string;
  immutable_payload: CaptureInput;
  validity: "valid" | "incomplete" | "conflict";
  issues: Issue[];
  active: boolean;
  preference: string | null;
}
export interface CaptureCreated {
  capture_id: string;
  session_id: string;
  revision: number;
  validity: Capture["validity"];
  issues: Issue[];
}
export interface CaptureUpdated {
  capture_id: string;
  active: boolean;
  preference: string | null;
  revision: number;
}
export interface Fact {
  id: string;
  key: string;
  value: Json;
  unit: string | null;
  state: "proposed" | "confirmed" | "unknown" | "conflict";
  source_kind: string;
  source_id: string;
  observed_at: string;
  scope: "identity" | "session" | "historical";
  subject_id: string | null;
  evidence_note: string | null;
  supersedes: string[];
}
export interface FactChange {
  fact_id?: string;
  key: string;
  value: Json;
  state: "confirmed" | "unknown";
  supersedes: string[];
  evidence_note: string | null;
}
export interface Question {
  id: string;
  text: string;
  required: boolean;
  fact_ids: string[];
  origin_run_id?: string;
  state?: string;
}
export interface ContextResponse {
  revision: number;
  blocking_issues: Issue[];
  invalidated_artifact_ids: string[];
  optional_questions_stopped: boolean;
  continuation_hint: {
    parent_run_id: string;
    effective_intent: string | null;
    expected_revision: number;
    continue_via: string;
  } | null;
}
export interface RunRef {
  run_id: string;
  session_id: string;
  status: string;
  kind: string;
  message_id?: string;
}
export interface RunEvent {
  seq: number;
  type: string;
  label: string;
  tool_name: string | null;
  artifact_id: string | null;
}
export interface Continuation {
  reason: string;
  can_continue: boolean;
  continued_by_run_id: string | null;
}
export interface RunStatus {
  run_id: string;
  session_id: string;
  status: string;
  events: RunEvent[];
  last_seq: number;
  result: Record<string, Json> | null;
  error: { code: string; message: string } | null;
  lineage: {
    parent_run_id: string | null;
    root_run_id: string;
    effective_intent: string | null;
  };
  continuation: Continuation | null;
}
export interface TimelineMessage {
  id: string;
  session_id: string;
  seq: number;
  role: "sales" | "assistant" | "system";
  type: "text" | "question" | "tool_summary" | "report_card";
  source_ref: { kind: string; id: string } | null;
  content: {
    text?: string;
    report_id?: string;
    title?: string;
    published_at?: string;
  };
  created_at: string;
}
export interface SourceRef {
  id: string;
  kind: string;
  url: string | null;
  observed_at: string;
  label: string;
}
export interface ReportModule {
  type: string;
  status: "ready" | "estimate" | "mock" | "missing";
  source_refs: SourceRef[];
  data: Record<string, Json>;
}
export interface Summary {
  comparing: string;
  confirmed: string[];
  pending: string[];
}
export interface ReportSnapshot {
  id: string;
  schema_version: number;
  customer_salutation: string;
  generated_at: string;
  published_at: string | null;
  summary: Summary;
  modules: ReportModule[];
  sources: {
    id: string;
    kind: string;
    url: string | null;
    observed_at: string;
    label: string;
  }[];
  asset_ids: string[];
  disclaimer: string;
}
export interface Draft {
  id: string;
  session_id: string;
  draft_revision: number;
  source_revision: number;
  customer_revision: number;
  report_data: ReportSnapshot;
  blocking_issues: Issue[];
  requires_review: boolean;
  stale: boolean;
}
export interface DraftUpdated {
  draft_id: string;
  draft_revision: number;
  requires_review: boolean;
  blocking_issues: Issue[];
}
export interface ReportPublished {
  report_id: string;
  session_id: string;
  timeline_message_id: string;
  url: string;
  published_at: string;
  snapshot_hash: string;
}
export interface SessionDetail {
  id: string;
  customer: {
    id: string;
    nickname: string;
    contact_mask: string;
    revision: number;
    phone: string | null;
    email: string | null;
  };
  revision: number;
  status: string;
  trial_vehicle: {
    model: string;
    variant: string | null;
    source_fact_ids: string[];
  } | null;
  captures: Capture[];
  inputs: unknown[];
  facts: Fact[];
  questions: Question[];
  artifacts: { id: string; tool_name: string; status: string; output: Json }[];
  active_run: { run_id: string; kind: string; status: string } | null;
  pending_run: {
    run_id: string;
    effective_intent: string | null;
    continuation: Continuation;
    questions: Question[];
  } | null;
  draft: Draft | null;
  reports: ReportSummary[];
  timeline: TimelineMessage[];
  followup: Record<string, Json> | null;
}
export interface Health {
  demo_advisor: {
    id: string;
    name: string;
    store_name: string;
    is_demo: boolean;
  };
  status: "ready" | "degraded";
  database: boolean;
  capabilities: {
    llm: "configured" | "missing";
    asr: "configured" | "missing";
    maps: "configured" | "missing";
  };
}
export interface MessageInput {
  text: string;
  source: "sales_text" | "asr_corrected";
  asr_session_id?: string | null;
  expected_revision: number;
  reply_to_run_id?: string | null;
  reply_to_question_ids?: string[];
  continue_run_id?: string | null;
  target_draft_id?: string | null;
  target_draft_revision?: number | null;
}
