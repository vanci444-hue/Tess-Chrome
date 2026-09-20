"""隔离 SQLite 业务回归；官网夹具来自 T001 实际 Capture 证据。"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from src.config.settings import Settings
from src.db.models import Artifact, Asset, Fact, Run, new_id
from src.main import create_app
from src.repositories.store import Store
from src.services.reports import ReportService

ORIGIN = "http://127.0.0.1:5199"
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def client(tmp_path):
    config = Settings(database_path=str(tmp_path / "isolated.db"),
                      upload_dir=str(tmp_path / "uploads"), report_origin="http://127.0.0.1:8003")
    app = create_app(config)
    with TestClient(app, base_url="http://127.0.0.1:8003") as value:
        yield value


def post(client, path, body, key=None):
    return client.post(path, json=body, headers={"Origin": ORIGIN, "Idempotency-Key": key or str(uuid4())})


def patch(client, path, body):
    return client.patch(path, json=body, headers={"Origin": ORIGIN})


def data(response, status=200):
    assert response.status_code == status, response.text
    payload = response.json()
    assert payload["success"] is True and payload["error"] is None
    assert payload["request_id"]
    return payload["data"]


def customer(client, nickname="Evan", email="evan@example.com"):
    return data(post(client, "/api/customers", {"nickname": nickname, "email": email,
        "phone": None, "identity_confirmed": True}), 201)


def session(client, customer_id):
    return data(post(client, "/api/sessions", {"customer_id": customer_id, "title": "本次 Model Y 试驾",
                                             "visit_at": None}), 201)


def capture_payload(filename="tester-0.1.1-awd-white20.json"):
    raw = json.loads((ROOT / "docs/evidence/capture-spike" / filename).read_text())
    keys = {"source_url", "captured_at", "adapter_version", "page_fingerprint", "readiness", "fields", "issues"}
    return {key: value for key, value in raw.items() if key in keys}


def capture(client, sid, revision=1, filename="tester-0.1.1-awd-white20.json"):
    return data(post(client, f"/api/sessions/{sid}/captures",
                     {"expected_revision": revision, "capture": capture_payload(filename)}), 201)


def make_draft(client, sid, revision, summary=None):
    async def save():
        async with client.app.state.session_factory() as db:
            result = await ReportService(Store(db), client.app.state.settings).save_draft(sid, revision, summary)
            await db.commit()
            return result
    return client.portal.call(save)


def publish(client, sid, draft, revision, key=None):
    return post(client, f"/api/sessions/{sid}/reports", {"draft_id": draft["id"],
        "draft_revision": draft["draft_revision"], "expected_revision": revision,
        "review_confirmed": True}, key)


def mutate_db(client, callback):
    async def run():
        async with client.app.state.session_factory() as db:
            await callback(Store(db))
            await db.commit()
    client.portal.call(run)


def test_identity_soft_duplicate_and_multiple_visits(client):
    first = customer(client)
    same = post(client, "/api/customers", {"nickname": "Evan再次到店", "email": "EVAN@example.com",
                                         "identity_confirmed": True})
    assert same.status_code == 409
    assert same.json()["metadata"]["reason"] == "DUPLICATE_CONTACT"
    assert "evan@example.com" not in json.dumps(same.json())
    second = customer(client, "Evan", "another@example.com")
    override = data(post(client, "/api/customers", {"nickname": "独立客户", "email": "evan@example.com",
                        "identity_confirmed": True, "allow_duplicate": True}), 201)
    assert len({first["id"], second["id"], override["id"]}) == 3
    visit = session(client, first["id"])
    capture(client, visit["id"])
    another = session(client, first["id"])
    assert data(client.get(f"/api/sessions/{another['id']}"))["captures"] == []
    old = data(client.get(f"/api/sessions/{visit['id']}"))
    assert len(old["captures"]) == 1 and old["trial_vehicle"] is None
    assert old["customer"]["revision"] == first["revision"]


def test_capture_two_real_configurations_immutable_limit_and_idempotence(client):
    sid = session(client, customer(client)["id"])["id"]
    first = capture(client, sid)
    assert first["validity"] == "valid"
    second = capture(client, sid, 2, "tester-0.1.1-awd-white19.json")
    assert second["validity"] == "valid"
    detail = data(client.get(f"/api/sessions/{sid}"))
    a, b = detail["captures"]
    prices = [{f["key"]: f["value"] for f in row["immutable_payload"]["fields"]}["vehicle_price"]
              for row in (a, b)]
    assert prices == [32150000, 31350000]
    assert a["immutable_payload"]["captured_at"] != b["immutable_payload"]["captured_at"]
    key = str(uuid4())
    body = {"expected_revision": 3, "capture": capture_payload()}
    r1 = data(post(client, f"/api/sessions/{sid}/captures", body, key), 201)
    r2 = data(post(client, f"/api/sessions/{sid}/captures", body, key), 201)
    assert r1 == r2
    extra = post(client, f"/api/sessions/{sid}/captures", {**body, "expected_revision": 4})
    assert extra.status_code == 409 and extra.json()["metadata"]["reason"] == "CANDIDATE_LIMIT"
    readonly = patch(client, f"/api/sessions/{sid}/captures/{a['id']}",
                     {"expected_revision": 4, "vehicle_price": 1})
    assert readonly.status_code == 400
    removed = data(patch(client, f"/api/sessions/{sid}/captures/{a['id']}",
                         {"expected_revision": 4, "active": False}))
    assert removed["revision"] == 5
    final = data(client.get(f"/api/sessions/{sid}"))
    assert final["captures"][0]["immutable_payload"] == a["immutable_payload"]


def test_publish_snapshot_double_click_restart_and_identity_privacy(client):
    c = customer(client)
    sid = session(client, c["id"])["id"]
    capture(client, sid)
    draft = make_draft(client, sid, 2)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: publish(client, sid, draft, 2, key), range(2)))
    first, retry = [data(r, 201) for r in responses]
    assert first == retry
    # 即使页面重开生成新 key，同一审核修订也只生成一张卡片。
    assert data(publish(client, sid, draft, 2), 201) == first
    report = data(client.get(f"/api/reports/{first['report_id']}"))
    option = next(m for m in report["modules"] if m["type"] == "options")
    fields = {f["key"]: f["value"] for f in option["data"]["options"][0]["fields"]}
    assert fields["vehicle_price"] == 32150000 and fields["variant"] == "长续航全轮驱动版"
    assert "evan@example.com" not in json.dumps(report)
    assert first["url"].startswith("http://127.0.0.1:8003/reports/")
    old_time = report["sources"][0]["observed_at"]
    data(patch(client, f"/api/customers/{c['id']}", {"expected_revision": 1,
        "nickname": "Evan先生", "identity_confirmed": True}))
    assert data(client.get(f"/api/reports/{first['report_id']}")) == report
    history = data(client.get(f"/api/customers/{c['id']}/reports"))
    assert len(history["items"]) == 1 and history["items"][0]["url"] == first["url"]
    detail = data(client.get(f"/api/sessions/{sid}"))
    assert len([m for m in detail["timeline"] if m["type"] == "report_card"]) == 1
    assert report["sources"][0]["observed_at"] == old_time
    # 新应用实例重新读取同一物理库，验证不是内存缓存。
    new_app = create_app(client.app.state.settings)
    with TestClient(new_app, base_url="http://127.0.0.1:8003") as restarted:
        assert data(restarted.get(f"/api/reports/{first['report_id']}")) == report


def test_revision_stale_artifact_and_auxiliary_missing(client):
    sid = session(client, customer(client)["id"])["id"]
    capture(client, sid)
    async def seed(store):
        await store.add(Artifact(session_id=sid, tool_name="energy", input_hash="test",
            source_revision=2, output={}, status="ready"))
    mutate_db(client, seed)
    draft = make_draft(client, sid, 2)
    update = data(patch(client, f"/api/sessions/{sid}/context", {"expected_revision": 2,
        "changes": [{"key": "monthly_budget", "value": 400000, "state": "confirmed", "supersedes": []}]}))
    assert update["invalidated_artifact_ids"]
    blocked = publish(client, sid, draft, 3)
    assert blocked.status_code == 409 and blocked.json()["metadata"]["reason"] == "STALE_DRAFT"
    draft2 = make_draft(client, sid, 3)
    result = data(publish(client, sid, draft2, 3), 201)
    report = data(client.get(f"/api/reports/{result['report_id']}"))
    assert next(m for m in report["modules"] if m["type"] == "charging")["status"] == "missing"


def test_conflicting_facts_block_until_explicit_supersedes(client):
    sid = session(client, customer(client)["id"])["id"]
    capture(client, sid)
    async def seed(store):
        await store.add(Fact(session_id=sid, key="monthly_budget", value=500000, state="conflict",
                             source_kind="sales_input", source_id=sid))
    mutate_db(client, seed)
    draft = make_draft(client, sid, 2)
    assert publish(client, sid, draft, 2).status_code == 409
    fact = data(client.get(f"/api/sessions/{sid}"))["facts"][0]
    data(patch(client, f"/api/sessions/{sid}/context", {"expected_revision": 2,
        "changes": [{"key": "monthly_budget", "value": 400000, "state": "confirmed",
                     "supersedes": [fact["id"]], "evidence_note": "销售二次确认"}]}))
    detail = data(client.get(f"/api/sessions/{sid}"))
    assert len(detail["facts"]) == 2 and detail["facts"][0]["value"] == 500000
    data(publish(client, sid, make_draft(client, sid, 3), 3), 201)


def test_history_requires_current_confirmation_and_no_candidate_trial_inheritance(client):
    c = customer(client)
    sid = session(client, c["id"])["id"]
    data(patch(client, f"/api/sessions/{sid}/context", {"expected_revision": 1, "changes": [
        {"key": "monthly_budget", "value": 400000, "state": "confirmed", "supersedes": []}]}))
    other = session(client, c["id"])["id"]
    capture(client, other)
    detail = data(client.get(f"/api/sessions/{other}"))
    assert detail["facts"][0]["scope"] == "historical"
    assert detail["trial_vehicle"] is None
    cross = patch(client, f"/api/sessions/{other}/context", {"expected_revision": 2, "changes": [
        {"key": "monthly_budget", "value": 400000, "state": "confirmed",
         "supersedes": [detail["facts"][0]["id"]]}]})
    assert cross.status_code == 404


def test_summary_numbers_readonly_but_wording_can_change(client):
    sid = session(client, customer(client)["id"])["id"]
    capture(client, sid)
    draft = make_draft(client, sid, 2, {"comparing": "Model Y 当前方案", "confirmed": ["预算4000元"], "pending": []})
    unchanged = patch(client, f"/api/sessions/{sid}/drafts/{draft['id']}", {"expected_revision": 2,
        "draft_revision": 1, "summary": {"comparing": "Model Y 候选方案", "confirmed": ["预算4000元"], "pending": []}})
    data(unchanged)
    changed = patch(client, f"/api/sessions/{sid}/drafts/{draft['id']}", {"expected_revision": 2,
        "draft_revision": 2, "summary": {"comparing": "Model Y 候选方案", "confirmed": ["当前预算1000元"], "pending": []}})
    assert changed.status_code == 400 and changed.json()["error_code"] == "READONLY_RESULT"


def test_security_envelope_health_missing_and_crm_no_fake_model(client):
    health = data(client.get("/api/health"))
    assert health["status"] == "degraded" and set(health["capabilities"].values()) == {"missing"}
    assert "key" not in json.dumps(health).lower()
    assert health["demo_advisor"]["name"] == "Alex"
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/api/health", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/customers", json={}).status_code == 403
    invalid = post(client, "/api/customers", {"nickname": "秘密邮箱@example.com", "identity_confirmed": False})
    assert invalid.status_code == 400
    assert invalid.json()["success"] is False
    crm = post(client, "/api/customers/extract", {"text": "真实业务预览未配置"})
    assert crm.status_code == 503 and crm.json()["error_code"] == "DEPENDENCY_UNAVAILABLE"
    bad_json = client.post("/api/customers", content="not-json", headers={"Origin": ORIGIN,
        "Content-Type": "application/json", "Idempotency-Key": str(uuid4())})
    assert bad_json.status_code == 400 and "input" not in bad_json.json()["metadata"]
    preflight = client.options("/api/customers", headers={"Origin": ORIGIN,
        "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type,Idempotency-Key"})
    assert preflight.status_code == 200 and preflight.headers["access-control-allow-origin"] == ORIGIN


def test_asset_scope_path_traversal_and_mock_private_filter(client, tmp_path):
    sid = session(client, customer(client)["id"])["id"]
    capture(client, sid)
    report = data(publish(client, sid, make_draft(client, sid, 2), 2), 201)
    events = data(post(client, f"/api/sessions/{sid}/events",
        {"expected_revision": 2, "fixture_id": "family-charging-followup"}))
    assert len(events["event_ids"]) == 2
    assert "私人内容测试哨兵" not in client.get(f"/api/sessions/{sid}").text
    asset_id = new_id()
    async def seed(store):
        await store.add(Asset(id=asset_id, session_id=sid, report_refs=[report["report_id"]],
            relative_path="../secret.png", mime="image/png", sha256="test", captured_at="2026-09-20T00:00:00Z"))
    mutate_db(client, seed)
    assert client.get(f"/api/sessions/{sid}/assets/{asset_id}").status_code == 404
    assert client.get(f"/api/reports/{report['report_id']}/assets/{asset_id}").status_code == 404


def test_run_partial_unique_index_and_restart_interruption(client):
    sid = session(client, customer(client)["id"])["id"]
    run_id = new_id()
    async def seed(store):
        await store.add(Run(id=run_id, session_id=sid, kind="analyze", root_run_id=run_id,
                            input_revision=1, current_revision=1, status="running"))
    mutate_db(client, seed)
    with TestClient(create_app(client.app.state.settings), base_url="http://127.0.0.1:8003") as restarted:
        assert data(restarted.get(f"/api/sessions/{sid}"))["active_run"] is None
    async def check(store):
        run = await store.require(Run, run_id, sid)
        assert run.status == "interrupted" and run.error["code"] == "PROCESS_RESTARTED"
    mutate_db(client, check)


def test_crm_two_phase_preview_idempotent_does_not_create_customer(client):
    calls = []
    async def extractor(text, config):
        assert not client.app.state.write_lock.locked()
        calls.append(text)
        return {"proposed": {"nickname": "CRM客户", "phone": None, "email": "crm@example.com"},
                "historical_facts": []}
    client.app.state.crm_extractor = extractor
    key = str(uuid4())
    body = {"text": "CRM 客户必要信息"}
    preview = data(post(client, "/api/customers/extract", body, key))
    assert data(post(client, "/api/customers/extract", body, key)) == preview
    assert calls == [body["text"]]
    assert data(client.get("/api/customers"))["items"] == []
    c = data(post(client, "/api/customers", {**preview["proposed"],
        "extraction_id": preview["extraction_id"], "identity_confirmed": True}), 201)
    assert c["nickname"] == "CRM客户"
    different = post(client, "/api/customers/extract", {"text": "不同文本"}, key)
    assert different.status_code == 409 and len(calls) == 1


def test_capture_invalid_source_dictionary_and_finance_conflict(client):
    sid = session(client, customer(client)["id"])["id"]
    cap = capture_payload()
    cap["source_url"] = "https://www.tesla.cn:invalid/modely/design"
    assert post(client, f"/api/sessions/{sid}/captures", {"expected_revision": 1, "capture": cap}).status_code == 400
    cap = capture_payload()
    for field in cap["fields"]:
        if field["key"] == "principal":
            field["value"] -= 100000
    saved = data(post(client, f"/api/sessions/{sid}/captures", {"expected_revision": 1, "capture": cap}), 201)
    assert saved["validity"] == "conflict"
    assert publish(client, sid, make_draft(client, sid, 2), 2).status_code == 409
    cap = capture_payload()
    for field in cap["fields"]:
        if field["key"] == "variant":
            field["evidence"]["kind"] = "initial_dictionary"
    incomplete = data(post(client, f"/api/sessions/{sid}/captures", {"expected_revision": 2, "capture": cap}), 201)
    assert incomplete["validity"] == "incomplete"


def test_capture_accepts_extras_and_option_surcharges(client):
    sid = session(client, customer(client)["id"])["id"]
    cap = capture_payload()
    stamp = cap["fields"][0]["observed_at"]
    evidence = {"kind": "dom_selected", "selector_hint": "selected extras"}
    cap["fields"].extend([
        {"key": "extras", "value": ["特斯拉辅助驾驶套件"], "unit": None,
         "raw_text": "特斯拉辅助驾驶套件", "evidence": evidence, "observed_at": stamp},
        {"key": "option_surcharges", "value": [
            {"group": "paint", "name": "珍珠白车漆", "amount": 1200000, "included": False},
            {"group": "wheels", "name": "19 英寸轮毂", "amount": 0, "included": True},
        ], "unit": None, "raw_text": "珍珠白车漆 1200000", "evidence": evidence, "observed_at": stamp},
    ])
    saved = data(post(client, f"/api/sessions/{sid}/captures", {"expected_revision": 1, "capture": cap}), 201)
    keys = {field["key"] for field in data(client.get(f"/api/sessions/{sid}"))["captures"][0]["immutable_payload"]["fields"]}
    assert saved["validity"] in {"valid", "incomplete", "conflict"}
    assert {"extras", "option_surcharges"} <= keys


@pytest.mark.parametrize("replacement", [
    {"comparing": "Model Y", "confirmed": ["月供4000元，预算4027元"], "pending": []},
    {"comparing": "Model Y", "confirmed": ["预算4027元，月供4000元"], "pending": []},
    {"comparing": "Model Y", "confirmed": [], "pending": ["月供4027元，预算4000元"]},
    {"comparing": "Model Y", "confirmed": ["已解决", "月供4027元，预算4000元"], "pending": []},
    {"comparing": "Model Y", "confirmed": ["当前月供4027元，预算4000元"], "pending": []},
])
def test_numeric_statement_and_summary_location_are_readonly(client, replacement):
    sid = session(client, customer(client)["id"])["id"]
    capture(client, sid)
    summary = {"comparing": "Model Y", "confirmed": ["月供4027元，预算4000元"], "pending": []}
    draft = make_draft(client, sid, 2, summary)
    response = patch(client, f"/api/sessions/{sid}/drafts/{draft['id']}", {
        "expected_revision": 2, "draft_revision": 1, "summary": replacement})
    assert response.status_code == 400 and response.json()["error_code"] == "READONLY_RESULT"
    stored = data(client.get(f"/api/sessions/{sid}"))["draft"]
    assert stored["report_data"]["summary"] == summary and stored["draft_revision"] == 1


def test_chinese_amount_statement_cannot_be_reassigned(client):
    sid = session(client, customer(client)["id"])["id"]
    capture(client, sid)
    draft = make_draft(client, sid, 2, {"comparing": "Model Y", "confirmed": ["月供四千，预算五千"], "pending": []})
    response = patch(client, f"/api/sessions/{sid}/drafts/{draft['id']}", {"expected_revision": 2,
        "draft_revision": 1, "summary": {"comparing": "Model Y", "confirmed": ["预算四千，月供五千"], "pending": []}})
    assert response.status_code == 400


@pytest.mark.parametrize("display", ["+12025550123", "+1 202 555 0123", "+1-202-555-0123",
                                     "+1 (202) 555-0123", "0012025550123", "12025550123"])
def test_known_international_identity_redacted_build_update_publish(client, display):
    c = data(post(client, "/api/customers", {"nickname": "隔离测试", "phone": "+1 202-555-0123",
        "email": "contact@example.com", "identity_confirmed": True}), 201)
    sid = session(client, c["id"])["id"]
    capture(client, sid)
    draft = make_draft(client, sid, 2, {"comparing": "Model Y", "confirmed": ["月供4027元"],
        "pending": ["通过 " + display + " 或 CONTACT@example.com 确认后排体验"]})
    text = json.dumps(draft["report_data"], ensure_ascii=False)
    assert display not in text and "CONTACT@example.com" not in text
    edited = patch(client, f"/api/sessions/{sid}/drafts/{draft['id']}", {"expected_revision": 2,
        "draft_revision": 1, "summary": {"comparing": "Model Y 当前候选", "confirmed": ["月供4027元"],
            "pending": ["请通过 " + display + " 联系确认后排体验"]}})
    data(edited)
    revised = data(client.get(f"/api/sessions/{sid}"))["draft"]
    assert display not in json.dumps(revised["report_data"], ensure_ascii=False)
    # 直接污染存储模拟旧草稿，验证 publish 自身也执行已知身份投影。
    async def seed_old_draft(store):
        from src.db.models import Draft
        row = await store.require(Draft, draft["id"], sid)
        row.report_data = {**row.report_data, "summary": {**row.report_data["summary"],
            "pending": ["旧草稿联系方式 " + display]}}
    mutate_db(client, seed_old_draft)
    published = data(publish(client, sid, revised, 2), 201)
    report = data(client.get(f"/api/reports/{published['report_id']}"))
    assert display not in json.dumps(report, ensure_ascii=False)
    fields = next(module for module in report["modules"] if module["type"] == "options")["data"]["options"][0]["fields"]
    assert next(field for field in fields if field["key"] == "vehicle_price")["value"] == 32150000
    assert report["summary"]["confirmed"] == ["月供4027元"]


def test_charging_search_needed_and_unknown_support():
    from src.services.facts import charging_search_needed, unknown_support

    region = {"id": "r", "key": "region", "value": "望京地铁站", "state": "confirmed",
              "scope": "session", "supersedes": []}
    assert charging_search_needed([
        region,
        {"id": "p", "key": "has_fixed_parking", "value": False, "state": "confirmed",
         "scope": "session", "supersedes": []},
    ])
    assert not charging_search_needed([
        region,
        {"id": "p", "key": "has_fixed_parking", "value": True, "state": "confirmed",
         "scope": "session", "supersedes": []},
        {"id": "h", "key": "home_charging", "value": "已安装", "state": "confirmed",
         "scope": "session", "supersedes": []},
    ])
    hints = unknown_support([
        {"id": "u", "key": "home_charging", "value": None, "state": "unknown",
         "scope": "session", "supersedes": []},
    ])
    assert hints[0]["key"] == "home_charging" and "超充" in hints[0]["message"]
