import { request, newKey } from "./api";
import type {
  CustomerList,
  Customer,
  IdentityInput,
  Extraction,
  SessionCreated,
  SessionsList,
  ReportsList,
  SessionDetail,
  CaptureInput,
  CaptureCreated,
  CaptureUpdated,
  FactChange,
  ContextResponse,
  RunRef,
  RunStatus,
  Summary,
  DraftUpdated,
  ReportPublished,
  ReportSnapshot,
  Health,
  MessageInput,
} from "../types/api";
const session = (id: string) => `/sessions/${encodeURIComponent(id)}`;
export const tess = {
  health: () => request<Health>("GET", "/health"),
  customers: (q = "", cursor = "") =>
    request<CustomerList>(
      "GET",
      `/customers?q=${encodeURIComponent(q)}&cursor=${encodeURIComponent(cursor)}`,
    ),
  extract: (text: string) =>
    // CRM 提取为同步接口，覆盖后端默认模型 60 秒超时；其他异步受理仍用短超时。
    request<Extraction>("POST", "/customers/extract", { text }, newKey(), 70000),
  createCustomer: (body: IdentityInput, key = newKey()) =>
    request<Customer>("POST", "/customers", body, key),
  editCustomer: (
    id: string,
    body: Partial<IdentityInput> & { expected_revision: number },
  ) => request<Customer>("PATCH", `/customers/${id}`, body),
  newSession: (customer_id: string, title = "本次 Model Y 试驾") =>
    request<SessionCreated>(
      "POST",
      "/sessions",
      { customer_id, title, visit_at: null },
      newKey(),
    ),
  sessions: (customerId: string, cursor = "") =>
    request<SessionsList>(
      "GET",
      `/sessions?customer_id=${customerId}&cursor=${encodeURIComponent(cursor)}`,
    ),
  reports: (customerId: string, cursor = "") =>
    request<ReportsList>(
      "GET",
      `/customers/${customerId}/reports?cursor=${encodeURIComponent(cursor)}`,
    ),
  session: (id: string) => request<SessionDetail>("GET", session(id)),
  capture: (
    id: string,
    revision: number,
    capture: CaptureInput,
    key = newKey(),
  ) =>
    request<CaptureCreated>(
      "POST",
      `${session(id)}/captures`,
      { expected_revision: revision, capture },
      key,
    ),
  updateCapture: (
    id: string,
    captureId: string,
    revision: number,
    change: { active?: false; preference?: string | null },
  ) =>
    request<CaptureUpdated>("PATCH", `${session(id)}/captures/${captureId}`, {
      expected_revision: revision,
      ...change,
    }),
  message: (id: string, body: MessageInput, key = newKey()) =>
    request<RunRef>("POST", `${session(id)}/messages`, body, key),
  context: (
    id: string,
    revision: number,
    changes: FactChange[],
    skip = false,
  ) =>
    request<ContextResponse>("PATCH", `${session(id)}/context`, {
      expected_revision: revision,
      changes,
      skip_optional_questions: skip,
    }),
  run: (
    id: string,
    revision: number,
    intent: "prepare_report" | "analyze" | "followup",
    continue_run_id?: string,
  ) =>
    request<RunRef>(
      "POST",
      `${session(id)}/runs`,
      {
        intent,
        message: null,
        expected_revision: revision,
        ...(continue_run_id ? { continue_run_id } : {}),
      },
      newKey(),
    ),
  runStatus: (id: string, runId: string) =>
    request<RunStatus>("GET", `${session(id)}/runs/${runId}`),
  editDraft: (
    id: string,
    draftId: string,
    revision: number,
    draftRevision: number,
    summary: Summary,
  ) =>
    request<DraftUpdated>("PATCH", `${session(id)}/drafts/${draftId}`, {
      expected_revision: revision,
      draft_revision: draftRevision,
      summary,
    }),
  publish: (
    id: string,
    draftId: string,
    revision: number,
    draftRevision: number,
    key: string,
  ) =>
    request<ReportPublished>(
      "POST",
      `${session(id)}/reports`,
      {
        draft_id: draftId,
        draft_revision: draftRevision,
        expected_revision: revision,
        review_confirmed: true,
      },
      key,
    ),
  report: (id: string) => request<ReportSnapshot>("GET", `/reports/${id}`),
  events: (id: string, revision: number, fixture_id: string) =>
    request<{ event_ids: string[]; source: "mock"; revision: number }>(
      "POST",
      `${session(id)}/events`,
      { expected_revision: revision, fixture_id },
      newKey(),
    ),
};
