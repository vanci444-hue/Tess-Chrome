"""真实数据库/HTTP运行器的协议回放；模型替身显式注入，不代表百炼实测。"""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from src.api.routes.runs import router
from src.config.settings import Settings
from src.db.models import Fact, MockEvent, Question
from src.main import create_app
from src.repositories.store import Store
from src.services.agent import install_agent
from src.services.agent.crm import extract_crm
from src.services.reports import ReportService

ORIGIN = 'http://127.0.0.1:5199'


def message(value):
    return {'role': 'assistant', 'content': json.dumps(value, ensure_ascii=False)}


def route(intent, **kw):
    return message({'intent': intent, **kw})


def finish(text='资料已整理', **kw):
    return message({'status': 'ready', 'summary': text, **kw})


def tool(name='lookup_official_knowledge', args=None, call_id='call1'):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': call_id, 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(args or {'topic': 'safety'})}}]}


class ReplayProvider:
    def __init__(self, steps=()):
        self.steps = list(steps)
        self.calls = []
        self.release = None

    async def complete(self, messages, tools=None, response_format=None):
        self.calls.append({'messages': messages, 'tools': tools, 'response_format': response_format})
        if self.release is not None:
            await self.release.wait()
        assert self.steps, 'unexpected model call'
        value = self.steps.pop(0)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(messages)
        return value


@pytest.fixture
def setup(tmp_path):
    opened = []

    def make(steps=(), **settings):
        config = Settings(database_path=str(tmp_path / f'{uuid4()}.db'), **settings)
        app = create_app(config, extra_routers=(router,))
        provider = ReplayProvider(steps)
        install_agent(app, provider=provider)
        client = TestClient(app, base_url='http://127.0.0.1:8003')
        client.__enter__()
        opened.append(client)
        customer = ok(post(client, '/api/customers', {'nickname': 'Evan', 'email': 'evan@example.com',
                                                      'identity_confirmed': True}), 201)
        session = ok(post(client, '/api/sessions', {'customer_id': customer['id'], 'title': 'Model Y'}), 201)
        return client, provider, session['id']

    yield make
    for client in opened:
        client.__exit__(None, None, None)


def post(client, path, body, key=None):
    return client.post(path, json=body, headers={'Origin': ORIGIN, 'Idempotency-Key': key or str(uuid4())})


def ok(response, status=200):
    assert response.status_code == status, response.text
    assert response.json()['success']
    return response.json()['data']


def send(client, sid, text='帮我解释家庭用车', revision=1, **extra):
    return ok(post(client, f'/api/sessions/{sid}/messages',
        {'text': text, 'expected_revision': revision, **extra}), 202)


def drain(client):
    async def wait():
        tasks = list(client.app.state.agent_runner.tasks.values())
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
    client.portal.call(wait)


def result(client, sid, rid):
    drain(client)
    return ok(client.get(f'/api/sessions/{sid}/runs/{rid}'))


def mutate(client, callback):
    async def work():
        async with client.app.state.write_lock, client.app.state.session_factory() as db:
            await callback(Store(db))
            await db.commit()
    client.portal.call(work)


def detail(client, sid):
    return ok(client.get(f'/api/sessions/{sid}'))


def capture(client, sid):
    path = Path(__file__).resolve().parents[3] / 'docs/evidence/capture-spike/tester-0.1.1-awd-white20.json'
    raw = json.loads(path.read_text())
    allowed = {'source_url','captured_at','adapter_version','page_fingerprint','readiness','fields','issues'}
    return ok(post(client, f'/api/sessions/{sid}/captures',
        {'expected_revision': 1, 'capture': {k:v for k,v in raw.items() if k in allowed}}), 201)


def test_receive_202_before_model_and_same_run_qa_no_report(setup):
    client, provider, sid = setup([route('qa'), message('结束工具回合'), finish('主动安全请以官方资料为准')])
    async def hold():
        provider.release = asyncio.Event()
    client.portal.call(hold)
    accepted = send(client, sid, '我的电话13812345678，邮件evan@example.com，安全怎么理解？')
    assert accepted['status'] == 'queued'
    stored = detail(client, sid)
    assert len(stored['inputs']) == 1 and len(stored['timeline']) == 1
    assert stored['active_run']['run_id'] == accepted['run_id']
    client.portal.call(provider.release.set)
    outcome = result(client, sid, accepted['run_id'])
    assert outcome['status'] == 'succeeded' and outcome['result']['outcome'] == 'answer'
    sent = json.dumps(provider.calls, ensure_ascii=False)
    assert '13812345678' not in sent and 'evan@example.com' not in sent
    assert detail(client, sid)['draft'] is None


