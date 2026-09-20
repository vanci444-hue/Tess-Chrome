/** Explicit local contract test transport. Never silently substituted for a failed API. */
import type {
  Envelope,
  Customer,
  SessionDetail,
  ReportSnapshot,
  RunStatus,
  Fact,
  FactChange,
  CaptureInput,
  Summary,
  Json,
  TimelineMessage,
} from "../types/api";
import { ApiError } from "../services/api";
import { mockHealth } from "./fixtures";
import { reportDemoModules } from "./reportFixtures";
import { currentFacts, appendConfirmation, reportFacts } from "../utils/facts";
import { factLabels, isMoneyFact, money, display } from "../utils/display";
interface Store {
  customers: Customer[];
  sessions: Record<
    string,
    SessionDetail & { title: string; created_at: string }
  >;
  reports: Record<string, ReportSnapshot>;
  runs: Record<string, RunStatus>;
  keys: Record<string, { body: string; data: unknown }>;
}
const STORAGE = "tess-contract-mock-v2";
const fresh = (): Store => ({
  customers: [],
  sessions: {},
  reports: {},
  runs: {},
  keys: {},
});
function read(): Store {
  try {
    return JSON.parse(localStorage.getItem(STORAGE) || "null") || fresh();
  } catch {
    return fresh();
  }
}
const uid = () => crypto.randomUUID(),
  now = () => new Date().toISOString();
const mask = (c: Customer) =>
  c.email
    ? c.email.slice(0, 1) + "***@" + c.email.split("@")[1]
    : (c.phone || "").slice(0, 3) + "****" + (c.phone || "").slice(-4);
