from sqlalchemy.orm import Session
from ..services import operations_service

def list_trainers(db: Session, **params): return operations_service.list_trainers(db, **params)
def create_trainer(db: Session, payload: dict): return operations_service.create_trainer(db, payload)
def update_trainer(db: Session, trainer_id: int, payload: dict): return operations_service.update_trainer(db, trainer_id, payload)
def delete_trainer(db: Session, trainer_id: int): return operations_service.delete_trainer(db, trainer_id)
def list_pt(db: Session, **params): return operations_service.list_pt(db, **params)
def create_pt(db: Session, member_id: int, payload: dict): return operations_service.create_pt(db, member_id, payload)
def update_pt(db: Session, enrollment_id: int, payload: dict): return operations_service.update_pt(db, enrollment_id, payload)
def checkin_candidates(db: Session, q: str): return operations_service.checkin_candidates(db, q)
def recent_checkins(db: Session, limit: int): return operations_service.recent_checkins(db, limit)
def create_checkin(db: Session, payload: dict): return operations_service.create_checkin(db, payload)
def checkout(db: Session, session_id: int): return operations_service.checkout(db, session_id)
def list_payments(db: Session, **params): return operations_service.list_payments(db, **params)
def settings(db: Session): return operations_service.settings(db)
