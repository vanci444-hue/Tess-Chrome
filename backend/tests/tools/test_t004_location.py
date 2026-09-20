"""当前确认 Fact 与跨会话位置引用的独立回归。"""

from src.db.models import Fact, LocationCandidate, Session
from src.tools.registry import ToolRegistry
from test_registry import Maps
from test_registry import context as context_fixture

context = context_fixture


async def test_superseded_and_foreign_location_not_usable(context):
    config, ctx = context
    maps = Maps()
    registry = ToolRegistry(config, maps)
    result = await registry.execute("search_charging", {"region": "望京"}, ctx)
    first, second = [x["id"] for x in result["data"]["candidates"]]
    async with ctx.session_factory() as db:
        old = Fact(
            session_id=ctx.session_id,
            key="confirmed_location_ref",
            value=first,
            state="confirmed",
            source_kind="sales_input",
            source_id=ctx.session_id,
        )
        db.add(old)
        await db.flush()
        db.add(
            Fact(
                session_id=ctx.session_id,
                key="confirmed_location_ref",
                value=second,
                state="confirmed",
                source_kind="sales_input",
                source_id=ctx.session_id,
                supersedes=[old.id],
            )
        )
        current_session = await db.get(Session, ctx.session_id)
        foreign_session = Session(customer_id=current_session.customer_id, title="另一会话")
        db.add(foreign_session)
        await db.flush()
        foreign = LocationCandidate(
            session_id=foreign_session.id,
            provider_poi_id="foreign",
            name="外会话地点",
            city="北京",
            address="区域",
            center_gcj02={"longitude": 116.4, "latitude": 40},
        )
        db.add(foreign)
        await db.commit()
        foreign_id = foreign.id
    old_result = await registry.execute(
        "search_charging", {"region": "望京", "confirmed_location_ref": first}, ctx
    )
    assert (
        old_result["status"] == "failed" and old_result["error"]["code"] == "LOCATION_NOT_CONFIRMED"
    )
    current = await registry.execute(
        "search_charging", {"region": "望京", "confirmed_location_ref": second}, ctx
    )
    assert current["data"]["stations"] and current["status"] == "partial"
    other = await registry.execute(
        "search_charging", {"region": "望京", "confirmed_location_ref": foreign_id}, ctx
    )
    assert other["status"] == "failed" and not other["data"]
    missing = await registry.execute("lookup_official_knowledge", {"topic": "air_quality"}, ctx)
    assert missing["data"]["state"] == "missing" and missing["source_refs"] == []
    energy = await registry.execute(
        "calculate_energy",
        dict(
            annual_km=12000,
            years=3,
            kwh_per_100km=17,
            electricity_yuan_per_kwh=1.2,
            liters_per_100km=8,
            fuel_yuan_per_liter=7.8,
            source="示例试算输入",
        ),
        ctx,
    )
    assert energy["data"]["report_module"]["status"] == "estimate"
    assert "未核验为销售已确认事实" in energy["source_refs"][0]["label"]
    assert len(energy["data"]["assumptions"]) == 7 and "仅能源" in energy["data"]["scope"]
