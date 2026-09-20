import { useState } from "react";
import type { Capture } from "../types/api";
import {
  money,
  display,
  optionLabel,
  deliveryLabel,
  extraLabels,
  surchargeLines,
  chargeText,
} from "../utils/display";
import { contractMock } from "../services/api";
import { openOfficialFinance } from "../services/capture";
import BorderGlow from "./BorderGlow";

const labels: Record<string, string> = {
  model: "车型",
  variant: "版本",
  paint: "外观",
  wheels: "轮毂",
  interior: "内饰",
  seats: "座位",
  autopilot: "辅助驾驶",
  accessories: "配件",
  extras: "加选",
  option_surcharges: "选配加价",
  trim_price: "版本标价",
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
  monthly_payment: "贷款月供",
  rate_value: "年化费率",
  rate_basis: "利率口径",
  fees: "费用",
  discounts: "优惠",
};

const groupLabels: Record<string, string> = {
  paint: "外观",
  wheels: "轮毂",
  interior: "内饰",
  seats: "座位",
  autopilot: "辅助驾驶",
  accessories: "配件",
  extras: "加选",
};
const yuan = (value: unknown) => money(value, 0);
const hiddenIssue = /FINANCE_NOT_VISIBLE|FIELD_MISSING|MOCK_DATA|FINANCE_MISSING/;
const hiddenDetail = new Set([
  "model",
  "variant",
  "paint",
  "wheels",
  "interior",
  "extras",
  "option_surcharges",
  "range_cltc",
  "top_speed",
  "zero_to_hundred",
  "vehicle_price",
  "monthly_payment",
  "down_payment",
  "term_months",
  "rate_value",
  "rate_basis",
  "delivery",
]);

