import type { Json } from "../types/api";
export const money = (fen: unknown, digits = 2) =>
  typeof fen === "number"
    ? new Intl.NumberFormat("zh-CN", {
        style: "currency",
        currency: "CNY",
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
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

/** Tesla 选项文案常带「- 包括」，卡片上只保留选项名。 */
export function optionLabel(value: Json | undefined) {
  const raw = display(value);
  if (raw === "未知") return raw;
  return raw
    .replace(/\s*[-–—]?\s*[¥￥].*$/g, "")
    .replace(/\s*[-–—]\s*包括\b.*$/g, "")
    .replace(/\s*包括\s*$/g, "")
    .replace(/\s*[-–—]+\s*$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function deliveryLabel(value: Json | undefined) {
  if (value == null) return "";
  const raw = String(value);
  const match = raw.match(/(\d+\s*[~\-–—至到]\s*\d+\s*周|\d+\s*周)/);
  if (!match) return "";
  return match[1]
    .replace(/\s+/g, "")
    .replace(/[至到~]/g, "–");
}

export function extraLabels(
  extras: Json | undefined,
  autopilot: Json | undefined,
  accessories: Json | undefined,
) {
  const from = (value: Json | undefined) =>
    value == null
      ? []
      : Array.isArray(value)
        ? value.map((item) => optionLabel(item)).filter(Boolean)
        : [optionLabel(value)].filter((item) => item && item !== "未知");
  const listed = from(extras);
  if (listed.length) return listed;
  const ap = optionLabel(autopilot);
  const paid =
    ap && ap !== "未知" && !/基础辅助|标配/.test(ap) ? [ap] : [];
  return [...paid, ...from(accessories)];
}

export function surchargeLines(value: Json | undefined) {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const name = optionLabel(item.name);
    if (!name || name === "未知") return [];
    const amount = typeof item.amount === "number" ? item.amount : 0;
    return [
      {
        group: String(item.group || ""),
        name,
        amount,
        included: item.included === true || amount === 0,
      },
    ];
  });
}

export function chargeText(amount: number, included: boolean) {
  return included || amount === 0 ? "包括" : money(amount, 0);
}
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
export function unknownSupport(key: string) {
  const messages: Record<string, string> = {
    home_charging:
      "补充家充条件后，可以判断是否需要查询周边超充，以及能否做家庭充电成本对照。",
    has_fixed_parking:
      "补充固定车位情况后，可以判断是否需要查询公共超充与驾车距离。",
    region:
      "补充常用区域后，可以通过高德查询真实充电站、驾车距离和带编号地图。",
    city: "补充城市后，可以缩小同名地点并查询该区域充电站。",
    trial_variant:
      "补充实际试驾版本后，体验反馈会正确归属，不会沿用候选配置。",
    monthly_budget: "补充月供预算后，可以用已确认规则试算可行首付与期限。",
    desired_monthly_payment:
      "补充期望月供后，可以用已确认规则试算可行方案。",
  };
  return messages[key] || "补充该信息后可以继续对应分析，Unknown 会如实保留。";
}
export function isMoneyFact(key: string) {
  return /budget|payment|price|cost|_fen$/.test(key);
}
