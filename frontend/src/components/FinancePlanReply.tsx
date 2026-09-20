import { useEffect, useState, type ReactNode } from "react";
import type { FinanceCaseAResult, FinanceToolCall } from "../mocks/demoFinance";
import type {
  KnowledgeSource,
  KnowledgeToolCall,
} from "../mocks/knowledgeCopilot";
import type {
  DecisionContextToolCall,
  DecisionSlot,
} from "../mocks/decisionContext";

const yuan = (value: number) => `¥${value.toLocaleString("zh-CN")}`;

export function ThinkingBubble({ label }: { label: string }) {
  return (
    <div className="chat-row assistant process">
      <div className="chat-process-line thinking">
        <span className="thinking-dots" aria-hidden>
          <i />
          <i />
          <i />
        </span>
        <span>{label}</span>
      </div>
    </div>
  );
}

/** 架构阶段：意图 / 路由（风控通过静默，不单独占卡） */
export function StageBubble({
  label,
  title,
  lines,
}: {
  label: string;
  title?: string;
  lines?: string[];
}) {
  return (
    <div className="chat-row assistant process">
      <div className="chat-process-block">
        <p className="chat-process-label">{label}</p>
        {title ? <p className="chat-process-title">{title}</p> : null}
        {lines && lines.length > 0 ? (
          <ul>
            {lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

/** @deprecated 用 StageBubble；保留兼容 */
export function UnderstandBubble({
  lines,
  label = "理解约束",
}: {
  lines: string[];
  label?: string;
}) {
  return <StageBubble label={label} lines={lines} />;
}

export function PlanningBubble({
  steps,
  loading,
  loadingText = "正在规划…",
}: {
  steps: string[];
  loading?: boolean;
  loadingText?: string;
}) {
  return (
    <div className="chat-row assistant process">
      <div className={`chat-process-block ${loading ? "is-loading" : ""}`}>
        <p className="chat-process-label">Plan</p>
        {loading ? (
          <p className="planning-loading">{loadingText}</p>
        ) : (
          <ol>
            {steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

export function ToolBubble({ call }: { call: FinanceToolCall }) {
  return (
    <div className="chat-row assistant process">
      <div
        className={`chat-process-block tool ${call.ok ? "is-ok" : "is-fail"}`}
      >
        <div className="finance-tool-head">
          <span>{call.title}</span>
          <strong>{call.ok ? "满足" : "不满足"}</strong>
        </div>
        <p>
          车价 {yuan(call.priceYuan)} · 车款首付 {yuan(call.downYuan)} · 月供{" "}
          {yuan(call.monthlyYuan)}
        </p>
        <p className="finance-tool-note">{call.note}</p>
      </div>
    </div>
  );
}

export function KnowledgeToolBubble({ call }: { call: KnowledgeToolCall }) {
  return (
    <div className="chat-row assistant process">
      <div
        className={`chat-process-block tool kb-tool ${call.ok ? "is-ok" : "is-fail"}`}
      >
        <div className="finance-tool-head">
          <span>{call.title}</span>
          <strong>{call.ok ? "已命中" : "未命中"}</strong>
        </div>
        <p className="kb-tool-query">query · {call.query}</p>
        <p className="finance-tool-note">
          {call.note}
          {call.hits.length
            ? ` · ${call.hits.map((hit) => hit.title).join("、")}`
            : ""}
        </p>
      </div>
    </div>
  );
}

export function DecisionContextToolBubble({
  call,
}: {
  call: DecisionContextToolCall;
}) {
  return (
    <div className="chat-row assistant process">
      <div
        className={`chat-process-block tool dc-tool ${call.ok ? "is-ok" : "is-fail"}`}
      >
        <div className="finance-tool-head">
          <span>{call.title}</span>
          <strong>{call.ok ? "完成" : "失败"}</strong>
        </div>
        <p className="kb-tool-query">action · {call.action}</p>
        <p className="finance-tool-note">
          {call.note}
          {call.gaps?.length ? ` · 缺口：${call.gaps.join("、")}` : ""}
        </p>
      </div>
    </div>
  );
}

export function DecisionContextReply({
  intro,
  slots,
  followup,
  compact,
}: {
  intro?: string;
  slots?: DecisionSlot[];
  followup?: string;
  /** 只展示增量更新项时用 */
  compact?: boolean;
}) {
  return (
    <div className="chat-row assistant">
      <div className="chat-meta">Tess</div>
      <div className="chat-bubble assistant conclusion">
        {intro ? <p className="reply-block">{intro}</p> : null}
        {slots && slots.length > 0 ? (
          <dl className={`decision-slots ${compact ? "is-compact" : ""}`}>
            {slots.map((slot) => (
              <div key={slot.key} className="decision-slot">
                <dt>{slot.label}</dt>
                <dd>{slot.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {followup
          ? followup.split(/\n\n+/).map((block, index) => (
              <p key={index} className="reply-block">
                {block.split("\n").map((line, lineIndex) => (
                  <span key={lineIndex}>
                    {lineIndex > 0 ? <br /> : null}
                    {line}
                  </span>
                ))}
              </p>
            ))
          : null}
      </div>
    </div>
  );
}

export function ProcessTrail({
  done,
  children,
}: {
  done: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(!done);

  useEffect(() => {
    if (done) setOpen(false);
  }, [done]);

  if (!done) return <>{children}</>;

  return (
    <div className="chat-row assistant process">
      <button
        type="button"
        className="process-toggle"
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "收起推理过程" : "已完成推理 · 展开"}
      </button>
      {open ? <div className="process-trail">{children}</div> : null}
    </div>
  );
}

export function FinanceConclusion({
  result,
  onAction,
}: {
  result: FinanceCaseAResult;
  onAction: (id: "apply_a" | "apply_b") => void;
}) {
  const bothOk = result.optionA.ok && result.optionB.ok;
  return (
    <div className="chat-row assistant">
      <div className="chat-meta">Tess</div>
      <div className="chat-bubble assistant conclusion">
        <p>
          <strong>{result.optionLabel} 现配置不满足。</strong>
          车款首付 {yuan(result.downYuan)}，月供 {yuan(result.currentMonthly)}
          （提车现金上限 {yuan(result.optionA.cashYuan)}，其中税险牌估算{" "}
          {yuan(result.taxInsPlateYuan)}）。
          {bothOk
            ? "下面两个方案都能满足硬约束，请按客户取舍选择："
            : null}
        </p>

        <section
          className={`finance-option ${result.optionA.ok ? "is-ok" : "is-fail"}`}
        >
          <header>
            <h4>{result.optionA.title}</h4>
            <span>{result.optionA.ok ? "可满足" : "不满足"}</span>
          </header>
          <p>
            {result.optionA.summary}。车款首付 {yuan(result.optionA.downYuan)}
            ，月供 {yuan(result.optionA.monthlyYuan)}。
          </p>
          {result.optionA.pros ? (
            <p className="finance-tradeoff">
              <strong>优势：</strong>
              {result.optionA.pros}
            </p>
          ) : null}
          {result.optionA.cons ? (
            <p className="finance-tradeoff">
              <strong>代价：</strong>
              {result.optionA.cons}
            </p>
          ) : null}
        </section>

        <section
          className={`finance-option ${result.optionB.ok ? "is-ok" : "is-fail"}`}
        >
          <header>
            <h4>{result.optionB.title}</h4>
            <span>{result.optionB.ok ? "可满足" : "不满足"}</span>
          </header>
          <p>
            {result.optionB.summary}。车款首付 {yuan(result.optionB.downYuan)}
            ，月供 {yuan(result.optionB.monthlyYuan)}
            {result.optionB.ok ? "。" : "，仍超出月供上限。"}
          </p>
          {result.optionB.pros ? (
            <p className="finance-tradeoff">
              <strong>优势：</strong>
              {result.optionB.pros}
            </p>
          ) : null}
          {result.optionB.cons ? (
            <p className="finance-tradeoff">
              <strong>代价：</strong>
              {result.optionB.cons}
            </p>
          ) : null}
        </section>

        <p className="finance-recommend">
          <strong>更推荐方案 {result.recommend}。</strong>
          {result.recommendReason}
        </p>

        <div className="finance-actions">
          {result.actions.map((action) => {
            const isRecommend =
              (action.id === "apply_a" && result.recommend === "A") ||
              (action.id === "apply_b" && result.recommend === "B");
            return (
              <button
                key={action.id}
                type="button"
                className={
                  bothOk
                    ? isRecommend
                      ? "secondary compact"
                      : "text-button"
                    : action.id === "apply_a"
                      ? "secondary compact"
                      : "text-button"
                }
                onClick={() => onAction(action.id)}
              >
                {action.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function ReplyBubble({
  text,
  sources,
}: {
  text: string;
  sources?: KnowledgeSource[];
}) {
  return (
    <div className="chat-row assistant">
      <div className="chat-meta">Tess</div>
      <div className="chat-bubble assistant conclusion">
        {text.split(/\n\n+/).map((block, index) => (
          <p key={index} className="reply-block">
            {block.split("\n").map((line, lineIndex) => (
              <span key={lineIndex}>
                {lineIndex > 0 ? <br /> : null}
                {line}
              </span>
            ))}
          </p>
        ))}
        {sources && sources.length > 0 ? (
          <div className="knowledge-sources">
            <span className="knowledge-sources-label">来源</span>
            {sources.map((source, index) => (
              <span key={source.id} className="knowledge-source-item">
                {index > 0 ? <span className="knowledge-source-sep">·</span> : null}
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.title}
                </a>
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