export default function CaptureCard({
  capture,
  index,
  busy,
  onRemove,
  onConfirmFinance,
  versionTag,
  readOnly = false,
  optionNumber,
}: {
  capture: Capture;
  index: number;
  busy: boolean;
  onRemove: () => void;
  onConfirmFinance: () => Promise<void>;
  versionTag?: string;
  readOnly?: boolean;
  optionNumber?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [financeOpen, setFinanceOpen] = useState(false);
  const [financeNote, setFinanceNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const payload = capture.immutable_payload,
    field = (key: string) => payload.fields.find((f) => f.key === key)?.value;
  const monthly = field("monthly_payment");
  const price = field("vehicle_price");
  const down = field("down_payment");
  const term = field("term_months");
  const rate = field("rate_value");
  const rateBasis = field("rate_basis");
  const finish = deliveryLabel(field("delivery"));
  const specs = [field("paint"), field("wheels"), field("interior")]
    .map((item) => optionLabel(item))
    .filter((item) => item && item !== "未知");
  const extras = extraLabels(
    field("extras"),
    field("autopilot"),
    field("accessories"),
  );
  const breakdown = surchargeLines(field("option_surcharges"));
  const stats = [
    field("range_cltc") != null && {
      value: `${field("range_cltc")}公里`,
      label: "续航 (CLTC)",
    },
    field("top_speed") != null && {
      value: `${field("top_speed")}公里/小时`,
      label: "最高车速",
    },
    field("zero_to_hundred") != null && {
      value: `${field("zero_to_hundred")}秒`,
      label: "百公里加速",
    },
  ].filter(Boolean) as { value: string; label: string }[];

  async function openFinance() {
    setFinanceOpen(true);
    if (contractMock) {
      setFinanceNote("演示版不打开官网。点右侧确认，会按当前 Mock 金融数据写回这张卡。");
      return;
    }
    try {
      await openOfficialFinance();
      setFinanceNote("在官网改完方案后，点右侧确认，抓取当前贷款月供、首付和期数。");
    } catch (error) {
      setFinanceNote(
        error instanceof Error
          ? error.message
          : "无法打开官网金融方案，请切到 Model Y 配置页后再试。",
      );
    }
  }

  return (
    <BorderGlow
      className="capture-glow"
      edgeSensitivity={30}
      glowColor="40 80 80"
      backgroundColor="#ffffff"
      borderRadius={16}
      glowRadius={0}
      glowIntensity={0}
      coneSpread={25}
      animated={false}
      fillOpacity={0}
      colors={["#c084fc", "#f472b6", "#38bdf8"]}
    >
    <article className="capture-card">
      <header className="capture-head">
        <span className="capture-kicker">
          OPTION{" "}
          {optionNumber != null
            ? optionNumber
            : String.fromCharCode(65 + index)}
          {versionTag ? ` · ${versionTag}` : ""}
        </span>
        {!readOnly && (
          <button
            className="capture-remove"
            type="button"
            disabled={busy}
            onClick={onRemove}
          >
            移除
          </button>
        )}
      </header>
      <div className="capture-title">
        <h3>
          {display(field("model"))} {display(field("variant"))}
        </h3>
        {finish ? <span className="capture-delivery">{finish}</span> : null}
      </div>
      {specs.length > 0 && (
        <p className="capture-specs">{specs.join("  · ")}</p>
      )}
      {extras.length > 0 && (
        <p className="capture-extras">{extras.join(" · ")}</p>
      )}
      {stats.length > 0 && (
        <dl className="capture-stats">
          {stats.map((item) => (
            <div key={item.label}>
              <dd>{item.value}</dd>
              <dt>{item.label}</dt>
            </div>
          ))}
        </dl>
      )}
      <dl className="capture-price">
        {typeof price === "number" && (
          <div className="is-price">
            <dt>车辆价格</dt>
            <dd>{yuan(price)}</dd>
          </div>
        )}
        {typeof monthly === "number" && (
          <div className="is-monthly">
            <dt>贷款月供</dt>
            <dd>
              {yuan(monthly)}
              <span className="capture-per"> /月</span>
            </dd>
          </div>
        )}
      </dl>
      {typeof down === "number" &&
        typeof rate === "number" &&
        term != null && (
          <p className="capture-finance-line">
            按首付 {yuan(down)}，
            {display(rateBasis) === "未知" ? "年化费率" : display(rateBasis)}{" "}
            {Number(rate).toFixed(2)}%，{display(term)} 期
          </p>
        )}
      {capture.issues
        .filter((issue) => issue.blocking && !hiddenIssue.test(issue.code))
        .map((issue, i) => (
          <p className="micro text-error" key={i}>
            {issue.message}
          </p>
        ))}
      <div className="capture-actions">
        <button className="text-button" onClick={() => setExpanded(!expanded)}>
          {expanded ? "收起" : "查看详情"}
        </button>
        <button
          className="text-button"
          type="button"
          disabled={busy}
          onClick={() => void openFinance()}
        >
          金融方案
        </button>
        {financeOpen && (
          <>
            <button
              className="capture-confirm"
              type="button"
              disabled={busy || confirming}
              onClick={() => {
                setConfirming(true);
                void onConfirmFinance()
                  .then(() => {
                    setFinanceOpen(false);
                    setFinanceNote("");
                  })
                  .finally(() => setConfirming(false));
              }}
            >
              {confirming ? "抓取中…" : "确认"}
            </button>
            <button
              className="capture-cancel"
              type="button"
              disabled={busy || confirming}
              onClick={() => {
                setFinanceOpen(false);
                setFinanceNote("");
              }}
            >
              取消
            </button>
          </>
        )}
      </div>
      {financeOpen && (
        <p className="capture-finance-note">{financeNote}</p>
      )}
      {expanded && (
        <div className="capture-detail">
          <section className="capture-breakdown">
            <h4>价格明细</h4>
            <dl>
              {breakdown.map((item) => (
                <div key={`${item.group}-${item.name}`}>
                  <dt>{groupLabels[item.group] || "选配"}</dt>
                  <dd>
                    <span>{item.name}</span>
                    <strong>{chargeText(item.amount, item.included)}</strong>
                  </dd>
                </div>
              ))}
              {typeof price === "number" && (
                <div className="is-total">
                  <dt>车辆价格</dt>
                  <dd>
                    <span>当前配置合计</span>
                    <strong>{yuan(price)}</strong>
                  </dd>
                </div>
              )}
              {typeof monthly === "number" && (
                <div>
                  <dt>贷款月供</dt>
                  <dd>
                    <span>
                      {typeof down === "number"
                        ? `首付 ${yuan(down)} · ${display(term)} 期`
                        : "当前方案"}
                    </span>
                    <strong>{yuan(monthly)}</strong>
                  </dd>
                </div>
              )}
            </dl>
          </section>
          <dl>
            {payload.fields
              .filter((f) => !hiddenDetail.has(f.key))
              .map((f) => (
                <div key={f.key}>
                  <dt>{labels[f.key] || f.key}</dt>
                  <dd>
                    {f.unit === "CNY_fen" ? yuan(f.value) : display(f.value)}
                    {f.unit && f.unit !== "CNY_fen" ? " " + f.unit : ""}
                  </dd>
                </div>
              ))}
          </dl>
          <a href={payload.source_url} target="_blank" rel="noreferrer">
            查看来源官网 ↗
          </a>
        </div>
      )}
    </article>
    </BorderGlow>
  );
}
