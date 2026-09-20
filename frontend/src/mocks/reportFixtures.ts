import type { Fact, Json, ReportModule } from "../types/api";
import { reportFacts } from "../utils/facts";
/** Illustrative contract data only. Visible Mock/Estimate markers are never removed. */
export function reportDemoModules(
  captureId: string,
  price: number,
  facts: Fact[],
): ReportModule[] {
  const budget = reportFacts(facts).find(
    (f) => f.key === "monthly_budget",
  )?.value;
  const down =
      typeof budget === "number"
        ? Math.max(8000000, price - budget * 60)
        : 8000000,
    principal = price - down,
    monthly = Math.ceil(principal / 60),
    last = principal - monthly * 59;
  const finance: ReportModule = {
    type: "finance",
    status: "mock",
    source_refs: [],
    data: {
      capture_id: captureId,
      product_id: "contract-zero-interest",
      state: "ready",
      solutions: [
        {
          term_months: 60,
          down_payment_fen: down,
          principal_fen: principal,
          monthly_payment_fen: monthly,
          last_payment_fen: last,
          total_installments_fen: principal,
          financing_cost_fen: 0,
          upfront_fees_fen: 0,
          financed_fees_fen: 0,
          method: "zero_interest",
          source_kind: "mock",
        },
      ],
      constraints:
        typeof budget === "number" ? { monthly_cap_fen: budget } : {},
      price_fen: price,
      unmet_constraints: [],
      note: "Mock：仅用于界面契约测试，不是当前官方金融产品。",
    },
  };
  const electric = 360000,
    fuel = 1280000;
  const energy: ReportModule = {
    type: "energy",
    status: "estimate",
    source_refs: [],
    data: {
      assumptions: {
        annual_km: 20000,
        years: 5,
        kwh_per_100km: 15,
        electricity_yuan_per_kwh: 1.2,
        liters_per_100km: 8,
        fuel_yuan_per_liter: 8,
        source: "Mock 演示假设，未经本次销售确认",
      },
      annual_electric_fen: electric,
      annual_fuel_fen: fuel,
      series: [1, 2, 3, 4, 5].map((year) => ({
        year,
        electric_fen: electric * year,
        fuel_fen: fuel * year,
        saving_fen: (fuel - electric) * year,
      })) as Json,
      scope: "energy_only",
      label: "Estimate",
    },
  };
  return [
    finance,
    energy,
    {
      type: "charging",
      status: "missing",
      source_refs: [],
      data: { reason: "Mock 契约模式未查询真实高德，不展示虚构站点或地图。" },
    },
    {
      type: "advisor",
      status: "mock",
      source_refs: [],
      data: {
        id: "demo-alex",
        name: "Alex",
        store_name: "Tesla ××体验中心",
        is_demo: true,
      },
    },
  ];
}
