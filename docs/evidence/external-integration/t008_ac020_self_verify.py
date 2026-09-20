"""T-008 返工3 Developer 自验 AC-020。隔离端口+临时库；真百炼；不杀 8099、不清空生产库。"""
from __future__ import annotations

import json
import re
import socket
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
PHONE = "13900139308"
EMAIL = "qa-t008-ac020@example.com"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def free_port():
    for port in (18131, 18132, 18133, 18141):
        if port in (8099, 18108):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no isolated port")


def redact(value):
    text = json.dumps(value, ensure_ascii=False, default=str)
    text = re.sub(r"(?i)(sk-|Bearer |key=)[A-Za-z0-9._\-]+", r"\1REDACTED", text)
    text = text.replace(PHONE, "[REDACTED]").replace(EMAIL, "[REDACTED]")
    text = re.sub(r"1[3-9]\d{9}", "[PHONE]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    return json.loads(text)


def save(name, payload):
    path = EVIDENCE / name
    path.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n")
    return str(path)


def data_ok(client, method, path, body=None, status=200, origin=""):
    response = client.request(
        method,
        path,
        json=body,
        headers={"Origin": origin, "Idempotency-Key": str(uuid4())},
        timeout=70,
    )
    if response.status_code != status:
        raise AssertionError(f"{method} {path} -> {response.status_code} {response.text[:800]}")
    payload = response.json()
    if not payload.get("success"):
        raise AssertionError(f"{method} {path} failed: {payload}")
    return payload["data"]


def detail(client, sid, origin):
    return data_ok(client, "GET", f"/api/sessions/{sid}", origin=origin)


def wait_run(client, sid, rid, origin, timeout=180):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = data_ok(client, "GET", f"/api/sessions/{sid}/runs/{rid}", origin=origin)
        if last["status"] not in ("queued", "running"):
            return last
        time.sleep(1)
    raise TimeoutError(f"run {rid} still {last and last['status']}")


def current_facts(session):
    superseded = {ref for fact in session["facts"] for ref in fact.get("supersedes") or []}
    return [fact for fact in session["facts"] if fact["id"] not in superseded and fact.get("scope") == "session"]


def confirm(client, sid, values, origin, skip_optional=True, reply=None):
    session = detail(client, sid, origin)
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
                "evidence_note": "T008 AC-020 自验确认",
            }
        )
    body = {
        "expected_revision": session["revision"],
        "changes": changes,
        "skip_optional_questions": skip_optional,
    }
    if reply:
        body.update(reply)
    return data_ok(client, "PATCH", f"/api/sessions/{sid}/context", body, origin=origin)


def start_run(client, sid, intent, origin, continue_run_id=None):
    body = {"intent": intent, "expected_revision": detail(client, sid, origin)["revision"]}
    if continue_run_id:
        body["continue_run_id"] = continue_run_id
    run = data_ok(client, "POST", f"/api/sessions/{sid}/runs", body, status=202, origin=origin)
    return wait_run(client, sid, run["run_id"], origin)


def run_questions(run, session):
    questions = (run.get("result") or {}).get("questions") or []
    if not questions:
        questions = (session.get("pending_run") or {}).get("questions") or []
    return questions


def drain_prepare(client, sid, run, origin, loops=5):
    current = run
    for _ in range(loops):
        if current["status"] != "needs_confirmation":
            break
        session = detail(client, sid, origin)
        questions = run_questions(current, session)
        reply = {"reply_to_run_id": current["run_id"]}
        if questions:
            reply["reply_to_question_ids"] = [q["id"] for q in questions if q.get("id")]
        confirm(client, sid, {}, origin, skip_optional=True, reply=reply)
        current = start_run(client, sid, "prepare_report", origin, continue_run_id=current["run_id"])
    return current


def capture(client, sid, origin):
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
        {"expected_revision": detail(client, sid, origin)["revision"], "capture": payload},
        status=201,
        origin=origin,
    )


def tool_names(run):
    return [e.get("tool_name") for e in run.get("events") or [] if e.get("tool_name")]