def test_button_skips_route_report_draft_never_publish(setup):
    client, provider, sid = setup([message('无需更多工具'), finish(report_summary={
        'comparing': '当前候选方案', 'confirmed': [], 'pending': ['实际试驾版本待确认']})])
    capture(client, sid)
    r = ok(post(client, f'/api/sessions/{sid}/runs', {'intent': 'prepare_report',
        'expected_revision': 2}), 202)
    out = result(client, sid, r['run_id'])
    assert out['result']['outcome'] == 'draft'
    assert len(provider.calls) == 2
    d = detail(client, sid)
    assert d['draft'] and not d['reports'] and d['trial_vehicle'] is None
    assert d['draft']['report_data']['modules'][1]['data']['options'][0]['fields']


def test_budget_confirmation_child_unknown_and_idempotency(setup):
    client, provider, sid = setup([route('prepare_report'), message({'facts': [
        {'key': 'monthly_budget', 'value': 400000, 'unit': 'CNY_fen', 'evidence_quote': '月供四千'}]})])
    capture(client, sid)
    first = send(client, sid, '月供四千，生成报告', revision=2)
    waiting = result(client, sid, first['run_id'])
    assert waiting['status'] == 'needs_confirmation'
    d = detail(client, sid)
    assert d['active_run'] is None and d['pending_run']['run_id'] == first['run_id']
    question = waiting['result']['questions'][0]
    assert question['required']
    confirm = client.patch(f'/api/sessions/{sid}/context', json={
        'expected_revision': d['revision'], 'changes': [{'fact_id': question['fact_ids'][0],
        'key': 'monthly_budget', 'value': None, 'state': 'unknown', 'supersedes': question['fact_ids']}],
        'reply_to_run_id': first['run_id'], 'reply_to_question_ids': [question['id']],
        'skip_optional_questions': True}, headers={'Origin': ORIGIN})
    revision = ok(confirm)['revision']
    assert len(provider.calls) == 2  # API011绝不自启模型
    provider.steps += [message('结束'), finish()]
    key = str(uuid4())
    body = {'intent': 'prepare_report', 'expected_revision': revision, 'continue_run_id': first['run_id']}
    child = ok(post(client, f'/api/sessions/{sid}/runs', body, key), 202)
    again = ok(post(client, f'/api/sessions/{sid}/runs', body, key), 202)
    assert child == again
    out = result(client, sid, child['run_id'])
    assert out['lineage'] == {'parent_run_id': first['run_id'], 'root_run_id': first['run_id'],
                              'effective_intent': 'prepare_report'}
    assert out['status'] == 'succeeded'
    old = ok(client.get(f"/api/sessions/{sid}/runs/{first['run_id']}"))
    assert old['status'] == 'needs_confirmation' and old['continuation']['continued_by_run_id'] == child['run_id']
    rejected = post(client, f'/api/sessions/{sid}/runs', body)
    assert rejected.status_code == 409
    assert len(provider.calls) == 4


def test_unrelated_qa_preserves_pending_and_questions(setup):
    client, provider, sid = setup([route('clarify', clarification='您想生成报告还是询问配置？')])
    first = send(client, sid, '帮我处理一下')
    result(client, sid, first['run_id'])
    provider.steps += [route('qa'), message('结束'), finish('可以先继续对比候选方案')]
    qa = send(client, sid, '候选是什么意思？')
    assert result(client, sid, qa['run_id'])['result']['outcome'] == 'answer'
    assert detail(client, sid)['pending_run']['run_id'] == first['run_id']


