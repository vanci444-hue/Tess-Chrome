import type { Capture, CaptureInput } from "../types/api";
import { tess } from "../services/tess";
import { optionLabel } from "../utils/display";
import { clearAppliedPlans } from "./sessionPlans";

/**
 * 场景 3 · 多轮 Case B · Option 2（文案与脚本见 caseBScript.ts）
 */
export {
  FINANCE_INPUT_B1,
  FINANCE_INPUT_B2,
  FINANCE_INPUT_B3,
} from "./caseBScript";
import {
  FINANCE_INPUT_B1,
  FINANCE_INPUT_B2,
  FINANCE_INPUT_B3,
} from "./caseBScript";

/** @deprecated 兼容旧复制按钮；正式多轮用 B1/B2/B3 */
export const FINANCE_INPUT_B = FINANCE_INPUT_B1;

/** 场景 3 · 单轮 Case A（硬约束，直接出方案） */
export const FINANCE_INPUT_A =
  "针对 Option 1：提车现金一共最多 10 万，月供不超过 3500。";

const CASH_MAX_YUAN = 100_000;
const MONTHLY_CAP_YUAN = 3_500;
const VEHICLE_DOWN_YUAN = 79_900;
const TAX_INS_PLATE_YUAN = CASH_MAX_YUAN - VEHICLE_DOWN_YUAN;
const TERM_MONTHS = 60;
/** 演示用标配底价：保证「砍光加装」与「只留辅助驾驶」都能压进月供上限 */
const DEMO_BASE_YUAN = 259_900;
/** 演示用辅助驾驶加价：现配置仍破月供，但「留 AP 砍外观」可满足 */
const DEMO_AUTOPILOT_YUAN = 28_000;

export type FinanceToolCall = {
  id: string;
  title: string;
  priceYuan: number;
  downYuan: number;
  monthlyYuan: number;
  ok: boolean;
  note: string;
};

export type FinancePlanOption = {
  id: "A" | "B";
  title: string;
  cuts: string[];
  keep: string[];
  priceYuan: number;
  monthlyYuan: number;
  downYuan: number;
  cashYuan: number;
  ok: boolean;
  summary: string;
  /** 相对另一方案的优势 */
  pros: string;
  /** 相对另一方案的代价 */
  cons: string;
};

export type FinanceCaseAResult = {
  optionLabel: string;
  understand: string[];
  planSteps: string[];
  tools: FinanceToolCall[];
  currentPriceYuan: number;
  currentMonthly: number;
  downYuan: number;
  taxInsPlateYuan: number;
  optionA: FinancePlanOption;
  optionB: FinancePlanOption;
  recommend: "A" | "B";
  recommendReason: string;
  actions: { id: "apply_a" | "apply_b"; label: string }[];
  sourceCapture?: Capture;
};

type Surcharge = {
  group: string;
  name: string;
  amountYuan: number;
};

function fen(yuan: number) {
  return Math.round(yuan * 100);
}

function fenToYuan(value: unknown): number | null {
  return typeof value === "number" ? Math.round(value / 100) : null;
}

function field(capture: Capture | undefined, key: string) {
  return capture?.immutable_payload.fields.find((f) => f.key === key)?.value;
}

function surchargesFrom(capture: Capture | undefined): Surcharge[] {
  const raw = field(capture, "option_surcharges");
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const name = optionLabel(item.name);
    const amountFen = typeof item.amount === "number" ? item.amount : 0;
    if (!name || name === "未知" || amountFen <= 0) return [];
    return [
      {
        group: String(item.group || ""),
        name,
        amountYuan: Math.round(amountFen / 100),
      },
    ];
  });
}

function isAutopilot(item: Surcharge) {
  return item.group === "autopilot" || /辅助驾驶|智能辅助/.test(item.name);
}

function monthlyPayment(priceYuan: number, downYuan: number) {
  return Math.ceil(Math.max(priceYuan - downYuan, 0) / TERM_MONTHS);
}

