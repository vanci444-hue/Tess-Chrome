"""完整正式装配上的本机 HTTP 联调。Provider 只在隔离测试显式注入。"""
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from fastapi.testclient import TestClient
from src.config.settings import Settings
from src.main import create_demo_app

ORIGIN = 'http://127.0.0.1:8003'
ROOT = Path(__file__).resolve().parents[3]


def message(value):
    return {'role': 'assistant', 'content': json.dumps(value, ensure_ascii=False)}


class Replay:
    """严格按协议回放，不接外网、不提供生产兜底。"""
    def __init__(self):
        self.steps = []

    async def complete(self, messages, tools=None, response_format=None):
        assert self.steps, 'unexpected model request'
        return self.steps.pop(0)


def tools(*calls):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': str(uuid4()), 'type': 'function', 'function': {'name': name,
            'arguments': json.dumps(args)}} for name, args in calls]}


def ending():
    return [message('工具结果已核对'), message({'status': 'ready', 'summary': '资料已整理',
        'report_summary': {'comparing': '当前候选方案', 'confirmed': ['销售已核对本次背景'],
                           'pending': ['充电便利性仍需结合日常行程确认']}})]


def request(client, method, path, body=None, status=200, key=None):
    response = client.request(method, path, json=body, headers={
        'Origin': ORIGIN, 'Idempotency-Key': key or str(uuid4())})
    assert response.status_code == status, response.text
    assert response.json()['success'], response.text
    return response.json()['data']


def detail(client, sid):
    return request(client, 'GET', f'/api/sessions/{sid}')


def wait_run(client, sid, rid):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = request(client, 'GET', f'/api/sessions/{sid}/runs/{rid}')
        if result['status'] not in ('queued', 'running'):
            return result
        threading.Event().wait(.02)
    raise AssertionError('run did not terminate')


@contextmanager
def http_server(config, provider=None):
    # 明确使用隔离端口及数据库；绑定失败直接失败，不结束其他服务。
    app = create_demo_app(config, provider=provider)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8003,
                                         log_level='error', access_log=False))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 10
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        threading.Event().wait(.02)
    assert server.started, 'isolated HTTP server did not start'
    try:
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=10) as client:
            yield client, app
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        assert not worker.is_alive(), 'isolated HTTP server did not stop'


def customer_session(client, customer=None):
    customer = customer or request(client, 'POST', '/api/customers', {
        'nickname': '集成测试客户', 'email': 'integration@example.com',
        'identity_confirmed': True}, status=201)['id']
    session = request(client, 'POST', '/api/sessions', {
        'customer_id': customer, 'title': '隔离联调'}, status=201)
    return customer, session['id']


def capture(client, sid, suffix):
    raw = json.loads((ROOT / f'docs/evidence/capture-spike/tester-0.1.1-awd-white{suffix}.json').read_text())
    data = {key: raw[key] for key in ('source_url', 'captured_at', 'adapter_version',
                                     'page_fingerprint', 'readiness', 'fields', 'issues')}
    # 同正式桥接层投影，调试 DOM 内容不提交服务。
    data['issues'] = [{**{k: v for k, v in issue.items() if k != 'severity'},
                       'blocking': issue.get('severity') == 'blocking'} for issue in data['issues']]
    result = request(client, 'POST', f'/api/sessions/{sid}/captures', {
        'expected_revision': detail(client, sid)['revision'], 'capture': data}, status=201)
    return result['capture_id'], raw


def patch_facts(client, sid, values):
    current = detail(client, sid)
    changes = []
    for key, value in values.items():
        refs = [f['id'] for f in current['facts'] if f['scope'] == 'session' and f['key'] == key]
        changes.append({'key': key, 'value': value, 'state': 'unknown' if value is None else 'confirmed',
                        'supersedes': refs, 'evidence_note': '隔离测试显式确认'})
    return request(client, 'PATCH', f'/api/sessions/{sid}/context', {
        'expected_revision': current['revision'], 'changes': changes, 'skip_optional_questions': True})


def prepare(client, sid, provider, calls=()):
    provider.steps.extend(([tools(*calls)] if calls else []) + ending())
    run = request(client, 'POST', f'/api/sessions/{sid}/runs', {
        'intent': 'prepare_report', 'expected_revision': detail(client, sid)['revision']}, status=202)
    result = wait_run(client, sid, run['run_id'])
    assert result['status'] == 'succeeded', result
    return detail(client, sid)['draft']


