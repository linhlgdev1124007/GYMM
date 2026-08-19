import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dependencies import require_roles
from ..models import User
from ..services import dah_local_sync_service, dah_service


router = APIRouter(tags=["dah"])


async def _payload(request: Request) -> dict:
    data = await request.json()
    return data if isinstance(data, dict) else {}


def _require_agent_token(authorization: str = Header("")):
    expected = settings.dah_agent_token
    if not expected:
        raise HTTPException(503, "GYM_DAH_AGENT_TOKEN chưa được cấu hình trên server.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, expected):
        raise HTTPException(401, "DAH agent token không hợp lệ.")
    return True


@router.post("/Subscribe/heartbeat")
@router.post("/Subscribe/HeartBeat")
async def dah_heartbeat(request: Request, db: Session = Depends(get_db)):
    return dah_service.heartbeat(db, await _payload(request))


@router.post("/Subscribe/Snap")
async def dah_snap(request: Request, db: Session = Depends(get_db)):
    return dah_service.snap(db, await _payload(request))


@router.post("/Subscribe/Verify")
async def dah_verify(request: Request, db: Session = Depends(get_db)):
    return dah_service.verify(db, await _payload(request))


@router.get("/api/dah/identity-candidates", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def identity_candidates(
    limit: int = Query(12, ge=1, le=30),
    targetType: str = Query("member"),
    includeAssigned: bool = Query(False),
    db: Session = Depends(get_db),
):
    return dah_service.identity_candidates(db, limit, targetType, includeAssigned)


@router.get("/api/dah/events", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def dah_events(
    view: str = "all",
    limit: int = Query(50, ge=1, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=10, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
):
    return dah_service.dah_events(db, view=view, limit=limit, page=page, page_size=page_size)


@router.get("/api/dah/local-agent/status", dependencies=[Depends(require_roles("admin", "manager"))])
def local_agent_status():
    return dah_local_sync_service.status()


@router.post("/api/dah/local-agent/sync-request", dependencies=[Depends(require_roles("admin", "manager"))])
def local_agent_sync_request(
    payload: dict,
    user: User = Depends(require_roles("admin", "manager")),
):
    return dah_local_sync_service.create_sync_job(payload, actor=user)


@router.post("/api/dah/local-agent/heartbeat", dependencies=[Depends(_require_agent_token)])
async def local_agent_heartbeat(request: Request):
    return dah_local_sync_service.heartbeat(await _payload(request))


@router.get("/api/dah/local-agent/jobs/next", dependencies=[Depends(_require_agent_token)])
def local_agent_next_job(
    response: Response,
    agentId: str = Query(""),
    timeout: int = Query(55, ge=0, le=55),
):
    job = dah_local_sync_service.next_job(agentId, timeout=timeout)
    if not job:
        response.status_code = 204
        return None
    return job


@router.post("/api/dah/local-agent/jobs/{job_id}/result", dependencies=[Depends(_require_agent_token)])
async def local_agent_job_result(job_id: str, request: Request, db: Session = Depends(get_db)):
    return dah_local_sync_service.record_result(db, job_id, await _payload(request))


@router.post("/api/members/{member_id}/dah-identity", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def assign_identity(member_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return dah_service.assign_identity_to_customer(
        db,
        member_id,
        payload.get("eventId"),
        actor=user,
        replace=bool(payload.get("replace")),
        confirmation_text=payload.get("confirmationText"),
    )


@router.delete("/api/members/{member_id}/dah-identity", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def delete_identity(member_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return dah_service.delete_customer_identity(
        db,
        member_id,
        confirmation_text=payload.get("confirmationText"),
        actor=user,
    )


@router.post("/api/employees/{employee_id}/dah-identity", dependencies=[Depends(require_roles("admin", "manager"))])
def assign_employee_identity(employee_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return dah_service.assign_identity_to_employee(db, employee_id, payload.get("eventId"), actor=user)
