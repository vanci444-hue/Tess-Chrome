"""T-008: confirm location then real stations/routes; ASR with aiohttp origin."""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from uuid import uuid4

import aiohttp
import httpx
import uvicorn

from src.adapters.amap import AmapProvider
from src.config.settings import Settings, load_settings
from src.main import create_demo_app
from src.tools.registry import ToolContext, ToolRegistry

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PORT = 18099
ORIGIN = f"http://127.0.0.1:{PORT}"


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


def data_ok(client, method, path, body=None, status=200):
    response = client.request(method, path, json=body, headers={
        "Origin": ORIGIN, "Idempotency-Key": str(uuid4())}, timeout=70)
    payload = response.json()
    if response.status_code != status or not payload.get("success"):
        raise AssertionError(f"{method} {path} {response.status_code} {payload}")
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
    raise TimeoutError(last)


def capture(client, sid):
    raw = json.loads((ROOT / "docs/evidence/capture-spike/tester-0.1.1-awd-white20.json").read_text())
    payload = {k: raw[k] for k in ("source_url", "captured_at", "adapter_version",
                                   "page_fingerprint", "readiness", "fields", "issues")}
    payload["issues"] = [{**{k: v for k, v in i.items() if k != "severity"},
                          "blocking": i.get("severity") == "blocking"} for i in payload["issues"]]
    return data_ok(client, "POST", f"/api/sessions/{sid}/captures",
                   {"expected_revision": detail(client, sid)["revision"], "capture": payload},
                   status=201)


def confirm(client, sid, values):
    session = detail(client, sid)
    superseded = {ref for f in session["facts"] for ref in f.get("supersedes") or []}
    current = [f for f in session["facts"] if f["id"] not in superseded and f.get("scope") == "session"]
    changes = [{"key": k, "value": v, "state": "confirmed",
                "supersedes": [f["id"] for f in current if f["key"] == k],
                "evidence_note": "T008 QA"} for k, v in values.items()]
    return data_ok(client, "PATCH", f"/api/sessions/{sid}/context", {
        "expected_revision": session["revision"], "changes": changes,
        "skip_optional_questions": True})


async def around_sample(config, center):
    provider = AmapProvider(config)
    samples = []
    for keyword in ("Tesla", "特斯拉", "特斯拉充电"):
        payload = await provider.request("/v5/place/around", {
            "location": f"{center['longitude']},{center['latitude']}",
            "radius": config.map_radius_m, "keywords": keyword,
            "page_size": config.map_page_size})
        pois = payload.get("pois") or []
        samples.append({
            "keyword": keyword,
            "count": len(pois),
            "names": [f"{p.get('name')} | {p.get('type')}" for p in pois[:8]],
        })
    return samples


async def asr_origin(ws_url, pcm):
    events = []
    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.ws_connect(ws_url, origin=ORIGIN) as ws:
            ready = json.loads((await ws.receive(timeout=12)).data)
            events.append(ready.get("type"))
            if ready.get("type") != "ready":
                return {"first": ready, "events": events}
            for index in range(0, len(pcm), 3200):
                await ws.send_bytes(pcm[index:index + 3200])
                await asyncio.sleep(0.04)
            await ws.send_str(json.dumps({"type": "finish"}))
            finals, partials, finished = [], [], None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                msg = await ws.receive(timeout=12)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                payload = json.loads(msg.data)
                kind = payload.get("type")
                events.append(kind)
                if kind == "partial":
                    partials.append(payload.get("text") or "")
                elif kind == "final":
                    finals.append(payload.get("transcript") or "")
                elif kind in {"finished", "error"}:
                    finished = {k: payload.get(k) for k in ("type", "complete", "code", "incomplete", "message")}
                    break
    return {
        "events": events,
        "partials": [p for p in partials if p],
        "finals": [t for t in finals if t],
        "finished": finished,
    }


