import { useState } from "react";
import { currentFacts, replacementIds, confirmationReferences } from "../utils/facts";
import type { Fact, FactChange, Question } from "../types/api";
import {
  factLabels,
  sourceLabels,
  display,
  isMoneyFact,
  money,
} from "../utils/display";
interface Props {
  facts: Fact[];
  questions: Question[];
  busy: boolean;
  onConfirm: (changes: FactChange[], skip: boolean) => Promise<void>;
}
export default function ContextCard({
  facts,
  questions,
  busy,
  onConfirm,
}: Props) {
  const [values, setValues] = useState<Record<string, string>>({}),
    [unknown, setUnknown] = useState<Record<string, boolean>>({}),
    [error, setError] = useState(""),
    [edit, setEdit] = useState(false);
  const current = currentFacts(facts);
  const groups = new Map<string, Fact[]>();
  for (const f of current) {
    if (!groups.has(f.key)) groups.set(f.key, []);
    groups.get(f.key)!.push(f);
  }
  const important = questions
    .filter((q) => !q.state || q.state === "open")
    .slice(0, 3);
  const needs =
    current.some((f) => f.state === "proposed" || f.state === "conflict") ||
    important.length > 0;
  const submit = async (skip: boolean) => {
    setError("");
    const changes: FactChange[] = [];
    for (const [key, group] of groups) {
      const last = group.at(-1)!;
      const isChanged = key in values || key in unknown;
      if (
        !isChanged &&
        (last.state === "confirmed" || last.state === "unknown") &&
        last.scope !== "historical"
      )
        continue;
      if (last.scope === "historical" && !isChanged) continue;
      if (group.some((f) => f.state === "conflict") && !isChanged) {
        setError("冲突项需要明确填写本次值或选择不知道。");
        return;
      }
      const raw =
        values[key] ??
        (isMoneyFact(key) && typeof last.value === "number"
          ? String(last.value / 100)
          : display(last.value));
      const isUnknown = unknown[key] === true;
      const number = isMoneyFact(key) || typeof last.value === "number";
      if (
        !isUnknown &&
        number &&
        (!raw.trim() || !Number.isFinite(Number(raw)))
      ) {
        setError("请填写有效数字，或选择不知道。");
        return;
      }
      const value = isUnknown
        ? null
        : isMoneyFact(key)
          ? Math.round(Number(raw) * 100)
          : number
            ? Number(raw)
            : raw.trim();
      changes.push({
        ...confirmationReferences(facts, group),
        key,
        value,
        state: isUnknown ? "unknown" : "confirmed",
        evidence_note: isUnknown ? "销售明确表示本次未知" : "销售核对本次信息",
      });
    }
    // Empty optional fields stay unknown; do not invent default budget/vehicle.
    for (const key of ["trial_variant", "monthly_budget", "region"])
      if (!groups.has(key) && (key in values || unknown[key])) {
        const raw = values[key] || "";
        if (!unknown[key] && !raw.trim()) continue;
        if (
          isMoneyFact(key) &&
          !unknown[key] &&
          !Number.isFinite(Number(raw))
        ) {
          setError("预算需为有效数字。");
          return;
        }
        changes.push({
          key,
          value: unknown[key]
            ? null
            : isMoneyFact(key)
              ? Math.round(Number(raw) * 100)
              : raw.trim(),
          state: unknown[key] ? "unknown" : "confirmed",
          supersedes: [],
          evidence_note: "销售补充并确认本次信息",
        });
      }
    try {
      await onConfirm(changes, skip);
      setEdit(false);
      setValues({});
      setUnknown({});
    } catch (e) {
      setError((e as Error).message);
    }
  };
  if (!needs && !edit)
    return (
      <section className="context-summary">
        <div className="row between">
          <h3>本次已记录</h3>
          <button className="text-button" onClick={() => setEdit(true)}>
            补充 / 纠正
          </button>
        </div>
        {current.length ? (
          current.slice(0, 5).map((f) => (
            <p key={f.id} className="micro">
              <span className="muted">{factLabels[f.key] || f.key} </span>
              {f.state === "unknown"
                ? "未知"
                : isMoneyFact(f.key)
                  ? money(f.value)
                  : display(f.value)}{" "}
              <span className="muted">
                ·{" "}
                {f.scope === "historical"
                  ? "历史参考，待本次确认"
                  : sourceLabels[f.source_kind] || f.source_kind}
              </span>
            </p>
          ))
        ) : (
          <p className="muted micro">
            实际试驾版本、预算与家庭需求尚待复盘。候选版本不会自动成为试驾事实。
          </p>
        )}
      </section>
    );
  const keys = [
    ...groups.keys(),
    ...["trial_variant", "monthly_budget", "region"].filter(
      (k) => !groups.has(k),
    ),
  ];
  return (
    <section className="context-card">
      <span className="eyebrow">REVIEW CONTEXT</span>
      <h3>核对本次信息</h3>
      {important.map((q) => (
        <p key={q.id} className={q.required ? "text-error" : "muted"}>
          {q.required ? "需确认 · " : ""}
          {q.text}
        </p>
      ))}
      <p className="muted micro">
        金额与关键疑点需要二次确认。不知道的内容保留 Unknown，不替客户猜测。
      </p>
      {keys.map((key) => {
        const group = groups.get(key) || [],
          last = group.at(-1);
        const evidenceIds = replacementIds(
          facts,
          key,
          group.map((f) => f.id),
        );
        const evidenceFacts = facts.filter((f) => evidenceIds.includes(f.id));
        const raw = last
          ? isMoneyFact(key) && typeof last.value === "number"
            ? String(last.value / 100)
            : display(last.value)
          : "";
        return (
          <div className="fact-field" key={key}>
            <label htmlFor={`fact-${key}`}>
              {factLabels[key] || key}
              {isMoneyFact(key) ? "（元）" : ""}
              {group.some((f) => f.state === "conflict") && (
                <span className="tag warning">冲突</span>
              )}
            </label>
            {group.length > 0 && (
              <div className="source-notes">
                {evidenceFacts.map((f) => (
                  <p key={f.id}>
                    {f.scope === "historical" ? "历史参考 · " : ""}
                    {sourceLabels[f.source_kind] || f.source_kind}：
                    {isMoneyFact(key) ? money(f.value) : display(f.value)}
                  </p>
                ))}
              </div>
            )}
            <div className="row">
              <input
                id={`fact-${key}`}
                disabled={busy || unknown[key]}
                value={values[key] ?? raw}
                placeholder="本次值，可保留未知"
                onChange={(e) =>
                  setValues((v) => ({ ...v, [key]: e.target.value }))
                }
              />
              <button
                className={unknown[key] ? "selected" : "secondary"}
                disabled={busy}
                onClick={() => setUnknown((v) => ({ ...v, [key]: !v[key] }))}
              >
                {unknown[key] ? "已设未知" : "不知道"}
              </button>
            </div>
          </div>
        );
      })}
      {error && (
        <p role="alert" className="text-error">
          {error}
        </p>
      )}
      <button
        className="primary full"
        disabled={busy}
        onClick={() => void submit(false)}
      >
        确认本次信息
      </button>
      <button
        className="text-button full"
        disabled={busy}
        onClick={() => void submit(true)}
      >
        暂不补充可选问题，先准备报告
      </button>
    </section>
  );
}
