from sqlalchemy.orm import Session

from ..services import members_service


def list_members(db: Session, **params): return members_service.list_members(db, **params)
def options(db: Session): return members_service.member_options(db)
def get_member(db: Session, member_id: int): return members_service.get_member(db, member_id)
def create_member(db: Session, payload: dict): return members_service.create_member(db, payload)
def update_member(db: Session, member_id: int, payload: dict): return members_service.update_member(db, member_id, payload)
def list_plans(db: Session, include_inactive: bool): return members_service.list_plans(db, include_inactive)
def create_plan(db: Session, payload: dict): return members_service.create_plan(db, payload)
def update_plan(db: Session, plan_id: int, payload: dict): return members_service.update_plan(db, plan_id, payload)
def list_memberships(db: Session, **params): return members_service.list_memberships(db, **params)
async def create_membership(db: Session, form: dict, receipt): return await members_service.create_membership(db, form, receipt)
async def update_membership(db: Session, membership_id: int, form: dict, receipt): return await members_service.update_membership(db, membership_id, form, receipt)
