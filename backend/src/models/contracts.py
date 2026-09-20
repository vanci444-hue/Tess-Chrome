"""前后端共享的业务契约。金额均为整数分，未知值不转换为零。"""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pycore.core.exceptions import PyCoreError
from src.config.settings import settings


class BusinessError(PyCoreError):
    """带 HTTP 分类的业务错误，最终交由 PyCore 信封输出。"""
    def __init__(self, message: str, reason: str, status: int = 409,
                 code: str = "CONFLICT", **details: Any):
        super().__init__(message, code=code, details={"reason": reason, **details})
        self.status = status


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Issue(Contract):
    code: str
    field: str | None = None
    blocking: bool
    message: str


class SourceRef(Contract):
    id: str
    kind: str
    url: str | None = None
    observed_at: str
    label: str


class FactRead(Contract):
    id: str
    key: str
    value: Any = None
    unit: str | None = None
    state: Literal["proposed", "confirmed", "unknown", "conflict"]
    source_kind: str
    source_id: str
    observed_at: str
    scope: Literal["identity", "session", "historical"] = "session"
    subject_id: str | None = None
    evidence_note: str | None = None
    supersedes: list[str] = Field(default_factory=list)


class QuestionRead(Contract):
    id: str
    text: str
    required: bool
    fact_ids: list[str] = Field(default_factory=list)
    origin_run_id: str | None = None
    state: str = "open"


class CustomerCreate(Contract):
    nickname: str = Field(min_length=1, max_length=settings.max_nickname_chars)
    phone: str | None = None
    email: str | None = Field(default=None, max_length=settings.max_email_chars)
    extraction_id: UUID | None = None
    allow_duplicate: bool = False
    identity_confirmed: bool


class CustomerUpdate(Contract):
    expected_revision: int = Field(ge=1)
    nickname: str | None = Field(default=None, min_length=1, max_length=settings.max_nickname_chars)
    phone: str | None = None
    email: str | None = Field(default=None, max_length=settings.max_email_chars)
    allow_duplicate: bool = False
    identity_confirmed: bool


class CustomerRead(Contract):
    id: str
    nickname: str
    phone: str | None
    email: str | None
    revision: int


class CustomerSummary(Contract):
    id: str
    nickname: str
    contact_mask: str
    latest_session_id: str | None = None


class SessionCustomerRead(CustomerSummary):
    revision: int
    phone: str | None
    email: str | None


class CustomerPage(Contract):
    items: list[CustomerSummary]
    next_cursor: str | None = None


class CRMExtractInput(Contract):
    text: str = Field(min_length=1, max_length=settings.max_text_chars)


class CRMProposed(Contract):
    nickname: str | None = None
    phone: str | None = None
    email: str | None = None


class CRMExtractRead(Contract):
    extraction_id: str
    proposed: CRMProposed
    historical_facts: list[FactRead]
    missing: list[str]


class SessionCreate(Contract):
    customer_id: UUID
    title: str = Field(min_length=1, max_length=settings.max_nickname_chars)
    visit_at: datetime | None = None


class SessionRead(Contract):
    id: str
    customer_id: str
    title: str
    revision: int
    status: str
    created_at: str


class SessionSummary(Contract):
    id: str
    title: str
    status: str
    created_at: str
    latest_report_id: str | None


class SessionPage(Contract):
    items: list[SessionSummary]
    next_cursor: str | None = None


class CapturedEvidence(Contract):
    kind: Literal["dom_selected", "dom_text", "initial_dictionary"]
    selector_hint: str | None = None


class CapturedField(Contract):
    key: str
    value: Any
    unit: str | None = None
    raw_text: str
    evidence: CapturedEvidence
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("来源时间必须带时区")
        return value


class CaptureInput(Contract):
    source_url: str
    captured_at: datetime
    adapter_version: str
    page_fingerprint: str
    readiness: Literal["ready", "unstable", "unsupported"]
    fields: list[CapturedField]
    issues: list[Issue] = Field(default_factory=list)

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("采集时间必须带时区")
        return value


class CaptureCreate(Contract):
    expected_revision: int = Field(ge=1)
    capture: CaptureInput


class CaptureRead(Contract):
    id: str
    session_id: str
    immutable_payload: CaptureInput
    validity: Literal["valid", "incomplete", "conflict"]
    issues: list[Issue]
    active: bool
    preference: str | None


class CaptureSaved(Contract):
    capture_id: str
    session_id: str
    revision: int
    validity: Literal["valid", "incomplete", "conflict"]
    issues: list[Issue]


class CaptureUpdate(Contract):
    expected_revision: int = Field(ge=1)
    active: Literal[False] | None = None
    preference: str | None = Field(default=None, max_length=settings.max_nickname_chars)

    @model_validator(mode="after")
    def require_change(self):
        if not ({"active", "preference"} & self.model_fields_set):
            raise ValueError("请选择移除或修改偏好")
        return self


