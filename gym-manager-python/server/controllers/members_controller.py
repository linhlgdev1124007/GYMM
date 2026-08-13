from sqlalchemy.orm import Session

from ..services import members_service


def list_members(db: Session, **params): return members_service.list_members(db, **params)
def options(db: Session): return members_service.member_options(db)
def get_member(db: Session, member_id: int): return members_service.get_member(db, member_id)
def create_member(db: Session, payload: dict, actor=None): return members_service.create_member(db, payload, actor)
def update_member(db: Session, member_id: int, payload: dict, actor=None): return members_service.update_member(db, member_id, payload, actor)
def list_plans(db: Session, include_inactive: bool): return members_service.list_plans(db, include_inactive)
def create_plan(db: Session, payload: dict, actor=None): return members_service.create_plan(db, payload, actor)
def update_plan(db: Session, plan_id: int, payload: dict, actor=None): return members_service.update_plan(db, plan_id, payload, actor)
def delete_plan(db: Session, plan_id: int, actor=None): return members_service.delete_plan(db, plan_id, actor)
def list_memberships(db: Session, **params): return members_service.list_memberships(db, **params)
async def create_membership(db: Session, form: dict, receipts, actor=None): return await members_service.create_membership(db, form, receipts, actor)
async def update_membership(db: Session, membership_id: int, form: dict, receipts, actor=None): return await members_service.update_membership(db, membership_id, form, receipts, actor)
def update_debt_due_date(db: Session, membership_id: int, payload: dict, actor=None): return members_service.update_debt_due_date(db, membership_id, payload, actor)
async def upload_payment_receipts(db: Session, payment_id: int, receipts, actor=None): return await members_service.upload_payment_receipts(db, payment_id, receipts, actor)
def freeze_membership(db: Session, membership_id: int, payload: dict, actor): return members_service.freeze_membership(db, membership_id, payload, actor)
def membership_action(db: Session, membership_id: int, payload: dict, actor): return members_service.membership_action(db, membership_id, payload, actor)
