"""受限工具目录。会话、修订和图片归属由服务端注入，不接受模型指定。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.adapters.amap import AmapProvider, search_link
from src.adapters.base import ProviderError
from src.config.settings import Settings
from src.db.models import Asset, Capture, Fact, LocationCandidate, utcnow
from src.models.contracts import BusinessError
from src.repositories.store import Store
from src.tools.energy import calculate_energy
from src.tools.finance import calculate_finance

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass
class ToolContext:
    session_id: str
    source_revision: int
    session_factory: async_sessionmaker[AsyncSession]
    write_lock: asyncio.Lock


def source(
    kind: str,
    label: str,
    url: str | None = None,
    identity: str | None = None,
    observed_at: str | None = None,
) -> dict:
    return {
        "id": identity or str(uuid4()),
        "kind": kind,
        "url": url,
        "observed_at": observed_at or utcnow(),
        "label": label,
    }


class ToolRegistry:
    def __init__(self, config: Settings, amap: AmapProvider | None = None):
        self.config, self.amap = config, amap or AmapProvider(config)

    def schemas(self) -> list[dict]:
        string = {"type": "string"}
        integer = {"type": "integer", "minimum": 0}
        number = {"type": "number", "exclusiveMinimum": 0}
        definitions = [
            (
                "search_charging",
                "查询已确认区域附近真实充电站；有同名地点时需确认",
                {
                    "region": string,
                    "city": {"type": ["string", "null"]},
                    "confirmed_location_ref": {"type": ["string", "null"]},
                    "radius_m": integer,
                },
                ["region"],
            ),
            (
                "list_finance_products",
                "读取明确标识的 Mock 金融产品规则",
                {"capture_id": string},
                ["capture_id"],
            ),
            (
                "calculate_finance",
                "用已知产品规则计算首付与月供硬约束，金额单位分",
                {
                    "capture_id": string,
                    "product_id": string,
                    "down_payment_min_fen": integer,
                    "down_payment_max_fen": integer,
                    "down_payment_fen": integer,
                    "terms_months": {"type": "array", "items": {"type": "integer", "minimum": 1}},
                    "monthly_cap_fen": {"type": ["integer", "null"], "minimum": 1},
                },
                ["capture_id", "product_id"],
            ),
            (
                "calculate_energy",
                "仅计算能源成本，必须提供全部假设及明确来源，不得补未知",
                {
                    "annual_km": number,
                    "years": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": self.config.energy_max_years,
                    },
                    "kwh_per_100km": number,
                    "electricity_yuan_per_kwh": number,
                    "liters_per_100km": number,
                    "fuel_yuan_per_liter": number,
                    "source": string,
                },
                [
                    "annual_km",
                    "years",
                    "kwh_per_100km",
                    "electricity_yuan_per_kwh",
                    "liters_per_100km",
                    "fuel_yuan_per_liter",
                    "source",
                ],
            ),
            (
                "lookup_official_knowledge",
                "仅查询已审核官方资料；safety/family，其他主题返回缺失",
                {"topic": string},
                ["topic"],
            ),
        ]
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                        "additionalProperties": False,
                    },
                },
            }
            for name, desc, props, required in definitions
        ]

    def validate(self, name: str, args: dict):
        schema = next(
            (s["function"]["parameters"] for s in self.schemas() if s["function"]["name"] == name),
            None,
        )
        if schema is None:
            raise ProviderError("TOOL_NOT_ALLOWED", "工具不在允许目录中")
        if (
            not isinstance(args, dict)
            or set(args) - set(schema["properties"])
            or set(schema["required"]) - set(args)
        ):
            raise ProviderError("TOOL_ARGUMENTS_INVALID", "工具参数缺失或包含未允许字段")
        for key, value in args.items():
            rule = schema["properties"][key]
            types = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
            valid = (
                (value is None and "null" in types)
                or (isinstance(value, str) and "string" in types)
                or (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and "number" in types
                )
                or (isinstance(value, int) and not isinstance(value, bool) and "integer" in types)
                or (isinstance(value, list) and "array" in types)
            )
            if not valid:
                raise ProviderError("TOOL_ARGUMENTS_INVALID", "工具参数类型错误")
            if isinstance(value, str) and (
                not value.strip() or len(value) > self.config.max_text_chars
            ):
                raise ProviderError("TOOL_ARGUMENTS_INVALID", "工具文本参数为空或过长")
            if isinstance(value, (int, float)):
                import math

                if (
                    not math.isfinite(value)
                    or ("minimum" in rule and value < rule["minimum"])
                    or ("maximum" in rule and value > rule["maximum"])
                    or ("exclusiveMinimum" in rule and value <= rule["exclusiveMinimum"])
                ):
                    raise ProviderError("TOOL_ARGUMENTS_INVALID", "工具数字参数超出范围")
            if isinstance(value, list) and (
                len(value) > self.config.max_tool_calls
                or any(not isinstance(x, int) or isinstance(x, bool) or x <= 0 for x in value)
            ):
                raise ProviderError("TOOL_ARGUMENTS_INVALID", "期限列表无效")

    async def execute(self, name: str, args: dict, context: ToolContext, call_id: str = "") -> dict:
        observation: dict[str, Any] = {
            "call_id": call_id,
            "tool": name,
            "status": "ok",
            "artifact_id": None,
            "data": {},
            "error": None,
            "source_refs": [],
            "observed_at": utcnow(),
        }
        try:
            self.validate(name, args)
            async with context.session_factory() as db:
                await Store(db).check_revision(context.session_id, context.source_revision)
            if name == "search_charging":
                data, refs, partial = await self.charging(args, context)
                module_type, module_status = (
                    "charging",
                    "ready" if data.get("stations") else "missing",
                )
                observation["status"] = "partial" if partial else "ok"
            elif name in {"list_finance_products", "calculate_finance"}:
                async with context.session_factory() as db:
                    capture = await Store(db).require(
                        Capture, args["capture_id"], context.session_id
                    )
                    if (
                        not capture.active
                        or capture.validity == "conflict"
                        or any(i.get("blocking") for i in capture.issues)
                    ):
                        raise ProviderError("CAPTURE_INVALID", "候选已移除或不可用于计算")
                    payload = capture.immutable_payload
                fixture = json.loads((FIXTURES / "finance/products.json").read_text())
                refs = [
                    source(
                        "mock",
                        fixture["label"],
                        identity="mock-finance-products",
                        observed_at=fixture["observed_at"],
                    ),
                    source(
                        "capture",
                        "本次官网配置快照",
                        payload.get("source_url"),
                        args["capture_id"],
                        payload.get("captured_at"),
                    ),
                ]
                if name == "list_finance_products":
                    data = {
                        "capture_id": args["capture_id"],
                        "products": fixture["products"],
                        "source_kind": "mock",
                    }
                    module_type = None
                    module_status = "mock"
                else:
                    product = next(
                        (p for p in fixture["products"] if p["id"] == args["product_id"]), None
                    )
                    if not product:
                        raise ProviderError("FINANCE_PRODUCT_NOT_FOUND", "指定金融规则不存在")
                    field = next(
                        (f for f in payload["fields"] if f["key"] == "vehicle_price"), None
                    )
                    if (
                        not field
                        or field.get("unit") not in {"fen", "CNY_fen"}
                        or not isinstance(field.get("value"), int)
                    ):
                        raise ProviderError("VEHICLE_PRICE_MISSING", "候选车价缺失或单位不明确")
                    data = calculate_finance(
                        field["value"],
                        product,
                        {k: v for k, v in args.items() if k not in {"capture_id", "product_id"}},
                    )
                    data.update(
                        capture_id=args["capture_id"],
                        product_id=product["id"],
                        capture_validity=capture.validity,
                        capture_issues=capture.issues,
                        product_rules=product,
                    )
                    module_type, module_status = "finance", "mock"
            elif name == "calculate_energy":
                data = calculate_energy(args, self.config.energy_max_years)
                refs = [source("estimate", "试算假设（未核验为销售已确认事实）：" + args["source"])]
                module_type, module_status = "energy", "estimate"
            else:
                entries = json.loads((FIXTURES / "knowledge/approved.json").read_text())["entries"]
                entries = [e for e in entries if e["topic"] == args["topic"]]
                data = {
                    "topic": args["topic"],
                    "entries": entries,
                    "state": "ready" if entries else "missing",
                }
                refs = [
                    source("official_knowledge", e["title"], e["url"], observed_at=e["reviewed_at"])
                    for e in entries
                ]
                module_type, module_status = "family", "ready" if entries else "missing"
            if module_type:
                data = {
                    **data,
                    "report_module": {
                        "type": module_type,
                        "status": module_status,
                        "source_refs": refs,
                        "data": dict(data),
                    },
                }
            observation.update(data=data, source_refs=refs)
        except (ProviderError, BusinessError) as error:
            observation.update(
                status="failed",
                error={
                    "code": getattr(error, "reason", None) or getattr(error, "code", "TOOL_FAILED"),
                    "message": getattr(error, "message", str(error)),
                    "retryable": getattr(error, "retryable", False),
                },
            )
        return observation

    async def charging(self, args: dict, context: ToolContext) -> tuple[dict, list, bool]:
        region, city = args["region"], args.get("city")
        radius = args.get("radius_m", self.config.map_radius_m)
        if not 0 < radius <= self.config.map_radius_m:
            raise ProviderError("MAP_RADIUS_INVALID", "查询半径超出当前演示支持范围")
        link = search_link(region, city)
        ref = args.get("confirmed_location_ref")
        if ref:
            async with context.session_factory() as db:
                store = Store(db)
                candidate = await store.require(LocationCandidate, ref, context.session_id)
                facts = await store.list(
                    Fact, session_id=context.session_id, key="confirmed_location_ref"
                )
                superseded = {old for f in facts for old in f.supersedes}
                current = [f for f in facts if f.id not in superseded and f.scope == "session"]
                if not current or any(f.state != "confirmed" or f.value != ref for f in current):
                    raise ProviderError("LOCATION_NOT_CONFIRMED", "该查询地点尚未由销售确认")
                center, region, city = candidate.center_gcj02, candidate.name, candidate.city
                link = search_link(region, city)
        else:
            candidates = await self.amap.search_region(region, city)
            if not candidates:
                return (
                    {
                        "state": "no_results",
                        "region": region,
                        "city": city,
                        "stations": [],
                        "warnings": ["未找到区域，请补充城市或地点"],
                        "map_status": "missing",
                        "map_asset_id": None,
                        "external_search": link,
                    },
                    [],
                    True,
                )
            # 多候选不猜测；持久化 ID 后交销售确认。
            if len(candidates) > 1:
                saved = []
                async with context.write_lock, context.session_factory() as db:
                    store = Store(db)
                    await store.check_revision(context.session_id, context.source_revision)
                    for c in candidates:
                        row = await store.add(LocationCandidate(session_id=context.session_id, **c))
                        saved.append({"id": row.id, **c})
                    await db.commit()
                return (
                    {
                        "state": "ambiguous",
                        "region": region,
                        "city": city,
                        "candidates": saved,
                        "stations": [],
                        "map_status": "missing",
                        "map_asset_id": None,
                        "warnings": ["存在多个地点，请选择查询中心"],
                        "external_search": link,
                    },
                    [],
                    True,
                )
            center = candidates[0]["center_gcj02"]
            region, city = candidates[0]["name"], candidates[0]["city"]
            link = search_link(region, city)
        stations = await self.amap.stations(center, radius)
        warnings = []
        for station in stations:
            try:
                station.update(await self.amap.route(center, station["location_gcj02"]))
            except ProviderError:
                warnings.append(f"站点 {station['number']} 路线缺失，保留中心点距离")
        asset_id = None
        if stations:
            try:
                raw, mime = await self.amap.static_map(center, stations)
                asset_id = str(uuid4())
                suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[mime]
                relative = f"maps/{asset_id}{suffix}"
                path = self.config.upload_path / relative
                async with context.write_lock, context.session_factory() as db:
                    store = Store(db)
                    await store.check_revision(context.session_id, context.source_revision)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                    try:
                        await store.add(
                            Asset(
                                id=asset_id,
                                session_id=context.session_id,
                                report_refs=[],
                                relative_path=relative,
                                mime=mime,
                                sha256=hashlib.sha256(raw).hexdigest(),
                                source_url="https://restapi.amap.com/v3/staticmap",
                                captured_at=utcnow(),
                            )
                        )
                        await db.commit()
                    except BaseException:
                        path.unlink(missing_ok=True)
                        raise
            except ProviderError:
                asset_id = None
                warnings.append("地图图像缺失，站点列表仍可查看")
        refs = [
            source("amap", "高德 POI 与查询时路线估算，不代表实时空闲状态", "https://www.amap.com")
        ]
        data = {
            "state": "ready" if stations else "no_results",
            "region": region,
            "city": city,
            "center_gcj02": center,
            "radius_m": radius,
            "stations": stations,
            "map_asset_id": asset_id,
            "map_status": "ready" if asset_id else "missing",
            "asset_ids": [asset_id] if asset_id else [],
            "external_search": link,
            "warnings": warnings,
            "observed_at": utcnow(),
        }
        return data, refs, bool(warnings) or not stations
