from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..controllers import day_passes_controller
from ..database import get_db
from ..dependencies import require_roles
from ..models import User


router = APIRouter(prefix="/api/day-passes", tags=["day-passes"])
operators = require_roles("admin", "manager", "receptionist")


@router.get("")
def list_day_passes(
    q: str = "",
    status: str = "all",
    method: str = "all",
    date_from: str = Query("", alias="dateFrom"),
    date_to: str = Query("", alias="dateTo"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=10, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
    _user: User = Depends(operators),
):
    return day_passes_controller.list_day_passes(
        db,
        q=q,
        status=status,
        method=method,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get("/{day_pass_id}")
def get_day_pass(day_pass_id: int, db: Session = Depends(get_db), _user: User = Depends(operators)):
    return day_passes_controller.get_day_pass(db, day_pass_id)


@router.post("")
def create_day_pass(payload: dict, db: Session = Depends(get_db), user: User = Depends(operators)):
    return day_passes_controller.create_day_pass(db, payload, user)


@router.patch("/{day_pass_id}")
def update_day_pass(day_pass_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(operators)):
    return day_passes_controller.update_day_pass(db, day_pass_id, payload, user)


@router.post("/{day_pass_id}/void")
def void_day_pass(day_pass_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(operators)):
    return day_passes_controller.void_day_pass(db, day_pass_id, payload, user)
