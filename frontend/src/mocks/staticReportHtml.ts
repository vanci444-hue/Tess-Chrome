/**
 * 场景 6 · 客户向静态试驾报告（移动端自包含 HTML）
 * 沿用旧版报告的对比条 / 月供条 / 油电累计曲线，生成后写入 localStorage。
 */

import type { Capture, Draft, ReportModule, SessionDetail, Summary } from "../types/api";

export const STATIC_REPORT_HTML_KEY = (sessionId: string) =>
  `tess.demo.report.html.v1.${sessionId}`;

const ADVISOR = {
  name: "Alex",
  store: "Tesla 上海 · 演示门店",
  phone: "1886889092",
  wechat: "Alex_Tesla_Demo",
} as const;

type EnergyPoint = {
  year: number;
  electric_fen: number;
  fuel_fen: number;
  saving_fen: number;
};

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function field(capture: Capture, key: string) {
  return capture.immutable_payload.fields.find((f) => f.key === key)?.value;
}

function numField(capture: Capture, key: string): number | null {
  const value = field(capture, key);
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function yuanFromFen(value: unknown) {
  if (typeof value !== "number") return "—";
  return `¥${Math.round(value / 100).toLocaleString("zh-CN")}`;
}

function textField(capture: Capture, key: string) {
  const value = field(capture, key);
  if (value == null) return "—";
  if (Array.isArray(value)) return value.map(String).join(" · ") || "—";
  return String(value);
}

function listHtml(items: string[]) {
  if (!items.length) return `<p class="muted">暂无</p>`;
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function optionCard(capture: Capture, index: number) {
  const label = `Option ${String.fromCharCode(65 + index)}`;
  const title = [textField(capture, "paint"), textField(capture, "variant")]
    .filter((x) => x !== "—")
    .join(" · ");
  const price = yuanFromFen(field(capture, "vehicle_price"));
  const range = numField(capture, "range_cltc");
  const accel = numField(capture, "zero_to_hundred");
  return `<article class="option">
    <span class="kicker">${escapeHtml(label)}</span>
    <h3>${escapeHtml(title || "Model Y")}</h3>
    <p class="price">${escapeHtml(price)}</p>
    <p class="meta">${escapeHtml(textField(capture, "wheels"))} · ${escapeHtml(textField(capture, "autopilot"))}</p>
    <div class="metrics">
      <div><strong>${range ?? "—"}</strong><span>CLTC km</span></div>
      <div><strong>${accel ?? "—"}</strong><span>0–100 s</span></div>
      <div><strong>${numField(capture, "top_speed") ?? "—"}</strong><span>最高 km/h</span></div>
    </div>
  </article>`;
}

function comparisonChart(
  label: string,
  unit: string,
  rows: { name: string; value: number | null }[],
) {
  const valid = rows.filter(
    (r): r is { name: string; value: number } =>
      r.value !== null && Number.isFinite(r.value),
  );
  if (valid.length < 2) return "";
  const max = Math.max(...valid.map((r) => r.value), 1);
  return `<div class="comparison-chart">
    <h3>${escapeHtml(label)}<span>${escapeHtml(unit)}</span></h3>
    ${rows
      .map(
        (row, i) => `<div class="metric-row">
      <span>${escapeHtml(row.name)}</span>
      <div class="metric-track">${
        row.value !== null
          ? `<div class="fill ${i === 0 ? "a" : "b"}" style="width:${(row.value / max) * 100}%"></div>`
          : ""
      }</div>
      <strong>${row.value ?? "—"}</strong>
    </div>`,
      )
      .join("")}
  </div>`;
}

function budgetChart(
  paymentFen: number,
  budgetFen: number | null,
  label: string,
) {
  const max = Math.max(paymentFen, budgetFen || 0, 1) * 1.12;
  return `<div class="budget-chart">
    <div class="budget-legend">${
      budgetFen == null
        ? "预算未知"
        : `家庭月供预算 ${escapeHtml(yuanFromFen(budgetFen))}`
    }</div>
    <div class="budget-row">
      <span>${escapeHtml(label)}</span>
      <div class="budget-track">
        <div class="budget-fill" style="width:${(paymentFen / max) * 100}%"></div>
        ${
          budgetFen != null
            ? `<div class="budget-line" style="left:${(budgetFen / max) * 100}%"></div>`
            : ""
        }
      </div>
      <strong>${escapeHtml(yuanFromFen(paymentFen))}</strong>
    </div>
  </div>`;
}

function energySection(module: ReportModule | undefined) {
  const data = module?.data as
    | {
        annual_electric_fen?: number;
        annual_fuel_fen?: number;
        series?: EnergyPoint[];
        assumptions?: {
          annual_km: number;
          years: number;
          kwh_per_100km: number;
          electricity_yuan_per_kwh: number;
          liters_per_100km: number;
          fuel_yuan_per_liter: number;
          source: string;
        };
      }
    | undefined;

  const annualElectric = data?.annual_electric_fen ?? 360_000;
  const annualFuel = data?.annual_fuel_fen ?? 1_280_000;
  const points: EnergyPoint[] =
    data?.series?.length &&
    data.series.every((p) =>
      [p.year, p.electric_fen, p.fuel_fen, p.saving_fen].every(
        (v) => typeof v === "number",
      ),
    )
      ? data.series
      : [1, 2, 3, 4, 5].map((year) => ({
          year,
          electric_fen: annualElectric * year,
          fuel_fen: annualFuel * year,
          saving_fen: (annualFuel - annualElectric) * year,
        }));

  const assumptions = data?.assumptions ?? {
    annual_km: 20000,
    years: 5,
    kwh_per_100km: 15,
    electricity_yuan_per_kwh: 1.2,
    liters_per_100km: 8,
    fuel_yuan_per_liter: 8,
    source: "Mock 演示假设，未经本次销售确认",
  };

  const last = points.at(-1)!;
  const width = 360;
  const height = 220;
  const left = 48;
  const right = 12;
  const top = 16;
  const bottom = 36;
  const maxYear = Math.max(...points.map((p) => p.year), 1);
  const max =
    Math.max(...points.flatMap((p) => [p.electric_fen, p.fuel_fen]), 1) * 1.12;
  const x = (year: number) => left + (year / maxYear) * (width - left - right);
  const y = (value: number) =>
    height - bottom - (value / max) * (height - top - bottom);
  const line = (key: "electric_fen" | "fuel_fen") =>
    `M ${x(0)} ${y(0)} ` +
    points.map((p) => `L ${x(p.year)} ${y(p[key])}`).join(" ");

  return `<section class="block">
    <p class="eyebrow">Energy Cost Estimate</p>
    <h2>长期使用，能源开支有多少差别？</h2>
    <p class="lead">Estimate · 仅能源成本，不含购车、保险、保养与折旧</p>
    <div class="energy-result">
      <p>${last.year} 年累计能源成本预计节省</p>
      <strong>${escapeHtml(yuanFromFen(Math.abs(last.saving_fen)))}</strong>
    </div>
    <div class="chart-key">
      <span><i class="electric"></i> 电车能源开支</span>
      <span><i class="fuel"></i> 对标燃油车</span>
    </div>
    <svg class="energy-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="累计能源成本曲线">
      ${[0, 0.5, 1]
        .map(
          (t) => `<g>
        <line x1="${left}" x2="${width - right}" y1="${y(max * t)}" y2="${y(max * t)}" stroke="#e4e6e8"/>
        <text x="${left - 6}" y="${y(max * t) + 4}" text-anchor="end" fill="#8c949f" font-size="9">¥${Math.round((max * t) / 100).toLocaleString("zh-CN")}</text>
      </g>`,
        )
        .join("")}
      <path d="${line("fuel_fen")}" fill="none" stroke="#929ba7" stroke-width="2"/>
      <path d="${line("electric_fen")}" fill="none" stroke="#3e6ae1" stroke-width="2.5"/>
      ${points
        .map(
          (p) => `<g>
        <circle cx="${x(p.year)}" cy="${y(p.electric_fen)}" r="3.5" fill="#3e6ae1"/>
        <circle cx="${x(p.year)}" cy="${y(p.fuel_fen)}" r="3.5" fill="#929ba7"/>
        <text x="${x(p.year)}" y="${height - 12}" text-anchor="middle" fill="#8c949f" font-size="9">第 ${p.year} 年</text>
      </g>`,
        )
        .join("")}
    </svg>
    <div class="assumption-grid">
      <div><span>年行驶里程</span><strong>${assumptions.annual_km.toLocaleString("zh-CN")} km</strong></div>
      <div><span>持有周期</span><strong>${assumptions.years} 年</strong></div>
      <div><span>电耗</span><strong>${assumptions.kwh_per_100km} kWh/100km</strong></div>
      <div><span>电价</span><strong>¥${assumptions.electricity_yuan_per_kwh}/kWh</strong></div>
      <div><span>对标油耗</span><strong>${assumptions.liters_per_100km} L/100km</strong></div>
      <div><span>油价</span><strong>¥${assumptions.fuel_yuan_per_liter}/L</strong></div>
    </div>
    <p class="micro muted">假设来源：${escapeHtml(assumptions.source)}。家充比例、实际能耗与能源价格都会影响结果。</p>
  </section>`;
}

function qrPlaceholder() {
  return `<div class="qr" aria-hidden="true">
    <svg viewBox="0 0 120 120" width="120" height="120" role="img">
      <rect width="120" height="120" fill="#fff"/>
      <g fill="#171a20">
        <rect x="8" y="8" width="36" height="36"/>
        <rect x="14" y="14" width="24" height="24" fill="#fff"/>
        <rect x="20" y="20" width="12" height="12"/>
        <rect x="76" y="8" width="36" height="36"/>
        <rect x="82" y="14" width="24" height="24" fill="#fff"/>
        <rect x="88" y="20" width="12" height="12"/>
        <rect x="8" y="76" width="36" height="36"/>
        <rect x="14" y="82" width="24" height="24" fill="#fff"/>
        <rect x="20" y="88" width="12" height="12"/>
        <rect x="52" y="52" width="10" height="10"/>
        <rect x="68" y="52" width="10" height="10"/>
        <rect x="52" y="68" width="10" height="10"/>
        <rect x="84" y="68" width="10" height="10"/>
        <rect x="68" y="84" width="10" height="10"/>
        <rect x="100" y="100" width="10" height="10"/>
        <rect x="52" y="100" width="10" height="10"/>
        <rect x="100" y="52" width="10" height="10"/>
      </g>
    </svg>
    <span>扫码添加顾问</span>
  </div>`;
}

function reportStyles() {
  return `<style>
  :root {
    color-scheme: light;
    --ink: #171a20;
    --muted: #5c6169;
    --line: #e5e7ea;
    --bg: #f3f4f6;
    --card: #ffffff;
    --accent: #3e6ae1;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC",
      "Helvetica Neue", sans-serif;
    font-size: 15px;
    line-height: 1.65;
  }
  .phone, .report-sheet {
    width: min(430px, 100%);
    min-height: 100vh;
    margin: 0 auto;
    background: var(--card);
    padding: 20px 20px 48px;
    padding-bottom: calc(48px + env(safe-area-inset-bottom, 0px));
  }
  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--muted);
    text-transform: uppercase;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--line);
  }
  .wordmark {
    color: var(--ink);
    letter-spacing: -0.06em;
    font-size: 18px;
    font-weight: 600;
    text-transform: none;
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .wordmark-mark {
    width: 22px;
    height: 22px;
    border-radius: 5px;
    overflow: hidden;
    display: grid;
    place-items: center;
    flex: none;
  }
  .wordmark-mark svg {
    width: 22px;
    height: 22px;
    display: block;
  }
  .hero { padding: 28px 0 8px; }
  .greeting { margin: 0 0 10px; font-size: 16px; font-weight: 500; }
  .hero h1 {
    margin: 0;
    font-size: clamp(28px, 7vw, 34px);
    font-weight: 560;
    letter-spacing: -0.03em;
    line-height: 1.2;
  }
  .subtitle {
    margin: 14px 0 0;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.55;
  }
  .questions { margin-top: 28px; border-top: 1px solid var(--line); }
  .questions section {
    padding: 18px 0;
    border-bottom: 1px solid var(--line);
  }
  .questions .idx {
    display: block;
    font-size: 10px;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin-bottom: 8px;
  }
  .questions h2 { margin: 0 0 8px; font-size: 17px; font-weight: 600; }
  .questions p, .questions li, .block li { margin: 0; }
  .questions ul, .block ul { margin: 0; padding-left: 1.1em; }
  .questions li + li, .block li + li { margin-top: 6px; }
  .block { margin-top: 28px; }
  .block .eyebrow {
    margin: 0 0 6px;
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .block h2 {
    margin: 0 0 6px;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .block > .lead { margin: 0 0 14px; color: var(--muted); font-size: 13px; }
  .muted, .micro.muted { color: var(--muted); }
  .micro { font-size: 12px; margin-top: 10px; }
  .option-list { display: grid; gap: 12px; }
  .option {
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 14px;
    background: #fafbfc;
  }
  .option .kicker {
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--muted);
  }
  .option h3 { margin: 6px 0; font-size: 16px; font-weight: 600; }
  .option .price { margin: 0; font-size: 18px; font-weight: 600; }
  .option .meta { margin: 6px 0 0; font-size: 12px; color: var(--muted); }
  .metrics {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--line);
  }
  .metrics strong { display: block; font-size: 15px; }
  .metrics span { font-size: 10px; color: var(--muted); }
  .parameter-charts { display: grid; gap: 18px; margin-top: 16px; }
  .comparison-chart h3 {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    margin: 0 0 8px;
  }
  .comparison-chart h3 span { font-weight: 400; color: var(--muted); }
  .metric-row {
    display: grid;
    grid-template-columns: 64px 1fr 36px;
    gap: 8px;
    align-items: center;
    margin: 10px 0;
    font-size: 11px;
  }
  .metric-row > span { color: var(--muted); }
  .metric-track { height: 7px; background: #eef0f2; border-radius: 99px; overflow: hidden; }
  .metric-track .fill { height: 100%; border-radius: 99px; }
  .metric-track .fill.a { background: #858e9b; }
  .metric-track .fill.b { background: var(--accent); }
  .metric-row > strong { text-align: right; font-size: 12px; font-weight: 500; }
  .budget-chart { padding: 8px 0 4px; }
  .budget-legend {
    font-size: 12px;
    color: var(--muted);
    text-align: right;
    margin-bottom: 12px;
  }
  .budget-row {
    display: grid;
    grid-template-columns: 72px 1fr 72px;
    align-items: center;
    gap: 10px;
    font-size: 12px;
  }
  .budget-track {
    height: 16px;
    position: relative;
    background: #eef0f2;
    border-radius: 4px;
    overflow: hidden;
  }
  .budget-fill { height: 100%; background: var(--accent); }
  .budget-line {
    position: absolute;
    top: -3px;
    bottom: -3px;
    width: 2px;
    background: var(--ink);
  }
  .energy-result {
    margin: 8px 0 16px;
    padding: 16px;
    border-radius: 14px;
    background: #f4f7ff;
  }
  .energy-result p { margin: 0; font-size: 13px; color: var(--muted); }
  .energy-result strong {
    display: block;
    margin-top: 4px;
    font-size: 28px;
    letter-spacing: -0.03em;
  }
  .chart-key {
    display: flex;
    gap: 16px;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 8px;
  }
  .chart-key i {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
  }
  .chart-key i.electric { background: #3e6ae1; }
  .chart-key i.fuel { background: #929ba7; }
  .energy-svg { width: 100%; height: auto; display: block; }
  .assumption-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 14px;
  }
  .assumption-grid div {
    padding: 10px 12px;
    border-radius: 10px;
    background: #fafbfc;
    border: 1px solid var(--line);
  }
  .assumption-grid span {
    display: block;
    font-size: 11px;
    color: var(--muted);
  }
  .assumption-grid strong { font-size: 13px; }
  .finance-note {
    border-left: 3px solid var(--ink);
    padding: 10px 0 10px 12px;
    font-size: 14px;
    margin-bottom: 12px;
  }
  .actions { display: grid; gap: 10px; margin-top: 14px; }
  .actions a {
    display: block;
    text-align: center;
    text-decoration: none;
    border-radius: 999px;
    padding: 14px 16px;
    font-size: 15px;
    font-weight: 600;
  }
  .actions a.primary { background: var(--ink); color: #fff; }
  .actions a.secondary {
    background: #fff;
    color: var(--ink);
    border: 1px solid var(--line);
  }
  .advisor {
    margin-top: 28px;
    padding: 18px;
    border-radius: 16px;
    border: 1px solid var(--line);
    background: #fafbfc;
    display: grid;
    gap: 16px;
    justify-items: center;
    text-align: center;
  }
  .advisor h2 { margin: 0; font-size: 18px; }
  .advisor p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
  .advisor .contact { font-size: 14px; color: var(--ink); line-height: 1.7; }
  .qr { display: grid; gap: 8px; justify-items: center; }
  .qr span { font-size: 12px; color: var(--muted); }
  .ask {
    margin-top: 20px;
    padding: 14px;
    border-radius: 14px;
    background: #f5f6f8;
    font-size: 13px;
  }
  .ask strong { display: block; margin-bottom: 6px; }
  .footer {
    margin-top: 36px;
    padding-top: 16px;
    border-top: 1px solid var(--line);
    font-size: 11px;
    color: var(--muted);
  }
  .signoff {
    display: block;
    margin-top: 20px;
    letter-spacing: 0.08em;
    font-size: 10px;
    color: #9aa0a6;
  }
</style>`;
}

export function buildStaticReportHtml(
  session: SessionDetail,
  draft: Draft,
): string {
  const summary: Summary = draft.report_data.summary;
  const active = session.captures.filter((c) => c.active);
  const matters = summary.confirmed
    .filter(
      (line) =>
        line.startsWith("关注：") ||
        line.startsWith("关注:") ||
        line.startsWith("Must-have"),
    )
    .map((line) => line.replace(/^(关注|Must-have)[:：]\s*/, ""));
  const resolved = summary.confirmed
    .filter((line) => line.startsWith("已解决：") || line.startsWith("已解决:"))
    .map((line) => line.replace(/^已解决[:：]\s*/, ""));
  const tradeoffs = summary.confirmed
    .filter((line) => line.startsWith("权衡：") || line.startsWith("权衡:"))
    .map((line) => line.replace(/^权衡[:：]\s*/, ""));
  const pending = summary.pending;
  const generated = new Date(draft.report_data.generated_at).toLocaleString(
    "zh-CN",
    { hour12: false },
  );

  const energyModule = draft.report_data.modules.find((m) => m.type === "energy");
  const financeModule = draft.report_data.modules.find((m) => m.type === "finance");
  const financeData = financeModule?.data as
    | {
        solutions?: { monthly_payment_fen: number; term_months: number; down_payment_fen: number }[];
        constraints?: { monthly_cap_fen?: number };
        note?: string;
      }
    | undefined;
  const solution = financeData?.solutions?.[0];
  const budgetFen =
    typeof financeData?.constraints?.monthly_cap_fen === "number"
      ? financeData.constraints.monthly_cap_fen
      : 3500 * 100;

  const paramCharts =
    active.length > 1
      ? `<div class="parameter-charts">
      ${comparisonChart(
        "CLTC 续航",
        "km",
        active.map((c, i) => ({
          name: `Option ${String.fromCharCode(65 + i)}`,
          value: numField(c, "range_cltc"),
        })),
      )}
      ${comparisonChart(
        "0—100 km/h",
        "s",
        active.map((c, i) => ({
          name: `Option ${String.fromCharCode(65 + i)}`,
          value: numField(c, "zero_to_hundred"),
        })),
      )}
      ${comparisonChart(
        "最高车速",
        "km/h",
        active.map((c, i) => ({
          name: `Option ${String.fromCharCode(65 + i)}`,
          value: numField(c, "top_speed"),
        })),
      )}
    </div>`
      : "";

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>张先生 · 试驾报告</title>
${reportStyles()}
</head>
<body>
  <main class="report-sheet">
    <header class="topbar">
      <span class="wordmark"><span class="wordmark-mark"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="22" height="22" aria-hidden="true"><defs><filter id="tess-mark-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><rect width="512" height="512" rx="102" fill="#000"/><g transform="translate(85.33 85.33) scale(14.22)" filter="url(#tess-mark-glow)"><path fill="#fff" d="M12 0.5C12.08 0.5 12.15 0.6 12.3 1.2 12.5 3 12.8 5.5 13.6 8.8 13.9 9.8 14.8 10.5 16 10.8 18.5 11.2 21 11.5 22.8 11.7 23.4 11.85 23.5 11.92 23.5 12 23.5 12.08 23.4 12.15 22.8 12.3 21 12.5 18.5 12.8 16 13.2 14.8 13.5 13.9 14.2 13.6 15.2 12.8 18.5 12.5 21 12.3 22.8 12.15 23.4 12.08 23.5 12 23.5 11.92 23.5 11.85 23.4 11.7 22.8 11.5 21 11.2 18.5 10.4 15.2 10.1 14.2 9.2 13.5 8 13.2 5.5 12.8 3 12.5 1.2 12.3 0.6 12.15 0.5 12.08 0.5 12 0.5 11.92 0.6 11.85 1.2 11.7 3 11.5 5.5 11.2 8 10.8 9.2 10.5 10.1 9.8 10.4 8.8 11.2 5.5 11.5 3 11.7 1.2 11.85 0.6 11.92 0.5 12 0.5z"/></g></svg></span><span>Tess</span></span>
      <span>Test Drive Report</span>
    </header>

    <header class="hero">
      <p class="greeting">张先生，您好</p>
      <h1>这一程，值得被记住。</h1>
      <p class="subtitle">今天开过的记忆都还在；方向盘上的念头，已帮您整理好。</p>
    </header>

    <div class="questions">
      <section>
        <span class="idx">01 / 现在比较什么</span>
        <h2>短名单</h2>
        <p>${escapeHtml(summary.comparing || "候选方案仍待确认")}</p>
      </section>
      <section>
        <span class="idx">02 / 已经明确什么</span>
        <h2>今天谈清的</h2>
        ${listHtml([
          ...matters.map((x) => `关注：${x}`),
          ...resolved.map((x) => `已解决：${x}`),
        ])}
      </section>
      <section>
        <span class="idx">03 / 还需确认什么</span>
        <h2>带回去对齐的</h2>
        ${listHtml(pending)}
      </section>
    </div>

    ${
      tradeoffs.length
        ? `<section class="block">
      <p class="eyebrow">Key Trade-offs</p>
      <h2>真正影响决策的取舍</h2>
      <p class="lead">在支付能力与偏好之间，今天需要看清的差别。</p>
      ${listHtml(tradeoffs)}
    </section>`
        : ""
    }

    <section class="block">
      <p class="eyebrow">Your Shortlist</p>
      <h2>当前考虑的方案</h2>
      <p class="lead">来自本次实际查看与讨论过的候选；动态信息保留采集时间。</p>
      <div class="option-list">
        ${active.map((c, i) => optionCard(c, i)).join("") || "<p class='muted'>暂无候选</p>"}
      </div>
      ${paramCharts}
    </section>

    <section class="block">
      <p class="eyebrow">Financing</p>
      <h2>月供，放回家庭预算里看。</h2>
      <p class="lead">${escapeHtml(financeData?.note || "Mock：演示金融对照，非当前官方产品。")}</p>
      <div class="finance-note">
        硬约束下已给出可落地的对照方案；差别主要在「是否保留辅助驾驶」与月供余量。
      </div>
      ${
        solution
          ? budgetChart(
              solution.monthly_payment_fen,
              budgetFen,
              `${solution.term_months} 期`,
            )
          : ""
      }
    </section>

    ${energySection(energyModule)}

    <section class="block">
      <p class="eyebrow">Next</p>
      <h2>下一步</h2>
      <p class="lead">需要时再联系；也可以先和家人一起看完这份报告。</p>
      <div class="actions">
        <a class="primary" href="tel:${ADVISOR.phone}">联系销售 · ${ADVISOR.phone}</a>
        <a class="secondary" href="#advisor">再约试驾 / 添加顾问</a>
      </div>
      <div class="ask">
        <strong>Ask Tess about this</strong>
        例如：如果我家不能安装私人充电桩，会不会影响我选择这个方案？<br/>
        <span class="muted">回答会继承今天的候选、偏好与待确认事项；无法可靠确认时，会建议联系顾问。</span>
      </div>
    </section>

    <section class="advisor" id="advisor">
      <div>
        <p class="eyebrow">Your Advisor</p>
        <h2>${escapeHtml(ADVISOR.name)}</h2>
        <p>${escapeHtml(ADVISOR.store)}</p>
      </div>
      ${qrPlaceholder()}
      <div class="contact">
        电话 ${escapeHtml(ADVISOR.phone)}<br/>
        微信 ${escapeHtml(ADVISOR.wechat)}
      </div>
    </section>

    <footer class="footer">
      <p>报告生成：${escapeHtml(generated)} · Demo 静态页</p>
      <p>价格、金融、权益、交付状态可能变化。本页保留采集时信息，不自动刷新为当前官方有效信息。</p>
      <p>${escapeHtml(draft.report_data.disclaimer)}</p>
      <span class="signoff">tess · a clearer next step.</span>
    </footer>
  </main>
</body>
</html>`;
}

export function writeStaticReportHtml(sessionId: string, html: string) {
  localStorage.setItem(STATIC_REPORT_HTML_KEY(sessionId), html);
  localStorage.setItem("tess.demo.report.html.latest", sessionId);
}

export function readStaticReportHtml(sessionId: string): string | null {
  try {
    return localStorage.getItem(STATIC_REPORT_HTML_KEY(sessionId));
  } catch {
    return null;
  }
}

export function seedStaticReport(session: SessionDetail, draft: Draft) {
  const html = buildStaticReportHtml(session, draft);
  writeStaticReportHtml(session.id, html);
  return html;
}
