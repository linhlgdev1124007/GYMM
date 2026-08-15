from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..controllers import members_controller
from ..database import get_db
from ..dependencies import current_user, require_roles
from ..models import User

router = APIRouter(prefix="/api", tags=["members"], dependencies=[Depends(current_user)])


@router.get("/members")
def list_members(q: str = "", status: str = "all", expiring_days: int = Query(14, ge=1, le=365, alias="expiringDays"), payment_status: str = Query("all", alias="paymentStatus"), overdue_days: int = Query(7, ge=1, le=365, alias="overdueDays"), view: str = "all", package_id: int | None = Query(None, alias="packageId"), trainer_id: int | None = Query(None, alias="trainerId"), sort: str = "newest", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return members_controller.list_members(db, q=q, member_status=status, expiring_days=expiring_days, payment_status=payment_status, overdue_days=overdue_days, view=view, package_id=package_id, trainer_id=trainer_id, sort=sort, page=page, page_size=page_size)


@router.get("/members/options")
def member_options(db: Session = Depends(get_db)):
    return members_controller.options(db)


@router.post("/members", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def create_member(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return members_controller.create_member(db, payload, user)


@router.get("/members/{member_id}")
def get_member(member_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return members_controller.get_member(db, member_id, include_audit=user.role == "admin")


@router.patch("/members/{member_id}", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def update_member(member_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return members_controller.update_member(db, member_id, payload, user)


@router.post("/members/{member_id}/reactivate", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def reactivate_member(member_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return members_controller.reactivate_member(db, member_id, user)


@router.get("/plans", dependencies=[Depends(require_roles("admin", "manager"))])
def list_plans(include_inactive: bool = Query(False, alias="includeInactive"), db: Session = Depends(get_db)):
    return members_controller.list_plans(db, include_inactive)


@router.post("/plans", dependencies=[Depends(require_roles("admin", "manager"))])
def create_plan(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return members_controller.create_plan(db, payload, user)


@router.patch("/plans/{plan_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def update_plan(plan_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return members_controller.update_plan(db, plan_id, payload, user)


@router.delete("/plans/{plan_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def delete_plan(plan_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return members_controller.delete_plan(db, plan_id, user)


@router.get("/memberships", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def list_memberships(q: str = "", status: str = "all", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return members_controller.list_memberships(db, q=q, membership_status=status, page=page, page_size=page_size)


@router.post("/memberships", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
async def create_membership(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    incoming = await request.form()
    form = {key: value for key, value in incoming.items() if key not in ("receipt", "receipts")}
    receipts = [item for item in [*incoming.getlist("receipts"), *incoming.getlist("receipt")] if getattr(item, "filename", None)]
    return await members_controller.create_membership(db, form, receipts, user)


@router.patch("/memberships/{membership_id}", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
async def update_membership(membership_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    incoming = await request.form()
    form = {key: value for key, value in incoming.items() if key not in ("receipt", "receipts")}
    receipts = [item for item in [*incoming.getlist("receipts"), *incoming.getlist("receipt")] if getattr(item, "filename", None)]
    return await members_controller.update_membership(db, membership_id, form, receipts, user)


@router.patch("/memberships/{membership_id}/debt-due-date", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def update_debt_due_date(membership_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return members_controller.update_debt_due_date(db, membership_id, payload, user)


@router.post("/payments/{payment_id}/receipts", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
async def upload_payment_receipts(payment_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    incoming = await request.form()
    receipts = [item for item in incoming.getlist("receipts") if getattr(item, "filename", None)]
    return await members_controller.upload_payment_receipts(db, payment_id, receipts, user)


@router.post("/memberships/{membership_id}/freeze")
def freeze_membership(membership_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return members_controller.freeze_membership(db, membership_id, payload, user)


@router.post("/memberships/{membership_id}/actions")
def membership_action(membership_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return members_controller.membership_action(db, membership_id, payload, user)
