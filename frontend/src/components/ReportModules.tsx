import { useState } from "react";
import type { Json, ReportModule, SourceRef } from "../types/api";
import type {
  OptionView,
  FinanceView,
  EnergyView,
  ChargingView,
  FamilyView,
} from "../types/report";
import { date, display, money } from "../utils/display";
import { apiBase } from "../services/api";
import {
  moduleData,
  fieldValue,
  numericField,
  financeRows,
  chartSeries,
  safeMapUrl,
  validFamilyEntries,
  safeOfficialUrl,
} from "../utils/reportData";
import { ComparisonBars, BudgetBars, EnergyChart } from "./ReportCharts";
export function Provenance({
  sources,
  status,
}: {
  sources: SourceRef[];
  status: string;
}) {
  return (
    <div className="module-provenance">
      <span className={`tag ${status === "missing" ? "warning" : ""}`}>
        {(
          {
            ready: "已获得数据",
            estimate: "Estimate · 估算",
            mock: "Mock · 模拟数据",
            missing: "Missing · 暂缺",
          } as Record<string, string>
        )[status] || status}
      </span>
      {sources.map((s) => (
        <span key={s.id}>
          {s.label} · {date(s.observed_at)}
        </span>
      ))}
    </div>
  );
}
export function StaticAsk({ children }: { children: string }) {
  return (
    <button
      className="static-ask"
      disabled
      title="Prototype 展示，暂不提供实际问答"
    >
      {children}
      <span>↗ 演示</span>
    </button>
  );
}
export function OptionsModule({
  options,
  modules,
}: {
  options: OptionView[];
  modules: ReportModule[];
}) {
  const activeModules = modules.filter((m) => m.type === "options");
  return (
    <section className="report-section" id="options">
      <div className="section-heading">
        <p className="eyebrow">YOUR OPTIONS</p>
        <h2>当前考虑的方案</h2>
        <p>来自本次实际查看、配置和讨论过的候选。动态信息保留原始采集时间。</p>
      </div>
      <div className="option-grid">
        {options.map((option, index) => {
          const value = (key: string) => fieldValue(option.fields, key);
          return (
            <article className="report-option" key={option.capture_id}>
              <div className="option-visual">
                <span>MODEL Y</span>
                <small>当前配置未提供可核实车辆图片</small>
              </div>
              <p className="eyebrow">
                OPTION {String.fromCharCode(65 + index)}
                {option.preference ? ` · ${option.preference}` : ""}
              </p>
              <h3>
                {display(value("model"))} {display(value("variant"))}
              </h3>
              <p className="option-price">{money(value("vehicle_price"))}</p>
              <p className="micro muted">
                {display(value("price_basis"))} · {date(option.captured_at)}
              </p>
              <dl className="report-specs">
                {[
                  ["paint", "外观"],
                  ["wheels", "轮毂"],
                  ["interior", "内饰"],
                  ["seats", "座位"],
                  ["autopilot", "辅助驾驶"],
                  ["accessories", "配件"],
                  ["delivery", "交付参考"],
                ].map(([key, label]) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{display(value(key))}</dd>
                  </div>
                ))}
              </dl>
              <div className="option-metrics">
                {[
                  ["range_cltc", "CLTC km"],
                  ["zero_to_hundred", "百公里加速 s"],
                  ["top_speed", "最高车速 km/h"],
                ].map(([key, label]) => (
                  <div key={key}>
                    <strong>{numericField(option.fields, key) ?? "—"}</strong>
                    <span>{label}</span>
                  </div>
                ))}
              </div>
              {option.issues.map((issue, i) => (
                <p
                  key={i}
                  className={`micro ${issue.blocking ? "text-error" : "muted"}`}
                >
                  {issue.message}
                </p>
              ))}
              <p className="micro muted">
                {option.validity === "valid"
                  ? "关键配置已捕获；金融条件以对应来源为准"
                  : "字段存在缺失或冲突，需回官网核对"}
              </p>
            </article>
          );
        })}
      </div>
      {options.length > 1 && (
        <div className="parameter-charts">
          {[
            ["range_cltc", "km", "CLTC 续航"],
            ["zero_to_hundred", "s", "0—100 km/h 加速"],
            ["top_speed", "km/h", "最高车速"],
          ].map(([key, unit, label]) => (
            <ComparisonBars
              key={key}
              label={label}
              unit={unit}
              rows={options.map((o, i) => ({
                name: `Option ${String.fromCharCode(65 + i)}`,
                value: numericField(o.fields, key),
              }))}
            />
          ))}
        </div>
      )}
      {activeModules.map((m, i) => (
        <Provenance key={i} status={m.status} sources={m.source_refs} />
      ))}
      <StaticAsk>问 Tess：这几个方案怎样取舍？</StaticAsk>
    </section>
  );
}
export function FinanceModule({
  module,
  options,
}: {
  module: ReportModule;
  options: OptionView[];
}) {
  const data = moduleData<FinanceView>(module),
    rows = financeRows(data),
    index = options.findIndex((o) => o.capture_id === data.capture_id),
    label =
      index >= 0 ? `Option ${String.fromCharCode(65 + index)}` : "当前方案";
  return (
    <section className="report-section">
      <div className="section-heading">
        <p className="eyebrow">FINANCING</p>
        <h2>月供，放回家庭预算里看。</h2>
        <p>
          {label} · {data.note}
        </p>
      </div>
      {data.state === "no_solution" ? (
        <div className="report-missing">
          <h3>当前没有满足全部条件的方案</h3>
          {data.unmet_constraints.map((x, i) => (
            <p key={i}>{x}</p>
          ))}
        </div>
      ) : (
        <>
          <BudgetBars
            budget={
              typeof data.constraints.monthly_cap_fen === "number"
                ? data.constraints.monthly_cap_fen
                : null
            }
            rows={rows.map((r, i) => ({
              name: `方案 ${i + 1} · ${r.term_months} 期`,
              payment: r.monthly_payment_fen,
            }))}
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>方案</th>
                  <th>首付</th>
                  <th>期数</th>
                  <th>月供</th>
                  <th>末期还款</th>
                  <th>融资成本</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td>{money(r.down_payment_fen)}</td>
                    <td>{r.term_months}</td>
                    <td>
                      <strong>{money(r.monthly_payment_fen)}</strong>
                    </td>
                    <td>{money(r.last_payment_fen)}</td>
                    <td>{money(r.financing_cost_fen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="micro muted">
            金额来自同一份确定性计算结果。金融产品、费用和适用资格需以当前官方条件及实际审核为准；Mock
            产品不代表官方承诺。
          </p>
        </>
      )}
      <Provenance status={module.status} sources={module.source_refs} />
      <StaticAsk>问 Tess：调整首付后，月供会如何变化？</StaticAsk>
    </section>
  );
}
export function ChargingModule({
  module,
  owner,
  preview,
}: {
  module: ReportModule;
  owner: string;
  preview: boolean;
}) {
  const data = moduleData<ChargingView>(module),
    [imageFailed, setImageFailed] = useState(false),
    url = safeMapUrl(data);
  const asset = data.map_asset_id
    ? `${apiBase}/${preview ? "sessions" : "reports"}/${encodeURIComponent(owner)}/assets/${encodeURIComponent(data.map_asset_id)}`
    : null;
  const map =
    asset && !imageFailed ? (
      <img
        className="charging-map"
        src={asset}
        alt={`${data.city || ""}${data.region}周边充电站静态地图，编号与下方列表对应`}
        onError={() => setImageFailed(true)}
      />
    ) : (
      <div className="map-unavailable">
        <span>地图暂不可用</span>
        <p>保留已查询到的站点；不会使用示意图替代真实地图。</p>
      </div>
    );
  return (
    <section className="report-section">
      <div className="section-heading">
        <p className="eyebrow">CHARGING AROUND YOU</p>
        <h2>从常用区域，看看补能选择。</h2>
        <p>
          {data.city || ""} {data.region} · 查询半径约 {data.radius_m / 1000} km
        </p>
      </div>
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="map-link"
        >
          {map}
        </a>
      ) : (
        map
      )}
      {data.state === "failed" && (
        <p className="report-missing">
          本次充电查询未完成。请结合已保留的来源信息核对，或进入高德重新搜索。
        </p>
      )}
      {data.state === "no_results" && (
        <p className="report-missing">
          本次未找到符合条件的 Tesla 充电设施；不代表该区域一定没有站点。
        </p>
      )}
      {data.state === "ambiguous" && (
        <p className="report-missing">地点存在多个候选，尚需确认具体区域。</p>
      )}
      <div className="station-list">
        {(data.stations || []).map((station) => (
          <article key={station.id}>
            <span className="station-number">{station.number}</span>
            <div>
              <h3>{station.name}</h3>
              <p>
                {station.distance_basis}约{" "}
                {(station.center_distance_m / 1000).toFixed(1)} km
                {station.driving_distance_m != null
                  ? ` · 驾车约 ${(station.driving_distance_m / 1000).toFixed(1)} km`
                  : ""}
                {station.driving_duration_seconds != null
                  ? ` / ${Math.round(station.driving_duration_seconds / 60)} 分钟`
                  : ""}
              </p>
            </div>
          </article>
        ))}
      </div>
      {data.warnings?.map((warning, i) => (
        <p className="micro muted" key={i}>
          {warning}
        </p>
      ))}
      {url && (
        <a
          className="amap-link"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
        >
          在高德继续搜索 ↗
        </a>
      )}
      <p className="micro muted">
        中心点距离与驾车距离口径不同。站点状态并非实时空闲状态；外部搜索为高德当前结果，可能与报告快照不同。是否方便还需要结合通勤里程与补能频率判断。
      </p>
      <Provenance status={module.status} sources={module.source_refs} />
      <StaticAsk>问 Tess：没有家充，日常补能会不会麻烦？</StaticAsk>
    </section>
  );
}
export function EnergyModule({ module }: { module: ReportModule }) {
  const data = moduleData<EnergyView>(module),
    points = chartSeries(data),
    last = points.at(-1),
    a = data.assumptions;
  return (
    <section className="report-section">
      <div className="section-heading">
        <p className="eyebrow">ENERGY COST ESTIMATE</p>
        <h2>长期使用，能源开支有多少差别？</h2>
      </div>
      {last && (
        <div className="energy-result">
          <p>
            {last.year} 年累计能源成本
            {last.saving_fen >= 0 ? "预计节省" : "预计增加"}
          </p>
          <strong>{money(Math.abs(last.saving_fen))}</strong>
          <span>Estimate · 仅能源成本，不包含购车、保险、保养与折旧</span>
        </div>
      )}
      <EnergyChart data={data} />
      <div className="assumption-grid">
        {[
          ["年行驶里程", `${a.annual_km.toLocaleString("zh-CN")} km`],
          ["持有周期", `${a.years} 年`],
          ["电耗", `${a.kwh_per_100km} kWh / 100km`],
          ["充电均价", `¥${a.electricity_yuan_per_kwh} / kWh`],
          ["对标油耗", `${a.liters_per_100km} L / 100km`],
          ["油价", `¥${a.fuel_yuan_per_liter} / L`],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <p className="micro muted">
        假设来源：{a.source}。估算输入不代表已由销售或客户确认。
      </p>
      <p className="micro muted">
        家充与公共充电比例、实际能耗、年里程及能源价格变化都会影响结果。此处为能源开支估算，不是整车总持有成本。
      </p>
      <Provenance status={module.status} sources={module.source_refs} />
      <StaticAsk>问 Tess：按实际通勤重新估算一下</StaticAsk>
    </section>
  );
}
export function FamilyModule({ module }: { module: ReportModule }) {
  const data = moduleData<FamilyView>(module),
    entries = validFamilyEntries(data);
  return (
    <section className="report-section">
      <div className="section-heading">
        <p className="eyebrow">FAMILY & EVERYDAY USE</p>
        <h2>和家庭更相关的信息</h2>
      </div>
      {entries.length ? (
        entries.map((entry, i) => (
          <article className="knowledge-entry" key={i}>
            <h3>{entry.title}</h3>
            <p>{entry.text}</p>
            <a
              href={safeOfficialUrl(entry.url)!}
              target="_blank"
              rel="noreferrer"
            >
              Tesla 官方来源 ↗
            </a>
            <small>{date(entry.reviewed_at)}</small>
          </article>
        ))
      ) : (
        <p className="report-missing">暂缺可核实官方资料，保留待进一步确认。</p>
      )}
      <Provenance status={module.status} sources={module.source_refs} />
    </section>
  );
}
export function TrialModule({ module }: { module: ReportModule }) {
  const data = moduleData<{
    vehicle: { model: string; variant: string | null } | null;
    feedback: { value: Json; source_kind: string; source_fact_id: string }[];
  }>(module);
  return (
    <section className="report-section trial-section">
      <div className="section-heading">
        <p className="eyebrow">THE TEST DRIVE</p>
        <h2>本次试驾</h2>
        <p>
          {data.vehicle
            ? `${data.vehicle.model} · ${data.vehicle.variant || "具体版本待确认"}`
            : "实际试驾车型尚待确认"}
        </p>
        <div className="option-visual trial-visual">
          <span>{data.vehicle?.model || "MODEL Y"}</span>
          <small>暂无本次试驾车辆的可核实图片</small>
        </div>
      </div>
      <div className="trial-notes">
        {data.feedback?.length ? (
          data.feedback.map((f, i) => (
            <p key={i}>
              {display(f.value)}
              <small>销售转述 · 仅归属本次实际试驾</small>
            </p>
          ))
        ) : (
          <p className="muted">
            本次尚无已确认的试驾反馈。候选配置不自动代表实际体验车型。
          </p>
        )}
      </div>
      <Provenance status={module.status} sources={module.source_refs} />
    </section>
  );
}
export function MissingModule({ module }: { module: ReportModule }) {
  const labels: Record<string, string> = {
    finance: "金融方案",
    charging: "家庭充电",
    energy: "能源成本",
    family: "家庭相关信息",
    missing: "待补充信息",
  };
  return (
    <section className="missing-module">
      <span className="tag warning">Missing</span>
      <h3>{labels[module.type] || "部分信息暂缺"}</h3>
      <p>{display(module.data.reason)}</p>
    </section>
  );
}