def test_full_http_two_real_captures_report_restart_and_missing_keys(tmp_path):
    config = Settings(database_path=str(tmp_path / 'integration.db'),
        upload_dir=str(tmp_path / 'uploads'), port=8003, report_origin=ORIGIN)
    provider = Replay()
    with http_server(config, provider) as (client, app):
        assert client.get('/').status_code == 200
        health = request(client, 'GET', '/api/health')
        assert health['capabilities'] == {'llm': 'missing', 'asr': 'missing', 'maps': 'missing'}
        cid, sid = customer_session(client)
        aid, a_raw = capture(client, sid, '20')
        bid, _ = capture(client, sid, '19')
        assert detail(client, sid)['trial_vehicle'] is None
        patch_facts(client, sid, {'monthly_budget': 400000, 'region': '望京地铁站', 'city': '北京',
            'home_charging': None, 'annual_mileage': 20000, 'holding_years': 5,
            'energy_consumption': 15, 'electricity_price': 1.2, 'fuel_consumption': 8, 'fuel_price': 8})
        def finance(cap, term):
            return ('calculate_finance', {'capture_id': cap, 'product_id': 'mock-zero-60',
                'terms_months': [term], 'monthly_cap_fen': 400000})
        energy = ('calculate_energy', {'annual_km': 20000, 'years': 5, 'kwh_per_100km': 15,
            'electricity_yuan_per_kwh': 1.2, 'liters_per_100km': 8, 'fuel_yuan_per_liter': 8,
            'source': '销售确认估算假设'})
        first = prepare(client, sid, provider, (finance(aid, 60), finance(bid, 60), energy,
            ('search_charging', {'region': '望京地铁站', 'city': '北京'})))
        initial = [m for m in first['report_data']['modules'] if m['type'] == 'finance']
        assert {m['data']['capture_id'] for m in initial} == {aid, bid}
        # 同 revision 新的期限试算覆盖该候选早期结果，另一个候选仍保留。
        draft = prepare(client, sid, provider, (finance(aid, 48),))
        modules = draft['report_data']['modules']
        financial = {m['data']['capture_id']: m for m in modules if m['type'] == 'finance'}
        assert financial[aid]['data']['solutions'][0]['term_months'] == 48
        assert financial[bid]['data']['solutions'][0]['term_months'] == 60
        for m in financial.values():
            solution = m['data']['solutions'][0]
            assert max(solution['monthly_payment_fen'], solution['last_payment_fen']) <= 400000
            assert solution['down_payment_fen'] + solution['principal_fen'] == m['data']['price_fen']
            assert m['status'] == 'mock'
        energy_data = next(m for m in modules if m['type'] == 'energy')['data']
        assert energy_data['series'][-1]['saving_fen'] == 4600000
        assert next(m for m in modules if m['type'] == 'charging')['status'] == 'missing'
        options = next(m for m in modules if m['type'] == 'options')['data']['options']
        for stored, raw in zip(options[0]['fields'], a_raw['fields'], strict=True):
            assert {k: v for k, v in stored.items() if k != 'observed_at'} == {k: v for k, v in raw.items() if k != 'observed_at'}
            assert datetime.fromisoformat(stored['observed_at']) == datetime.fromisoformat(raw['observed_at'])
        assert len({s['id'] for s in draft['report_data']['sources']}) == len(draft['report_data']['sources'])
        # 审核由正式 PATCH 路由持久化；数字来自服务重建模块。
        summary = {**draft['report_data']['summary'], 'comparing': '比较当前候选的预算与续航'}
        reviewed = request(client, 'PATCH', f"/api/sessions/{sid}/drafts/{draft['id']}", {
            'expected_revision': detail(client, sid)['revision'], 'draft_revision': draft['draft_revision'],
            'summary': summary})
        body = {'expected_revision': detail(client, sid)['revision'], 'draft_id': draft['id'],
                'draft_revision': reviewed['draft_revision'], 'review_confirmed': True}
        published = request(client, 'POST', f'/api/sessions/{sid}/reports', body, status=201)
        duplicate = request(client, 'POST', f'/api/sessions/{sid}/reports', body, status=201)
        assert duplicate == published
        report_id = published['report_id']
        frozen = request(client, 'GET', f'/api/reports/{report_id}')
        assert 'integration@example.com' not in json.dumps(frozen)
        assert datetime.fromisoformat(options[0]['captured_at']) == datetime.fromisoformat(a_raw['captured_at'])
        html = client.get(f'/reports/{report_id}')
        assert html.status_code == 200 and '/assets/' in html.text
        import re
        asset = re.search(r'src="(/assets/[^\"]+)"', html.text).group(1)
        assert client.get(asset).status_code == 200
        assert len([m for m in detail(client, sid)['timeline'] if m['type'] == 'report_card']) == 1
        _, second_sid = customer_session(client, cid)
        assert detail(client, second_sid)['reports'] == []
        history = request(client, 'GET', f'/api/customers/{cid}/reports')
        assert history['items'][0]['report_id'] == report_id
        foreign = client.post(f'/api/sessions/{second_sid}/reports', json={**body, 'expected_revision': 1},
                             headers={'Origin': ORIGIN, 'Idempotency-Key': str(uuid4())})
        assert foreign.status_code in (403, 404)
        patch_facts(client, sid, {'monthly_budget': 350000})
        assert detail(client, sid)['draft']['stale']
        rejected = client.post(f'/api/sessions/{sid}/reports', json={**body,
            'expected_revision': detail(client, sid)['revision']},
            headers={'Origin': ORIGIN, 'Idempotency-Key': str(uuid4())})
        assert rejected.status_code == 409
        assert request(client, 'GET', f'/api/reports/{report_id}') == frozen
    # 再创建正式 app，验证 SQLite 固定快照和来源时间不因重启/客户变化而更新。
    with http_server(config) as (client, app):
        assert request(client, 'GET', f'/api/reports/{report_id}') == frozen
        text = '文字已提交，即使模型没配置也不能丢失'
        run = request(client, 'POST', f'/api/sessions/{second_sid}/messages', {
            'text': text, 'source': 'sales_text', 'expected_revision': 1}, status=202)
        failed = wait_run(client, second_sid, run['run_id'])
        assert failed['status'] == 'failed' and failed['error']['code'] == 'LLM_NOT_CONFIGURED'
        assert detail(client, second_sid)['inputs'][0]['corrected_text'] == text
        audio = client.post(f'/api/sessions/{second_sid}/audio', json={'expected_revision': 1},
                            headers={'Origin': ORIGIN, 'Idempotency-Key': str(uuid4())})
        assert audio.status_code == 503 and audio.json()['metadata']['reason'] == 'ASR_NOT_CONFIGURED'


