"""After analyze candidates, confirm 望京(地铁站), then prepare. Isolated real Qwen/Amap."""
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
import t008_retest_r2 as r2
from src.config.settings import Settings, load_settings
from src.main import create_demo_app
from t008_retest_r2 import (
    capture,
    charging_artifacts,
    confirm,
    current_facts,
    detail,
    pick_wangjing,
    redact,
    save,
    start_run,
    summary_blob,
    tool_names,
    utcnow,
)

PORT = 18121
ORIGIN = f"http://127.0.0.1:{PORT}"
r2.PORT = PORT
r2.ORIGIN = ORIGIN
PHONE = "13900139228"
EMAIL = "qa-t008-r2d@example.com"
ROOT = Path(__file__).resolve().parents[3]


def ok(client, method, path, body=None, status=200):
    response = client.request(
        method,
        path,
        json=body,
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
        timeout=70,
    )
    if response.status_code != status:
        raise AssertionError(f"{method} {path} -> {response.status_code} {response.text[:800]}")
    payload = response.json()
    if not payload.get("success"):
        raise AssertionError(payload)
    return payload["data"]


def main():
    results = {"started_at": utcnow(), "origin": ORIGIN}
    base = load_settings()
    prod_db = ROOT / "backend/data/tess-chrome.db"
    results["prod_db_before"] = prod_db.stat().st_size
    results["prod_8099"] = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()["data"]["status"]
    tmp = Path(tempfile.mkdtemp(prefix="t008-r2d-"))
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
            ok(client, "GET", "/api/health")
            created = ok(
                client,
                "POST",
                "/api/customers",
                {"nickname": "QA返工2丁", "phone": PHONE, "email": EMAIL, "identity_confirmed": True},
                status=201,
            )
            session = ok(
                client,
                "POST",
                "/api/sessions",
                {"customer_id": created["id"], "title": "T008-r2 确认望京后出稿", "visit_at": None},
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
            analyze = start_run(client, sid, "analyze", message="请查询望京充电站")
            session_now = detail(client, sid)
            candidates = []
            for data in charging_artifacts(session_now):
                candidates.extend(data.get("candidates") or [])
            chosen = pick_wangjing(candidates)
            results["analyze"] = {
                "status": analyze.get("status"),
                "candidate_names": [c.get("name") for c in candidates[:8]],
                "chosen": (chosen or {}).get("name"),
                "chosen_id": (chosen or {}).get("id"),
            }
            if not chosen:
                raise AssertionError("no wangjing candidate")
            confirm(client, sid, {"confirmed_location_ref": chosen["id"]}, skip_optional=True)
            facts = {f["key"]: f["value"] for f in current_facts(detail(client, sid)) if f["state"] == "confirmed"}
            results["confirmed_location"] = facts.get("confirmed_location_ref")
            prep = start_run(client, sid, "prepare_report")
            session_after = detail(client, sid)
            draft = session_after.get("draft")
            charging = {}
            for data in charging_artifacts(session_after):
                if data.get("state") == "ready" and data.get("stations"):
                    charging = data
                    break
                charging = data or charging
            stations = charging.get("stations") or []
            _, summary = summary_blob(draft)
            results["prepare"] = {
                "run_status": prep.get("status"),
                "error": prep.get("error"),
                "tools": tool_names(prep),
                "has_draft": bool(draft),
                "charging_state": charging.get("state"),
                "station_count": len(stations),
                "station_names": [s.get("name") for s in stations],
                "routes_ready": [
                    s.get("name") for s in stations if s.get("route_status") == "ready" and s.get("driving_distance_m")
                ],
                "map_status": charging.get("map_status"),
                "map_asset_id": charging.get("map_asset_id"),
                "distance_basis": list({s.get("distance_basis") for s in stations if s.get("distance_basis")}),
                "external_search_has_key": "key=" in json.dumps(charging.get("external_search") or {}),
                "summary": summary,
            }
            save("ac013-confirm-center-prepare-r2.json", results["prepare"] | {"analyze": results["analyze"]})
    finally:
        server.should_exit = True
        worker.join(timeout=5)
    results["prod_db_after"] = prod_db.stat().st_size
    results["prod_8099_after"] = httpx.get("http://127.0.0.1:8099/api/health", timeout=5).json()["data"]["status"]
    results["ended_at"] = utcnow()
    save("t008-retest-r2-confirm-center-summary.json", results)
    print(json.dumps(redact(results), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
