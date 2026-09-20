"""模拟事件只允许购车主题，私人对话在模型前即排除。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config.settings import Settings
from src.db.models import MockEvent, Report
from src.models.contracts import BusinessError, EventInject
from src.repositories.store import Store

FIXTURES = {"family-charging-followup", "family-rear-seat-followup", "budget-followup"}
TOPICS = {"charging", "rear_seat", "finance", "vehicle", "safety", "energy", "delivery"}


class EventService:
    def __init__(self, store: Store, config: Settings):
        self.store, self.config = store, config

    async def inject(self, session_id: str, data: EventInject) -> dict[str, Any]:
        session = await self.store.check_revision(session_id, data.expected_revision)
        if data.fixture_id not in FIXTURES:
            raise BusinessError("没有此演示事件集", "UNKNOWN_FIXTURE", 400, "VALIDATION_ERROR")
        if not await self.store.list(Report, session_id=session_id):
            raise BusinessError("请先发布本次报告", "REPORT_NOT_FOUND", 404, "NOT_FOUND")
        path = Path(__file__).resolve().parents[1] / "fixtures" / "events" / (data.fixture_id + ".json")
        ids = []
        for item in json.loads(path.read_text()):
            if item["topic"] not in TOPICS:
                continue
            row = await self.store.add(MockEvent(session_id=session_id, fixture_id=data.fixture_id,
                product_topic=item["topic"], safe_summary=item["safe_summary"],
                resolution_evidence=item.get("resolution_evidence")))
            ids.append(row.id)
        await self.store.bump(session)
        return {"event_ids": ids, "source": "mock", "revision": session.revision}
