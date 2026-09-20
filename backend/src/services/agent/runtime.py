"""有界单进程 Agent：事务只用于读取/写回，模型与工具等待始终在锁外。"""
from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from src.db.models import Artifact, Draft, Fact, Question, Run, RunEvent, Session, utcnow
from src.models.contracts import BusinessError, DraftUpdate
from src.repositories.store import Store, digest
from src.services.agent.context import as_data, context_snapshot, prompt
from src.services.agent.contracts import Extraction, Finish, RouteDecision, SuggestedQuestion
from src.services.agent.submissions import attach_parent, question_read
from src.services.facts import (
    FACT_KEYS, MONEY_FACTS, blocking_facts, charging_search_needed, current_facts,
    unknown_support,
)
from src.services.reports import ReportService, safe_projection

from pycore.core import get_logger

logger = get_logger()
T = TypeVar('T', bound=BaseModel)


class LimitReached(Exception):
    pass


class InputsChanged(Exception):
    pass


class InvalidModelOutput(Exception):
    pass


LOCAL_SCHEMAS = [
    {'type': 'function', 'function': {'name': 'read_session', 'description': '读取当前会话可信上下文',
      'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}},
    {'type': 'function', 'function': {'name': 'validate_report', 'description': '校验本次草稿来源与阻塞项，不发布',
      'parameters': {'type': 'object', 'properties': {'draft_section_refs':
                     {'type': 'array', 'items': {'type': 'string'}}}, 'additionalProperties': False}}},
]


class AgentRunner:
    def __init__(self, app: Any, provider: Any = None, registry: Any = None):
        self.app, self.config = app, app.state.settings
        # 生产默认只能真实适配器；测试在构造时显式注入协议替身。
        injected_provider = provider
        if provider is None:
            from src.adapters.llm import BailianLLMProvider
            provider = BailianLLMProvider(self.config)
        if registry is None:
            from src.tools.registry import ToolRegistry
            registry = ToolRegistry(self.config)
        self.provider, self.registry = provider, registry
        self.injected_provider = injected_provider
        self.tasks: dict[str, asyncio.Task] = {}

    def schedule(self, run_id: str) -> None:
        if run_id not in self.tasks:
            task = asyncio.create_task(self.execute(run_id), name=f'tess-run-{run_id}')
            self.tasks[run_id] = task
            task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    @asynccontextmanager
    async def transaction(self, run_id: str, *, check: bool = True):
        async with self.app.state.write_lock:
            async with self.app.state.session_factory() as db:
                store = Store(db)
                run = await store.require(Run, run_id)
                session = await store.require(Session, run.session_id)
                if check and run.current_revision != session.revision:
                    raise InputsChanged()
                try:
                    yield store, run, session
                    await db.commit()
                except BaseException:
                    await db.rollback()
                    raise

    async def snapshot(self, run_id: str) -> dict[str, Any]:
        async with self.transaction(run_id) as (store, run, _):
            return await context_snapshot(store, run)

    async def event(self, store: Store, run: Run, type_: str, label: str,
                    tool: str | None = None, artifact: str | None = None):
        events = await store.list(RunEvent, run_id=run.id)
        await store.add(RunEvent(run_id=run.id, seq=max((e.seq for e in events), default=0) + 1,
            type=type_, label=label, tool_name=tool, artifact_id=artifact))

    async def execute(self, run_id: str) -> None:
        budget: dict[str, Any] = {'rounds': 0, 'tools': 0, 'repair': 0, 'failed_adjustments': 0}
        if self.injected_provider is None:
            from src.adapters.llm import BailianLLMProvider
            budget['provider'] = BailianLLMProvider(self.config)
        else:
            budget['provider'] = self.injected_provider
        try:
            async with self.transaction(run_id) as (store, run, _):
                if run.status != 'queued':
                    return
                run.status, run.started_at = 'running', utcnow()
                await self.event(store, run, 'started', '正在处理已提交的信息')
            async with asyncio.timeout(self.config.run_timeout):
                await self.work(run_id, budget)
        except (LimitReached, TimeoutError):
            await self.stop(run_id, 'limit_reached', '本次处理达到保护上限，请明确继续', partial=True)
        except InputsChanged:
            await self.stop(run_id, 'inputs_changed', '信息已更新，请基于最新信息继续', partial=True)
        except asyncio.CancelledError:
            await self.fail(run_id, 'INTERRUPTED', '处理已中断，请明确重新开始', interrupted=True)
            raise
        except Exception as error:
            # 依赖/格式/内部错误均显式失败；日志只含异常类型和运行ID。
            code = getattr(error, 'code', 'INVALID_MODEL_OUTPUT' if isinstance(error,
                     (InvalidModelOutput, ValidationError)) else 'AGENT_FAILED')
            if isinstance(error, BusinessError):
                code = error.details.get('reason', error.code)
            logger.error('Agent处理失败', run_id=run_id, error_type=type(error).__name__, code=code)
            await self.fail(run_id, code, '处理未完成；已提交文字仍已保存，请检查配置或重试')

    async def call(self, run_id: str, budget: dict[str, Any], messages: list[dict[str, Any]],
                   *, tools: list[dict[str, Any]] | None = None, structured: bool = False):
        await self.snapshot(run_id)  # 每次外部调用前核对归属修订，不持锁等待。
        if budget['rounds'] >= self.config.max_model_rounds:
            raise LimitReached()
        budget['rounds'] += 1
        response = await budget['provider'].complete(messages, tools=tools,
            response_format={'type': 'json_object'} if structured else None)
        metadata = getattr(budget['provider'], 'last_response_metadata', {})
        if metadata:
            async with self.transaction(run_id) as (_, run, _session):
                run.checkpoint = {**run.checkpoint, 'model_response':
                    {k: metadata.get(k) for k in ('model', 'id', 'usage')}}
        return response

    async def structured(self, run_id: str, budget: dict[str, Any], messages: list[dict[str, Any]],
                         schema: type[T]) -> T:
        messages = [*messages, {'role': 'user', 'content': '严格使用此JSON Schema: ' +
                    json.dumps(schema.model_json_schema(), ensure_ascii=False)}]
        for attempt in range(2):
            response = await self.call(run_id, budget, messages, structured=True)
            try:
                return schema.model_validate_json(response.get('content') or '')
            except (ValueError, ValidationError) as error:
                if attempt or budget['repair']:
                    raise InvalidModelOutput() from error
                budget['repair'] += 1
                # 不回传包含敏感原值的验证异常，也不存模型思维链。
                messages = [*messages, {'role': 'user', 'content':
                    '输出不符合JSON契约。只返回所要求的JSON字段，不添加Markdown；修复一次。Schema: '
                    + json.dumps(schema.model_json_schema(), ensure_ascii=False)}]
        raise InvalidModelOutput()

    async def work(self, run_id: str, budget: dict[str, Any]) -> None:
        snapshot = await self.snapshot(run_id)
        async with self.transaction(run_id) as (_, run, _session):
            intent, kind = run.effective_intent, run.kind
            submission = run.checkpoint['submission']
            has_text = run.checkpoint['has_text']
            parent_id = run.parent_run_id
        if parent_id and not intent and submission['text'].strip('。！! ') in ('继续', '重试', '是的', '好的', '嗯', '继续原任务'):
            questions = [SuggestedQuestion(text=q['text'], required=q['required'], fact_ids=q['fact_ids'])
                         for q in snapshot['questions'] if q['origin_run_id'] == run_id]
            await self.ask(run_id, questions or [SuggestedQuestion(text='请明确要处理的目标，不能只回复继续。')],
                           reason='route_ambiguity')
            return
        if parent_id and submission.get('reply_to_run_id') and re.search(r'换个问题|另起任务|重新开始任务', submission['text']):
            await self.ask(run_id, [SuggestedQuestion(text='请确认继续原任务，还是开始新的问题。')],
                           reason='route_ambiguity')
            return
        needs_extract = kind in ('extract_context', 'edit_draft') or bool(submission.get('reply_to_run_id'))
        if kind == 'interaction' and not (parent_id and intent):
            route = await self.structured(run_id, budget, [
                {'role': 'system', 'content': prompt('route')},
                {'role': 'user', 'content': as_data(snapshot)}], RouteDecision)
            intent = await self.apply_route(run_id, route)
            needs_extract |= route.intent in ('supplement_facts', 'answer_question', 'prepare_report', 'edit_draft')
            if route.intent == 'clarify' or intent is None:
                await self.ask(run_id, [SuggestedQuestion(text=route.clarification or
                    '请说明是补充信息、询问问题，还是生成报告。')], reason='route_ambiguity')
                return
        if intent == 'prepare_report' and has_text and not submission.get('continue_run_id'):
            needs_extract = True
        if needs_extract:
            try:
                output = await self.structured(run_id, budget, [
                    {'role': 'system', 'content': prompt('context_extract')},
                    {'role': 'user', 'content': as_data(await self.snapshot(run_id))}], Extraction)
            except InvalidModelOutput:
                # 已提交文字已入库；契约失败时保留 Unknown 并说明补充能支持什么，不丢输入。
                output = Extraction()
            fact_ids, questions = await self.save_extraction(run_id, output)
            support = await self.unknown_support_for(run_id)
            if questions:
                await self.ask(run_id, questions)
                return
            if intent in ('extract_context', 'supplement_facts'):
                await self.finish(run_id, {'outcome': 'context', 'status': 'ready',
                                          'proposed_fact_ids': fact_ids, 'questions': [],
                                          'unknown_support': support})
                return
        # 关键冲突与required未回答项优先；Unknown不变成零且不反复问。
        required = await self.required_questions(run_id) if intent not in ('qa', 'followup') else []
        if required:
            await self.ask(run_id, required)
            return
        if intent in ('extract_context', 'supplement_facts'):
            await self.finish(run_id, {'outcome': 'context', 'status': 'ready',
                                      'proposed_fact_ids': [], 'questions': [],
                                      'unknown_support': await self.unknown_support_for(run_id)})
            return
        snapshot = await self.snapshot(run_id)
        if intent == 'followup':
            await self.complete_output(run_id, await self.finish_followup(run_id, budget, snapshot))
            return
        system = prompt('agent')
        messages: list[dict[str, Any]] = [{'role': 'system', 'content': system},
                                         {'role': 'user', 'content': as_data(snapshot)}]
        schemas = [*self.registry.schemas(), *LOCAL_SCHEMAS]
        failed_hashes: set[str] = set()
        while True:
            response = await self.call(run_id, budget, messages, tools=schemas)
            calls = response.get('tool_calls') or []
            if not calls:
                break
            if len(calls) > self.config.max_tool_calls - budget['tools']:
                raise LimitReached()
            messages.append({'role': 'assistant', 'content': response.get('content'), 'tool_calls': calls})
            for call in calls:
                budget['tools'] += 1
                observation = await self.tool(run_id, call, failed_hashes)
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': as_data(observation)})
            observations = [json.loads(m['content']) for m in messages[-len(calls):]]
            round_failed = any(item.get('status') == 'failed' for item in observations)
            round_ok = any(item.get('status') in ('ok', 'partial') for item in observations)
            if round_failed and not round_ok:
                budget['failed_adjustments'] += 1
                # 留一次根据失败观察调整策略的模型回合；已有成功观察则继续必要检查。
                if budget['failed_adjustments'] > 1:
                    if intent == 'prepare_report':
                        break
                    raise LimitReached()
        await self.ensure_prepare_tools(run_id, failed_hashes)
        messages.append({'role': 'user', 'content': prompt('report') +
            '\n当前目标=' + str(intent) + '。只能完成该目标；qa/analyze不能生成报告。'})
        finished = await self.structured(run_id, budget, messages, Finish)
        if intent in ('prepare_report', 'edit_draft') and self.summary_has_numbers(finished):
            if budget['rounds'] < self.config.max_model_rounds:
                try:
                    retried = await self.structured(run_id, budget, [
                        *messages,
                        {'role': 'user', 'content':
                         '定性摘要不得含阿拉伯数字或数量词（如十二万、四千元）。金额、距离、期限只出现在工具结果；'
                         'report_summary 只写比较点/已明确项/待确认项。必要检查已完成则 status=ready，不要再问无阻塞确认。'}],
                        Finish)
                    finished = retried
                except (InvalidModelOutput, LimitReached):
                    pass
        await self.complete_output(run_id, finished)

    async def finish_followup(self, run_id: str, budget: dict[str, Any],
                              snapshot: dict[str, Any]) -> Finish:
        event_ids = [e['id'] for e in snapshot.get('events') or []]
        messages = [{'role': 'system', 'content': prompt('agent') + '\n' + prompt('followup')},
                    {'role': 'user', 'content': as_data(snapshot)},
                    {'role': 'user', 'content': prompt('followup') +
                     '\n当前目标=followup。只返回 Finish JSON，status=ready，不要调用查询工具。'
                     'source_ids 只能使用这些事件ID：' + json.dumps(event_ids, ensure_ascii=False) +
                     '。无明确 resolution_evidence 时不得写已解决、顾虑消除或购买意愿。'}]
        try:
            return await self.structured(run_id, budget, messages, Finish)
        except (InvalidModelOutput, LimitReached):
            return Finish(status='ready', summary=self.neutral_followup_summary(snapshot),
                          source_ids=event_ids)

    @staticmethod
    def neutral_followup_summary(snapshot: dict[str, Any]) -> str:
        events = snapshot.get('events') or []
        if not events:
            return '暂无新的产品相关动态，待销售进一步确认'
        parts = []
        for event in events:
            evidence = event.get('resolution_evidence')
            state = '已有确认依据，可视为该项已核实' if isinstance(evidence, str) and evidence.strip() else '已提供信息，待客户确认'
            parts.append(f"{event.get('topic')}: {event.get('safe_summary')}（{state}）")
        return '本轮 Mock 产品互动：' + '；'.join(parts)

    async def apply_route(self, run_id: str, route: RouteDecision) -> str | None:
        async with self.transaction(run_id) as (store, run, session):
            intent: str | None = route.intent
            if route.intent == 'answer_question':
                parent_id = str(route.reply_to_run_id) if route.reply_to_run_id else session.pending_run_id
                if not parent_id:
                    raise BusinessError('没有可关联的追问', 'INVALID_CONTINUATION')
                parent = await store.require(Run, parent_id, session.id)
                if session.pending_run_id != parent.id:
                    raise BusinessError('追问不是当前待答组', 'INVALID_CONTINUATION')
                for qid in route.question_ids:
                    q = await store.require(Question, str(qid), session.id)
                    if q.origin_run_id != parent.id or q.state != 'open':
                        raise BusinessError('追问引用不匹配', 'INVALID_QUESTION')
                await attach_parent(store, run, parent)
                intent = parent.effective_intent
            else:
                run.effective_intent = None if route.intent == 'clarify' else intent
            if route.intent == 'edit_draft':
                target = run.checkpoint['submission'].get('target_draft_id')
                if target is None and route.target_draft_id:
                    target = str(route.target_draft_id)
                drafts = [d for d in await store.list(Draft, session_id=session.id) if not d.stale]
                if not target:
                    target = drafts[-1].id if len(drafts) == 1 else None
                if not target:
                    run.effective_intent = None
                    return None
                draft = await store.require(Draft, target, session.id)
                run.checkpoint = {**run.checkpoint, 'target_draft_id': target,
                                  'target_draft_revision': draft.draft_revision}
            # 新报告目标替代旧待答目标；无关QA不消费或替代原组。
            if route.intent == 'prepare_report' and session.pending_run_id and not run.parent_run_id:
                previous = await store.require(Run, session.pending_run_id, session.id)
                previous.checkpoint = {**previous.checkpoint, 'superseded': True}
                for q in await store.list(Question, session_id=session.id, origin_run_id=previous.id):
                    if q.state == 'open' and not q.required:
                        q.state = 'superseded'
                session.pending_run_id = None
            await self.event(store, run, 'routed', '已确定本次处理目标')
            return run.effective_intent

    async def save_extraction(self, run_id: str, output: Extraction):
        ids: list[str] = []
        questions: list[SuggestedQuestion] = []
        async with self.transaction(run_id) as (store, run, session):
            text = safe_projection(run.checkpoint['submission']['text'])
            existing = current_facts(await store.list(Fact, session_id=session.id))
            for item in output.facts:
                if item.key not in FACT_KEYS or item.key == 'resolved_concerns':
                    continue
                if item.evidence_quote not in text:
                    continue
                same = [f for f in existing if f.key == item.key]
                if item.state == 'unknown' and any(f.state == 'unknown' for f in same):
                    continue
                if any(f.value == item.value and f.state in ('confirmed', 'unknown') for f in same):
                    continue
                is_money = item.key in MONEY_FACTS
                invalid_money = is_money and (type(item.value) is not int or item.value < 0
                    or item.unit != 'CNY_fen')
                conflict = item.state == 'conflict' or invalid_money or any(
                    f.state == 'confirmed' and f.value != item.value for f in same)
                state = 'conflict' if conflict else 'proposed'
                row = await store.add(Fact(session_id=session.id, key=item.key,
                    value=item.value, unit=item.unit, state=state, source_kind='sales_input',
                    source_id=run.source_message_id or run.id, subject_id=item.subject_id,
                    evidence_note=item.evidence_quote, scope='session', supersedes=[]))
                ids.append(row.id)
                # 金额/单位/冲突必须二次确认；模型提到“不知道”也需销售采用确认。
                required = conflict or is_money
                if required or not session.optional_questions_stopped:
                    questions.append(SuggestedQuestion(text=f'请确认{item.key}：{item.evidence_quote}',
                        key=item.key, required=required, fact_ids=[row.id, *[f.id for f in same]]))
            if ids:
                await store.bump(session)
                run.current_revision = session.revision
            if not session.optional_questions_stopped:
                for q in output.questions:
                    if q.key and any(f.key == q.key and f.state == 'unknown' for f in existing):
                        continue
                    # 模型的required不能单独阻断；需来自真实冲突/预算事实。
                    questions.append(q.model_copy(update={'required': False, 'fact_ids': []}))
            # 原问题只有结构化确认才能标answered；自由文本新增事实仍须确认，不抢先消失。
            return ids, sorted(questions, key=lambda q: not q.required)

    async def required_questions(self, run_id: str) -> list[SuggestedQuestion]:
        async with self.transaction(run_id) as (store, run, session):
            facts = await store.list(Fact, session_id=session.id)
            result = [SuggestedQuestion(text=q.text, required=True, fact_ids=q.fact_ids)
                      for q in await store.list(Question, session_id=session.id)
                      if q.required and q.state == 'open']
            for issue in blocking_facts(facts):
                if not result:
                    result.append(SuggestedQuestion(text=issue['message'], required=True,
                        fact_ids=[f.id for f in current_facts(facts) if f.key == issue['field']]))
            return result

    async def ask(self, run_id: str, suggestions: list[SuggestedQuestion], reason: str = 'questions'):
        async with self.transaction(run_id) as (store, run, session):
            facts = current_facts(await store.list(Fact, session_id=session.id))
            existing = [q for q in await store.list(Question, session_id=session.id) if q.state == 'open']
            for suggestion in suggestions:
                if not suggestion.required and session.optional_questions_stopped:
                    continue
                # Unknown只抑制重复的可选追问，不能屏蔽新输入金额/冲突的强确认。
                if not suggestion.required and suggestion.key and any(
                        f.key == suggestion.key and f.state == 'unknown' for f in facts):
                    continue
                refs = []
                for fid in suggestion.fact_ids:
                    await store.require(Fact, fid, session.id)
                    refs.append(fid)
                match = next((q for q in existing if q.text == suggestion.text or
                              (refs and set(q.fact_ids) == set(refs))), None)
                if match:
                    match.origin_run_id = run.id
                    continue
                q = await store.add(Question(session_id=session.id, text=suggestion.text,
                    required=suggestion.required, fact_ids=refs, origin_run_id=run.id))
                existing.append(q)
            # 关键问题不因旧目标被替代而消失；未知/answered不再次出现。
            for q in existing:
                if q.required:
                    q.origin_run_id = run.id
            visible = sorted([q for q in existing if q.origin_run_id == run.id],
                             key=lambda q: not q.required)[:self.config.max_questions_per_round]
            if not visible:
                run.result = {'outcome': 'context', 'status': 'ready',
                              'proposed_fact_ids': [], 'questions': []}
                run.status, run.finished_at = 'succeeded', utcnow()
                return
            run.checkpoint = {**run.checkpoint, 'reason': reason,
                              'question_ids': [q.id for q in existing if q.origin_run_id == run.id]}
            run.status, run.finished_at = 'needs_confirmation', utcnow()
            run.result = {'outcome': 'clarification', 'status': 'needs_confirmation',
                          'questions': [question_read(q) for q in visible],
                          'unknown_support': unknown_support(facts)}
            session.pending_run_id = run.id
            await self.event(store, run, 'needs_confirmation', '等待销售确认后继续')
            await store.timeline(session.id, 'question', 'assistant',
                {'text': '请确认以下信息', 'questions': [question_read(q) for q in visible]},
                {'kind': 'run', 'id': run.id})

    async def stop(self, run_id: str, reason: str, text: str, *, partial: bool):
        async with self.transaction(run_id, check=False) as (store, run, session):
            run.status, run.finished_at = 'needs_confirmation', utcnow()
            run.checkpoint = {**run.checkpoint, 'reason': reason}
            run.result = {'outcome': 'partial', 'status': 'partial',
                'completed_artifact_ids': run.checkpoint.get('artifact_ids', []),
                'remaining_items': [text]}
            session.pending_run_id = run.id
            await self.event(store, run, 'needs_confirmation', text)
            await store.timeline(session.id, 'text', 'assistant', {'text': text},
                                 {'kind': 'run', 'id': run.id})

    async def fail(self, run_id: str, code: str, message: str, interrupted: bool = False):
        async with self.transaction(run_id, check=False) as (store, run, _):
            run.status, run.finished_at = ('interrupted' if interrupted else 'failed'), utcnow()
            run.error = {'code': code, 'message': message, 'retryable': True}
            await self.event(store, run, 'failed', message)

    async def finish(self, run_id: str, result: dict[str, Any]):
        async with self.transaction(run_id) as (store, run, session):
            run.status, run.finished_at, run.result = 'succeeded', utcnow(), result
            if session.pending_run_id in (run.id, run.parent_run_id):
                session.pending_run_id = None
            await self.event(store, run, 'completed', '本次处理已完成，请查看结果')
            await store.timeline(session.id, 'text', 'assistant', result,
                                 {'kind': 'run', 'id': run.id})

    async def tool(self, run_id: str, call: dict[str, Any], failed_hashes: set[str]):
        function = call.get('function', {})
        name, call_id = function.get('name', ''), call.get('id', '')
        if not call_id:
            raise InvalidModelOutput()
        observation: dict[str, Any] = {'call_id': call_id, 'tool': name, 'status': 'failed',
            'artifact_id': None, 'data': {}, 'error': None, 'source_refs': [], 'observed_at': utcnow()}
        try:
            args = json.loads(function.get('arguments', '{}'))
            if not isinstance(args, dict):
                raise ValueError('arguments must be object')
        except (ValueError, TypeError):
            observation['error'] = {'code': 'INVALID_ARGUMENTS', 'message': '工具参数不是JSON对象',
                                    'retryable': False}
            return observation
        request_hash = digest({'tool': name, 'arguments': args})
        async with self.transaction(run_id) as (store, run, session):
            revision, session_id = run.current_revision, session.id
            if request_hash in failed_hashes:
                observation['error'] = {'code': 'REPEATED_FAILURE', 'message': '相同失败调用不能重复',
                                        'retryable': False}
                return observation
            for artifact in await store.list(Artifact, session_id=session.id):
                if artifact.input_hash == request_hash and artifact.source_revision == revision and artifact.status == 'ok':
                    return {**observation, 'status': 'ok', 'artifact_id': artifact.id,
                            'data': artifact.output, 'error': None, 'source_refs': artifact.source_refs,
                            'observed_at': artifact.observed_at}
            await self.event(store, run, 'tool_started', '正在执行：' + name, tool=name)
        try:
            if name in ('read_session', 'validate_report'):
                allowed = set() if name == 'read_session' else {'draft_section_refs'}
                if set(args) - allowed:
                    raise BusinessError('工具包含未允许参数', 'INVALID_ARGUMENTS')
                async with self.transaction(run_id) as (store, run, _):
                    if name == 'read_session':
                        data = await context_snapshot(store, run)
                    else:
                        for ref in args.get('draft_section_refs', []):
                            await store.require(Artifact, ref, session_id)
                        data = {'blocking_issues': await ReportService(store, self.config).blocking_issues(session_id)}
                    observation.update(status='ok', data=data)
            else:
                from src.tools.registry import ToolContext
                await self.guard_tool_inputs(run_id, name, args)
                observation = await self.registry.execute(name, args,
                    ToolContext(session_id, revision, self.app.state.session_factory, self.app.state.write_lock),
                    call_id=call_id)
        except InputsChanged:
            raise
        except Exception as error:
            logger.warning('Agent工具调用失败', run_id=run_id, tool=name, error_type=type(error).__name__)
            observation['error'] = {'code': getattr(error, 'code', 'TOOL_FAILED'),
                                    'message': getattr(error, 'message', '工具未完成，已保留其他信息'), 'retryable': False}
        if observation['status'] == 'failed':
            failed_hashes.add(request_hash)
        # 工具等待过程中输入被修改则禁止旧结果写回当前revision。
        async with self.transaction(run_id) as (store, run, _):
            artifact = await store.add(Artifact(session_id=session_id, tool_name=name,
                input_hash=request_hash, source_revision=revision, output=safe_projection(observation['data']),
                status=observation['status'], source_refs=safe_projection(observation.get('source_refs', [])),
                observed_at=observation.get('observed_at', utcnow())))
            observation['artifact_id'] = artifact.id
            run.checkpoint = {**run.checkpoint, 'artifact_ids':
                              [*run.checkpoint.get('artifact_ids', []), artifact.id]}
            await self.event(store, run, 'tool_completed',
                '查询完成' if observation['status'] == 'ok' else '查询存在缺项或失败',
                tool=name, artifact=artifact.id)
        return safe_projection(observation)

    async def complete_output(self, run_id: str, output: Finish):
        snapshot = await self.snapshot(run_id)
        intent = snapshot.get('effective_intent')
        if intent == 'followup':
            output = output.model_copy(update={'questions': [], 'status': 'ready', 'rejected': False})
        elif output.rejected:
            await self.finish(run_id, {'outcome': 'rejected', 'status': 'ready',
                'reason': output.summary, 'allowed_next_action': '请在草稿中明确审核并点击发布'})
            return
        close_prepare = (snapshot.get('effective_intent') == 'prepare_report'
                         and not await self.prepare_blocked(run_id, snapshot))
        if output.questions:
            unknown_keys = {f['key'] for f in snapshot['facts'] if f['state'] == 'unknown'}
            allowed = [q.model_copy(update={'required': False}) for q in output.questions
                       if not snapshot['optional_questions_stopped'] and q.key not in unknown_keys]
            if allowed and not close_prepare:
                await self.ask(run_id, allowed)
                return
            output = output.model_copy(update={'questions': [], 'status': 'ready',
                'report_summary': self.merge_pending_questions(output, allowed if close_prepare else [])})
        if output.status != 'ready' and not close_prepare:
            await self.stop(run_id, 'limit_reached', output.summary or '仍有信息需要继续处理', partial=True)
            return
        if close_prepare:
            output = output.model_copy(update={'questions': [], 'status': 'ready'})
        intent = snapshot['effective_intent']
        if intent is None:
            await self.ask(run_id, [SuggestedQuestion(text='请明确本次要修改的草稿或需要处理的目标。')],
                           reason='route_ambiguity')
            return
        source_refs = []
        available = {f['id']: {'id': f['id'], 'kind': f['source_kind'], 'label': f['key'],
                               'observed_at': f['observed_at']} for f in snapshot['facts']}
        for a in snapshot['artifacts']:
            for ref in a['source_refs']:
                available[ref['id']] = ref
        for c in snapshot['captures']:
            available[c['id']] = {'id': c['id'], 'kind': 'official_capture', 'label': '官网采集',
                'url': c['payload']['source_url'], 'observed_at': c['payload']['captured_at']}
        source_refs = [available[x] for x in output.source_ids if x in available]
        if intent in ('prepare_report', 'edit_draft'):
            async with self.transaction(run_id) as (store, run, session):
                service = ReportService(store, self.config)
                if intent == 'edit_draft':
                    target = run.checkpoint.get('target_draft_id') or run.checkpoint['submission'].get('target_draft_id')
                    draft = await store.require(Draft, target or '', session.id)
                    revision = run.checkpoint.get('target_draft_revision') or run.checkpoint['submission'].get('target_draft_revision')
                    if output.report_summary is None:
                        raise InvalidModelOutput()
                    if draft.source_revision != session.revision:
                        updated = await service.save_draft(session.id, session.revision,
                            summary=self.qualitative_summary(output))
                        result = {'outcome': 'draft', 'status': 'ready', 'draft_id': updated['id'],
                                  'draft_revision': updated['draft_revision']}
                    else:
                        result = await service.update(session.id, draft.id, DraftUpdate(
                            expected_revision=session.revision, draft_revision=revision,
                            summary=output.report_summary))
                        result = {'outcome': 'draft', 'status': 'ready', 'draft_id': result['draft_id'],
                                  'draft_revision': result['draft_revision']}
                else:
                    # 数字只留在确定性模块；定性摘要去数字后仍保存已成功的金融/地图产物。
                    summary = self.qualitative_summary(output)
                    draft_result = await service.save_draft(session.id, session.revision, summary=summary)
                    result = {'outcome': 'draft', 'status': 'ready', 'draft_id': draft_result['id'],
                              'draft_revision': draft_result['draft_revision']}
            await self.finish(run_id, result)
        elif intent == 'followup':
            events = snapshot['events']
            allowed_ids = {e['id'] for e in events}
            ids = [x for x in output.source_ids if x in allowed_ids]
            confirmed_resolutions = [f for f in snapshot['facts'] if f['id'] in output.source_ids
                and f['key'] == 'resolved_concerns' and f['state'] == 'confirmed']
            if events:
                latest_fixture = events[-1].get('fixture_id')
                latest_ids = [e['id'] for e in events if e.get('fixture_id') == latest_fixture]
                if ids:
                    ids = list(dict.fromkeys([*ids, *latest_ids]))
                elif not confirmed_resolutions:
                    ids = latest_ids or [e['id'] for e in events]
            selected_events = [e for e in events if e['id'] in ids]
            # all([])不能作为已解决的证明。必须有非空引用，并逐条携带明确确认依据。
            evidence = [e['resolution_evidence'] for e in selected_events] + [
                f.get('evidence_note') for f in confirmed_resolutions]
            has_resolution_evidence = any(
                isinstance(note, str) and bool(note.strip()) for note in evidence)
            if (re.search(r'购买意愿|购买意向|成交概率|下单概率', output.summary) or
                    (re.search(r'已解决|已经解决|顾虑消除', output.summary) and
                     not has_resolution_evidence)):
                raise BusinessError('跟进结论缺少客户确认依据', 'UNSUPPORTED_FOLLOWUP_CLAIM')
            summary = safe_projection(output.summary) or self.neutral_followup_summary(snapshot)
            if not str(summary).strip():
                summary = self.neutral_followup_summary(snapshot)
            # 显式附产品来源与原证据；无证据一律保持待确认，不从模型文本推导状态。
            brief = {'brief': summary, 'summary': summary, 'source': 'mock',
                'source_event_ids': ids,
                'confirmed_resolution_fact_ids': [f['id'] for f in confirmed_resolutions],
                'items': [{'topic': e['topic'], 'summary': e['safe_summary'],
                           'status': 'resolved' if isinstance(e['resolution_evidence'], str) and
                               e['resolution_evidence'].strip() else 'needs_confirmation',
                           'resolution_evidence': e['resolution_evidence'], 'source_event_id': e['id']}
                          for e in events if e['id'] in ids]}
            async with self.transaction(run_id) as (_, _run, session):
                session.followup = brief
            await self.finish(run_id, {'outcome': 'followup', 'status': 'ready',
                                      'brief': brief, 'source_event_ids': ids})
        else:
            await self.finish(run_id, {'outcome': 'answer', 'status': 'ready',
                                      'text': safe_projection(output.summary), 'source_refs': source_refs})

    async def guard_tool_inputs(self, run_id: str, name: str, args: dict[str, Any]):
        """参数来自当前确认事实；模型不能把猜测预算/地区送入真实查询。"""
        snapshot = await self.snapshot(run_id)
        confirmed = {f['key']: f['value'] for f in snapshot['facts'] if f['state'] == 'confirmed'}
        if name == 'search_charging':
            if args.get('confirmed_location_ref'):
                valid = args['confirmed_location_ref'] == confirmed.get('confirmed_location_ref')
            else:
                valid = args.get('region') == confirmed.get('region') and bool(confirmed.get('region'))
                if args.get('city'):
                    valid &= args['city'] == confirmed.get('city')
            if not valid:
                raise BusinessError('请先让销售确认城市和常用区域', 'LOCATION_NOT_CONFIRMED')
        if name == 'calculate_finance':
            budgets = {'down_payment_min_fen': ('desired_down_payment', 'down_payment_budget'),
                'down_payment_fen': ('desired_down_payment', 'down_payment_budget'),
                'down_payment_max_fen': ('max_down_payment', 'down_payment_budget'),
                'monthly_cap_fen': ('monthly_budget', 'desired_monthly_payment')}
            for key, fact_keys in budgets.items():
                confirmed_value = next((confirmed[k] for k in fact_keys if k in confirmed), None)
                provided = args.get(key)
                if provided is None:
                    if key == 'monthly_cap_fen' and isinstance(confirmed_value, int) and confirmed_value > 0:
                        args[key] = confirmed_value
                    continue
                if confirmed_value is None:
                    raise BusinessError('计算预算需先经销售确认，不能猜测', 'BUDGET_NOT_CONFIRMED')
                if provided == confirmed_value:
                    continue
                if (isinstance(provided, (int, float)) and not isinstance(provided, bool)
                        and provided * 100 == confirmed_value):
                    args[key] = confirmed_value
                    continue
                # 单位或取值偏差时改用已确认分值，避免模型反复试错打满回合上限。
                args[key] = confirmed_value
            if args.get('terms_months') and 'term_months' in confirmed:
                if any(t != confirmed['term_months'] for t in args['terms_months']):
                    raise BusinessError('期限与确认要求不一致', 'TERM_NOT_CONFIRMED')
        if name == 'calculate_energy':
            mapping = {'annual_km': 'annual_mileage', 'years': 'holding_years',
                'kwh_per_100km': 'energy_consumption', 'electricity_yuan_per_kwh': 'electricity_price',
                'liters_per_100km': 'fuel_consumption', 'fuel_yuan_per_liter': 'fuel_price'}
            if any(key not in args or confirmed.get(fact) != args[key] for key, fact in mapping.items()):
                raise BusinessError('能源试算需要明确全部假设并经销售确认', 'ENERGY_ASSUMPTIONS_MISSING')

    SUMMARY_NUMBER_RE = re.compile(
        r'\d|[零〇一二三四五六七八九十两]*[百千万亿]+|[零〇一二三四五六七八九十百千万亿两]+(?:元|万|公里|个月|年|%|分)')

    @classmethod
    def summary_has_numbers(cls, output: Finish) -> bool:
        summary = output.report_summary.model_dump() if output.report_summary else None
        return bool(summary and cls.SUMMARY_NUMBER_RE.search(as_data(summary)))

    @classmethod
    def strip_summary_numbers(cls, value: str) -> str:
        text = cls.SUMMARY_NUMBER_RE.sub('', value)
        return re.sub(r'[ \t]{2,}', ' ', text).strip(' ，,。;；/、')

    @classmethod
    def qualitative_summary(cls, output: Finish):
        summary = output.report_summary.model_dump() if output.report_summary else None
        if not summary:
            return summary
        confirmed = [text for item in summary.get('confirmed') or []
                     if (text := cls.strip_summary_numbers(item))]
        pending = [text for item in summary.get('pending') or []
                   if (text := cls.strip_summary_numbers(item))]
        return {'comparing': cls.strip_summary_numbers(summary.get('comparing') or '') or '当前候选方案',
                'confirmed': confirmed, 'pending': pending}

    @classmethod
    def merge_pending_questions(cls, output: Finish, questions: list[SuggestedQuestion]):
        summary = output.report_summary
        if summary is None or not questions:
            return summary
        pending = list(summary.pending)
        for question in questions:
            if question.text not in pending:
                pending.append(question.text)
        return summary.model_copy(update={'pending': pending})

    async def prepare_blocked(self, run_id: str, snapshot: dict[str, Any] | None = None) -> bool:
        snapshot = snapshot or await self.snapshot(run_id)
        async with self.transaction(run_id) as (store, _, session):
            issues = await ReportService(store, self.config).blocking_issues(session.id)
        if any(issue.get('blocking') for issue in issues):
            return True
        artifacts = [item for item in snapshot.get('artifacts') or [] if item.get('tool') == 'search_charging']
        if artifacts:
            data = artifacts[-1].get('data') or {}
            if data.get('state') == 'ambiguous':
                confirmed = {f['key']: f['value'] for f in snapshot.get('facts') or []
                             if f.get('state') == 'confirmed'}
                if not confirmed.get('confirmed_location_ref'):
                    return True
        return False

    async def unknown_support_for(self, run_id: str) -> list[dict[str, str]]:
        async with self.transaction(run_id) as (store, run, session):
            return unknown_support(await store.list(Fact, session_id=session.id))

    async def ensure_prepare_tools(self, run_id: str, failed_hashes: set[str]) -> None:
        snapshot = await self.snapshot(run_id)
        if snapshot.get('effective_intent') != 'prepare_report':
            return
        artifacts = snapshot.get('artifacts') or []

        def used(name: str, predicate) -> bool:
            return any(item.get('tool') == name and predicate(item.get('data') or {}) for item in artifacts)

        captures = [c for c in snapshot.get('captures') or [] if c.get('validity') == 'valid']
        if captures and not used('calculate_finance', lambda data: data.get('state') in ('ready', 'no_solution')):
            capture_id = captures[0]['id']
            if not used('list_finance_products', lambda data: bool(data.get('products'))):
                await self.tool(run_id, {'id': 'auto-list-finance', 'type': 'function',
                    'function': {'name': 'list_finance_products',
                                 'arguments': json.dumps({'capture_id': capture_id})}}, failed_hashes)
                snapshot = await self.snapshot(run_id)
                artifacts = snapshot.get('artifacts') or []
            products = next((item['data']['products'] for item in artifacts
                             if item.get('tool') == 'list_finance_products' and item.get('data', {}).get('products')),
                            [{'id': 'mock-zero-60'}])
            args = {'capture_id': capture_id, 'product_id': products[0]['id']}
            await self.tool(run_id, {'id': 'auto-calculate-finance', 'type': 'function',
                'function': {'name': 'calculate_finance', 'arguments': json.dumps(args)}}, failed_hashes)
            snapshot = await self.snapshot(run_id)
        if charging_search_needed(snapshot.get('facts') or []) and not used(
                'search_charging', lambda data: bool(data.get('state'))):
            confirmed = {f['key']: f['value'] for f in snapshot['facts'] if f['state'] == 'confirmed'}
            args = {'region': confirmed.get('region') or '已确认地点'}
            if confirmed.get('city'):
                args['city'] = confirmed['city']
            if confirmed.get('confirmed_location_ref'):
                args['confirmed_location_ref'] = confirmed['confirmed_location_ref']
            await self.tool(run_id, {'id': 'auto-search-charging', 'type': 'function',
                'function': {'name': 'search_charging', 'arguments': json.dumps(args)}}, failed_hashes)
