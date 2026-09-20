"""T-008 retry-2 independent Tester retest. Isolated SQLite; real Qwen/Amap; no 8099 kill."""
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
PORT = 18118
ORIGIN = f"http://127.0.0.1:{PORT}"
RUN_WAIT = 180
PHONE = "13900139208"
EMAIL = "qa-t008-r2@example.com"
PHONE_B = "13900139209"
EMAIL_B = "qa-t008-r2b@example.com"

DIGIT_RE = re.compile(r"\d")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    text = json.dumps(value, ensure_ascii=False, default=str)
    text = re.sub(r"(?i)(sk-|Bearer |key=)[A-Za-z0-9._\-]+", r"\1REDACTED", text)
    for secret in (PHONE, EMAIL, PHONE_B, EMAIL_B):
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
                "evidence_note": "T008 r2 QA 确认",
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


def run_questions(run, session):
    questions = (run.get("result") or {}).get("questions") or []
    if not questions:
        questions = ((session.get("pending_run") or {}).get("result") or {}).get("questions") or []
    if not questions:
        questions = (session.get("pending_run") or {}).get("questions") or []
    return questions


def continue_prepare(client, sid, run):
    session = detail(client, sid)
    facts = current_facts(session)
    proposed = [f for f in facts if f["key"] == "confirmed_location_ref" and f["state"] == "proposed"]
    candidates = []
    for data in charging_artifacts(session):
        candidates.extend(data.get("candidates") or [])
    chosen = pick_wangjing(candidates)
    questions = run_questions(run, session)
    reply = {"reply_to_run_id": run["run_id"]}
    if questions:
        reply["reply_to_question_ids"] = [q["id"] for q in questions if q.get("id")]
    values = {}
    if proposed:
        values["confirmed_location_ref"] = proposed[0]["value"]
    elif chosen:
        values["confirmed_location_ref"] = chosen["id"]
    confirm(client, sid, values, skip_optional=True, reply=reply)
    return start_run(client, sid, "prepare_report", continue_run_id=run["run_id"]), questions


def drain_prepare(client, sid, run, loops=5):
    history = []
    current = run
    for _ in range(loops):
        if current["status"] != "needs_confirmation":
            break
        session = detail(client, sid)
        questions = run_questions(current, session)
        charging_ready = any((data.get("state") == "ready" and data.get("stations")) for data in charging_artifacts(session))
        required = [q for q in questions if q.get("required")]
        history.append(
            {
                "status": current["status"],
                "required_questions": [q.get("text") for q in required],
                "optional_questions": [q.get("text") for q in questions if not q.get("required")],
                "charging_ready": charging_ready,
                "error": current.get("error"),
            }
        )
        current, _ = continue_prepare(client, sid, current)
    return current, history


def save(name, payload):
    path = EVIDENCE / name
    path.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n")
    return str(path)


def summary_blob(draft):
    data = (draft or {}).get("report_data") or {}
    summary = data.get("summary") or {}
    return json.dumps(summary, ensure_ascii=False), summary