def test_production_router_boundaries_and_extension_origin(tmp_path):
    config = Settings(database_path=str(tmp_path / 'routes.db'))
    with TestClient(create_demo_app(config), base_url='http://127.0.0.1:8003') as client:
        # manifest 公钥 ID 与后端默认白名单必须一致。
        identity = json.loads((ROOT / 'frontend/extension-identity.json').read_text())
        origin = 'chrome-extension://' + identity['id']
        response = client.post('/api/customers', headers={'Origin': origin, 'Idempotency-Key': str(uuid4())},
            json={'nickname': '插件测试', 'email': 'extension@example.com', 'identity_confirmed': True})
        assert response.status_code == 201
        assert client.get('/api/health', headers={'Origin': 'https://evil.example'}).status_code == 403
        assert client.get('/api/health', headers={'Host': 'evil.example'}).status_code == 403
        paths = client.get('/openapi.json').json()['paths']
        assert '/api/sessions/{session_id}/runs' in paths
        assert '/api/sessions/{session_id}/audio' in paths
        assert callable(client.app.state.crm_extractor) and callable(client.app.state.draft_editor)


def test_latest_modules_and_explicit_artifact_selection(tmp_path):
    from src.db.models import Artifact
    from src.repositories.store import Store
    from src.services.reports import ReportService
    config = Settings(database_path=str(tmp_path / 'select.db'), report_origin=ORIGIN)
    with TestClient(create_demo_app(config), base_url=ORIGIN) as client:
        _, sid = customer_session(client)
        async def check():
            async with client.app.state.write_lock, client.app.state.session_factory() as db:
                store = Store(db)
                old = await store.add(Artifact(session_id=sid, tool_name='search_charging', input_hash='old',
                    source_revision=1, status='partial', created_at='2026-09-20T00:00:00Z',
                    output={'report_module': {'type': 'charging', 'status': 'missing', 'source_refs': [],
                                             'data': {'reason': '服务临时不可用'}}}))
                new = await store.add(Artifact(session_id=sid, tool_name='search_charging', input_hash='new',
                    source_revision=1, status='ok', created_at='2026-09-20T00:00:01Z',
                    output={'report_module': {'type': 'charging', 'status': 'ready', 'source_refs': [],
                        'data': {'stations': [], 'label': '明确注入的隔离契约结果'}}}))
                svc = ReportService(store, config)
                report, used = await svc.build_data(sid)
                assert used == [new.id]
                assert next(m for m in report['modules'] if m['type'] == 'charging')['status'] == 'ready'
                selected, ids = await svc.build_data(sid, artifact_ids=[old.id])
                assert ids == [old.id]
                assert next(m for m in selected['modules'] if m['type'] == 'charging')['status'] == 'missing'
                await db.commit()
        client.portal.call(check)


