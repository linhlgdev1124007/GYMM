import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import SessionLocal, get_db
from ..dependencies import require_roles
from ..models import AuthSession, CheckinSpeechEvent, User
from ..security import token_digest
from ..timeutils import utc_now
from ..services.checkin_speech_service import speech_event_data, speech_settings_data, update_speech_settings


router = APIRouter(prefix="/api/checkin-speech", tags=["checkin-speech"])
listeners = require_roles("admin", "manager", "receptionist")


def _authorize_event_stream(request: Request):
    token = request.cookies.get("gym_session")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    db = SessionLocal()
    try:
        auth = db.query(AuthSession).options(joinedload(AuthSession.user)).filter(
            AuthSession.token_hash == token_digest(token),
            AuthSession.expires_at > utc_now(),
        ).first()
        if not auth or not auth.user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        if auth.user.role not in {"admin", "manager", "receptionist"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action")
    finally:
        db.close()


@router.get("/config")
def config(db: Session = Depends(get_db), _user: User = Depends(listeners)):
    data = speech_settings_data(db)
    db.commit()
    return data


@router.put("/config")
def update_config(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return update_speech_settings(db, payload, user)


@router.get("/events")
async def events(request: Request):
    _authorize_event_stream(request)
    raw_last_id = request.headers.get("last-event-id", "")
    try:
        cursor = max(int(raw_last_id), 0)
    except ValueError:
        cursor = 0
    if not cursor:
        db = SessionLocal()
        try:
            cursor = db.query(func.max(CheckinSpeechEvent.id)).scalar() or 0
        finally:
            db.close()

    async def stream():
        nonlocal cursor
        idle_ticks = 0
        yield "retry: 2000\n\n"
        while not await request.is_disconnected():
            db = SessionLocal()
            try:
                rows = db.query(CheckinSpeechEvent).filter(CheckinSpeechEvent.id > cursor).order_by(CheckinSpeechEvent.id).limit(20).all()
                for row in rows:
                    cursor = row.id
                    payload = json.dumps(speech_event_data(row), ensure_ascii=False)
                    yield f"id: {row.id}\nevent: checkin\ndata: {payload}\n\n"
                    idle_ticks = 0
            finally:
                db.close()
            idle_ticks += 1
            if idle_ticks >= 15:
                yield ": keep-alive\n\n"
                idle_ticks = 0
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