function formatYuan(value: number) {
  return `¥${value.toLocaleString("zh-CN")}`;
}

function normalizeInput(text: string) {
  return text.replace(/\s+/g, "").replace(/[。．.!?！？]/g, "");
}

export function isFinanceInputA(text: string) {
  return normalizeInput(text) === normalizeInput(FINANCE_INPUT_A);
}

export function isFinanceInputB1(text: string) {
  return normalizeInput(text) === normalizeInput(FINANCE_INPUT_B1);
}

export function isFinanceInputB2(text: string) {
  return normalizeInput(text) === normalizeInput(FINANCE_INPUT_B2);
}

export function isFinanceInputB3(text: string) {
  return normalizeInput(text) === normalizeInput(FINANCE_INPUT_B3);
}

export function isFinanceInputB(text: string) {
  return (
    isFinanceInputB1(text) || isFinanceInputB2(text) || isFinanceInputB3(text)
  );
}

function makeFields(
  values: Record<string, unknown>,
  now: string,
): CaptureInput["fields"] {
  return Object.entries(values).map(([key, value]) => ({
    key,
    value: value as CaptureInput["fields"][number]["value"],
    unit:
      /price|payment|down_payment/.test(key)
        ? "CNY_fen"
        : key === "term_months"
          ? "months"
          : key === "rate_value"
            ? "percent"
            : key === "range_cltc"
              ? "km"
              : key === "top_speed"
                ? "km/h"
                : key === "zero_to_hundred"
                  ? "s"
                  : null,
    raw_text: Array.isArray(value)
      ? value.length
        ? value.join(" · ")
        : "无"
      : String(value),
    evidence: { kind: "dom_selected", selector_hint: "finance-scene-seed" },
    observed_at: now,
  }));
}

/** Option 1：含辅助驾驶+加装，现方案破月供；优化后 A/B 均可满足 */
export function financeSceneOption1Input(): CaptureInput {
  const now = new Date().toISOString();
  const price = DEMO_BASE_YUAN + 8_000 + 12_000 + DEMO_AUTOPILOT_YUAN;
  const monthly = monthlyPayment(price, VEHICLE_DOWN_YUAN);
  return {
    source_url: "https://www.tesla.cn/modely/design#overview",
    captured_at: now,
    adapter_version: "finance-scene-seed/option-1",
    page_fingerprint: crypto.randomUUID(),
    readiness: "ready",
    issues: [
      {
        code: "MOCK_DATA",
        field: null,
        blocking: false,
        message: "场景 3 预制候选，非官网实时快照。",
      },
    ],
    fields: makeFields(
      {
        model: "Model Y",
        variant: "后轮驱动版",
        paint: "纯黑车漆",
        wheels: "21 英寸乌伯莱轮毂",
        interior: "深色高级内饰",
        seats: "五座",
        autopilot: "特斯拉辅助驾驶套件",
        accessories: [],
        extras: [
          "特斯拉辅助驾驶套件",
          "纯黑车漆",
          "21 英寸乌伯莱轮毂",
        ],
        option_surcharges: [
          {
            group: "paint",
            name: "纯黑车漆",
            amount: fen(8_000),
            included: false,
          },
          {
            group: "wheels",
            name: "21 英寸乌伯莱轮毂",
            amount: fen(12_000),
            included: false,
          },
          {
            group: "autopilot",
            name: "特斯拉辅助驾驶套件",
            amount: fen(DEMO_AUTOPILOT_YUAN),
            included: false,
          },
        ],
        vehicle_price: fen(price),
        price_basis: "车辆价格",
        delivery: "3–5周",
        range_cltc: 593,
        top_speed: 201,
        zero_to_hundred: 5.9,
        monthly_payment: fen(monthly),
        down_payment: fen(VEHICLE_DOWN_YUAN),
        term_months: TERM_MONTHS,
        rate_value: 0,
        rate_basis: "年化费率",
      },
      now,
    ),
  };
}