def make_pcm(text):
    with tempfile.TemporaryDirectory() as folder:
        aiff, wav = Path(folder) / "a.aiff", Path(folder) / "a.wav"
        subprocess.run(["say", "-r", "180", "-o", str(aiff), text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
                       check=True)
        with wave.open(str(wav), "rb") as handle:
            return handle.readframes(handle.getnframes())


def main():
    results = {}
    base = load_settings()
    tmp = Path(tempfile.mkdtemp(prefix="t008-qa3-"))
    config = Settings(
        database_path=str(tmp / "qa.db"), upload_dir=str(tmp / "uploads"),
        port=PORT, report_origin=ORIGIN,
        bailian_base_url=base.bailian_base_url, bailian_api_key=base.bailian_api_key,
        bailian_asr_ws_url=base.bailian_asr_ws_url, llm_model=base.llm_model,
        asr_model=base.asr_model, amap_web_service_key=base.amap_web_service_key,
        amap_base_url=base.amap_base_url, frontend_dist=base.frontend_dist,
        allowed_extension_origin=base.allowed_extension_origin,
    )
    app = create_demo_app(config)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT,
                                          log_level="warning", access_log=False))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    deadline = time.monotonic() + 15
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    try:
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=70) as client:
            customer = data_ok(client, "POST", "/api/customers", {
                "nickname": "QA定位", "email": "qa-t008-loc@example.com",
                "identity_confirmed": True}, status=201)
            session = data_ok(client, "POST", "/api/sessions", {
                "customer_id": customer["id"], "title": "T008 loc", "visit_at": None}, status=201)
            sid = session["id"]
            capture(client, sid)
            confirm(client, sid, {"region": "望京地铁站", "city": "北京", "has_fixed_parking": False})

            async def execute(args):
                registry = ToolRegistry(config)
                context = ToolContext(sid, detail(client, sid)["revision"],
                                      app.state.session_factory, app.state.write_lock)
                return await registry.execute("search_charging", args, context)

            first = asyncio.run(execute({"region": "望京地铁站", "city": "北京"}))
            candidates = (first.get("data") or {}).get("candidates") or []
            chosen = next((c for c in candidates if c.get("name") == "望京(地铁站)"), candidates[0] if candidates else None)
            results["first_state"] = (first.get("data") or {}).get("state")
            results["candidate_count"] = len(candidates)
            if chosen:
                confirm(client, sid, {"confirmed_location_ref": chosen["id"]})
                results["around_sample"] = asyncio.run(around_sample(config, chosen["center_gcj02"]))
                second = asyncio.run(execute({
                    "region": "望京地铁站", "city": "北京",
                    "confirmed_location_ref": chosen["id"]}))
                data = second.get("data") or {}
                stations = data.get("stations") or []
                if data.get("map_asset_id"):
                    # copy map bytes already saved in upload_dir
                    uploads = Path(config.upload_dir)
                    maps = list((uploads / "maps").glob("*")) if (uploads / "maps").exists() else []
                    results["saved_map_files"] = [p.name for p in maps]
                    for path in maps:
                        (EVIDENCE / ("confirmed-" + path.name)).write_bytes(path.read_bytes())
                results["confirmed"] = {
                    "center_name": chosen["name"],
                    "status": second.get("status"),
                    "state": data.get("state"),
                    "map_status": data.get("map_status"),
                    "map_asset_id": data.get("map_asset_id"),
                    "radius_m": data.get("radius_m"),
                    "warnings": data.get("warnings"),
                    "external_search": data.get("external_search"),
                    "stations": [{
                        "number": s.get("number"), "name": s.get("name"),
                        "center_distance_m": s.get("center_distance_m"),
                        "distance_basis": s.get("distance_basis"),
                        "driving_distance_m": s.get("driving_distance_m"),
                        "driving_duration_seconds": s.get("driving_duration_seconds"),
                        "route_status": s.get("route_status"),
                    } for s in stations],
                }
                save("ac007-confirmed-charging.json", {"first": first.get("data"), "second": data})
                run = data_ok(client, "POST", f"/api/sessions/{sid}/runs", {
                    "intent": "analyze",
                    "message": "已确认查询中心为望京地铁站，请基于该中心查询充电站。",
                    "expected_revision": detail(client, sid)["revision"]}, status=202)
                analyzed = wait_run(client, sid, run["run_id"])
                results["analyze_after_confirm"] = {
                    "status": analyzed["status"],
                    "tools": [e.get("tool_name") for e in analyzed.get("events") or [] if e.get("tool_name")],
                    "result_status": (analyzed.get("result") or {}).get("status"),
                }

            asr = data_ok(client, "POST", f"/api/sessions/{sid}/audio", {
                "expected_revision": detail(client, sid)["revision"], "language": "zh"}, status=201)
            before = detail(client, sid)
            pcm = make_pcm("客户张伟希望月供四千元")
            ws_url = "ws://127.0.0.1:18099" + asr["ws_path"]
            try:
                live = asyncio.run(asr_origin(ws_url, pcm))
            except Exception as error:
                live = {"error": type(error).__name__, "message": str(error)[:300]}
            after = detail(client, sid)
            results["asr"] = {
                "create": asr.get("state"),
                "live": live,
                "revision_unchanged": before["revision"] == after["revision"],
                "timeline_unchanged": len(before["timeline"]) == len(after["timeline"]),
            }
            save("ac004-asr-round3.json", results["asr"])
    except Exception as error:
        results["error"] = {"type": type(error).__name__, "message": str(error)[:400]}
    finally:
        server.should_exit = True
        worker.join(timeout=15)
        save("t008-live-summary-3.json", results)
        print(json.dumps(redact(results), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
