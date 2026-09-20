"""最小必要上下文投影。模型不接触客户联系方式及完整私人对话。"""
import json
from pathlib import Path
from typing import Any

from src.db.models import (
    Artifact,
    Capture,
    CRMExtraction,
    Customer,
    Draft,
    Fact,
    MockEvent,
    Question,
    Report,
    Run,
    Session,
)
from src.repositories.store import Store
from src.services.agent.submissions import question_read
from src.services.events import TOPICS
from src.services.facts import FACT_KEYS, current_facts, fact_read, trial_vehicle
from src.services.reports import safe_projection

PROMPTS = Path(__file__).resolve().parents[2] / 'prompts'


def prompt(name: str) -> str:
    return (PROMPTS / f'{name}.txt').read_text()


def as_data(value: Any) -> str:
    return json.dumps(safe_projection(value), ensure_ascii=False, default=str)


async def context_snapshot(store: Store, run: Run) -> dict[str, Any]:
    session = await store.require(Session, run.session_id)
    customer = await store.require(Customer, session.customer_id)
    facts = current_facts(await store.list(Fact, session_id=session.id))
    captures = await store.list(Capture, session_id=session.id, active=True)
    drafts = await store.list(Draft, session_id=session.id)
    artifacts = await store.list(Artifact, session_id=session.id)
    pending = await store.get(Run, session.pending_run_id) if session.pending_run_id else None
    events = await store.list(MockEvent, session_id=session.id)
    published = await store.list(Report, session_id=session.id)
    historical: list[dict[str, Any]] = []
    for old in await store.list(Session, customer_id=customer.id):
        if old.id != session.id and old.created_at < session.created_at:
            historical.extend({**fact_read(f), 'scope': 'historical'} for f in current_facts(
                await store.list(Fact, session_id=old.id)) if f.state == 'confirmed')
    for extracted in await store.list(CRMExtraction, customer_id=customer.id):
        historical.extend({**f, 'scope': 'historical'} for f in extracted.historical_facts)
    result = {'session_id': session.id, 'revision': session.revision, 'historical_facts': historical[-30:],
        'facts': [fact_read(f) for f in facts], 'trial_vehicle': trial_vehicle(facts),
        'captures': [{'id': c.id, 'payload': c.immutable_payload, 'validity': c.validity} for c in captures],
        'questions': [question_read(q) for q in await store.list(Question, session_id=session.id)
                      if q.state == 'open'], 'optional_questions_stopped': session.optional_questions_stopped,
        'drafts': [{'id': d.id, 'draft_revision': d.draft_revision, 'stale': d.stale,
                    'summary': d.report_data['summary']} for d in drafts[-3:]],
        'artifacts': [{'id': a.id, 'tool': a.tool_name, 'data': a.output, 'source_refs': a.source_refs}
                      for a in artifacts if a.source_revision == session.revision and a.status != 'stale'],
        'pending': {'run_id': pending.id, 'effective_intent': pending.effective_intent,
                    'original_goal': pending.checkpoint.get('original_goal')}
                   if pending and not pending.continued_by_run_id else None,
        'events': [{'id': e.id, 'topic': e.product_topic, 'safe_summary': e.safe_summary,
                    'resolution_evidence': e.resolution_evidence, 'source': 'mock'}
                   for e in events if e.product_topic in TOPICS],
        'published_report': published[-1].snapshot if published else None,
        'allowed_fact_keys': sorted(FACT_KEYS), 'goal': run.checkpoint.get('original_goal'),
        'submission': run.checkpoint.get('submission'), 'effective_intent': run.effective_intent}
    # safe_summary 是已白名单投影的产品事件；绝不读取 fixture 的原始私人内容。
    return safe_projection(result, phone=customer.normalized_phone, email=customer.normalized_email)