def test_tool_observation_failure_changes_next_action_and_report_module(setup):
    def after_failed(messages):
        obs = json.loads(messages[-1]['content'])
        assert obs['status'] == 'failed' and obs['error']
        return tool('lookup_official_knowledge', {'topic': 'safety'}, 'safe2')
    client, provider, sid = setup([route('qa'), tool('shell', {'command': 'unsafe'}), after_failed,
                                   message('资料已获得'), finish('使用官方安全资料，不作绝对安全承诺')])
    r = send(client, sid)
    out = result(client, sid, r['run_id'])
    assert out['status'] == 'succeeded'
    artifacts = detail(client, sid)['artifacts']
    assert artifacts[0]['status'] == 'failed' and artifacts[1]['status'] == 'ok'
    assert artifacts[1]['output']['report_module']['type'] == 'family'
    assert [e['tool_name'] for e in out['events'] if e['type'] == 'tool_completed'] == ['shell','lookup_official_knowledge']


def test_limit_stops_without_auto_restart_and_stale_write_rejected(setup):
    client, provider, sid = setup([route('qa'), tool()], max_model_rounds=2)
    r = send(client, sid)
    out = result(client, sid, r['run_id'])
    assert out['status'] == 'needs_confirmation' and out['result']['status'] == 'partial'
    assert out['continuation']['reason'] == 'limit_reached'
    assert len(provider.calls) == 2
    assert detail(client, sid)['active_run'] is None


def test_edit_during_model_wait_does_not_overwrite_new_revision(setup):
    client, provider, sid = setup([route('qa')])
    async def hold():
        provider.release = asyncio.Event()
    client.portal.call(hold)
    r = send(client, sid)
    ok(client.patch(f'/api/sessions/{sid}/context', json={'expected_revision': 1,
        'changes': [{'key': 'monthly_budget', 'value': 350000, 'state': 'confirmed', 'supersedes': []}]},
        headers={'Origin': ORIGIN}))
    client.portal.call(provider.release.set)
    out = result(client, sid, r['run_id'])
    assert out['status'] == 'needs_confirmation'
    assert out['continuation']['reason'] == 'inputs_changed'
    assert detail(client, sid)['revision'] == 2


def test_concurrent_continue_only_one_child(setup):
    client, provider, sid = setup([route('clarify', clarification='请说明任务')])
    r = send(client, sid)
    result(client, sid, r['run_id'])
    provider.steps += [route('qa'), message('结束'), finish()]
    body = {'text': '继续，我要问配置', 'expected_revision': 1, 'continue_run_id': r['run_id']}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(client, f'/api/sessions/{sid}/messages', body), range(2)))
    assert sorted(x.status_code for x in results) == [202, 409]
    drain(client)


def test_missing_key_preserves_manual_input_and_is_honest_failure(setup):
    client, _, sid = setup()
    client.app.state.agent_runner.injected_provider = None
    r = send(client, sid, '记录本次驾驶体验')
    out = result(client, sid, r['run_id'])
    assert out['status'] == 'failed' and out['error']['code'] == 'LLM_NOT_CONFIGURED'
    assert detail(client, sid)['inputs'][0]['corrected_text'] == '记录本次驾驶体验'


def test_three_questions_unknown_no_repeat_and_trial_not_inherited(setup):
    facts = [{'key': k, 'value': v, 'evidence_quote': text} for k,v,text in [
        ('home_charging',False,'没家充'), ('region','望京','望京'),
        ('feedback','后排一般','后排一般'), ('family_context','一家三口','一家三口')]]
    client, _, sid = setup([message({'facts': facts})])
    capture(client, sid)
    r = ok(post(client, f'/api/sessions/{sid}/inputs', {'text': '没家充，望京，后排一般，一家三口',
                                                     'expected_revision': 2}), 202)
    out = result(client, sid, r['run_id'])
    assert len(out['result']['questions']) == 3
    d = detail(client, sid)
    assert d['trial_vehicle'] is None
    async def count(store):
        assert len(await store.list(Question, session_id=sid, state='open')) == 4
    mutate(client, count)


def test_crm_contacts_redacted_historical_only():
    provider = ReplayProvider([message({'nickname': 'Evan', 'facts': [
        {'key': 'monthly_budget', 'value': 400000, 'unit': 'CNY_fen', 'evidence_quote': '预算四千'}]})])
    result = asyncio.run(extract_crm('Evan 13812345678 evan@example.com 上次预算四千', Settings(), provider))
    assert result['proposed']['phone'] == '13812345678'
    assert result['historical_facts'][0]['scope'] == 'historical'
    assert result['historical_facts'][0]['state'] == 'proposed'
    assert '13812345678' not in json.dumps(provider.calls)


