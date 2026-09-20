"""客户身份与 CRM 预览；联系方式查重是提示，不是身份合并。"""
from __future__ import annotations

import base64
import builtins
import re
from typing import Any

from sqlalchemy import or_, select
from src.config.settings import Settings
from src.db.models import CRMExtraction, Customer, Draft, Session, utcnow
from src.models.contracts import BusinessError, CustomerCreate, CustomerUpdate
from src.repositories.store import Store


def contact_mask(customer: Customer) -> str:
    if customer.normalized_phone:
        return customer.normalized_phone[:3] + "****" + customer.normalized_phone[-4:]
    email = customer.normalized_email or ""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def customer_read(customer: Customer) -> dict[str, Any]:
    return {"id": customer.id, "nickname": customer.nickname, "phone": customer.normalized_phone,
            "email": customer.normalized_email, "revision": customer.revision}


def clean_identity(nickname: str, phone: str | None, email: str | None,
                   config: Settings) -> tuple[str, str | None, str | None]:
    nickname = nickname.strip()
    if not nickname or len(nickname) > config.max_nickname_chars:
        raise BusinessError("请填写客户称呼", "INVALID_NICKNAME", 400, "VALIDATION_ERROR")
    if any(ord(c) < 32 for c in nickname):
        raise BusinessError("称呼包含无效字符", "INVALID_NICKNAME", 400, "VALIDATION_ERROR")
    phone = re.sub(r"[\s-]", "", phone) if phone else None
    if phone:
        if re.fullmatch(r"1[3-9]\d{9}", phone) and config.default_phone_region == "CN":
            phone = "+86" + phone
        if not re.fullmatch(r"\+[1-9]\d{6,14}", phone):
            raise BusinessError("请输入有效手机号及明确国家区号", "INVALID_PHONE", 400,
                                "VALIDATION_ERROR")
    email = email.strip().lower() if email else None
    if email and (len(email) > config.max_email_chars or not re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        raise BusinessError("邮箱格式不正确", "INVALID_EMAIL", 400, "VALIDATION_ERROR")
    if not phone and not email:
        raise BusinessError("请至少填写手机号或邮箱", "MISSING_CONTACT", 400, "VALIDATION_ERROR")
    return nickname, phone, email


def page_slice(rows: list[Any], cursor: str | None, limit: int) -> tuple[list[Any], str | None]:
    offset = 0
    if cursor:
        try:
            offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
            if offset < 0:
                raise ValueError()
        except (ValueError, UnicodeError):
            raise BusinessError("分页位置无效", "INVALID_CURSOR", 400, "VALIDATION_ERROR") from None
    page = rows[offset:offset + limit]
    next_cursor = (base64.urlsafe_b64encode(str(offset + limit).encode()).decode()
                   if offset + limit < len(rows) else None)
    return page, next_cursor


class CustomerService:
    def __init__(self, store: Store, config: Settings):
        self.store, self.config = store, config

    async def check_duplicate(self, phone: str | None, email: str | None,
                              allow: bool, exclude: str | None = None) -> None:
        clauses = []
        if phone:
            clauses.append(Customer.normalized_phone == phone)
        if email:
            clauses.append(Customer.normalized_email == email)
        matches = list((await self.store.db.scalars(select(Customer).where(or_(*clauses)))).all())
        matches = [row for row in matches if row.id != exclude]
        if matches and not allow:
            raise BusinessError("已有相同联系方式的客户，请确认是否为同一人", "DUPLICATE_CONTACT",
                candidates=[{"id": x.id, "nickname": x.nickname, "contact_mask": contact_mask(x)}
                            for x in matches])

    async def create(self, data: CustomerCreate) -> dict[str, Any]:
        if not data.identity_confirmed:
            raise BusinessError("请先确认客户身份信息", "IDENTITY_NOT_CONFIRMED", 400,
                                "VALIDATION_ERROR")
        nickname, phone, email = clean_identity(data.nickname, data.phone, data.email, self.config)
        await self.check_duplicate(phone, email, data.allow_duplicate)
        extraction = None
        if data.extraction_id:
            extraction = await self.store.require(CRMExtraction, str(data.extraction_id))
            if extraction.customer_id:
                raise BusinessError("此预览已确认，请重新预览或手动建档", "EXTRACTION_USED")
        customer = await self.store.add(Customer(nickname=nickname, normalized_phone=phone,
                                                normalized_email=email))
        if extraction:
            extraction.customer_id = customer.id
        return customer_read(customer)

    async def update(self, customer_id: str, data: CustomerUpdate) -> dict[str, Any]:
        customer = await self.store.require(Customer, customer_id)
        if data.expected_revision != customer.revision:
            raise BusinessError("客户信息已变更，请刷新后再确认", "STALE_REVISION")
        if not data.identity_confirmed:
            raise BusinessError("请确认修改后的身份信息", "IDENTITY_NOT_CONFIRMED", 400,
                                "VALIDATION_ERROR")
        supplied = data.model_fields_set & {"nickname", "phone", "email"}
        if not supplied:
            raise BusinessError("没有修改字段", "EMPTY_CHANGES", 400, "VALIDATION_ERROR")
        nickname, phone, email = clean_identity(
            (data.nickname or "") if "nickname" in supplied else customer.nickname,
            data.phone if "phone" in supplied else customer.normalized_phone,
            data.email if "email" in supplied else customer.normalized_email, self.config)
        await self.check_duplicate(phone, email, data.allow_duplicate, customer.id)
        customer.nickname, customer.normalized_phone, customer.normalized_email = nickname, phone, email
        customer.revision += 1
        customer.updated_at = utcnow()
        for session in await self.store.list(Session, customer_id=customer.id):
            for draft in await self.store.list(Draft, session_id=session.id):
                draft.requires_review = True
                draft.stale = True
        return customer_read(customer)

    async def list(self, q: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
        query = select(Customer).order_by(Customer.created_at.desc(), Customer.id.desc())
        if q:
            # contains(autoescape=True) 防止百分号被当作查询通配符。
            query = query.where(or_(Customer.nickname.contains(q, autoescape=True),
                Customer.normalized_phone.contains(re.sub(r"[\s-]", "", q), autoescape=True),
                Customer.normalized_email.contains(q.lower(), autoescape=True)))
        rows = list((await self.store.db.scalars(query)).all())
        page, next_cursor = page_slice(rows, cursor, limit)
        items = []
        for row in page:
            sessions = await self.store.list(Session, customer_id=row.id)
            items.append({"id": row.id, "nickname": row.nickname, "contact_mask": contact_mask(row),
                          "latest_session_id": sessions[-1].id if sessions else None})
        return {"items": items, "next_cursor": next_cursor}

    async def save_extraction(self, proposed: dict[str, Any],
                              historical_facts: builtins.list[dict[str, Any]]) -> dict[str, Any]:
        """由 T005 模型适配器调用；只存预览，不提前创建身份。"""
        row = await self.store.add(CRMExtraction(proposed=proposed, historical_facts=historical_facts))
        missing = []
        if not proposed.get("nickname"):
            missing.append("nickname")
        if not (proposed.get("phone") or proposed.get("email")):
            missing.append("contact")
        return {"extraction_id": row.id, "proposed": proposed,
                "historical_facts": historical_facts, "missing": missing}