def module_has_digits(draft, module_type):
    data = (draft or {}).get("report_data") or {}
    for module in data.get("modules") or []:
        if module.get("type") == module_type:
            return bool(DIGIT_RE.search(json.dumps(module, ensure_ascii=False))), module.get("status")
    return False, None


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
    }
    prod_db = ROOT / "backend/data/tess-chrome.db"
    results["prod_db_before"] = {
        "exists": prod_db.exists(),
        "size": prod_db.stat().st_size if prod_db.exists() else 0,
    }
    health_prod = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()
    results["prod_8099_before"] = {
        "pid_check": "not_killed",
        "status": (health_prod.get("data") or {}).get("status"),
        "capabilities": (health_prod.get("data") or {}).get("capabilities"),
    }
    tmp = Path(tempfile.mkdtemp(prefix="t008-r2-"))
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

            created = data_ok(
                client,
                "POST",
                "/api/customers",
                {
                    "nickname": "QA返工2甲",
                    "phone": PHONE,
                    "email": EMAIL,
                    "identity_confirmed": True,
                },
                status=201,
            )

            # AC-013 case A: complete home charging + parking + confirmed monthly budget
            try:
                session_a = data_ok(
                    client,
                    "POST",
                    "/api/sessions",
                    {"customer_id": created["id"], "title": "T008-r2 家充齐全", "visit_at": None},
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
                run_a, loops_a = drain_prepare(client, sid_a, run_a)
                tools_a = tool_names(run_a)
                session_a_final = detail(client, sid_a)
                draft_a = session_a_final.get("draft")
                summary_text, summary = summary_blob(draft_a)
                finance_digits, finance_status = module_has_digits(draft_a, "finance")
                results["cases"]["ac013_complete"] = {
                    "run_status": run_a["status"],
                    "error_code": (run_a.get("error") or {}).get("code")
                    if isinstance(run_a.get("error"), dict)
                    else run_a.get("error"),
                    "tools": tools_a,
                    "skipped_search_charging": "search_charging" not in tools_a,
                    "has_draft": bool(draft_a),
                    "summary_has_arabic_digits": bool(DIGIT_RE.search(summary_text)),
                    "summary": summary,
                    "finance_module_has_digits": finance_digits,
                    "finance_status": finance_status,
                    "confirmation_loops": loops_a,
                }
                save(
                    "ac013-complete-r2.json",
                    {
                        "run": {
                            "status": run_a.get("status"),
                            "tools": tools_a,
                            "error": run_a.get("error"),
                            "result": run_a.get("result"),
                        },
                        "draft": bool(draft_a),
                        "summary": summary,
                        "blocking_issues": (draft_a or {}).get("blocking_issues"),
                        "loops": loops_a,
                    },
                )
            except Exception as error:
                remember(error, "ac013_complete")
                results["cases"]["ac013_complete"] = {"error": str(error)[:400]}
                sid_a = None
                draft_a = None
                run_a = None

            # Session B: no parking + 望京; also AC-005 spot
            try:
                customer_b = data_ok(
                    client,
                    "POST",
                    "/api/customers",
                    {
                        "nickname": "QA返工2乙",
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
                    {"customer_id": customer_b["id"], "title": "T008-r2 无车位望京", "visit_at": None},
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
                loop_check = submit_text(client, sid_b, "公司充电条件还是不知道，请不要再问同一件事。")
                support = (loop_check.get("result") or {}).get("unknown_support") or []
                inputs = detail(client, sid_b).get("inputs") or []
                retained = any("还是不知道" in (item.get("corrected_text") or "") for item in inputs)
                results["cases"]["ac005"] = {
                    "first_extract_status": extract_b.get("status"),
                    "second_status": loop_check.get("status"),
                    "second_error": loop_check.get("error"),
                    "invalid_model_output": "INVALID_MODEL_OUTPUT" in str(loop_check.get("error")),
                    "unknown_support": support,
                    "text_retained": retained,
                    "question_count_first": len(questions_b),
                }
                save(
                    "ac005-unknown-r2.json",
                    {
                        "first": {"status": extract_b.get("status"), "questions": questions_b[:3]},
                        "second_status": loop_check.get("status"),
                        "second_error": loop_check.get("error"),
                        "unknown_support": support,
                    },
                )

                confirm(client, sid_b, {}, skip_optional=True)
                run_b = start_run(client, sid_b, "prepare_report")
                run_b, loops_b = drain_prepare(client, sid_b, run_b)
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
                summary_text_b, summary_b = summary_blob(draft_b)
                results["cases"]["ac013_no_parking"] = {
                    "run_status": run_b["status"],
                    "error": run_b.get("error"),
                    "tools": tools_b,
                    "used_search_charging": "search_charging" in tools_b,
                    "has_draft": bool(draft_b),
                    "charging_state": charging_data.get("state"),
                    "station_count": len(stations),
                    "station_names": [s.get("name") for s in stations],
                    "routes_ready": [
                        s.get("name")
                        for s in stations
                        if s.get("route_status") == "ready" and s.get("driving_distance_m")
                    ],
                    "map_status": charging_data.get("map_status"),
                    "map_asset_id": charging_data.get("map_asset_id"),
                    "distance_basis": list({s.get("distance_basis") for s in stations if s.get("distance_basis")}),
                    "external_search_has_key": "key=" in json.dumps(charging_data.get("external_search") or {}),
                    "summary_has_arabic_digits": bool(DIGIT_RE.search(summary_text_b)),
                    "confirmation_loops": loops_b,
                }
                results["cases"]["ac007_029_spot"] = {
                    "complete_skipped_search": results["cases"].get("ac013_complete", {}).get(
                        "skipped_search_charging"
                    ),
                    "no_parking_used_search": "search_charging" in tools_b,
                    "charging_state": charging_data.get("state"),
                    "station_count": len(stations),
                    "map_status": charging_data.get("map_status"),
                    "distance_basis": list({s.get("distance_basis") for s in stations if s.get("distance_basis")}),
                }
                save(
                    "ac013-no-parking-r2.json",
                    {
                        "run": {
                            "status": run_b.get("status"),
                            "tools": tools_b,
                            "error": run_b.get("error"),
                            "result": run_b.get("result"),
                        },
                        "charging": {
                            "state": charging_data.get("state"),
                            "station_count": len(stations),
                            "station_names": [s.get("name") for s in stations],
                            "map_status": charging_data.get("map_status"),
                            "external_search": charging_data.get("external_search"),
                            "distance_basis": list(
                                {s.get("distance_basis") for s in stations if s.get("distance_basis")}
                            ),
                        },
                        "draft": bool(draft_b),
                        "summary": summary_b,
                        "loops": loops_b,
                    },
                )
            except Exception as error:
                remember(error, "session_b")
                results["cases"]["ac005"] = results["cases"].get("ac005") or {"error": str(error)[:400]}
                results["cases"]["ac013_no_parking"] = {"error": str(error)[:400]}
                sid_b = None
                draft_b = None
                run_b = None

            # AC-020 only if a draft can be published this round
            try:
                follow_sid = None
                follow_draft = None
                follow_run = None
                if results["cases"].get("ac013_no_parking", {}).get("has_draft"):
                    follow_sid, follow_draft, follow_run = sid_b, draft_b, run_b
                elif results["cases"].get("ac013_complete", {}).get("has_draft"):
                    follow_sid, follow_draft, follow_run = sid_a, draft_a, run_a
                if follow_sid and follow_run and follow_run.get("status") == "succeeded":
                    session_now = detail(client, follow_sid)
                    draft_now = session_now.get("draft") or {}
                    blocking = [i for i in (draft_now.get("blocking_issues") or []) if i.get("blocking")]
                    if not blocking:
                        reviewed = data_ok(
                            client,
                            "PATCH",
                            f"/api/sessions/{follow_sid}/drafts/{draft_now['id']}",
                            {
                                "expected_revision": session_now["revision"],
                                "draft_revision": draft_now["draft_revision"],
                                "summary": draft_now["report_data"]["summary"],
                            },
                        )
                        data_ok(
                            client,
                            "POST",
                            f"/api/sessions/{follow_sid}/reports",
                            {
                                "draft_id": draft_now["id"],
                                "draft_revision": reviewed["draft_revision"],
                                "expected_revision": detail(client, follow_sid)["revision"],
                                "review_confirmed": True,
                            },
                            status=201,
                        )
                        followups = []
                        for fixture in ("family-charging-followup", "budget-followup"):
                            injected = data_ok(
                                client,
                                "POST",
                                f"/api/sessions/{follow_sid}/events",
                                {
                                    "fixture_id": fixture,
                                    "expected_revision": detail(client, follow_sid)["revision"],
                                },
                            )
                            run_f = start_run(client, follow_sid, "followup")
                            followup = detail(client, follow_sid).get("followup")
                            blob = json.dumps(followup, ensure_ascii=False)
                            item = {
                                "fixture": fixture,
                                "event_ids": injected.get("event_ids"),
                                "status": run_f.get("status"),
                                "private_sentinel": "私人内容测试哨兵" in blob,
                                "source_event_ids": (followup or {}).get("source_event_ids")
                                if isinstance(followup, dict)
                                else None,
                                "brief_excerpt": ((followup or {}).get("brief") or "")[:180]
                                if isinstance(followup, dict)
                                else str(followup)[:180],
                            }
                            followups.append(item)
                            save(f"ac020-{fixture}-r2.json", {"run": run_f, "followup": followup})
                        results["cases"]["ac020"] = {
                            "published": True,
                            "followups": followups,
                            "briefs_differ": len({item["brief_excerpt"] for item in followups}) > 1,
                        }
                    else:
                        results["cases"]["ac020"] = {
                            "published": False,
                            "reason": "draft_blocking",
                            "blocking": blocking,
                        }
                else:
                    results["cases"]["ac020"] = {
                        "published": False,
                        "reason": "no_succeeded_draft",
                    }
            except Exception as error:
                remember(error, "ac020")
                results["cases"]["ac020"] = {"error": str(error)[:400]}
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
    save("t008-retest-r2-summary.json", results)
    print(json.dumps(redact(results), ensure_ascii=False, indent=2))
    return results


if __name__ == "__main__":
    main()
