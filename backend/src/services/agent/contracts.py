"""Agent 边界契约：用户输入与模型输出分别验证，不接受模型写数据库对象。"""
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator
from src.config.settings import settings
from src.models.contracts import Contract, ReportSummaryText

Intent = Literal['qa', 'supplement_facts', 'answer_question', 'prepare_report',
                 'edit_draft', 'analyze', 'followup', 'clarify']


class Submission(Contract):
    text: str = Field(min_length=1, max_length=settings.max_text_chars)
    source: Literal['sales_text', 'asr_corrected'] = 'sales_text'
    asr_session_id: UUID | None = None
    expected_revision: int = Field(ge=1)
    reply_to_run_id: UUID | None = None
    reply_to_question_ids: list[UUID] = Field(default_factory=list, max_length=3)
    continue_run_id: UUID | None = None
    target_draft_id: UUID | None = None
    target_draft_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def references(self):
        if self.source == 'asr_corrected' and not self.asr_session_id:
            raise ValueError('已纠正语音必须关联本次语音会话')
        if self.continue_run_id and self.reply_to_run_id:
            raise ValueError('回答与继续不能同时使用')
        if self.reply_to_question_ids and not self.reply_to_run_id:
            raise ValueError('问题引用必须包含原运行')
        if (self.target_draft_id is None) != (self.target_draft_revision is None):
            raise ValueError('草稿和修订必须成对提供')
        return self


class RunSubmission(Contract):
    intent: Literal['analyze', 'prepare_report', 'followup']
    message: str | None = Field(default=None, min_length=1, max_length=settings.max_text_chars)
    expected_revision: int = Field(ge=1)
    continue_run_id: UUID | None = None


class RouteDecision(Contract):
    intent: Intent
    effective_intent: str | None = None
    target_draft_id: UUID | None = None
    reply_to_run_id: UUID | None = None
    question_ids: list[UUID] = Field(default_factory=list, max_length=3)
    normalized_request: str = ''
    retrieval_query: str | None = None
    clarification: str | None = None


class ProposedFact(Contract):
    key: str
    value: Any = None
    unit: str | None = None
    # unknown 仍由销售确认卡确认，模型不得自行形成 confirmed。
    state: Literal['proposed', 'conflict', 'unknown'] = 'proposed'
    evidence_quote: str = Field(min_length=1)
    subject_id: str | None = None


class SuggestedQuestion(Contract):
    text: str = Field(min_length=1, max_length=500)
    key: str | None = None
    required: bool = False
    fact_ids: list[str] = Field(default_factory=list)


class Extraction(Contract):
    facts: list[ProposedFact] = Field(default_factory=list, max_length=30)
    questions: list[SuggestedQuestion] = Field(default_factory=list, max_length=3)


class Finish(Contract):
    status: Literal['ready', 'needs_confirmation', 'partial']
    summary: str = Field(default='', max_length=8000)
    questions: list[SuggestedQuestion] = Field(default_factory=list, max_length=3)
    sections: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    report_summary: ReportSummaryText | None = None
    source_ids: list[str] = Field(default_factory=list, max_length=40)
    rejected: bool = False
