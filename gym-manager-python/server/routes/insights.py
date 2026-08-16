from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..controllers import insights_controller
from ..database import get_db
from ..dependencies import current_user, require_roles
from ..models import User

router = APIRouter(prefix="/api", tags=["insights"], dependencies=[Depends(current_user)])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return insights_controller.dashboard(db, user.role in {"admin", "manager"})


@router.get("/reports", dependencies=[Depends(require_roles("admin", "manager"))])
def reports(date_from: str | None = Query(None, alias="dateFrom"), date_to: str | None = Query(None, alias="dateTo"), db: Session = Depends(get_db)):
    return insights_controller.reports(db, date_from, date_to)


@router.get("/alerts")
def alerts(
    expiring_days: int = Query(14, ge=1, le=90, alias="expiringDays"),
    pt_sessions: int = Query(3, ge=0, le=20, alias="ptSessions"),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return insights_controller.alerts(db, user.id, expiring_days, pt_sessions, limit, user.role in {"admin", "manager"})


@router.patch("/alerts/{alert_key}/read")
def mark_alert_read(alert_key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not insights_controller.mark_alert_read(db, user.id, alert_key, user.role in {"admin", "manager"}):
        raise HTTPException(status_code=404, detail="Cảnh báo không còn tồn tại.")
    return {"ok": True}


@router.post("/alerts/read-all")
def mark_all_alerts_read(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"ok": True, "marked": insights_controller.mark_all_alerts_read(db, user.id, user.role in {"admin", "manager"})}
