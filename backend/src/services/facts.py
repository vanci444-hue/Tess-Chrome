"""事实采用追加记录；每次确认都保留被替代来源。"""
from __future__ import annotations

import re
from typing import Any

from src.config.settings import Settings
from src.db.models import Fact, LocationCandidate, Question, Run
from src.models.contracts import BusinessError, ContextUpdate
from src.repositories.store import Store

FACT_KEYS = frozenset("monthly_budget down_payment_budget max_down_payment term_months annual_mileage "
    "holding_years electricity_price fuel_price fuel_consumption energy_consumption home_charging "
    "has_fixed_parking region city confirmed_location_ref daily_commute trial_model trial_variant "
    "trial_vehicle feedback family_context concerns resolved_concerns preference confirmed_findings "
    "pending_items charging_ratio desired_monthly_payment desired_down_payment".split())
MONEY_FACTS = frozenset("monthly_budget down_payment_budget max_down_payment desired_monthly_payment "
                       "desired_down_payment".split())


def fact_read(row: Fact, historical: bool = False) -> dict[str, Any]:
    return {"id": row.id, "key": row.key, "value": row.value, "unit": row.unit,
            "state": row.state, "source_kind": row.source_kind, "source_id": row.source_id,
            "observed_at": row.observed_at, "scope": "historical" if historical else row.scope,
            "subject_id": row.subject_id, "evidence_note": row.evidence_note,
            "supersedes": row.supersedes}


def current_facts(rows: list[Fact]) -> list[Fact]:
    superseded = {ref for row in rows for ref in row.supersedes}
    return [row for row in rows if row.id not in superseded and row.scope == "session"]


def blocking_facts(rows: list[Fact]) -> list[dict[str, Any]]:
    current = current_facts(rows)
    issues = []
    for row in current:
        if row.state == "conflict":
            issues.append({"code": "UNRESOLVED_FACT", "field": row.key, "blocking": True,
                           "message": "请确认存在冲突的" + row.key})
    grouped: dict[str, list[Any]] = {}
    for row in current:
        if row.state == "confirmed":
            grouped.setdefault(row.key, []).append(row.value)
    for key, values in grouped.items():
        if any(value != values[0] for value in values[1:]):
            issues.append({"code": "UNRESOLVED_FACT", "field": key, "blocking": True,
                           "message": "同一字段仍存在不同的已确认值，请明确替代关系"})
    return issues


UNKNOWN_SUPPORT = {
    "home_charging": "补充家充条件后，可以判断是否需要查询周边超充，以及能否做家庭充电成本对照。",
    "has_fixed_parking": "补充固定车位情况后，可以判断是否需要查询公共超充与驾车距离。",
    "region": "补充常用区域后，可以通过高德查询真实充电站、驾车距离和带编号地图。",
    "city": "补充城市后，可以缩小同名地点并查询该区域充电站。",
    "trial_variant": "补充实际试驾版本后，体验反馈会正确归属，不会沿用候选配置。",
    "monthly_budget": "补充月供预算后，可以用已确认规则试算可行首付与期限。",
    "desired_monthly_payment": "补充期望月供后，可以用已确认规则试算可行方案。",
}


def unknown_support(rows: list[Any]) -> list[dict[str, str]]:
    messages, seen = [], set()
    for row in current_projection(rows):
        if row["state"] != "unknown" or row["key"] in seen or row["key"] not in UNKNOWN_SUPPORT:
            continue
        seen.add(row["key"])
        messages.append({"key": row["key"], "message": UNKNOWN_SUPPORT[row["key"]]})
    return messages


def current_projection(rows: list[Any]) -> list[dict[str, Any]]:
    if not rows:
        return []
    if hasattr(rows[0], "key"):
        return [fact_read(row) for row in current_facts(rows)]
    superseded = {ref for row in rows for ref in row.get("supersedes") or []}
    return [row for row in rows if row.get("id") not in superseded and row.get("scope", "session") == "session"]


def _charge_flag(value: Any, *, unknown: bool) -> str:
    if unknown or value is None:
        return "unknown"
    if value is True:
        return "yes"
    if value is False:
        return "no"
    text = str(value).strip()
    negative = bool(re.search(r"无|没有|否|不便|不能|未知|unknown", text, re.I))
    positive = bool(re.search(r"有|已装|安装|家充|可以|具备|固定车位|true|yes", text, re.I))
    if negative:
        return "no"
    if positive:
        return "yes"
    return "unknown"


def charging_search_needed(rows: list[Any]) -> bool:
    """无车位或家充未知/不具备时，在已确认地点查询超充；家充与车位都明确具备则跳过。"""
    facts = current_projection(rows)
    confirmed = {row["key"]: row["value"] for row in facts if row["state"] == "confirmed"}
    unknown = {row["key"] for row in facts if row["state"] == "unknown"}
    if not (confirmed.get("confirmed_location_ref") or confirmed.get("region")):
        return False
    parking = _charge_flag(confirmed.get("has_fixed_parking"), unknown="has_fixed_parking" in unknown)
    home = _charge_flag(confirmed.get("home_charging"), unknown="home_charging" in unknown)
    if "has_fixed_parking" not in confirmed and "has_fixed_parking" not in unknown:
        parking = "unknown"
    if "home_charging" not in confirmed and "home_charging" not in unknown:
        home = "unknown"
    return not (parking == "yes" and home == "yes")


