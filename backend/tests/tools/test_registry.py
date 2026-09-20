"""会话绑定、真实抓取单位、地点确认与地图部分失败的隔离合同测试。"""

import asyncio
import json
from pathlib import Path

import pytest
from src.adapters.base import ProviderError
from src.config.settings import Settings
from src.db.models import Asset, Capture, Customer, Fact, Session
from src.db.session import create_database, init_db
from src.tools.registry import ToolContext, ToolRegistry


@pytest.fixture
async def context(tmp_path):
    config = Settings(
        database_path=str(tmp_path / "db.sqlite"), upload_dir=str(tmp_path / "uploads")
    )
    engine, factory = create_database(config)
    await init_db(engine)
    async with factory() as db:
        customer = Customer(nickname="测试")
        db.add(customer)
        await db.flush()
        session = Session(customer_id=customer.id, title="测试")
        db.add(session)
        await db.commit()
        ctx = ToolContext(session.id, 1, factory, asyncio.Lock())
    yield config, ctx
    await engine.dispose()


class Maps:
    many = True
    image_fails = True

    async def search_region(self, *args):
        results = [
            dict(
                provider_poi_id="a",
                name="望京",
                city="北京",
                address="A",
                center_gcj02={"longitude": 116.4, "latitude": 40},
            )
        ]
        return results * 2 if self.many else results

    async def stations(self, *args):
        return [
            dict(
                id="station",
                number=1,
                name="Tesla充电站",
                location_gcj02={"longitude": 116.41, "latitude": 40},
                center_distance_m=1000,
                distance_basis="高德中心点距离",
                route_status="missing",
                driving_distance_m=None,
                driving_duration_seconds=None,
            )
        ]

    async def route(self, *args):
        raise ProviderError("ROUTE_MISSING", "路线不可用")

    async def static_map(self, *args):
        if self.image_fails:
            raise ProviderError("IMAGE_MISSING", "图片不可用")
        return b"\x89PNG\r\n\x1a\ntest", "image/png"


async def test_ambiguous_confirmed_ref_required_partial_map(context):
    config, ctx = context
    maps = Maps()
    registry = ToolRegistry(config, maps)
    result = await registry.execute(
        "search_charging", {"region": "望京", "city": "北京"}, ctx, "c1"
    )
    assert result["status"] == "partial" and result["data"]["state"] == "ambiguous"
    ref = result["data"]["candidates"][0]["id"]
    args = {"region": "望京", "city": "北京", "confirmed_location_ref": ref}
    unconfirmed = await registry.execute("search_charging", args, ctx, "c2")
    assert (
        unconfirmed["status"] == "failed"
        and unconfirmed["error"]["code"] == "LOCATION_NOT_CONFIRMED"
    )
    async with ctx.session_factory() as db:
        db.add(
            Fact(
                session_id=ctx.session_id,
                key="confirmed_location_ref",
                value=ref,
                state="confirmed",
                source_kind="sales_input",
                source_id=ctx.session_id,
            )
        )
        await db.commit()
    partial = await registry.execute("search_charging", args, ctx, "c3")
    assert (
        partial["status"] == "partial"
        and partial["data"]["stations"][0]["driving_duration_seconds"] is None
    )
    assert partial["data"]["map_asset_id"] is None
    maps.image_fails = False
    asset = await registry.execute("search_charging", args, ctx, "c4")
    aid = asset["data"]["map_asset_id"]
    assert aid
    async with ctx.session_factory() as db:
        row = await db.get(Asset, aid)
        assert row.session_id == ctx.session_id and "key=" not in row.source_url
        assert (config.upload_path / row.relative_path).exists()
    assert asset["data"]["report_module"]["data"]["stations"][0]["number"] == 1


async def test_real_capture_fen_and_source_label(context):
    config, ctx = context
    payload = json.loads(
        (
            Path(__file__).parents[3] / "docs/evidence/capture-spike/tester-0.1.1-awd-white20.json"
        ).read_text()
    )
    async with ctx.session_factory() as db:
        capture = Capture(
            session_id=ctx.session_id, immutable_payload=payload, validity="valid", issues=[]
        )
        db.add(capture)
        await db.commit()
        cid = capture.id
    result = await ToolRegistry(config).execute(
        "calculate_finance",
        {
            "capture_id": cid,
            "product_id": "mock-zero-60",
            "down_payment_fen": 7990000,
            "terms_months": [60],
        },
        ctx,
    )
    assert result["status"] == "ok"
    assert result["data"]["solutions"][0]["principal_fen"] == 24160000
    assert result["data"]["report_module"]["status"] == "mock"
    assert result["data"]["constraints"]["down_payment_fen"] == 7990000
    async with ctx.session_factory() as db:
        original = await db.get(Capture, cid)
        assert original.immutable_payload == payload
        original.validity = "conflict"
        await db.commit()
    refused = await ToolRegistry(config).execute(
        "calculate_finance", {"capture_id": cid, "product_id": "mock-zero-60"}, ctx
    )
    assert refused["error"]["code"] == "CAPTURE_INVALID"


async def test_stale_and_unknown_inputs_do_not_generate_results(context):
    config, ctx = context
    registry = ToolRegistry(config)
    result = await registry.execute("calculate_energy", {"annual_km": 20000}, ctx)
    assert result["status"] == "failed" and result["data"] == {}
    async with ctx.session_factory() as db:
        row = await db.get(Session, ctx.session_id)
        row.revision = 2
        await db.commit()
    result = await registry.execute("lookup_official_knowledge", {"topic": "family"}, ctx)
    assert result["status"] == "failed"
