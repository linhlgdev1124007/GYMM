from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..controllers import users_controller
from ..database import get_db
from ..dependencies import require_roles
from ..models import User

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
def users(db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    return users_controller.list_users(db)


@router.post("")
def create_user(payload: dict, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    return users_controller.create_user(db, payload, actor)


@router.patch("/{user_id}")
def update_user(user_id: int, payload: dict, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    return users_controller.update_user(db, user_id, payload, actor)


@router.patch("/{user_id}/password")
def update_password(user_id: int, payload: dict, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    return users_controller.update_password(db, user_id, payload, actor)
