import { strict as assert } from "node:assert";
import { test } from "node:test";
import type { Fact, FactChange } from "../types/api.ts";
import {
  currentFacts,
  confirmationReferences,
  replacementIds,
  appendConfirmation,
  reportFacts,
} from "./facts.ts";
const initial: Fact = {
  id: "budget-4000",
  key: "monthly_budget",
  value: 400000,
  unit: "CNY_fen",
  state: "confirmed",
  source_kind: "sales_input",
  source_id: "old-input",
  observed_at: "2026-09-20T00:00:00Z",
  scope: "session",
  subject_id: null,
  evidence_note: "销售确认",
  supersedes: [],
};
const conflict = (id: string, value: number, supersedes: string[]): Fact => ({
  ...initial,
  id,
  value,
  state: "conflict",
  source_kind: "mock",
  supersedes,
});
const confirm = (
  facts: Fact[],
  id: string,
  value: number | null,
  state: "confirmed" | "unknown",
  newId: string,
) => {
  const change: FactChange = {
    fact_id: id,
    key: "monthly_budget",
    value,
    state,
    supersedes: replacementIds(
      facts,
      "monthly_budget",
      currentFacts(facts).map((f) => f.id),
    ),
    evidence_note: "已人工核对",
  };
  return {
    change,
    facts: appendConfirmation(facts, change, {
      id: newId,
      sourceId: "manual",
      observedAt: "2026-09-20T01:00:00Z",
    }),
  };
};
test("4000 → 8000 conflict → explicit 8001 retains original evidence but reports only 8001", () => {
  const facts = [initial, conflict("budget-8000", 800000, ["budget-4000"])],
    before = structuredClone(facts);
  const result = confirm(
    facts,
    "budget-8000",
    800100,
    "confirmed",
    "budget-8001",
  );
  assert.deepEqual(result.change.supersedes, ["budget-8000", "budget-4000"]);
  assert.equal(result.facts.length, 3);
  assert.deepEqual(result.facts.slice(0, 2), before);
  assert.deepEqual(
    currentFacts(result.facts).map((f) => f.value),
    [800100],
  );
  assert.deepEqual(
    reportFacts(result.facts).map((f) => f.value),
    [800100],
  );
  assert.deepEqual(facts, before);
});
test("successive corrections and Unknown never resurrect superseded budgets", () => {
  const facts = confirm(
    [initial, conflict("p1", 800000, [initial.id])],
    "p1",
    800100,
    "confirmed",
    "c1",
  ).facts;
  facts.push(conflict("p2", 900000, ["c1"]));
  const second = confirm(facts, "p2", 900100, "confirmed", "c2");
  assert.deepEqual(
    new Set(second.change.supersedes),
    new Set(["p2", "c1", "p1", initial.id]),
  );
  assert.deepEqual(
    reportFacts(second.facts).map((f) => f.value),
    [900100],
  );
  const unknown = confirm(second.facts, "c2", null, "unknown", "u1").facts;
  assert.deepEqual(
    currentFacts(unknown).map((f) => [f.state, f.value]),
    [["unknown", null]],
  );
  assert.equal(reportFacts(unknown).length, 0);
  assert.equal(unknown.length, 6);
  const restored = confirm(unknown, "u1", 350000, "confirmed", "c3").facts;
  assert.deepEqual(
    reportFacts(restored).map((f) => f.value),
    [350000],
  );
  assert.equal(restored.find((f) => f.id === initial.id)?.value, 400000);
});
test("historical references never become current report conclusions without a session confirmation", () => {
  assert.deepEqual(reportFacts([{ ...initial, scope: "historical" }]), []);
});

test("history confirmation creates local fact; current Unknown wins over old history", () => {
  const historical: Fact = { ...initial, id: "history", scope: "historical" };
  assert.deepEqual(confirmationReferences([historical], [historical]), { fact_id: undefined, supersedes: [] });
  const local: Fact = { ...initial, id: "current", value: null, state: "unknown" };
  assert.deepEqual(currentFacts([local, historical]), [local]);
  assert.deepEqual(confirmationReferences([local, historical], [local]), { fact_id: "current", supersedes: ["current"] });
});
