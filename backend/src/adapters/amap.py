"""真实高德 Web Service 传输层。错误不含 URL、Key 或原始供应商正文。"""

import math
import re
from typing import Any
from urllib.parse import urlencode

import httpx
from src.adapters.base import ProviderError
from src.config.settings import Settings


def location(value: str) -> dict:
    try:
        lon, lat = map(float, value.split(","))
        if not math.isfinite(lon + lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError()
        return {"longitude": lon, "latitude": lat}
    except (ValueError, AttributeError):
        raise ProviderError("MAP_COORDINATE_INVALID", "地图坐标缺失或无效") from None


def coordinate(value: dict) -> str:
    return f"{value['longitude']},{value['latitude']}"


def search_link(region: str, city: str | None) -> dict:
    # 仅传地点查询词，拒绝常见电话、邮箱和长 CRM 文本。
    if re.search(r"@|\d{7,}|[\r\n]", region + (city or "")):
        raise ProviderError("LOCATION_TEXT_INVALID", "请仅提供区域或地铁站，不提供联系方式")
    query = {
        "keyword": region + " 特斯拉充电站",
        "view": "map",
        "src": "tess-chrome",
        "callnative": "0",
    }
    if city:
        query["city"] = city
    return {"label": "在高德继续搜索", "url": "https://uri.amap.com/search?" + urlencode(query)}


class AmapProvider:
    def __init__(self, config: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.config, self.transport = config, transport

    async def request(self, path: str, params: dict, image: bool = False):
        cfg = self.config
        if not cfg.amap_web_service_key:
            raise ProviderError("AMAP_NOT_CONFIGURED", "高德服务未配置，地图和站点信息缺失")
        try:
            async with httpx.AsyncClient(
                trust_env=False,
                transport=self.transport,
                timeout=httpx.Timeout(cfg.map_timeout, connect=cfg.http_connect_timeout),
            ) as client:
                async with client.stream(
                    "GET",
                    cfg.amap_base_url.rstrip("/") + path,
                    params={**params, "key": cfg.amap_web_service_key},
                ) as response:
                    if response.status_code != 200:
                        raise ProviderError("MAP_UPSTREAM_ERROR", "地图服务请求失败")
                    # 图片和 JSON 都有边界；不将异常页面无界读入内存。
                    content = bytearray()
                    limit = cfg.map_image_max_bytes if image else cfg.max_request_bytes
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > limit:
                            raise ProviderError("MAP_RESPONSE_TOO_LARGE", "地图响应超过限制")
                    mime = response.headers.get("content-type", "").split(";")[0]
            if image:
                raw = bytes(content)
                signatures = {
                    "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
                    "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
                    "image/webp": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
                }
                if not signatures.get(mime):
                    raise ProviderError("MAP_IMAGE_INVALID", "静态地图未返回有效图片，保留站点列表")
                return raw, mime
            import json

            payload = json.loads(content)
            if str(payload.get("status")) != "1":
                raise ProviderError("MAP_UPSTREAM_ERROR", "高德接口返回业务错误，请检查配额与配置")
            return payload
        except httpx.TimeoutException:
            raise ProviderError("MAP_TIMEOUT", "地图查询超时") from None
        except httpx.HTTPError:
            raise ProviderError("MAP_CONNECTION_ERROR", "地图连接失败") from None
        except (ValueError, TypeError, AttributeError):
            raise ProviderError("MAP_INVALID_RESPONSE", "地图响应格式不符合约定") from None

    async def search_region(self, region: str, city: str | None) -> list[dict]:
        params = {"keywords": region, "page_size": self.config.map_page_size}
        if city:
            params["region"] = city
        payload = await self.request("/v5/place/text", params)
        results = []
        for poi in payload.get("pois", []):
            try:
                results.append(
                    {
                        "provider_poi_id": str(poi["id"]),
                        "name": str(poi["name"]),
                        "city": poi.get("cityname") or city or "",
                        "address": poi.get("address") or "",
                        "center_gcj02": location(poi["location"]),
                    }
                )
            except (KeyError, ProviderError):
                continue
        return results

    async def stations(self, center: dict, radius: int) -> list[dict]:
        candidates: dict[str, Any] = {}
        # 裸搜 Tesla/特斯拉会命中门店与维修，再滤「充电」后为空；周边词需直接指向充电站。
        for keyword in ("特斯拉充电", "Tesla Supercharger", "超级充电站"):
            payload = await self.request(
                "/v5/place/around",
                {
                    "location": coordinate(center),
                    "radius": radius,
                    "keywords": keyword,
                    "page_size": self.config.map_page_size,
                },
            )
            for poi in payload.get("pois", []):
                evidence = str(poi.get("name", "")) + " " + str(poi.get("type", ""))
                if not re.search(r"充电|supercharg|destination charg", evidence, re.I):
                    continue
                try:
                    distance = float(poi["distance"])
                    if not math.isfinite(distance) or not 0 <= distance <= radius:
                        continue
                    candidates[str(poi["id"])] = {
                        "id": str(poi["id"]),
                        "name": str(poi["name"]),
                        "location_gcj02": location(poi["location"]),
                        "center_distance_m": distance,
                        "distance_basis": "高德中心点距离",
                        "route_status": "missing",
                        "driving_distance_m": None,
                        "driving_duration_seconds": None,
                    }
                except (KeyError, ValueError, ProviderError):
                    continue
        stations = sorted(candidates.values(), key=lambda x: x["center_distance_m"])
        return [
            dict(p, number=i + 1) for i, p in enumerate(stations[: self.config.map_station_limit])
        ]

    async def route(self, origin: dict, destination: dict) -> dict:
        payload = await self.request(
            "/v3/direction/driving",
            {
                "origin": coordinate(origin),
                "destination": coordinate(destination),
                "extensions": "base",
                "output": "JSON",
            },
        )
        try:
            path = payload["route"]["paths"][0]
            distance, duration = float(path["distance"]), float(path["duration"])
            if min(distance, duration) < 0 or not math.isfinite(distance + duration):
                raise ValueError()
            return {
                "driving_distance_m": distance,
                "driving_duration_seconds": duration,
                "route_status": "ready",
            }
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("MAP_ROUTE_MISSING", "路线不可用，保留中心点距离") from None

    async def static_map(self, center: dict, stations: list[dict]) -> tuple[bytes, str]:
        markers = ["mid,0x333333,中:" + coordinate(center)]
        markers.extend(
            f"mid,0xE82127,{p['number']}:" + coordinate(p["location_gcj02"]) for p in stations
        )
        return await self.request(
            "/v3/staticmap",
            {
                "size": f"{self.config.map_image_width}*{self.config.map_image_height}",
                "markers": "|".join(markers),
            },
            image=True,
        )
