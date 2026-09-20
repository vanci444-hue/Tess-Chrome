"""独立 Agent 边界回放；替身模型、真实临时 SQLite，不代表真实 Qwen 验收。"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
spec = importlib.util.spec_from_file_location('agent_helpers', ROOT / 'backend/tests/agent/test_agent.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
setup = h.setup

from src.db.models import Fact, Run


def test_no_evidence_cannot_resolve_followup(setup):
    c, p, sid = setup([h.message('无需工具'), h.finish('客户充电顾虑已解决')])
    accepted = h.ok(h.post(c, f'/api/sessions/{sid}/runs', {
        'intent': 'followup', 'expected_revision': 1}), 202)
    out = h.result(c, sid, accepted['run_id'])
    assert out['status'] == 'failed', 'no events or confirmed resolution, but resolved summary accepted'
    assert out['error']['code'] == 'UNSUPPORTED_FOLLOWUP_CLAIM'


def test_new_budget_after_unknown_still_requires_confirmation(setup):
    c, p, sid = setup([h.message({'facts': [{'key': 'monthly_budget', 'value': 400000,
        'unit': 'CNY_fen', 'evidence_quote': '现在月供四千'}]})])
    async def seed(store):
        await store.add(Fact(session_id=sid, key='monthly_budget', value=None, state='unknown',
            source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
    h.mutate(c, seed)
    accepted = h.ok(h.post(c, f'/api/sessions/{sid}/inputs', {
        'text': '客户刚补充现在月供四千', 'expected_revision': 1}), 202)
    out = h.result(c, sid, accepted['run_id'])
    assert out['status'] == 'needs_confirmation', 'new monetary fact bypasses confirmation after earlier Unknown'
    assert any(q['required'] for q in out['result']['questions'])


def test_limit_releases_worker_then_explicit_child_retains_goal(setup):
    c, p, sid = setup([h.route('qa'), h.tool()], max_model_rounds=2)
    accepted = h.send(c, sid)
    original = h.result(c, sid, accepted['run_id'])
    assert original['status'] == 'needs_confirmation'
    async def inspect(store):
        run = await store.require(Run, accepted['run_id'])
        assert run.finished_at is not None
    h.mutate(c, inspect)
    assert c.app.state.agent_runner.tasks == {}
    p.steps += [h.message('结束'), h.finish('可继续阅读官方安全资料')]
    child = h.send(c, sid, '继续', continue_run_id=accepted['run_id'])
    out = h.result(c, sid, child['run_id'])
    assert out['status'] == 'succeeded'
    assert out['lineage']['parent_run_id'] == accepted['run_id']
    assert out['lineage']['effective_intent'] == 'qa'
    assert len(p.calls) == 4
    assert not h.detail(c, sid)['reports']


def test_superseded_budget_not_revived_in_model_snapshot(setup):
    c, p, sid = setup([h.route('qa'), h.message('结束'), h.finish('按当前确认输入处理')])
    async def seed(store):
        first = await store.add(Fact(session_id=sid, key='monthly_budget', value=400000,
            state='confirmed', source_kind='sales_input', source_id=sid, scope='session', supersedes=[]))
        second = await store.add(Fact(session_id=sid, key='monthly_budget', value=350000,
            state='confirmed', source_kind='sales_input', source_id=sid, scope='session', supersedes=[first.id]))
        await store.add(Fact(session_id=sid, key='monthly_budget', value=300000,
            state='confirmed', source_kind='sales_input', source_id=sid, scope='session', supersedes=[second.id]))
    h.mutate(c, seed)
    out = h.result(c, sid, h.send(c, sid, '当前采用哪个预算？')['run_id'])
    assert out['status'] == 'succeeded'
    context = json.loads(p.calls[0]['messages'][1]['content'])
    assert [f['value'] for f in context['facts'] if f['key'] == 'monthly_budget'] == [300000]
    assert len(h.detail(c, sid)['facts']) == 3
