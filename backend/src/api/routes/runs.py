"""明确提交才受理业务run；返回202后由管理器异步执行，GET只读进度。"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.api.responses import APIResponse, success_response
from src.api.deps import get_db, idempotency_key
from src.models.contracts import BusinessError, DraftUpdate
from src.repositories.store import Store
from src.services.agent.contracts import RunSubmission, Submission
from src.services.agent.submissions import accept_submission, read_run

router = APIRouter(prefix='/api/sessions/{session_id}', tags=['runs'])


def runner(request: Request):
    manager = getattr(request.app.state, 'agent_runner', None)
    if manager is None:
        raise BusinessError('Agent 尚未装配，已保存内容不受影响', 'AGENT_NOT_REGISTERED',
                            503, 'DEPENDENCY_UNAVAILABLE')
    return manager


async def submit(session_id: str, data: Submission, kind: str, request: Request,
                 db: AsyncSession, key: str, *, has_text: bool = True):
    manager = runner(request)
    result = await accept_submission(Store(db), session_id, data, key, kind, has_text=has_text)
    # 先持久化再调度。任务只在HTTP事务释放write_lock后开始读取，绝不等待模型才返回。
    await db.commit()
    manager.schedule(result['run_id'])
    return success_response(result, message='已接收', request_id=request.state.request_id)


@router.post('/messages', status_code=202, response_model=APIResponse[dict])
async def message(session_id: UUID, data: Submission, request: Request,
                  db: AsyncSession = Depends(get_db), key: str = Depends(idempotency_key)):
    return await submit(str(session_id), data, 'interaction', request, db, key)


@router.post('/inputs', status_code=202, response_model=APIResponse[dict])
async def input_text(session_id: UUID, data: Submission, request: Request,
                     db: AsyncSession = Depends(get_db), key: str = Depends(idempotency_key)):
    return await submit(str(session_id), data, 'extract_context', request, db, key)


@router.post('/runs', status_code=202, response_model=APIResponse[dict])
async def run(session_id: UUID, data: RunSubmission, request: Request,
              db: AsyncSession = Depends(get_db), key: str = Depends(idempotency_key)):
    submission = Submission(text=data.message or {'analyze': '分析当前方案',
        'prepare_report': '生成试驾报告草稿', 'followup': '整理产品相关跟进摘要'}[data.intent],
        expected_revision=data.expected_revision, continue_run_id=data.continue_run_id)
    return await submit(str(session_id), submission, data.intent, request, db, key,
                        has_text=data.message is not None)


@router.get('/runs/{run_id}', response_model=APIResponse[dict])
async def state(session_id: UUID, run_id: UUID, request: Request,
                after_seq: int = Query(default=0, ge=0), db: AsyncSession = Depends(get_db)):
    return success_response(await read_run(Store(db), str(session_id), str(run_id), after_seq),
                            message='ok', request_id=request.state.request_id)


async def draft_editor(session_id: str, draft_id: str, data: DraftUpdate,
                       request: Request, db: AsyncSession):
    try:
        key = str(UUID(request.headers.get('Idempotency-Key', '')))
    except ValueError as error:
        raise BusinessError('自然语言修改需要请求标识', 'IDEMPOTENCY_KEY_REQUIRED',
                            400, 'VALIDATION_ERROR') from error
    submission = Submission(text=data.change_request or '', expected_revision=data.expected_revision,
                            target_draft_id=UUID(draft_id), target_draft_revision=data.draft_revision)
    envelope = await submit(session_id, submission, 'edit_draft', request, db, key)
    # 显式Response绕过原PATCH同步DraftUpdated的response_model，保留统一PyCore信封。
    return JSONResponse(envelope.model_dump(mode='json'), status_code=202)
