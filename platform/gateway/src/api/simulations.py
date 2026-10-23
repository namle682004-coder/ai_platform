"""
Simulation & Interactive Playground Data APIs.
Compliant with Clean Architecture DDD.
Allows sandbox users, staff developers, and frontend portals to persist test runs,
multi-turn chat histories, OCR document extractions, and biometric verification sessions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from common.models.simulation import SimulationRun
from common.models.chat_session import ConversationSession, ChatMessageRecord, PromptTemplate
from common.models.ocr_record import OCRDocumentRecord
from common.models.ekyc_session import EKYCVerificationSession
from common.models.audio_record import AudioTranscriptionRecord, AudioSynthesisRecord
from common.repositories.mongo_repositories import (
    simulation_run_repository,
    chat_session_repository,
    ocr_record_repository,
    ekyc_session_repository,
    audio_record_repository,
)

router = APIRouter(prefix="/v1/simulations", tags=["Simulation & Playground Data"])


def _resolve_user_id(request: Request) -> str:
    """Extract authenticated user email or fallback to demo user."""
    return getattr(request.state, "user_email", "admin@company.com") or "admin@company.com"


# ---------------------------------------------------------------------------
# 1. General Simulation Runs
# ---------------------------------------------------------------------------


@router.post("/runs", summary="Record a Sandbox Simulation Run", response_model=dict)
async def create_simulation_run(run: SimulationRun, request: Request):
    """Save an interactive playground execution run (inputs, outputs, latency, tokens)."""
    user_id = _resolve_user_id(request)
    data = run.model_dump()
    data["user_id"] = user_id
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()
    return await simulation_run_repository.create_run(data)


@router.get("/runs", summary="List Sandbox Simulation Runs")
async def list_simulation_runs(
    request: Request,
    domain: Optional[str] = Query(None, description="Filter by AI domain (chat, ocr, audio, etc.)"),
    status: Optional[str] = Query(None, description="Filter by status (success, failed)"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
):
    """List simulation history for the current user/tenant with optional filters."""
    user_id = _resolve_user_id(request)
    runs = await simulation_run_repository.list_runs(
        user_id=user_id, domain=domain, status=status, limit=limit, skip=skip
    )
    return {"object": "list", "data": runs, "count": len(runs)}


@router.get("/runs/{run_id}", summary="Get Detailed Simulation Run")
async def get_simulation_run(run_id: str):
    """Retrieve full input/output payload and execution metrics for a specific run."""
    run = await simulation_run_repository.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Simulation run '{run_id}' not found.")
    return run


@router.delete("/runs/{run_id}", summary="Delete a Simulation Run")
async def delete_simulation_run(run_id: str):
    deleted = await simulation_run_repository.delete_run(run_id)
    return {"success": deleted, "run_id": run_id}


# ---------------------------------------------------------------------------
# 2. Multi-Turn Chat Sessions & Message History
# ---------------------------------------------------------------------------


class CreateChatSessionRequest(BaseModel):
    title: str = Field(default="New Conversation")
    model_alias: str = Field(default="chat-general-standard")
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1024


@router.post("/chat/sessions", summary="Create Multi-Turn Chat Conversation Session")
async def create_chat_session(payload: CreateChatSessionRequest, request: Request):
    """Create a persistent conversation thread in the playground."""
    user_id = _resolve_user_id(request)
    session = ConversationSession(
        user_id=user_id,
        title=payload.title,
        model_alias=payload.model_alias,
        system_prompt=payload.system_prompt,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    data = session.model_dump()
    data["created_at"] = data["created_at"].isoformat()
    data["updated_at"] = data["updated_at"].isoformat()
    return await chat_session_repository.create_session(data)


@router.get("/chat/sessions", summary="List User Chat Sessions")
async def list_chat_sessions(request: Request, limit: int = Query(50, ge=1, le=100)):
    user_id = _resolve_user_id(request)
    sessions = await chat_session_repository.list_sessions(user_id=user_id, limit=limit)
    return {"object": "list", "data": sessions, "count": len(sessions)}


@router.get("/chat/sessions/{session_id}", summary="Get Chat Session Details")
async def get_chat_session(session_id: str):
    session = await chat_session_repository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Chat session '{session_id}' not found.")
    return session


@router.delete("/chat/sessions/{session_id}", summary="Delete Chat Session and Messages")
async def delete_chat_session(session_id: str):
    await chat_session_repository.delete_session(session_id)
    return {"success": True, "session_id": session_id}


class AddChatMessageRequest(BaseModel):
    role: str = Field(..., description="user, assistant, or system")
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0


@router.post("/chat/sessions/{session_id}/messages", summary="Append Message to Chat Session")
async def add_chat_message(session_id: str, payload: AddChatMessageRequest):
    """Record a user or assistant response into the conversation thread."""
    session = await chat_session_repository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Chat session '{session_id}' not found.")

    msg = ChatMessageRecord(
        session_id=session_id,
        role=payload.role,
        content=payload.content,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        latency_ms=payload.latency_ms,
    )
    data = msg.model_dump()
    data["created_at"] = data["created_at"].isoformat()
    return await chat_session_repository.add_message(data)


@router.get("/chat/sessions/{session_id}/messages", summary="Retrieve Message Thread History")
async def get_chat_messages(session_id: str, limit: int = Query(100, ge=1, le=500)):
    messages = await chat_session_repository.get_session_messages(session_id, limit=limit)
    return {"object": "list", "session_id": session_id, "data": messages, "count": len(messages)}


# ---------------------------------------------------------------------------
# 3. Prompt Templates
# ---------------------------------------------------------------------------


class CreatePromptTemplateRequest(BaseModel):
    title: str
    category: str = "general"
    template_content: str
    variables: list[str] = Field(default_factory=list)
    is_public: bool = False


@router.post("/chat/templates", summary="Save Custom Prompt Template")
async def create_prompt_template(payload: CreatePromptTemplateRequest, request: Request):
    user_id = _resolve_user_id(request)
    tmpl = PromptTemplate(
        user_id=user_id,
        title=payload.title,
        category=payload.category,
        template_content=payload.template_content,
        variables=payload.variables,
        is_public=payload.is_public,
    )
    data = tmpl.model_dump()
    data["created_at"] = data["created_at"].isoformat()
    return await chat_session_repository.create_prompt_template(data)


@router.get("/chat/templates", summary="List Saved Prompt Templates")
async def list_prompt_templates(request: Request):
    user_id = _resolve_user_id(request)
    templates = await chat_session_repository.list_prompt_templates(user_id=user_id)
    return {"object": "list", "data": templates, "count": len(templates)}


# ---------------------------------------------------------------------------
# 4. OCR Document Records
# ---------------------------------------------------------------------------


@router.post("/ocr/records", summary="Save OCR Document Extraction Record")
async def create_ocr_record(record: OCRDocumentRecord, request: Request):
    user_id = _resolve_user_id(request)
    data = record.model_dump()
    data["user_id"] = user_id
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()
    return await ocr_record_repository.create_record(data)


@router.get("/ocr/records", summary="List OCR Document Records")
async def list_ocr_records(
    request: Request,
    doc_type: Optional[str] = Query(None, description="id_card, driver_license, passport, invoice"),
    limit: int = Query(50, ge=1, le=100),
):
    user_id = _resolve_user_id(request)
    records = await ocr_record_repository.list_records(user_id=user_id, doc_type=doc_type, limit=limit)
    return {"object": "list", "data": records, "count": len(records)}


@router.get("/ocr/records/{record_id}", summary="Get Detailed OCR Record")
async def get_ocr_record(record_id: str):
    rec = await ocr_record_repository.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"OCR record '{record_id}' not found.")
    return rec


# ---------------------------------------------------------------------------
# 5. eKYC Biometric Verification Sessions
# ---------------------------------------------------------------------------


@router.post("/ekyc/sessions", summary="Save eKYC Biometric Verification Run")
async def create_ekyc_session(session: EKYCVerificationSession, request: Request):
    user_id = _resolve_user_id(request)
    data = session.model_dump()
    data["user_id"] = user_id
    if isinstance(data.get("verified_at"), datetime):
        data["verified_at"] = data["verified_at"].isoformat()
    return await ekyc_session_repository.create_session(data)


@router.get("/ekyc/sessions", summary="List eKYC Verification Sessions")
async def list_ekyc_sessions(request: Request, limit: int = Query(50, ge=1, le=100)):
    user_id = _resolve_user_id(request)
    sessions = await ekyc_session_repository.list_sessions(user_id=user_id, limit=limit)
    return {"object": "list", "data": sessions, "count": len(sessions)}


# ---------------------------------------------------------------------------
# 6. Audio Speech-to-Text & Text-to-Speech Records
# ---------------------------------------------------------------------------


@router.post("/audio/transcriptions", summary="Save STT Transcription Record")
async def create_stt_record(record: AudioTranscriptionRecord, request: Request):
    user_id = _resolve_user_id(request)
    data = record.model_dump()
    data["user_id"] = user_id
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()
    return await audio_record_repository.create_transcription(data)


@router.get("/audio/transcriptions", summary="List STT Transcription Records")
async def list_stt_records(request: Request, limit: int = Query(50, ge=1, le=100)):
    user_id = _resolve_user_id(request)
    records = await audio_record_repository.list_transcriptions(user_id=user_id, limit=limit)
    return {"object": "list", "data": records, "count": len(records)}


@router.post("/audio/syntheses", summary="Save TTS Synthesis Record")
async def create_tts_record(record: AudioSynthesisRecord, request: Request):
    user_id = _resolve_user_id(request)
    data = record.model_dump()
    data["user_id"] = user_id
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()
    return await audio_record_repository.create_synthesis(data)


@router.get("/audio/syntheses", summary="List TTS Synthesis Records")
async def list_tts_records(request: Request, limit: int = Query(50, ge=1, le=100)):
    user_id = _resolve_user_id(request)
    records = await audio_record_repository.list_syntheses(user_id=user_id, limit=limit)
    return {"object": "list", "data": records, "count": len(records)}