class CaptureUpdated(Contract):
    capture_id: str
    active: bool
    preference: str | None
    revision: int


class AudioCreate(Contract):
    expected_revision: int = Field(ge=1)
    language: str | None = None


class AudioCreated(Contract):
    asr_session_id: str
    session_id: str
    ws_path: str
    state: Literal["created"]
    expires_in_seconds: int


class FactChange(Contract):
    fact_id: UUID | None = None
    key: str
    value: Any = None
    state: Literal["confirmed", "unknown"]
    supersedes: list[UUID] = Field(default_factory=list)
    evidence_note: str | None = Field(default=None, max_length=settings.max_text_chars)


class ContextUpdate(Contract):
    expected_revision: int = Field(ge=1)
    changes: list[FactChange]
    skip_optional_questions: bool = False
    reply_to_run_id: UUID | None = None
    reply_to_question_ids: list[UUID] = Field(default_factory=list)


class ContextUpdated(Contract):
    revision: int
    blocking_issues: list[Issue]
    invalidated_artifact_ids: list[str]
    optional_questions_stopped: bool
    continuation_hint: dict[str, Any] | None = None


class ReportSummaryText(Contract):
    comparing: str = Field(max_length=settings.max_text_chars)
    confirmed: list[str]
    pending: list[str]


class ReportModule(Contract):
    type: Literal["trial", "options", "finance", "charging", "energy", "family", "advisor", "missing"]
    status: Literal["ready", "estimate", "mock", "missing"]
    source_refs: list[SourceRef] = Field(default_factory=list)
    data: dict[str, Any]


class ReportSnapshot(Contract):
    id: str
    schema_version: int = 1
    customer_salutation: str
    generated_at: str
    published_at: str | None = None
    summary: ReportSummaryText
    modules: list[ReportModule]
    sources: list[SourceRef]
    asset_ids: list[str]
    disclaimer: str


class DraftRead(Contract):
    id: str
    session_id: str
    draft_revision: int
    source_revision: int
    customer_revision: int
    report_data: ReportSnapshot
    blocking_issues: list[Issue]
    requires_review: bool
    stale: bool


class DraftUpdate(Contract):
    expected_revision: int = Field(ge=1)
    draft_revision: int = Field(ge=1)
    summary: ReportSummaryText | None = None
    change_request: str | None = Field(default=None, min_length=1, max_length=settings.max_text_chars)

    @model_validator(mode="after")
    def exclusive_input(self):
        if (self.summary is None) == (self.change_request is None):
            raise ValueError("摘要编辑与自然语言修改意见必须选择一个")
        return self


class DraftUpdated(Contract):
    draft_id: str
    draft_revision: int
    requires_review: bool
    blocking_issues: list[Issue]


class PublishInput(Contract):
    draft_id: UUID
    draft_revision: int = Field(ge=1)
    expected_revision: int = Field(ge=1)
    review_confirmed: bool


class PublishRead(Contract):
    report_id: str
    session_id: str
    timeline_message_id: str
    url: str
    published_at: str
    snapshot_hash: str


class ReportSummary(Contract):
    report_id: str
    session_id: str
    session_title: str
    title: str
    published_at: str
    url: str


class ReportPage(Contract):
    items: list[ReportSummary]
    next_cursor: str | None = None


class TimelineRead(Contract):
    id: str
    session_id: str
    seq: int
    role: str
    type: str
    source_ref: dict[str, str] | None
    content: dict[str, Any]
    created_at: str


class TrialVehicle(Contract):
    model: str
    variant: str | None = None
    source_fact_ids: list[str]


class SessionDetail(Contract):
    id: str
    customer: SessionCustomerRead
    revision: int
    status: str
    trial_vehicle: TrialVehicle | None
    captures: list[CaptureRead]
    inputs: list[dict[str, Any]]
    facts: list[FactRead]
    questions: list[QuestionRead]
    artifacts: list[dict[str, Any]]
    active_run: dict[str, Any] | None
    pending_run: dict[str, Any] | None
    draft: DraftRead | None
    reports: list[ReportSummary]
    timeline: list[TimelineRead]
    followup: dict[str, Any] | None


class EventInject(Contract):
    fixture_id: str
    expected_revision: int = Field(ge=1)


class EventInjected(Contract):
    event_ids: list[str]
    source: Literal["mock"] = "mock"
    revision: int


class DemoAdvisor(Contract):
    id: str
    name: str
    store_name: str
    is_demo: Literal[True] = True


class HealthRead(Contract):
    demo_advisor: DemoAdvisor
    status: Literal["ready", "degraded"]
    database: bool
    capabilities: dict[str, Literal["configured", "missing"]]
