"""从 PyCore integrations/db/models.py 模板扩展的本地持久化模型。"""
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Entity:
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)


class Customer(Entity, Base):
    __tablename__ = "customers"
    nickname: Mapped[str]
    normalized_phone: Mapped[str | None] = mapped_column(index=True)
    normalized_email: Mapped[str | None] = mapped_column(index=True)
    revision: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[str] = mapped_column(default=utcnow)


class CRMExtraction(Entity, Base):
    __tablename__ = "crm_extractions"
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"))
    proposed: Mapped[dict[str, Any]] = mapped_column(JSON)
    historical_facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class Session(Entity, Base):
    __tablename__ = "sessions"
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    title: Mapped[str]
    visit_at: Mapped[str | None]
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default="collecting")
    optional_questions_stopped: Mapped[bool] = mapped_column(default=False)
    pending_run_id: Mapped[str | None]
    followup: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Capture(Entity, Base):
    __tablename__ = "captures"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    immutable_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    validity: Mapped[str]
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    preference: Mapped[str | None]


class ASRSession(Entity, Base):
    __tablename__ = "asr_sessions"
    language: Mapped[str | None] = mapped_column(nullable=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    state: Mapped[str] = mapped_column(default="created")
    finished_at: Mapped[str | None]
    error_code: Mapped[str | None]
    duration_seconds: Mapped[float | None]


class SalesInput(Entity, Base):
    __tablename__ = "inputs"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    corrected_text: Mapped[str]
    asr_session_id: Mapped[str | None] = mapped_column(ForeignKey("asr_sessions.id"))
    source: Mapped[str]


class Fact(Entity, Base):
    __tablename__ = "facts"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    key: Mapped[str]
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    unit: Mapped[str | None]
    state: Mapped[str]
    source_kind: Mapped[str]
    source_id: Mapped[str]
    observed_at: Mapped[str] = mapped_column(default=utcnow)
    scope: Mapped[str] = mapped_column(default="session")
    subject_id: Mapped[str | None]
    evidence_note: Mapped[str | None]
    supersedes: Mapped[list[str]] = mapped_column(JSON, default=list)


class Question(Entity, Base):
    __tablename__ = "questions"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    text: Mapped[str]
    required: Mapped[bool]
    fact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    origin_run_id: Mapped[str | None]
    state: Mapped[str] = mapped_column(default="open")


class Artifact(Entity, Base):
    __tablename__ = "artifacts"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    tool_name: Mapped[str]
    input_hash: Mapped[str]
    source_revision: Mapped[int]
    output: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str]
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    observed_at: Mapped[str] = mapped_column(default=utcnow)


class Run(Entity, Base):
    __tablename__ = "runs"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    kind: Mapped[str]
    effective_intent: Mapped[str | None]
    source_message_id: Mapped[str | None]
    parent_run_id: Mapped[str | None]
    root_run_id: Mapped[str]
    continued_by_run_id: Mapped[str | None]
    input_revision: Mapped[int]
    current_revision: Mapped[int]
    status: Mapped[str] = mapped_column(default="queued")
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[str | None]
    finished_at: Mapped[str | None]
    idempotency_key: Mapped[str | None]
    body_hash: Mapped[str | None]
    __table_args__ = (Index("one_active_run", "session_id", unique=True,
                           sqlite_where=text("status IN ('queued','running')")),)


class RunEvent(Entity, Base):
    __tablename__ = "run_events"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int]
    type: Mapped[str]
    label: Mapped[str]
    tool_name: Mapped[str | None]
    artifact_id: Mapped[str | None]
    __table_args__ = (UniqueConstraint("run_id", "seq"),)


class Draft(Entity, Base):
    __tablename__ = "drafts"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    draft_revision: Mapped[int] = mapped_column(default=1)
    source_revision: Mapped[int]
    customer_revision: Mapped[int]
    report_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    blocking_issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    requires_review: Mapped[bool] = mapped_column(default=True)
    stale: Mapped[bool] = mapped_column(default=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class Report(Entity, Base):
    __tablename__ = "reports"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot_hash: Mapped[str]
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("drafts.id"))
    draft_revision: Mapped[int | None]
    __table_args__ = (UniqueConstraint("draft_id", "draft_revision"),)
    generated_at: Mapped[str]
    published_at: Mapped[str] = mapped_column(default=utcnow)


class TimelineMessage(Entity, Base):
    __tablename__ = "timeline_messages"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    seq: Mapped[int]
    type: Mapped[str]
    role: Mapped[str]
    source_ref: Mapped[dict[str, str] | None] = mapped_column(JSON)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("reports.id"), unique=True)
    __table_args__ = (UniqueConstraint("session_id", "seq"),)


class Asset(Entity, Base):
    __tablename__ = "assets"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    report_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    relative_path: Mapped[str]
    mime: Mapped[str]
    sha256: Mapped[str]
    source_url: Mapped[str | None]
    captured_at: Mapped[str]


class LocationCandidate(Entity, Base):
    __tablename__ = "location_candidates"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    provider_poi_id: Mapped[str]
    name: Mapped[str]
    city: Mapped[str]
    address: Mapped[str]
    center_gcj02: Mapped[dict[str, float]] = mapped_column(JSON)
    observed_at: Mapped[str] = mapped_column(default=utcnow)


class MockEvent(Entity, Base):
    __tablename__ = "mock_events"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    fixture_id: Mapped[str]
    product_topic: Mapped[str]
    safe_summary: Mapped[str]
    resolution_evidence: Mapped[str | None]
    source: Mapped[str] = mapped_column(default="mock")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    key: Mapped[str] = mapped_column(primary_key=True)
    operation: Mapped[str]
    body_hash: Mapped[str]
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=utcnow)