const fail = (
  message: string,
  reason: string,
  metadata: Record<string, unknown> = {},
): never => {
  throw new ApiError(message, "CONFLICT", { reason, ...metadata });
};
const add = (s: SessionDetail, role: TimelineMessage["role"], text: string) => {
  s.timeline.push({
    id: uid(),
    session_id: s.id,
    seq: s.timeline.length + 1,
    role,
    type: "text",
    source_ref: null,
    content: { text },
    created_at: now(),
  });
};
function startRun(
  store: Store,
  s: SessionDetail,
  intent: string,
  text?: string,
): { run_id: string; session_id: string; status: string; kind: string } {
  if (text) add(s, "sales", text);
  const rid = uid();
  let result: RunStatus["result"] = {
    outcome: "answer",
    status: "ready",
    text: "Mock：已保留本次输入。真实分析需要连接后端及模型。",
    source_refs: [],
  };
  let status = "succeeded";
  if (intent === "interaction") {
    const budget = text?.match(/(?:月供|预算)[^\d]{0,8}(\d+(?:\.\d+)?)/);
    if (budget) {
      const old = currentFacts(s.facts).find(
        (f) => f.key === "monthly_budget" && f.state === "confirmed",
      );
      const val = Math.round(Number(budget[1]) * 100);
      const fact: Fact = {
        id: uid(),
        key: "monthly_budget",
        value: val,
        unit: "CNY_fen",
        state: old && old.value !== val ? "conflict" : "proposed",
        source_kind: "mock",
        source_id: rid,
        observed_at: now(),
        scope: "session",
        subject_id: null,
        evidence_note: null,
        supersedes: old ? [old.id] : [],
      };
      s.facts.push(fact);
      s.revision++;
      if (s.draft) s.draft.stale = true;
      s.questions = [
        {
          id: uid(),
          text: old
            ? "历史预算与本次输入不同，请确认本次月供预算。"
            : "请确认本次月供预算。",
          required: !!old,
          fact_ids: old ? [old.id, fact.id] : [fact.id],
          origin_run_id: rid,
          state: "open",
        },
      ];
      status = "needs_confirmation";
      result = {
        outcome: "context",
        status: "needs_confirmation",
        proposed_fact_ids: [fact.id],
        questions: s.questions as unknown as Json,
      };
    } else {
      add(s, "assistant", String(result.text));
    }
  }
  if (intent === "prepare_report") {
    if (!s.captures.some((c) => c.active)) {
      status = "failed";
      result = null;
    } else if (currentFacts(s.facts).some((f) => f.state === "conflict")) {
      status = "needs_confirmation";
      result = {
        outcome: "clarification",
        status: "needs_confirmation",
        questions: s.questions as unknown as Json,
      };
    } else {
      const summary: Summary = {
        comparing:
          s.captures.filter((c) => c.active).length + " 个 Model Y 候选方案",
        confirmed: reportFacts(s.facts).map(
          (f) =>
            (factLabels[f.key] || f.key) +
            "：" +
            (isMoneyFact(f.key) ? money(f.value) : display(f.value)),
        ),
        pending: [
          ...currentFacts(s.facts)
            .filter((f) => f.scope !== "historical" && f.state === "unknown")
            .map((f) => (factLabels[f.key] || f.key) + "未知，仍待确认"),
          ...(!reportFacts(s.facts).some(
            (f) => f.key === "trial_variant" && f.state === "confirmed",
          )
            ? ["实际试驾版本仍待确认"]
            : []),
          "Missing：地图未查询；能源成本仅为 Mock 假设试算",
        ],
      };
      s.draft = {
        id: uid(),
        session_id: s.id,
        draft_revision: 1,
        source_revision: s.revision,
        customer_revision: store.customers.find((c) => c.id === s.customer.id)!
          .revision,
        blocking_issues: [],
        requires_review: true,
        stale: false,
        report_data: {
          id: "",
          schema_version: 1,
          customer_salutation: s.customer.nickname + "，您好",
          generated_at: now(),
          published_at: null,
          summary,
          modules: [
            ...reportDemoModules(
              s.captures.find((c) => c.active)!.id,
              Number(
                s.captures
                  .find((c) => c.active)!
                  .immutable_payload.fields.find(
                    (f) => f.key === "vehicle_price",
                  )?.value,
              ),
              s.facts,
            ),
            {
              type: "options",
              status: "mock",
              source_refs: [],
              data: {
                options: s.captures
                  .filter((c) => c.active)
                  .map((c) => ({
                    capture_id: c.id,
                    validity: c.validity,
                    fields: c.immutable_payload.fields,
                    issues: c.issues,
                    preference: c.preference,
                    captured_at: c.immutable_payload.captured_at,
                  })) as unknown as Json,
              },
            },
            {
              type: "missing",
              status: "missing",
              source_refs: [],
              data: { reason: "契约 Mock：未调用真实模型/地图" },
            },
          ],
          sources: [],
          asset_ids: [],
          disclaimer: "契约 Mock，仅供前端验收",
        },
      };
      result = {
        outcome: "draft",
        status: "ready",
        draft_id: s.draft.id,
        draft_revision: 1,
      };
      add(s, "assistant", "Mock：审核草稿已准备。地图等缺失项已保留。");
    }
  }
  if (intent === "followup") {
    s.followup = {
      brief:
        "Mock：本次互动关注 " +
        (s.artifacts.at(-1)?.output || "待确认事项") +
        "。已提供信息，仍需客户确认。",
      source_event_ids: s.artifacts.map((a) => a.id),
    };
    result = {
      outcome: "followup",
      status: "ready",
      brief: s.followup.brief,
      source_event_ids: s.followup.source_event_ids,
    };
  }
  const run: RunStatus = {
    run_id: rid,
    session_id: s.id,
    status,
    events: [
      {
        seq: 1,
        type: status,
        label: "Mock 契约结果 · 未调用模型",
        tool_name: null,
        artifact_id: null,
      },
    ],
    last_seq: 1,
    result,
    error:
      status === "failed"
        ? {
            code: "MISSING_CAPTURE",
            message: "请先 Capture 至少一个候选方案。",
          }
        : null,
    lineage: {
      parent_run_id: null,
      root_run_id: rid,
      effective_intent: intent,
    },
    continuation:
      status === "needs_confirmation"
        ? { reason: "questions", can_continue: true, continued_by_run_id: null }
        : null,
  };
  store.runs[rid] = run;
  s.active_run = null;
  s.pending_run = run.continuation
    ? {
        run_id: rid,
        effective_intent: intent,
        continuation: run.continuation,
        questions: s.questions,
      }
    : null;
  return { run_id: rid, session_id: s.id, status: "queued", kind: intent };
}
export async function mockRequest<T>(
  method: string,
  url: string,
  input?: unknown,
  key?: string,
): Promise<Envelope<T>> {
  const store = read();
  for (const session of Object.values(store.sessions)) {
    const customer = store.customers.find((c) => c.id === session.customer.id);
    if (customer)
      session.customer = {
        id: customer.id,
        nickname: customer.nickname,
        contact_mask: mask(customer),
        revision: customer.revision,
        phone: customer.phone,
        email: customer.email,
      };
  }
  const u = new URL(url, "http://mock.local"),
    path = u.pathname,
    b = (input || {}) as Record<string, unknown>,
    body = JSON.stringify(input);
  if (key && store.keys[key]) {
    if (store.keys[key].body !== body)
      fail("请求标识已用于其他操作", "IDEMPOTENCY_CONFLICT");
    return envelope(store.keys[key].data as T);
  }
  let data: unknown;
  const sm = path.match(/^\/sessions\/([^/]+)/),
    s = sm ? store.sessions[sm[1]] : undefined;
  if (sm && !s) fail("会话不存在", "SESSION_NOT_FOUND");
  if (
    s &&
    method !== "GET" &&
    "expected_revision" in b &&
    b.expected_revision !== s.revision
  )
    fail("信息已更新，请刷新后再确认", "STALE_REVISION");
  if (path.endsWith("/audio"))
    throw new ApiError(
      "契约 Mock 模式不启用真实音频，请关闭 Mock 并连接已配置的后端。",
      "ASR_NOT_CONFIGURED",
    );
  if (path === "/health") data = { ...mockHealth };
  else if (path === "/customers/extract") {
    const text = String(b.text || "");
    const email = text.match(/[\w.+-]+@[\w.-]+\.[a-zA-Z]+/)?.[0] || null;
    const phone = text.match(/1[3-9]\d{9}/)?.[0] || null;
    const nickname =
      text.match(/(?:称呼|姓名|客户)[:：\s]+([^；;，,\n]+)/)?.[1] || null;
    data = {
      extraction_id: uid(),
      proposed: { nickname, phone, email },
      historical_facts: [],
      missing: [
        ...(!nickname ? ["nickname"] : []),
        ...(!phone && !email ? ["contact"] : []),
      ],
    };
  } else if (path === "/customers" && method === "GET") {
    const q = u.searchParams.get("q") || "";
    data = {
      items: store.customers
        .filter((c) =>
          [c.nickname, c.email, c.phone].some((v) => v?.includes(q)),
        )
        .map((c) => ({
          id: c.id,
          nickname: c.nickname,
          contact_mask: mask(c),
          latest_session_id:
            Object.values(store.sessions)
              .filter((s) => s.customer.id === c.id)
              .at(-1)?.id || null,
        })),
      next_cursor: null,
    };
  } else if (path === "/customers" && method === "POST") {
    const dup = store.customers.filter(
      (c) =>
        (b.phone && c.phone === b.phone) || (b.email && c.email === b.email),
    );
    if (dup.length && !b.allow_duplicate)
      fail("已有相同联系方式的客户", "DUPLICATE_CONTACT", {
        candidates: dup.map((c) => ({
          id: c.id,
          nickname: c.nickname,
          contact_mask: mask(c),
          latest_session_id:
            Object.values(store.sessions).find((s) => s.customer.id === c.id)
              ?.id || null,
        })),
      });
    if (!b.nickname || (!b.phone && !b.email) || !b.identity_confirmed)
      fail("请确认称呼和联系方式", "MISSING_IDENTITY");
    const c: Customer = {
      id: uid(),
      nickname: String(b.nickname),
      phone: b.phone as string | null,
      email: b.email as string | null,
      revision: 1,
    };
    store.customers.push(c);
    data = {
      id: c.id,
      nickname: c.nickname,
      phone: c.phone,
      email: c.email,
      revision: c.revision,
    };
  } else if (/^\/customers\/[^/]+$/.test(path) && method === "PATCH") {
    const c = store.customers.find((c) => c.id === path.split("/")[2]);
    if (!c) fail("客户不存在", "CUSTOMER_NOT_FOUND");
    if (c!.revision !== b.expected_revision)
      fail("身份信息已变化，请重新核对", "STALE_REVISION");
    const dup = store.customers.some(
      (other) =>
        other.id !== c!.id &&
        ((b.phone && other.phone === b.phone) ||
          (b.email && other.email === b.email)),
    );
    if (dup && !b.allow_duplicate)
      fail("此联系方式关联其他客户，请核对身份", "DUPLICATE_CONTACT");
    if (!b.nickname || (!b.phone && !b.email) || !b.identity_confirmed)
      fail("请补齐并确认身份", "MISSING_IDENTITY");
    c!.nickname = String(b.nickname);
    c!.phone = b.phone as string | null;
    c!.email = b.email as string | null;
    c!.revision++;
    for (const session of Object.values(store.sessions)) {
      if (session.customer.id === c!.id) {
        session.customer = {
          id: c!.id,
          nickname: c!.nickname,
          contact_mask: mask(c!),
          revision: c!.revision,
          phone: c!.phone,
          email: c!.email,
        };
        if (session.draft) session.draft.stale = true;
      }
    }
    data = {
      id: c!.id,
      nickname: c!.nickname,
      phone: c!.phone,
      email: c!.email,
      revision: c!.revision,
    };
  } else if (path === "/sessions" && method === "POST") {
    const c = store.customers.find((c) => c.id === b.customer_id)!;
    const id = uid();
    store.sessions[id] = {
      id,
      title: String(b.title),
      created_at: now(),
      customer: {
        id: c.id,
        nickname: c.nickname,
        contact_mask: mask(c),
        revision: c.revision,
        phone: c.phone,
        email: c.email,
      },
      revision: 1,
      status: "collecting",
      trial_vehicle: null,
      captures: [],
      inputs: [],
      facts: [],
      questions: [],
      artifacts: [],
      active_run: null,
      pending_run: null,
      draft: null,
      reports: [],
      timeline: [],
      followup: null,
    };
    data = {
      id,
      customer_id: c.id,
      title: b.title,
      revision: 1,
      status: "collecting",
      created_at: store.sessions[id].created_at,
    };
  } else if (path === "/sessions" && method === "GET")
    data = {
      items: Object.values(store.sessions)
        .filter((s) => s.customer.id === u.searchParams.get("customer_id"))
        .reverse()
        .map((s) => ({
          id: s.id,
          title: s.title,
          status: s.status,
          created_at: s.created_at,
          latest_report_id: s.reports.at(-1)?.report_id || null,
        })),
      next_cursor: null,
    };
  else if (/^\/customers\/[^/]+\/reports$/.test(path)) {
    data = {
      items: Object.values(store.sessions)
        .filter((s) => s.customer.id === path.split("/")[2])
        .flatMap((s) => s.reports)
        .sort((a, b) => b.published_at.localeCompare(a.published_at)),
      next_cursor: null,
    };
  } else if (s && path === `/sessions/${s.id}`) {
    data = {
      id: s.id,
      customer: s.customer,
      revision: s.revision,
      status: s.status,
      trial_vehicle: s.trial_vehicle,
      captures: s.captures,
      inputs: s.inputs,
      facts: s.facts,
      questions: s.questions,
      artifacts: s.artifacts,
      active_run: s.active_run,
      pending_run: s.pending_run,
      draft: s.draft,
      reports: s.reports,
      timeline: s.timeline,
      followup: s.followup,
    };
  } else if (s && path.endsWith("/captures") && method === "POST") {
    if (s.captures.filter((c) => c.active).length >= 3)
      fail("已有三个候选，请先移除一个", "CANDIDATE_LIMIT");
    const id = uid(),
      payload = b.capture as CaptureInput;
    s.captures.push({
      id,
      session_id: s.id,
      immutable_payload: payload,
      validity: "valid",
      issues: payload.issues,
      active: true,
      preference: null,
    });
    s.revision++;
    if (s.draft) s.draft.stale = true;
    data = {
      capture_id: id,
      session_id: s.id,
      revision: s.revision,
      validity: "valid",
      issues: payload.issues,
    };
  } else if (s && path.includes("/captures/") && method === "PATCH") {
    const c = s.captures.find((c) => c.id === path.split("/").at(-1))!;
    if (b.active === false) c.active = false;
    if ("preference" in b) c.preference = b.preference as string | null;
    s.revision++;
    if (s.draft) s.draft.stale = true;
    data = {
      capture_id: c.id,
      active: c.active,
      preference: c.preference,
      revision: s.revision,
    };
  } else if (
    s &&
    (path.endsWith("/messages") || path.endsWith("/runs")) &&
    method === "POST"
  )
    data = startRun(
      store,
      s,
      String(b.intent || "interaction"),
      b.text as string | undefined,
    );
  else if (s && path.includes("/runs/") && method === "GET")
    data = { ...store.runs[path.split("/").at(-1)!] };
  else if (s && path.endsWith("/context")) {
    for (const c of b.changes as FactChange[]) {
      s.facts = appendConfirmation(s.facts, c, {
        id: uid(),
        sourceId: uid(),
        observedAt: now(),
      });
    }
    s.questions = s.questions.filter(
      (q) =>
        q.required &&
        currentFacts(s.facts).some(
          (f) => f.state === "conflict" && q.fact_ids.includes(f.id),
        ),
    );
    s.revision++;
    if (s.draft) s.draft.stale = true;
    data = {
      revision: s.revision,
      blocking_issues: [],
      invalidated_artifact_ids: [],
      optional_questions_stopped: !!b.skip_optional_questions,
      continuation_hint: null,
    };
  } else if (s && path.includes("/drafts/")) {
    if (!s.draft) fail("没有草稿", "DRAFT_NOT_FOUND");
    s.draft!.report_data.summary = b.summary as Summary;
    s.draft!.draft_revision++;
    data = {
      draft_id: s.draft!.id,
      draft_revision: s.draft!.draft_revision,
      requires_review: true,
      blocking_issues: [],
    };
  } else if (s && path.endsWith("/reports") && method === "POST") {
    const d = s.draft;
    if (
      !d ||
      d.stale ||
      d.draft_revision !== b.draft_revision ||
      !b.review_confirmed ||
      currentFacts(s.facts).some((f) => f.state === "conflict")
    )
      fail("请重新生成并审核草稿", "STALE_DRAFT");
    const id = uid(),
      time = now(),
      mid = uid();
    store.reports[id] = {
      ...structuredClone(d!.report_data),
      id,
      published_at: time,
    };
    const report = {
      report_id: id,
      session_id: s.id,
      session_title: store.sessions[s.id].title,
      title: s.customer.nickname + " 的试驾报告",
      published_at: time,
      url: `/?mock=1#/reports/${id}`,
    };
    s.reports.push(report);
    s.timeline.push({
      id: mid,
      session_id: s.id,
      seq: s.timeline.length + 1,
      role: "system",
      type: "report_card",
      source_ref: { kind: "report", id },
      content: { report_id: id, title: report.title, published_at: time },
      created_at: time,
    });
    data = {
      report_id: id,
      session_id: s.id,
      timeline_message_id: mid,
      url: report.url,
      published_at: time,
      snapshot_hash: "contract-mock",
    };
  } else if (s && path.endsWith("/events")) {
    const id = uid();
    s.artifacts.push({
      id,
      tool_name: "mock_event",
      status: "mock",
      output: String(b.fixture_id),
    });
    s.revision++;
    data = { event_ids: [id], source: "mock", revision: s.revision };
  } else if (path.startsWith("/reports/")) {
    const r = store.reports[path.split("/")[2]];
    if (!r) fail("报告不存在", "REPORT_NOT_FOUND");
    data = { ...r };
  } else throw new ApiError("该接口不在契约 Mock 范围", "MOCK_UNSUPPORTED");
  if (key) store.keys[key] = { body, data };
  localStorage.setItem(STORAGE, JSON.stringify(store));
  return envelope(structuredClone(data) as T);
}
function envelope<T>(data: T): Envelope<T> {
  return {
    success: true,
    data,
    error: null,
    error_code: null,
    message: "Mock",
    timestamp: now(),
    request_id: uid(),
    metadata: { mode: "contract_mock" },
  };
}