def trial_vehicle(rows: list[Fact]) -> dict[str, Any] | None:
    facts = {r.key: r for r in current_facts(rows) if r.state == "confirmed"}
    if "trial_vehicle" in facts and isinstance(facts["trial_vehicle"].value, dict):
        value = facts["trial_vehicle"].value
        return {"model": value.get("model", "Model Y"), "variant": value.get("variant"),
                "source_fact_ids": [facts["trial_vehicle"].id]}
    if "trial_model" not in facts and "trial_variant" not in facts:
        return None
    return {"model": facts["trial_model"].value if "trial_model" in facts else "Model Y",
            "variant": facts["trial_variant"].value if "trial_variant" in facts else None,
            "source_fact_ids": [facts[k].id for k in ("trial_model", "trial_variant") if k in facts]}


class FactService:
    def __init__(self, store: Store, config: Settings):
        self.store, self.config = store, config

    async def update(self, session_id: str, data: ContextUpdate) -> dict[str, Any]:
        session = await self.store.check_revision(session_id, data.expected_revision)
        parent = None
        if data.reply_to_run_id:
            parent = await self.store.require(Run, str(data.reply_to_run_id), session_id)
            if parent.status != "needs_confirmation" or parent.continued_by_run_id:
                raise BusinessError("该确认记录已失效", "INVALID_CONTINUATION")
        for question_id in data.reply_to_question_ids:
            question = await self.store.require(Question, str(question_id), session_id)
            if not parent or question.origin_run_id != parent.id or question.state != "open":
                raise BusinessError("追问引用与当前处理记录不一致", "INVALID_QUESTION", 400,
                                    "VALIDATION_ERROR")
        resolved_ids = set()
        for change in data.changes:
            if change.key not in FACT_KEYS:
                raise BusinessError("此字段不可通过 Context 修改", "READONLY_CONTEXT", 400,
                                    "VALIDATION_ERROR")
            if change.state == "confirmed" and change.value is None:
                raise BusinessError("未知信息请选择不知道", "UNKNOWN_VALUE", 400, "VALIDATION_ERROR")
            if change.key in MONEY_FACTS and change.state == "confirmed" and (
                    type(change.value) is not int or change.value < 0):
                raise BusinessError("预算必须使用非负整数分", "INVALID_MONEY", 400, "VALIDATION_ERROR")
            refs = list(dict.fromkeys([str(x) for x in change.supersedes] +
                                     ([str(change.fact_id)] if change.fact_id else [])))
            for ref in refs:
                previous = await self.store.require(Fact, ref, session_id)
                if previous.key != change.key:
                    raise BusinessError("不能替代其他字段的事实", "INVALID_SUPERSEDES", 400,
                                        "VALIDATION_ERROR")
            if change.key == "confirmed_location_ref" and change.state == "confirmed":
                await self.store.require(LocationCandidate, str(change.value), session_id)
            if change.key == "resolved_concerns" and not change.evidence_note:
                raise BusinessError("顾虑解决需要明确确认依据", "RESOLUTION_EVIDENCE_REQUIRED", 400,
                                    "VALIDATION_ERROR")
            await self.store.add(Fact(session_id=session_id, key=change.key,
                value=None if change.state == "unknown" else change.value,
                unit="CNY_fen" if change.key in MONEY_FACTS else None,
                state=change.state, source_kind="sales_input", source_id=session_id,
                scope="session", evidence_note=change.evidence_note, supersedes=refs))
            resolved_ids.update(refs)
        for question in await self.store.list(Question, session_id=session_id):
            if question.state != "open":
                continue
            if question.id in {str(x) for x in data.reply_to_question_ids} or (
                    question.fact_ids and set(question.fact_ids) <= resolved_ids):
                question.state = "unknown" if any(c.state == "unknown" for c in data.changes) else "answered"
            elif data.skip_optional_questions and not question.required:
                question.state = "unknown"
        session.optional_questions_stopped |= data.skip_optional_questions
        invalidated = await self.store.bump(session)
        issues = blocking_facts(await self.store.list(Fact, session_id=session_id))
        hint = None
        if parent:
            hint = {"parent_run_id": parent.id, "effective_intent": parent.effective_intent,
                    "expected_revision": session.revision,
                    "continue_via": "API-012" if parent.effective_intent in
                    ("analyze", "prepare_report", "followup") else "API-021"}
        return {"revision": session.revision, "blocking_issues": issues,
                "invalidated_artifact_ids": invalidated,
                "optional_questions_stopped": session.optional_questions_stopped,
                "continuation_hint": hint}
