from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..controllers import insights_controller
from ..database import get_db
from ..dependencies import current_user, require_roles

router = APIRouter(prefix="/api", tags=["insights"], dependencies=[Depends(current_user)])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return insights_controller.dashboard(db)


@router.get("/reports", dependencies=[Depends(require_roles("admin", "manager"))])
def reports(date_from: str | None = Query(None, alias="dateFrom"), date_to: str | None = Query(None, alias="dateTo"), db: Session = Depends(get_db)):
    return insights_controller.reports(db, date_from, date_to)
