"""报告数字来自持久化事实和工具产物，发布复制完整快照并原子写卡片。"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.config.settings import Settings
from src.db.models import (
    Artifact,
    Asset,
    Capture,
    Customer,
    Draft,
    Fact,
    Question,
    Report,
    Session,
    new_id,
    utcnow,
)
from src.models.contracts import (
    BusinessError,
    DraftUpdate,
    PublishInput,
    ReportSnapshot,
    ReportSummaryText,
)
from src.repositories.store import Store, digest
from src.services.facts import blocking_facts, current_facts, trial_vehicle
from src.services.sessions import draft_read

ADVISOR_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "advisor.json"
PRIVATE_KEYS = frozenset("phone email normalized_phone normalized_email contact_mask corrected_text "
    "crm_text private_chat raw_conversation audio token authorization api_key "
    "bailian_api_key amap_web_service_key".split())


def advisor() -> dict[str, Any]:
    return json.loads(ADVISOR_PATH.read_text())


def safe_text(value: str, *, phone: str | None = None, email: str | None = None) -> str:
    """按已知身份精确去标识，号码格式变化不改变其身份。

    不把所有长数字都当电话；只匹配已知号码的完整数字序列，允许
    空格/连接符等展示分隔符，保留正常车价和月供数字。
    """
    if phone:
        digits = phone.lstrip("+")
        separator = r"[\s()（）.\-–—]*"
        number = separator.join(re.escape(digit) for digit in digits)
        pattern = rf"(?<![\d+])(?:\+{separator}|00{separator})?{number}(?!\d)"
        value = re.sub(pattern, "[联系方式已隐藏]", value)
    if email:
        value = re.sub(re.escape(email), "[联系方式已隐藏]", value, flags=re.IGNORECASE)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[联系方式已隐藏]", value)
    return re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[联系方式已隐藏]", value)


def safe_projection(value: Any, *, phone: str | None = None, email: str | None = None) -> Any:
    """草稿、审核、发布共用安全投影；保留 CapturedField.key。"""
    if isinstance(value, dict):
        return {key: safe_projection(item, phone=phone, email=email) for key, item in value.items()
                if key.lower() not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [safe_projection(item, phone=phone, email=email) for item in value]
    if isinstance(value, str):
        # 先识别未编码的身份信息，再处理 URL 凭据参数。
        value = safe_text(value, phone=phone, email=email)
        if value.startswith(("http://", "https://")):
            parsed = urlsplit(value)
            if parsed.username or parsed.password:
                return "[来源链接已隐藏]"
            query = [(key, safe_text(val, phone=phone, email=email))
                     for key, val in parse_qsl(parsed.query)
                     if key.lower() not in PRIVATE_KEYS and key.lower() != "key" and "token" not in key.lower()]
            value = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
        return value
    return value


def numeric_summary_facts(summary: dict[str, Any]) -> dict[tuple[str, int], str]:
    """保守冻结含数字的完整事实句及其字段/条目位置。

    只比较数字集合或顺序都会丢失“月供”和“预算”等语义归属。
    本地无可靠语义等价判定时，任何数字事实句修改均走重新生成。
    """
    pattern = r"\d|[零〇一二三四五六七八九十百千万亿两]"
    protected = {}
    for field, value in summary.items():
        statements = [value] if isinstance(value, str) else value
        for index, statement in enumerate(statements):
            if re.search(pattern, statement):
                protected[(field, index)] = statement
    return protected


class ReportService:
    def __init__(self, store: Store, config: Settings):
        self.store, self.config = store, config

    async def build_data(self, session_id: str, summary: dict[str, Any] | None = None,
                         artifact_ids: list[str] | None = None) -> tuple[dict[str, Any], list[str]]:
        session = await self.store.require(Session, session_id)
        customer = await self.store.require(Customer, session.customer_id)
        facts = await self.store.list(Fact, session_id=session_id)
        captures = await self.store.list(Capture, session_id=session_id, active=True)
        sources = [{"id": capture.id, "kind": "official_capture",
                    "url": capture.immutable_payload["source_url"],
                    "observed_at": capture.immutable_payload["captured_at"], "label": "Tesla 官网配置采集"}
                   for capture in captures]
        options = [{"capture_id": capture.id, "validity": capture.validity,
                    "fields": capture.immutable_payload["fields"], "issues": capture.issues,
                    "preference": capture.preference,
                    "captured_at": capture.immutable_payload["captured_at"]}
                   for capture in captures]
        modules: list[dict[str, Any]] = [
            {"type": "trial", "status": "ready" if trial_vehicle(facts) else "missing",
             "source_refs": [], "data": {"vehicle": trial_vehicle(facts), "feedback": [
                 {"value": row.value, "source_fact_id": row.id, "source_kind": row.source_kind}
                 for row in current_facts(facts) if row.key == "feedback" and row.state == "confirmed"]}},
            {"type": "options", "status": "ready" if captures else "missing",
             "source_refs": sources, "data": {"options": options}},
        ]
        used_artifacts = []
        available_modules: set[str] = set()
        assets: list[str] = []
        # 同候选试算取最新结果；不同候选/金融产品各自保留。显式 artifact_ids
        # 先限定本次选择，避免后来的无关试算覆盖销售选择的结果。
        selected: dict[tuple[str, str, str], tuple[Artifact, dict[str, Any]]] = {}
        for artifact in await self.store.list(Artifact, session_id=session_id):
            if artifact_ids is not None and artifact.id not in artifact_ids:
                continue
            if artifact.status == "stale" or artifact.source_revision != session.revision:
                continue
            module = artifact.output.get("report_module")
            if not module or module.get("type") not in {"finance", "charging", "energy", "family"}:
                continue
            kind, data = module["type"], module.get("data", {})
            key = (kind, str(data.get("capture_id", "")), str(data.get("product_id", "")))
            if kind == "family":
                key = (kind, str(data.get("topic", "")), "")
            previous = selected.get(key)
            if previous is None or (artifact.created_at, artifact.id) > (previous[0].created_at, previous[0].id):
                selected[key] = (artifact, module)
        for artifact, module in selected.values():
            available_modules.add(module["type"])
            used_artifacts.append(artifact.id)
            modules.append(copy.deepcopy(module))
            sources.extend(artifact.source_refs)
            for asset_id in artifact.output.get("asset_ids", []):
                await self.store.require(Asset, asset_id, session_id)
                assets.append(asset_id)
        sources = list({source["id"]: source for source in sources}.values())
        for kind in ("finance", "charging", "energy", "family"):
            if kind not in available_modules:
                modules.append({"type": kind, "status": "missing", "source_refs": [],
                                "data": {"reason": "尚无本次可核验结果"}})
        modules.append({"type": "advisor", "status": "mock", "source_refs": [], "data": advisor()})
        if summary is None:
            summary = {"comparing": "Model Y 当前候选方案", "confirmed": [], "pending": [
                "请继续确认本次试驾与购车关注事项"]}
        summary = ReportSummaryText.model_validate(summary).model_dump()
        report = {"id": new_id(), "schema_version": 1,
            "customer_salutation": customer.nickname + "，您好", "generated_at": utcnow(),
            "published_at": None, "summary": summary, "modules": modules, "sources": sources,
            "asset_ids": list(dict.fromkeys(assets)),
            "disclaimer": "动态内容反映采集时的信息；Mock 与 Estimate 不代表 Tesla 当前官方承诺。"}
        return ReportSnapshot.model_validate(safe_projection(report, phone=customer.normalized_phone,
            email=customer.normalized_email)).model_dump(), used_artifacts

    async def save_draft(self, session_id: str, expected_revision: int,
                         summary: dict[str, Any] | None = None,
                         artifact_ids: list[str] | None = None) -> dict[str, Any]:
        """T005 prepare_report 调用：此处不调用模型、不产生发布链接。"""
        session = await self.store.check_revision(session_id, expected_revision)
        customer = await self.store.require(Customer, session.customer_id)
        report_data, used = await self.build_data(session_id, summary, artifact_ids)
        issues = await self.blocking_issues(session_id)
        draft = await self.store.add(Draft(session_id=session_id, source_revision=session.revision,
            customer_revision=customer.revision, report_data=report_data, blocking_issues=issues,
            artifact_ids=used))
        return draft_read(draft)

    async def blocking_issues(self, session_id: str) -> list[dict[str, Any]]:
        captures = await self.store.list(Capture, session_id=session_id, active=True)
        issues = blocking_facts(await self.store.list(Fact, session_id=session_id))
        if not any(c.validity == "valid" for c in captures):
            issues.append({"code": "NO_VALID_CAPTURE", "field": "captures", "blocking": True,
                           "message": "至少需要一个有效候选方案"})
        if any(c.validity == "conflict" for c in captures):
            issues.append({"code": "CAPTURE_CONFLICT", "field": "captures", "blocking": True,
                           "message": "候选方案存在金额冲突，请重新抓取或移除"})
        for question in await self.store.list(Question, session_id=session_id):
            if question.required and question.state == "open":
                issues.append({"code": "UNRESOLVED_QUESTION", "field": question.id,
                               "blocking": True, "message": question.text})
        return issues

    async def update(self, session_id: str, draft_id: str,
                     data: DraftUpdate) -> dict[str, Any]:
        session = await self.store.check_revision(session_id, data.expected_revision)
        draft = await self.store.require(Draft, draft_id, session_id)
        if draft.draft_revision != data.draft_revision or draft.source_revision != session.revision:
            raise BusinessError("草稿已过期，请重新生成", "STALE_DRAFT")
        if data.change_request:
            raise BusinessError("修改意见需要已配置的 Agent 处理", "AGENT_NOT_REGISTERED", 503,
                                "DEPENDENCY_UNAVAILABLE")
        # 先去标识再校验，客户联系方式不作为可发布的数字事实。
        assert data.summary is not None
        customer = await self.store.require(Customer, session.customer_id)
        old_summary = safe_projection(draft.report_data["summary"],
            phone=customer.normalized_phone, email=customer.normalized_email)
        new_summary = safe_projection(data.summary.model_dump(),
            phone=customer.normalized_phone, email=customer.normalized_email)
        if numeric_summary_facts(old_summary) != numeric_summary_facts(new_summary):
            raise BusinessError("含数字的事实句不可直接修改或移动；请修改输入并重新生成报告",
                                "READONLY_RESULT", 400, "READONLY_RESULT")
        # 身份改变后在明确审核编辑时重建称呼；历史报告从不改写。
        draft.report_data = safe_projection({**draft.report_data, "summary": new_summary,
            "customer_salutation": customer.nickname + "，您好"},
            phone=customer.normalized_phone, email=customer.normalized_email)
        draft.customer_revision = customer.revision
        draft.draft_revision += 1
        draft.requires_review = True
        draft.stale = False
        draft.blocking_issues = await self.blocking_issues(session_id)
        return {"draft_id": draft.id, "draft_revision": draft.draft_revision,
                "requires_review": True, "blocking_issues": draft.blocking_issues}

    async def publish(self, session_id: str, data: PublishInput) -> dict[str, Any]:
        session = await self.store.check_revision(session_id, data.expected_revision)
        draft = await self.store.require(Draft, str(data.draft_id), session_id)
        customer = await self.store.require(Customer, session.customer_id)
        if not data.review_confirmed:
            raise BusinessError("请先确认已审核报告", "PUBLISH_BLOCKED")
        if (draft.draft_revision != data.draft_revision or draft.source_revision != session.revision
                or draft.customer_revision != customer.revision or draft.stale):
            raise BusinessError("草稿依据已变更，请重新生成并审核", "STALE_DRAFT")
        existing = await self.store.list(Report, draft_id=draft.id, draft_revision=draft.draft_revision)
        if existing:
            report = existing[0]
            message = await self.store.timeline(session_id, "report_card", "assistant",
                {"report_id": report.id, "title": "Model Y 试驾报告", "published_at": report.published_at},
                {"kind": "report", "id": report.id}, report.id)
            return {"report_id": report.id, "session_id": session_id, "timeline_message_id": message.id,
                "url": self.config.report_origin.rstrip("/") + "/reports/" + report.id,
                "published_at": report.published_at, "snapshot_hash": report.snapshot_hash}
        issues = await self.blocking_issues(session_id)
        for artifact_id in draft.artifact_ids:
            artifact = await self.store.require(Artifact, artifact_id, session_id)
            if artifact.status == "stale" or artifact.source_revision != session.revision:
                issues.append({"code": "STALE_ARTIFACT", "field": artifact_id,
                               "blocking": True, "message": "报告包含待更新计算结果"})
        if issues:
            raise BusinessError("请先处理影响报告结论的问题", "PUBLISH_BLOCKED", issues=issues)
        snapshot = copy.deepcopy(draft.report_data)
        snapshot["id"], snapshot["published_at"] = new_id(), utcnow()
        snapshot = ReportSnapshot.model_validate(safe_projection(snapshot, phone=customer.normalized_phone,
            email=customer.normalized_email)).model_dump()
        snapshot_hash = digest(snapshot)
        report = await self.store.add(Report(id=snapshot["id"], session_id=session_id,
            snapshot=snapshot, snapshot_hash=snapshot_hash, draft_id=draft.id,
            draft_revision=draft.draft_revision, generated_at=snapshot["generated_at"],
            published_at=snapshot["published_at"]))
        for asset_id in snapshot["asset_ids"]:
            asset = await self.store.require(Asset, asset_id, session_id)
            asset.report_refs = [*asset.report_refs, report.id]
        message = await self.store.timeline(session_id, "report_card", "assistant",
            {"report_id": report.id, "title": "Model Y 试驾报告", "published_at": report.published_at},
            {"kind": "report", "id": report.id}, report.id)
        session.status = "published"
        draft.requires_review = False
        return {"report_id": report.id, "session_id": session_id,
                "timeline_message_id": message.id,
                "url": self.config.report_origin.rstrip("/") + "/reports/" + report.id,
                "published_at": report.published_at, "snapshot_hash": snapshot_hash}

    async def get(self, report_id: str) -> dict[str, Any]:
        row = await self.store.get(Report, report_id)
        if row is None:
            raise BusinessError("报告不存在", "REPORT_NOT_FOUND", 404, "REPORT_NOT_FOUND")
        return row.snapshot