def test_confirmation_unknown_new_money_and_late_run_isolation(tmp_path):
    import asyncio
    config = Settings(database_path=str(tmp_path / 'lineage.db'), report_origin=ORIGIN)
    provider = Replay()
    with TestClient(create_demo_app(config, provider=provider), base_url=ORIGIN) as client:
        cid, sid = customer_session(client)
        capture(client, sid, '20')
        patch_facts(client, sid, {'monthly_budget': None})
        provider.steps.extend([message({'intent': 'prepare_report'}), message({'facts': [
            {'key': 'monthly_budget', 'value': 400000, 'unit': 'CNY_fen', 'evidence_quote': '月供四千'}]})])
        run = request(client, 'POST', f'/api/sessions/{sid}/messages', {
            'text': '月供四千，准备报告', 'expected_revision': detail(client, sid)['revision']}, status=202)
        waiting = wait_run(client, sid, run['run_id'])
        assert waiting['status'] == 'needs_confirmation'
        question = waiting['result']['questions'][0]
        assert question['required']
        confirmed = request(client, 'PATCH', f'/api/sessions/{sid}/context', {
            'expected_revision': detail(client, sid)['revision'], 'skip_optional_questions': True,
            'reply_to_run_id': run['run_id'], 'reply_to_question_ids': [question['id']], 'changes': [
                {'key': 'monthly_budget', 'value': None, 'state': 'unknown',
                 'fact_id': question['fact_ids'][0], 'supersedes': question['fact_ids']}]})
        provider.steps.extend(ending())
        child_body = {'intent': 'prepare_report', 'expected_revision': confirmed['revision'],
                      'continue_run_id': run['run_id']}
        key = str(uuid4())
        child = request(client, 'POST', f'/api/sessions/{sid}/runs', child_body, status=202, key=key)
        assert request(client, 'POST', f'/api/sessions/{sid}/runs', child_body, status=202, key=key) == child
        completed = wait_run(client, sid, child['run_id'])
        assert completed['status'] == 'succeeded'
        assert completed['lineage']['root_run_id'] == run['run_id']
        # 模型迟到：当前 revision 已改变，旧 run 不可写回草稿/事实。
        _, another = customer_session(client, cid)
        class HeldProvider:
            async def complete(self, *args, **kwargs):
                await self.release.wait()
                return message({'intent': 'qa'})
        held = HeldProvider()
        async def set_hold():
            held.release = asyncio.Event()
            client.app.state.agent_runner.injected_provider = held
        client.portal.call(set_hold)
        late = request(client, 'POST', f'/api/sessions/{another}/messages', {
            'text': '了解配置', 'expected_revision': 1}, status=202)
        patch_facts(client, another, {'region': '望京'})
        client.portal.call(held.release.set)
        result = wait_run(client, another, late['run_id'])
        assert result['status'] == 'needs_confirmation'
        assert result['continuation']['reason'] == 'inputs_changed'
        assert detail(client, another)['draft'] is None
        assert detail(client, sid)['draft']['id'] == completed['result']['draft_id']