def test_followup_only_safe_product_event_and_no_false_resolved(setup):
    client, provider, sid = setup()
    async def seed(store):
        await store.add(MockEvent(id='safe-event', session_id=sid, fixture_id='family-rear-seat-followup',
            product_topic='rear_seat', safe_summary='家属关注后排支撑', resolution_evidence=None))
        await store.add(MockEvent(id='private-event', session_id=sid, fixture_id='test-only',
            product_topic='private_chat', safe_summary='私人健康与家庭争执', resolution_evidence=None))
    mutate(client, seed)
    provider.steps += [message('结束'), finish('Mock事件显示后排支撑仍需确认', source_ids=['safe-event'])]
    r = ok(post(client, f'/api/sessions/{sid}/runs', {'intent': 'followup', 'expected_revision': 1}), 202)
    out = result(client, sid, r['run_id'])
    assert out['result']['brief']['items'][0]['status'] == 'needs_confirmation'
    assert '私人健康' not in json.dumps(provider.calls, ensure_ascii=False)
    assert out['result']['source_event_ids'] == ['safe-event']


def test_draft_change_request_202_shared_service_and_readonly_numbers(setup):
    client, provider, sid = setup()
    capture(client, sid)
    async def seed():
        async with client.app.state.session_factory() as db:
            draft = await ReportService(Store(db), client.app.state.settings).save_draft(sid, 2,
                summary={'comparing': '当前候选方案', 'confirmed': [], 'pending': ['补能待确认']})
            await db.commit()
            return draft
    draft = client.portal.call(seed)
    provider.steps += [message({'facts': []}), message('结束'), finish(report_summary={
        'comparing': '当前更关注续航的候选方案', 'confirmed': [], 'pending': ['补能仍需确认']})]
    response = client.patch(f"/api/sessions/{sid}/drafts/{draft['id']}", json={
        'expected_revision': 2, 'draft_revision': 1, 'change_request': '摘要说明更关注续航'},
        headers={'Origin': ORIGIN, 'Idempotency-Key': str(uuid4())})
    r = ok(response, 202)
    out = result(client, sid, r['run_id'])
    assert out['status'] == 'succeeded' and out['result']['draft_revision'] == 2
    assert detail(client, sid)['draft']['requires_review']
    assert len(provider.calls) == 3  # 明确编辑不走路由分类


def test_natural_answer_keeps_parent_goal_and_unanswered_question(setup):
    client, provider, sid = setup([route('prepare_report'), message({'facts': [
        {'key': 'monthly_budget', 'value': 400000, 'unit': 'CNY_fen', 'evidence_quote': '月供四千'},
        {'key': 'max_down_payment', 'value': 10000000, 'unit': 'CNY_fen', 'evidence_quote': '首付十万'}]})])
    first = send(client, sid, '月供四千、首付十万，生成报告')
    pending = result(client, sid, first['run_id'])
    provider.steps += [route('answer_question', reply_to_run_id=first['run_id'],
        question_ids=[pending['result']['questions'][0]['id']]), message({'facts': [
        {'key': 'monthly_budget', 'value': 350000, 'unit': 'CNY_fen', 'evidence_quote': '月供改三千五'}]})]
    answer = send(client, sid, '月供改三千五', revision=2)
    out = result(client, sid, answer['run_id'])
    assert out['status'] == 'needs_confirmation' and out['lineage']['effective_intent'] == 'prepare_report'
    assert out['lineage']['parent_run_id'] == first['run_id']
    assert any('首付十万' in q['text'] for q in out['result']['questions'])
    assert detail(client, sid)['revision'] == 3  # 自己的合法修订不误判stale


def test_tools_reject_guessed_budget_region_and_wrong_session(setup):
    client, _, sid = setup()
    capture(client, sid)
    runner = client.app.state.agent_runner
    r = send(client, sid, revision=2)
    drain(client)  # 缺少脚本输出会诚实失败，仍可独立验证参数guard
    async def check():
        for name, args in [('calculate_finance', {'down_payment_fen': 12000000}),
                           ('search_charging', {'region': '望京'}),
                           ('calculate_energy', {'annual_km': 20000})]:
            with pytest.raises(Exception) as caught:
                await runner.guard_tool_inputs(r['run_id'], name, args)
            assert caught.value.__class__.__name__ == 'BusinessError'
    client.portal.call(check)
    other = ok(post(client, '/api/sessions', {'customer_id': detail(client, sid)['customer']['id'],
                                            'title': '其他试驾'}), 201)['id']
    assert client.get(f"/api/sessions/{other}/runs/{r['run_id']}").status_code == 404


