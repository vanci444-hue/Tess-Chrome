"""T-008 isolated live provider verification. Real Qwen/ASR/Amap; isolated SQLite."""
from __future__ import annotations

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

import aiohttp
import httpx
import uvicorn
from src.config.settings import Settings, load_settings
from src.main import create_demo_app

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PORT = 18099
ORIGIN = f"http://127.0.0.1:{PORT}"
RUN_WAIT = 180
PHONE = "13900139008"
EMAIL = "qa-t008-a@example.com"
PHONE_B = "13900139009"
EMAIL_B = "qa-t008-b@example.com"
PHONE_C = "13900139010"
EMAIL_C = "qa-t008-c@example.com"


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
    payload = response.json()
    return response.status_code, payload


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


def capture(client, sid, suffix="20"):
    raw = json.loads(
        (ROOT / f"docs/evidence/capture-spike/tester-0.1.1-awd-white{suffix}.json").read_text()
    )
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
        {
            **{k: v for k, v in issue.items() if k != "severity"},
            "blocking": issue.get("severity") == "blocking",
        }
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
                "evidence_note": "T008 QA 确认",
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


def submit_text(client, sid, text, source="sales_text", asr_id=None):
    body = {
        "text": text,
        "source": source,
        "expected_revision": detail(client, sid)["revision"],
    }
    if asr_id:
        body["asr_session_id"] = asr_id
    run = data_ok(client, "POST", f"/api/sessions/{sid}/inputs", body, status=202)
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


def make_pcm(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        aiff = Path(folder) / "speech.aiff"
        wav = Path(folder) / "speech.wav"
        subprocess.run(["say", "-r", "180", "-o", str(aiff), text], check=True)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
            check=True,
        )
        with wave.open(str(wav), "rb") as handle:
            assert handle.getnchannels() == 1 and handle.getsampwidth() == 2
            assert handle.getframerate() == 16000
            return handle.readframes(handle.getnframes())


async def asr_stream(ws_url: str, pcm: bytes | None):
    events = []
    timeout = aiohttp.ClientTimeout(total=40)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.ws_connect(ws_url, headers={"Origin": ORIGIN}) as ws:
            ready = False
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                msg = await ws.receive(timeout=12)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    payload = json.loads(msg.data)
                    events.append({"type": payload.get("type"), "keys": sorted(payload)})
                    if payload.get("type") == "ready":
                        ready = True
                        break
                    if payload.get("type") == "error":
                        return {"ready": False, "events": events, "error": payload.get("code")}
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    return {"ready": False, "events": events, "closed": True}
            if not ready:
                return {"ready": False, "events": events}
            if pcm:
                chunk = 3200
                for index in range(0, len(pcm), chunk):
                    await ws.send_bytes(pcm[index : index + chunk])
                    await asyncio_sleep(0.05)
            await ws.send_str(json.dumps({"type": "finish"}))
            finals = []
            partials = []
            finished = None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                msg = await ws.receive(timeout=12)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    payload = json.loads(msg.data)
                    kind = payload.get("type")
                    events.append({"type": kind})
                    if kind == "partial":
                        partials.append(payload.get("text") or payload.get("stash") or "")
                    elif kind == "final":
                        finals.append(payload.get("transcript") or "")
                    elif kind == "finished":
                        finished = payload
                        break
                    elif kind == "error":
                        return {
                            "ready": True,
                            "events": events,
                            "error": payload.get("code"),
                            "incomplete": payload.get("incomplete"),
                            "message": payload.get("message"),
                        }
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    break
    return {
        "ready": True,
        "events": events,
        "partials": [p for p in partials if p],
        "finals": [t for t in finals if t],
        "finished": finished,
    }


def asyncio_sleep(seconds):
    import asyncio

    return asyncio.sleep(seconds)


def run_async(coro):
    import asyncio

    return asyncio.run(coro)


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
        raise RuntimeError("isolated QA server did not start on 18099")
    return server, worker, app


def save(name, payload):
    path = EVIDENCE / name
    path.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n")
    return str(path)


