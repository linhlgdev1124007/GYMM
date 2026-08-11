from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..controllers import auth_controller
from ..database import get_db
from ..dependencies import current_user
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: dict, request: Request, response: Response, db: Session = Depends(get_db)):
    return auth_controller.login(payload, request, response, db)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    return auth_controller.logout(request, response, db)


@router.get("/me")
def me(request: Request, response: Response, user: User = Depends(current_user)):
    return auth_controller.me(request, response, user)
