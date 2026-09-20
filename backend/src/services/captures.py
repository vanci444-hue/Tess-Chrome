"""验证官网投影，只改变候选关系，不改变已采集事实。"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from src.config.settings import Settings
from src.db.models import Capture
from src.models.contracts import BusinessError, CaptureCreate, CaptureUpdate
from src.repositories.store import Store

CAPTURE_KEYS = frozenset("model variant paint wheels interior seats autopilot accessories extras "
    "option_surcharges trim_price vehicle_price "
    "price_basis delivery range_cltc top_speed zero_to_hundred finance_product down_payment principal "
    "term_months monthly_payment rate_value rate_basis fees discounts".split())
REQUIRED_KEYS = frozenset("model variant paint wheels interior seats autopilot accessories "
                          "vehicle_price price_basis".split())
MONEY_KEYS = frozenset("vehicle_price trim_price down_payment principal monthly_payment fees discounts".split())
SURCHARGE_GROUPS = frozenset("paint wheels interior seats autopilot accessories extras".split())


def _valid_surcharges(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        name, group, amount = item.get("name"), item.get("group"), item.get("amount")
        if not isinstance(name, str) or not name.strip():
            return False
        if group not in SURCHARGE_GROUPS:
            return False
        if type(amount) is not int or amount < 0:
            return False
        if "included" in item and type(item["included"]) is not bool:
            return False
    return True


def capture_read(row: Capture) -> dict[str, Any]:
    return {"id": row.id, "session_id": row.session_id, "immutable_payload": row.immutable_payload,
            "validity": row.validity, "issues": row.issues, "active": row.active,
            "preference": row.preference}


class CaptureService:
    def __init__(self, store: Store, config: Settings):
        self.store, self.config = store, config

    async def create(self, session_id: str, data: CaptureCreate) -> dict[str, Any]:
        session = await self.store.check_revision(session_id, data.expected_revision)
        try:
            url = urlsplit(data.capture.source_url)
            valid_port = url.port in (None, 443)
        except ValueError:
            raise BusinessError("采集来源 URL 不合法", "INVALID_CAPTURE_SOURCE", 400,
                                "VALIDATION_ERROR") from None
        if url.scheme != "https" or url.hostname != "www.tesla.cn" or url.path != "/modely/design" or not valid_port or url.username or url.password:
            raise BusinessError("仅支持 Tesla 中国 Model Y 配置页面", "INVALID_CAPTURE_SOURCE", 400,
                                "VALIDATION_ERROR")
        if data.capture.readiness != "ready":
            raise BusinessError("官网配置尚未稳定，请等待页面更新后重新抓取", "CAPTURE_UNSTABLE", 400,
                                "VALIDATION_ERROR")
        captures = await self.store.list(Capture, session_id=session_id, active=True)
        if len(captures) >= self.config.max_active_captures:
            raise BusinessError("已有三个候选，请先移除一个", "CANDIDATE_LIMIT")
        values: dict[str, Any] = {}
        evidence: dict[str, str] = {}
        raw_evidence: dict[str, str] = {}
        issues = [x.model_dump() for x in data.capture.issues]
        for field in data.capture.fields:
            if field.key not in CAPTURE_KEYS or field.key in values:
                raise BusinessError("采集字段非法或重复", "INVALID_CAPTURE_FIELD", 400, "VALIDATION_ERROR")
            if field.key in REQUIRED_KEYS - {"accessories", "vehicle_price"} and not isinstance(field.value, str):
                raise BusinessError("选配字段必须是页面可见文字", "INVALID_CAPTURE_FIELD", 400,
                                    "VALIDATION_ERROR")
            if field.key == "accessories" and not isinstance(field.value, (list, str)):
                raise BusinessError("配件必须是明确选中清单", "INVALID_CAPTURE_FIELD", 400,
                                    "VALIDATION_ERROR")
            if field.key == "extras" and not (isinstance(field.value, list) and
                    all(isinstance(item, str) and item.strip() for item in field.value)):
                raise BusinessError("加选清单必须是页面可见文字", "INVALID_CAPTURE_FIELD", 400,
                                    "VALIDATION_ERROR")
            if field.key == "option_surcharges" and not _valid_surcharges(field.value):
                raise BusinessError("选配价格必须是已选项及金额", "INVALID_CAPTURE_FIELD", 400,
                                    "VALIDATION_ERROR")
            if field.key in MONEY_KEYS and (type(field.value) is not int or field.value < 0 or
                                            field.unit != "CNY_fen"):
                raise BusinessError("金额必须为整数分并带单位", "INVALID_MONEY", 400, "VALIDATION_ERROR")
            values[field.key], evidence[field.key] = field.value, field.evidence.kind
            raw_evidence[field.key] = field.raw_text.strip()
        if values.get("model") not in (None, "Model Y"):
            raise BusinessError("车型不属于 Model Y", "INVALID_MODEL", 400, "VALIDATION_ERROR")
        for key in sorted(REQUIRED_KEYS):
            if (key not in values or values[key] is None or values[key] == "" or
                    evidence.get(key) == "initial_dictionary" or not raw_evidence.get(key)):
                issues.append({"code": "MISSING_FIELD", "field": key, "blocking": True,
                               "message": "未读取到当前选中的" + key})
        relation_keys = {"vehicle_price", "down_payment", "principal", "fees", "discounts"}
        conflict = False
        if relation_keys <= values.keys():
            conflict = (values["vehicle_price"] + values["fees"] - values["discounts"] !=
                        values["down_payment"] + values["principal"])
            if conflict:
                issues.append({"code": "FINANCE_AMOUNT_CONFLICT", "field": "principal",
                    "blocking": True, "message": "车价、费用、优惠与首付及本金不闭合，请重新核对官网"})
        elif {"down_payment", "principal"} <= values.keys():
            conflict = values.get("vehicle_price") != values["down_payment"] + values["principal"]
            issues.append({"code": "FINANCE_AMOUNT_CONFLICT" if conflict else "FINANCE_BASIS_MISSING",
                "field": "finance_product", "blocking": conflict,
                "message": "金额不闭合且缺少优惠/费用解释" if conflict else
                           "融资费用和优惠口径未读取；保留原值，不补零或宣称完整金融方案"})
        validity = "conflict" if conflict else ("incomplete" if any(i["blocking"] for i in issues)
                                                else "valid")
        row = await self.store.add(Capture(session_id=session_id,
            immutable_payload=data.capture.model_dump(mode="json"), validity=validity, issues=issues))
        await self.store.bump(session)
        return {"capture_id": row.id, "session_id": session_id, "revision": session.revision,
                "validity": validity, "issues": issues}

    async def update(self, session_id: str, capture_id: str,
                     data: CaptureUpdate) -> dict[str, Any]:
        session = await self.store.check_revision(session_id, data.expected_revision)
        row = await self.store.require(Capture, capture_id, session_id)
        if "active" in data.model_fields_set:
            row.active = False
        if "preference" in data.model_fields_set:
            row.preference = data.preference
        await self.store.bump(session)
        return {"capture_id": row.id, "active": row.active, "preference": row.preference,
                "revision": session.revision}