def main():
    results = {
        "started_at": utcnow(),
        "origin": ORIGIN,
        "git_head": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT)
        .decode()
        .strip(),
        "provider": "real",
        "cases": {},
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
    tmp = Path(tempfile.mkdtemp(prefix="t008-qa-"))
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
    server, worker, _app = http_server(config)
    try:
        with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=70) as client:
            def remember(error, where):
                results.setdefault("errors", []).append(
                    {"where": where, "type": type(error).__name__, "message": str(error)[:400]}
                )
            health = data_ok(client, "GET", "/api/health")
            results["health"] = {
                "status": health["status"],
                "capabilities": health["capabilities"],
                "database": health["database"],
            }
            results["cases"]["health"] = health["capabilities"] == {
                "llm": "configured",
                "asr": "configured",
                "maps": "configured",
            } and health["status"] == "ready"

            # AC-022 CRM extract + missing contact + no customer until confirm
            preview = data_ok(
                client,
                "POST",
                "/api/customers/extract",
                {
                    "text": (
                        f"客户称呼 QA甲；手机 {PHONE}；邮箱 {EMAIL}；"
                        "此前沟通月供目标四千左右，关注后排体验。"
                    )
                },
            )
            missing_preview = data_ok(
                client,
                "POST",
                "/api/customers/extract",
                {"text": "客户称呼 QA乙，暂无手机和邮箱，只说最近在看 Model Y。"},
            )
            no_contact = request(
                client,
                "POST",
                "/api/customers",
                {"nickname": "QA乙", "identity_confirmed": True},
                status=None,
            )
            created = data_ok(
                client,
                "POST",
                "/api/customers",
                {
                    "nickname": preview["proposed"]["nickname"] or "QA甲",
                    "phone": PHONE,
                    "email": EMAIL,
                    "extraction_id": preview["extraction_id"],
                    "identity_confirmed": True,
                },
                status=201,
            )
            listed = data_ok(client, "GET", "/api/customers")
            results["cases"]["ac022"] = {
                "preview_missing": preview.get("missing"),
                "proposed_nickname": bool(preview["proposed"].get("nickname")),
                "has_contact": bool(preview["proposed"].get("phone") or preview["proposed"].get("email")),
                "historical_facts": len(preview.get("historical_facts") or []),
                "incomplete_missing": missing_preview.get("missing"),
                "create_without_contact_status": no_contact[0],
                "create_without_contact_code": no_contact[1].get("error_code"),
                "customer_created": bool(created.get("id")),
                "extract_did_not_list_until_confirm": created["id"]
                in {item["id"] for item in listed["items"]},
            }
            save("ac022-crm.json", {"preview": preview, "missing": missing_preview, "created_id": created["id"]})

            # Session A: home charging, skip charging tool, no map link
            session_a = data_ok(
                client,
                "POST",
                "/api/sessions",
                {"customer_id": created["id"], "title": "T008-A 家充齐全", "visit_at": None},
                status=201,
            )
            sid_a = session_a["id"]
            cap_a = capture(client, sid_a)
            submit_text(
                client,
                sid_a,
                "客户已有固定车位和家充桩，试驾了这台候选车，预算按官网金融方案即可，没有新的月供约束，也不需要查周边充电站或能源开支。",
            )
            confirm(
                client,
                sid_a,
                {
                    "has_fixed_parking": True,
                    "home_charging": True,
                    "monthly_budget": 400000,
                },
                skip_optional=True,
            )
            run_a = start_run(client, sid_a, "prepare_report")
            tools_a = tool_names(run_a)
            draft_a = detail(client, sid_a).get("draft")
            charging_a = next(
                (
                    m
                    for m in (draft_a or {}).get("report_data", {}).get("modules", [])
                    if m.get("type") == "charging"
                ),
                {},
            )
            results["cases"]["ac029_skip"] = {
                "run_status": run_a["status"],
                "tools": tools_a,
                "skipped_search_charging": "search_charging" not in tools_a,
                "skipped_energy": "calculate_energy" not in tools_a,
                "charging_module_status": charging_a.get("status"),
                "no_fake_map_link": not (charging_a.get("data") or {}).get("external_search"),
            }
            save("ac029-skip-tools.json", {"run": run_a, "charging": charging_a})

            # Session B: parking clue + maps + trial mismatch + 3-question cap
            customer_b = data_ok(
                client,
                "POST",
                "/api/customers",
                {
                    "nickname": "QA丙",
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
                {"customer_id": customer_b["id"], "title": "T008-B 无车位望京", "visit_at": None},
                status=201,
            )
            sid_b = session_b["id"]
            capture(client, sid_b, "20")
            extract_b = submit_text(
                client,
                sid_b,
                "客户没有固定车位，常用区域在望京地铁站附近。实际试驾的是后轮驱动，具体版本客户说不太确定。"
                "月供希望四千左右，也关心以后能源开支。公司充电条件客户说不知道。",
            )
            questions_b = (extract_b.get("result") or {}).get("questions") or []
            session_after = detail(client, sid_b)
            facts_b = current_facts(session_after)
            q_texts = [q.get("text", "") for q in questions_b]
            parking_related = any(
                any(token in text for token in ("车位", "充电", "公司", "补能", "家充"))
                for text in q_texts
            )
            trial = session_after.get("trial_vehicle")
            capture_variant = None
            for cap in session_after.get("captures") or []:
                for field in cap.get("immutable_payload", {}).get("fields") or []:
                    if field.get("key") == "variant":
                        capture_variant = field.get("value") or field.get("raw_text")
            unknown_keys = [
                f["key"]
                for f in facts_b
                if f["key"] in {"home_charging", "trial_variant"} and f["state"] in {"proposed", "unknown"}
            ]
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
                unknown=unknown_keys or ["home_charging"],
                skip_optional=False,
                reply={
                    "reply_to_run_id": extract_b["run_id"],
                    "reply_to_question_ids": [q["id"] for q in questions_b if q.get("id")],
                }
                if questions_b
                else None,
            )
            # Second extract should not re-ask the already unknown home charging.
            loop_check = submit_text(
                client,
                sid_b,
                "公司充电条件还是不知道，请不要再问同一件事。常用还是望京地铁站附近。",
            )
            loop_questions = (loop_check.get("result") or {}).get("questions") or []
            repeat_unknown = [
                q
                for q in loop_questions
                if (not q.get("required"))
                and any(token in (q.get("text") or "") for token in ("公司充电", "家充", "充电条件"))
            ]
            confirm(client, sid_b, {}, skip_optional=True)
            run_b = start_run(client, sid_b, "prepare_report")
            if run_b["status"] == "needs_confirmation":
                loc_facts = [
                    f
                    for f in current_facts(detail(client, sid_b))
                    if f["key"] == "confirmed_location_ref" and f["state"] == "proposed"
                ]
                if loc_facts:
                    confirm(
                        client,
                        sid_b,
                        {"confirmed_location_ref": loc_facts[0]["value"]},
                        skip_optional=True,
                        reply={
                            "reply_to_run_id": run_b["run_id"],
                            "reply_to_question_ids": [
                                q["id"] for q in (run_b.get("result") or {}).get("questions") or []
                            ],
                        },
                    )
                    run_b = start_run(
                        client, sid_b, "prepare_report", continue_run_id=run_b["run_id"]
                    )
                else:
                    confirm(
                        client,
                        sid_b,
                        {},
                        skip_optional=True,
                        reply={"reply_to_run_id": run_b["run_id"]},
                    )
                    run_b = start_run(
                        client, sid_b, "prepare_report", continue_run_id=run_b["run_id"]
                    )
            tools_b = tool_names(run_b)
            session_b_final = detail(client, sid_b)
            draft_b = session_b_final.get("draft") or {}
            charging_b = next(
                (
                    m
                    for m in draft_b.get("report_data", {}).get("modules", [])
                    if m.get("type") == "charging"
                ),
                {},
            )
            charging_data = charging_b.get("data") or {}
            stations = charging_data.get("stations") or []
            distance_notes = []
            for station in stations:
                distance_notes.append(
                    {
                        "number": station.get("number"),
                        "name": station.get("name"),
                        "center_distance_m": station.get("distance_m") or station.get("distance"),
                        "driving_distance_m": station.get("driving_distance_m")
                        or station.get("route_distance_m"),
                        "duration_s": station.get("duration_s") or station.get("driving_duration_s"),
                    }
                )
            unknown_now = [
                f["key"] for f in current_facts(session_b_final) if f["state"] == "unknown"
            ]
            pending = (draft_b.get("report_data") or {}).get("summary", {}).get("pending") or []
            results["cases"]["extract_b"] = {
                "run_status": extract_b["status"],
                "question_count": len(questions_b),
                "questions_le_3": len(questions_b) <= 3,
                "parking_related": parking_related,
                "question_texts": q_texts,
                "trial_vehicle": trial,
                "capture_variant": capture_variant,
                "unknown_after_confirm": unknown_now,
                "repeat_unknown_optional": [q.get("text") for q in repeat_unknown],
                "loop_question_count": len(loop_questions),
            }
            results["cases"]["maps_b"] = {
                "prepare_status": run_b["status"],
                "tools": tools_b,
                "used_search_charging": "search_charging" in tools_b,
                "charging_status": charging_b.get("status"),
                "station_count": len(stations),
                "map_status": charging_data.get("map_status"),
                "map_asset_id": charging_data.get("map_asset_id"),
                "radius_m": charging_data.get("radius_m"),
                "warnings": charging_data.get("warnings"),
                "external_search": charging_data.get("external_search"),
                "distance_notes": distance_notes,
                "state": charging_data.get("state"),
            }
            save(
                "ac-maps-and-extract.json",
                {
                    "extract": extract_b,
                    "loop": loop_check,
                    "prepare": run_b,
                    "charging": charging_b,
                    "trial": trial,
                    "facts": current_facts(session_b_final),
                    "pending": pending,
                },
            )

            published = None
            if draft_b and run_b["status"] == "succeeded":
                issues = draft_b.get("blocking_issues") or []
                blocking = [i for i in issues if i.get("blocking")]
                if not blocking:
                    reviewed = data_ok(
                        client,
                        "PATCH",
                        f"/api/sessions/{sid_b}/drafts/{draft_b['id']}",
                        {
                            "expected_revision": session_b_final["revision"],
                            "draft_revision": draft_b["draft_revision"],
                            "summary": draft_b["report_data"]["summary"],
                        },
                    )
                    published = data_ok(
                        client,
                        "POST",
                        f"/api/sessions/{sid_b}/reports",
                        {
                            "draft_id": draft_b["id"],
                            "draft_revision": reviewed["draft_revision"],
                            "expected_revision": detail(client, sid_b)["revision"],
                            "review_confirmed": True,
                        },
                        status=201,
                    )
            report = None
            if published:
                report = data_ok(client, "GET", f"/api/reports/{published['report_id']}")
                charging_pub = next(
                    (m for m in report["modules"] if m.get("type") == "charging"), {}
                )
                url = ((charging_pub.get("data") or {}).get("external_search") or {}).get("url")
                parsed = urlparse(url) if url else None
                query = parse_qs(parsed.query) if parsed else {}
                blob = json.dumps(report, ensure_ascii=False)
                results["cases"]["ac043"] = {
                    "published": True,
                    "url": url,
                    "host_ok": bool(parsed and parsed.scheme == "https" and parsed.hostname == "uri.amap.com"),
                    "keyword": (query.get("keyword") or [None])[0],
                    "city": (query.get("city") or [None])[0],
                    "src": (query.get("src") or [None])[0],
                    "has_identity": any(
                        token in blob for token in (PHONE_B, EMAIL_B, "QA丙", "crm")
                    )
                    and "QA丙" in blob,
                    "has_phone_or_email": PHONE_B in blob or EMAIL_B in blob,
                    "has_key_query": "key=" in (url or "").lower(),
                    "observed_at": (charging_pub.get("data") or {}).get("observed_at"),
                    "report_id": published["report_id"],
                    "report_url": published.get("url"),
                }
                save("ac043-report.json", {"published": published, "charging": charging_pub, "url": url})
            else:
                results["cases"]["ac043"] = {
                    "published": False,
                    "prepare_status": run_b["status"],
                    "blocking": (draft_b or {}).get("blocking_issues"),
                }

            # AC-020 followup with two fixtures if we have a published report; else publish A if possible
            follow_sid = None
            if published:
                follow_sid = sid_b
            elif draft_a and run_a["status"] == "succeeded":
                session_a_final = detail(client, sid_a)
                draft_now = session_a_final.get("draft") or {}
                blocking = [i for i in (draft_now.get("blocking_issues") or []) if i.get("blocking")]
                if not blocking:
                    reviewed = data_ok(
                        client,
                        "PATCH",
                        f"/api/sessions/{sid_a}/drafts/{draft_now['id']}",
                        {
                            "expected_revision": session_a_final["revision"],
                            "draft_revision": draft_now["draft_revision"],
                            "summary": draft_now["report_data"]["summary"],
                        },
                    )
                    pub_a = data_ok(
                        client,
                        "POST",
                        f"/api/sessions/{sid_a}/reports",
                        {
                            "draft_id": draft_now["id"],
                            "draft_revision": reviewed["draft_revision"],
                            "expected_revision": detail(client, sid_a)["revision"],
                            "review_confirmed": True,
                        },
                        status=201,
                    )
                    follow_sid = sid_a
                    results["cases"]["published_a"] = pub_a.get("report_id")
            follow_results = []
            if follow_sid:
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
                    blob = json.dumps(redact({"run": run_f, "followup": followup}), ensure_ascii=False)
                    follow_results.append(
                        {
                            "fixture": fixture,
                            "event_ids": injected.get("event_ids"),
                            "status": run_f["status"],
                            "followup": followup,
                            "leaked_private_sentinel": "私人内容测试哨兵" in blob,
                            "source_event_ids": (followup or {}).get("source_event_ids")
                            if isinstance(followup, dict)
                            else None,
                        }
                    )
                    # Keep only last fixture's pending events by using a second published session if needed.
                    if fixture == "family-charging-followup":
                        save("ac020-charging-followup.json", {"run": run_f, "followup": followup})
            results["cases"]["ac020"] = follow_results

            # AC-028 conflict across CRM/history and new input
            preview_c = data_ok(
                client,
                "POST",
                "/api/customers/extract",
                {"text": f"客户称呼 QA丁；邮箱 {EMAIL_C}；历史记录月供目标五千元。"},
            )
            customer_c = data_ok(
                client,
                "POST",
                "/api/customers",
                {
                    "nickname": "QA丁",
                    "email": EMAIL_C,
                    "extraction_id": preview_c["extraction_id"],
                    "identity_confirmed": True,
                },
                status=201,
            )
            session_c1 = data_ok(
                client,
                "POST",
                "/api/sessions",
                {"customer_id": customer_c["id"], "title": "T008-C1 历史预算", "visit_at": None},
                status=201,
            )
            sid_c1 = session_c1["id"]
            capture(client, sid_c1)
            confirm(client, sid_c1, {"monthly_budget": 400000}, skip_optional=True)
            budget_c1 = next(
                f["value"] for f in current_facts(detail(client, sid_c1)) if f["key"] == "monthly_budget"
            )
            session_c2 = data_ok(
                client,
                "POST",
                "/api/sessions",
                {"customer_id": customer_c["id"], "title": "T008-C2 新预算冲突", "visit_at": None},
                status=201,
            )
            sid_c2 = session_c2["id"]
            capture(client, sid_c2)
            conflict_run = submit_text(
                client,
                sid_c2,
                "本次销售复盘：客户现在说月供八千，和以前五千的说法不一样，请按八千处理前先确认。",
            )
            facts_c2 = current_facts(detail(client, sid_c2))
            conflict_facts = [f for f in facts_c2 if f["key"] == "monthly_budget"]
            questions_c2 = (conflict_run.get("result") or {}).get("questions") or []
            required_conflict = [q for q in questions_c2 if q.get("required")]
            publish_blocked = None
            prepare_c2 = start_run(client, sid_c2, "prepare_report")
            draft_c2 = detail(client, sid_c2).get("draft")
            if draft_c2:
                code, payload = request(
                    client,
                    "POST",
                    f"/api/sessions/{sid_c2}/reports",
                    {
                        "draft_id": draft_c2["id"],
                        "draft_revision": draft_c2["draft_revision"],
                        "expected_revision": detail(client, sid_c2)["revision"],
                        "review_confirmed": True,
                    },
                )
                publish_blocked = {"status": code, "error_code": payload.get("error_code"), "metadata": payload.get("metadata")}
            new_id = next((f["id"] for f in conflict_facts if f["state"] in {"proposed", "conflict"}), None)
            old_ids = [f["id"] for f in conflict_facts if f["id"] != new_id]
            confirm(
                client,
                sid_c2,
                {"monthly_budget": 800000},
                skip_optional=True,
                reply={"reply_to_run_id": conflict_run["run_id"]} if conflict_run.get("status") == "needs_confirmation" else None,
            )
            after_c2 = next(
                f for f in current_facts(detail(client, sid_c2)) if f["key"] == "monthly_budget"
            )
            after_c1 = next(
                f for f in current_facts(detail(client, sid_c1)) if f["key"] == "monthly_budget"
            )
            results["cases"]["ac028"] = {
                "historical_preview_facts": len(preview_c.get("historical_facts") or []),
                "c1_budget": budget_c1,
                "conflict_run_status": conflict_run["status"],
                "budget_facts_states": [f["state"] for f in conflict_facts],
                "required_questions": [q.get("text") for q in required_conflict],
                "publish_blocked": publish_blocked,
                "prepare_status": prepare_c2["status"],
                "confirmed_c2": after_c2["value"],
                "c1_unchanged": after_c1["value"] == 400000,
                "c1_id_unchanged": after_c1["id"] != after_c2["id"],
            }
            save(
                "ac028-conflict.json",
                {
                    "conflict_run": conflict_run,
                    "c1": after_c1,
                    "c2": after_c2,
                    "publish_blocked": publish_blocked,
                },
            )

            # ASR: create, stream TTS pcm, finish must not create timeline/run
            sid_asr = sid_a
            asr = data_ok(
                client,
                "POST",
                f"/api/sessions/{sid_asr}/audio",
                {"expected_revision": detail(client, sid_asr)["revision"], "language": "zh"},
                status=201,
            )
            before = detail(client, sid_asr)
            pcm = make_pcm("客户张伟希望月供四千元")
            ws_url = ORIGIN.replace("http", "ws") + asr["ws_path"]
            asr_live = run_async(asr_stream(ws_url, pcm))
            after = detail(client, sid_asr)
            asr_runs = [
                item
                for item in after.get("timeline") or []
                if item.get("created_at", "") >= before.get("updated_at", "")
            ]
            # Compare timeline length and facts count: finish must not add sales message automatically.
            results["cases"]["asr"] = {
                "created_state": asr.get("state"),
                "ws_path": asr.get("ws_path"),
                "ready": asr_live.get("ready"),
                "partials": asr_live.get("partials"),
                "finals": asr_live.get("finals"),
                "finished": asr_live.get("finished"),
                "error": asr_live.get("error"),
                "timeline_before": len(before.get("timeline") or []),
                "timeline_after": len(after.get("timeline") or []),
                "revision_before": before["revision"],
                "revision_after": after["revision"],
                "pcm_bytes": len(pcm),
                "events": asr_live.get("events"),
            }
            save("ac004-asr.json", {"create": asr, "live": asr_live, "timeline_after": after.get("timeline")})

            # Manual send of corrected ASR-like text after stop (API equivalent)
            try:
                if asr_live.get("finals"):
                    spoken = asr_live["finals"][-1]
                else:
                    spoken = "客户张伟希望月供四千元"
                corrected = spoken + "（销售已改为四千八百）"
                before_send = detail(client, sid_asr)
                send_run = data_ok(
                    client,
                    "POST",
                    f"/api/sessions/{sid_asr}/inputs",
                    {
                        "text": corrected,
                        "source": "asr_corrected",
                        "asr_session_id": asr["asr_session_id"],
                        "expected_revision": before_send["revision"],
                    },
                    status=202,
                )
                send_wait = wait_run(client, sid_asr, send_run["run_id"])
                after_send = detail(client, sid_asr)
                results["cases"]["asr_manual_send"] = {
                    "send_status": send_wait["status"],
                    "revision_changed": after_send["revision"] > before_send["revision"],
                    "timeline_grew": len(after_send.get("timeline") or [])
                    > len(before_send.get("timeline") or []),
                    "used_corrected_text": any(
                        "四千八百" in json.dumps(item, ensure_ascii=False)
                        for item in after_send.get("timeline") or []
                    ),
                }
            except Exception as error:
                remember(error, "asr_manual_send")
    except Exception as error:
        results.setdefault("errors", []).append(
            {"where": "main", "type": type(error).__name__, "message": str(error)[:500]}
        )
        raise
    finally:
        server.should_exit = True
        worker.join(timeout=15)
        results["server_stopped"] = not worker.is_alive()
        results["prod_db_after"] = {
            "exists": prod_db.exists(),
            "size": prod_db.stat().st_size if prod_db.exists() else 0,
        }
        results["finished_at"] = utcnow()
        save("t008-live-summary.json", results)
        print(json.dumps(redact(results), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
