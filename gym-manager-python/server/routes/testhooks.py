from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ..config import settings
from ..database import get_db
from ..models import Customer, Membership
from ..services.members_service import get_member
from ..timeutils import set_test_today, vietnam_today

router = APIRouter(prefix="/api/test-hooks", tags=["test-hooks"])


def _ensure_test_environment():
    if settings.environment != "test":
        raise HTTPException(404, "Not found")


@router.post("/time", dependencies=[Depends(_ensure_test_environment)])
def set_time(payload: dict):
    value = payload.get("today")
    set_test_today(date.fromisoformat(value) if value else None)
    return {"today": vietnam_today().isoformat()}


@router.get("/time", dependencies=[Depends(_ensure_test_environment)])
def get_time():
    return {"today": vietnam_today().isoformat()}


@router.get("/member-state", dependencies=[Depends(_ensure_test_environment)])
def member_state(customer_code: str = Query(..., alias="customerCode"), db: Session = Depends(get_db)):
    customer = (
        db.query(Customer)
        .options(
            joinedload(Customer.person),
            joinedload(Customer.memberships).joinedload(Membership.package),
            joinedload(Customer.memberships).joinedload(Membership.freezes),
        )
        .filter(Customer.customer_code == customer_code)
        .first()
    )
    if not customer:
        raise HTTPException(404, "Không tìm thấy hội viên.")
    return get_member(db, customer.id)