def test_explicit_unknown_question_not_reasked(setup):
    client, provider, sid = setup()
    async def seed(store):
        await store.add(Fact(session_id=sid, key='home_charging', value=None, state='unknown',
            source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    mutate(client, seed)
    provider.steps += [message({'facts': [], 'questions': [
        {'text': '能否安装家充？', 'key': 'home_charging'}]})]
    r = ok(post(client, f'/api/sessions/{sid}/inputs', {'text': '补充驾驶体验不错',
                                                     'expected_revision': 1}), 202)
    out = result(client, sid, r['run_id'])
    assert out['status'] == 'succeeded' and not detail(client, sid)['questions']


def test_ambiguous_draft_and_invalid_schema_repair_once(setup):
    client, provider, sid = setup([{'role': 'assistant', 'content': 'not json'},
                                  route('edit_draft')])
    r = send(client, sid, '修改那个报告')
    out = result(client, sid, r['run_id'])
    assert out['status'] == 'needs_confirmation' and out['continuation']['reason'] == 'route_ambiguity'
    assert len(provider.calls) == 2


def test_followup_rejects_unfounded_resolution(setup):
    client, provider, sid = setup()
    async def seed(store):
        await store.add(MockEvent(id='event1', session_id=sid, fixture_id='family-charging-followup',
            product_topic='charging', safe_summary='关注充电位置', resolution_evidence=None))
    mutate(client, seed)
    provider.steps += [message('结束'), finish('顾虑已解决', source_ids=['event1'])]
    r = ok(post(client, f'/api/sessions/{sid}/runs', {'intent':'followup', 'expected_revision':1}), 202)
    out = result(client, sid, r['run_id'])
    assert out['status'] == 'failed' and out['error']['code'] == 'UNSUPPORTED_FOLLOWUP_CLAIM'


def test_known_international_contact_redacted_from_all_model_context(setup):
    client, provider, sid = setup([route('qa'), message('结束'), finish('可继续确认配置')])
    customer = detail(client, sid)['customer']
    ok(client.patch(f"/api/customers/{customer['id']}", json={'expected_revision': 1,
        'identity_confirmed': True, 'phone': '+12025550123'}, headers={'Origin': ORIGIN}))
    r = send(client, sid, '联系 Evan +1 (202) 555-0123，想了解安全')
    result(client, sid, r['run_id'])
    payload = json.dumps(provider.calls, ensure_ascii=False)
    assert '+1 (202) 555-0123' not in payload and '202' not in payload
    assert '[联系方式已隐藏]' in payload


def test_crm_international_preview_local_and_redacted_to_provider():
    provider = ReplayProvider([message({'nickname': 'Evan', 'facts': []})])
    output = asyncio.run(extract_crm('Evan 电话 +1 (202) 555-0123 邮箱evan@example.com', Settings(), provider))
    assert output['proposed']['phone'] == '+12025550123'
    calls = json.dumps(provider.calls, ensure_ascii=False)
    assert '555-0123' not in calls and 'evan@example.com' not in calls


def test_generic_continue_after_ambiguity_does_not_guess_goal(setup):
    client, provider, sid = setup([route('clarify', clarification='要生成报告还是问车型？')])
    first = send(client, sid, '处理这个')
    pending = result(client, sid, first['run_id'])
    continued = send(client, sid, '继续', continue_run_id=first['run_id'])
    out = result(client, sid, continued['run_id'])
    assert out['status'] == 'needs_confirmation'
    assert out['result']['questions'][0]['id'] == pending['result']['questions'][0]['id']
    assert len(provider.calls) == 1


def test_missing_key_crm_is_explicit_503_manual_creation_stays_available(setup):
    client, _, _ = setup()
    response = post(client, '/api/customers/extract', {'text': 'Evan +12025550123'})
    assert response.status_code == 503
    assert response.json()['metadata']['reason'] == 'LLM_NOT_CONFIGURED'


def test_unknown_then_new_budget_requires_confirmation_even_when_optional_stopped(setup):
    from src.db.models import Session
    from src.services.facts import current_facts

    client, _, sid = setup([message({'facts': [{'key': 'monthly_budget', 'value': 400000,
        'unit': 'CNY_fen', 'evidence_quote': '现在月供四千'}]})])
    old_ids = []
    async def seed(store):
        old = await store.add(Fact(session_id=sid, key='monthly_budget', value=None, state='unknown',
            source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
        old_ids.append(old.id)
        session = await store.require(Session, sid)
        session.optional_questions_stopped = True
    mutate(client, seed)
    accepted = ok(post(client, f'/api/sessions/{sid}/inputs', {
        'text': '客户刚补充现在月供四千', 'expected_revision': 1}), 202)
    out = result(client, sid, accepted['run_id'])
    assert out['status'] == 'needs_confirmation'
    question = out['result']['questions'][0]
    assert question['required'] and old_ids[0] in question['fact_ids']
    ok(client.patch(f'/api/sessions/{sid}/context', json={'expected_revision': 2,
        'changes': [{'key': 'monthly_budget', 'value': 400000, 'state': 'confirmed',
                     'supersedes': question['fact_ids'], 'evidence_note': '销售二次确认月供四千'}],
        'reply_to_run_id': accepted['run_id'], 'reply_to_question_ids': [question['id']]},
        headers={'Origin': ORIGIN}))
    async def verify(store):
        rows = await store.list(Fact, session_id=sid)
        assert len(rows) == 3  # Unknown、新proposed和confirmed历史全部保留
        current = current_facts(rows)
        assert len(current) == 1 and current[0].value == 400000 and current[0].state == 'confirmed'
        assert set(current[0].supersedes) == set(question['fact_ids'])
    mutate(client, verify)
    assert detail(client, sid)['questions'] == []


@pytest.mark.parametrize('evidence,expected', [(None, 'failed'), ('   ', 'failed'),
                                               ('客户明确反馈充电顾虑已解决', 'succeeded')])
def test_resolution_claim_requires_nonempty_cited_evidence(setup, evidence, expected):
    client, provider, sid = setup()
    if evidence is not None:
        async def seed(store):
            await store.add(MockEvent(id='resolution-event', session_id=sid, fixture_id='test',
                product_topic='charging', safe_summary='讨论充电', resolution_evidence=evidence))
        mutate(client, seed)
    provider.steps += [message('结束'), finish('客户充电顾虑已解决',
        source_ids=['resolution-event'] if evidence is not None else [])]
    accepted = ok(post(client, f'/api/sessions/{sid}/runs',
        {'intent': 'followup', 'expected_revision': 1}), 202)
    out = result(client, sid, accepted['run_id'])
    assert out['status'] == expected
    if expected == 'failed':
        assert out['error']['code'] == 'UNSUPPORTED_FOLLOWUP_CLAIM'
    else:
        assert out['result']['brief']['items'][0]['status'] == 'resolved'


def test_no_events_neutral_followup_still_valid(setup):
    client, _, sid = setup([message('结束'), finish('暂无新的产品相关动态，待销售进一步确认')])
    accepted = ok(post(client, f'/api/sessions/{sid}/runs',
        {'intent': 'followup', 'expected_revision': 1}), 202)
    out = result(client, sid, accepted['run_id'])
    assert out['status'] == 'succeeded' and out['result']['brief']['items'] == []


def test_confirmed_resolution_fact_is_traceable_evidence(setup):
    client, provider, sid = setup()
    async def seed(store):
        await store.add(Fact(id='resolution-fact', session_id=sid, key='resolved_concerns',
            value=['充电'], state='confirmed', source_kind='sales_input', source_id=sid,
            evidence_note='客户向销售明确确认公司充电安排可用', scope='session', supersedes=[]))
    mutate(client, seed)
    provider.steps += [message('结束'), finish('充电顾虑已解决', source_ids=['resolution-fact'])]
    accepted = ok(post(client, f'/api/sessions/{sid}/runs',
        {'intent': 'followup', 'expected_revision': 1}), 202)
    out = result(client, sid, accepted['run_id'])
    assert out['status'] == 'succeeded'
    assert out['result']['brief']['confirmed_resolution_fact_ids'] == ['resolution-fact']


def test_unknown_repeat_skips_stale_quote_and_explains_support(setup):
    client, provider, sid = setup()
    async def seed(store):
        await store.add(Fact(session_id=sid, key='home_charging', value=None, state='unknown',
            source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    mutate(client, seed)
    provider.steps += [message({'facts': [{'key': 'home_charging', 'value': '不知道', 'state': 'unknown',
        'evidence_quote': '公司充电不知道'}], 'questions': [{'text': '家充情况？', 'key': 'home_charging'}]})]
    accepted = ok(post(client, f'/api/sessions/{sid}/inputs',
                       {'text': '还是不知道', 'expected_revision': 1}), 202)
    out = result(client, sid, accepted['run_id'])
    assert out['status'] == 'succeeded' and out['error'] is None
    assert any(item['key'] == 'home_charging' for item in out['result']['unknown_support'])
    assert detail(client, sid)['inputs'][-1]['corrected_text'] == '还是不知道'


def test_guard_rewrites_yuan_cap_to_confirmed_fen(setup):
    client, _, sid = setup()
    capture(client, sid)
    async def seed(store):
        await store.add(Fact(session_id=sid, key='monthly_budget', value=400000, unit='CNY_fen',
            state='confirmed', source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    mutate(client, seed)
    accepted = send(client, sid, revision=2)
    drain(client)
    async def check():
        args = {'monthly_cap_fen': 4000}
        await client.app.state.agent_runner.guard_tool_inputs(
            accepted['run_id'], 'calculate_finance', args)
        assert args['monthly_cap_fen'] == 400000
    client.portal.call(check)


def test_prepare_skips_charging_when_home_and_parking_ready(setup):
    client, provider, sid = setup([message('无需更多工具'), finish(report_summary={
        'comparing': '当前候选方案', 'confirmed': ['家充与车位已明确'], 'pending': []})])
    capture(client, sid)
    async def seed(store):
        for key, value in (('has_fixed_parking', True), ('home_charging', '已安装家充'),
                           ('region', '望京地铁站'), ('monthly_budget', 400000)):
            await store.add(Fact(session_id=sid, key=key, value=value,
                unit='CNY_fen' if key == 'monthly_budget' else None, state='confirmed',
                source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    mutate(client, seed)
    accepted = ok(post(client, f'/api/sessions/{sid}/runs',
                       {'intent': 'prepare_report', 'expected_revision': 2}), 202)
    out = result(client, sid, accepted['run_id'])
    tools = [event['tool_name'] for event in out['events'] if event['type'] == 'tool_started']
    assert out['result']['outcome'] == 'draft'
    assert 'calculate_finance' in tools
    assert 'search_charging' not in tools


def test_prepare_searches_charging_without_parking(setup):
    client, provider, sid = setup([message('无需更多工具'), finish(report_summary={
        'comparing': '当前候选方案', 'confirmed': [], 'pending': ['公共补能待查看']})])
    capture(client, sid)
    async def seed(store):
        for key, value in (('has_fixed_parking', False), ('region', '望京地铁站'),
                           ('city', '北京'), ('monthly_budget', 400000)):
            await store.add(Fact(session_id=sid, key=key, value=value,
                unit='CNY_fen' if key == 'monthly_budget' else None, state='confirmed',
                source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    mutate(client, seed)
    accepted = ok(post(client, f'/api/sessions/{sid}/runs',
                       {'intent': 'prepare_report', 'expected_revision': 2}), 202)
    out = result(client, sid, accepted['run_id'])
    tools = [event['tool_name'] for event in out['events'] if event['type'] == 'tool_started']
    assert out['result']['outcome'] == 'draft'
    assert 'search_charging' in tools
    assert 'calculate_finance' in tools


def test_prepare_numeric_summary_retries_then_drafts_without_failing(setup):
    client, provider, sid = setup([
        message('无需更多工具'),
        finish(report_summary={'comparing': '候选价约313900元，月供十二万不合适',
                               'confirmed': ['月供400000分已确认'], 'pending': []}),
        finish(report_summary={'comparing': '当前候选方案与已确认预算',
                               'confirmed': ['家充与车位已明确'], 'pending': []}),
    ])
    capture(client, sid)
    async def seed(store):
        for key, value in (('has_fixed_parking', True), ('home_charging', '小区车位已安装家充'),
                           ('monthly_budget', 400000)):
            await store.add(Fact(session_id=sid, key=key, value=value,
                unit='CNY_fen' if key == 'monthly_budget' else None, state='confirmed',
                source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    mutate(client, seed)
    accepted = ok(post(client, f'/api/sessions/{sid}/runs',
                       {'intent': 'prepare_report', 'expected_revision': 2}), 202)
    out = result(client, sid, accepted['run_id'])
    assert out['status'] == 'succeeded' and out['result']['outcome'] == 'draft'
    assert out.get('error') is None
    draft = detail(client, sid)['draft']
    summary = json.dumps(draft['report_data']['summary'], ensure_ascii=False)
    assert '313900' not in summary and '十二万' not in summary and '400000' not in summary
    assert any(module['type'] == 'finance' and module['status'] in ('mock', 'ready')
               for module in draft['report_data']['modules'])
    assert len(provider.calls) == 3


def test_prepare_optional_questions_after_charging_still_drafts(setup):
    client, provider, sid = setup([message('无需更多工具'), finish(
        '充电站已查出', status='needs_confirmation',
        questions=[{'text': '是否还要确认公司充电？', 'key': 'home_charging'}],
        report_summary={'comparing': '当前候选方案', 'confirmed': [],
                        'pending': ['公共补能可继续查看']})])
    capture(client, sid)
    async def seed(store):
        for key, value in (('has_fixed_parking', False), ('region', '望京地铁站'),
                           ('city', '北京'), ('monthly_budget', 400000)):
            await store.add(Fact(session_id=sid, key=key, value=value,
                unit='CNY_fen' if key == 'monthly_budget' else None, state='confirmed',
                source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    mutate(client, seed)
    accepted = ok(post(client, f'/api/sessions/{sid}/runs',
                       {'intent': 'prepare_report', 'expected_revision': 2}), 202)
    out = result(client, sid, accepted['run_id'])
    tools = [event['tool_name'] for event in out['events'] if event['type'] == 'tool_started']
    assert out['status'] == 'succeeded' and out['result']['outcome'] == 'draft'
    assert 'search_charging' in tools
    assert detail(client, sid)['draft']
    pending = ' '.join(detail(client, sid)['draft']['report_data']['summary']['pending'])
    assert '公司充电' in pending


def test_prepare_still_drafts_after_failed_model_finance_calls(setup):
    capture_id = {'value': None}
    def first_fail(messages):
        return tool('calculate_finance', {'capture_id': capture_id['value'],
                                          'product_id': 'missing-product', 'monthly_cap_fen': 1}, 'fin1')
    def second_fail(messages):
        return tool('calculate_finance', {'capture_id': capture_id['value'],
                                          'product_id': 'missing-product', 'monthly_cap_fen': 2}, 'fin2')
    client, provider, sid = setup([
        first_fail, second_fail,
        finish(report_summary={'comparing': '当前候选方案', 'confirmed': ['预算已确认'], 'pending': []}),
    ])
    saved = capture(client, sid)
    capture_id['value'] = saved['capture_id']
    async def seed(store):
        await store.add(Fact(session_id=sid, key='monthly_budget', value=400000, unit='CNY_fen',
            state='confirmed', source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
        await store.add(Fact(session_id=sid, key='has_fixed_parking', value=True, state='confirmed',
            source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
        await store.add(Fact(session_id=sid, key='home_charging', value='已安装家充', state='confirmed',
            source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    mutate(client, seed)
    accepted = ok(post(client, f'/api/sessions/{sid}/runs',
                       {'intent': 'prepare_report', 'expected_revision': 2}), 202)
    out = result(client, sid, accepted['run_id'])
    assert out['status'] == 'succeeded' and out['result']['outcome'] == 'draft'
    tools = [event['tool_name'] for event in out['events'] if event['type'] == 'tool_started']
    assert tools.count('calculate_finance') >= 3
    assert any(module['type'] == 'finance' for module in detail(client, sid)['draft']['report_data']['modules'])
