/**
 * 场景 6 · 生成 Test Drive Report（路径 B）
 * 纯前端 Mock：不打后端落草稿接口；草稿存在本机，预览页读取。
 */

import { prepareFinanceScene } from "./demoFinance";
import { reportDemoModules } from "./reportFixtures";
import { seedStaticReport } from "./staticReportHtml";
import type {
  Draft,
  Json,
  SessionDetail,
  Summary,
} from "../types/api";

/** 路径 B：已确认决策语境下的报告摘要（客户向） */
export const DEMO_REPORT_SUMMARY: Summary = {
  comparing:
    "Option 1 白色长续航，与 Option 2 对照方案——今天讨论的两套 Model Y 候选",
  confirmed: [
    "关注：白色长续航与座舱空间；月供与家充不确定性；接送便利优先",
    "已解决：金融方案已对照候选讲清；超充中后段掉功率已解释并获理解",
    "权衡：保长续航则月供更紧；预算紧时可用后驱换空间，但会牺牲续航偏好",
    "Must-have：白色与当前轮毂意向；可妥协：后驱 vs 长续航仍可谈",
  ],
  pending: [
    "小区装桩可行性仍待核实（勿写死）",
    "与家人最终拍板",
  ],
};

export const REPORT_SCRIPT = {
  /** 销售点「生成报告」时写入会话的 query */
  salesQuery: "帮我生成这个客户最近一次试驾的报告。",
  intent: {
    title: "准备试驾报告",
    lines: ["汇总 Explicit Context → 生成客户向草稿"],
  },
  router: {
    title: "→ Report Composer",
    lines: ["CRM · 候选 · 金融 · 决策语境"],
  },
  planSteps: [
    "读取 CRM 与候选配置",
    "并入金融结论与已确认决策语境",
    "生成客户向草稿（不追问销售）",
  ],
  sources: [
    "CRM 初始信息",
    "候选配置 Option 1 / 2",
    "金融规划结果",
    "销售补充 · Decision Context（已确认）",
  ],
  reply:
    "报告已生成。可在新标签打开，或复制链接 / 发给客户的文案。",
} as const;

const DRAFT_KEY = (sessionId: string) => `tess.demo.draft.v1.${sessionId}`;

function storage() {
  try {
    return localStorage;
  } catch {
    return sessionStorage;
  }
}

export function readDemoDraft(sessionId: string): Draft | null {
  try {
    const store = storage();
    const raw =
      store.getItem(DRAFT_KEY(sessionId)) ||
      sessionStorage.getItem(DRAFT_KEY(sessionId));
    if (!raw) return null;
    return JSON.parse(raw) as Draft;
  } catch {
    return null;
  }
}

export function writeDemoDraft(draft: Draft) {
  const raw = JSON.stringify(draft);
  try {
    localStorage.setItem(DRAFT_KEY(draft.session_id), raw);
  } catch {
    /* ignore quota */
  }
  try {
    sessionStorage.setItem(DRAFT_KEY(draft.session_id), raw);
  } catch {
    /* ignore */
  }
}

export function clearDemoDraft(sessionId: string) {
  try {
    localStorage.removeItem(DRAFT_KEY(sessionId));
  } catch {
    /* ignore */
  }
  try {
    sessionStorage.removeItem(DRAFT_KEY(sessionId));
  } catch {
    /* ignore */
  }
}

export function buildDemoDraft(session: SessionDetail, summary = DEMO_REPORT_SUMMARY): Draft {
  const active = session.captures.filter((c) => c.active);
  if (!active.length) {
    throw new Error("至少需要一个候选方案才能生成报告");
  }
  const primary = active[0];
  const price = Number(
    primary.immutable_payload.fields.find((f) => f.key === "vehicle_price")
      ?.value ?? 0,
  );
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    session_id: session.id,
    draft_revision: 1,
    source_revision: session.revision,
    customer_revision: 1,
    blocking_issues: [],
    requires_review: true,
    stale: false,
    report_data: {
      id: "",
      schema_version: 1,
      customer_salutation: "张先生，您好",
      generated_at: now,
      published_at: null,
      summary: structuredClone(summary),
      modules: [
        ...reportDemoModules(primary.id, price, session.facts),
        {
          type: "options",
          status: "mock",
          source_refs: [],
          data: {
            options: active.map((c) => ({
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
          data: { reason: "Demo：未调用真实模型 / 地图" },
        },
      ],
      sources: [],
      asset_ids: [],
      disclaimer:
        "动态内容反映采集时的信息；Mock 与 Estimate 不代表 Tesla 当前官方承诺。本报告为前端 Demo。",
    },
  };
}

/** 纯前端落草稿，并写出移动端静态 HTML */
export function seedDemoReportDraft(session: SessionDetail): Draft {
  const draft = buildDemoDraft(session);
  writeDemoDraft(draft);
  seedStaticReport(session, draft);
  return draft;
}

export function updateDemoDraftSummary(
  sessionId: string,
  summary: Summary,
): Draft | null {
  const draft = readDemoDraft(sessionId);
  if (!draft) return null;
  const next: Draft = {
    ...draft,
    draft_revision: draft.draft_revision + 1,
    report_data: {
      ...draft.report_data,
      summary: structuredClone(summary),
    },
  };
  writeDemoDraft(next);
  return next;
}

/** 进入场景 6：复用场景 3 种子；摘要按场景 5 完成态组装 */
export async function prepareReportScene(sessionId: string) {
  await prepareFinanceScene(sessionId);
}

export function tradeoffLines(summary: Summary): string[] {
  return summary.confirmed
    .filter((line) => line.startsWith("权衡：") || line.startsWith("权衡:"))
    .map((line) => line.replace(/^权衡[:：]\s*/, ""));
}

export function matterLines(summary: Summary): string[] {
  return summary.confirmed.filter(
    (line) =>
      line.startsWith("关注：") ||
      line.startsWith("关注:") ||
      line.startsWith("Must-have"),
  );
}

export function resolvedLines(summary: Summary): string[] {
  return summary.confirmed.filter(
    (line) => line.startsWith("已解决：") || line.startsWith("已解决:"),
  );
}
