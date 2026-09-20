import { useState } from "react";
import type { Capture } from "../types/api";
import { money, date, display } from "../utils/display";
import { SourceTag } from "./Shared";
const labels: Record<string, string> = {
  model: "车型",
  variant: "版本",
  paint: "外观",
  wheels: "轮毂",
  interior: "内饰",
  seats: "座位",
  autopilot: "辅助驾驶",
  accessories: "配件",
  vehicle_price: "车辆价格",
  price_basis: "价格口径",
  delivery: "交付",
  range_cltc: "CLTC 续航",
  top_speed: "最高车速",
  zero_to_hundred: "百公里加速",
  finance_product: "金融产品",
  down_payment: "首付",
  principal: "贷款本金",
  term_months: "期数",
  monthly_payment: "月供",
  rate_value: "利率",
  rate_basis: "利率口径",
  fees: "费用",
  discounts: "优惠",
};
export default function CaptureCard({
  capture,
  index,
  busy,
  ownerName,
  onRemove,
  onPreference,
}: {
  capture: Capture;
  index: number;
  busy: boolean;
  ownerName: string;
  onRemove: () => void;
  onPreference: (value: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const payload = capture.immutable_payload,
    field = (key: string) => payload.fields.find((f) => f.key === key)?.value;
  const isMock = payload.adapter_version.includes("mock");
  const finance = field("finance_product") != null;
  return (
    <article className="capture-card">
      <div className="row between">
        <span className="eyebrow">
          OPTION {String.fromCharCode(65 + index)}
        </span>
        <SourceTag tone={capture.validity === "valid" ? "success" : "warning"}>
          {isMock
            ? "Mock"
            : capture.validity === "valid"
              ? "官网快照"
              : "需核对"}
        </SourceTag>
      </div>
      <h3>
        {display(field("model"))} {display(field("variant"))}
      </h3>
      <p className="muted micro">
        {[field("paint"), field("wheels"), field("interior")]
          .filter(Boolean)
          .map((x) => display(x))
          .join(" · ")}
      </p>
      <div className="row between">
        <strong className="price">{money(field("vehicle_price"))}</strong>
        <span className="muted micro">{date(payload.captured_at)}</span>
      </div>
      <p className="micro muted">
        {capture.validity === "valid" ? "关键配置已捕获" : "关键配置尚需核对"} ·{" "}
        {finance ? "金融以本次采集条件为准" : "金融待获取"}
      </p>
      {capture.issues.map((issue, i) => (
        <p
          className={`micro ${issue.blocking ? "text-error" : "muted"}`}
          key={i}
        >
          {issue.message}
        </p>
      ))}
      <div className="capture-actions">
        <label className="sr-only" htmlFor={`pref-${capture.id}`}>
          方案偏好归属
        </label>
        <select
          id={`pref-${capture.id}`}
          value={capture.preference || ""}
          disabled={busy}
          onChange={(e) => onPreference(e.target.value)}
        >
          <option value="">未标注偏好</option>
          <option value={ownerName}>{ownerName} 更偏好</option>
          <option value="家人">家人更偏好</option>
          <option value="Shared">家庭共同考虑</option>
        </select>
        <button className="text-button" onClick={() => setExpanded(!expanded)}>
          {expanded ? "收起" : "查看字段"}
        </button>
        <button className="text-button" disabled={busy} onClick={onRemove}>
          移除
        </button>
      </div>
      {expanded && (
        <div className="capture-detail">
          <dl>
            {payload.fields.map((f) => (
              <div key={f.key}>
                <dt>{labels[f.key] || f.key}</dt>
                <dd>
                  {f.unit === "CNY_fen" ? money(f.value) : display(f.value)}
                  {f.unit && f.unit !== "CNY_fen" ? " " + f.unit : ""}
                </dd>
              </div>
            ))}
          </dl>
          <a href={payload.source_url} target="_blank" rel="noreferrer">
            查看来源官网 ↗
          </a>
          <p className="micro muted">
            动态信息仅反映采集时状态。官方事实不可在此编辑，请回官网重新配置并
            Capture。
          </p>
        </div>
      )}
    </article>
  );
}
