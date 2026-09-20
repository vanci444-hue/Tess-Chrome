import type { Json } from "../types/api";
export const money = (fen: unknown) =>
  typeof fen === "number"
    ? new Intl.NumberFormat("zh-CN", {
        style: "currency",
        currency: "CNY",
        maximumFractionDigits: 2,
      }).format(fen / 100)
    : "待获取";
export const date = (iso: string) =>
  new Date(iso).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const display = (value: Json | undefined) =>
  value == null
    ? "未知"
    : Array.isArray(value)
      ? value.map(String).join("、") || "无额外选配"
      : typeof value === "object"
        ? JSON.stringify(value)
        : String(value);
export const factLabels: Record<string, string> = {
  monthly_budget: "月供预算",
  down_payment_max: "首付上限",
  annual_km: "年行驶里程",
  region: "常用区域",
  city: "城市",
  trial_variant: "实际试驾版本",
  trial_vehicle: "实际试驾车型",
  home_charging: "家充条件",
  commute_km: "每日通勤",
  household: "家庭情况",
  feedback: "试驾反馈",
  concerns: "仍有顾虑",
};
export const sourceLabels: Record<string, string> = {
  official_capture: "官网采集",
  sales_input: "销售输入",
  sales_relay: "销售转述",
  crm_paste: "CRM 粘贴",
  historical: "历史参考",
  amap: "高德",
  deterministic: "确定性计算",
  mock: "Mock",
  missing: "Missing",
};
export function isMoneyFact(key: string) {
  return /budget|payment|price|cost|_fen$/.test(key);
}