/** Option 2：多轮 Case B 用——现配置破月供；澄清后 A/B 均可满足硬约束 */
export function financeSceneOption2Input(): CaptureInput {
  const now = new Date().toISOString();
  const price = DEMO_BASE_YUAN + 8_000 + 8_000 + DEMO_AUTOPILOT_YUAN;
  const monthly = monthlyPayment(price, VEHICLE_DOWN_YUAN);
  return {
    source_url: "https://www.tesla.cn/modely/design#overview",
    captured_at: now,
    adapter_version: "finance-scene-seed/option-2",
    page_fingerprint: crypto.randomUUID(),
    readiness: "ready",
    issues: [
      {
        code: "MOCK_DATA",
        field: null,
        blocking: false,
        message: "场景 3 预制候选，非官网实时快照。",
      },
    ],
    fields: makeFields(
      {
        model: "Model Y",
        variant: "后轮驱动版",
        paint: "纯白车漆",
        wheels: "20 英寸螺旋轮毂",
        interior: "深色高级内饰",
        seats: "五座",
        autopilot: "特斯拉辅助驾驶套件",
        accessories: [],
        extras: [
          "特斯拉辅助驾驶套件",
          "纯白车漆",
          "20 英寸螺旋轮毂",
        ],
        option_surcharges: [
          {
            group: "paint",
            name: "纯白车漆",
            amount: fen(8_000),
            included: false,
          },
          {
            group: "wheels",
            name: "20 英寸螺旋轮毂",
            amount: fen(8_000),
            included: false,
          },
          {
            group: "autopilot",
            name: "特斯拉辅助驾驶套件",
            amount: fen(DEMO_AUTOPILOT_YUAN),
            included: false,
          },
        ],
        vehicle_price: fen(price),
        price_basis: "车辆价格",
        delivery: "3–5周",
        range_cltc: 593,
        top_speed: 201,
        zero_to_hundred: 5.9,
        monthly_payment: fen(monthly),
        down_payment: fen(VEHICLE_DOWN_YUAN),
        term_months: TERM_MONTHS,
        rate_value: 0,
        rate_basis: "年化费率",
      },
      now,
    ),
  };
}

/** 进入场景 3：清掉现有候选，写入假 Option 1 / 2 */
export async function prepareFinanceScene(sessionId: string) {
  clearAppliedPlans(sessionId);
  const detail = await tess.session(sessionId);
  let revision = detail.revision;
  for (const capture of detail.captures.filter((item) => item.active)) {
    const updated = await tess.updateCapture(sessionId, capture.id, revision, {
      active: false,
    });
    revision = updated.revision;
  }
  const first = await tess.capture(
    sessionId,
    revision,
    financeSceneOption1Input(),
  );
  revision = first.revision;
  await tess.capture(sessionId, revision, financeSceneOption2Input());
}

