import type {
  FinanceCaseAResult,
  FinancePlanOption,
  FinanceToolCall,
} from "./demoFinance";
import type { Capture } from "../types/api";

/**
 * 场景 3 · Case B（Option 2）多轮文案定稿
 *
 * 口径（与 Case A 一致：澄清后给出两个都可满足的方案）：
 * - 提车现金 ≤ ¥100,000 → 车款首付 ¥79,900
 * - Option 2 现价 ¥303,900 → 月供 ¥3,734（破约束）
 * - 方案 A：去 AP+漆+轮 → ¥259,900 → 月供 ¥3,000（满足）
 * - 方案 B：留 AP、砍漆+轮 → ¥287,900 → 月供 ¥3,467（满足）
 */

export const FINANCE_INPUT_B1 =
  "Option 2 这边帮我算一下：客户说月供最好别超过 3000，首付大概 10 万左右。";

export const FINANCE_INPUT_B2 =
  "刚问清楚了：月供硬上限可以到 3500（3000 是偏好）；提车现金一共就 10 万，税险牌也算在里面。辅助驾驶他还想留，但不是必须。";

export const FINANCE_INPUT_B3 =
  "那就按更宽裕的方案 A 改 Option 2 吧。";

const PLAN_A_PRICE = 259_900;
const PLAN_A_MONTHLY = 3_000;
const PLAN_B_PRICE = 287_900;
const PLAN_B_MONTHLY = 3_467;
const CURRENT_PRICE = 303_900;
const CURRENT_MONTHLY = 3_734;

export const CASE_B_PLAN_A: FinancePlanOption = {
  id: "A",
  title: "方案 A",
  cuts: ["特斯拉辅助驾驶套件", "纯白车漆", "20 英寸螺旋轮毂"],
  keep: [],
  priceYuan: PLAN_A_PRICE,
  monthlyYuan: PLAN_A_MONTHLY,
  downYuan: 79_900,
  cashYuan: 100_000,
  ok: true,
  summary: "去掉辅助驾驶、纯白车漆、20 英寸螺旋轮毂",
  pros: "月供更低（¥3,000），比偏好线更宽裕，后续加装空间更大",
  cons: "放弃辅助驾驶与当前外观加装，驾驶辅助能力回到基础版",
};

export const CASE_B_PLAN_B: FinancePlanOption = {
  id: "B",
  title: "方案 B",
  cuts: ["纯白车漆", "20 英寸螺旋轮毂"],
  keep: ["特斯拉辅助驾驶套件"],
  priceYuan: PLAN_B_PRICE,
  monthlyYuan: PLAN_B_MONTHLY,
  downYuan: 79_900,
  cashYuan: 100_000,
  ok: true,
  summary: "保留辅助驾驶，去掉白漆和 20 寸轮毂",
  pros: "保留辅助驾驶，更贴近客户「想留」的偏好",
  cons: "月供更高（¥3,467），外观更素，相对硬上限余量更薄",
};

function tool(
  partial: Omit<FinanceToolCall, "id"> & { id?: string },
): FinanceToolCall {
  return { id: partial.id || crypto.randomUUID(), ...partial };
}

export const CASE_B_SCRIPT = {
  round1: {
    sales: FINANCE_INPUT_B1,
    understand: [
      "对象：Option 2",
      "月供「最好别超过 3000」——尚未确认是否硬上限",
      "首付「大概 10 万」——未说明是否含税险牌",
    ],
    planSteps: [
      "先按 Option 2 现配置试算",
      "约束表述偏软，试算后先澄清再改配置",
    ],
    tools: (): FinanceToolCall[] => [
      tool({
        id: "b1-t1",
        title: "Finance Tool · 现配置",
        priceYuan: CURRENT_PRICE,
        downYuan: 79_900,
        monthlyYuan: CURRENT_MONTHLY,
        ok: false,
        note: "先按车款首付 ¥79,900 试算：月供 ¥3,734，高于客户说的 3000",
      }),
    ],
    reply: `Option 2 按现配置看：车价 ¥303,900。若车款首付先按 ¥79,900 估，月供大约 ¥3,734，已经高于客户说的 3000。

不过这两句还不够下刀——「最好」和「大概」我不敢当成硬约束。确认两件事就行：

1. 月供 3000 是不能超的上限，还是可以松到比如 3500？
2. 这 10 万是提车现金总预算（税、险、上牌都算进去），还是只指车款首付？`,
  },

  round2: {
    sales: FINANCE_INPUT_B2,
    understand: [
      "对象：仍为 Option 2",
      "月供 ≤ ¥3,500（硬）；¥3,000 为偏好",
      "提车现金 ≤ ¥100,000（含税险牌）→ 车款首付 ¥79,900",
      "偏好：尽量保留特斯拉辅助驾驶套件（非必须）",
    ],
    planSteps: [
      "按硬约束重算现配置",
      "生成两个都可满足硬约束的方案",
      "对照优劣并推荐，由销售/客户选择落地",
    ],
    tools: (): FinanceToolCall[] => [
      tool({
        id: "b2-t1",
        title: "Finance Tool · 现配置",
        priceYuan: CURRENT_PRICE,
        downYuan: 79_900,
        monthlyYuan: CURRENT_MONTHLY,
        ok: false,
        note: "硬约束下仍为月供 ¥3,734，不满足",
      }),
      tool({
        id: "b2-t2",
        title: "Finance Tool · 方案对照",
        priceYuan: PLAN_A_PRICE,
        downYuan: 79_900,
        monthlyYuan: PLAN_A_MONTHLY,
        ok: true,
        note: "A：去 AP+白漆+轮毂 → 月供 ¥3,000（满足）；B：留 AP、砍白漆+轮毂 → 月供 ¥3,467（满足）",
      }),
    ],
  },

  round3: {
    sales: FINANCE_INPUT_B3,
    versionTag: "V1",
    note: "已按方案 A 更新 Option 2 · V1。",
    plan: CASE_B_PLAN_A,
  },
} as const;

/** 与 Case A 同一套结论卡结构，保证界面样式一致 */
export function buildFinanceCaseBResult(
  capture?: Capture,
): FinanceCaseAResult {
  return {
    optionLabel: "Option 2",
    understand: [...CASE_B_SCRIPT.round2.understand],
    planSteps: [...CASE_B_SCRIPT.round2.planSteps],
    tools: CASE_B_SCRIPT.round2.tools(),
    currentPriceYuan: CURRENT_PRICE,
    currentMonthly: CURRENT_MONTHLY,
    downYuan: 79_900,
    taxInsPlateYuan: 20_100,
    optionA: CASE_B_PLAN_A,
    optionB: CASE_B_PLAN_B,
    recommend: "A",
    recommendReason:
      "两个方案都能同时满足提车现金与月供硬上限。更推荐方案 A：月供 ¥3,000，更贴近客户偏好线，也更宽裕；若客户更坚持留辅助驾驶，再选方案 B（月供 ¥3,467）即可。",
    actions: [
      { id: "apply_a", label: "按方案 A 更改 Option 2" },
      { id: "apply_b", label: "按方案 B 更改 Option 2" },
    ],
    sourceCapture: capture,
  };
}