def main():
    port = free_port()
    origin = f"http://127.0.0.1:{port}"
    prod_db = ROOT / "backend/data/tess-chrome.db"
    results = {
        "task_id": "T-008",
        "role": "developer-self-verify",
        "ac": "AC-020",
        "started_at": utcnow(),
        "origin": origin,
        "git_head": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT).decode().strip(),
        "provider": "real-bailian",
        "key_logged": False,
        "production_8099": "not_killed",
        "business_db": "not_cleared",
        "prod_db_before": {"exists": prod_db.exists(), "size": prod_db.stat().st_size if prod_db.exists() else 0},
        "followups": [],
        "errors": [],
    }
    health_prod = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()
    results["prod_8099_before"] = {
        "status": (health_prod.get("data") or {}).get("status"),
        "capabilities": (health_prod.get("data") or {}).get("capabilities"),
    }
    base = load_settings()
    results["config_presence"] = {
        "bailian_api_key": bool(base.bailian_api_key),
        "bailian_base_url": bool(base.bailian_base_url),
        "amap_web_service_key": bool(base.amap_web_service_key),
        "llm_model": base.llm_model,
    }
    tmp = Path(tempfile.mkdtemp(prefix="t008-ac020-"))
    config = Settings(
        database_path=str(tmp / "qa.db"),
        upload_dir=str(tmp / "uploads"),
        port=port,
        report_origin=origin,
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
    app = create_demo_app(config)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 15
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError(f"isolated server failed on {port}")
    try:
        with httpx.Client(base_url=origin, trust_env=False, timeout=70) as client:
            health = data_ok(client, "GET", "/api/health", origin=origin)
            results["isolated_health"] = {"status": health["status"], "capabilities": health["capabilities"]}
            customer = data_ok(
                client,
                "POST",
                "/api/customers",
                {"nickname": "QA跟进甲", "phone": PHONE, "email": EMAIL, "identity_confirmed": True},
                status=201,
                origin=origin,
            )
            session = data_ok(
                client,
                "POST",
                "/api/sessions",
                {"customer_id": customer["id"], "title": "T008 AC-020 跟进", "visit_at": None},
                status=201,
                origin=origin,
            )
            sid = session["id"]
            capture(client, sid, origin)
            confirm(
                client,
                sid,
                {
                    "has_fixed_parking": True,
                    "home_charging": "小区车位已安装家充",
                    "monthly_budget": 400000,
                    "region": "望京地铁站",
                    "city": "北京",
                },
                origin,
            )
            prepared = drain_prepare(client, sid, start_run(client, sid, "prepare_report", origin), origin)
            results["prepare"] = {
                "status": prepared["status"],
                "error": prepared.get("error"),
                "tools": tool_names(prepared),
            }
            session_now = detail(client, sid, origin)
            draft = session_now.get("draft") or {}
            if prepared["status"] != "succeeded" or not draft:
                raise AssertionError(f"prepare did not yield draft: {prepared.get('error')}")
            blocking = [i for i in (draft.get("blocking_issues") or []) if i.get("blocking")]
            if blocking:
                raise AssertionError(f"draft still blocking: {blocking}")
            reviewed = data_ok(
                client,
                "PATCH",
                f"/api/sessions/{sid}/drafts/{draft['id']}",
                {
                    "expected_revision": session_now["revision"],
                    "draft_revision": draft["draft_revision"],
                    "summary": draft["report_data"]["summary"],
                },
                origin=origin,
            )
            data_ok(
                client,
                "POST",
                f"/api/sessions/{sid}/reports",
                {
                    "draft_id": draft["id"],
                    "draft_revision": reviewed["draft_revision"],
                    "expected_revision": detail(client, sid, origin)["revision"],
                    "review_confirmed": True,
                },
                status=201,
                origin=origin,
            )
            results["published"] = True
            for fixture in ("family-charging-followup", "budget-followup"):
                injected = data_ok(
                    client,
                    "POST",
                    f"/api/sessions/{sid}/events",
                    {"fixture_id": fixture, "expected_revision": detail(client, sid, origin)["revision"]},
                    origin=origin,
                )
                run_f = start_run(client, sid, "followup", origin)
                followup = detail(client, sid, origin).get("followup")
                brief = (followup or {}).get("brief") if isinstance(followup, dict) else None
                source_ids = (followup or {}).get("source_event_ids") if isinstance(followup, dict) else None
                items = (followup or {}).get("items") if isinstance(followup, dict) else []
                event_ids = injected.get("event_ids") or []
                item = {
                    "fixture": fixture,
                    "event_ids": event_ids,
                    "status": run_f.get("status"),
                    "error_code": (run_f.get("error") or {}).get("code")
                    if isinstance(run_f.get("error"), dict)
                    else run_f.get("error"),
                    "tools": tool_names(run_f),
                    "private_sentinel": "私人内容测试哨兵" in json.dumps(followup, ensure_ascii=False),
                    "source_event_ids": source_ids,
                    "brief_excerpt": (brief or "")[:180] if isinstance(brief, str) else brief,
                    "item_statuses": [
                        {"topic": row.get("topic"), "status": row.get("status"), "source_event_id": row.get("source_event_id")}
                        for row in items or []
                    ],
                    "traces_round_events": bool(source_ids) and any(eid in (source_ids or []) for eid in event_ids),
                    "brief_nonempty": isinstance(brief, str) and bool(brief.strip()),
                }
                results["followups"].append(item)
                save(f"ac020-{fixture}-r3.json", {"run": run_f, "followup": followup, "injected": injected})
            results["pass"] = all(
                row["status"] == "succeeded"
                and row["error_code"] != "INVALID_MODEL_OUTPUT"
                and row["brief_nonempty"]
                and row["traces_round_events"]
                and not row["private_sentinel"]
                and "search_charging" not in (row["tools"] or [])
                for row in results["followups"]
            ) and len({row["brief_excerpt"] for row in results["followups"]}) > 1
    except Exception as error:
        results["errors"].append({"type": type(error).__name__, "message": str(error)[:500]})
        results["pass"] = False
    finally:
        server.should_exit = True
        worker.join(timeout=5)
    results["prod_db_after"] = {"exists": prod_db.exists(), "size": prod_db.stat().st_size if prod_db.exists() else 0}
    health_after = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()
    results["prod_8099_after"] = {
        "status": (health_after.get("data") or {}).get("status"),
        "capabilities": (health_after.get("data") or {}).get("capabilities"),
    }
    results["ended_at"] = utcnow()
    save("t008-rework3-self-verify.json", results)
    print(json.dumps(redact(results), ensure_ascii=False, indent=2))
    if not results.get("pass"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