export function buildFinanceCaseA(
  capture: Capture | undefined,
  optionIndex = 0,
): FinanceCaseAResult {
  const downYuan = VEHICLE_DOWN_YUAN;
  const listed = surchargesFrom(capture);
  const priceFromCapture = fenToYuan(field(capture, "vehicle_price"));
  const optionLabelText = `Option ${optionIndex + 1}`;

  let autopilot = listed.find(isAutopilot);
  let others = listed.filter((item) => !isAutopilot(item));

  if (!autopilot) {
    autopilot = {
      group: "autopilot",
      name: "特斯拉辅助驾驶套件",
      amountYuan: DEMO_AUTOPILOT_YUAN,
    };
  }
  if (others.reduce((sum, item) => sum + item.amountYuan, 0) < 16_000) {
    others = [
      { group: "paint", name: "纯黑车漆", amountYuan: 8_000 },
      { group: "wheels", name: "21 英寸乌伯莱轮毂", amountYuan: 12_000 },
      ...others,
    ];
  }

  const extrasTotal =
    autopilot.amountYuan +
    others.reduce((sum, item) => sum + item.amountYuan, 0);
  const baseYuan =
    priceFromCapture != null
      ? Math.max(priceFromCapture - extrasTotal, DEMO_BASE_YUAN)
      : DEMO_BASE_YUAN;
  const currentPrice = baseYuan + extrasTotal;
  const currentMonthly = monthlyPayment(currentPrice, downYuan);

  const sortedOthers = [...others].sort(
    (a, b) => b.amountYuan - a.amountYuan,
  );
  const cutExtras = sortedOthers.slice(0, Math.min(2, sortedOthers.length));
  // 方案 A：砍辅助驾驶 + 外观加装 → 月供更低
  const planAPrice =
    currentPrice -
    autopilot.amountYuan -
    cutExtras.reduce((sum, item) => sum + item.amountYuan, 0);
  const planAMonthly = monthlyPayment(planAPrice, downYuan);
  // 方案 B：保留辅助驾驶，只砍外观 → 仍压进月供上限
  const planBPrice = baseYuan + autopilot.amountYuan;
  const planBMonthly = monthlyPayment(planBPrice, downYuan);
  const planAOk = planAMonthly <= MONTHLY_CAP_YUAN;
  const planBOk = planBMonthly <= MONTHLY_CAP_YUAN;

  // 两次工具调用：现配置一次，A/B 对照一次（避免刷屏）
  const tools: FinanceToolCall[] = [
    {
      id: "t1",
      title: "Finance Tool · 现配置",
      priceYuan: currentPrice,
      downYuan,
      monthlyYuan: currentMonthly,
      ok: currentMonthly <= MONTHLY_CAP_YUAN,
      note:
        currentMonthly <= MONTHLY_CAP_YUAN
          ? `月供 ${formatYuan(currentMonthly)}，满足`
          : `月供 ${formatYuan(currentMonthly)}，超出 ${MONTHLY_CAP_YUAN}`,
    },
    {
      id: "t2",
      title: "Finance Tool · 方案 A / B 对照",
      priceYuan: planAPrice,
      downYuan,
      monthlyYuan: planAMonthly,
      ok: planAOk && planBOk,
      note: `A：去掉${[autopilot.name, ...cutExtras.map((i) => i.name)].join("、")} → 月供 ${formatYuan(planAMonthly)}（满足）；B：保留${autopilot.name}、去掉外观加装 → 月供 ${formatYuan(planBMonthly)}（满足）`,
    },
  ];

  const cutExtraNames = cutExtras.map((item) => item.name);
  const optionA: FinancePlanOption = {
    id: "A",
    title: "方案 A",
    cuts: [autopilot.name, ...cutExtraNames],
    keep: [],
    priceYuan: planAPrice,
    monthlyYuan: planAMonthly,
    downYuan,
    cashYuan: CASH_MAX_YUAN,
    ok: planAOk,
    summary: `去掉 ${[autopilot.name, ...cutExtraNames].join("、")}`,
    pros: `月供更低（${formatYuan(planAMonthly)}），月供压力更小，后续加装空间更大`,
    cons: "放弃辅助驾驶与当前外观加装，驾驶辅助能力回到基础版",
  };
  const optionB: FinancePlanOption = {
    id: "B",
    title: "方案 B",
    cuts: others.map((item) => item.name),
    keep: [autopilot.name],
    priceYuan: planBPrice,
    monthlyYuan: planBMonthly,
    downYuan,
    cashYuan: CASH_MAX_YUAN,
    ok: planBOk,
    summary: `保留 ${autopilot.name}，去掉其他加装`,
    pros: "保留辅助驾驶，通勤辅助体验更完整",
    cons: `月供更高（${formatYuan(planBMonthly)}），外观回到更素的配置，月供余量更薄`,
  };

  return {
    optionLabel: optionLabelText,
    understand: [
      `对象：${optionLabelText}`,
      `提车现金 ≤ ${formatYuan(CASH_MAX_YUAN)}（默认含购置税 / 保险 / 上牌）`,
      `车款首付 ${formatYuan(downYuan)}，税险牌估算 ${formatYuan(TAX_INS_PLATE_YUAN)}`,
      `月供 ≤ ${formatYuan(MONTHLY_CAP_YUAN)}`,
    ],
    planSteps: [
      "先按现配置试算",
      "不满足 → 生成两个都可满足硬约束的方案",
      "对照优劣，给出推荐，由销售/客户选择落地",
    ],
    tools,
    currentPriceYuan: currentPrice,
    currentMonthly,
    downYuan,
    taxInsPlateYuan: TAX_INS_PLATE_YUAN,
    optionA,
    optionB,
    recommend: "A",
    recommendReason: `两个方案都能同时满足提车现金与月供。更推荐方案 A：月供 ${formatYuan(planAMonthly)}，比方案 B 的 ${formatYuan(planBMonthly)} 更宽裕；若客户更在意辅助驾驶，再选方案 B 即可。`,
    actions: [
      { id: "apply_a", label: `按方案 A 更改 ${optionLabelText}` },
      { id: "apply_b", label: `按方案 B 更改 ${optionLabelText}` },
    ],
    sourceCapture: capture,
  };
}

