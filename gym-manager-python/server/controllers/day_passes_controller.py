from sqlalchemy.orm import Session

from ..services import day_passes_service


def list_day_passes(db: Session, **params):
    return day_passes_service.list_day_passes(db, **params)


def get_day_pass(db: Session, day_pass_id: int):
    return day_passes_service.get_day_pass(db, day_pass_id)


def create_day_pass(db: Session, payload: dict, actor=None):
    return day_passes_service.create_day_pass(db, payload, actor)


def update_day_pass(db: Session, day_pass_id: int, payload: dict, actor=None):
    return day_passes_service.update_day_pass(db, day_pass_id, payload, actor)


def void_day_pass(db: Session, day_pass_id: int, payload: dict, actor=None):
    return day_passes_service.void_day_pass(db, day_pass_id, payload, actor)
