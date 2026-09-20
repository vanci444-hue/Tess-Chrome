"""CRM 自动预览：联系方式规则抽取留本机，脱敏后才交模型提取历史背景。"""
import re
from typing import Any

from pydantic import Field
from src.adapters.base import ProviderError
from src.config.settings import Settings
from src.db.models import new_id, utcnow
from src.models.contracts import BusinessError, Contract
from src.services.agent.context import as_data, prompt
from src.services.agent.contracts import ProposedFact
from src.services.facts import FACT_KEYS
from src.services.reports import safe_projection


class CRMResult(Contract):
    nickname: str | None = None
    facts: list[ProposedFact] = Field(default_factory=list, max_length=30)


async def extract_crm(text: str, config: Settings, provider: Any = None) -> dict[str, Any]:
    if provider is None:
        from src.adapters.llm import BailianLLMProvider
        provider = BailianLLMProvider(config)
    phones = re.findall(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)', text)
    emails = re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
    safe = safe_projection(text)
    # 接受有明确国家区号的国际格式；多号码不猜主联系人，但全部先脱敏。
    international = re.findall(r'(?<![\w\d])(?:\+|00)[1-9][\d ()（）.\-]{5,25}\d(?!\d)', text)
    for raw in international:
        digits = re.sub(r'\D', '', raw)
        normalized = '+' + (digits[2:] if raw.startswith('00') else digits)
        if 7 <= len(normalized) - 1 <= 15:
            phones.append(normalized)
        safe = safe.replace(raw, '[联系方式已隐藏]')
        safe = safe_projection(safe, phone=normalized)
    phones = list(dict.fromkeys(phones))
    try:
        response = await provider.complete([
            {'role': 'system', 'content': prompt('crm_extract')},
            {'role': 'user', 'content': as_data({'text': safe, 'allowed_fact_keys': sorted(FACT_KEYS)})}],
            response_format={'type': 'json_object'})
    except ProviderError as error:
        raise BusinessError(error.message, error.code, 503, "DEPENDENCY_UNAVAILABLE") from error
    try:
        result = CRMResult.model_validate_json(response.get('content') or '')
        if result.nickname and result.nickname not in safe:
            raise ValueError('unsupported nickname')
        for f in result.facts:
            if f.evidence_quote not in safe:
                raise ValueError('unsupported evidence')
    except ValueError as error:
        raise BusinessError('CRM预览未获得可靠结构，可改手动填写', 'INVALID_MODEL_OUTPUT',
                            502, 'DEPENDENCY_UNAVAILABLE') from error
    return {'proposed': {'nickname': result.nickname, 'phone': phones[0] if len(phones) == 1 else None,
                         'email': emails[0] if len(emails) == 1 else None},
        'historical_facts': [{'id': new_id(), 'key': f.key, 'value': safe_projection(f.value),
            'unit': f.unit, 'state': 'proposed', 'source_kind': 'crm_paste', 'source_id': 'crm-preview',
            'observed_at': utcnow(), 'scope': 'historical', 'subject_id': f.subject_id,
            'evidence_note': f.evidence_quote, 'supersedes': []}
            for f in result.facts if f.key in FACT_KEYS and f.key != 'resolved_concerns']}
