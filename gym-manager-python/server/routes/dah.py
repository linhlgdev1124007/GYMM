from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_roles
from ..models import User
from ..services import dah_service


router = APIRouter(tags=["dah"])


async def _payload(request: Request) -> dict:
    data = await request.json()
    return data if isinstance(data, dict) else {}


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


@router.post("/api/employees/{employee_id}/dah-identity", dependencies=[Depends(require_roles("admin", "manager"))])
def assign_employee_identity(employee_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return dah_service.assign_identity_to_employee(db, employee_id, payload.get("eventId"), actor=user)
