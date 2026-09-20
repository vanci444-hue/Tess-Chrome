"""Confirm 望京 center then search+prepare; isolated real Amap/Qwen."""
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from src.config.settings import Settings, load_settings
from src.main import create_demo_app

import t008_retest_r2 as r2
from t008_retest_r2 import (
    capture,
    confirm,
    continue_prepare,
    current_facts,
    detail,
    pick_wangjing,
    redact,
    save,
    start_run,
    summary_blob,
    tool_names,
    charging_artifacts,
    utcnow,
)

PORT = 18119
ORIGIN = f"http://127.0.0.1:{PORT}"
r2.PORT = PORT
r2.ORIGIN = ORIGIN
PHONE = "13900139218"
EMAIL = "qa-t008-r2c@example.com"
ROOT = Path(__file__).resolve().parents[3]


def request_origin(client, method, path, body=None, status=None):
    response = client.request(
        method,
        path,
        json=body,
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
        timeout=70,
    )
    if status is not None and response.status_code != status:
        raise AssertionError(f"{method} {path} -> {response.status_code} {response.text[:800]}")
    return response.status_code, response.json()


def ok(client, method, path, body=None, status=200):
    _, payload = request_origin(client, method, path, body, status=status)
    if not payload.get("success"):
        raise AssertionError(payload)
    return payload["data"]


def continue_location(client, sid, run):
    session = ok(client, "GET", f"/api/sessions/{sid}")
    facts = current_facts(session)
    proposed = [f for f in facts if f["key"] == "confirmed_location_ref" and f["state"] == "proposed"]
    candidates = []
    for data in charging_artifacts(session):
        candidates.extend(data.get("candidates") or [])
        if data.get("region_candidates"):
            candidates.extend(data["region_candidates"])
    chosen = pick_wangjing(candidates)
    questions = (run.get("result") or {}).get("questions") or []
    reply = {"reply_to_run_id": run["run_id"]}
    if questions:
        reply["reply_to_question_ids"] = [q["id"] for q in questions if q.get("id")]
    values = {}
    if proposed:
        values["confirmed_location_ref"] = proposed[0]["value"]
    elif chosen:
        values["confirmed_location_ref"] = chosen["id"]
    confirm(client, sid, values, skip_optional=True, reply=reply)
    return start_run(client, sid, run.get("kind") or "analyze", continue_run_id=run["run_id"])


def main():
    results = {"started_at": utcnow(), "origin": ORIGIN, "provider": "real", "errors": []}
    base = load_settings()
    prod_db = ROOT / "backend/data/tess-chrome.db"
    results["prod_db_before"] = prod_db.stat().st_size if prod_db.exists() else 0
    results["prod_8099"] = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()["data"]["status"]
    tmp = Path(tempfile.mkdtemp(prefix="t008-r2c-"))
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
    app = create_demo_app(config)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning", access_log=False))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 15
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("server failed")
    try:
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=70) as client:
            health = ok(client, "GET", "/api/health")
            results["isolated_health"] = health["capabilities"]
            created = ok(
                client,
                "POST",
                "/api/customers",
                {"nickname": "QA返工2丙", "phone": PHONE, "email": EMAIL, "identity_confirmed": True},
                status=201,
            )
            session = ok(
                client,
                "POST",
                "/api/sessions",
                {"customer_id": created["id"], "title": "T008-r2 望京确认中心", "visit_at": None},
                status=201,
            )
            sid = session["id"]
            capture(client, sid)
            confirm(
                client,
                sid,
                {
                    "has_fixed_parking": False,
                    "home_charging": False,
                    "region": "望京地铁站",
                    "city": "北京",
                    "monthly_budget": 400000,
                },
                skip_optional=True,
            )
            run = start_run(client, sid, "analyze", message="请查询望京充电站")
            loops = []
            for _ in range(4):
                if run["status"] != "needs_confirmation":
                    break
                session_now = detail(client, sid)
                questions = (run.get("result") or {}).get("questions") or []
                loops.append({"status": run["status"], "questions": [q.get("text") for q in questions], "tools": tool_names(run)})
                run = continue_location(client, sid, run)
            session_final = detail(client, sid)
            charging_data = {}
            for data in charging_artifacts(session_final):
                if data.get("stations"):
                    charging_data = data
                    break
                charging_data = data or charging_data
            stations = charging_data.get("stations") or []
            results["analyze"] = {
                "run_status": run.get("status"),
                "tools": tool_names(run),
                "error": run.get("error"),
                "loops": loops,
                "charging_state": charging_data.get("state"),
                "station_count": len(stations),
                "station_names": [s.get("name") for s in stations],
                "map_status": charging_data.get("map_status"),
                "distance_basis": list({s.get("distance_basis") for s in stations if s.get("distance_basis")}),
                "external_search_has_key": "key=" in json.dumps(charging_data.get("external_search") or {}),
                "artifact_keys": [list((art.get("output") or art).keys())[:8] for art in (session_final.get("artifacts") or [])[:6]],
                "artifact_tools": [art.get("tool_name") or art.get("tool") for art in (session_final.get("artifacts") or [])],
            }
            if run["status"] == "needs_confirmation":
                confirm(client, sid, {}, skip_optional=True, reply={"reply_to_run_id": run["run_id"]})
            prep = start_run(client, sid, "prepare_report")
            prep_loops = []
            for _ in range(4):
                if prep["status"] != "needs_confirmation":
                    break
                session_now = detail(client, sid)
                questions = (prep.get("result") or {}).get("questions") or []
                required = [q for q in questions if q.get("required")]
                prep_loops.append(
                    {
                        "status": prep["status"],
                        "required": [q.get("text") for q in required],
                        "optional": [q.get("text") for q in questions if not q.get("required")],
                    }
                )
                prep, _ = continue_prepare(client, sid, prep)
            session_after = detail(client, sid)
            draft = session_after.get("draft")
            charging_after = {}
            for data in charging_artifacts(session_after):
                if data.get("stations"):
                    charging_after = data
                    break
                charging_after = data or charging_after
            _, summary = summary_blob(draft)
            results["prepare"] = {
                "run_status": prep.get("status"),
                "error": prep.get("error"),
                "tools": tool_names(prep),
                "has_draft": bool(draft),
                "loops": prep_loops,
                "charging_state": charging_after.get("state"),
                "station_count": len(charging_after.get("stations") or []),
                "summary": summary,
            }
            save(
                "ac007-confirm-center-r2.json",
                {"analyze": results["analyze"], "prepare": results["prepare"], "charging": charging_after},
            )
    finally:
        server.should_exit = True
        worker.join(timeout=5)
    results["prod_db_after"] = prod_db.stat().st_size if prod_db.exists() else 0
    results["prod_8099_after"] = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()["data"]["status"]
    results["ended_at"] = utcnow()
    save("t008-retest-r2-charging-summary.json", results)
    print(json.dumps(redact(results), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