export function buildTrialCapture(
  source: Capture | undefined,
  plan: FinancePlanOption,
  versionTag: string,
): Capture {
  const now = new Date().toISOString();
  const baseFields = source?.immutable_payload.fields || [];
  const byKey = new Map(baseFields.map((f) => [f.key, f]));
  const removeAp = plan.cuts.some((c) => /辅助驾驶/.test(c));
  const paint = plan.cuts.some((c) => /车漆|纯黑|纯白/.test(c))
    ? "星空灰车漆"
    : byKey.get("paint")?.value;
  const wheels = plan.cuts.some((c) => /轮毂/.test(c))
    ? "19 英寸交互风暴轮毂"
    : byKey.get("wheels")?.value;

  const values: Record<string, unknown> = {
    model: "Model Y",
    variant: String(byKey.get("variant")?.value || "后轮驱动版"),
    paint: String(paint || "星空灰车漆"),
    wheels: String(wheels || "19 英寸交互风暴轮毂"),
    interior: String(byKey.get("interior")?.value || "深色高级内饰"),
    seats: String(byKey.get("seats")?.value || "五座"),
    autopilot: removeAp
      ? "基础辅助驾驶"
      : String(byKey.get("autopilot")?.value || "特斯拉辅助驾驶套件"),
    accessories: [],
    extras: [],
    vehicle_price: fen(plan.priceYuan),
    monthly_payment: fen(plan.monthlyYuan),
    down_payment: fen(plan.downYuan),
    term_months: TERM_MONTHS,
    rate_value: 0,
    rate_basis: "年化费率",
    delivery: String(byKey.get("delivery")?.value || "3–5周"),
    range_cltc: byKey.get("range_cltc")?.value ?? 593,
    top_speed: byKey.get("top_speed")?.value ?? 201,
    zero_to_hundred: byKey.get("zero_to_hundred")?.value ?? 5.9,
  };

  return {
    id: `trial-${versionTag}-${crypto.randomUUID()}`,
    session_id: source?.session_id || "demo",
    immutable_payload: {
      source_url:
        source?.immutable_payload.source_url ||
        "https://www.tesla.cn/modely/design#overview",
      captured_at: now,
      adapter_version: "finance-trial-demo",
      page_fingerprint: crypto.randomUUID(),
      readiness: "ready",
      fields: makeFields(values, now),
      issues: [
        {
          code: "MOCK_DATA",
          field: null,
          blocking: false,
          message: `试算版 ${versionTag}`,
        },
      ],
    },
    validity: "valid",
    issues: [],
    active: true,
    preference: null,
  };
}

export function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
