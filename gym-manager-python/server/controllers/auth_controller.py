import os

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..models import AuthSession, User
from ..security import create_session, token_digest, verify_password


def login(payload: dict, response: Response, db: Session):
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tên đăng nhập hoặc mật khẩu không đúng.")
    token = create_session(db, user)
    response.set_cookie("gym_session", token, httponly=True, samesite="strict", secure=os.getenv("GYM_SECURE_COOKIES", "0") == "1", max_age=7 * 86400, path="/")
    return {"user": {"id": user.id, "username": user.username, "displayName": user.display_name, "role": user.role}}


def logout(request: Request, response: Response, db: Session):
    token = request.cookies.get("gym_session")
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == token_digest(token)).delete()
        db.commit()
    response.delete_cookie("gym_session", path="/")
    return {"ok": True}


def me(user: User):
    return {"id": user.id, "username": user.username, "displayName": user.display_name, "role": user.role}
