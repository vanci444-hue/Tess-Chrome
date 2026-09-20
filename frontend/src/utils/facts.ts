import type { Fact, FactChange } from "../types/api";
/** Facts are append-only. Every consumer must project the non-superseded tips. */
export function currentFacts(facts: readonly Fact[]): Fact[] {
  const superseded = new Set(facts.flatMap((f) => f.supersedes));
  const tips = facts.filter((f) => !superseded.has(f.id));
  const sessionKeys = new Set(tips.filter((f) => f.scope !== "historical").map((f) => f.key));
  // 历史只作参考，已有本次值时不能覆盖本次确认或 Unknown。
  return tips.filter((f) => f.scope !== "historical" || !sessionKeys.has(f.key));
}
/** Include ancestors even when the UI currently displays only the latest proposal. */
export function replacementIds(
  facts: readonly Fact[],
  key: string,
  roots: readonly string[],
): string[] {
  const byId = new Map(facts.map((f) => [f.id, f])),
    seen = new Set<string>();
  const visit = (id: string) => {
    if (seen.has(id)) return;
    const fact = byId.get(id);
    if (fact && fact.key !== key) return;
    seen.add(id);
    fact?.supersedes.forEach(visit);
  };
  roots.forEach(visit);
  return [...seen];
}
/** 历史引用属于另一会话，确认时新增本次事实，不跨会话 supersede。 */
export function confirmationReferences(facts: readonly Fact[], group: readonly Fact[]) {
  const last = group.at(-1);
  const sessionFacts = facts.filter((f) => f.scope !== "historical");
  return {
    fact_id: last?.scope === "historical" ? undefined : last?.id,
    supersedes: replacementIds(sessionFacts, last?.key || "", group
      .filter((f) => f.scope !== "historical").map((f) => f.id)),
  };
}
/** Shared by the contract transport; no fact is deleted or rewritten on correction. */
export function appendConfirmation(
  facts: readonly Fact[],
  change: FactChange,
  meta: { id: string; sourceId: string; observedAt: string },
): Fact[] {
  const old = facts.find((f) => f.id === change.fact_id);
  const supersedes = replacementIds(facts, change.key, [
    ...change.supersedes,
    ...(change.fact_id ? [change.fact_id] : []),
  ]);
  return [
    ...facts,
    {
      id: meta.id,
      key: change.key,
      value: change.state === "unknown" ? null : change.value,
      unit: old?.unit || null,
      state: change.state,
      source_kind: "sales_input",
      source_id: meta.sourceId,
      observed_at: meta.observedAt,
      scope: "session",
      subject_id: null,
      evidence_note: change.evidence_note,
      supersedes,
    },
  ];
}
/** Report assertions and rendering use this same projection, never the historical log. */
export function reportFacts(facts: readonly Fact[]): Fact[] {
  return currentFacts(facts).filter(
    (f) => f.scope !== "historical" && f.state === "confirmed",
  );
}
