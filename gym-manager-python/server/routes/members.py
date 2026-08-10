from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..controllers import members_controller
from ..database import get_db
from ..dependencies import current_user, require_roles

router = APIRouter(prefix="/api", tags=["members"], dependencies=[Depends(current_user)])


@router.get("/members")
def list_members(q: str = "", status: str = "all", expiring_days: int = Query(14, ge=1, le=365, alias="expiringDays"), view: str = "all", package_id: int | None = Query(None, alias="packageId"), trainer_id: int | None = Query(None, alias="trainerId"), sort: str = "newest", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return members_controller.list_members(db, q=q, member_status=status, expiring_days=expiring_days, view=view, package_id=package_id, trainer_id=trainer_id, sort=sort, page=page, page_size=page_size)


@router.get("/members/options")
def member_options(db: Session = Depends(get_db)):
    return members_controller.options(db)


@router.post("/members", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def create_member(payload: dict, db: Session = Depends(get_db)):
    return members_controller.create_member(db, payload)


@router.get("/members/{member_id}")
def get_member(member_id: int, db: Session = Depends(get_db)):
    return members_controller.get_member(db, member_id)


@router.patch("/members/{member_id}", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def update_member(member_id: int, payload: dict, db: Session = Depends(get_db)):
    return members_controller.update_member(db, member_id, payload)


@router.get("/plans")
def list_plans(include_inactive: bool = Query(False, alias="includeInactive"), db: Session = Depends(get_db)):
    return members_controller.list_plans(db, include_inactive)


@router.post("/plans", dependencies=[Depends(require_roles("admin", "manager"))])
def create_plan(payload: dict, db: Session = Depends(get_db)):
    return members_controller.create_plan(db, payload)


@router.patch("/plans/{plan_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def update_plan(plan_id: int, payload: dict, db: Session = Depends(get_db)):
    return members_controller.update_plan(db, plan_id, payload)


@router.get("/memberships")
def list_memberships(q: str = "", status: str = "all", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return members_controller.list_memberships(db, q=q, membership_status=status, page=page, page_size=page_size)


@router.post("/memberships", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
async def create_membership(request: Request, db: Session = Depends(get_db)):
    incoming = await request.form()
    form = {key: value for key, value in incoming.items() if key != "receipt"}
    return await members_controller.create_membership(db, form, incoming.get("receipt"))


@router.patch("/memberships/{membership_id}", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
async def update_membership(membership_id: int, request: Request, db: Session = Depends(get_db)):
    incoming = await request.form()
    form = {key: value for key, value in incoming.items() if key != "receipt"}
    return await members_controller.update_membership(db, membership_id, form, incoming.get("receipt"))


@router.patch("/memberships/{membership_id}/debt-due-date", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def update_debt_due_date(membership_id: int, payload: dict, db: Session = Depends(get_db)):
    return members_controller.update_debt_due_date(db, membership_id, payload)
