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
      variant: "长续航全轮驱动版",
      paint: "珍珠白",
      wheels: "20 英寸轮毂",
      interior: "深色内饰",
      seats: "五座",
      autopilot: "基础辅助驾驶",
      accessories: [],
      vehicle_price: 32150000,
      price_basis: "车辆价格",
    }).map(([key, value]) => ({
      key,
      value,
      unit: key === "vehicle_price" ? "CNY_fen" : null,
      raw_text: String(value),
      evidence: { kind: "dom_selected", selector_hint: null },
      observed_at: time,
    })),
  };
}
