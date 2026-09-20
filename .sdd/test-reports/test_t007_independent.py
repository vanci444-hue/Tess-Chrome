"""T007 独立 HTTP/数据边界；隔离 8003 与 tmp_path，不使用生产数据。"""
import importlib.util
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
spec = importlib.util.spec_from_file_location('local_http_helpers', ROOT / 'backend/tests/integration/test_local_http.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
from src.config.settings import Settings
from src.db.models import Artifact
from src.main import create_demo_app
from src.repositories.store import Store
from src.services.reports import ReportService


def test_live_http_customer_visit_identity_limit_and_new_confirmation(tmp_path):
    config = Settings(database_path=str(tmp_path/'tester-http.db'), upload_dir=str(tmp_path/'uploads'),
                      port=8003, report_origin=h.ORIGIN)
    with h.http_server(config) as (c, app):
        a, sid = h.customer_session(c)
        extension = 'chrome-extension://' + json.loads((ROOT/'frontend/extension-identity.json').read_text())['id']
        body = {'nickname': '另一个客户', 'email': 'tester-b@example.com', 'identity_confirmed': True}
        response = c.post('/api/customers', json=body, headers={'Origin': extension, 'Idempotency-Key': str(uuid4())})
        assert response.status_code == 201
        b = response.json()['data']['id']
        _, bsid = h.customer_session(c, b)
        aid, _ = h.capture(c, sid, '20')
        h.capture(c, sid, '19')
        h.capture(c, sid, '19')
        original = h.detail(c, sid)['captures']
        payload = original[0]['immutable_payload']
        too_many = c.post(f'/api/sessions/{sid}/captures', json={'expected_revision':4,'capture':payload},
                          headers={'Origin':h.ORIGIN,'Idempotency-Key':str(uuid4())})
        assert too_many.status_code == 409
        assert too_many.json()['metadata']['reason'] == 'CANDIDATE_LIMIT'
        foreign = c.patch(f'/api/sessions/{bsid}/captures/{aid}', json={'expected_revision':1,'active':False},
                          headers={'Origin':h.ORIGIN})
        assert foreign.status_code == 404
        assert h.detail(c, bsid)['captures'] == []
        assert h.detail(c, sid)['captures'] == original
        h.patch_facts(c, sid, {'monthly_budget':400000})
        old_fact = next(f for f in h.detail(c,sid)['facts'] if f['key']=='monthly_budget')
        _, second = h.customer_session(c, a)
        history = h.detail(c,second)['facts']
        assert history[0]['id']==old_fact['id'] and history[0]['scope']=='historical'
        invalid = c.patch(f'/api/sessions/{second}/context',json={'expected_revision':1,'changes':[
            {'key':'monthly_budget','value':350000,'state':'confirmed','fact_id':old_fact['id'],'supersedes':[old_fact['id']]}]},
            headers={'Origin':h.ORIGIN})
        assert invalid.status_code==404
        h.patch_facts(c,second,{'monthly_budget':None})
        local = [f for f in h.detail(c,second)['facts'] if f['scope']=='session']
        assert len(local)==1 and local[0]['state']=='unknown'
        assert next(f for f in h.detail(c,sid)['facts'] if f['id']==old_fact['id'])['value']==400000
        assert h.detail(c,bsid)['facts']==[]
        assert c.get('/api/health',headers={'Origin':'https://untrusted.example'}).status_code==403
        assert c.get('/api/health',headers={'Origin':'chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}).status_code==403


def test_artifact_grouping_preserves_products_and_ignores_stale_and_foreign(tmp_path):
    config=Settings(database_path=str(tmp_path/'tester-artifacts.db'),report_origin=h.ORIGIN)
    with TestClient(create_demo_app(config),base_url=h.ORIGIN) as c:
        cid,sid=h.customer_session(c)
        _,other=h.customer_session(c,cid)
        async def check():
            async with c.app.state.session_factory() as db:
                store=Store(db)
                async def add(cap,product,tag,second,status='ok',revision=1,owner=sid):
                    return await store.add(Artifact(session_id=owner,tool_name='calculate_finance',
                        input_hash=tag,source_revision=revision,status=status,created_at=f'2026-09-20T00:00:{second:02d}Z',
                        output={'report_module':{'type':'finance','status':'mock','source_refs':[],
                            'data':{'capture_id':cap,'product_id':product,'tag':tag}}}))
                old=await add('A','p1','A-p1-old',1)
                new=await add('A','p1','A-p1-new',2)
                p2=await add('A','p2','A-p2',3)
                b=await add('B','p1','B-p1',4)
                await add('A','p1','stale',5,status='stale')
                await add('A','p1','wrong-revision',6,revision=2)
                await add('A','p1','foreign',7,owner=other)
                svc=ReportService(store,config)
                report,used=await svc.build_data(sid)
                assert set(used)=={new.id,p2.id,b.id}
                assert {m['data']['tag'] for m in report['modules'] if m['type']=='finance'}=={'A-p1-new','A-p2','B-p1'}
                explicit,used=await svc.build_data(sid,artifact_ids=[old.id,p2.id])
                assert set(used)=={old.id,p2.id}
                assert {m['data']['tag'] for m in explicit['modules'] if m['type']=='finance'}=={'A-p1-old','A-p2'}
        c.portal.call(check)


def test_report_calculations_match_independent_decimal_arithmetic(tmp_path):
    config=Settings(database_path=str(tmp_path/'tester-math.db'),report_origin=h.ORIGIN)
    provider=h.Replay()
    with TestClient(create_demo_app(config,provider=provider),base_url=h.ORIGIN) as c:
        _,sid=h.customer_session(c)
        aid,_=h.capture(c,sid,'20')
        h.patch_facts(c,sid,{'monthly_budget':333333,'annual_mileage':12345,'holding_years':4,
            'energy_consumption':17.4,'electricity_price':1.35,'fuel_consumption':8.6,'fuel_price':7.8})
        draft=h.prepare(c,sid,provider,(
            ('calculate_finance',{'capture_id':aid,'product_id':'mock-zero-60','terms_months':[48],
                                  'monthly_cap_fen':333333}),
            ('calculate_energy',{'annual_km':12345,'years':4,'kwh_per_100km':17.4,
                'electricity_yuan_per_kwh':1.35,'liters_per_100km':8.6,'fuel_yuan_per_liter':7.8,
                'source':'隔离验收独立数学输入'})))
        modules=draft['report_data']['modules']
        finance=next(m for m in modules if m['type']=='finance')
        solution=finance['data']['solutions'][0]
        assert finance['status']=='mock'
        assert solution['principal_fen']==333333*48
        assert solution['down_payment_fen']==32150000-333333*48
        assert solution['monthly_payment_fen']==solution['last_payment_fen']==333333
        energy=next(m for m in modules if m['type']=='energy')
        assert energy['status']=='estimate'
        expected=(Decimal('12345')*(Decimal('8.6')*Decimal('7.8')-Decimal('17.4')*Decimal('1.35'))*4).quantize(Decimal('1'),rounding=ROUND_HALF_UP)
        assert energy['data']['series'][-1]['saving_fen']==int(expected)
