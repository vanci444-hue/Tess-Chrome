import type { CaptureInput, Health } from "../types/api";
export const mockHealth: Health = {
  demo_advisor: {
    id: "demo-alex",
    name: "Alex",
    store_name: "Tesla ××体验中心",
    is_demo: true,
  },
  status: "degraded",
  database: true,
  capabilities: { llm: "missing", asr: "missing", maps: "missing" },
};
export const followupFixtures = [
  { id: "family-charging-followup", label: "家人继续询问充电" },
  { id: "family-rear-seat-followup", label: "家人继续关注后排" },
];
export function mockCapture(): CaptureInput {
  const time = new Date().toISOString();
  return {
    source_url: "https://www.tesla.cn/modely/design#overview",
    captured_at: time,
    adapter_version: "contract-mock-only",
    page_fingerprint: crypto.randomUUID(),
    readiness: "ready",
    issues: [
      {
        code: "MOCK_DATA",
        field: null,
        blocking: false,
        message: "Mock：本条只用于前端契约验收，未读取当前官网。",
      },
      {
        code: "FINANCE_MISSING",
        field: "finance_product",
        blocking: false,
        message: "Missing：金融条件待获取。",
      },
    ],
    fields: Object.entries({
      model: "Model Y",
      variant: "后轮驱动版",
      paint: "星空灰车漆",
      wheels: "19 英寸交互风暴轮毂",
      interior: "深色高级内饰",
      seats: "五座",
      autopilot: "特斯拉辅助驾驶套件",
      accessories: ["娱乐服务年包 1年", "轮胎修理工具包"],
      extras: [
        "特斯拉辅助驾驶套件",
        "娱乐服务年包 1年",
        "轮胎修理工具包",
      ],
      option_surcharges: [
        {
          group: "paint",
          name: "星空灰车漆",
          amount: 0,
          included: true,
        },
        {
          group: "wheels",
          name: "19 英寸交互风暴轮毂",
          amount: 0,
          included: true,
        },
        {
          group: "interior",
          name: "深色高级内饰",
          amount: 0,
          included: true,
        },
        {
          group: "autopilot",
          name: "特斯拉辅助驾驶套件",
          amount: 3200000,
          included: false,
        },
        {
          group: "extras",
          name: "娱乐服务年包 1年",
          amount: 144000,
          included: false,
        },
        {
          group: "extras",
          name: "轮胎修理工具包",
          amount: 16500,
          included: false,
        },
      ],
      vehicle_price: 26350000,
      price_basis: "车辆价格",
      delivery: "3–5周",
      range_cltc: 593,
      top_speed: 201,
      zero_to_hundred: 5.9,
      monthly_payment: 306000,
      down_payment: 7990000,
      term_months: 60,
      rate_value: 0,
      rate_basis: "年化费率",
    }).map(([key, value]) => ({
      key,
      value,
      unit:
        /price|payment/.test(key)
          ? "CNY_fen"
          : key === "term_months"
            ? "months"
            : key === "rate_value"
              ? "percent"
              : null,
      raw_text: String(value),
      evidence: { kind: "dom_selected", selector_hint: null },
      observed_at: time,
    })),
  };
}
