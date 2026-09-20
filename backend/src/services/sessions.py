"""本次会话是客户下的独立工作单元，历史事实仅作参考。"""
from __future__ import annotations

from typing import Any

from src.config.settings import Settings
from src.db.models import (
    Artifact,
    Capture,
    CRMExtraction,
    Customer,
    Draft,
    Fact,
    Question,
    Report,
    Run,
    SalesInput,
    Session,
    TimelineMessage,
)
from src.models.contracts import SessionCreate
from src.repositories.store import Store
from src.services.captures import capture_read
from src.services.customers import contact_mask, page_slice
from src.services.facts import current_facts, fact_read, trial_vehicle


def draft_read(row: Draft) -> dict[str, Any]:
    return {key: getattr(row, key) for key in ("id", "session_id", "draft_revision",
        "source_revision", "customer_revision", "report_data", "blocking_issues", "requires_review", "stale")}


def report_summary(report: Report, session: Session, config: Settings) -> dict[str, Any]:
    return {"report_id": report.id, "session_id": session.id, "session_title": session.title,
            "title": "Model Y 试驾报告", "published_at": report.published_at,
            "url": config.report_origin.rstrip("/") + "/reports/" + report.id}


class SessionService:
    def __init__(self, store: Store, config: Settings):
        self.store, self.config = store, config

    async def create(self, data: SessionCreate) -> dict[str, Any]:
        customer = await self.store.require(Customer, str(data.customer_id))
        row = await self.store.add(Session(customer_id=customer.id, title=data.title,
            visit_at=data.visit_at.isoformat() if data.visit_at else None))
        return {key: getattr(row, key) for key in
                ("id", "customer_id", "title", "revision", "status", "created_at")}

    async def list(self, customer_id: str, cursor: str | None, limit: int) -> dict[str, Any]:
        await self.store.require(Customer, customer_id)
        rows = list(reversed(await self.store.list(Session, customer_id=customer_id)))
        page, next_cursor = page_slice(rows, cursor, limit)
        items: list[dict[str, Any]] = []
        for row in page:
            reports = await self.store.list(Report, session_id=row.id)
            items.append({"id": row.id, "title": row.title, "status": row.status,
                "created_at": row.created_at, "latest_report_id": reports[-1].id if reports else None})
        return {"items": items, "next_cursor": next_cursor}

    async def history(self, customer_id: str, cursor: str | None, limit: int) -> dict[str, Any]:
        await self.store.require(Customer, customer_id)
        items: list[dict[str, Any]] = []
        for row in await self.store.list(Session, customer_id=customer_id):
            items.extend(report_summary(r, row, self.config) for r in
                         await self.store.list(Report, session_id=row.id))
        items.sort(key=lambda x: (x["published_at"], x["report_id"]), reverse=True)
        page, next_cursor = page_slice(items, cursor, limit)
        return {"items": page, "next_cursor": next_cursor}

    async def detail(self, session_id: str) -> dict[str, Any]:
        session = await self.store.require(Session, session_id)
        customer = await self.store.require(Customer, session.customer_id)
        facts = await self.store.list(Fact, session_id=session_id)
        historical: list[dict[str, Any]] = []
        for old_session in await self.store.list(Session, customer_id=customer.id):
            if old_session.id != session_id and old_session.created_at < session.created_at:
                historical.extend(fact_read(row, historical=True) for row in current_facts(
                    await self.store.list(Fact, session_id=old_session.id)) if row.state == "confirmed")
        for extraction in await self.store.list(CRMExtraction, customer_id=customer.id):
            historical.extend({**fact, "scope": "historical"} for fact in extraction.historical_facts)
        runs = await self.store.list(Run, session_id=session_id)
        active = next((r for r in reversed(runs) if r.status in ("queued", "running")), None)
        pending = next((r for r in reversed(runs) if r.id == session.pending_run_id and
                        r.status == "needs_confirmation" and not r.continued_by_run_id), None)
        questions = await self.store.list(Question, session_id=session_id)
        question_data = [{key: getattr(q, key) for key in
            ("id", "text", "required", "fact_ids", "origin_run_id", "state")}
            for q in questions if q.state == "open"]
        question_data.sort(key=lambda q: not q["required"])
        drafts = await self.store.list(Draft, session_id=session_id)
        return {"id": session.id, "customer": {"id": customer.id, "nickname": customer.nickname,
                    "contact_mask": contact_mask(customer), "latest_session_id": session.id,
                    "revision": customer.revision, "phone": customer.normalized_phone,
                    "email": customer.normalized_email},
            "revision": session.revision, "status": session.status, "trial_vehicle": trial_vehicle(facts),
            "captures": [capture_read(x) for x in await self.store.list(Capture, session_id=session_id)],
            "inputs": [{key: getattr(x, key) for key in
                        ("id", "corrected_text", "asr_session_id", "source", "created_at")}
                       for x in await self.store.list(SalesInput, session_id=session_id)],
            "facts": [fact_read(x) for x in facts] + historical,
            "questions": question_data[:self.config.max_questions_per_round],
            "artifacts": [{key: getattr(x, key) for key in ("id", "session_id", "tool_name",
                "input_hash", "source_revision", "output", "status", "source_refs", "observed_at")}
                for x in await self.store.list(Artifact, session_id=session_id)],
            "active_run": {"run_id": active.id, "kind": active.kind, "status": active.status} if active else None,
            "pending_run": {"run_id": pending.id, "effective_intent": pending.effective_intent,
                "continuation": {"reason": pending.checkpoint.get("reason", "questions"),
                                 "can_continue": True, "continued_by_run_id": None},
                "questions": [q for q in question_data if q["origin_run_id"] == pending.id]
                } if pending else None,
            "draft": draft_read(drafts[-1]) if drafts else None,
            "reports": [report_summary(x, session, self.config) for x in
                        await self.store.list(Report, session_id=session_id)],
            "timeline": [{key: getattr(x, key) for key in
                ("id", "session_id", "seq", "role", "type", "source_ref", "content", "created_at")}
                for x in sorted(await self.store.list(TimelineMessage, session_id=session_id), key=lambda x: x.seq)],
            "followup": session.followup}
