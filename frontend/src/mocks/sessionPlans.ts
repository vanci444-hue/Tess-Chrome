import type { Capture } from "../types/api";

export type AppliedPlan = {
  id: string;
  optionNumber: number;
  versionTag: string;
  planId: "A" | "B";
  note: string;
  capture: Capture;
  appliedAt: string;
};

function storageKey(sessionId: string) {
  return `tess.session-plans.v1.${sessionId}`;
}

export function loadAppliedPlans(sessionId: string): AppliedPlan[] {
  try {
    const raw = localStorage.getItem(storageKey(sessionId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as AppliedPlan[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveAppliedPlan(sessionId: string, plan: AppliedPlan) {
  const current = loadAppliedPlans(sessionId).filter(
    (item) => item.optionNumber !== plan.optionNumber,
  );
  current.push(plan);
  current.sort((a, b) => a.optionNumber - b.optionNumber);
  localStorage.setItem(storageKey(sessionId), JSON.stringify(current));
}

export function clearAppliedPlans(sessionId: string) {
  localStorage.removeItem(storageKey(sessionId));
}

/** 当前工作候选：已应用的 V1 会替代对应 Option */
export function mergeWorkingOptions(
  activeCaptures: Capture[],
  plans: AppliedPlan[],
): {
  optionNumber: number;
  versionTag?: string;
  capture: Capture;
  replaced: boolean;
  planId?: "A" | "B";
}[] {
  const byOption = new Map(
    plans.map((plan) => [plan.optionNumber, plan] as const),
  );
  return activeCaptures.map((capture, index) => {
    const optionNumber = index + 1;
    const applied = byOption.get(optionNumber);
    if (!applied) {
      return { optionNumber, capture, replaced: false };
    }
    return {
      optionNumber,
      versionTag: applied.versionTag,
      capture: applied.capture,
      replaced: true,
      planId: applied.planId,
    };
  });
}
