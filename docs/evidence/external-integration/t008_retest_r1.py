"""T-008 retry-1 independent Tester retest. Isolated SQLite; real Qwen/Amap; no 8099 kill."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from src.config.settings import Settings, load_settings
from src.main import create_demo_app

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PORT = 18108
ORIGIN = f"http://127.0.0.1:{PORT}"
RUN_WAIT = 180
PHONE = "13900139108"
EMAIL = "qa-t008-r1@example.com"
PHONE_B = "13900139109"
EMAIL_B = "qa-t008-r1b@example.com"
PHONE_C = "13900139110"
EMAIL_C = "qa-t008-r1c@example.com"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    text = json.dumps(value, ensure_ascii=False, default=str)
    text = re.sub(r"(?i)(sk-|Bearer |key=)[A-Za-z0-9._\-]+", r"\1REDACTED", text)
    for secret in (PHONE, EMAIL, PHONE_B, EMAIL_B, PHONE_C, EMAIL_C):
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"1[3-9]\d{9}", "[PHONE]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    return json.loads(text)


def request(client, method, path, body=None, status=None, key=None):
    response = client.request(
        method,
        path,
        json=body,
        headers={"Origin": ORIGIN, "Idempotency-Key": key or str(uuid4())},
        timeout=70,
    )
    if status is not None and response.status_code != status:
        raise AssertionError(f"{method} {path} -> {response.status_code} {response.text[:800]}")
    return response.status_code, response.json()


def data_ok(client, method, path, body=None, status=200, key=None):
    code, payload = request(client, method, path, body, status=status, key=key)
    if not payload.get("success"):
        raise AssertionError(f"{method} {path} failed: {payload}")
    return payload["data"]


def detail(client, sid):
    return data_ok(client, "GET", f"/api/sessions/{sid}")


def wait_run(client, sid, rid, timeout=RUN_WAIT):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = data_ok(client, "GET", f"/api/sessions/{sid}/runs/{rid}")
        if last["status"] not in ("queued", "running"):
            return last
        time.sleep(1)
    raise TimeoutError(f"run {rid} still {last and last['status']}")


def capture(client, sid):
    raw = json.loads((ROOT / "docs/evidence/capture-spike/tester-0.1.1-awd-white20.json").read_text())
    payload = {
        key: raw[key]
        for key in (
            "source_url",
            "captured_at",
            "adapter_version",
            "page_fingerprint",
            "readiness",
            "fields",
            "issues",
        )
    }
    payload["issues"] = [
        {**{k: v for k, v in issue.items() if k != "severity"}, "blocking": issue.get("severity") == "blocking"}
        for issue in payload["issues"]
    ]
    return data_ok(
        client,
        "POST",
        f"/api/sessions/{sid}/captures",
        {"expected_revision": detail(client, sid)["revision"], "capture": payload},
        status=201,
    )


def current_facts(session):
    superseded = {ref for fact in session["facts"] for ref in fact.get("supersedes") or []}
    return [
        fact
        for fact in session["facts"]
        if fact["id"] not in superseded and fact.get("scope") == "session"
    ]


def confirm(client, sid, values, *, unknown=(), skip_optional=False, reply=None):
    session = detail(client, sid)
    facts = current_facts(session)
    changes = []
    for key, value in values.items():
        refs = [f["id"] for f in facts if f["key"] == key]
        changes.append(
            {
                "key": key,
                "value": value,
                "state": "confirmed",
                "supersedes": refs,
                "evidence_note": "T008 r1 QA 确认",
            }
        )
    for key in unknown:
        refs = [f["id"] for f in facts if f["key"] == key]
        changes.append(
            {
                "key": key,
                "value": None,
                "state": "unknown",
                "supersedes": refs,
                "evidence_note": "销售回复不知道",
            }
        )
    body = {
        "expected_revision": session["revision"],
        "changes": changes,
        "skip_optional_questions": skip_optional,
    }
    if reply:
        body.update(reply)
    return data_ok(client, "PATCH", f"/api/sessions/{sid}/context", body)


def submit_text(client, sid, text, source="sales_text"):
    run = data_ok(
        client,
        "POST",
        f"/api/sessions/{sid}/inputs",
        {"text": text, "source": source, "expected_revision": detail(client, sid)["revision"]},
        status=202,
    )
    return wait_run(client, sid, run["run_id"])


def start_run(client, sid, intent, continue_run_id=None, message=None):
    body = {
        "intent": intent,
        "message": message,
        "expected_revision": detail(client, sid)["revision"],
    }
    if continue_run_id:
        body["continue_run_id"] = continue_run_id
    run = data_ok(client, "POST", f"/api/sessions/{sid}/runs", body, status=202)
    return wait_run(client, sid, run["run_id"])


def tool_names(run):
    return [e.get("tool_name") for e in run.get("events") or [] if e.get("tool_name")]


def charging_artifacts(session):
    items = []
    for art in session.get("artifacts") or []:
        if art.get("tool_name") != "search_charging":
            continue
        output = art.get("output") or {}
        data = output.get("data") or output
        items.append(data)
    return items


def pick_wangjing(candidates):
    named = [c for c in candidates if "望京" in (c.get("name") or "") and "地铁" in (c.get("name") or "")]
    return (named or candidates)[0] if candidates else None


def continue_location(client, sid, run):
    session = detail(client, sid)
    facts = current_facts(session)
    proposed = [f for f in facts if f["key"] == "confirmed_location_ref" and f["state"] == "proposed"]
    candidates = []
    for data in charging_artifacts(session):
        candidates.extend(data.get("candidates") or [])
    chosen = pick_wangjing(candidates)
    questions = (run.get("result") or {}).get("questions") or []
    if not questions:
        questions = (session.get("pending_run") or {}).get("questions") or []
    reply = {"reply_to_run_id": run["run_id"]}
    if questions:
        reply["reply_to_question_ids"] = [q["id"] for q in questions if q.get("id")]
    values = {}
    if proposed:
        values["confirmed_location_ref"] = proposed[0]["value"]
    elif chosen:
        values["confirmed_location_ref"] = chosen["id"]
    confirm(client, sid, values, skip_optional=True, reply=reply)
    return start_run(client, sid, run.get("kind") or "prepare_report", continue_run_id=run["run_id"])


def save(name, payload):
    path = EVIDENCE / name
    path.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n")
    return str(path)


def http_server(config):
    app = create_demo_app(config)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning", access_log=False)
    )
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 15
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError(f"isolated QA server did not start on {PORT}")
    return server, worker


def main():
    results = {
        "started_at": utcnow(),
        "origin": ORIGIN,
        "git_head": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT)
        .decode()
        .strip(),
        "provider": "real",
        "cases": {},
        "errors": [],
    }
    base = load_settings()
    results["config_presence"] = {
        "bailian_api_key": bool(base.bailian_api_key),
        "bailian_base_url": bool(base.bailian_base_url),
        "bailian_asr_ws_url": bool(base.bailian_asr_ws_url),
        "amap_web_service_key": bool(base.amap_web_service_key),
        "llm_model": base.llm_model,
        "asr_model": base.asr_model,
        "uvicorn_standard_requirement": "uvicorn[standard]==0.53.0"
        in (ROOT / "backend/requirements.txt").read_text(),
    }
    prod_db = ROOT / "backend/data/tess-chrome.db"
    results["prod_db_before"] = {
        "exists": prod_db.exists(),
        "size": prod_db.stat().st_size if prod_db.exists() else 0,
    }
    health_prod = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()
    results["prod_8099_before"] = {
        "status": (health_prod.get("data") or {}).get("status"),
        "capabilities": (health_prod.get("data") or {}).get("capabilities"),
    }
    tmp = Path(tempfile.mkdtemp(prefix="t008-r1-"))
    config = Settings(
        database_path=str(tmp / "qa.db"),
        upload_dir=str(tmp / "uploads"),
        port=PORT,
        report_origin=ORIGIN,
        bailian_base_url=base.bailian_base_url,
        bailian_api_key=base.bailian_api_key,
        bailian_asr_ws_url=base.bailian_asr_ws_url,
        llm_model=base.llm_model,
        asr_model=base.asr_model,
        amap_web_service_key=base.amap_web_service_key,
        amap_base_url=base.amap_base_url,
        frontend_dist=base.frontend_dist,
        allowed_extension_origin=base.allowed_extension_origin,
    )
    server, worker = http_server(config)
    try:
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=70) as client:

            def remember(error, where):
                results["errors"].append(
                    {"where": where, "type": type(error).__name__, "message": str(error)[:500]}
                )

            health = data_ok(client, "GET", "/api/health")
            results["isolated_health"] = {
                "status": health["status"],
                "capabilities": health["capabilities"],
            }

            # AC-022 spot check
            try:
                preview = data_ok(
                    client,
                    "POST",
                    "/api/customers/extract",
                    {
                        "text": (
                            f"客户称呼 QA复验甲；手机 {PHONE}；邮箱 {EMAIL}；"
                            "此前沟通月供目标四千左右。"
                        )
                    },
                )
                missing = data_ok(
                    client,
                    "POST",
                    "/api/customers/extract",
                    {"text": "客户称呼 QA复验乙，暂无手机和邮箱。"},
                )
                no_contact = request(
                    client,
                    "POST",
                    "/api/customers",
                    {"nickname": "QA复验乙", "identity_confirmed": True},
                )
                created = data_ok(
                    client,
                    "POST",
                    "/api/customers",
                    {
                        "nickname": preview["proposed"]["nickname"] or "QA复验甲",
                        "phone": PHONE,
                        "email": EMAIL,
                        "extraction_id": preview["extraction_id"],
                        "identity_confirmed": True,
                    },
                    status=201,
                )
                results["cases"]["ac022"] = {
                    "preview_missing": preview.get("missing"),
                    "has_contact": bool(preview["proposed"].get("phone") or preview["proposed"].get("email")),
                    "incomplete_missing": missing.get("missing"),
                    "create_without_contact_status": no_contact[0],
                    "create_without_contact_code": no_contact[1].get("error_code"),
                    "customer_id": created.get("id"),
                }
            except Exception as error:
                remember(error, "ac022")
                created = data_ok(
                    client,
                    "POST",
                    "/api/customers",
                    {
                        "nickname": "QA复验甲",
                        "phone": PHONE,
                        "email": EMAIL,
                        "identity_confirmed": True,
                    },
                    status=201,
                )
                results["cases"]["ac022"] = {"error": str(error)[:300]}

            # AC-004: official uvicorn WS upgrade (not TestClient, not Side Panel)
            try:
                session_ws = data_ok(
                    client,
                    "POST",
                    "/api/sessions",
                    {"customer_id": created["id"], "title": "T008-r1 WS", "visit_at": None},
                    status=201,
                )
                sid_ws = session_ws["id"]
                before = detail(client, sid_ws)
                audio = data_ok(
                    client,
                    "POST",
                    f"/api/sessions/{sid_ws}/audio",
                    {"expected_revision": before["revision"]},
                    status=201,
                )
                path = audio["ws_path"]
                import asyncio

                import websockets

                async def handshake():
                    url = f"ws://127.0.0.1:{PORT}{path}"
                    async with websockets.connect(
                        url,
                        additional_headers={"Origin": ORIGIN, "Host": f"127.0.0.1:{PORT}"},
                        open_timeout=8,
                    ) as ws:
                        first = await asyncio.wait_for(ws.recv(), timeout=8)
                        payload = json.loads(first) if isinstance(first, str) else {"raw": str(first)[:200]}
                        await ws.close()
                        return payload

                first = asyncio.run(handshake())
                after = detail(client, sid_ws)
                results["cases"]["ac004_ws"] = {
                    "asr_state": audio.get("state"),
                    "ws_path": path,
                    "first_event_type": first.get("type"),
                    "upgrade_ok": first.get("type") in {"ready", "partial", "error", "session.updated"}
                    or bool(first.get("type")),
                    "revision_unchanged_before_finish": after["revision"] == before["revision"],
                    "timeline_empty": not after.get("timeline"),
                    "not_testclient": True,
                    "not_side_panel": True,
                }
                save("ac004-ws-r1.json", {"audio": audio, "first": first})
            except Exception as error:
                remember(error, "ac004_ws")
                results["cases"]["ac004_ws"] = {"error": str(error)[:400], "upgrade_ok": False}

            # AC-029 A: home charging + parking skip stations; prepare draft
            try:
                session_a = data_ok(
                    client,
                    "POST",
                    "/api/sessions",
                    {"customer_id": created["id"], "title": "T008-r1 家充齐全", "visit_at": None},
                    status=201,
                )
                sid_a = session_a["id"]
                capture(client, sid_a)
                confirm(
                    client,
                    sid_a,
                    {
                        "has_fixed_parking": True,
                        "home_charging": "小区车位已安装家充",
                        "monthly_budget": 400000,
                        "region": "望京地铁站",
                        "city": "北京",
                    },
                    skip_optional=True,
                )
                run_a = start_run(client, sid_a, "prepare_report")
                loops = 0
                while run_a["status"] == "needs_confirmation" and loops < 3:
                    loops += 1
                    run_a = continue_location(client, sid_a, run_a)
                tools_a = tool_names(run_a)
                session_a_final = detail(client, sid_a)
                draft_a = session_a_final.get("draft")
                results["cases"]["ac029_skip"] = {
                    "run_status": run_a["status"],
                    "error_code": (run_a.get("error") or {}).get("code") if isinstance(run_a.get("error"), dict) else run_a.get("error"),
                    "tools": tools_a,
                    "skipped_search_charging": "search_charging" not in tools_a,
                    "has_draft": bool(draft_a),
                    "home_charging_value": next(
                        (f["value"] for f in current_facts(session_a_final) if f["key"] == "home_charging"),
                        None,
                    ),
                }
                save("ac029-skip-r1.json", {"run": run_a, "draft": bool(draft_a), "tools": tools_a})
            except Exception as error:
                remember(error, "ac029_skip")
                results["cases"]["ac029_skip"] = {"error": str(error)[:400]}

            # Session B: no parking, 望京, unknown home charging
            try:
                customer_b = data_ok(
                    client,
                    "POST",
                    "/api/customers",
                    {
                        "nickname": "QA复验丙",
                        "phone": PHONE_B,
                        "email": EMAIL_B,
                        "identity_confirmed": True,
                    },
                    status=201,
                )
                session_b = data_ok(
                    client,
                    "POST",
                    "/api/sessions",
                    {"customer_id": customer_b["id"], "title": "T008-r1 无车位望京", "visit_at": None},
                    status=201,
                )
                sid_b = session_b["id"]
                capture(client, sid_b)
                extract_b = submit_text(
                    client,
                    sid_b,
                    "客户没有固定车位，常用区域在望京地铁站附近。实际试驾的是后轮驱动，具体版本客户说不太确定。"
                    "月供希望四千左右。公司充电条件客户说不知道。",
                )
                questions_b = (extract_b.get("result") or {}).get("questions") or []
                facts_b = current_facts(detail(client, sid_b))
                confirm(
                    client,
                    sid_b,
                    {
                        "has_fixed_parking": False,
                        "region": "望京地铁站",
                        "city": "北京",
                        "monthly_budget": 400000,
                        "trial_model": "Model Y",
                    },
                    unknown=["home_charging"]
                    + [
                        f["key"]
                        for f in facts_b
                        if f["key"] == "trial_variant" and f["state"] in {"proposed", "unknown"}
                    ],
                    skip_optional=False,
                    reply={
                        "reply_to_run_id": extract_b["run_id"],
                        "reply_to_question_ids": [q["id"] for q in questions_b if q.get("id")],
                    }
                    if questions_b
                    else None,
                )
                # AC-005: unknown then still don't know
                loop_check = submit_text(client, sid_b, "公司充电条件还是不知道，请不要再问同一件事。")
                support = (loop_check.get("result") or {}).get("unknown_support") or []
                inputs = detail(client, sid_b).get("inputs") or []
                retained = any("还是不知道" in (item.get("corrected_text") or "") for item in inputs)
                results["cases"]["ac005"] = {
                    "first_extract_status": extract_b.get("status"),
                    "second_status": loop_check.get("status"),
                    "second_error": loop_check.get("error"),
                    "invalid_model_output": str(loop_check.get("error")).find("INVALID_MODEL_OUTPUT") >= 0
                    or (loop_check.get("result") or {}).get("code") == "INVALID_MODEL_OUTPUT",
                    "unknown_support": support,
                    "text_retained": retained,
                    "question_count_first": len(questions_b),
                }
                save(
                    "ac005-unknown-r1.json",
                    {
                        "first": {"status": extract_b.get("status"), "questions": questions_b[:3]},
                        "second": loop_check,
                        "inputs": inputs,
                    },
                )

                confirm(client, sid_b, {}, skip_optional=True)
                run_b = start_run(client, sid_b, "prepare_report")
                loops = 0
                while run_b["status"] == "needs_confirmation" and loops < 4:
                    loops += 1
                    run_b = continue_location(client, sid_b, run_b)
                tools_b = tool_names(run_b)
                session_b_final = detail(client, sid_b)
                draft_b = session_b_final.get("draft")
                charging_data = {}
                for data in charging_artifacts(session_b_final):
                    if data.get("stations"):
                        charging_data = data
                        break
                    charging_data = data
                stations = charging_data.get("stations") or []
                results["cases"]["ac013_029_search"] = {
                    "run_status": run_b["status"],
                    "error": run_b.get("error"),
                    "tools": tools_b,
                    "used_search_charging": "search_charging" in tools_b,
                    "has_draft": bool(draft_b),
                    "charging_state": charging_data.get("state"),
                    "station_count": len(stations),
                    "station_names": [s.get("name") for s in stations],
                    "routes": [
                        {
                            "name": s.get("name"),
                            "route_status": s.get("route_status"),
                            "driving_distance_m": s.get("driving_distance_m"),
                            "center_distance_m": s.get("center_distance_m"),
                            "distance_basis": s.get("distance_basis"),
                        }
                        for s in stations
                    ],
                    "map_status": charging_data.get("map_status"),
                    "map_asset_id": charging_data.get("map_asset_id"),
                    "distance_basis_present": any(s.get("distance_basis") or s.get("driving_distance_m") for s in stations),
                }
                trial = session_b_final.get("trial_vehicle")
                capture_variant = None
                for cap in session_b_final.get("captures") or []:
                    for field in (cap.get("immutable_payload") or cap).get("fields") or []:
                        if field.get("key") == "variant":
                            capture_variant = field.get("value") or field.get("raw_text")
                unknown_now = [f["key"] for f in current_facts(session_b_final) if f["state"] == "unknown"]
                results["cases"]["ac035_036_spot"] = {
                    "trial_vehicle": trial,
                    "capture_variant": capture_variant,
                    "unknown_keys": unknown_now,
                    "first_round_questions": len(questions_b),
                }
                save(
                    "ac007-prepare-charging-r1.json",
                    {
                        "run": {
                            "status": run_b.get("status"),
                            "tools": tools_b,
                            "error": run_b.get("error"),
                        },
                        "charging": charging_data,
                        "draft": bool(draft_b),
                    },
                )
            except Exception as error:
                remember(error, "session_b")
                results["cases"]["ac005"] = results["cases"].get("ac005") or {"error": str(error)[:400]}
                results["cases"]["ac013_029_search"] = {"error": str(error)[:400]}

            # AC-007 dedicated: confirm 望京 then search_charging via analyze if prepare did not fill
            try:
                customer_c = data_ok(
                    client,
                    "POST",
                    "/api/customers",
                    {
                        "nickname": "QA复验丁",
                        "phone": PHONE_C,
                        "email": EMAIL_C,
                        "identity_confirmed": True,
                    },
                    status=201,
                )
                session_c = data_ok(
                    client,
                    "POST",
                    "/api/sessions",
                    {"customer_id": customer_c["id"], "title": "T008-r1 望京查站", "visit_at": None},
                    status=201,
                )
                sid_c = session_c["id"]
                capture(client, sid_c)
                confirm(
                    client,
                    sid_c,
                    {
                        "has_fixed_parking": False,
                        "home_charging": False,
                        "region": "望京地铁站",
                        "city": "北京",
                        "monthly_budget": 400000,
                    },
                    skip_optional=True,
                )
                run_c = start_run(client, sid_c, "analyze", message="请查询望京充电站")
                loops = 0
                while run_c["status"] == "needs_confirmation" and loops < 4:
                    loops += 1
                    run_c = continue_location(client, sid_c, run_c)
                session_c_final = detail(client, sid_c)
                charging_c = {}
                for data in charging_artifacts(session_c_final):
                    if data.get("state") == "ready" and data.get("stations"):
                        charging_c = data
                        break
                    charging_c = data
                stations_c = charging_c.get("stations") or []
                results["cases"]["ac007"] = {
                    "run_status": run_c.get("status"),
                    "tools": tool_names(run_c),
                    "state": charging_c.get("state"),
                    "station_count": len(stations_c),
                    "station_names": [s.get("name") for s in stations_c],
                    "routes_ready": [
                        s.get("name")
                        for s in stations_c
                        if s.get("route_status") == "ready" and s.get("driving_distance_m")
                    ],
                    "map_status": charging_c.get("map_status"),
                    "map_asset_id": charging_c.get("map_asset_id"),
                    "distance_basis": list({s.get("distance_basis") for s in stations_c if s.get("distance_basis")}),
                    "external_search_has_key": "key=" in json.dumps(charging_c.get("external_search") or {}),
                }
                save("ac007-analyze-charging-r1.json", {"run": run_c, "charging": charging_c})
            except Exception as error:
                remember(error, "ac007")
                results["cases"]["ac007"] = {"error": str(error)[:400]}
    finally:
        server.should_exit = True
        worker.join(timeout=5)

    results["prod_db_after"] = {
        "exists": prod_db.exists(),
        "size": prod_db.stat().st_size if prod_db.exists() else 0,
    }
    health_prod_after = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()
    results["prod_8099_after"] = {
        "status": (health_prod_after.get("data") or {}).get("status"),
        "capabilities": (health_prod_after.get("data") or {}).get("capabilities"),
    }
    results["ended_at"] = utcnow()
    save("t008-retest-r1-summary.json", results)
    print(json.dumps(redact(results), ensure_ascii=False, indent=2))
    return results


if __name__ == "__main__":
    main()
