import type { ReportModule, CapturedField } from "../types/api";
import type {
  EnergyView,
  FinanceView,
  OptionView,
  ChargingView,
  FamilyView,
} from "../types/report";
export function fieldValue(fields: CapturedField[], key: string) {
  return fields.find((f) => f.key === key)?.value;
}
export function numericField(
  fields: CapturedField[],
  key: string,
): number | null {
  const n = fieldValue(fields, key);
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}
export function moduleData<T>(module: ReportModule): T {
  return module.data as unknown as T;
}
export function optionsFrom(modules: ReportModule[]): OptionView[] {
  return modules
    .filter((m) => m.type === "options" && m.status !== "missing")
    .flatMap((m) => moduleData<{ options?: OptionView[] }>(m).options || []);
}
export function chartSeries(energy: EnergyView) {
  return energy.series.filter((p) =>
    [p.year, p.electric_fen, p.fuel_fen, p.saving_fen].every(
      (v) => typeof v === "number" && Number.isFinite(v),
    ),
  );
}
export function financeRows(finance: FinanceView) {
  return finance.solutions.filter((p) =>
    [p.monthly_payment_fen, p.down_payment_fen, p.term_months].every(
      (v) => typeof v === "number" && Number.isFinite(v),
    ),
  );
}
/** External navigation only accepts the approved Amap search URL with safe query keys. */
export function safeMapUrl(charging: ChargingView): string | null {
  if (!charging.region?.trim() || !charging.external_search?.url) return null;
  try {
    const u = new URL(charging.external_search.url);
    if (
      u.protocol !== "https:" ||
      u.hostname !== "uri.amap.com" ||
      u.pathname !== "/search" ||
      u.username ||
      u.password
    )
      return null;
    const allowed = new Set(["keyword", "city", "view", "src", "callnative"]);
    for (const key of u.searchParams.keys()) if (!allowed.has(key)) return null;
    if (!u.searchParams.get("keyword")) return null;
    return u.toString();
  } catch {
    return null;
  }
}
export function safeOfficialUrl(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === "https:" &&
      (u.hostname === "tesla.cn" ||
        u.hostname.endsWith(".tesla.cn") ||
        u.hostname === "tesla.com" ||
        u.hostname.endsWith(".tesla.com"))
      ? u.toString()
      : null;
  } catch {
    return null;
  }
}
export function validFamilyEntries(family: FamilyView) {
  return (family.entries || []).filter((e) => e.text && safeOfficialUrl(e.url));
}
