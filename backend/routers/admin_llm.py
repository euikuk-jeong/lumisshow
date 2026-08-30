import os

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from backend.models.database import get_db
from backend.models.schemas import (
    LlmSettingsResponse,
    LlmSettingsUpdate,
    LlmSuggestRequest,
    LlmSuggestResponse,
    LlmTestConnectionResponse,
)
from backend.services import llm_settings as llm_settings_svc
from backend.services.album_style_suggest import suggest_style
from backend.services.auth import get_current_admin
from backend.services.llm_client import LlmError, call_llm

router = APIRouter(prefix="/api/admin/llm", tags=["admin-llm"])


@router.get("/settings", response_model=LlmSettingsResponse)
async def read_llm_settings(
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    return await llm_settings_svc.get_llm_settings(db)


@router.patch("/settings", response_model=LlmSettingsResponse)
async def update_llm_settings(
    body: LlmSettingsUpdate,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    if body.provider == "openai_compatible" and body.base_url is not None and not body.base_url.strip():
        raise HTTPException(status_code=422, detail="OpenAI 호환 provider는 base_url이 필요합니다")
    await llm_settings_svc.update_llm_settings(
        db,
        provider=body.provider,
        base_url=body.base_url,
        model=body.model,
        api_key=body.api_key,
    )
    return await llm_settings_svc.get_llm_settings(db)


@router.delete("/settings", response_model=LlmSettingsResponse)
async def reset_llm_settings(
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    await llm_settings_svc.reset_llm_settings(db)
    return await llm_settings_svc.get_llm_settings(db)


@router.post("/settings/test", response_model=LlmTestConnectionResponse)
async def test_llm_connection(
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    config = await llm_settings_svc.get_decrypted_config(db)
    if config is None:
        return LlmTestConnectionResponse(
            ok=False, message="LLM이 설정되지 않았거나 키를 복호화할 수 없습니다. 설정에서 다시 등록해주세요.",
        )
    try:
        await run_in_threadpool(call_llm, config, '이 메시지를 받으면 "ok"라고만 답하세요.')
    except LlmError as e:
        return LlmTestConnectionResponse(ok=False, message=str(e))
    return LlmTestConnectionResponse(ok=True, message="연결 성공")


@router.post("/suggest-style", response_model=LlmSuggestResponse)
async def suggest_album_style(
    body: LlmSuggestRequest,
    _: str = Depends(get_current_admin),
    db=Depends(get_db),
):
    config = await llm_settings_svc.get_decrypted_config(db)
    if config is None:
        raise HTTPException(status_code=409, detail="LLM이 설정되지 않았습니다. 설정에서 먼저 등록해주세요.")
    data_dir = os.getenv("DATA_DIR", "./testdata/data")
    try:
        result = await run_in_threadpool(
            suggest_style, config, body.name, body.description, data_dir,
        )
    except LlmError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return result
