"""T-008 follow-up: real Amap stack, explicit charging analyze, ASR via TestClient."""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import tempfile
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import uvicorn
from starlette.testclient import TestClient

from src.adapters.amap import AmapProvider, search_link
from src.config.settings import Settings, load_settings
from src.main import create_demo_app
from src.tools.registry import ToolContext, ToolRegistry

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PORT = 18099
ORIGIN = f"http://127.0.0.1:{PORT}"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    text = json.dumps(value, ensure_ascii=False, default=str)
    text = re.sub(r"(?i)(sk-|Bearer |key=)[A-Za-z0-9._\-]+", r"\1REDACTED", text)
    text = re.sub(r"1[3-9]\d{9}", "[PHONE]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    return json.loads(text)


def save(name, payload):
    path = EVIDENCE / name
    path.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n")
    return str(path)


def request(client, method, path, body=None, status=None):
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


def data_ok(client, method, path, body=None, status=200):
    code, payload = request(client, method, path, body, status=status)
    if not payload.get("success"):
        raise AssertionError(payload)
    return payload["data"]


def detail(client, sid):
    return data_ok(client, "GET", f"/api/sessions/{sid}")


def wait_run(client, sid, rid, timeout=180):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = data_ok(client, "GET", f"/api/sessions/{sid}/runs/{rid}")
        if last["status"] not in ("queued", "running"):
            return last
        time.sleep(1)
    raise TimeoutError(last and last["status"])


def capture(client, sid):
    raw = json.loads((ROOT / "docs/evidence/capture-spike/tester-0.1.1-awd-white20.json").read_text())
    payload = {k: raw[k] for k in ("source_url", "captured_at", "adapter_version",
                                   "page_fingerprint", "readiness", "fields", "issues")}
    payload["issues"] = [{**{k: v for k, v in i.items() if k != "severity"},
                          "blocking": i.get("severity") == "blocking"} for i in payload["issues"]]
    return data_ok(client, "POST", f"/api/sessions/{sid}/captures",
                   {"expected_revision": detail(client, sid)["revision"], "capture": payload}, status=201)


def confirm(client, sid, values, skip_optional=True):
    session = detail(client, sid)
    superseded = {ref for f in session["facts"] for ref in f.get("supersedes") or []}
    current = [f for f in session["facts"] if f["id"] not in superseded and f.get("scope") == "session"]
    changes = []
    for key, value in values.items():
        refs = [f["id"] for f in current if f["key"] == key]
        changes.append({"key": key, "value": value, "state": "confirmed",
                        "supersedes": refs, "evidence_note": "T008 QA"})
    return data_ok(client, "PATCH", f"/api/sessions/{sid}/context", {
        "expected_revision": session["revision"], "changes": changes,
        "skip_optional_questions": skip_optional})


async def live_maps(config):
    provider = AmapProvider(config)
    candidates = await provider.search_region("望京地铁站", "北京")
    if not candidates:
        return {"candidates": 0}
    center = candidates[0]["center_gcj02"]
    stations = await provider.stations(center, config.map_radius_m)
    routes = []
    for station in stations:
        try:
            routed = await provider.route(center, station["location_gcj02"])
            station.update(routed)
            routes.append({
                "number": station.get("number"),
                "name": station.get("name"),
                "center_distance_m": station.get("center_distance_m"),
                "distance_basis": station.get("distance_basis"),
                "driving_distance_m": station.get("driving_distance_m"),
                "driving_duration_seconds": station.get("driving_duration_seconds"),
                "route_status": station.get("route_status"),
            })
        except Exception as error:
            routes.append({"name": station.get("name"), "route_error": type(error).__name__})
    image = {"ok": False}
    try:
        raw, mime = await provider.static_map(center, stations)
        image_path = EVIDENCE / "amap-static-wangjing.png"
        if mime == "image/jpeg":
            image_path = EVIDENCE / "amap-static-wangjing.jpg"
        image_path.write_bytes(raw)
        image = {"ok": True, "mime": mime, "bytes": len(raw), "path": str(image_path),
                 "png_signature": raw.startswith(b"\x89PNG\r\n\x1a\n")}
    except Exception as error:
        image = {"ok": False, "error_type": type(error).__name__, "message": str(error)[:200]}
    link = search_link("望京地铁站", "北京")
    parsed = urlparse(link["url"])
    query = parse_qs(parsed.query)
    return {
        "candidate_count": len(candidates),
        "candidate_names": [c["name"] for c in candidates[:5]],
        "center_city": candidates[0]["city"],
        "station_count": len(stations),
        "stations": [{"number": s.get("number"), "name": s.get("name"),
                      "center_distance_m": s.get("center_distance_m"),
                      "distance_basis": s.get("distance_basis")} for s in stations],
        "routes": routes,
        "image": image,
        "external_search": link,
        "url_host": parsed.hostname,
        "url_keyword": (query.get("keyword") or [None])[0],
        "url_city": (query.get("city") or [None])[0],
        "url_has_key": "key" in query,
        "url_has_phone": bool(re.search(r"1[3-9]\d{9}", link["url"])),
    }


def make_pcm(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        aiff = Path(folder) / "speech.aiff"
        wav = Path(folder) / "speech.wav"
        subprocess.run(["say", "-r", "180", "-o", str(aiff), text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
                       check=True)
        with wave.open(str(wav), "rb") as handle:
            return handle.readframes(handle.getnframes())


def asr_via_testclient(app, sid, pcm):
    with TestClient(app, base_url=ORIGIN) as client:
        created = data_ok(client, "POST", f"/api/sessions/{sid}/audio",
                          {"expected_revision": detail(client, sid)["revision"], "language": "zh"},
                          status=201)
        before = detail(client, sid)
        events = []
        finals = []
        partials = []
        finished = None
        with client.websocket_connect(created["ws_path"], headers={"Origin": ORIGIN}) as ws:
            ready = ws.receive_json()
            events.append(ready.get("type"))
            if ready.get("type") != "ready":
                return {"create": created, "first": ready, "timeline_before": len(before["timeline"])}
            chunk = 3200
            for index in range(0, len(pcm), chunk):
                ws.send_bytes(pcm[index:index + chunk])
            ws.send_json({"type": "finish"})
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                payload = ws.receive_json()
                kind = payload.get("type")
                events.append(kind)
                if kind == "partial":
                    partials.append(payload.get("text") or "")
                elif kind == "final":
                    finals.append(payload.get("transcript") or "")
                elif kind in {"finished", "error"}:
                    finished = payload
                    break
        after = detail(client, sid)
        send = None
        try:
            text = (finals[-1] if finals else "客户张伟希望月供四千元") + "（销售改为四千八百）"
            run = data_ok(client, "POST", f"/api/sessions/{sid}/inputs", {
                "text": text, "source": "asr_corrected",
                "asr_session_id": created["asr_session_id"],
                "expected_revision": after["revision"]}, status=202)
            send = wait_run(client, sid, run["run_id"])
            after_send = detail(client, sid)
            send = {
                "status": send["status"],
                "revision_grew": after_send["revision"] > after["revision"],
                "timeline_grew": len(after_send["timeline"]) > len(after["timeline"]),
                "uses_corrected": any("四千八百" in json.dumps(item, ensure_ascii=False)
                                      for item in after_send["timeline"]),
            }
        except Exception as error:
            send = {"error": type(error).__name__, "message": str(error)[:300]}
        return {
            "create_state": created.get("state"),
            "events": events,
            "partials": [p for p in partials if p],
            "finals": [t for t in finals if t],
            "finished": finished,
            "revision_before": before["revision"],
            "revision_after_finish": after["revision"],
            "timeline_before": len(before["timeline"]),
            "timeline_after_finish": len(after["timeline"]),
            "manual_send": send,
        }


def main():
    results = {"started_at": utcnow(), "origin": ORIGIN}
    base = load_settings()
    config = Settings(
        database_path=str(Path(tempfile.mkdtemp(prefix="t008-qa2-")) / "qa.db"),
        upload_dir=str(Path(tempfile.mkdtemp(prefix="t008-up-"))),
        port=PORT, report_origin=ORIGIN,
        bailian_base_url=base.bailian_base_url, bailian_api_key=base.bailian_api_key,
        bailian_asr_ws_url=base.bailian_asr_ws_url, llm_model=base.llm_model,
        asr_model=base.asr_model, amap_web_service_key=base.amap_web_service_key,
        amap_base_url=base.amap_base_url, frontend_dist=base.frontend_dist,
        allowed_extension_origin=base.allowed_extension_origin,
    )
    results["maps"] = redact(asyncio.run(live_maps(config)))
    save("ac007-amap-direct.json", results["maps"])

    app = create_demo_app(config)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT,
                                          log_level="warning", access_log=False))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 15
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "QA server failed"
    try:
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=70) as client:
            customer = data_ok(client, "POST", "/api/customers", {
                "nickname": "QA地图", "email": "qa-t008-map@example.com",
                "identity_confirmed": True}, status=201)
            session = data_ok(client, "POST", "/api/sessions", {
                "customer_id": customer["id"], "title": "T008 maps", "visit_at": None}, status=201)
            sid = session["id"]
            cap = capture(client, sid)
            confirm(client, sid, {
                "has_fixed_parking": False, "region": "望京地铁站", "city": "北京",
                "monthly_budget": 400000, "home_charging": False})
            # Direct product tool path with confirmed session revision.
            async def run_tool():
                registry = ToolRegistry(config)
                context = ToolContext(session_id=sid, source_revision=detail(client, sid)["revision"],
                                      session_factory=app.state.session_factory,
                                      write_lock=app.state.write_lock)
                return await registry.execute("search_charging", {
                    "region": "望京地铁站", "city": "北京"}, context)
            tool_obs = asyncio.run(run_tool())
            results["charging_tool"] = {
                "status": tool_obs.get("status"),
                "state": (tool_obs.get("data") or {}).get("state"),
                "station_count": len((tool_obs.get("data") or {}).get("stations") or []),
                "map_status": (tool_obs.get("data") or {}).get("map_status"),
                "map_asset_id": (tool_obs.get("data") or {}).get("map_asset_id"),
                "radius_m": (tool_obs.get("data") or {}).get("radius_m"),
                "warnings": (tool_obs.get("data") or {}).get("warnings"),
                "external_search": (tool_obs.get("data") or {}).get("external_search"),
                "stations": [
                    {"number": s.get("number"), "name": s.get("name"),
                     "center_distance_m": s.get("center_distance_m"),
                     "distance_basis": s.get("distance_basis"),
                     "driving_distance_m": s.get("driving_distance_m"),
                     "driving_duration_seconds": s.get("driving_duration_seconds"),
                     "route_status": s.get("route_status")}
                    for s in (tool_obs.get("data") or {}).get("stations") or []
                ],
            }
            save("ac007-charging-tool.json", {"observation": {
                "status": tool_obs.get("status"), "data": tool_obs.get("data"),
                "error": tool_obs.get("error")}})

            analyze = data_ok(client, "POST", f"/api/sessions/{sid}/runs", {
                "intent": "analyze",
                "message": "请查询望京地铁站附近特斯拉充电站，并说明距离口径。",
                "expected_revision": detail(client, sid)["revision"]}, status=202)
            analyze_run = wait_run(client, sid, analyze["run_id"])
            results["analyze_charging"] = {
                "status": analyze_run["status"],
                "tools": [e.get("tool_name") for e in analyze_run.get("events") or [] if e.get("tool_name")],
                "error": analyze_run.get("error"),
            }
            save("ac013-analyze-charging.json", analyze_run)

            # Follow-up publish path: skip remaining questions and prepare.
            confirm(client, sid, {}, skip_optional=True)
            prep = data_ok(client, "POST", f"/api/sessions/{sid}/runs", {
                "intent": "prepare_report", "expected_revision": detail(client, sid)["revision"]},
                           status=202)
            prep_run = wait_run(client, sid, prep["run_id"])
            if prep_run["status"] == "needs_confirmation":
                confirm(client, sid, {}, skip_optional=True)
                try:
                    prep = data_ok(client, "POST", f"/api/sessions/{sid}/runs", {
                        "intent": "prepare_report",
                        "continue_run_id": prep_run["run_id"],
                        "expected_revision": detail(client, sid)["revision"]}, status=202)
                    prep_run = wait_run(client, sid, prep["run_id"])
                except Exception as error:
                    results["prepare_continue_error"] = type(error).__name__ + ":" + str(error)[:200]
            draft = detail(client, sid).get("draft")
            results["prepare"] = {
                "status": prep_run["status"],
                "tools": [e.get("tool_name") for e in prep_run.get("events") or [] if e.get("tool_name")],
                "has_draft": bool(draft),
                "blocking": (draft or {}).get("blocking_issues"),
            }
            published = None
            if draft and not [i for i in (draft.get("blocking_issues") or []) if i.get("blocking")]:
                reviewed = data_ok(client, "PATCH", f"/api/sessions/{sid}/drafts/{draft['id']}", {
                    "expected_revision": detail(client, sid)["revision"],
                    "draft_revision": draft["draft_revision"],
                    "summary": draft["report_data"]["summary"]})
                published = data_ok(client, "POST", f"/api/sessions/{sid}/reports", {
                    "draft_id": draft["id"], "draft_revision": reviewed["draft_revision"],
                    "expected_revision": detail(client, sid)["revision"],
                    "review_confirmed": True}, status=201)
                report = data_ok(client, "GET", f"/api/reports/{published['report_id']}")
                charging = next((m for m in report["modules"] if m["type"] == "charging"), {})
                url = ((charging.get("data") or {}).get("external_search") or {}).get("url")
                snapshot_time = (charging.get("data") or {}).get("observed_at")
                results["published"] = {
                    "report_id": published["report_id"],
                    "url": published.get("url"),
                    "charging_status": charging.get("status"),
                    "search_url": url,
                    "observed_at": snapshot_time,
                }
                save("ac043-published.json", {"published": published, "charging": charging})
                for fixture in ("family-charging-followup", "budget-followup"):
                    injected = data_ok(client, "POST", f"/api/sessions/{sid}/events", {
                        "fixture_id": fixture,
                        "expected_revision": detail(client, sid)["revision"]})
                    run = data_ok(client, "POST", f"/api/sessions/{sid}/runs", {
                        "intent": "followup",
                        "expected_revision": detail(client, sid)["revision"]}, status=202)
                    waited = wait_run(client, sid, run["run_id"])
                    followup = detail(client, sid).get("followup")
                    blob = json.dumps(followup, ensure_ascii=False)
                    results.setdefault("followups", []).append({
                        "fixture": fixture,
                        "event_ids": injected.get("event_ids"),
                        "status": waited["status"],
                        "followup": followup,
                        "private_sentinel": "私人内容测试哨兵" in blob,
                    })
                    if fixture == "family-charging-followup":
                        save("ac020-followup-charging.json", {"run": waited, "followup": followup})
                    else:
                        save("ac020-followup-budget.json", {"run": waited, "followup": followup})

            # ASR on a fresh session so finish isolation is obvious.
            asr_session = data_ok(client, "POST", "/api/sessions", {
                "customer_id": customer["id"], "title": "T008 asr", "visit_at": None}, status=201)
            pcm = make_pcm("客户张伟希望月供四千元")
            results["asr"] = asr_via_testclient(app, asr_session["id"], pcm)
            save("ac004-asr-round2.json", results["asr"])
    except Exception as error:
        results["error"] = {"type": type(error).__name__, "message": str(error)[:500]}
    finally:
        server.should_exit = True
        worker.join(timeout=15)
        results["finished_at"] = utcnow()
        save("t008-live-summary-2.json", results)
        print(json.dumps(redact(results), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
