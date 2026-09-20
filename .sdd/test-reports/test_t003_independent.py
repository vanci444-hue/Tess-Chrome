"""T003 Tester 独立边界用例，所有业务数据在 pytest tmp_path。"""
import asyncio
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location("core_helpers", ROOT / "backend/tests/core/test_core.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
from src.config.settings import Settings
from src.main import create_app
from src.repositories.store import Store


@pytest.fixture
def client(tmp_path):
    config = Settings(database_path=str(tmp_path / "tester.db"), upload_dir=str(tmp_path / "uploads"))
    with TestClient(create_app(config), base_url="http://127.0.0.1:8003") as c:
        yield c


def test_amount_assignment_cannot_be_swapped_in_summary(client):
    sid = helper.session(client, helper.customer(client)["id"])["id"]
    helper.capture(client, sid)
    old = {"comparing": "Model Y", "confirmed": ["月供4027元，预算4000元"], "pending": []}
    draft = helper.make_draft(client, sid, 2, old)
    response = helper.patch(client, f"/api/sessions/{sid}/drafts/{draft['id']}", {
        "expected_revision": 2, "draft_revision": 1,
        "summary": {**old, "confirmed": ["月供4000元，预算4027元"]}})
    assert response.status_code == 400, f"amount reassignment accepted HTTP {response.status_code}"


def test_accepted_international_contact_hidden_from_report(client):
    phone = "+12025550123"  # reserved fictional test contact, not user data
    customer = helper.data(helper.post(client, "/api/customers", {
        "nickname": "测试客户", "phone": phone, "identity_confirmed": True}), 201)
    sid = helper.session(client, customer["id"])["id"]
    helper.capture(client, sid)
    draft = helper.make_draft(client, sid, 2, {"comparing": "Model Y",
        "confirmed": [], "pending": ["后续通过 " + phone + " 联系确认后排体验"]})
    pub = helper.data(helper.publish(client, sid, draft, 2), 201)
    report = helper.data(client.get(f"/api/reports/{pub['report_id']}"))
    assert phone not in json.dumps(report), "accepted contact remains in published report body"


def test_publish_rollback_no_orphan_and_retry_single_card(client, monkeypatch):
    sid = helper.session(client, helper.customer(client)["id"])["id"]
    helper.capture(client, sid)
    draft = helper.make_draft(client, sid, 2)
    key = str(uuid4())
    original = Store.timeline
    async def fail_card(self, *args, **kwargs):
        raise RuntimeError("tester simulated card persistence failure")
    monkeypatch.setattr(Store, "timeline", fail_card)
    assert helper.publish(client, sid, draft, 2, key).status_code == 500
    detail = helper.data(client.get(f"/api/sessions/{sid}"))
    assert detail["reports"] == [] and detail["timeline"] == []
    monkeypatch.setattr(Store, "timeline", original)
    pub = helper.data(helper.publish(client, sid, draft, 2, key), 201)
    assert helper.data(helper.publish(client, sid, draft, 2, key), 201) == pub
    detail = helper.data(client.get(f"/api/sessions/{sid}"))
    assert len(detail["reports"]) == len(detail["timeline"]) == 1


def test_crm_external_wait_does_not_block_manual_customer(client):
    entered, release = Event(), Event()
    async def extractor(text, config):
        assert not client.app.state.write_lock.locked()
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.01)
        return {"proposed": {"nickname": "CRM预览", "email": "preview@example.com"}, "historical_facts": []}
    client.app.state.crm_extractor = extractor
    with ThreadPoolExecutor(max_workers=2) as pool:
        waiting = pool.submit(helper.post, client, "/api/customers/extract", {"text": "模拟缓慢模型"})
        assert entered.wait(2)
        try:
            manual = pool.submit(helper.customer, client)
            assert manual.result(timeout=2)["nickname"] == "Evan"
        finally:
            release.set()
        helper.data(waiting.result(timeout=2))


def test_loopback_configuration_rejects_all_interfaces():
    with pytest.raises(ValueError):
        Settings(host="0.0.0.0")
