"""所有入口共用一次接收事务，绝不在这个事务调用模型。"""
from typing import Any

from src.db.models import ASRSession, Draft, Question, Run, SalesInput, Session, new_id
from src.models.contracts import BusinessError
from src.repositories.store import Store, digest
from src.services.agent.contracts import Submission


def question_read(q: Question) -> dict[str, Any]:
    return {k: getattr(q, k) for k in
            ('id', 'text', 'required', 'fact_ids', 'origin_run_id', 'state')}


async def attach_parent(store: Store, run: Run, parent: Run) -> None:
    """调用方持有单进程写锁；DB active-run唯一索引为第二道保护。"""
    if parent.status != 'needs_confirmation' or parent.checkpoint.get('superseded'):
        raise BusinessError('原任务已结束或被替代', 'INVALID_CONTINUATION')
    if parent.continued_by_run_id and parent.continued_by_run_id != run.id:
        raise BusinessError('该追问已有新的处理记录，请刷新后继续', 'CONTINUATION_CONSUMED',
                            current_run_id=parent.continued_by_run_id)
    parent.continued_by_run_id = run.id
    run.parent_run_id, run.root_run_id = parent.id, parent.root_run_id
    run.effective_intent = parent.effective_intent
    run.checkpoint = {**run.checkpoint, 'original_goal': parent.checkpoint.get('original_goal'),
                      'parent_questions': parent.checkpoint.get('question_ids', []),
                      'target_draft_id': parent.checkpoint.get('target_draft_id') or
                          parent.checkpoint.get('submission', {}).get('target_draft_id'),
                      'target_draft_revision': parent.checkpoint.get('target_draft_revision') or
                          parent.checkpoint.get('submission', {}).get('target_draft_revision')}
    # 未回答的问题移交给child，不删除问题，也不丢未覆盖的required项。
    for q in await store.list(Question, session_id=run.session_id, origin_run_id=parent.id):
        if q.state == 'open':
            q.origin_run_id = run.id


async def accept_submission(store: Store, session_id: str, data: Submission, key: str,
                            kind: str, *, has_text: bool = True) -> dict[str, Any]:
    body = {'kind': kind, **data.model_dump(mode='json'), 'has_text': has_text}

    async def action():
        await store.check_revision(session_id, data.expected_revision)
        if any(r.status in ('queued', 'running') for r in await store.list(Run, session_id=session_id)):
            raise BusinessError('当前会话正在处理，请等待结果', 'RUN_ACTIVE')
        if data.asr_session_id:
            await store.require(ASRSession, str(data.asr_session_id), session_id)
        if data.target_draft_id:
            draft = await store.require(Draft, str(data.target_draft_id), session_id)
            if draft.draft_revision != data.target_draft_revision or draft.stale:
                raise BusinessError('草稿已过期，请重新查看', 'STALE_DRAFT')
        parent_id = data.reply_to_run_id or data.continue_run_id
        parent = await store.require(Run, str(parent_id), session_id) if parent_id else None
        if parent:
            if parent.status != 'needs_confirmation' or parent.checkpoint.get('superseded'):
                raise BusinessError('该记录不可继续', 'INVALID_CONTINUATION')
            if parent.continued_by_run_id:
                raise BusinessError('该追问已有新的处理记录，请刷新后继续', 'CONTINUATION_CONSUMED',
                                    current_run_id=parent.continued_by_run_id)
            if kind in ('analyze', 'prepare_report', 'followup') and parent.effective_intent != kind:
                raise BusinessError('继续目标与原任务不一致', 'INTENT_MISMATCH', 400, 'VALIDATION_ERROR')
            for qid in data.reply_to_question_ids:
                q = await store.require(Question, str(qid), session_id)
                if q.origin_run_id != parent.id or q.state != 'open':
                    raise BusinessError('问题不属于当前待答组', 'INVALID_QUESTION', 400, 'VALIDATION_ERROR')
        run_id = new_id()
        source_id = None
        if has_text:
            entry = await store.add(SalesInput(session_id=session_id, corrected_text=data.text,
                source=data.source, asr_session_id=str(data.asr_session_id) if data.asr_session_id else None))
            message = await store.timeline(session_id, 'text', 'sales', {'text': data.text},
                                           {'kind': 'input', 'id': entry.id})
            source_id = message.id
        checkpoint = {'submission': data.model_dump(mode='json'), 'has_text': has_text,
                      'original_goal': data.text, 'artifact_ids': [], 'question_ids': []}
        run = await store.add(Run(id=run_id, session_id=session_id, kind=kind,
            effective_intent=None if kind == 'interaction' else kind, source_message_id=source_id,
            root_run_id=run_id, input_revision=data.expected_revision,
            current_revision=data.expected_revision, checkpoint=checkpoint,
            idempotency_key=key, body_hash=digest(body)))
        if parent:
            await attach_parent(store, run, parent)
        return {'message_id': source_id, 'run_id': run.id, 'session_id': session_id,
                'status': 'queued', 'kind': kind}

    return await store.idempotent(key, f'submission:{session_id}', body, action)


async def read_run(store: Store, session_id: str, run_id: str, after_seq: int = 0) -> dict[str, Any]:
    from src.db.models import RunEvent
    await store.require(Session, session_id)
    run = await store.require(Run, run_id, session_id)
    events = await store.list(RunEvent, run_id=run_id)
    continuation = None
    if run.status == 'needs_confirmation':
        continuation = {'reason': run.checkpoint.get('reason', 'questions'),
            'can_continue': not run.continued_by_run_id and not run.checkpoint.get('superseded', False),
            'continued_by_run_id': run.continued_by_run_id}
    return {'run_id': run.id, 'session_id': session_id, 'status': run.status,
        'events': [{k: getattr(e, k) for k in ('seq', 'type', 'label', 'tool_name', 'artifact_id')}
                   for e in sorted(events, key=lambda e: e.seq) if e.seq > after_seq],
        'last_seq': max((e.seq for e in events), default=0), 'result': run.result, 'error': run.error,
        'lineage': {'parent_run_id': run.parent_run_id, 'root_run_id': run.root_run_id,
                    'effective_intent': run.effective_intent}, 'continuation': continuation}
