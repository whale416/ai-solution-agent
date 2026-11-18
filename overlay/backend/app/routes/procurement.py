"""Public-case workflow, evidence lookup and acceptance report routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import BACKEND_DIR
from app.models.procurement import ProcurementCase, ProcurementSession, PublicAnswer, PublicQuery
from app.services.procurement_report import render_procurement_report
from app.services.procurement_sessions import ProcurementSessions, StaleClarification
from app.services.procurement_sources import answer_public, load_case

router = APIRouter(prefix="/api/procurement", tags=["procurement-poc"])
_sessions = ProcurementSessions(BACKEND_DIR / "data" / "procurement.sqlite")


def session_store() -> ProcurementSessions:
    return _sessions


Sessions = Annotated[ProcurementSessions, Depends(session_store)]


class SessionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_id: str = Field(min_length=1, max_length=80)
    user_input: str = Field(min_length=1, max_length=4000)


class SessionResume(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(min_length=1, max_length=2000)


@router.get("/case")
def get_case() -> ProcurementCase:
    return load_case()


@router.post("/query")
def query_public(body: PublicQuery) -> PublicAnswer:
    return answer_public(body.question, body.project_id, body.as_of)


@router.post("/sessions", status_code=201)
def start_session(body: SessionCreate, sessions: Sessions) -> ProcurementSession:
    try:
        return sessions.start(body.case_id, body.user_input)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc


@router.get("/sessions/{session_id}")
def get_session(session_id: UUID, sessions: Sessions) -> ProcurementSession:
    try:
        return sessions.get(str(session_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc


@router.post("/sessions/{session_id}/resume")
def resume_session(session_id: UUID, body: SessionResume, sessions: Sessions) -> ProcurementSession:
    try:
        return sessions.resume(str(session_id), body.question_id, body.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc
    except StaleClarification as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/report")
def download_report(session_id: UUID, sessions: Sessions) -> Response:
    session = get_session(session_id, sessions)
    if session.status != "completed":
        raise HTTPException(status_code=409, detail="完成公开用例验证后可下载报告")
    filename = f"procurement-poc-{session_id.hex[:8]}.md"
    return Response(
        render_procurement_report(session),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
