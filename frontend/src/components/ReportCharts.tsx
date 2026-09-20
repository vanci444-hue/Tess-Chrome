import { money } from "../utils/display";
import type { EnergyView } from "../types/report";
import { chartSeries } from "../utils/reportData";
export function ComparisonBars({
  rows,
  unit,
  label,
}: {
  rows: { name: string; value: number | null }[];
  unit: string;
  label: string;
}) {
  const valid = rows.filter(
    (r): r is { name: string; value: number } =>
      r.value !== null && Number.isFinite(r.value),
  );
  if (valid.length < 2)
    return (
      <p className="report-missing">
        {label}：至少需要两组可核实参数才能比较。
      </p>
    );
  const max = Math.max(...valid.map((r) => r.value), 1);
  return (
    <div
      className="comparison-chart"
      role="img"
      aria-label={`${label}：${valid.map((r) => `${r.name} ${r.value}${unit}`).join("；")}`}
    >
      <h3>
        {label}
        <span>{unit}</span>
      </h3>
      {rows.map((row) => (
        <div className="metric-row" key={row.name}>
          <span>{row.name}</span>
          <div className="metric-track">
            {row.value !== null && (
              <div style={{ width: `${(row.value / max) * 100}%` }} />
            )}
          </div>
          <strong>{row.value ?? "Missing"}</strong>
        </div>
      ))}
    </div>
  );
}
export function BudgetBars({
  rows,
  budget,
}: {
  rows: { name: string; payment: number }[];
  budget: number | null;
}) {
  if (!rows.length)
    return <p className="report-missing">没有可展示的月供结果。</p>;
  const max = Math.max(...rows.map((r) => r.payment), budget || 0, 1) * 1.12;
  return (
    <div
      className="budget-chart"
      role="img"
      aria-label={`各方案月供${rows.map((r) => r.name + money(r.payment)).join("，")}；预算${budget === null ? "未知" : money(budget)}`}
    >
      <div className="budget-legend">
        {budget === null
          ? "预算未知，未绘制预算线"
          : `家庭月供预算 ${money(budget)}`}
      </div>
      {rows.map((row) => (
        <div className="budget-row" key={row.name}>
          <span>{row.name}</span>
          <div className="budget-track">
            <div
              className="budget-fill"
              style={{ width: `${(row.payment / max) * 100}%` }}
            />
            {budget !== null && (
              <div
                className="budget-line"
                style={{ left: `${(budget / max) * 100}%` }}
              />
            )}
          </div>
          <strong>{money(row.payment)}</strong>
        </div>
      ))}
    </div>
  );
}
export function EnergyChart({ data }: { data: EnergyView }) {
  const points = chartSeries(data);
  if (!points.length)
    return <p className="report-missing">能源成本数据缺失，未绘制曲线。</p>;
  const width = 760,
    height = 280,
    left = 74,
    right = 28,
    top = 24,
    bottom = 44,
    maxYear = Math.max(...points.map((p) => p.year), 1),
    max =
      Math.max(...points.flatMap((p) => [p.electric_fen, p.fuel_fen]), 1) *
      1.12;
  const x = (year: number) => left + (year / maxYear) * (width - left - right),
    y = (value: number) =>
      height - bottom - (value / max) * (height - top - bottom);
  const line = (key: "electric_fen" | "fuel_fen") =>
    `M ${x(0)} ${y(0)} ` +
    points.map((p) => `L ${x(p.year)} ${y(p[key])}`).join(" ");
  return (
    <div className="energy-chart">
      <div className="chart-key">
        <span className="electric-dot" /> 电车能源开支{" "}
        <span className="fuel-dot" /> 对标燃油车能源开支
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="累计能源成本曲线；详细数值见下方表格"
      >
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line
              x1={left}
              x2={width - right}
              y1={y(max * t)}
              y2={y(max * t)}
              stroke="#e4e6e8"
            />
            <text x={left - 10} y={y(max * t) + 4} textAnchor="end">
              ¥{Math.round((max * t) / 100).toLocaleString("zh-CN")}
            </text>
          </g>
        ))}
        <path d={line("fuel_fen")} stroke="#929ba7" />
        <path d={line("electric_fen")} stroke="#3e6ae1" />
        {points.map((p) => (
          <g key={p.year}>
            <circle
              cx={x(p.year)}
              cy={y(p.electric_fen)}
              r="4"
              fill="#3e6ae1"
            />
            <circle cx={x(p.year)} cy={y(p.fuel_fen)} r="4" fill="#929ba7" />
            <text x={x(p.year)} y={height - 14} textAnchor="middle">
              第 {p.year} 年
            </text>
          </g>
        ))}
      </svg>
      <details>
        <summary>查看逐年计算数值</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>年份</th>
                <th>电车能源开支</th>
                <th>燃油能源开支</th>
                <th>能源差额</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.year}>
                  <td>{p.year}</td>
                  <td>{money(p.electric_fen)}</td>
                  <td>{money(p.fuel_fen)}</td>
                  <td>{money(p.saving_fen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
