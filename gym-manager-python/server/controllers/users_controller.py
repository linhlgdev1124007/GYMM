from sqlalchemy.orm import Session

from ..services import users_service


def list_users(db: Session):
    return users_service.list_users(db)


def create_user(db: Session, payload: dict, actor):
    return users_service.create_user(db, payload, actor)


def update_user(db: Session, user_id: int, payload: dict, actor):
    return users_service.update_user(db, user_id, payload, actor)


def update_password(db: Session, user_id: int, payload: dict, actor):
    return users_service.update_password(db, user_id, payload, actor)
