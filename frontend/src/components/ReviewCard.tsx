import { useEffect, useRef, useState } from "react";
import type { SessionDetail, Summary } from "../types/api";
import { tess } from "../services/tess";
import { newKey, staticReportUrl } from "../services/api";
import { ErrorNotice } from "./Shared";
import BorderGlow from "./BorderGlow";

interface Props {
  session: SessionDetail;
  onRefresh: () => Promise<unknown>;
  onError: (message: string) => void;
  /** 场景 6：精简报告卡，打开预览 / 复制链接 / 复制文案 */
  previewOnly?: boolean;
}

export default function ReviewCard({
  session,
  onRefresh,
  onError,
  previewOnly = false,
}: Props) {
  const draft = session.draft!,
    [editing, setEditing] = useState(false),
    [summary, setSummary] = useState<Summary>(draft.report_data.summary),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [reviewed, setReviewed] = useState(false),
    [copied, setCopied] = useState("");
  const keyStorage = `tess.publish.${session.id}.${draft.id}.${draft.draft_revision}`;
  const publishKey = useRef(localStorage.getItem(keyStorage) || newKey());
  const latestSummary = useRef(draft.report_data.summary);
  latestSummary.current = draft.report_data.summary;
  const preview = staticReportUrl(session.id);
  const customerName = "张先生";

  function shareMessage() {
    return `${customerName}，您好：
这是您今天试驾后的旅程入口，可查看复盘总结或继续与助手沟通。

链接：
${preview}
若还有疑问，随时联系我。期待您再次到店。
—— Alex · 销售顾问 1886889092`;
  }

  useEffect(() => {
    setSummary(latestSummary.current);
    setReviewed(false);
    publishKey.current = localStorage.getItem(keyStorage) || newKey();
    localStorage.setItem(keyStorage, publishKey.current);
  }, [draft.id, draft.draft_revision, keyStorage]);

  const changed =
    JSON.stringify(summary) !== JSON.stringify(draft.report_data.summary);

  async function save() {
    setBusy(true);
    setError("");
    try {
      await tess.editDraft(
        session.id,
        draft.id,
        session.revision,
        draft.draft_revision,
        summary,
      );
      await onRefresh();
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    setBusy(true);
    setError("");
    try {
      await tess.publish(
        session.id,
        draft.id,
        session.revision,
        draft.draft_revision,
        publishKey.current,
      );
      await onRefresh();
    } catch (e) {
      setError((e as Error).message);
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function openPreview() {
    window.open(preview, "_blank", "noopener,noreferrer");
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(preview);
      setCopied("已复制链接");
      window.setTimeout(() => setCopied(""), 2000);
    } catch {
      onError("复制失败，请重试。");
    }
  }

  async function copyShare() {
    try {
      await navigator.clipboard.writeText(shareMessage());
      setCopied("已复制发给客户的文案");
      window.setTimeout(() => setCopied(""), 2000);
    } catch {
      onError("复制失败，请重试。");
    }
  }

  const block =
    draft.stale ||
    draft.source_revision !== session.revision ||
    draft.blocking_issues.some((i) => i.blocking);

  if (previewOnly) {
    return (
      <BorderGlow
        className="report-ready-glow"
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
        <section className="report-ready-card">
          <div className="row between">
            <span className="eyebrow">TEST DRIVE REPORT</span>
          </div>
          <h2>{customerName || "客户"} · 试驾报告</h2>
          <p className="muted micro">
            {draft.report_data.summary.comparing || "本次候选方案已整理"}
          </p>
          <button
            className="primary full"
            type="button"
            onClick={openPreview}
          >
            查看报告
          </button>
          <div className="row wrap report-ready-actions">
            <button
              className="text-button"
              type="button"
              onClick={() => void copyLink()}
            >
              {copied === "已复制链接" ? copied : "复制链接"}
            </button>
            <button
              className="text-button"
              type="button"
              onClick={() => void copyShare()}
            >
              {copied === "已复制发给客户的文案"
                ? copied
                : "复制发给客户的文案"}
            </button>
          </div>
        </section>
      </BorderGlow>
    );
  }

  return (
    <section className="review-card">
      <div className="row between">
        <span className="eyebrow">READY FOR YOUR REVIEW</span>
        <span className={`tag ${block ? "warning" : "success"}`}>
          {block ? "待更新" : "待销售审核"}
        </span>
      </div>
      <h2>把这次试驾，整理清楚。</h2>
      {block && (
        <div className="notice warning">
          输入或事实已变化，请重新准备报告。旧计算不能直接发布。
        </div>
      )}
      {draft.blocking_issues.map((i, n) => (
        <p className={i.blocking ? "text-error" : "muted"} key={n}>
          {i.message}
        </p>
      ))}
      {editing ? (
        <div className="form-stack">
          <p className="notice">
            含数字的事实句保留原文与位置，不能在总结里直接改动。请先纠正预算、区域或其他输入，再重新准备报告。这里可调整其余纯文字表达。
          </p>
          <label>
            现在比较什么
            <textarea
              readOnly={/[\d零〇一二三四五六七八九十百千万亿两]/.test(
                draft.report_data.summary.comparing,
              )}
              value={summary.comparing}
              onChange={(e) =>
                setSummary((v) => ({ ...v, comparing: e.target.value }))
              }
            />
          </label>
          {(["confirmed", "pending"] as const).map((field) => (
            <div key={field}>
              <h3>{field === "confirmed" ? "已经明确什么" : "还需确认什么"}</h3>
              {summary[field].map((line, index) => (
                <label key={index} className="summary-line">
                  <span className="micro muted">
                    第 {index + 1} 项{" "}
                    {/[\d零〇一二三四五六七八九十百千万亿两]/.test(
                      draft.report_data.summary[field][index] || "",
                    )
                      ? "· 数字事实，只读"
                      : ""}
                  </span>
                  <textarea
                    readOnly={/[\d零〇一二三四五六七八九十百千万亿两]/.test(
                      draft.report_data.summary[field][index] || "",
                    )}
                    value={line}
                    onChange={(e) =>
                      setSummary((v) => ({
                        ...v,
                        [field]: v[field].map((old, i) =>
                          i === index ? e.target.value : old,
                        ),
                      }))
                    }
                  />
                </label>
              ))}
              <button
                className="text-button"
                onClick={() =>
                  setSummary((v) => ({ ...v, [field]: [...v[field], ""] }))
                }
              >
                ＋ 补充文字
              </button>
            </div>
          ))}
          <p className="muted micro">
            官网事实需重新 Capture。来源与 Mock / Estimate 标记会一直保留。
          </p>
          <button disabled={busy || !changed} onClick={() => void save()}>
            保存措辞调整
          </button>
        </div>
      ) : (
        <>
          <div className="review-section">
            <span>现在比较什么</span>
            <p>{summary.comparing}</p>
          </div>
          <div className="review-section">
            <span>已经明确什么</span>
            {summary.confirmed.length ? (
              summary.confirmed.map((x, i) => <p key={i}>{x}</p>)
            ) : (
              <p className="muted">暂无已确认结论</p>
            )}
          </div>
          <div className="review-section">
            <span>还需确认什么</span>
            {summary.pending.map((x, i) => (
              <p key={i}>{x}</p>
            ))}
          </div>
        </>
      )}
      <div className="row wrap">
        <button className="text-button" onClick={() => setEditing(!editing)}>
          {editing ? "收起编辑" : "调整总结措辞"}
        </button>
        <button
          className="text-button"
          type="button"
          onClick={openPreview}
          disabled={block}
        >
          完整预览 ↗
        </button>
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={reviewed}
          disabled={block || changed}
          onChange={(e) => setReviewed(e.target.checked)}
        />
        已核对本次客户、候选与报告内容
      </label>
      <ErrorNotice message={error} />
      <button
        className="primary full"
        disabled={busy || block || changed || !reviewed}
        onClick={() => void publish()}
      >
        {busy ? "正在保存…" : "确认并生成链接"}
      </button>
      <p className="muted micro">
        生成固定报告。之后调整并重新发布，不会改变旧链接。
      </p>
    </section>
  );
}
